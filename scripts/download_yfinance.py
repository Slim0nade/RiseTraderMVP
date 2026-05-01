#!/usr/bin/env python3
"""
yfinance D1 downloader for TSLA and MSFT.
D1 only — yfinance does not provide reliable M1/H1 for equities at no cost.

Writes directly to PostgreSQL (no CSV intermediate).  Supports resumable
runs by querying MAX(time) per symbol before downloading.

Usage:
    python3 scripts/download_yfinance.py
    python3 scripts/download_yfinance.py --symbol TSLA
"""
import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Symbol map  (internal DB name -> Yahoo Finance ticker)
# ---------------------------------------------------------------------------

YFINANCE_SYMBOLS = {
    "TSLA": "TSLA",
    "MSFT": "MSFT",
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def get_resume_point(conn: asyncpg.Connection, symbol: str) -> str:
    """
    Return the day *after* the latest D1 row already in the DB for this
    symbol, formatted as 'YYYY-MM-DD'.  Falls back to '2020-01-01' when the
    symbol has no rows yet.
    """
    row = await conn.fetchrow(
        """
        SELECT MAX(time)
        FROM market_data
        WHERE symbol = $1
          AND source = 'CSV'
          AND CAST(timeframe AS TEXT) = 'D1'
        """,
        symbol,
    )
    if row and row[0]:
        next_day = row[0].date() + timedelta(days=1)
        return next_day.strftime("%Y-%m-%d")
    return "2020-01-01"


async def insert_candles(
    conn: asyncpg.Connection, symbol: str, df: pd.DataFrame
) -> int:
    """
    Upsert D1 candles into market_data.

    Computes change and change_percent from open/close so the values match
    the convention used by every other importer in this codebase.

    Returns the number of rows submitted (including conflicts updated in-place).
    """
    rows = []
    for idx, row in df.iterrows():
        ts = idx.to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        o = float(row["Open"])
        c = float(row["Close"])
        change = round(c - o, 6)
        change_pct = round((c - o) / o * 100, 4) if o != 0 else 0.0
        vol = int(row["Volume"]) if pd.notna(row.get("Volume", 0)) else 0

        rows.append(
            (
                ts,                   # $1  time
                symbol,               # $2  symbol
                f"{symbol}_YF",       # $3  import_symbol
                "D1",                 # $4  timeframe  (cast below)
                "CSV",                # $5  source     (cast below)
                o,                    # $6  open
                float(row["High"]),   # $7  high
                float(row["Low"]),    # $8  low
                c,                    # $9  last  (close)
                change,               # $10 change
                change_pct,           # $11 change_percent
                vol,                  # $12 volume
            )
        )

    if not rows:
        return 0

    await conn.executemany(
        """
        INSERT INTO market_data
            (time, symbol, import_symbol, timeframe, source,
             open, high, low, last, change, change_percent, volume,
             created_at, updated_at)
        VALUES
            ($1, $2, $3, $4::timeframe, $5::datasource,
             $6, $7, $8, $9, $10, $11, $12,
             NOW(), NOW())
        ON CONFLICT (time, source, timeframe, symbol) DO UPDATE SET
            open            = EXCLUDED.open,
            high            = EXCLUDED.high,
            low             = EXCLUDED.low,
            last            = EXCLUDED.last,
            change          = EXCLUDED.change,
            change_percent  = EXCLUDED.change_percent,
            volume          = EXCLUDED.volume,
            updated_at      = NOW()
        """,
        rows,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Per-symbol orchestration
# ---------------------------------------------------------------------------


async def download_symbol(symbol: str, db_url: str) -> None:
    """Download D1 data for one symbol and upsert into PostgreSQL."""
    conn = await asyncpg.connect(db_url)
    try:
        start = await get_resume_point(conn, symbol)
        end = (datetime.utcnow().date() + timedelta(days=1)).isoformat()

        print(f"[{symbol}] Downloading D1 from {start} to {end} ...")

        ticker = yf.Ticker(YFINANCE_SYMBOLS[symbol])
        df = ticker.history(
            start=start,
            end=end,
            interval="1d",
            auto_adjust=True,
        )

        if df.empty:
            print(f"[{symbol}] No new data returned by yfinance")
            return

        # Drop rows with missing OHLC; sort chronologically; remove duplicates
        df = (
            df.dropna(subset=["Open", "High", "Low", "Close"])
            .sort_index()
            .loc[~df.index.duplicated(keep="last")]
        )

        count = await insert_candles(conn, symbol, df)
        print(
            f"[{symbol}] Upserted {count:,} D1 candles "
            f"({df.index[0].date()} -> {df.index[-1].date()})"
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download D1 candles for TSLA and MSFT from yfinance into PostgreSQL.",
        epilog="D1 only — yfinance does not provide reliable M1/H1 for equities.",
    )
    parser.add_argument(
        "--symbol",
        help="Download a specific symbol (TSLA or MSFT). Defaults to both.",
    )
    args = parser.parse_args()

    # Strip SQLAlchemy driver prefix if DATABASE_URL comes from .env
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:risetrader2024@localhost:5433/risetrader",
    )
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "+asyncpg", ""
    )

    symbols = [args.symbol] if args.symbol else list(YFINANCE_SYMBOLS.keys())

    for symbol in symbols:
        if symbol not in YFINANCE_SYMBOLS:
            print(f"Unknown symbol: {symbol}. Valid options: {list(YFINANCE_SYMBOLS.keys())}")
            sys.exit(1)
        await download_symbol(symbol, db_url)

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
