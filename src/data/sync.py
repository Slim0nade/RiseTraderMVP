#!/usr/bin/env python3
"""
RiseTrader Data Sync Service

Automatically detects data gaps and downloads missing data from free sources.
Can be run manually, as a cron job, or as a background service.

Usage:
    # Check status only
    python -m src.data.sync status
    
    # Sync all symbols (auto-detect gaps, download, import)
    python -m src.data.sync
    
    # Sync specific symbol
    python -m src.data.sync --symbol CrudeOIL
    
    # Dry run (show what would be downloaded)
    python -m src.data.sync --dry-run
    
    # Force re-download last N days
    python -m src.data.sync --force-days 7

Docker:
    docker exec -it risetrader-api python -m src.data.sync
    docker exec -it risetrader-api python -m src.data.sync status

Cron (daily at 6am):
    0 6 * * * docker exec risetrader-api python -m src.data.sync >> /var/log/risetrader-sync.log 2>&1
"""
import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("data_sync")


@dataclass
class SymbolConfig:
    """Configuration for a symbol to sync."""
    symbol: str
    sources: List[str]  # Priority order: try first source, fallback to next
    min_bars_per_day: int = 500  # Minimum expected bars for quality check
    enabled: bool = True


@dataclass 
class GapInfo:
    """Information about a data gap."""
    symbol: str
    source: str
    gap_start: date
    gap_end: date
    trading_days: int
    
    def __str__(self):
        return f"{self.symbol} ({self.source}): {self.gap_start} → {self.gap_end} ({self.trading_days} trading days)"


@dataclass
class SyncResult:
    """Result of a sync operation."""
    symbol: str
    source: str
    success: bool
    bars_downloaded: int = 0
    bars_imported: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0


# Default symbols to sync
DEFAULT_SYMBOLS = [
    SymbolConfig("CrudeOIL", ["DUKASCOPY", "HISTDATA"], min_bars_per_day=800),
    SymbolConfig("GOLD", ["DUKASCOPY", "HISTDATA"], min_bars_per_day=800),
    SymbolConfig("DXY", ["DUKASCOPY"], min_bars_per_day=500, enabled=False),  # Not on Dukascopy
    SymbolConfig("SPX500", ["DUKASCOPY"], min_bars_per_day=500),
]


