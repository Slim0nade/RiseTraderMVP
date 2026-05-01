#!/usr/bin/env python3
"""
Import Barchart-formatted CSVs into market_data.

Design
------
Barchart's on-demand/export CSV has a handful of shapes depending on the
product (historical download, intraday export, Excel add-in). This importer
auto-detects the common ones so the user doesn't have to hand-edit files:

    Shape A (most common intraday):
        Time, Open, High, Low, Last, Volume
    Shape B (with change columns):
        Time, Open, High, Low, Last, Change, % Chg, Volume
    Shape C (daily):
        Date, Open, High, Low, Close, Volume
    Shape D (generic OHLC):
        timestamp, open, high, low, close, volume

Time column is parsed with pandas; naive stamps are assumed exchange-local
and converted to UTC based on the symbol's market (CrudeOIL → America/Chicago,
TSLA → America/New_York). Override with --assume-utc if your export is
already UTC.

File naming convention
----------------------
Drop files at::

    data/downloads/barchart/{SYMBOL}_{TF}_{optional_range}.csv

Examples::

    data/downloads/barchart/CrudeOIL_M1_2025.csv
    data/downloads/barchart/CrudeOIL_M1_2026_jan_apr.csv
    data/downloads/barchart/TSLA_M1_full.csv
    data/downloads/barchart/TSLA_D1.csv

Symbol and TF are parsed from the filename prefix before the first underscore
(or the first two underscores if TF is present). SYMBOL must match what's
already in market_data ("CrudeOIL", "TSLA", "USA500", "GBPJPY" — NO trailing
dot, NO '#' prefix, per the DB normalisation).

Insertion semantics
-------------------
    source = 'BC'
    ON CONFLICT (time, source, timeframe, symbol) DO NOTHING

That means:
    - Re-running is safe.
    - Existing BC rows are NOT overwritten (user's live MT4 rows in a
      different source are fully untouched either way).
    - Bars that exist under source='MT4' at the same timestamp remain
      separate rows (different source composite key).

Run
---
    # Import everything in data/downloads/barchart/ with inferred timezones
    python3 scripts/import_barchart_csvs.py

    # Import a single file
    python3 scripts/import_barchart_csvs.py --file data/downloads/barchart/CrudeOIL_M1_2025.csv

    # Treat timestamps as UTC (Barchart sometimes exports UTC)
    python3 scripts/import_barchart_csvs.py --assume-utc

    # Dry-run: parse everything, show row counts, don't insert
    python3 scripts/import_barchart_csvs.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
PG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5433")),
    "dbname": os.environ.get("PGDATABASE", "risetrader"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "risetrader2024"),
}

BC_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads" / "barchart"

# Default timezones for naive timestamps — overridden by --assume-utc.
SYMBOL_TZ: Dict[str, str] = {
    # ─── NYMEX / CME / ICE futures (all CT) ──────────────────────────
    "CrudeOIL":  "America/Chicago",   # CL — NYMEX
    "BRENT_OIL": "America/Chicago",   # BZ — ICE (BC quotes in CT)
    "GASOLINE":  "America/Chicago",   # RB — NYMEX
    "WHEAT":     "America/Chicago",   # ZW — CBOT
    "CORN":      "America/Chicago",   # ZC — CBOT
    # ─── Cash indices on Barchart's futures pages (CT) ───────────────
    "DXY":       "America/Chicago",   # ICE-quoted, BC serves CT
    "VIX":       "America/Chicago",   # CBOE-quoted, BC serves CT
    # ─── Cash equity indices and stocks (ET) ─────────────────────────
    "USA500":    "America/New_York",  # $SPX cash
    "TSLA":      "America/New_York",  # NASDAQ
    "MSFT":      "America/New_York",  # NASDAQ
    # ─── Forex ───────────────────────────────────────────────────────
    "GBPJPY":    "UTC",
}

IMPORT_SYMBOL_MAP: Dict[str, str] = {
    "CrudeOIL":  "CrudeOIL_BC",
    "BRENT_OIL": "BRENT_OIL_BC",
    "GASOLINE":  "GASOLINE_BC",
    "WHEAT":     "WHEAT_BC",
    "CORN":      "CORN_BC",
    "DXY":       "DXY_BC",
    "VIX":       "VIX_BC",
    "USA500":    "USA500_BC",
    "TSLA":      "TSLA_BC",
    "MSFT":      "MSFT_BC",
    "GBPJPY":    "GBPJPY_BC",
}

VALID_TFS = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}

# Symbols valid for filename inference (must match SYMBOL_TZ + IMPORT_SYMBOL_MAP).
VALID_SYMBOLS = set(SYMBOL_TZ.keys())


# ----------------------------------------------------------------------
# CSV parsing
# ----------------------------------------------------------------------
def infer_symbol_and_tf(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Parse SYMBOL_TF_rest.csv -> ('SYMBOL', 'TF') or (None, None)."""
    stem = path.stem
    parts = stem.split("_")
    if len(parts) < 2:
        return None, None
    symbol = parts[0]
    tf = parts[1].upper()
    if tf not in VALID_TFS:
        # Maybe the filename is SYMBOL_rest with no TF; default to D1 only if daily words present.
        return None, None
    if symbol not in IMPORT_SYMBOL_MAP:
        return None, None
    return symbol, tf


