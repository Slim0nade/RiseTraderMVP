#!/usr/bin/env python3
"""
Historical Data Backfill for RiseTrader.

Downloads M1 candle data from Dukascopy and HistData, aggregates to H1,
and bulk-inserts both timeframes into PostgreSQL. Supports resumable runs
by querying MAX(time) per symbol/timeframe before each month.

Sources:
  - Dukascopy: tick data (bi5 binary) -> M1 aggregation via async HTTP
  - yfinance:  D1 daily candles for equities (TSLA, MSFT)

Target symbols:
  USA500     <- Dukascopy  USA500IDXUSD
  CrudeOIL   <- Dukascopy  LIGHTCMDUSD
  GBPJPY     <- Dukascopy  GBPJPY
  BRENT_OIL  <- Dukascopy  BRENTCMDUSD
  XAUUSD     <- Dukascopy  XAUUSD
  CORN       <- Dukascopy  CORNUSD  (probe only, confirmed unavailable)
  WHEAT      <- Dukascopy  WHEATUSD (probe only, confirmed unavailable)
  GASOLINE   <- Dukascopy  GASUSD   (probe only, confirmed unavailable)
  TSLA       <- yfinance   D1 only
  MSFT       <- yfinance   D1 only

Usage:
  python scripts/backfill_historical_data.py --symbols USA500,BRENT_OIL,GBPJPY
  python scripts/backfill_historical_data.py --symbols all
  python scripts/backfill_historical_data.py --symbols TSLA,MSFT --source yfinance
  python scripts/backfill_historical_data.py --symbols CrudeOIL --start 2019-01-01 --end 2024-01-01
"""

import argparse
import asyncio
import gzip
import logging
import lzma
import os
import ssl
import struct
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import aiohttp
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")

# ---------------------------------------------------------------------------
# Database connection (host machine -> Docker container on port 5433)
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "dbname": os.getenv("DB_NAME", "risetrader"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD") or "risetrader2024",
}

# ---------------------------------------------------------------------------
# Symbol registry
# ---------------------------------------------------------------------------

# Each entry: db_symbol -> {source, src_symbol, point, decimals}
# point = price multiplier for Dukascopy integer -> float conversion
DUKASCOPY_SYMBOLS: Dict[str, dict] = {
    "USA500": {
        "src_symbol": "USA500IDXUSD",
        "point": 0.001,
        "description": "S&P 500 Index",
    },
    "CrudeOIL": {
        "src_symbol": "LIGHTCMDUSD",
        "point": 0.001,
        "description": "WTI Crude Oil",
    },
    "GBPJPY": {
        "src_symbol": "GBPJPY",
        "point": 0.001,
        "description": "British Pound vs Japanese Yen",
    },
    "BRENT_OIL": {
        "src_symbol": "BRENTCMDUSD",
        "point": 0.001,
        "description": "Brent Crude Oil",
    },
    "XAUUSD": {
        "src_symbol": "XAUUSD",
        "point": 0.001,
        "description": "Gold Spot",
    },
    # Commodity availability probes — may return no data; handled gracefully
    "CORN": {
        "src_symbol": "CORNUSD",
        "point": 0.001,
        "description": "Corn futures (probe)",
    },
    "WHEAT": {
        "src_symbol": "WHEATUSD",
        "point": 0.001,
        "description": "Wheat futures (probe)",
    },
    "GASOLINE": {
        "src_symbol": "GASUSD",
        "point": 0.00001,
        "description": "RBOB Gasoline (probe)",
    },
}

# HistData symbols: db_symbol -> src_symbol on FX-1-Minute-Data GitHub
# (empty — BRENT_OIL and GBPJPY moved to Dukascopy; HistData repo no longer hosts CSVs)
HISTDATA_SYMBOLS: Dict[str, str] = {}

YFINANCE_SYMBOLS: Dict[str, str] = {
    "TSLA": "TSLA",
    "MSFT": "MSFT",
}

# Full list of all supported db symbols (used for --symbols all)
ALL_SYMBOLS = (
    list(DUKASCOPY_SYMBOLS.keys())
    + list(HISTDATA_SYMBOLS.keys())
    + list(YFINANCE_SYMBOLS.keys())
)

# ---------------------------------------------------------------------------
# Default date range
# ---------------------------------------------------------------------------

DEFAULT_START = date(2019, 1, 1)
DEFAULT_END = date(2026, 1, 1)

# ---------------------------------------------------------------------------
# Dukascopy downloader (async, aiohttp)
# Re-implements the proven pattern from download_dukascopy_host.py
# ---------------------------------------------------------------------------

DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"


