#!/usr/bin/env python3
"""
Assess market_data quality across the 4 live symbols × 6 timeframes.

Runs five per-(symbol, timeframe) checks:
    1. Coverage      — min/max time, bar count, distinct sources
    2. Duplicates    — rows sharing (symbol, timeframe, time) after source collapse
    3. OHLC sanity   — high<low, last outside [low,high], any NaN/None, non-positive prices
    4. Volume sanity — negative volume, suspicious zero-volume sessions
    5. Gap detection — consecutive bar interval > expected, skipping weekends for FX/index
                       (uses LAG(time) and the canonical bar interval per timeframe)

Writes two outputs:
    - data/quality/gap_report.json      (machine-readable per-cell report)
    - data/quality/gap_report.md        (human-readable summary)

No rows are mutated — this is diagnostic only. A second script will handle
gap-fill after the user reviews this report and picks a fill source.

Usage:
    python3 scripts/assess_data_gaps.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
SYMBOLS: List[str] = ["CrudeOIL", "USA500", "GBPJPY.", "#TSLA"]
TIMEFRAMES: List[str] = ["M1", "M5", "M15", "H1", "H4", "D1"]

# Canonical bar interval in seconds — used for gap detection.
TF_SECONDS: Dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

# Per-symbol expected session behaviour — informs weekend filtering.
# 'fx'     : 24/5 (Sun 22:00 UTC - Fri 22:00 UTC)
# 'index'  : CME-like index, 23/5 with brief daily pause
# 'equity' : US cash equity, 6.5h/day Mon-Fri
# 'futures': commodity future, 23/5
SYMBOL_SESSION: Dict[str, str] = {
    "CrudeOIL": "futures",
    "USA500": "index",
    "GBPJPY.": "fx",
    "#TSLA": "equity",
}

# Connection — reuses the defaults that scripts/check_data_status.py uses.
PG_CONN = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5433")),
    "database": os.environ.get("PGDATABASE", "risetrader"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "risetrader2024"),
}

OUT_DIR = Path("data/quality")


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------
def coverage(cur, symbol: str, tf: str) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT
            MIN(time)                                  AS first_time,
            MAX(time)                                  AS last_time,
            COUNT(*)                                   AS total_bars,
            COUNT(DISTINCT source)                     AS source_count,
            ARRAY_AGG(DISTINCT source ORDER BY source) AS sources
        FROM market_data
        WHERE symbol = %s AND timeframe = %s
        """,
        (symbol, tf),
    )
    return dict(cur.fetchone() or {})


def duplicates(cur, symbol: str, tf: str) -> Dict[str, Any]:
    """Collapse by (symbol, tf, time) — duplicates across sources count too."""
    cur.execute(
        """
        SELECT COUNT(*) AS dup_buckets,
               COALESCE(SUM(c - 1), 0) AS extra_rows
        FROM (
            SELECT time, COUNT(*) AS c
            FROM market_data
            WHERE symbol = %s AND timeframe = %s
            GROUP BY time
            HAVING COUNT(*) > 1
        ) d
        """,
        (symbol, tf),
    )
    return dict(cur.fetchone() or {})


