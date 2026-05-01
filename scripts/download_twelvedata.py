#!/usr/bin/env python3
"""
TwelveData Historical Downloader for RiseTrader.

Downloads M1 candle data from the TwelveData REST API for WHEAT, CORN, and
GASOLINE. Aggregates M1 locally to H1. Bulk-upserts both timeframes into
PostgreSQL using asyncpg.

Resumable: queries MAX(time) per symbol/timeframe before each chunk and
skips already-imported windows.

Free-tier budget: 800 API calls/day, 5000 datapoints/call, 8 calls/min.
Script tracks calls in-memory and exits cleanly at 790 to leave a safety
margin, logging a message to re-run tomorrow.

Symbol mapping (TwelveData API symbol -> DB symbol):
  W_1   (CBOT)  -> WHEAT
  C_1   (CBOT)  -> CORN
  XB1   (NYMEX) -> GASOLINE

Usage:
  python3 scripts/download_twelvedata.py                      # All 3 symbols
  python3 scripts/download_twelvedata.py --symbol WHEAT       # Single symbol
  python3 scripts/download_twelvedata.py --dry-run            # Show plan, no API calls
  python3 scripts/download_twelvedata.py --symbol CORN --start 2022-01-01
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import asyncpg
import httpx
import pandas as pd

# ---------------------------------------------------------------------------
# Project root on path (mirrors existing scripts)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("twelvedata")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")
TWELVEDATA_BASE_URL = "https://api.twelvedata.com/time_series"

# DB connection — mirrors backfill_historical_data.py defaults
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:risetrader2024@localhost:5433/risetrader",
)

# Rate-limit constants (free tier)
DAILY_CALL_BUDGET = 800
DAILY_CALL_SOFT_LIMIT = 790       # Exit cleanly before hitting hard cap
CALLS_PER_MINUTE = 8
CALL_SLEEP_SECONDS = 1.5          # 1.5s between calls ≈ 40 calls/min (well under 8/min limit)
HTTP_429_RETRY_SLEEP = 60         # Back off 60s on rate-limit response
MAX_RETRIES = 3                    # Retry count for network/5xx errors
BATCH_SIZE = 5000                  # asyncpg batch insert size
PROGRESS_EVERY_N_CALLS = 50       # How often to print progress line

# M1 chunk: TwelveData returns up to 5000 datapoints; 3.5 days * 24h * 60min ≈ 5040
CHUNK_DAYS = 3.5

DEFAULT_START = datetime(2020, 1, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Symbol registry
# ---------------------------------------------------------------------------

TWELVEDATA_SYMBOLS: Dict[str, Dict[str, str]] = {
    "WHEAT": {
        "api_symbol": "W_1",
        "db_symbol": "WHEAT",
        "exchange": "CBOT",
    },
    "CORN": {
        "api_symbol": "C_1",
        "db_symbol": "CORN",
        "exchange": "CBOT",
    },
    "GASOLINE": {
        "api_symbol": "XB1",
        "db_symbol": "GASOLINE",
        "exchange": "NYMEX",
    },
}

SOURCE = "TWELVEDATA"

# ---------------------------------------------------------------------------
# Date-range chunking
# ---------------------------------------------------------------------------


def date_chunks(
    start: datetime,
    end: datetime,
    chunk_days: float = CHUNK_DAYS,
) -> Iterator[Tuple[datetime, datetime]]:
    """
    Yield (chunk_start, chunk_end) pairs spanning [start, end).

    Each chunk is at most chunk_days wide so that a single TwelveData M1
    call stays within the 5000-datapoint limit (3.5 days * 1440 min/day
    = 5040 ≈ limit).

    Args:
        start: Inclusive start of the range (UTC-aware).
        end: Exclusive end of the range (UTC-aware).
        chunk_days: Maximum width of each chunk in days (default 3.5).

    Yields:
        Tuples of (chunk_start, chunk_end), both UTC-aware datetimes.
    """
    current = start
    delta = timedelta(days=chunk_days)
    while current < end:
        chunk_end = min(current + delta, end)
        yield current, chunk_end
        current = chunk_end


# ---------------------------------------------------------------------------
# Database helpers (asyncpg direct — fastest for bulk inserts)
# ---------------------------------------------------------------------------


async def connect_db() -> asyncpg.Connection:
    """
    Open an asyncpg connection from DATABASE_URL.

    Returns:
        An open asyncpg.Connection.

    Raises:
        asyncpg.PostgresError: If the connection fails.
    """
    return await asyncpg.connect(DATABASE_URL)


async def get_resume_timestamp(
    conn: asyncpg.Connection,
    db_symbol: str,
    timeframe: str,
) -> Optional[datetime]:
    """
    Query the latest imported candle time for a symbol/timeframe/source trio.

    Used to skip already-imported windows on resumable runs.

    Args:
        conn: Open asyncpg connection.
        db_symbol: Internal DB symbol name (e.g. 'WHEAT').
        timeframe: DB timeframe enum string ('M1' or 'H1').

    Returns:
        UTC-aware datetime of the most recent row, or None if no rows exist.
    """
    row = await conn.fetchrow(
        """
        SELECT MAX(time)
        FROM market_data
        WHERE symbol = $1
          AND CAST(timeframe AS TEXT) = $2
          AND CAST(source AS TEXT) = $3
        """,
        db_symbol,
        timeframe,
        SOURCE,
    )
    if row and row[0]:
        ts = row[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


async def bulk_upsert(
    conn: asyncpg.Connection,
    rows: List[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """
    Upsert OHLCV rows into market_data via asyncpg copy/executemany.

    Uses ON CONFLICT (time, source, timeframe, symbol) DO NOTHING so that
    re-running the script is always safe.

    Each row tuple must be:
      (time, symbol, import_symbol, timeframe, source,
       open, high, low, last, change, change_percent, volume)

    Args:
        conn: Open asyncpg connection.
        rows: List of 12-element tuples (see format above).
        batch_size: Number of rows per executemany batch (default 5000).

    Returns:
        Total number of rows submitted (conflicts silently skipped by DB).
    """
    if not rows:
        return 0

    sql = """
        INSERT INTO market_data
            (time, symbol, import_symbol, timeframe, source,
             open, high, low, last, change, change_percent, volume,
             created_at, updated_at)
        VALUES ($1, $2, $3, $4::timeframe, $5::datasource,
                $6, $7, $8, $9, $10, $11, $12,
                NOW(), NOW())
        ON CONFLICT (time, source, timeframe, symbol) DO NOTHING
    """

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        await conn.executemany(sql, batch)
        total += len(batch)
    return total


def df_to_rows(
    df: pd.DataFrame,
    db_symbol: str,
    import_symbol: str,
    timeframe: str,
) -> List[tuple]:
    """
    Convert a candle DataFrame to the 12-element row-tuple format for bulk_upsert.

    Computes:
      - change       = close - open
      - change_pct   = (close - open) / open * 100, rounded to 4 dp

    The DB 'last' column stores the close price. Timestamps are made UTC-aware.

    Args:
        df: DataFrame with columns [time, open, high, low, close, volume].
        db_symbol: Internal DB symbol (e.g. 'WHEAT').
        import_symbol: TwelveData API symbol (e.g. 'W_1').
        timeframe: DB timeframe string ('M1' or 'H1').

    Returns:
        List of 12-element tuples ready for bulk_upsert.

    Edge cases:
        - Zero open price: change_pct set to 0.0 to avoid division by zero.
        - NaN volume: treated as 0.
        - Timezone-naive timestamps: localized to UTC.
    """
    rows = []
    for _, row in df.iterrows():
        t = row["time"]
        if isinstance(t, pd.Timestamp):
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            t = t.to_pydatetime()
        elif isinstance(t, datetime) and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)

        o = float(row["open"])
        h = float(row["high"])
        lo = float(row["low"])
        c = float(row["close"])
        vol = int(row["volume"]) if pd.notna(row.get("volume", 0)) else 0
        change = round(c - o, 6)
        change_pct = round((c - o) / o * 100, 4) if o != 0 else 0.0

        rows.append((t, db_symbol, import_symbol, timeframe, SOURCE,
                      o, h, lo, c, change, change_pct, vol))
    return rows


# ---------------------------------------------------------------------------
# TwelveData HTTP client
# ---------------------------------------------------------------------------


async def fetch_candles_twelvedata(
    client: httpx.AsyncClient,
    api_symbol: str,
    exchange: str,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    api_key: str,
    call_counter: List[int],
) -> Optional[pd.DataFrame]:
    """
    Fetch a single chunk of OHLCV candles from TwelveData /time_series endpoint.

    Handles HTTP 429 (rate limit) with a 60s sleep+retry and HTTP 4xx/5xx
    with up to MAX_RETRIES exponential-backoff retries.

    Args:
        client: Shared httpx.AsyncClient for connection pooling.
        api_symbol: TwelveData symbol string (e.g. 'W_1').
        exchange: Exchange code (e.g. 'CBOT').
        interval: Candle interval ('1min' for M1).
        start_dt: UTC-aware start of the window (inclusive).
        end_dt: UTC-aware end of the window (exclusive; used as end_date param).
        api_key: TwelveData API key.
        call_counter: Single-element list used as a mutable call counter
                      so callers can track total API calls made.

    Returns:
        DataFrame with columns [time, open, high, low, close, volume]
        sorted ascending by time, or None if the chunk returned no data.

    Edge cases:
        - 'no_data' status from API: returns None (not an error).
        - Empty values list: returns None.
        - Timestamps already UTC-aware from API but function normalises them.
    """
    params = {
        "symbol": api_symbol,
        "exchange": exchange,
        "interval": interval,
        "start_date": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "outputsize": 5000,
        "apikey": api_key,
        "format": "JSON",
        "timezone": "UTC",
    }

    for attempt in range(MAX_RETRIES):
        try:
            call_counter[0] += 1
            resp = await client.get(TWELVEDATA_BASE_URL, params=params, timeout=30.0)

            if resp.status_code == 429:
                logger.warning(
                    "[%s %s] HTTP 429 rate-limit on attempt %d — sleeping %ds",
                    api_symbol, interval, attempt + 1, HTTP_429_RETRY_SLEEP,
                )
                await asyncio.sleep(HTTP_429_RETRY_SLEEP)
                # Retry without incrementing call counter again
                call_counter[0] -= 1
                continue

            if resp.status_code >= 500:
                logger.warning(
                    "[%s %s] HTTP %d on attempt %d — retrying",
                    api_symbol, interval, resp.status_code, attempt + 1,
                )
                await asyncio.sleep(2 ** attempt)
                call_counter[0] -= 1
                continue

            if resp.status_code >= 400:
                logger.error(
                    "[%s %s] HTTP %d — skipping chunk %s → %s: %s",
                    api_symbol, interval, resp.status_code,
                    start_dt.date(), end_dt.date(), resp.text[:200],
                )
                return None

            data = resp.json()

            # API-level error codes
            if data.get("status") == "error":
                code = data.get("code", "unknown")
                msg = data.get("message", "")
                if code == 400 or "no_data" in msg.lower():
                    logger.debug(
                        "[%s %s] no_data for %s → %s",
                        api_symbol, interval, start_dt.date(), end_dt.date(),
                    )
                    return None
                logger.error(
                    "[%s %s] API error code=%s msg=%s — skipping chunk",
                    api_symbol, interval, code, msg,
                )
                return None

            values = data.get("values", [])
            if not values:
                return None

            # Parse into DataFrame
            records = []
            for v in values:
                records.append({
                    "time": pd.Timestamp(v["datetime"], tz="UTC"),
                    "open": float(v["open"]),
                    "high": float(v["high"]),
                    "low": float(v["low"]),
                    "close": float(v["close"]),
                    "volume": int(v.get("volume", 0)),
                })

            df = pd.DataFrame(records).sort_values("time").reset_index(drop=True)
            return df

        except httpx.TimeoutException:
            logger.warning(
                "[%s %s] Timeout on attempt %d — retrying",
                api_symbol, interval, attempt + 1,
            )
            await asyncio.sleep(2 ** attempt)
            call_counter[0] -= 1
            continue
        except Exception as exc:
            logger.warning(
                "[%s %s] Network error on attempt %d: %s — retrying",
                api_symbol, interval, attempt + 1, exc,
            )
            await asyncio.sleep(2 ** attempt)
            call_counter[0] -= 1
            continue

    logger.error(
        "[%s %s] All %d retries exhausted for chunk %s → %s — skipping",
        api_symbol, interval, MAX_RETRIES, start_dt.date(), end_dt.date(),
    )
    return None


# ---------------------------------------------------------------------------
# H1 aggregation from M1
# ---------------------------------------------------------------------------


def aggregate_m1_to_h1(df_m1: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate a M1 candle DataFrame to H1 using pandas resample.

    Resamples on the 'time' column (which must be a DatetimeTZDtype UTC index
    or column). Uses OHLCV semantics: open=first, high=max, low=min,
    close=last, volume=sum.

    Args:
        df_m1: DataFrame with columns [time, open, high, low, close, volume].
               'time' must be UTC-aware pd.Timestamp values.

    Returns:
        H1 DataFrame with the same columns, time aligned to the start of each
        hour. Rows with all-NaN OHLCV (gaps) are dropped via dropna(subset).

    Edge cases:
        - Empty input: returns empty DataFrame with same columns.
        - Partial hours at end of range: included (resample does not discard).
    """
    if df_m1.empty:
        return df_m1.copy()

    df = df_m1.copy()
    df = df.set_index("time").sort_index()

    df_h1 = df.resample("1h").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open", "high", "low", "close"])

    df_h1 = df_h1.reset_index().rename(columns={"time": "time"})
    return df_h1