def _parse_bi5(data: bytes, point: float) -> List[dict]:
    """
    Parse Dukascopy bi5 (LZMA or gzip compressed) binary tick records.

    Each record is 20 bytes big-endian:
      uint32: milliseconds since start-of-hour
      uint32: ask price (raw integer)
      uint32: bid price (raw integer)
      float32: ask volume
      float32: bid volume

    Returns list of dicts with keys: ms, mid, volume
    Price = raw_int * point.

    Args:
        data: Raw compressed bytes from Dukascopy HTTP response.
        point: Decimal point multiplier (e.g., 0.001 for 3 decimal places).

    Returns:
        List of tick dicts. Empty list if data is empty or unparseable.
    """
    if not data:
        return []
    try:
        try:
            raw = lzma.decompress(data)
        except Exception:
            raw = gzip.decompress(data)
    except Exception:
        return []

    ticks = []
    record_size = 20
    for i in range(0, len(raw) - record_size + 1, record_size):
        chunk = raw[i : i + record_size]
        if len(chunk) < record_size:
            break
        ms, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(">IIIff", chunk)
        mid = (ask_raw + bid_raw) / 2 * point
        ticks.append({"ms": ms, "mid": mid, "volume": ask_vol + bid_vol})
    return ticks


def _ticks_to_m1(ticks: List[dict], hour_start: datetime) -> List[dict]:
    """
    Aggregate intra-hour tick data into 1-minute OHLCV candles.

    Args:
        ticks: List of tick dicts (ms, mid, volume) for a single hour.
        hour_start: UTC datetime for the start of that hour (minute=0, second=0).

    Returns:
        List of M1 candle dicts: {time, open, high, low, close, volume}.
        One entry per minute that had at least one tick.
    """
    if not ticks:
        return []
    groups: Dict[int, List[dict]] = defaultdict(list)
    for t in ticks:
        groups[t["ms"] // 60000].append(t)

    candles = []
    for minute_idx, group in sorted(groups.items()):
        prices = [t["mid"] for t in group]
        candles.append(
            {
                "time": hour_start + timedelta(minutes=minute_idx),
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "volume": int(sum(t["volume"] for t in group)),
            }
        )
    return candles


async def _download_hour(
    session: aiohttp.ClientSession,
    dk_symbol: str,
    dt: datetime,
    point: float,
    semaphore: asyncio.Semaphore,
    retries: int = 2,
) -> List[dict]:
    """
    Download and parse one hour of Dukascopy tick data into M1 candles.

    Args:
        session: aiohttp ClientSession.
        dk_symbol: Dukascopy symbol string (e.g., 'LIGHTCMDUSD').
        dt: Exact UTC datetime for the hour (e.g., datetime(2024, 3, 15, 9)).
        point: Decimal multiplier for price conversion.
        semaphore: Concurrency limiter.
        retries: Number of retry attempts on transient errors.

    Returns:
        List of M1 candle dicts, or empty list on 404 / network failure.
    """
    # Dukascopy uses 0-indexed months in the URL
    month_0 = dt.month - 1
    url = f"{DUKASCOPY_BASE}/{dk_symbol}/{dt.year}/{month_0:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"

    for attempt in range(retries + 1):
        async with semaphore:
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        ticks = _parse_bi5(data, point)
                        hour_start = dt.replace(minute=0, second=0, microsecond=0)
                        return _ticks_to_m1(ticks, hour_start)
                    elif resp.status == 404:
                        return []  # No data for this hour (weekend/holiday)
                    elif resp.status == 503 and attempt < retries:
                        await asyncio.sleep(1.5)
                        continue
                    else:
                        return []
            except asyncio.TimeoutError:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return []
            except Exception:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return []
    return []


async def download_dukascopy_month(
    dk_symbol: str,
    point: float,
    year: int,
    month: int,
) -> pd.DataFrame:
    """
    Download all M1 candles for one calendar month from Dukascopy.

    Uses async HTTP with a semaphore of 15 to avoid overwhelming the server.
    All 24 hours per trading day are fetched concurrently within each day.

    Args:
        dk_symbol: Dukascopy source symbol (e.g., 'USA500IDXUSD').
        point: Price decimal multiplier.
        year: Calendar year (e.g., 2023).
        month: Calendar month, 1-indexed (e.g., 3 for March).

    Returns:
        DataFrame with columns [time, open, high, low, close, volume], sorted
        by time with duplicates removed. Empty DataFrame if no data found.
    """
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(limit=30, limit_per_host=15, ssl=ssl_ctx)
    semaphore = asyncio.Semaphore(15)

    all_candles: List[dict] = []
    current = month_start

    async with aiohttp.ClientSession(connector=connector) as session:
        while current < month_end:
            if current.weekday() < 5:  # Skip Saturday (5) and Sunday (6)
                tasks = [
                    _download_hour(
                        session,
                        dk_symbol,
                        datetime(current.year, current.month, current.day, hour),
                        point,
                        semaphore,
                    )
                    for hour in range(24)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        all_candles.extend(r)
            current += timedelta(days=1)

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# HistData downloader (sync, urllib — matches download_free_data.py pattern)
# ---------------------------------------------------------------------------

HISTDATA_BASE = (
    "https://raw.githubusercontent.com/philipperemy/FX-1-Minute-Data/master/data"
)


def download_histdata_year(src_symbol: str, year: int) -> Optional[pd.DataFrame]:
    """
    Download one year of M1 data from the FX-1-Minute-Data GitHub repo.

    File format: CSV with columns [DateTime, Open, High, Low, Close, Volume].
    No header row — uses fixed column names.

    Args:
        src_symbol: HistData symbol (e.g., 'BCOUSD', 'GBPJPY').
        year: Calendar year (e.g., 2022).

    Returns:
        DataFrame with [time, open, high, low, close, volume] or None on 404/error.
        The 'time' column is a timezone-naive UTC datetime.
    """
    url = f"{HISTDATA_BASE}/{src_symbol}/{src_symbol}_{year}.csv"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urlopen(req, timeout=60, context=SSL_CONTEXT)
        df = pd.read_csv(
            BytesIO(resp.read()),
            names=["time", "open", "high", "low", "close", "volume"],
            parse_dates=["time"],
        )
        if df.empty:
            return None
        logger.info(f"  HistData: {src_symbol} {year} -> {len(df):,} M1 candles")
        return df
    except HTTPError as e:
        if e.code == 404:
            logger.debug(f"  HistData: {src_symbol} {year} not available (404)")
        else:
            logger.warning(f"  HistData: HTTP {e.code} for {src_symbol} {year}")
        return None
    except URLError as e:
        logger.warning(f"  HistData: URL error for {src_symbol} {year}: {e}")
        return None
    except Exception as e:
        logger.warning(f"  HistData: parse error for {src_symbol} {year}: {e}")
        return None


def filter_histdata_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """
    Filter a full-year HistData DataFrame to a single calendar month.

    Args:
        df: Full-year DataFrame with 'time' column (datetime).
        year: Target year.
        month: Target month (1-indexed).

    Returns:
        Filtered DataFrame for that month, sorted by time.
    """
    mask = (df["time"].dt.year == year) & (df["time"].dt.month == month)
    return df[mask].copy().sort_values("time").reset_index(drop=True)


# ---------------------------------------------------------------------------
# yfinance downloader (D1 only for equities)
# ---------------------------------------------------------------------------


def download_yfinance_d1(yf_symbol: str, start: date, end: date) -> pd.DataFrame:
    """
    Download daily (D1) OHLCV data from yfinance for the given date range.

    Args:
        yf_symbol: Yahoo Finance ticker (e.g., 'TSLA', 'MSFT').
        start: Inclusive start date.
        end: Exclusive end date (yfinance convention).

    Returns:
        DataFrame with [time, open, high, low, close, volume] or empty DataFrame.
        'time' column contains timezone-naive UTC dates at midnight.

    Raises:
        ImportError: If yfinance is not installed.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        raise

    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        auto_adjust=True,
    )
    if hist.empty:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "time": hist.index.tz_localize(None) if hist.index.tz else hist.index,
            "open": hist["Open"].values,
            "high": hist["High"].values,
            "low": hist["Low"].values,
            "close": hist["Close"].values,
            "volume": hist["Volume"].astype(int).values,
        }
    )
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    logger.info(f"  yfinance: {yf_symbol} D1 -> {len(df):,} candles")
    return df


# ---------------------------------------------------------------------------
# M1 -> H1 aggregation (in Python before insert)
# ---------------------------------------------------------------------------


def aggregate_m1_to_period(df_m1: pd.DataFrame, freq: str = "h") -> pd.DataFrame:
    """
    Aggregate 1-minute candles into a higher timeframe.

    Groups by flooring the time to the given frequency.
    - open:   first M1 open within the period
    - high:   max of all M1 highs
    - low:    min of all M1 lows
    - close:  last M1 close
    - volume: sum of all M1 volumes

    Args:
        df_m1: DataFrame with [time, open, high, low, close, volume].
               'time' must be datetime-compatible.
        freq: Pandas frequency string: "h" for H1, "30min" for M30.

    Returns:
        DataFrame with aggregated candles, same column layout.
        Empty DataFrame if input is empty.
    """
    if df_m1.empty:
        return pd.DataFrame()

    df = df_m1.copy()
    df["time"] = pd.to_datetime(df["time"])
    df["period"] = df["time"].dt.floor(freq)

    agg = (
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
    return agg.sort_values("time").reset_index(drop=True)


def aggregate_m1_to_h1(df_m1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate M1 candles to H1 (backward-compatible wrapper)."""
    return aggregate_m1_to_period(df_m1, freq="h")


def aggregate_m1_to_m30(df_m1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate M1 candles to M30."""
    return aggregate_m1_to_period(df_m1, freq="30min")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_db_connection() -> psycopg2.extensions.connection:
    """
    Open a psycopg2 connection to the RiseTrader PostgreSQL instance.

    Connects to localhost:5433 (Docker port-forward) using credentials from
    DB_CONFIG, which can be overridden via environment variables.

    Returns:
        Open psycopg2 connection with autocommit=False.
    """
    return psycopg2.connect(**DB_CONFIG)


def query_max_time(
    conn,
    db_symbol: str,
    timeframe: str,
    source: str,
) -> Optional[datetime]:
    """
    Query the latest candle timestamp for a symbol/timeframe/source combo.

    Used for resumable downloads: any month whose last day is <= max_time
    has already been fully imported and can be skipped.

    Args:
        conn: Open psycopg2 connection.
        db_symbol: Target symbol name in the DB (e.g., 'USA500').
        timeframe: DB timeframe enum value (e.g., 'M1', 'H1').
        source: DB datasource enum value (e.g., 'DUKASCOPY', 'HISTDATA', 'CSV').

    Returns:
        UTC-aware datetime of the latest row, or None if no rows exist.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT MAX(time)
        FROM market_data
        WHERE symbol = %s AND timeframe = %s::timeframe AND source = %s::datasource
        """,
        (db_symbol, timeframe, source),
    )
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    return None


def bulk_insert(
    conn,
    rows: List[tuple],
    batch_size: int = 50_000,
) -> int:
    """
    Bulk-insert OHLCV rows into market_data using psycopg2 execute_values.

    Each row tuple must be:
      (time, symbol, import_symbol, timeframe, source,
       open, high, low, last, change, change_percent, volume)

    Uses ON CONFLICT DO NOTHING to handle the unique constraint
    (time, source, timeframe, symbol) silently.

    Args:
        conn: Open psycopg2 connection.
        rows: List of 12-element tuples (see format above).
        batch_size: Number of rows per execute_values call (default 50,000).

    Returns:
        Total number of rows submitted (includes conflicts that were skipped).
    """
    if not rows:
        return 0

    insert_sql = """
        INSERT INTO market_data
            (time, symbol, import_symbol, timeframe, source,
             open, high, low, last, change, change_percent, volume,
             created_at, updated_at)
        VALUES %s
        ON CONFLICT (time, source, timeframe, symbol) DO NOTHING
    """
    template = """(
        %s, %s, %s, %s::timeframe, %s::datasource,
        %s, %s, %s, %s, %s, %s, %s,
        NOW(), NOW()
    )"""

    cur = conn.cursor()
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        execute_values(cur, insert_sql, batch, template=template, page_size=batch_size)
        total += len(batch)
    conn.commit()
    return total


def df_to_rows(
    df: pd.DataFrame,
    db_symbol: str,
    import_symbol: str,
    timeframe: str,
    source: str,
) -> List[tuple]:
    """
    Convert a candle DataFrame into the row-tuple format expected by bulk_insert.

    Computes:
      - change = close - open
      - change_percent = ((close - open) / open) * 100, rounded to 4 dp

    The DB 'last' column stores the close price. Timestamps are made UTC-aware.

    Args:
        df: DataFrame with [time, open, high, low, close, volume].
        db_symbol: Internal symbol name for the DB (e.g., 'USA500').
        import_symbol: Source symbol name (e.g., 'USA500IDXUSD').
        timeframe: DB timeframe string ('M1', 'H1', 'D1', etc.).
        source: DB source string ('DUKASCOPY', 'HISTDATA', 'CSV').

    Returns:
        List of 12-element tuples ready for bulk_insert.
    """
    rows = []
    for _, row in df.iterrows():
        t = row["time"]
        # Ensure UTC-aware timestamp
        if hasattr(t, "tzinfo") and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        elif hasattr(t, "tz") and t.tz is None:
            t = t.tz_localize("UTC")

        o = float(row["open"])
        c = float(row["close"])
        change = round(c - o, 6)
        change_pct = round((c - o) / o * 100, 4) if o != 0 else 0.0
        vol = int(row["volume"]) if pd.notna(row.get("volume", 0)) else 0

        rows.append(
            (
                t,
                db_symbol,
                import_symbol,
                timeframe,
                source,
                o,
                float(row["high"]),
                float(row["low"]),
                c,      # last = close
                change,
                change_pct,
                vol,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Symbol availability probe (Dukascopy)
# ---------------------------------------------------------------------------


async def probe_dukascopy_symbol(dk_symbol: str, point: float) -> bool:
    """
    Attempt to download one hour of data to verify a Dukascopy symbol exists.

    Probes the first Monday of January 2024 (2024-01-08, 10:00 UTC), which
    is a reliable trading day for most instruments. Returns True if any M1
    candles are returned for that hour.

    Args:
        dk_symbol: Dukascopy symbol to probe (e.g., 'CORNUSD').
        point: Price decimal multiplier.

    Returns:
        True if the symbol is available (got at least 1 candle), False otherwise.
    """
    probe_dt = datetime(2024, 1, 8, 10)  # First Monday of Jan 2024, 10:00 UTC
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    semaphore = asyncio.Semaphore(1)

    async with aiohttp.ClientSession(connector=connector) as session:
        candles = await _download_hour(session, dk_symbol, probe_dt, point, semaphore)
    return len(candles) > 0


def probe_histdata_symbol(src_symbol: str) -> bool:
    """
    Verify that a HistData/GitHub symbol has available data for 2024.

    This is a synchronous probe — it calls download_histdata_year which uses
    urllib (blocking I/O), so it must NOT be called inside an async context
    without running in a thread executor. In practice, backfill_histdata is
    dispatched via asyncio.to_thread() from run_backfill, so this is safe.

    Args:
        src_symbol: Symbol string (e.g., 'BCOUSD', 'GBPJPY').

    Returns:
        True if the 2024 CSV file exists and is non-empty, False otherwise.
    """
    df = download_histdata_year(src_symbol, 2024)
    return df is not None and not df.empty


# ---------------------------------------------------------------------------
# Core per-symbol backfill routines
# ---------------------------------------------------------------------------


async def backfill_dukascopy(
    db_symbol: str,
    dk_symbol: str,
    point: float,
    start: date,
    end: date,
    conn,
) -> None:
    """
    Backfill M1 and H1 data for a Dukascopy symbol over a date range.

    Processing strategy (memory-efficient):
      1. Probe symbol availability (one test hour). Skip if unavailable.
      2. For each calendar month between start and end:
         a. Check MAX(time) in DB — skip month if already fully imported.
         b. Download M1 candles for the month asynchronously.
         c. Aggregate M1 -> H1 in Python.
         d. Bulk-insert M1 and H1 into DB (50,000 rows/batch).
         e. Log progress: symbol, month, rows inserted, elapsed seconds.

    Args:
        db_symbol: Internal DB symbol name (e.g., 'USA500').
        dk_symbol: Dukascopy source symbol (e.g., 'USA500IDXUSD').
        point: Price decimal multiplier.
        start: First date to include (inclusive).
        end: Last date to include (exclusive — process up to but not including).
        conn: Open psycopg2 connection.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"DUKASCOPY: {db_symbol} ({dk_symbol})")
    logger.info(f"Range: {start} -> {end}")
    logger.info(f"{'='*60}")

    # Availability probe
    logger.info(f"  Probing symbol availability: {dk_symbol}...")
    available = await probe_dukascopy_symbol(dk_symbol, point)
    if not available:
        logger.warning(
            f"  SKIP {db_symbol}: symbol '{dk_symbol}' returned no data on probe. "
            f"This symbol may not be available on Dukascopy."
        )
        return

    logger.info(f"  Symbol confirmed available.")

    # Check what's already in DB to support resumability
    m1_max = query_max_time(conn, db_symbol, "M1", "DUKASCOPY")
    h1_max = query_max_time(conn, db_symbol, "H1", "DUKASCOPY")
    m30_max = query_max_time(conn, db_symbol, "M30", "DUKASCOPY")
    if m1_max:
        logger.info(f"  DB M1 latest: {m1_max.date()} — will skip completed months")
    if h1_max:
        logger.info(f"  DB H1 latest: {h1_max.date()} — will skip completed months")

    # Iterate month by month
    current_year = start.year
    current_month = start.month

    while date(current_year, current_month, 1) < end:
        month_str = f"{current_year}-{current_month:02d}"

        # Compute the last day of this month
        if current_month == 12:
            next_month_start = date(current_year + 1, 1, 1)
        else:
            next_month_start = date(current_year, current_month + 1, 1)
        last_day_of_month = next_month_start - timedelta(days=1)

        # Resumability check: if DB M1 already has data past end-of-month, skip
        if m1_max and m1_max.date() >= last_day_of_month:
            logger.info(f"  SKIP {db_symbol} M1 {month_str} (already imported)")
        else:
            t0 = time.time()
            logger.info(f"  Downloading {db_symbol} M1 {month_str}...")
            df_m1 = await download_dukascopy_month(
                dk_symbol, point, current_year, current_month
            )

            if df_m1.empty:
                logger.info(f"  {month_str}: no M1 data returned (holiday month or gap)")
            else:
                m1_rows = df_to_rows(df_m1, db_symbol, dk_symbol, "M1", "DUKASCOPY")
                inserted_m1 = bulk_insert(conn, m1_rows)
                elapsed = time.time() - t0
                logger.info(
                    f"  {db_symbol} M1 {month_str}: "
                    f"{len(m1_rows):,} submitted, {elapsed:.1f}s"
                )

                # Aggregate and insert H1 for the same month
                if h1_max and h1_max.date() >= last_day_of_month:
                    logger.info(f"  SKIP {db_symbol} H1 {month_str} (already imported)")
                else:
                    df_h1 = aggregate_m1_to_h1(df_m1)
                    if not df_h1.empty:
                        h1_rows = df_to_rows(
                            df_h1, db_symbol, dk_symbol, "H1", "DUKASCOPY"
                        )
                        bulk_insert(conn, h1_rows)
                        logger.info(
                            f"  {db_symbol} H1 {month_str}: {len(h1_rows):,} bars"
                        )

                # Aggregate and insert M30 for the same month
                if m30_max and m30_max.date() >= last_day_of_month:
                    logger.info(f"  SKIP {db_symbol} M30 {month_str} (already imported)")
                else:
                    df_m30 = aggregate_m1_to_m30(df_m1)
                    if not df_m30.empty:
                        m30_rows = df_to_rows(
                            df_m30, db_symbol, dk_symbol, "M30", "DUKASCOPY"
                        )
                        bulk_insert(conn, m30_rows)
                        logger.info(
                            f"  {db_symbol} M30 {month_str}: {len(m30_rows):,} bars"
                        )

        # Advance to next month
        if current_month == 12:
            current_year += 1
            current_month = 1
        else:
            current_month += 1

    logger.info(f"  {db_symbol} Dukascopy backfill complete.")


def backfill_histdata(
    db_symbol: str,
    src_symbol: str,
    start: date,
    end: date,
    conn,
) -> None:
    """
    Backfill M1 and H1 data for a HistData symbol over a date range.

    Processing strategy (memory-efficient):
      1. Probe symbol availability (2024 year file). Skip if unavailable.
      2. For each year in the range, download the full year CSV once.
      3. Filter to each calendar month within that year.
      4. Check DB MAX(time) for resumability — skip complete months.
      5. Bulk-insert M1 and aggregate -> H1 per month.

    Args:
        db_symbol: Internal DB symbol name (e.g., 'BRENT_OIL').
        src_symbol: HistData GitHub symbol (e.g., 'BCOUSD').
        start: First date to include (inclusive).
        end: Last date to include (exclusive).
        conn: Open psycopg2 connection.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"HISTDATA: {db_symbol} ({src_symbol})")
    logger.info(f"Range: {start} -> {end}")
    logger.info(f"{'='*60}")

    # Availability probe (sync — probe_histdata_symbol uses urllib blocking I/O)
    logger.info(f"  Probing symbol availability: {src_symbol}...")
    if not probe_histdata_symbol(src_symbol):
        logger.warning(
            f"  SKIP {db_symbol}: symbol '{src_symbol}' not found on HistData GitHub. "
            f"Data may not be available for this instrument."
        )
        return
    logger.info(f"  Symbol confirmed available.")

    # Check existing DB state
    m1_max = query_max_time(conn, db_symbol, "M1", "HISTDATA")
    h1_max = query_max_time(conn, db_symbol, "H1", "HISTDATA")
    m30_max = query_max_time(conn, db_symbol, "M30", "HISTDATA")
    if m1_max:
        logger.info(f"  DB M1 latest: {m1_max.date()} — will skip completed months")

    for year in range(start.year, end.year + 1):
        # Download the entire year's data at once (HistData is year-granular)
        year_df = download_histdata_year(src_symbol, year)
        if year_df is None or year_df.empty:
            logger.info(f"  {db_symbol} {year}: no data from HistData")
            continue

        # Process each month within this year
        start_month = start.month if year == start.year else 1
        # For the end year, don't process beyond the end date's month
        if year == end.year:
            # end is exclusive, so we process up to (end.month - 1) if end.day == 1
            # but to be safe, filter by the month's last day after the fact
            end_month = end.month
        else:
            end_month = 12

        for month in range(start_month, end_month + 1):
            month_str = f"{year}-{month:02d}"

            if month == 12:
                last_day_of_month = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day_of_month = date(year, month + 1, 1) - timedelta(days=1)

            # Skip if this month extends beyond our end date
            if date(year, month, 1) >= end:
                break

            # Resumability check
            if m1_max and m1_max.date() >= last_day_of_month:
                logger.info(f"  SKIP {db_symbol} M1 {month_str} (already imported)")
                continue

            t0 = time.time()
            df_month = filter_histdata_month(year_df, year, month)
            if df_month.empty:
                logger.info(f"  {month_str}: no data in this month")
                continue

            # Insert M1
            m1_rows = df_to_rows(df_month, db_symbol, src_symbol, "M1", "HISTDATA")
            bulk_insert(conn, m1_rows)
            elapsed = time.time() - t0
            logger.info(
                f"  {db_symbol} M1 {month_str}: "
                f"{len(m1_rows):,} rows, {elapsed:.1f}s"
            )

            # Aggregate to H1 and insert
            if h1_max and h1_max.date() >= last_day_of_month:
                logger.info(f"  SKIP {db_symbol} H1 {month_str} (already imported)")
            else:
                df_h1 = aggregate_m1_to_h1(df_month)
                if not df_h1.empty:
                    h1_rows = df_to_rows(df_h1, db_symbol, src_symbol, "H1", "HISTDATA")
                    bulk_insert(conn, h1_rows)
                    logger.info(
                        f"  {db_symbol} H1 {month_str}: {len(h1_rows):,} bars"
                    )

            # Aggregate to M30 and insert
            if m30_max and m30_max.date() >= last_day_of_month:
                logger.info(f"  SKIP {db_symbol} M30 {month_str} (already imported)")
            else:
                df_m30 = aggregate_m1_to_m30(df_month)
                if not df_m30.empty:
                    m30_rows = df_to_rows(df_m30, db_symbol, src_symbol, "M30", "HISTDATA")
                    bulk_insert(conn, m30_rows)
                    logger.info(
                        f"  {db_symbol} M30 {month_str}: {len(m30_rows):,} bars"
                    )

    logger.info(f"  {db_symbol} HistData backfill complete.")


def backfill_yfinance(
    db_symbol: str,
    yf_symbol: str,
    start: date,
    end: date,
    conn,
) -> None:
    """
    Backfill D1 daily candle data for an equity symbol via yfinance.

    Downloads the full date range in a single call (yfinance handles pagination).
    Inserts as D1 timeframe with source='CSV' and import_symbol='{SYMBOL}_YF'.

    Args:
        db_symbol: Internal DB symbol name (e.g., 'TSLA').
        yf_symbol: Yahoo Finance ticker (e.g., 'TSLA').
        start: Inclusive start date.
        end: Exclusive end date.
        conn: Open psycopg2 connection.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"YFINANCE D1: {db_symbol} ({yf_symbol})")
    logger.info(f"Range: {start} -> {end}")
    logger.info(f"{'='*60}")

    # Resumability: find latest D1 row
    d1_max = query_max_time(conn, db_symbol, "D1", "CSV")
    if d1_max:
        resume_start = (d1_max.date() + timedelta(days=1))
        if resume_start >= end:
            logger.info(f"  {db_symbol} D1 already up to date (latest: {d1_max.date()})")
            return
        logger.info(f"  Resuming from {resume_start} (DB latest: {d1_max.date()})")
        start = resume_start

    t0 = time.time()
    df = download_yfinance_d1(yf_symbol, start, end)
    if df.empty:
        logger.warning(f"  {db_symbol}: yfinance returned no D1 data")
        return

    import_symbol = f"{yf_symbol}_YF"
    rows = df_to_rows(df, db_symbol, import_symbol, "D1", "CSV")
    inserted = bulk_insert(conn, rows)
    elapsed = time.time() - t0
    logger.info(
        f"  {db_symbol} D1: {len(rows):,} rows submitted, "
        f"{elapsed:.1f}s "
        f"[{df['time'].min().date()} -> {df['time'].max().date()}]"
    )


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill historical M1/H1/D1 candle data into RiseTrader PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backfill_historical_data.py --symbols USA500,BRENT_OIL,GBPJPY
  python scripts/backfill_historical_data.py --symbols all
  python scripts/backfill_historical_data.py --symbols TSLA,MSFT --source yfinance
  python scripts/backfill_historical_data.py --symbols CrudeOIL --start 2022-01-01 --end 2024-01-01

All DB symbol names (case-sensitive):
  Dukascopy: USA500, CrudeOIL, GBPJPY, BRENT_OIL, XAUUSD, CORN*, WHEAT*, GASOLINE*
  yfinance:  TSLA, MSFT
  (* = probe only, confirmed unavailable on Dukascopy free feed)
        """,
    )
    parser.add_argument(
        "--symbols",
        type=str,
        required=True,
        help='Comma-separated DB symbol names, or "all"',
    )
    parser.add_argument(
        "--start",
        type=str,
        default=DEFAULT_START.isoformat(),
        help=f"Start date YYYY-MM-DD (default: {DEFAULT_START})",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=DEFAULT_END.isoformat(),
        help=f"End date YYYY-MM-DD (default: {DEFAULT_END})",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["auto", "dukascopy", "histdata", "yfinance"],
        default="auto",
        help="Force a specific source (default: auto-detect per symbol)",
    )
    return parser.parse_args()


async def run_backfill(
    symbols: List[str],
    start: date,
    end: date,
    force_source: Optional[str],
) -> None:
    """
    Orchestrate backfill for a list of DB symbols.

    For each symbol, determines the correct source (Dukascopy / HistData /
    yfinance) and calls the appropriate backfill routine. Dukascopy symbols
    use async download; HistData and yfinance are synchronous.

    Args:
        symbols: List of DB symbol names to process.
        start: Start date (inclusive).
        end: End date (exclusive for per-month logic).
        force_source: If set, override auto-detection with this source.
    """
    conn = get_db_connection()
    logger.info(f"Connected to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}")

    try:
        for db_symbol in symbols:
            # Determine source
            if force_source and force_source != "auto":
                source = force_source
            elif db_symbol in DUKASCOPY_SYMBOLS:
                source = "dukascopy"
            elif db_symbol in HISTDATA_SYMBOLS:
                source = "histdata"
            elif db_symbol in YFINANCE_SYMBOLS:
                source = "yfinance"
            else:
                logger.warning(
                    f"SKIP {db_symbol}: unknown symbol. "
                    f"Known symbols: {ALL_SYMBOLS}"
                )
                continue

            if source == "dukascopy":
                if db_symbol not in DUKASCOPY_SYMBOLS:
                    logger.warning(
                        f"SKIP {db_symbol}: not in DUKASCOPY_SYMBOLS registry"
                    )
                    continue
                cfg = DUKASCOPY_SYMBOLS[db_symbol]
                await backfill_dukascopy(
                    db_symbol,
                    cfg["src_symbol"],
                    cfg["point"],
                    start,
                    end,
                    conn,
                )

            elif source == "histdata":
                if db_symbol not in HISTDATA_SYMBOLS:
                    logger.warning(
                        f"SKIP {db_symbol}: not in HISTDATA_SYMBOLS registry"
                    )
                    continue
                src_symbol = HISTDATA_SYMBOLS[db_symbol]
                # Run blocking urllib/psycopg2 code in a thread so the event
                # loop stays responsive while year-file downloads are in progress.
                await asyncio.to_thread(
                    backfill_histdata, db_symbol, src_symbol, start, end, conn
                )

            elif source == "yfinance":
                if db_symbol not in YFINANCE_SYMBOLS:
                    logger.warning(
                        f"SKIP {db_symbol}: not in YFINANCE_SYMBOLS registry. "
                        f"yfinance supports: {list(YFINANCE_SYMBOLS.keys())}"
                    )
                    continue
                yf_sym = YFINANCE_SYMBOLS[db_symbol]
                # Run blocking yfinance HTTP + psycopg2 in a thread.
                await asyncio.to_thread(
                    backfill_yfinance, db_symbol, yf_sym, start, end, conn
                )

    finally:
        conn.close()
        logger.info("\nDatabase connection closed.")

    # Print final summary
    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)

    # Re-open a brief connection for summary stats
    conn2 = get_db_connection()
    try:
        cur = conn2.cursor()
        cur.execute(
            """
            SELECT symbol, timeframe, source,
                   COUNT(*) AS candles,
                   MIN(time)::date AS start_date,
                   MAX(time)::date AS end_date
            FROM market_data
            WHERE symbol = ANY(%s)
            GROUP BY symbol, timeframe, source
            ORDER BY symbol, timeframe, source
            """,
            (symbols,),
        )
        rows = cur.fetchall()
        if rows:
            print(f"\n{'Symbol':<14} {'TF':<5} {'Source':<12} {'Candles':>10} {'Start':>12} {'End':>12}")
            print("-" * 70)
            for r in rows:
                print(
                    f"{r[0]:<14} {r[1]:<5} {r[2]:<12} {r[3]:>10,} "
                    f"{str(r[4]):>12} {str(r[5]):>12}"
                )
    finally:
        conn2.close()


def main() -> None:
    """Entry point: parse args, resolve symbol list, run async backfill."""
    args = parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    if args.symbols.lower() == "all":
        symbols = ALL_SYMBOLS
    else:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    if not symbols:
        logger.error("No symbols specified. Use --symbols USA500,BRENT_OIL or --symbols all")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("RiseTrader Historical Data Backfill")
    logger.info(f"  Symbols:  {symbols}")
    logger.info(f"  Range:    {start} -> {end}")
    logger.info(f"  Source:   {args.source}")
    logger.info(f"  DB:       {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    logger.info("=" * 60)

    asyncio.run(run_backfill(symbols, start, end, args.source))


if __name__ == "__main__":
    main()
