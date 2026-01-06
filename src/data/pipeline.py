#!/usr/bin/env python3
"""
Data Quality Analysis and Gap Filling Pipeline for RiseTrader.

This script:
1. Analyzes existing data coverage and gaps
2. Downloads missing data from free sources (Dukascopy, HistData)
3. Merges and validates data quality
4. Imports into PostgreSQL database

Current Data Status (as of Jan 5, 2026):
- CrudeOIL BC M1: 2009-08-04 to 2025-03-28 (5.4M records) ✓
- CrudeOIL MT4 M1: 2024-08-19 to 2026-01-05 (74K records, 69% missing days)
- DXY BC M1: 2008-05-04 to 2025-03-31 (5.7M records) ✓
- VIX BC M1: 2014-03-17 to 2025-04-01 (1.9M records) ✓

Gap to fill: April 2025 to January 2026 (~9 months)
"""
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.base import DataSource, Timeframe
from src.data.dukascopy import DukascopyDownloader
from src.data.histdata import HistDataDownloader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('data/data_pipeline.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DataCoverage:
    """Data coverage information for a symbol."""
    symbol: str
    source: DataSource
    timeframe: Timeframe
    start_date: date
    end_date: date
    record_count: int
    missing_days: int
    completeness_pct: float


@dataclass
class GapInfo:
    """Information about a data gap."""
    symbol: str
    start_date: date
    end_date: date
    trading_days: int
    priority: str  # 'high', 'medium', 'low'


class DataPipelineManager:
    """
    Manages the data pipeline for RiseTrader.
    
    Responsibilities:
    - Analyze data coverage and identify gaps
    - Download data from multiple sources
    - Merge and validate data
    - Import into database
    """
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize downloaders
        self.downloaders = {
            DataSource.DUKASCOPY: DukascopyDownloader(self.data_dir / "dukascopy"),
            DataSource.HISTDATA: HistDataDownloader(self.data_dir / "histdata"),
        }
        
        # Symbol priorities
        self.symbol_priorities = {
            "CrudeOIL": "high",
            "GOLD": "high",
            "DXY": "medium",
            "VIX": "medium",
            "SPX500": "low",
        }
    
    async def analyze_database_coverage(self) -> Dict[str, List[DataCoverage]]:
        """Analyze current data coverage in database."""
        from sqlalchemy import create_engine, text
        
        engine = create_engine("postgresql://postgres:risetrader2024@localhost:5433/risetrader")
        
        query = """
        WITH symbol_coverage AS (
            SELECT 
                symbol,
                source,
                timeframe,
                MIN(time)::date as start_date,
                MAX(time)::date as end_date,
                COUNT(*) as record_count,
                COUNT(DISTINCT DATE(time)) as days_with_data
            FROM market_data
            WHERE timeframe = 'M1'
            GROUP BY symbol, source, timeframe
        ),
        date_range AS (
            SELECT 
                symbol,
                source,
                generate_series(start_date, end_date, '1 day'::interval)::date as date
            FROM symbol_coverage
        ),
        trading_days AS (
            SELECT symbol, source, COUNT(*) as total_trading_days
            FROM date_range
            WHERE EXTRACT(DOW FROM date) NOT IN (0, 6)
            GROUP BY symbol, source
        )
        SELECT 
            sc.symbol,
            sc.source,
            sc.timeframe,
            sc.start_date,
            sc.end_date,
            sc.record_count,
            sc.days_with_data,
            td.total_trading_days,
            td.total_trading_days - sc.days_with_data as missing_days,
            ROUND(sc.days_with_data::numeric / NULLIF(td.total_trading_days, 0) * 100, 2) as completeness_pct
        FROM symbol_coverage sc
        JOIN trading_days td ON sc.symbol = td.symbol AND sc.source = td.source
        ORDER BY sc.symbol, sc.source;
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
        
        coverage = {}
        for row in rows:
            symbol = row[0]
            if symbol not in coverage:
                coverage[symbol] = []
            
            coverage[symbol].append(DataCoverage(
                symbol=symbol,
                source=DataSource(row[1]),
                timeframe=Timeframe(row[2]),
                start_date=row[3],
                end_date=row[4],
                record_count=row[5],
                missing_days=row[8] or 0,
                completeness_pct=float(row[9] or 0)
            ))
        
        return coverage
    
    def identify_gaps(self, coverage: Dict[str, List[DataCoverage]], 
                     target_end: date = None) -> List[GapInfo]:
        """Identify data gaps that need to be filled."""
        if target_end is None:
            target_end = date.today()
        
        gaps = []
        
        for symbol, coverages in coverage.items():
            # Find the latest end date across all sources
            latest_end = max(c.end_date for c in coverages)
            
            if latest_end < target_end:
                # Calculate trading days in gap
                trading_days = sum(
                    1 for d in pd.date_range(latest_end + timedelta(days=1), target_end)
                    if d.dayofweek < 5
                )
                
                gaps.append(GapInfo(
                    symbol=symbol,
                    start_date=latest_end + timedelta(days=1),
                    end_date=target_end,
                    trading_days=trading_days,
                    priority=self.symbol_priorities.get(symbol, "low")
                ))
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        gaps.sort(key=lambda g: (priority_order[g.priority], -g.trading_days))
        
        return gaps
    
    async def download_gap_data(self, gap: GapInfo, 
                               source: DataSource = DataSource.DUKASCOPY):
        """Download data to fill a gap."""
        logger.info(f"Downloading {gap.symbol} from {source.value}: {gap.start_date} to {gap.end_date}")
        
        downloader = self.downloaders.get(source)
        if not downloader:
            raise ValueError(f"No downloader available for {source.value}")
        
        result = await downloader.download(
            symbol=gap.symbol,
            start_date=gap.start_date,
            end_date=gap.end_date,
            timeframe=Timeframe.M1
        )
        
        return result
    
    async def fill_all_gaps(self, gaps: List[GapInfo], 
                           primary_source: DataSource = DataSource.DUKASCOPY):
        """Fill all identified gaps."""
        results = []
        
        for gap in gaps:
            logger.info(f"\n{'='*60}")
            logger.info(f"Filling gap for {gap.symbol}: {gap.start_date} to {gap.end_date}")
            logger.info(f"Priority: {gap.priority}, Trading days: {gap.trading_days}")
            
            try:
                result = await self.download_gap_data(gap, primary_source)
                results.append((gap, result))
                
                if result.success:
                    logger.info(f"✓ Downloaded {result.bars_count} bars to {result.file_path}")
                else:
                    logger.warning(f"✗ Download failed: {result.error}")
                    
                    # Try fallback source
                    if primary_source == DataSource.DUKASCOPY:
                        logger.info("Trying HistData as fallback...")
                        result = await self.download_gap_data(gap, DataSource.HISTDATA)
                        results.append((gap, result))
                        
            except Exception as e:
                logger.error(f"Error filling gap for {gap.symbol}: {e}")
        
        return results
    
    def print_coverage_report(self, coverage: Dict[str, List[DataCoverage]]):
        """Print a formatted coverage report."""
        print("\n" + "="*80)
        print("DATA COVERAGE REPORT")
        print("="*80)
        
        for symbol, coverages in sorted(coverage.items()):
            print(f"\n{symbol}:")
            print("-" * 40)
            
            for c in coverages:
                status = "✓" if c.completeness_pct > 95 else "⚠" if c.completeness_pct > 80 else "✗"
                print(f"  {status} {c.source.value:10} | {c.start_date} to {c.end_date} | "
                      f"{c.record_count:,} records | {c.completeness_pct:.1f}% complete")
                if c.missing_days > 0:
                    print(f"    └─ Missing {c.missing_days} trading days")
    
    def print_gap_report(self, gaps: List[GapInfo]):
        """Print a formatted gap report."""
        print("\n" + "="*80)
        print("DATA GAPS TO FILL")
        print("="*80)
        
        if not gaps:
            print("\n✓ No gaps found - data is complete!")
            return
        
        for gap in gaps:
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[gap.priority]
            print(f"\n{priority_emoji} {gap.symbol}")
            print(f"   Gap: {gap.start_date} to {gap.end_date}")
            print(f"   Trading days: {gap.trading_days}")
            print(f"   Priority: {gap.priority}")


async def main():
    """Main entry point for data pipeline."""
    logger.info("Starting Data Pipeline Analysis")
    
    # Create pipeline manager
    manager = DataPipelineManager(data_dir=Path("data"))
    
    # Analyze current coverage
    logger.info("Analyzing database coverage...")
    coverage = await manager.analyze_database_coverage()
    manager.print_coverage_report(coverage)
    
    # Identify gaps
    target_date = date(2026, 1, 5)  # Today
    gaps = manager.identify_gaps(coverage, target_date)
    manager.print_gap_report(gaps)
    
    if gaps:
        print("\n" + "="*80)
        print("RECOMMENDED ACTIONS")
        print("="*80)
        
        for gap in gaps:
            print(f"\n→ {gap.symbol}: Download {gap.trading_days} days from Dukascopy")
            print(f"  Command: python -m src.data.pipeline download {gap.symbol} {gap.start_date} {gap.end_date}")
    
    return coverage, gaps


async def download_and_import(symbol: str, start_date: str, end_date: str, 
                             source: str = "DUKASCOPY"):
    """Download data and import to database."""
    from src.data.importer import DataImporter
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    
    manager = DataPipelineManager(data_dir=Path("data"))
    
    # Download
    gap = GapInfo(
        symbol=symbol,
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date(),
        trading_days=0,
        priority="high"
    )
    
    result = await manager.download_gap_data(gap, DataSource(source))
    
    if not result.success:
        logger.error(f"Download failed: {result.error}")
        return
    
    logger.info(f"Download complete: {result.bars_count} bars")
    
    # Import to database
    logger.info("Importing to database...")
    
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    importer = DataImporter(session_factory)
    import_result = await importer.import_csv(
        file_path=result.file_path,
        symbol=symbol,
        source=DataSource(source),
        timeframe=Timeframe.M1
    )
    
    await engine.dispose()
    
    logger.info(f"Import complete: {import_result.inserted} inserted, "
               f"{import_result.skipped} skipped, {import_result.errors} errors")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "analyze":
            asyncio.run(main())
        elif command == "download" and len(sys.argv) >= 5:
            symbol = sys.argv[2]
            start_date = sys.argv[3]
            end_date = sys.argv[4]
            source = sys.argv[5] if len(sys.argv) > 5 else "DUKASCOPY"
            asyncio.run(download_and_import(symbol, start_date, end_date, source))
        else:
            print("Usage:")
            print("  python -m src.data.pipeline analyze")
            print("  python -m src.data.pipeline download <symbol> <start_date> <end_date> [source]")
            print("")
            print("Examples:")
            print("  python -m src.data.pipeline analyze")
            print("  python -m src.data.pipeline download CrudeOIL 2025-04-01 2026-01-05 DUKASCOPY")
    else:
        asyncio.run(main())