class DataSyncService:
    """
    Service for syncing market data from external sources to database.
    
    Features:
    - Auto-detects gaps by querying database
    - Downloads from multiple sources with fallback
    - Imports to database with deduplication
    - Progress tracking and resume capability
    - Configurable symbols and sources
    """
    
    def __init__(self, database_url: str = None, data_dir: Path = None):
        self.database_url = database_url or self._get_database_url()
        self.data_dir = data_dir or Path("data/sync")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.progress_file = self.data_dir / "sync_progress.json"
        
        # Lazy-loaded components
        self._engine = None
        self._session_factory = None
        self._downloaders = {}
    
    def _get_database_url(self) -> str:
        """Get database URL from environment or default."""
        import os
        return os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:risetrader2024@postgres:5432/risetrader"
        )
    
    async def _get_engine(self):
        """Get or create async engine."""
        if self._engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            self._engine = create_async_engine(self.database_url)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        return self._engine
    
    async def _get_downloader(self, source: str):
        """Get or create downloader for source."""
        if source not in self._downloaders:
            if source == "DUKASCOPY":
                from src.data.dukascopy import DukascopyDownloader
                self._downloaders[source] = DukascopyDownloader(self.data_dir / "dukascopy")
            elif source == "HISTDATA":
                from src.data.histdata import HistDataDownloader
                self._downloaders[source] = HistDataDownloader(self.data_dir / "histdata")
            else:
                raise ValueError(f"Unknown source: {source}")
        return self._downloaders[source]
    
    async def get_data_status(self) -> Dict[str, dict]:
        """Get current data status from database."""
        await self._get_engine()
        
        query = """
            SELECT 
                symbol,
                source,
                COUNT(*) as records,
                MIN(time)::date as start_date,
                MAX(time)::date as end_date,
                COUNT(DISTINCT DATE(time)) as days_with_data
            FROM market_data
            WHERE timeframe = 'M1'
            GROUP BY symbol, source
            ORDER BY symbol, source
        """
        
        async with self._engine.connect() as conn:
            from sqlalchemy import text
            result = await conn.execute(text(query))
            rows = result.fetchall()
        
        status = {}
        for row in rows:
            symbol, source, records, start, end, days = row
            key = f"{symbol}_{source}"
            status[key] = {
                "symbol": symbol,
                "source": source,
                "records": records,
                "start_date": start,
                "end_date": end,
                "days_with_data": days,
                "avg_bars_per_day": records // days if days > 0 else 0
            }
        
        return status
    
    async def detect_gaps(self, symbols: List[SymbolConfig] = None, 
                          target_date: date = None) -> List[GapInfo]:
        """Detect data gaps for configured symbols."""
        if symbols is None:
            symbols = [s for s in DEFAULT_SYMBOLS if s.enabled]
        if target_date is None:
            target_date = date.today()
        
        status = await self.get_data_status()
        gaps = []
        
        for config in symbols:
            # Find the latest data for this symbol across all sources
            latest_end = None
            best_source = None
            
            for source in config.sources:
                key = f"{config.symbol}_{source}"
                if key in status:
                    end = status[key]["end_date"]
                    if latest_end is None or end > latest_end:
                        latest_end = end
                        best_source = source
            
            # Also check BC (Barchart) data as baseline
            bc_key = f"{config.symbol}_BC"
            if bc_key in status:
                bc_end = status[bc_key]["end_date"]
                if latest_end is None or bc_end > latest_end:
                    latest_end = bc_end
            
            # Calculate gap
            if latest_end is None:
                # No data at all - need full history (limit to 2 years)
                gap_start = target_date - timedelta(days=730)
                logger.warning(f"{config.symbol}: No data found, will download from {gap_start}")
            elif latest_end < target_date:
                gap_start = latest_end + timedelta(days=1)
            else:
                # No gap
                continue
            
            # Calculate trading days
            trading_days = sum(
                1 for i in range((target_date - gap_start).days + 1)
                if (gap_start + timedelta(days=i)).weekday() < 5
            )
            
            if trading_days > 0:
                gaps.append(GapInfo(
                    symbol=config.symbol,
                    source=config.sources[0],  # Primary source
                    gap_start=gap_start,
                    gap_end=target_date,
                    trading_days=trading_days
                ))
        
        return gaps
    
    async def download_gap(self, gap: GapInfo, sources: List[str] = None) -> Tuple[bool, Path, int]:
        """
        Download data to fill a gap.
        
        Returns: (success, file_path, bars_count)
        """
        if sources is None:
            sources = [gap.source]
        
        for source in sources:
            try:
                logger.info(f"Downloading {gap.symbol} from {source}: {gap.gap_start} → {gap.gap_end}")
                
                downloader = await self._get_downloader(source)
                
                from src.data.base import Timeframe
                result = await downloader.download(
                    symbol=gap.symbol,
                    start_date=gap.gap_start,
                    end_date=gap.gap_end,
                    timeframe=Timeframe.M1
                )
                
                if result.success:
                    logger.info(f"✅ Downloaded {result.bars_count:,} bars from {source}")
                    return True, result.file_path, result.bars_count
                else:
                    logger.warning(f"❌ {source} failed: {result.error}")
                    
            except Exception as e:
                logger.warning(f"❌ {source} exception: {e}")
                continue
        
        return False, None, 0
    
    async def import_file(self, file_path: Path, symbol: str, source: str) -> int:
        """Import a CSV file to database."""
        from src.data.importer import DataImporter
        from src.data.base import DataSource, Timeframe
        
        await self._get_engine()
        
        importer = DataImporter(self._session_factory)
        result = await importer.import_csv(
            file_path=file_path,
            symbol=symbol,
            source=DataSource(source),
            timeframe=Timeframe.M1
        )
        
        if result.success:
            logger.info(f"✅ Imported: {result.inserted} new, {result.updated} updated, {result.skipped} skipped")
            return result.inserted + result.updated
        else:
            logger.error(f"❌ Import failed: {result.error_message}")
            return 0
    
    async def sync_symbol(self, config: SymbolConfig, target_date: date = None,
                          dry_run: bool = False, force_days: int = 0) -> SyncResult:
        """Sync a single symbol."""
        start_time = datetime.now()
        
        if target_date is None:
            target_date = date.today()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 SYNCING: {config.symbol}")
        logger.info(f"{'='*60}")
        
        # Detect gap
        gaps = await self.detect_gaps([config], target_date)
        
        if not gaps and force_days == 0:
            logger.info(f"✅ {config.symbol} is up to date!")
            return SyncResult(
                symbol=config.symbol,
                source=config.sources[0],
                success=True,
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )
        
        # If force_days, create artificial gap
        if force_days > 0:
            gap = GapInfo(
                symbol=config.symbol,
                source=config.sources[0],
                gap_start=target_date - timedelta(days=force_days),
                gap_end=target_date,
                trading_days=force_days
            )
        else:
            gap = gaps[0]
        
        logger.info(f"📥 Gap: {gap}")
        
        if dry_run:
            logger.info(f"🔍 DRY RUN - would download {gap.trading_days} trading days")
            return SyncResult(
                symbol=config.symbol,
                source=gap.source,
                success=True,
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )
        
        # Download
        success, file_path, bars = await self.download_gap(gap, config.sources)
        
        if not success:
            return SyncResult(
                symbol=config.symbol,
                source=gap.source,
                success=False,
                error="Download failed from all sources",
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )
        
        # Import
        imported = await self.import_file(file_path, config.symbol, gap.source)
        
        return SyncResult(
            symbol=config.symbol,
            source=gap.source,
            success=True,
            bars_downloaded=bars,
            bars_imported=imported,
            duration_seconds=(datetime.now() - start_time).total_seconds()
        )
    
    async def sync_all(self, symbols: List[SymbolConfig] = None, 
                       dry_run: bool = False, force_days: int = 0) -> List[SyncResult]:
        """Sync all configured symbols."""
        if symbols is None:
            symbols = [s for s in DEFAULT_SYMBOLS if s.enabled]
        
        results = []
        
        logger.info("=" * 60)
        logger.info("🚀 RISETRADER DATA SYNC")
        logger.info(f"   Symbols: {[s.symbol for s in symbols]}")
        logger.info(f"   Target:  {date.today()}")
        logger.info(f"   Mode:    {'DRY RUN' if dry_run else 'LIVE'}")
        logger.info("=" * 60)
        
        for config in symbols:
            try:
                result = await self.sync_symbol(config, dry_run=dry_run, force_days=force_days)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Error syncing {config.symbol}: {e}")
                results.append(SyncResult(
                    symbol=config.symbol,
                    source=config.sources[0] if config.sources else "UNKNOWN",
                    success=False,
                    error=str(e)
                ))
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 SYNC SUMMARY")
        logger.info("=" * 60)
        
        total_downloaded = sum(r.bars_downloaded for r in results)
        total_imported = sum(r.bars_imported for r in results)
        successes = sum(1 for r in results if r.success)
        
        for r in results:
            status = "✅" if r.success else "❌"
            logger.info(f"   {status} {r.symbol}: {r.bars_downloaded:,} downloaded, {r.bars_imported:,} imported")
        
        logger.info(f"\n   Total: {total_downloaded:,} bars downloaded, {total_imported:,} imported")
        logger.info(f"   Success: {successes}/{len(results)}")
        
        # Save results
        self._save_sync_log(results)
        
        return results
    
    def _save_sync_log(self, results: List[SyncResult]):
        """Save sync results to log file."""
        log_file = self.data_dir / "sync_log.jsonl"
        
        with open(log_file, 'a') as f:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "results": [asdict(r) for r in results]
            }
            f.write(json.dumps(entry) + "\n")
    
    async def print_status(self):
        """Print current data status."""
        status = await self.get_data_status()
        gaps = await self.detect_gaps()
        
        print("\n" + "=" * 70)
        print("📊 RISETRADER DATA STATUS")
        print("=" * 70)
        
        print(f"\n{'Symbol':<12} {'Source':<12} {'Records':>12} {'Start':<12} {'End':<12} {'Bars/Day':>10}")
        print("-" * 70)
        
        for key, s in sorted(status.items()):
            print(f"{s['symbol']:<12} {s['source']:<12} {s['records']:>12,} "
                  f"{str(s['start_date']):<12} {str(s['end_date']):<12} {s['avg_bars_per_day']:>10}")
        
        if gaps:
            print("\n" + "=" * 70)
            print("⚠️  DATA GAPS TO FILL")
            print("=" * 70)
            for gap in gaps:
                print(f"   • {gap}")
        else:
            print("\n✅ All data is up to date!")
        
        print()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="RiseTrader Data Sync Service")
    parser.add_argument("command", nargs="?", default="sync", 
                        choices=["sync", "status"],
                        help="Command to run (default: sync)")
    parser.add_argument("--symbol", "-s", help="Sync specific symbol only")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would be done without doing it")
    parser.add_argument("--force-days", "-f", type=int, default=0,
                        help="Force re-download last N days")
    parser.add_argument("--data-dir", "-d", type=Path, default=Path("data/sync"),
                        help="Data directory for downloads")
    
    args = parser.parse_args()
    
    service = DataSyncService(data_dir=args.data_dir)
    
    if args.command == "status":
        await service.print_status()
    else:
        if args.symbol:
            # Find symbol config
            config = next((s for s in DEFAULT_SYMBOLS if s.symbol == args.symbol), None)
            if config is None:
                # Create default config for unknown symbol
                config = SymbolConfig(args.symbol, ["DUKASCOPY", "HISTDATA"])
            symbols = [config]
        else:
            symbols = None
        
        await service.sync_all(
            symbols=symbols,
            dry_run=args.dry_run,
            force_days=args.force_days
        )


if __name__ == "__main__":
    asyncio.run(main())
