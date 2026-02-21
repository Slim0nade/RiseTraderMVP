#!/usr/bin/env python3
"""
Download historical data from Dukascopy and import to database.

Downloads tick data, aggregates to M1/M5/H1, and imports to database
with source='DUKASCOPY'.

Usage:
    # Download and import CrudeOIL from 2009 to present
    python scripts/import_dukascopy.py --symbol CrudeOIL --start 2009-08-01 --end 2026-01-14
    
    # Download specific timeframe only
    python scripts/import_dukascopy.py --symbol CrudeOIL --start 2024-01-01 --timeframe M1
    
    # Resume interrupted download
    python scripts/import_dukascopy.py --symbol CrudeOIL --resume

This is a LARGE download (~16 years = ~144,000 hourly files).
Estimated time: 2-4 hours depending on connection.
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.database.config import create_session_factory, create_engine_from_env
from src.data.dukascopy import DukascopyDownloader
from src.data.base import Timeframe, DataSource

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


class DukascopyImporter:
    """Downloads from Dukascopy and imports to database."""
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path("data/downloads/dukascopy")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.downloader = DukascopyDownloader(self.data_dir)
        self.progress_file = self.data_dir / "import_progress.json"
        
    def _load_progress(self, symbol: str) -> dict:
        """Load progress from file."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                progress = json.load(f)
                return progress.get(symbol, {})
        return {}
    
    def _save_progress(self, symbol: str, timeframe: str, last_date: str):
        """Save progress to file."""
        progress = {}
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                progress = json.load(f)
        
        if symbol not in progress:
            progress[symbol] = {}
        progress[symbol][timeframe] = {
            "last_date": last_date,
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.progress_file, "w") as f:
            json.dump(progress, f, indent=2)
    
    async def download_and_import(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframes: List[Timeframe] = None,
        batch_days: int = 30,
    ):
        """
        Download data in batches and import to database.
        
        Args:
            symbol: Trading symbol (e.g., 'CrudeOIL')
            start_date: Start date
            end_date: End date
            timeframes: List of timeframes to generate (default: M1, M5, H1)
            batch_days: Days per batch (for memory management)
        """
        timeframes = timeframes or [Timeframe.M1]
        
        engine = create_engine_from_env()
        session_factory = create_session_factory(engine)
        
        # Calculate total batches
        total_days = (end_date - start_date).days
        total_batches = (total_days + batch_days - 1) // batch_days
        
        logger.info(f"Starting Dukascopy import for {symbol}")
        logger.info(f"Date range: {start_date} to {end_date} ({total_days} days)")
        logger.info(f"Timeframes: {[tf.value for tf in timeframes]}")
        logger.info(f"Batches: {total_batches} × {batch_days} days each")
        
        # Process in batches
        current_start = start_date
        batch_num = 0
        total_bars_imported = {tf.value: 0 for tf in timeframes}
        
        while current_start < end_date:
            batch_num += 1
            current_end = min(current_start + timedelta(days=batch_days), end_date)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Batch {batch_num}/{total_batches}: {current_start} to {current_end}")
            logger.info(f"{'='*60}")
            
            for timeframe in timeframes:
                try:
                    # Download from Dukascopy
                    logger.info(f"Downloading {timeframe.value} data...")
                    result = await self.downloader.download(
                        symbol=symbol,
                        start_date=current_start,
                        end_date=current_end,
                        timeframe=timeframe,
                    )
                    
                    if not result.success:
                        logger.warning(f"Download failed: {result.error}")
                        continue
                    
                    if result.bars_count == 0:
                        logger.warning(f"No data for this period")
                        continue
                    
                    logger.info(f"Downloaded {result.bars_count} {timeframe.value} bars")
                    
                    # Import to database
                    if result.file_path:
                        imported = await self._import_csv_to_db(
                            session_factory,
                            result.file_path,
                            symbol,
                            timeframe,
                        )
                        total_bars_imported[timeframe.value] += imported
                        logger.info(f"Imported {imported} bars to database")
                    
                    # Save progress
                    self._save_progress(symbol, timeframe.value, current_end.isoformat())
                    
                except Exception as e:
                    logger.error(f"Error processing {timeframe.value}: {e}")
                    continue
            
            current_start = current_end
            
            # Progress summary
            logger.info(f"\nProgress: {batch_num}/{total_batches} batches complete")
            for tf, count in total_bars_imported.items():
                logger.info(f"  {tf}: {count:,} bars imported")
        
        # Final summary
        logger.info(f"\n{'='*60}")
        logger.info("IMPORT COMPLETE")
        logger.info(f"{'='*60}")
        for tf, count in total_bars_imported.items():
            logger.info(f"  {tf}: {count:,} total bars")
        
        await self.downloader.close()
        return total_bars_imported
    
    async def _import_csv_to_db(
        self,
        session_factory,
        csv_path: Path,
        symbol: str,
        timeframe: Timeframe,
    ) -> int:
        """Import CSV file to database."""
        import pandas as pd
        
        df = pd.read_csv(csv_path, parse_dates=['time'])
        
        if df.empty:
            return 0
        
        async with session_factory() as session:
            # Delete existing data for this range to avoid duplicates
            min_time = df['time'].min()
            max_time = df['time'].max()
            
            delete_query = text("""
                DELETE FROM market_data 
                WHERE symbol = :symbol 
                AND timeframe = :timeframe 
                AND source = 'DUKASCOPY'
                AND time >= :min_time 
                AND time <= :max_time
            """)
            await session.execute(delete_query, {
                "symbol": symbol,
                "timeframe": timeframe.value,
                "min_time": min_time,
                "max_time": max_time,
            })
            
            # Batch insert
            batch_size = 1000
            inserted = 0
            
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                
                values = []
                for _, row in batch.iterrows():
                    values.append({
                        "time": row['time'],
                        "symbol": symbol,
                        "import_symbol": "DUKASCOPY",
                        "timeframe": timeframe.value,
                        "source": "DUKASCOPY",
                        "open": str(row['open']),
                        "high": str(row['high']),
                        "low": str(row['low']),
                        "last": str(row['close']),
                        "change": "0",
                        "change_percent": "0",
                        "volume": int(row.get('volume', 0)),
                    })
                
                insert_query = text("""
                    INSERT INTO market_data (
                        time, symbol, import_symbol, timeframe, source,
                        open, high, low, last, change, change_percent, volume,
                        created_at, updated_at
                    ) VALUES (
                        :time, :symbol, :import_symbol, :timeframe, :source,
                        :open, :high, :low, :last, :change, :change_percent, :volume,
                        NOW(), NOW()
                    )
                    ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        last = EXCLUDED.last,
                        volume = EXCLUDED.volume,
                        updated_at = NOW()
                """)
                
                for val in values:
                    await session.execute(insert_query, val)
                
                inserted += len(batch)
            
            await session.commit()
            return inserted


