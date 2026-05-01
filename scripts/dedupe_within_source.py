#!/usr/bin/env python3
"""
Remove within-source duplicate rows in market_data.

Duplicate definition
--------------------
Within-source dup = rows sharing (symbol, timeframe, time, source).
Cross-source dup (same timestamp across 'BC' and 'MT4', for example) is
preserved per user policy — sources are distinct and kept separate.

Keep rule
---------
Keep the row with the LOWEST id (oldest insertion) — stable tiebreaker.
Delete the rest.

Safety
------
Default is --dry-run: prints per (symbol, timeframe, source) dup counts
without deleting. Add --execute to apply.

Scope
-----
Default scans only the 4 live symbols. --all processes the entire table.

Run
---
    python3 scripts/dedupe_within_source.py                 # dry-run, 4 symbols
    python3 scripts/dedupe_within_source.py --execute       # apply
    python3 scripts/dedupe_within_source.py --all --execute # apply table-wide
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

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

# SQL fragments.
# NOTE: market_data unique constraint already enforces (time, source, timeframe, symbol),
# which means "within-source dup" *should* be impossible. In practice dupes may exist
# from before the constraint was added or from partial reindex states. We still scan.
SCAN_SQL = """
    WITH grouped AS (
        SELECT symbol, timeframe, source, time, COUNT(*) AS c, MIN(id) AS keep_id
        FROM market_data
        WHERE ({where_clause})
        GROUP BY symbol, timeframe, source, time
        HAVING COUNT(*) > 1
    )
    SELECT symbol, timeframe, source,
           COUNT(*)                     AS dup_buckets,
           COALESCE(SUM(c - 1), 0)      AS extra_rows
    FROM grouped
    GROUP BY symbol, timeframe, source
    ORDER BY symbol, timeframe, source;
"""

DELETE_SQL = """
    WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY symbol, timeframe, source, time
                   ORDER BY id
               ) AS rn
        FROM market_data
        WHERE ({where_clause})
    )
    DELETE FROM market_data
    WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
"""


def build_where(symbols: List[str] | None) -> tuple[str, List]:
    if not symbols:
        return "TRUE", []
    placeholders = ", ".join(["%s"] * len(symbols))
    return f"symbol IN ({placeholders})", list(symbols)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="Apply deletes (default is dry-run)")
    ap.add_argument("--all", action="store_true", help="Process all symbols, not just the 4 live ones")
    args = ap.parse_args()

    symbols = None if args.all else DEFAULT_SYMBOLS
    where_clause, params = build_where(symbols)

    scope = "ALL SYMBOLS" if args.all else f"symbols={DEFAULT_SYMBOLS}"
    print(f"[*] scope: {scope}")
    print(f"[*] mode:  {'EXECUTE (destructive)' if args.execute else 'DRY-RUN'}")

    conn = psycopg2.connect(**PG)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(SCAN_SQL.format(where_clause=where_clause), params)
            rows = cur.fetchall()

        if not rows:
            print("\nNo within-source duplicates found. ✅")
            return 0

        print(f"\n{'SYMBOL':<12} {'TF':<5} {'SOURCE':<12} {'DUP BUCKETS':>12} {'EXTRA ROWS':>12}")
        print("-" * 60)
        total_extra = 0
        for r in rows:
            print(f"{r['symbol']:<12} {r['timeframe']:<5} {r['source']:<12} "
                  f"{r['dup_buckets']:>12,} {r['extra_rows']:>12,}")
            total_extra += int(r["extra_rows"])
        print("-" * 60)
        print(f"{'TOTAL EXTRA ROWS':<40} {total_extra:>12,}")

        if not args.execute:
            print("\n(dry-run only — pass --execute to delete)")
            return 0

        with conn.cursor() as cur:
            cur.execute(DELETE_SQL.format(where_clause=where_clause), params)
            deleted = cur.rowcount
        conn.commit()
        print(f"\n✅ deleted {deleted:,} duplicate rows")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
