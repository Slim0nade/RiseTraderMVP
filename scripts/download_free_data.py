"""
Free Market Data Downloader for RiseTrader

Downloads 1-minute historical data from FREE sources:
1. Dukascopy - Tick data (aggregated to M1) for forex/commodities
2. HistData - Pre-aggregated M1 data from GitHub repo

Supported instruments:
- CrudeOIL (WTI/USD) 
- Gold (XAU/USD)
- S&P 500 (SPX500/USD)
- US Dollar Index (UDX/USD)
- VIX (via VXX proxy from HistData)

Usage:
    python download_free_data.py --source dukascopy --symbol WTIUSD --start 2020-01-01 --end 2024-12-31
    python download_free_data.py --source histdata --symbol all --start 2020-01-01
    python download_free_data.py --import-all  # Import all downloaded CSVs to database
"""

import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
import struct
import lzma
from io import BytesIO
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import pandas as pd
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Symbol Mapping
# =============================================================================

SYMBOL_MAPPING = {
    # Our symbol -> (Dukascopy symbol, HistData symbol, Description)
    'CrudeOIL':  ('WTIUSD',        'WTIUSD',    'WTI Crude Oil'),
    'XAUUSD':    ('XAUUSD',        'XAUUSD',    'Gold'),
    'SPX500':    ('SPX500USD',     'SPX500USD', 'S&P 500 Index'),
    'DXY':       ('USDOLLARINDEX', 'UDX',       'US Dollar Index'),
    'VIX':       (None,            'VXXUSD',    'VIX Volatility Index (via VXX proxy)'),
    # Phase 2 additions — data-gap fills
    'USA500':    ('USA500IDXUSD',  None,        'US 500 Cash Index'),
    'BRENT_OIL': ('BCOUSD',        'BCOUSD',    'Brent Crude Oil'),
    'GBPJPY':    ('GBPJPY',        'GBPJPY',    'GBP/JPY'),
}

# Dukascopy instrument details: point = 10 ** (-decimals), i.e. the price multiplier
DUKASCOPY_INSTRUMENTS = {
    'WTIUSD':        {'decimals': 3, 'name': 'WTI/USD'},
    'XAUUSD':        {'decimals': 3, 'name': 'Gold'},
    'SPX500USD':     {'decimals': 2, 'name': 'S&P 500'},
    'USDOLLARINDEX': {'decimals': 3, 'name': 'US Dollar Index'},
    # Phase 2 additions
    'USA500IDXUSD':  {'decimals': 3, 'name': 'US 500 Cash Index'},  # ~5000-6000, 3dp confirmed
    'BCOUSD':        {'decimals': 3, 'name': 'Brent Crude Oil'},    # ~$80, same range as WTI
    'GBPJPY':        {'decimals': 3, 'name': 'GBP/JPY'},            # ~190.xxx, 3dp standard forex
}


# =============================================================================
# Utility: resumability + H1 aggregation
# =============================================================================

async def get_resume_point(symbol: str, timeframe: str = "M1") -> Optional[datetime]:
    """
    Query the latest candle timestamp stored for this symbol+timeframe in PostgreSQL.

    Uses the DUKASCOPY source filter so that MT4-sourced rows (which may be
    partial or missing weekends) do not distort the resume position.

    Args:
        symbol:    RiseTrader internal symbol name (e.g. 'USA500', 'BRENT_OIL').
        timeframe: 'M1' or 'H1'.  Must match the ENUM value stored in market_data.

    Returns:
        Latest datetime (UTC-aware) already in the DB, or None if no rows exist.

    Edge cases:
        - Returns None when the table is empty for this symbol/timeframe.
        - The DB stores timeframe as a PostgreSQL ENUM; casting to TEXT avoids
          type mismatch on the equality check.
    """
    import asyncpg

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:risetrader2024@localhost:5433/risetrader"
    )
    # asyncpg uses plain postgresql:// — strip SQLAlchemy driver suffix if present
    db_url = db_url.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")

    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow(
            "SELECT MAX(time) FROM market_data "
            "WHERE symbol = $1 AND source = 'DUKASCOPY' AND CAST(timeframe AS TEXT) = $2",
            symbol, timeframe
        )
        return row[0] if row and row[0] else None
    finally:
        await conn.close()