async def aggregate_to_higher_timeframes(symbol: str):
    """Aggregate M1 data to M5 and H1 in the database."""
    engine = create_engine_from_env()
    session_factory = create_session_factory(engine)
    
    async with session_factory() as session:
        # Check M1 data exists
        count_query = text("""
            SELECT COUNT(*) as cnt FROM market_data 
            WHERE symbol = :symbol AND source = 'DUKASCOPY' AND timeframe = 'M1'
        """)
        result = await session.execute(count_query, {"symbol": symbol})
        m1_count = result.scalar()
        
        if m1_count == 0:
            logger.error("No M1 data found for DUKASCOPY source")
            return
        
        logger.info(f"Found {m1_count:,} M1 candles to aggregate")
        
        # Aggregate to M5
        logger.info("Aggregating M1 to M5...")
        m5_query = text("""
            INSERT INTO market_data (
                time, symbol, import_symbol, timeframe, source,
                open, high, low, last, change, change_percent, volume,
                created_at, updated_at
            )
            SELECT 
                date_trunc('hour', time) + 
                    (EXTRACT(MINUTE FROM time)::int / 5 * 5 || ' minutes')::interval as time,
                symbol,
                'AGGREGATED' as import_symbol,
                'M5' as timeframe,
                'DUKASCOPY' as source,
                (array_agg(open ORDER BY time))[1] as open,
                MAX(high) as high,
                MIN(low) as low,
                (array_agg(last ORDER BY time DESC))[1] as last,
                '0' as change,
                '0' as change_percent,
                SUM(volume) as volume,
                NOW() as created_at,
                NOW() as updated_at
            FROM market_data
            WHERE symbol = :symbol AND source = 'DUKASCOPY' AND timeframe = 'M1'
            GROUP BY 
                date_trunc('hour', time) + 
                    (EXTRACT(MINUTE FROM time)::int / 5 * 5 || ' minutes')::interval,
                symbol
            ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                last = EXCLUDED.last,
                volume = EXCLUDED.volume,
                updated_at = NOW()
        """)
        await session.execute(m5_query, {"symbol": symbol})
        await session.commit()
        
        # Count M5
        result = await session.execute(text("""
            SELECT COUNT(*) FROM market_data 
            WHERE symbol = :symbol AND source = 'DUKASCOPY' AND timeframe = 'M5'
        """), {"symbol": symbol})
        m5_count = result.scalar()
        logger.info(f"Created {m5_count:,} M5 candles")
        
        # Aggregate to H1
        logger.info("Aggregating M1 to H1...")
        h1_query = text("""
            INSERT INTO market_data (
                time, symbol, import_symbol, timeframe, source,
                open, high, low, last, change, change_percent, volume,
                created_at, updated_at
            )
            SELECT 
                date_trunc('hour', time) as time,
                symbol,
                'AGGREGATED' as import_symbol,
                'H1' as timeframe,
                'DUKASCOPY' as source,
                (array_agg(open ORDER BY time))[1] as open,
                MAX(high) as high,
                MIN(low) as low,
                (array_agg(last ORDER BY time DESC))[1] as last,
                '0' as change,
                '0' as change_percent,
                SUM(volume) as volume,
                NOW() as created_at,
                NOW() as updated_at
            FROM market_data
            WHERE symbol = :symbol AND source = 'DUKASCOPY' AND timeframe = 'M1'
            GROUP BY date_trunc('hour', time), symbol
            ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                last = EXCLUDED.last,
                volume = EXCLUDED.volume,
                updated_at = NOW()
        """)
        await session.execute(h1_query, {"symbol": symbol})
        await session.commit()
        
        # Count H1
        result = await session.execute(text("""
            SELECT COUNT(*) FROM market_data 
            WHERE symbol = :symbol AND source = 'DUKASCOPY' AND timeframe = 'H1'
        """), {"symbol": symbol})
        h1_count = result.scalar()
        logger.info(f"Created {h1_count:,} H1 candles")
        
        logger.info("Aggregation complete!")


async def main():
    parser = argparse.ArgumentParser(description="Import Dukascopy data")
    parser.add_argument("--symbol", required=True, help="Symbol to download (e.g., CrudeOIL)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD), default=today")
    parser.add_argument("--timeframe", default="M1", help="Timeframe to download (M1, M5, H1)")
    parser.add_argument("--batch-days", type=int, default=30, help="Days per batch")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate M1 to M5/H1 after import")
    parser.add_argument("--aggregate-only", action="store_true", help="Only run aggregation (skip download)")
    args = parser.parse_args()
    
    if args.aggregate_only:
        await aggregate_to_higher_timeframes(args.symbol)
        return
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    
    timeframe_map = {
        "M1": Timeframe.M1,
        "M5": Timeframe.M5,
        "H1": Timeframe.H1,
    }
    timeframe = timeframe_map.get(args.timeframe, Timeframe.M1)
    
    importer = DukascopyImporter()
    await importer.download_and_import(
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        timeframes=[timeframe],
        batch_days=args.batch_days,
    )
    
    if args.aggregate:
        await aggregate_to_higher_timeframes(args.symbol)


if __name__ == "__main__":
    asyncio.run(main())