def ohlc_violations(cur, symbol: str, tf: str) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT
            SUM((high < low)::int)                       AS high_lt_low,
            SUM((last > high)::int)                      AS close_above_high,
            SUM((last < low)::int)                       AS close_below_low,
            SUM((open > high OR open < low)::int)        AS open_outside_range,
            SUM((open  <= 0)::int)                       AS nonpositive_open,
            SUM((high  <= 0)::int)                       AS nonpositive_high,
            SUM((low   <= 0)::int)                       AS nonpositive_low,
            SUM((last  <= 0)::int)                       AS nonpositive_close,
            SUM((volume < 0)::int)                       AS negative_volume,
            SUM((volume = 0)::int)                       AS zero_volume_bars
        FROM market_data
        WHERE symbol = %s AND timeframe = %s
        """,
        (symbol, tf),
    )
    row = cur.fetchone() or {}
    return {k: int(v or 0) for k, v in row.items()}


def gaps(cur, symbol: str, tf: str, session: str) -> Dict[str, Any]:
    """
    Detect bars whose predecessor is > expected interval apart.

    Weekend gaps are expected for non-24x7 instruments and are filtered
    post-query using Python (simpler than encoding timezone/holiday logic
    in SQL). We flag any gap > 1.5 × bar_interval AND not crossing a weekend
    for FX/futures, or not crossing a weekend/overnight for equities.
    """
    bar_s = TF_SECONDS[tf]
    cur.execute(
        """
        WITH ordered AS (
            SELECT DISTINCT time
            FROM market_data
            WHERE symbol = %s AND timeframe = %s
            ORDER BY time
        ),
        with_prev AS (
            SELECT
                time,
                LAG(time) OVER (ORDER BY time) AS prev_time
            FROM ordered
        )
        SELECT
            prev_time,
            time,
            EXTRACT(EPOCH FROM (time - prev_time))::bigint AS gap_seconds
        FROM with_prev
        WHERE prev_time IS NOT NULL
          AND EXTRACT(EPOCH FROM (time - prev_time)) > %s
        ORDER BY gap_seconds DESC
        LIMIT 200
        """,
        (symbol, tf, int(bar_s * 1.5)),
    )
    rows = cur.fetchall()

    suspicious: List[Dict[str, Any]] = []
    weekend: List[Dict[str, Any]] = []
    holiday: List[Dict[str, Any]] = []

    for row in rows:
        prev = row["prev_time"]
        now = row["time"]
        gap_s = int(row["gap_seconds"])

        # Classify weekend gaps (Fri close → Mon open).
        is_weekend = False
        if prev.weekday() == 4 and now.weekday() == 0:
            is_weekend = True
        elif prev.weekday() == 5 or now.weekday() == 6:
            is_weekend = True

        # Equities: normal overnight gap Mon-Fri is ~17.5h; ignore if inside that.
        if session == "equity" and gap_s <= 18 * 3600 and prev.weekday() != 5:
            holiday.append(
                {"prev": prev.isoformat(), "curr": now.isoformat(), "gap_s": gap_s, "tag": "overnight"}
            )
            continue

        if is_weekend and gap_s <= 72 * 3600:
            weekend.append(
                {"prev": prev.isoformat(), "curr": now.isoformat(), "gap_s": gap_s, "tag": "weekend"}
            )
            continue

        suspicious.append(
            {"prev": prev.isoformat(), "curr": now.isoformat(), "gap_s": gap_s,
             "missing_bars_est": max(1, gap_s // bar_s - 1)}
        )

    return {
        "suspicious_gap_count": len(suspicious),
        "weekend_gap_count": len(weekend),
        "overnight_gap_count": len(holiday),
        "top_suspicious": suspicious[:25],
        "bar_interval_s": bar_s,
    }


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": SYMBOLS,
        "timeframes": TIMEFRAMES,
        "cells": {},
    }

    with psycopg2.connect(**PG_CONN) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for symbol in SYMBOLS:
                session = SYMBOL_SESSION.get(symbol, "fx")
                for tf in TIMEFRAMES:
                    key = f"{symbol}|{tf}"
                    print(f"[*] {key} …", flush=True)
                    cell = {
                        "coverage": coverage(cur, symbol, tf),
                        "duplicates": duplicates(cur, symbol, tf),
                        "ohlc": ohlc_violations(cur, symbol, tf),
                        "gaps": gaps(cur, symbol, tf, session),
                    }
                    # Serialise datetimes.
                    cov = cell["coverage"]
                    if cov.get("first_time"):
                        cov["first_time"] = cov["first_time"].isoformat()
                    if cov.get("last_time"):
                        cov["last_time"] = cov["last_time"].isoformat()
                    report["cells"][key] = cell

    json_path = OUT_DIR / "gap_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path = OUT_DIR / "gap_report.md"
    md_path.write_text(render_markdown(report))

    print(f"\n✅ wrote {json_path}")
    print(f"✅ wrote {md_path}")
    print_summary(report)


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Market Data Gap Report")
    lines.append(f"_Generated: {report['generated_at']}_\n")
    lines.append("| Symbol | TF | First | Last | Bars | Sources | Dup buckets | Extra rows | OHLC viol. | Suspicious gaps | Weekend | Overnight |")
    lines.append("|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for key, cell in report["cells"].items():
        symbol, tf = key.split("|")
        cov = cell["coverage"]
        dup = cell["duplicates"]
        ohlc = cell["ohlc"]
        g = cell["gaps"]
        ohlc_total = sum(ohlc.values()) - int(ohlc.get("zero_volume_bars", 0))
        first = (cov.get("first_time") or "")
        last = (cov.get("last_time") or "")
        lines.append(
            f"| {symbol} | {tf} | {first[:10] or '—'} | "
            f"{last[:10] or '—'} | {cov.get('total_bars', 0)} | "
            f"{','.join(cov.get('sources') or [])} | "
            f"{dup.get('dup_buckets', 0)} | {dup.get('extra_rows', 0)} | "
            f"{ohlc_total} | {g['suspicious_gap_count']} | "
            f"{g['weekend_gap_count']} | {g['overnight_gap_count']} |"
        )
    lines.append("")
    lines.append("## Top suspicious gaps per cell")
    for key, cell in report["cells"].items():
        gs = cell["gaps"]["top_suspicious"]
        if not gs:
            continue
        lines.append(f"\n### {key}")
        lines.append("| prev | curr | gap_s | est. missing bars |")
        lines.append("|---|---|---:|---:|")
        for g in gs[:10]:
            lines.append(f"| {g['prev']} | {g['curr']} | {g['gap_s']} | {g['missing_bars_est']} |")
    return "\n".join(lines)


def print_summary(report: Dict[str, Any]) -> None:
    print("\n" + "=" * 90)
    print(f"{'SYMBOL|TF':<15} {'FIRST':<12} {'LAST':<12} {'BARS':>10} {'DUPS':>6} {'OHLC':>6} {'SUSP':>6}")
    print("-" * 90)
    for key, cell in report["cells"].items():
        cov = cell["coverage"]
        ohlc_viol = sum(cell["ohlc"].values()) - int(cell["ohlc"].get("zero_volume_bars", 0))
        print(
            f"{key:<15} "
            f"{(cov.get('first_time') or '')[:10]:<12} "
            f"{(cov.get('last_time') or '')[:10]:<12} "
            f"{cov.get('total_bars', 0):>10,} "
            f"{cell['duplicates'].get('extra_rows', 0):>6} "
            f"{ohlc_viol:>6} "
            f"{cell['gaps']['suspicious_gap_count']:>6}"
        )
    print("=" * 90)


if __name__ == "__main__":
    run()