# ---------------------------------------------------------------------------
# Per-symbol download orchestrator
# ---------------------------------------------------------------------------


async def download_symbol(
    symbol_key: str,
    start_override: Optional[datetime],
    end_dt: datetime,
    call_counter: List[int],
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Download M1 data for one symbol from TwelveData and upsert M1 + H1.

    Queries the DB for MAX(time) per timeframe to resume from the last
    successfully imported candle. Chunks the date range into 3.5-day windows
    to stay within the 5000-datapoint limit. Inserts M1 and H1 rows in a
    single DB connection per symbol.

    Args:
        symbol_key: Key in TWELVEDATA_SYMBOLS (e.g. 'WHEAT').
        start_override: If provided, use this as the start instead of DB MAX(time)+1m.
        end_dt: Exclusive end of the download range (UTC-aware).
        call_counter: Shared mutable [int] for tracking total API calls.
        dry_run: If True, log the plan but make no API or DB calls.

    Returns:
        Dict with keys 'm1_rows', 'h1_rows', 'chunks_skipped', 'chunks_downloaded'.

    Raises:
        SystemExit: If TWELVEDATA_API_KEY is empty at call time.
    """
    cfg = TWELVEDATA_SYMBOLS[symbol_key]
    api_symbol = cfg["api_symbol"]
    db_symbol = cfg["db_symbol"]
    exchange = cfg["exchange"]

    stats = {"m1_rows": 0, "h1_rows": 0, "chunks_skipped": 0, "chunks_downloaded": 0}

    conn = await connect_db()
    try:
        # Determine start for M1 (resume from last imported candle + 1 min)
        if start_override:
            m1_start = start_override
        else:
            max_m1 = await get_resume_timestamp(conn, db_symbol, "M1")
            if max_m1:
                m1_start = max_m1 + timedelta(minutes=1)
                logger.info(
                    "[%s M1] Resuming from %s", db_symbol, m1_start.strftime("%Y-%m-%d %H:%M")
                )
            else:
                m1_start = DEFAULT_START
                logger.info("[%s M1] No existing data — starting from %s", db_symbol, m1_start.date())

        if m1_start >= end_dt:
            logger.info("[%s] Already up to date (last=%s)", db_symbol, m1_start)
            return stats

        all_chunks = list(date_chunks(m1_start, end_dt))
        total_chunks = len(all_chunks)

        if dry_run:
            logger.info(
                "[DRY-RUN] %s: %d M1 chunks from %s → %s (~%d API calls)",
                db_symbol,
                total_chunks,
                m1_start.date(),
                end_dt.date(),
                total_chunks,
            )
            return stats

        logger.info(
            "[%s] Downloading %d chunks (%s → %s)",
            db_symbol, total_chunks, m1_start.date(), end_dt.date(),
        )

        async with httpx.AsyncClient() as http_client:
            for chunk_idx, (chunk_start, chunk_end) in enumerate(all_chunks, start=1):
                # Daily budget guard
                if call_counter[0] >= DAILY_CALL_SOFT_LIMIT:
                    logger.warning(
                        "Daily API budget reached (%d/%d calls). "
                        "Exiting cleanly — re-run tomorrow to continue.",
                        call_counter[0], DAILY_CALL_BUDGET,
                    )
                    return stats

                # Rate-limit sleep between calls (1.5s ≈ safe under 8/min)
                if chunk_idx > 1:
                    await asyncio.sleep(CALL_SLEEP_SECONDS)

                df_m1 = await fetch_candles_twelvedata(
                    client=http_client,
                    api_symbol=api_symbol,
                    exchange=exchange,
                    interval="1min",
                    start_dt=chunk_start,
                    end_dt=chunk_end,
                    api_key=TWELVEDATA_API_KEY,
                    call_counter=call_counter,
                )

                if df_m1 is None or df_m1.empty:
                    stats["chunks_skipped"] += 1
                    logger.debug(
                        "[%s M1] chunk %d/%d no data (%s → %s)",
                        db_symbol, chunk_idx, total_chunks,
                        chunk_start.date(), chunk_end.date(),
                    )
                    continue

                stats["chunks_downloaded"] += 1

                # Upsert M1
                m1_rows = df_to_rows(df_m1, db_symbol, api_symbol, "M1")
                inserted_m1 = await bulk_upsert(conn, m1_rows)
                stats["m1_rows"] += inserted_m1

                # Aggregate M1 → H1 and upsert
                df_h1 = aggregate_m1_to_h1(df_m1)
                if not df_h1.empty:
                    h1_rows = df_to_rows(df_h1, db_symbol, api_symbol, "H1")
                    inserted_h1 = await bulk_upsert(conn, h1_rows)
                    stats["h1_rows"] += inserted_h1

                # Progress log every N calls
                if call_counter[0] % PROGRESS_EVERY_N_CALLS == 0:
                    logger.info(
                        "[%s M1] %d/%d chunks | %s → %s | %d M1 rows | %d/%d daily budget",
                        db_symbol,
                        chunk_idx,
                        total_chunks,
                        chunk_start.strftime("%Y-%m-%d"),
                        chunk_end.strftime("%Y-%m-%d"),
                        stats["m1_rows"],
                        call_counter[0],
                        DAILY_CALL_BUDGET,
                    )

    finally:
        await conn.close()

    return stats


# ---------------------------------------------------------------------------
# Dry-run plan printer
# ---------------------------------------------------------------------------


async def show_dry_run_plan(
    symbols: List[str],
    start_override: Optional[datetime],
    end_dt: datetime,
) -> None:
    """
    Print the download plan without making any API or DB calls.

    For each symbol, queries the DB for the resume point and computes the
    number of M1 chunks required.

    Args:
        symbols: List of symbol keys to show the plan for.
        start_override: If set, overrides the DB resume point.
        end_dt: Exclusive end of the download range.
    """
    conn = await connect_db()
    try:
        for symbol_key in symbols:
            cfg = TWELVEDATA_SYMBOLS[symbol_key]
            db_symbol = cfg["db_symbol"]

            if start_override:
                m1_start = start_override
            else:
                max_m1 = await get_resume_timestamp(conn, db_symbol, "M1")
                m1_start = (max_m1 + timedelta(minutes=1)) if max_m1 else DEFAULT_START

            chunks = list(date_chunks(m1_start, end_dt))
            logger.info(
                "[DRY-RUN] %-10s | resume from %-20s | %d M1 chunks | ~%d API calls",
                db_symbol,
                m1_start.strftime("%Y-%m-%d %H:%M") if m1_start else "beginning",
                len(chunks),
                len(chunks),
            )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main(
    symbols: List[str],
    start_override: Optional[datetime],
    end_dt: datetime,
    dry_run: bool,
) -> None:
    """
    Main async entry point.

    Iterates over the requested symbols sequentially (to respect the shared
    daily API budget). Shared call_counter is passed to each symbol's
    downloader so the budget is tracked across all symbols in one run.

    Args:
        symbols: List of symbol keys from TWELVEDATA_SYMBOLS.
        start_override: Optional hard start date (overrides DB resume).
        end_dt: Exclusive end of the download range.
        dry_run: If True, only print the plan.
    """
    if not TWELVEDATA_API_KEY and not dry_run:
        logger.error(
            "TWELVEDATA_API_KEY environment variable is not set. "
            "Export it before running: export TWELVEDATA_API_KEY=your_key_here"
        )
        sys.exit(1)

    if dry_run:
        logger.info("=== DRY RUN — no API calls or DB writes will be made ===")
        await show_dry_run_plan(symbols, start_override, end_dt)
        return

    # Shared mutable call counter (single-element list for pass-by-reference)
    call_counter = [0]
    grand_total = {"m1_rows": 0, "h1_rows": 0}

    logger.info("=" * 60)
    logger.info("RiseTrader TwelveData Downloader")
    logger.info("Symbols : %s", ", ".join(symbols))
    logger.info("End date: %s", end_dt.date())
    logger.info("Budget  : %d calls/day (soft limit %d)", DAILY_CALL_BUDGET, DAILY_CALL_SOFT_LIMIT)
    logger.info("=" * 60)

    for symbol_key in symbols:
        if call_counter[0] >= DAILY_CALL_SOFT_LIMIT:
            logger.warning(
                "Daily budget reached before starting %s. Re-run tomorrow.",
                symbol_key,
            )
            break

        logger.info("\n--- %s ---", symbol_key)
        stats = await download_symbol(
            symbol_key=symbol_key,
            start_override=start_override,
            end_dt=end_dt,
            call_counter=call_counter,
            dry_run=dry_run,
        )
        grand_total["m1_rows"] += stats["m1_rows"]
        grand_total["h1_rows"] += stats["h1_rows"]

        logger.info(
            "[%s] DONE | M1 rows=%d | H1 rows=%d | chunks downloaded=%d | skipped=%d",
            symbol_key,
            stats["m1_rows"],
            stats["h1_rows"],
            stats["chunks_downloaded"],
            stats["chunks_skipped"],
        )

    logger.info("\n%s", "=" * 60)
    logger.info("ALL COMPLETE")
    logger.info("  Total M1 rows upserted : %d", grand_total["m1_rows"])
    logger.info("  Total H1 rows upserted : %d", grand_total["h1_rows"])
    logger.info("  Total API calls made   : %d / %d", call_counter[0], DAILY_CALL_BUDGET)
    logger.info("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Download WHEAT/CORN/GASOLINE candles from TwelveData into PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/download_twelvedata.py
  python3 scripts/download_twelvedata.py --symbol WHEAT
  python3 scripts/download_twelvedata.py --symbol CORN --start 2022-01-01
  python3 scripts/download_twelvedata.py --dry-run
        """,
    )
    parser.add_argument(
        "--symbol",
        type=str,
        choices=list(TWELVEDATA_SYMBOLS.keys()),
        default=None,
        help="Single symbol to download (default: all 3 symbols).",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Override start date (YYYY-MM-DD). Default: resume from DB MAX(time).",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Override end date (YYYY-MM-DD). Default: today UTC.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the download plan without making any API calls or DB writes.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Resolve symbol list
    if args.symbol:
        target_symbols = [args.symbol]
    else:
        target_symbols = list(TWELVEDATA_SYMBOLS.keys())

    # Resolve date range
    start_override: Optional[datetime] = None
    if args.start:
        start_override = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    if args.end:
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(tz=timezone.utc)
        end_dt = today.replace(hour=0, minute=0, second=0, microsecond=0)

    asyncio.run(main(target_symbols, start_override, end_dt, args.dry_run))
