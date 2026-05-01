#!/usr/bin/env python3
"""
Master backfill orchestrator — pick the highest-accuracy source per symbol
from the existing scrapers and run them in priority order.

DOES NOT modify the database schema. Uses existing source-tagging in
market_data (`source` ENUM: BC, MT4, DUKASCOPY, CSV).

Per-symbol source selection (highest accuracy first):

| MT4 symbol  | Best source            | Why                                   | Scraper                          |
|-------------|------------------------|---------------------------------------|----------------------------------|
| CrudeOIL    | Barchart CL*0          | NYMEX continuous = native exchange    | scrape_barchart_gaps.py          |
| BRENT_OIL   | Dukascopy BRENTCMDUSD  | already wired, deep + clean           | backfill_historical_data.py      |
| GASOLINE    | Barchart RB*0          | Dukascopy unavailable, BC = native    | scrape_barchart_gaps.py          |
| WHEAT       | Barchart ZW*0          | Dukascopy unavailable, BC = native    | scrape_barchart_gaps.py          |
| CORN        | Barchart ZC*0          | Dukascopy unavailable, BC = native    | scrape_barchart_gaps.py          |
| USA500      | Dukascopy USA500IDXUSD | already wired, ~20yr depth            | backfill_historical_data.py      |
| GBPJPY      | Dukascopy GBPJPY       | spot FX, already wired                | backfill_historical_data.py      |
| XAUUSD      | Dukascopy XAUUSD       | spot gold, already wired              | backfill_historical_data.py      |
| DXY         | Barchart $DXY          | Dukascopy doesn't have it             | scrape_barchart_gaps.py          |
| VIX         | Barchart $VIX          | Dukascopy doesn't have it             | scrape_barchart_gaps.py          |
| TSLA        | yfinance D1 + BC M1/M5 | yfinance has 20yr D1; BC has M1/M5    | download_yfinance.py + BC        |
| MSFT        | yfinance D1 + BC M1/M5 | same                                  | download_yfinance.py + BC        |
| DOLLAR_INDX | (skip)                 | Duplicate of DXY                      | —                                |

Usage:
    # Print the planned commands (default — dry-run):
    python3 scripts/backfill_all_symbols.py

    # Print and immediately execute (sequentially, with rate-limit pacing):
    python3 scripts/backfill_all_symbols.py --execute

    # Limit to specific symbols:
    python3 scripts/backfill_all_symbols.py --symbols DXY,VIX --execute

    # Cap Barchart downloads per day (default 200, leaves headroom under 250 limit):
    python3 scripts/backfill_all_symbols.py --execute --max-bc-per-day 200

The orchestrator is RESUME-SAFE: each underlying scraper checks DB max(time)
per (symbol,tf) and only downloads windows newer than that, so re-running
this script after a partial run picks up where it left off. It also stays
under the Barchart 250 files/day rate limit.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# ──────────────────────────────────────────────────────────────────────
# Per-symbol backfill plan
# ──────────────────────────────────────────────────────────────────────
# Each entry describes one logical backfill task. The orchestrator
# expands these into actual scraper invocations.
#
# Fields:
#   sources    : list of (source, target_tfs, earliest_known_date) tuples.
#                Multiple sources allowed; the orchestrator runs them in
#                listed order so the most-accurate source lands first
#                and weaker sources only fill what's missing thanks to
#                ON CONFLICT DO NOTHING in import scripts.
#   skip       : if True, this symbol is intentionally skipped.
#                Reason: kept in `notes`.
PLAN: List[Dict] = [
    {
        "symbol": "CrudeOIL",
        "sources": [
            ("BC",        ["M1"],          "2009-08-04"),  # CL*0 continuous
            # Higher TFs are aggregated from M1 by aggregate_m1_to_m5.py
        ],
        "notes": "NYMEX CL*0 — already mostly done this session, just refresh latest.",
    },
    {
        "symbol": "BRENT_OIL",
        "sources": [
            ("DUKASCOPY", ["M1"],          "2019-01-02"),
            ("BC",        ["M1"],          None),          # gap-fill if Dukascopy has holes
        ],
        "notes": "Dukascopy primary; BC BZ*0 fills any gaps.",
    },
    {
        "symbol": "GASOLINE",
        "sources": [
            ("BC",        ["M1"],          "2015-01-01"),  # RB*0 continuous
        ],
        "notes": "Dukascopy unavailable for RBOB; BC RB*0 is the right source.",
    },
    {
        "symbol": "WHEAT",
        "sources": [
            ("BC",        ["M1"],          "2015-01-01"),
        ],
        "notes": "Dukascopy unavailable; BC ZW*0 native CBOT.",
    },
    {
        "symbol": "CORN",
        "sources": [
            ("BC",        ["M1"],          "2015-01-01"),
        ],
        "notes": "Dukascopy unavailable; BC ZC*0 native CBOT.",
    },
    {
        "symbol": "USA500",
        "sources": [
            ("DUKASCOPY", ["M1"],          "2003-01-01"),  # very deep
            ("BC",        ["M1"],          None),          # gap-fill via $SPX cash
        ],
        "notes": "Dukascopy index data goes deep; BC $SPX as backup.",
    },
    {
        "symbol": "GBPJPY",
        "sources": [
            ("DUKASCOPY", ["M1"],          "2003-01-01"),
        ],
        "notes": "Spot FX — Dukascopy is canonical, BC FX is provider-dependent.",
    },
    {
        "symbol": "XAUUSD",
        "sources": [
            ("DUKASCOPY", ["M1"],          "2026-02-27"),  # restart from staleness date
        ],
        "notes": "Dukascopy XAUUSD is spot gold — matches the existing DB rows.",
    },
    {
        "symbol": "DXY",
        "sources": [
            ("BC",        ["M1"],          "2025-04-01"),  # restart from staleness date
        ],
        "notes": "BC $DXY — restart since Apr 2025 dead feed.",
    },
    {
        "symbol": "VIX",
        "sources": [
            ("BC",        ["M1"],          "2025-04-01"),
        ],
        "notes": "BC $VIX — restart since Apr 2025 dead feed.",
    },
    {
        "symbol": "TSLA",
        "sources": [
            ("YFINANCE",  ["D1"],          "2010-06-29"),  # IPO
            ("BC",        ["M1"],          None),          # ~6-12mo cap on stock M1
        ],
        "notes": "yfinance D1 deep history + BC M1 for last year of intraday.",
    },
    {
        "symbol": "MSFT",
        "sources": [
            ("YFINANCE",  ["D1"],          "1986-03-13"),  # already deep, just refresh
            ("BC",        ["M1"],          None),
        ],
        "notes": "yfinance for D1 (since 1986); BC M1 for recent intraday.",
    },
    # DOLLAR_INDX intentionally skipped — duplicate of DXY.
]


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def chunk_dates(start: date, end: date, days: int) -> List[Tuple[date, date]]:
    """Walk [start, end] forward in `days`-day windows, returning (s, e) tuples."""
    out = []
    cur = start
    while cur <= end:
        nxt = min(end, cur + timedelta(days=days - 1))
        out.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return out


def build_commands(plan: List[Dict], end_date: date,
                   max_bc_per_day: int) -> List[Tuple[str, List[str], str]]:
    """Return a list of (label, argv, notes) commands ordered by priority.
    Barchart commands are split into 20-day windows (Barchart's intraday cap)
    and the orchestrator paces them across days to stay under the rate limit.
    """
    cmds: List[Tuple[str, List[str], str]] = []
    for entry in plan:
        sym = entry["symbol"]
        for source, tfs, earliest in entry["sources"]:
            for tf in tfs:
                if source == "BC":
                    if not earliest:
                        # earliest=None means "fill missing only"; skip in
                        # this orchestrator pass, the daily-refresh cron
                        # handles that.
                        continue
                    start_d = date.fromisoformat(earliest)
                    interval_min = {"M1": 1, "M5": 5, "M15": 15}.get(tf, 1)
                    for s, e in chunk_dates(start_d, end_date, days=20):
                        cmds.append((
                            f"BC scrape {sym} {tf} {s} → {e}",
                            ["python3", str(SCRIPTS / "scrape_barchart_gaps.py"),
                             "--symbol", sym, "--interval", str(interval_min),
                             "--start", s.isoformat(), "--end", e.isoformat()],
                            f"Profile=futures/stock/forex per SYMBOL_CONFIG. {entry['notes']}",
                        ))
                elif source == "DUKASCOPY":
                    if not earliest:
                        continue
                    cmds.append((
                        f"Dukascopy {sym} {tf} {earliest} → {end_date}",
                        ["python3", str(SCRIPTS / "backfill_historical_data.py"),
                         "--symbols", sym,
                         "--start", earliest,
                         "--end", end_date.isoformat()],
                        entry["notes"],
                    ))
                elif source == "YFINANCE":
                    cmds.append((
                        f"yfinance {sym} {tf}",
                        ["python3", str(SCRIPTS / "download_yfinance.py"),
                         "--symbol", sym],
                        entry["notes"],
                    ))
                else:
                    raise ValueError(f"unknown source: {source}")
    return cmds


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--symbols",
                   help="Comma-separated subset (default: all in PLAN). "
                        "Example: --symbols DXY,VIX,GASOLINE")
    p.add_argument("--execute", action="store_true",
                   help="Actually run the commands. Default is dry-run (print only).")
    p.add_argument("--end", default=today_utc().isoformat(),
                   help=f"End date for backfill (default: today UTC = {today_utc()})")
    p.add_argument("--max-bc-per-day", type=int, default=200,
                   help="Cap on Barchart commands run per 24h (default 200, "
                        "below the 250 rate limit). Pacing kicks in when "
                        "more than this many BC commands queued.")
    p.add_argument("--no-import", action="store_true",
                   help="Run scrapers but skip the post-scrape import step.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    end_date = date.fromisoformat(args.end)

    plan = PLAN
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",")}
        plan = [e for e in plan if e["symbol"].upper() in wanted]
        if not plan:
            print(f"!! no PLAN entries match --symbols={args.symbols}")
            return 1

    cmds = build_commands(plan, end_date, args.max_bc_per_day)

    print(f"\n=== BACKFILL PLAN ({len(cmds)} commands) ===\n")
    bc_count = sum(1 for c in cmds if "scrape_barchart_gaps.py" in c[1][1])
    print(f"  Barchart commands:  {bc_count}  (will pace at {args.max_bc_per_day}/day)")
    print(f"  Dukascopy commands: {sum(1 for c in cmds if 'backfill_historical_data' in c[1][1])}")
    print(f"  yfinance commands:  {sum(1 for c in cmds if 'download_yfinance' in c[1][1])}")
    print(f"  End date:           {end_date}")
    print()
    for i, (label, argv, notes) in enumerate(cmds, start=1):
        print(f"  [{i:>3}/{len(cmds)}]  {label}")
        print(f"           cmd: {shlex.join(argv)}")
    print()

    if not args.execute:
        print("Dry-run mode (default). Re-run with --execute to actually run these commands.")
        print("Each Barchart command is a single 20-day window; orchestrator paces them.")
        return 0

    # ─── execute ───────────────────────────────────────────────
    bc_run_today = 0
    day_started = datetime.now(timezone.utc)
    print(f"=== EXECUTING ({len(cmds)} commands) ===\n")
    for i, (label, argv, notes) in enumerate(cmds, start=1):
        is_bc = "scrape_barchart_gaps.py" in argv[1]
        if is_bc:
            # Pacing: if we've used the daily allowance, sleep until next 24h window.
            if bc_run_today >= args.max_bc_per_day:
                wait_to = day_started + timedelta(hours=24)
                wait_s = max(0, (wait_to - datetime.now(timezone.utc)).total_seconds())
                if wait_s > 0:
                    print(f"\n  ⏸  hit BC daily cap ({args.max_bc_per_day}); sleeping "
                          f"{wait_s/3600:.1f}h until {wait_to:%Y-%m-%d %H:%M UTC}")
                    time.sleep(wait_s)
                bc_run_today = 0
                day_started = datetime.now(timezone.utc)

        print(f"\n  [{i:>3}/{len(cmds)}]  {label}")
        rc = subprocess.call(argv, cwd=str(ROOT))
        if rc != 0:
            print(f"  !!  command exited with rc={rc}; continuing")
        if is_bc:
            bc_run_today += 1

    # Post-run import for any landed BC CSVs
    if not args.no_import:
        print("\n=== importing any landed BC CSVs ===\n")
        subprocess.call(
            ["python3", str(SCRIPTS / "import_barchart_csvs.py")],
            cwd=str(ROOT),
        )

    print("\n=== DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