def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower_map = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    return None


def normalise_frame(df: pd.DataFrame, symbol: str, assume_utc: bool) -> pd.DataFrame:
    """Coerce a Barchart-ish frame into (time, open, high, low, last, volume) in UTC."""
    time_col = _find_column(df, ["time", "date", "datetime", "timestamp"])
    open_col = _find_column(df, ["open"])
    high_col = _find_column(df, ["high"])
    low_col = _find_column(df, ["low"])
    # Barchart's current historical-download CSV exports the close as `Latest`;
    # older exports used `Close` or `Last`. Accept all three.
    close_col = _find_column(df, ["last", "close", "latest"])
    volume_col = _find_column(df, ["volume", "vol"])

    missing = [n for n, c in [
        ("time", time_col), ("open", open_col), ("high", high_col),
        ("low", low_col), ("close/last", close_col)
    ] if c is None]
    if missing:
        raise ValueError(f"missing required columns: {missing}; got {list(df.columns)}")

    out = pd.DataFrame({
        "time": pd.to_datetime(df[time_col], errors="coerce"),
        "open": pd.to_numeric(df[open_col], errors="coerce"),
        "high": pd.to_numeric(df[high_col], errors="coerce"),
        "low":  pd.to_numeric(df[low_col], errors="coerce"),
        "last": pd.to_numeric(df[close_col], errors="coerce"),
    })
    out["volume"] = (
        pd.to_numeric(df[volume_col], errors="coerce").fillna(0).astype(int)
        if volume_col else 0
    )

    # Drop junk rows (NaN price/time).
    out = out.dropna(subset=["time", "open", "high", "low", "last"])

    # Timezone handling.
    if out["time"].dt.tz is None:
        tz = "UTC" if assume_utc else SYMBOL_TZ.get(symbol, "UTC")
        # Tolerate ambiguous/nonexistent (DST transitions) — shift forward, infer.
        out["time"] = out["time"].dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
        out = out.dropna(subset=["time"])  # drop any NaT from ambiguous handling
    out["time"] = out["time"].dt.tz_convert("UTC")

    # OHLC sanity: drop rows where high < low or close outside range.
    bad = (out["high"] < out["low"]) | (out["last"] > out["high"]) | (out["last"] < out["low"])
    if bad.any():
        print(f"  ! dropping {int(bad.sum())} OHLC-violating rows")
        out = out[~bad]

    # Positive prices only.
    bad_px = (out["open"] <= 0) | (out["high"] <= 0) | (out["low"] <= 0) | (out["last"] <= 0)
    if bad_px.any():
        print(f"  ! dropping {int(bad_px.sum())} non-positive-price rows")
        out = out[~bad_px]

    # Sort + dedupe within this file.
    out = out.sort_values("time").drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)

    out["change"] = out["last"] - out["open"]
    out["change_percent"] = ((out["last"] - out["open"]) / out["open"] * 100).round(4)
    return out