def aggregate_m1_to_h1(m1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate M1 candles to H1 using standard OHLCV rules.

    Groups by flooring the timestamp to the nearest hour:
        open   = first M1 open in the hour
        high   = max of all M1 highs
        low    = min of all M1 lows
        close  = last M1 close
        volume = sum of all M1 volumes

    Args:
        m1_df: DataFrame with columns [time, open, high, low, close, volume].
               'time' must be datetime-compatible (naive or tz-aware).

    Returns:
        DataFrame with H1 candles sorted ascending by time.
        Empty DataFrame if input is empty.

    Edge cases:
        - Handles both tz-aware and tz-naive timestamps.
        - Hours with only one M1 candle produce a valid H1 candle (O=H=L=C).
        - NaN volumes are treated as 0 before summing.
    """
    if m1_df.empty:
        return pd.DataFrame()

    df = m1_df.copy()
    df["time"] = pd.to_datetime(df["time"])
    df["volume"] = df["volume"].fillna(0)
    df["period"] = df["time"].dt.floor("h")

    h1 = (
        df.groupby("period")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
        .rename(columns={"period": "time"})
    )
    return h1.sort_values("time").reset_index(drop=True)


# =============================================================================
# Dukascopy Downloader
# =============================================================================

class DukascopyDownloader:
    """
    Downloads tick data from Dukascopy and aggregates to M1 candles.
    
    Dukascopy provides FREE tick-level historical data going back to 2009+
    No API key required - just HTTP requests to their data server.
    """
    
    BASE_URL = "https://datafeed.dukascopy.com/datafeed"
    
    def __init__(self, output_dir: str = "data/dukascopy"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_url(self, symbol: str, year: int, month: int, day: int, hour: int) -> str:
        """Generate URL for hourly tick data file."""
        # Dukascopy uses 0-indexed months
        return f"{self.BASE_URL}/{symbol}/{year}/{month-1:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
    
    def _decompress_lzma(self, data: bytes) -> bytes:
        """Decompress LZMA compressed data."""
        try:
            return lzma.decompress(data)
        except lzma.LZMAError:
            return data  # Already decompressed or empty
    
    def _parse_ticks(self, data: bytes, decimals: int) -> List[Dict]:
        """
        Parse binary tick data from Dukascopy.
        
        Format: 20 bytes per tick
        - 4 bytes: milliseconds since hour start (uint32)
        - 4 bytes: ask price (uint32, needs decimal adjustment)
        - 4 bytes: bid price (uint32, needs decimal adjustment)
        - 4 bytes: ask volume (float32)
        - 4 bytes: bid volume (float32)
        """
        ticks = []
        point = 10 ** (-decimals)
        
        for i in range(0, len(data), 20):
            if i + 20 > len(data):
                break
                
            chunk = data[i:i+20]
            try:
                ms, ask, bid, ask_vol, bid_vol = struct.unpack('>IIIff', chunk)
                ticks.append({
                    'ms': ms,
                    'ask': ask * point,
                    'bid': bid * point,
                    'ask_volume': ask_vol,
                    'bid_volume': bid_vol,
                    'mid': (ask + bid) / 2 * point
                })
            except struct.error:
                continue
                
        return ticks
    
    def _aggregate_to_m1(self, ticks: List[Dict], base_time: datetime) -> Optional[Dict]:
        """Aggregate ticks to a single M1 candle."""
        if not ticks:
            return None
            
        prices = [t['mid'] for t in ticks]
        volumes = [t['ask_volume'] + t['bid_volume'] for t in ticks]
        
        return {
            'time': base_time,
            'open': prices[0],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': int(sum(volumes))
        }
    
    def download_hour(self, symbol: str, dt: datetime) -> List[Dict]:
        """Download and parse one hour of tick data, aggregate to M1."""
        url = self._get_url(symbol, dt.year, dt.month, dt.day, dt.hour)
        
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urlopen(req, timeout=30)
            compressed_data = response.read()
            
            if not compressed_data:
                return []
                
            data = self._decompress_lzma(compressed_data)
            decimals = DUKASCOPY_INSTRUMENTS.get(symbol, {}).get('decimals', 5)
            ticks = self._parse_ticks(data, decimals)
            
            if not ticks:
                return []
            
            # Group ticks by minute and aggregate
            candles = []
            minute_ticks = {}
            
            for tick in ticks:
                minute = tick['ms'] // 60000
                if minute not in minute_ticks:
                    minute_ticks[minute] = []
                minute_ticks[minute].append(tick)
            
            for minute, mticks in sorted(minute_ticks.items()):
                candle_time = dt.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
                candle = self._aggregate_to_m1(mticks, candle_time)
                if candle:
                    candles.append(candle)
                    
            return candles
            
        except HTTPError as e:
            if e.code == 404:
                return []  # No data for this hour (weekend, holiday)
            logger.warning(f"HTTP error {e.code} for {url}")
            return []
        except URLError as e:
            logger.warning(f"URL error for {url}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error downloading {url}: {e}")
            return []
    
    def download_range(
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime,
        progress_callback=None
    ) -> pd.DataFrame:
        """
        Download data for a date range.
        
        Args:
            symbol: Dukascopy symbol (e.g., 'WTIUSD')
            start_date: Start date
            end_date: End date
            progress_callback: Optional callback(current_date, total_hours, completed_hours)
            
        Returns:
            DataFrame with M1 candles
        """
        all_candles = []
        current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_date.replace(hour=23, minute=59, second=59)
        
        total_hours = int((end - current).total_seconds() / 3600) + 1
        completed = 0
        
        logger.info(f"Downloading {symbol} from {start_date.date()} to {end_date.date()}")
        logger.info(f"Total hours to fetch: {total_hours}")
        
        while current <= end:
            candles = self.download_hour(symbol, current)
            all_candles.extend(candles)
            
            completed += 1
            if completed % 100 == 0:
                logger.info(f"Progress: {completed}/{total_hours} hours ({100*completed/total_hours:.1f}%)")
                
            if progress_callback:
                progress_callback(current, total_hours, completed)
                
            current += timedelta(hours=1)
            
        if not all_candles:
            logger.warning(f"No data retrieved for {symbol}")
            return pd.DataFrame()
            
        df = pd.DataFrame(all_candles)
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time').drop_duplicates(subset=['time'])
        df = df.reset_index(drop=True)
        
        logger.info(f"Downloaded {len(df)} M1 candles for {symbol}")
        return df
    
    def save_csv(self, df: pd.DataFrame, symbol: str, start_date: datetime, end_date: datetime) -> Path:
        """Save DataFrame to CSV file."""
        filename = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}_M1.csv"
        filepath = self.output_dir / filename
        df.to_csv(filepath, index=False)
        logger.info(f"Saved {len(df)} records to {filepath}")
        return filepath


# =============================================================================
# HistData Downloader (GitHub FX-1-Minute-Data)
# =============================================================================

class HistDataDownloader:
    """
    Downloads pre-processed 1-minute data from the FX-1-Minute-Data GitHub repo.
    
    Repository: https://github.com/philipperemy/FX-1-Minute-Data
    Data source: histdata.com
    Coverage: 2000-present for many forex pairs and some commodities
    """
    
    BASE_URL = "https://raw.githubusercontent.com/philipperemy/FX-1-Minute-Data/master/data"
    
    # Available symbols in the repo
    AVAILABLE_SYMBOLS = [
        'AUDJPY', 'AUDNZD', 'AUDUSD', 'CADJPY', 'CHFJPY', 'EURCHF', 'EURGBP',
        'EURJPY', 'EURUSD', 'GBPCHF', 'GBPJPY', 'GBPUSD', 'NZDJPY', 'NZDUSD',
        'USDCAD', 'USDCHF', 'USDJPY', 'XAUUSD', 'XAGUSD', 'WTIUSD', 'BCOUSD',
        'SPX500USD', 'BTCUSD', 'ETHUSD', 'UDX'  # UDX = US Dollar Index
    ]
    
    def __init__(self, output_dir: str = "data/histdata"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def get_available_years(self, symbol: str) -> List[int]:
        """Get list of available years for a symbol (approximate)."""
        # Most symbols have data from around 2000-2010 to present
        current_year = datetime.now().year
        if symbol in ['BTCUSD', 'ETHUSD']:
            return list(range(2017, current_year + 1))
        elif symbol in ['SPX500USD', 'WTIUSD', 'XAUUSD']:
            return list(range(2010, current_year + 1))
        else:
            return list(range(2000, current_year + 1))
    
    def download_year(self, symbol: str, year: int) -> Optional[pd.DataFrame]:
        """Download one year of M1 data."""
        # HistData files are named like: XAUUSD_2020.csv
        url = f"{self.BASE_URL}/{symbol}/{symbol}_{year}.csv"
        
        try:
            logger.info(f"Downloading {symbol} {year}...")
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urlopen(req, timeout=60)
            
            # Parse CSV - format is: DateTime,Open,High,Low,Close,Volume
            df = pd.read_csv(
                BytesIO(response.read()),
                names=['time', 'open', 'high', 'low', 'close', 'volume'],
                parse_dates=['time']
            )
            
            logger.info(f"Downloaded {len(df)} records for {symbol} {year}")
            return df
            
        except HTTPError as e:
            if e.code == 404:
                logger.debug(f"No data for {symbol} {year} (404)")
                return None
            logger.warning(f"HTTP error {e.code} for {symbol} {year}")
            return None
        except Exception as e:
            logger.warning(f"Error downloading {symbol} {year}: {e}")
            return None
    
    def download_range(
        self,
        symbol: str,
        start_year: int,
        end_year: int
    ) -> pd.DataFrame:
        """Download multiple years of data."""
        all_data = []
        
        for year in range(start_year, end_year + 1):
            df = self.download_year(symbol, year)
            if df is not None and len(df) > 0:
                all_data.append(df)
                
        if not all_data:
            return pd.DataFrame()
            
        combined = pd.concat(all_data, ignore_index=True)
        combined = combined.sort_values('time').drop_duplicates(subset=['time'])
        combined = combined.reset_index(drop=True)
        
        logger.info(f"Total: {len(combined)} records for {symbol}")
        return combined
    
    def save_csv(self, df: pd.DataFrame, symbol: str) -> Path:
        """Save DataFrame to CSV file."""
        if df.empty:
            return None
            
        start = df['time'].min().strftime('%Y%m%d')
        end = df['time'].max().strftime('%Y%m%d')
        filename = f"{symbol}_{start}_{end}_M1_histdata.csv"
        filepath = self.output_dir / filename
        df.to_csv(filepath, index=False)
        logger.info(f"Saved {len(df)} records to {filepath}")
        return filepath


# =============================================================================
# Database Importer
# =============================================================================

class DataImporter:
    """Import downloaded CSV data into PostgreSQL database."""
    
    def __init__(self, db_url: str = None):
        """
        Initialize importer.
        
        Args:
            db_url: Database URL. If None, reads from environment.
        """
        self.db_url = db_url or self._get_db_url()
        
    def _get_db_url(self) -> str:
        """Get database URL from environment."""
        from dotenv import load_dotenv
        load_dotenv()
        
        user = os.getenv('POSTGRES_USER', 'postgres')
        password = os.getenv('POSTGRES_PASSWORD', 'risetrader2024')
        host = os.getenv('DB_HOST_NAME', 'localhost')
        port = os.getenv('DB_PORT', '5433')
        dbname = os.getenv('DB_NAME', 'risetrader')
        
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
    
    async def import_csv(
        self,
        filepath: Path,
        symbol: str,
        source: str = 'DUKASCOPY',
        timeframe: str = 'M1',
        batch_size: int = 10000
    ) -> Tuple[int, int, int]:
        """
        Import CSV file to database.
        
        Args:
            filepath: Path to CSV file
            symbol: Target symbol name (e.g., 'CrudeOIL')
            source: Data source (DUKASCOPY, HISTDATA)
            timeframe: Timeframe (M1)
            batch_size: Records per batch insert
            
        Returns:
            Tuple of (inserted, updated, skipped) counts
        """
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text
        
        logger.info(f"Importing {filepath} as {symbol} from {source}")
        
        # Read CSV
        df = pd.read_csv(filepath, parse_dates=['time'])
        df['time'] = pd.to_datetime(df['time'], utc=True)
        
        # Prepare data
        df['symbol'] = symbol
        df['import_symbol'] = filepath.stem.split('_')[0]
        df['source'] = source
        df['timeframe'] = timeframe
        df['change'] = df['close'].diff().fillna(0)
        df['change_percent'] = df['close'].pct_change().fillna(0)
        
        # Rename columns to match database schema
        if 'close' in df.columns:
            df['last'] = df['close']
            
        engine = create_async_engine(self.db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        inserted = 0
        updated = 0
        skipped = 0
        
        async with async_session() as session:
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                
                for _, row in batch.iterrows():
                    try:
                        # Use INSERT ON CONFLICT for upsert
                        query = text("""
                            INSERT INTO market_data 
                            (time, symbol, import_symbol, source, timeframe, open, high, low, last, change, change_percent, volume)
                            VALUES (:time, :symbol, :import_symbol, :source, :timeframe, :open, :high, :low, :last, :change, :change_percent, :volume)
                            ON CONFLICT (time, source, timeframe, symbol) 
                            DO UPDATE SET
                                open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                last = EXCLUDED.last,
                                change = EXCLUDED.change,
                                change_percent = EXCLUDED.change_percent,
                                volume = EXCLUDED.volume,
                                updated_at = NOW()
                            RETURNING (xmax = 0) as inserted
                        """)
                        
                        result = await session.execute(query, {
                            'time': row['time'],
                            'symbol': row['symbol'],
                            'import_symbol': row['import_symbol'],
                            'source': row['source'],
                            'timeframe': row['timeframe'],
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'last': float(row['last']),
                            'change': float(row['change']),
                            'change_percent': float(row['change_percent']),
                            'volume': int(row['volume']) if pd.notna(row['volume']) else 0
                        })
                        
                        was_inserted = result.scalar()
                        if was_inserted:
                            inserted += 1
                        else:
                            updated += 1
                            
                    except Exception as e:
                        logger.debug(f"Error inserting row: {e}")
                        skipped += 1
                        continue
                
                await session.commit()
                logger.info(f"Processed {min(i+batch_size, len(df))}/{len(df)} records")
                
        await engine.dispose()
        
        logger.info(f"Import complete: {inserted} inserted, {updated} updated, {skipped} skipped")
        return inserted, updated, skipped


# =============================================================================
# CLI Interface
# =============================================================================

def _download_and_import_symbol(
    rise_symbol: str,
    start_date: datetime,
    end_date: datetime,
    output_dir: str,
    import_db: bool,
    resume: bool,
) -> None:
    """
    Download M1 data for a single RiseTrader internal symbol from Dukascopy,
    optionally aggregating to H1 and importing both timeframes to the database.

    Args:
        rise_symbol: Internal name, e.g. 'USA500', 'BRENT_OIL', 'GBPJPY'.
                     Must be present in SYMBOL_MAPPING.
        start_date:  Earliest date to fetch.  Overridden by DB resume point if
                     resume=True and the DB already has later data.
        end_date:    Latest date to fetch (inclusive).
        output_dir:  Root output directory; CSVs land in <output_dir>/dukascopy/.
        import_db:   When True, insert M1 and H1 candles directly into PostgreSQL.
        resume:      When True, query MAX(time) for this symbol from the DB and
                     advance start_date to (resume_point + 1 minute) to avoid
                     re-downloading data already present.

    Edge cases:
        - Unknown symbol: logs an error and returns without raising.
        - Empty download (weekend gap, holiday): skips CSV write and DB import.
        - If DB resume query fails (DB offline), falls back to start_date with a
          warning rather than aborting the run.
    """
    mapping = SYMBOL_MAPPING.get(rise_symbol)
    if mapping is None:
        logger.error(
            f"Unknown symbol '{rise_symbol}'. "
            f"Known symbols: {list(SYMBOL_MAPPING.keys())}"
        )
        return

    dk_symbol, _, description = mapping
    if dk_symbol is None:
        logger.error(f"'{rise_symbol}' has no Dukascopy source — skipping.")
        return

    effective_start = start_date

    if resume:
        try:
            resume_point: Optional[datetime] = asyncio.run(
                get_resume_point(rise_symbol, "M1")
            )
            if resume_point is not None:
                # Advance start to one minute after the last stored candle
                resume_dt = resume_point.replace(tzinfo=None) + timedelta(minutes=1)
                if resume_dt > end_date:
                    logger.info(
                        f"[{rise_symbol}] DB is up to date "
                        f"(latest M1: {resume_point}). Nothing to download."
                    )
                    return
                logger.info(
                    f"[{rise_symbol}] Resuming from {resume_dt.date()} "
                    f"(DB latest M1: {resume_point.date()})"
                )
                effective_start = resume_dt
            else:
                logger.info(
                    f"[{rise_symbol}] No existing data found — "
                    f"downloading from {effective_start.date()}"
                )
        except Exception as exc:
            logger.warning(
                f"[{rise_symbol}] Resume query failed ({exc}); "
                f"falling back to --start {start_date.date()}"
            )

    downloader = DukascopyDownloader(output_dir=f"{output_dir}/dukascopy")
    logger.info(
        f"[{rise_symbol}] Downloading {dk_symbol} "
        f"({description}) {effective_start.date()} → {end_date.date()}"
    )
    df_m1 = downloader.download_range(dk_symbol, effective_start, end_date)

    if df_m1.empty:
        logger.warning(f"[{rise_symbol}] No M1 data returned — nothing to save.")
        return

    # Save M1 CSV
    m1_filepath = downloader.save_csv(df_m1, dk_symbol, effective_start, end_date)

    # Aggregate to H1
    df_h1 = aggregate_m1_to_h1(df_m1)
    logger.info(f"[{rise_symbol}] Aggregated {len(df_m1)} M1 → {len(df_h1)} H1 candles")

    # Save H1 CSV alongside M1
    if not df_h1.empty:
        h1_filename = (
            f"{dk_symbol}_{effective_start.strftime('%Y%m%d')}"
            f"_{end_date.strftime('%Y%m%d')}_H1.csv"
        )
        h1_filepath = downloader.output_dir / h1_filename
        df_h1.to_csv(h1_filepath, index=False)
        logger.info(f"[{rise_symbol}] Saved {len(df_h1)} H1 records to {h1_filepath}")

    if import_db:
        importer = DataImporter()
        logger.info(f"[{rise_symbol}] Importing M1 to DB as '{rise_symbol}'...")
        asyncio.run(
            importer.import_csv(m1_filepath, rise_symbol, source='DUKASCOPY', timeframe='M1')
        )
        if not df_h1.empty:
            logger.info(f"[{rise_symbol}] Importing H1 to DB as '{rise_symbol}'...")
            asyncio.run(
                importer.import_csv(h1_filepath, rise_symbol, source='DUKASCOPY', timeframe='H1')
            )


def main():
    parser = argparse.ArgumentParser(
        description='Download free market data from Dukascopy / HistData',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download 3 symbols with resume + DB import
  python3 scripts/download_free_data.py --symbols USA500,BRENT_OIL,GBPJPY --start 2020-01-01 --import-db --resume

  # Single symbol, no DB import
  python3 scripts/download_free_data.py --symbols USA500 --start 2020-01-01

  # Legacy single-symbol Dukascopy download (raw Dukascopy symbol name)
  python3 scripts/download_free_data.py --source dukascopy --symbol WTIUSD --start 2024-01-01

Known --symbols values: CrudeOIL, XAUUSD, SPX500, DXY, USA500, BRENT_OIL, GBPJPY
        """
    )
    # New multi-symbol interface
    parser.add_argument(
        '--symbols', type=str, default=None,
        help=(
            'Comma-separated list of RiseTrader internal symbol names to download '
            '(e.g. USA500,BRENT_OIL,GBPJPY).  When set, --source is forced to '
            '"dukascopy" and H1 aggregation is performed automatically.'
        )
    )
    parser.add_argument(
        '--resume', action='store_true',
        help=(
            'Skip already-downloaded data by querying MAX(time) from PostgreSQL '
            'for each symbol before downloading.  Requires DB to be reachable.'
        )
    )
    # Legacy interface (kept for backward compatibility)
    parser.add_argument('--source', choices=['dukascopy', 'histdata', 'all'],
                        default='dukascopy', help='Data source (legacy --symbol path)')
    parser.add_argument('--symbol', type=str, default='WTIUSD',
                        help='Raw Dukascopy/HistData symbol name (legacy single-symbol path)')
    parser.add_argument('--start', type=str, default='2024-01-01',
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None,
                        help='End date (YYYY-MM-DD), defaults to today')
    parser.add_argument('--output-dir', type=str, default='data',
                        help='Output directory root')
    parser.add_argument('--import-db', action='store_true',
                        help='Import downloaded data to PostgreSQL database')
    parser.add_argument('--target-symbol', type=str, default=None,
                        help='Override target symbol name for DB (legacy path only)')

    args = parser.parse_args()

    start_date = datetime.strptime(args.start, '%Y-%m-%d')
    end_date = datetime.strptime(args.end, '%Y-%m-%d') if args.end else datetime.now()

    # -------------------------------------------------------------------------
    # New path: --symbols USA500,BRENT_OIL,GBPJPY
    # -------------------------------------------------------------------------
    if args.symbols:
        symbol_list = [s.strip() for s in args.symbols.split(',') if s.strip()]
        logger.info(
            f"Multi-symbol download: {symbol_list} "
            f"| start={start_date.date()} end={end_date.date()} "
            f"| resume={args.resume} import_db={args.import_db}"
        )
        for rise_symbol in symbol_list:
            try:
                _download_and_import_symbol(
                    rise_symbol=rise_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    output_dir=args.output_dir,
                    import_db=args.import_db,
                    resume=args.resume,
                )
            except Exception as exc:
                logger.error(f"[{rise_symbol}] Unhandled error: {exc}", exc_info=True)
        return

    # -------------------------------------------------------------------------
    # Legacy path: --source / --symbol (raw Dukascopy symbol names)
    # -------------------------------------------------------------------------
    if args.source == 'dukascopy':
        downloader = DukascopyDownloader(output_dir=f"{args.output_dir}/dukascopy")
        df = downloader.download_range(args.symbol, start_date, end_date)
        if not df.empty:
            filepath = downloader.save_csv(df, args.symbol, start_date, end_date)

            if args.import_db:
                target = args.target_symbol or args.symbol
                importer = DataImporter()
                asyncio.run(importer.import_csv(filepath, target, source='DUKASCOPY'))

    elif args.source == 'histdata':
        downloader = HistDataDownloader(output_dir=f"{args.output_dir}/histdata")
        df = downloader.download_range(args.symbol, start_date.year, end_date.year)
        if not df.empty:
            filepath = downloader.save_csv(df, args.symbol)

            if args.import_db:
                target = args.target_symbol or args.symbol
                importer = DataImporter()
                asyncio.run(importer.import_csv(filepath, target, source='HISTDATA'))

    elif args.source == 'all':
        logger.info("Downloading all available symbols from all sources...")

        duka = DukascopyDownloader(output_dir=f"{args.output_dir}/dukascopy")
        for symbol in DUKASCOPY_INSTRUMENTS.keys():
            try:
                df = duka.download_range(symbol, start_date, end_date)
                if not df.empty:
                    duka.save_csv(df, symbol, start_date, end_date)
            except Exception as e:
                logger.error(f"Error downloading {symbol} from Dukascopy: {e}")

        hist = HistDataDownloader(output_dir=f"{args.output_dir}/histdata")
        for symbol in ['WTIUSD', 'XAUUSD', 'SPX500USD', 'UDX']:
            try:
                df = hist.download_range(symbol, start_date.year, end_date.year)
                if not df.empty:
                    hist.save_csv(df, symbol)
            except Exception as e:
                logger.error(f"Error downloading {symbol} from HistData: {e}")


if __name__ == '__main__':
    main()
