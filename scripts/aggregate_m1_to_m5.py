#!/usr/bin/env python3
"""
Aggregate M1 candles to M5 in-place.

Mirrors scripts/aggregate_m1_to_h1.py but:
  - 5-minute buckets via to_timestamp(floor(epoch/300)*300).
  - Idempotent: uses ON CONFLICT (time, source, timeframe, symbol)
    DO UPDATE — safe to re-run after new M1 arrives.
  - Processes every source present in M1 independently, so the aggregate
    preserves source provenance (MT4 M1 -> MT4 M5, BC M1 -> BC M5).
  - Default scope is the 4 live symbols; --all processes every symbol
    that has M1 data.

Run
---
    python3 scripts/aggregate_m1_to_m5.py
    python3 scripts/aggregate_m1_to_m5.py --symbol CrudeOIL
    python3 scripts/aggregate_m1_to_m5.py --since 2024-01-01
    python3 scripts/aggregate_m1_to_m5.py --all
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


PG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5433")),
    "dbname": os.environ.get("PGDATABASE", "risetrader"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "risetrader2024"),
}

DEFAULT_SYMBOLS: List[str] = ["CrudeOIL", "USA500", "GBPJPY", "TSLA"]

# 5-minute bucket aggregate.
# Uses array_agg ordered by time to get first-open and last-close from
# the set of M1 bars in the bucket. SUM(volume). MAX(high), MIN(low).
AGG_SQL = """
    INSERT INTO market_data (
        time, symbol, import_symbol, timeframe, source,
        open, high, low, last,
        change, change_percent, volume,
        created_at, updated_at
    )
    SELECT
        to_timestamp(floor(extract(epoch from time) / 300) * 300) AT TIME ZONE 'UTC' AS bucket_time,
        symbol,
        'AGGREGATED_M5'                          AS import_symbol,
        'M5'::timeframe                          AS timeframe,
        source,
        (array_agg(open ORDER BY time))[1]       AS open,
        MAX(high)                                AS high,
        MIN(low)                                 AS low,
        (array_agg(last ORDER BY time DESC))[1]  AS last,
        0                                        AS change,
        0                                        AS change_percent,
        SUM(volume)                              AS volume,
        NOW()                                    AS created_at,
        NOW()                                    AS updated_at
    FROM market_data
    WHERE symbol = %s
      AND timeframe = 'M1'
      AND (%s::timestamptz IS NULL OR time >= %s::timestamptz)
    GROUP BY bucket_time, symbol, source
    ON CONFLICT (time, source, timeframe, symbol) DO UPDATE SET
        open           = EXCLUDED.open,
        high           = EXCLUDED.high,
        low            = EXCLUDED.low,
        last           = EXCLUDED.last,
        volume         = EXCLUDED.volume,
        change         = EXCLUDED.change,
        change_percent = EXCLUDED.change_percent,
        updated_at     = NOW()
"""

COUNT_M1_SQL = """
    SELECT COUNT(*) AS n,
           MIN(time) AS first_t,
           MAX(time) AS last_t,
           COUNT(DISTINCT source) AS source_count
    FROM market_data
    WHERE symbol = %s AND timeframe = 'M1'
      AND (%s::timestamptz IS NULL OR time >= %s::timestamptz);
"""

COUNT_M5_SQL = """
    SELECT COUNT(*) AS n,
           MIN(time) AS first_t,
           MAX(time) AS last_t
    FROM market_data
    WHERE symbol = %s AND timeframe = 'M5';
"""

LIST_ALL_SYMBOLS_SQL = """
    SELECT DISTINCT symbol
    FROM market_data
    WHERE timeframe = 'M1'
    ORDER BY symbol;
"""


def aggregate_one(conn, symbol: str, since: Optional[datetime]) -> None:
    print(f"\n[*] {symbol}")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(COUNT_M1_SQL, (symbol, since, since))
        pre = cur.fetchone()
        if not pre or not pre["n"]:
            print(f"  (no M1 data{' since ' + since.isoformat() if since else ''}) — skipping")
            return
        print(f"  M1 input:  {pre['n']:,} rows across {pre['source_count']} source(s)  "
              f"[{pre['first_t']} -> {pre['last_t']}]")

    t0 = datetime.now()
    with conn.cursor() as cur:
        cur.execute(AGG_SQL, (symbol, since, since))
        affected = cur.rowcount
    conn.commit()
    elapsed = (datetime.now() - t0).total_seconds()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(COUNT_M5_SQL, (symbol,))
        post = cur.fetchone()

    print(f"  M5 post:   {post['n']:,} rows  [{post['first_t']} -> {post['last_t']}]")
    print(f"  upserted:  {affected:,} buckets  ({elapsed:.1f}s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", help="Single symbol to aggregate (otherwise default 4 symbols or --all)")
    ap.add_argument("--since", help="ISO date/datetime; only aggregate M1 bars at or after this time")
    ap.add_argument("--all", action="store_true", help="Aggregate every symbol that has M1 data")
    args = ap.parse_args()

    since: Optional[datetime] = None
    if args.since:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))

    conn = psycopg2.connect(**PG)
    try:
        if args.symbol:
            symbols = [args.symbol]
        elif args.all:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(LIST_ALL_SYMBOLS_SQL)
                symbols = [r["symbol"] for r in cur.fetchall()]
        else:
            symbols = DEFAULT_SYMBOLS

        print(f"symbols: {symbols}")
        if since:
            print(f"since:   {since.isoformat()}")

        for sym in symbols:
            try:
                aggregate_one(conn, sym, since)
            except Exception as exc:
                conn.rollback()
                print(f"  ! {sym} failed: {exc}")

        print("\n✅ done")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