# ----------------------------------------------------------------------
# DB insert
# ----------------------------------------------------------------------
INSERT_SQL = """
    INSERT INTO market_data
        (time, symbol, import_symbol, timeframe, source,
         open, high, low, last, change, change_percent, volume,
         created_at, updated_at)
    VALUES %s
    ON CONFLICT (time, source, timeframe, symbol) DO NOTHING
"""

INSERT_TEMPLATE = """(
    %s, %s, %s, %s::timeframe, %s::datasource,
    %s, %s, %s, %s, %s, %s, %s,
    NOW(), NOW()
)"""


def insert_frame(conn, df: pd.DataFrame, symbol: str, tf: str) -> int:
    if df.empty:
        return 0
    import_symbol = IMPORT_SYMBOL_MAP[symbol]
    rows = [
        (
            r["time"].to_pydatetime(),
            symbol,
            import_symbol,
            tf,
            "BC",
            float(r["open"]),
            float(r["high"]),
            float(r["low"]),
            float(r["last"]),
            float(r["change"]),
            float(r["change_percent"]),
            int(r["volume"]),
        )
        for _, r in df.iterrows()
    ]
    # Manual batching so we can accumulate rowcount across pages.
    # `execute_values(..., page_size=N)` only leaves cur.rowcount equal to the
    # LAST batch's count, not the total — that's why old runs reported wildly
    # wrong "skipped" numbers (always a multiple of 5000). Splitting here
    # ourselves and summing rowcount fixes it.
    BATCH = 5000
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i : i + BATCH]
            execute_values(cur, INSERT_SQL, chunk, template=INSERT_TEMPLATE)
            inserted += cur.rowcount
    conn.commit()
    return inserted


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
def process_file(conn, path: Path, assume_utc: bool, dry_run: bool) -> Dict[str, int]:
    symbol, tf = infer_symbol_and_tf(path)
    if symbol is None or tf is None:
        print(f"  ! skipping {path.name}: can't parse SYMBOL_TF from filename")
        return {"parsed": 0, "inserted": 0}

    print(f"\n[*] {path.name}  ->  symbol={symbol} tf={tf}")
    try:
        raw = pd.read_csv(path)
    except Exception as exc:
        print(f"  ! read error: {exc}")
        return {"parsed": 0, "inserted": 0}

    try:
        df = normalise_frame(raw, symbol=symbol, assume_utc=assume_utc)
    except Exception as exc:
        print(f"  ! parse error: {exc}")
        return {"parsed": 0, "inserted": 0}

    print(
        f"  parsed {len(df):,} rows  "
        f"[{df['time'].min()} -> {df['time'].max()}]"
    )
    if dry_run:
        return {"parsed": len(df), "inserted": 0}

    inserted = insert_frame(conn, df, symbol=symbol, tf=tf)
    skipped = len(df) - inserted
    print(f"  inserted {inserted:,} new rows  (skipped {skipped:,} existing)")
    return {"parsed": len(df), "inserted": inserted}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="Single CSV file instead of scanning the barchart folder")
    ap.add_argument("--assume-utc", action="store_true", help="Treat naive timestamps as UTC (not market-local)")
    ap.add_argument("--dry-run", action="store_true", help="Parse and count only; don't write to DB")
    args = ap.parse_args()

    files: List[Path]
    if args.file:
        files = [Path(args.file)]
    else:
        if not BC_DIR.exists():
            BC_DIR.mkdir(parents=True, exist_ok=True)
            print(f"created {BC_DIR} — drop Barchart CSVs here and re-run.")
            return 0
        files = sorted(BC_DIR.glob("*.csv"))

    if not files:
        print(f"no CSVs found in {BC_DIR}. Expected filenames like: CrudeOIL_M1_2025.csv")
        return 0

    conn = psycopg2.connect(**PG)
    try:
        total_parsed = 0
        total_inserted = 0
        for f in files:
            out = process_file(conn, f, assume_utc=args.assume_utc, dry_run=args.dry_run)
            total_parsed += out["parsed"]
            total_inserted += out["inserted"]
        print("\n" + "=" * 60)
        print(f"parsed:    {total_parsed:,}")
        print(f"inserted:  {total_inserted:,}")
        print(f"skipped:   {total_parsed - total_inserted:,}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
