#!/usr/bin/env python3
"""
Comprehensive coverage + gap analysis for every (symbol, timeframe) in market_data.

For each (symbol, timeframe) combination present in the DB, this script reports:
  - first_ts, last_ts, total_bars
  - sources active and their per-source first/last/count
  - days since last bar (staleness)
  - gap inventory classified into:
      • weekend (Fri close → Sun/Mon open)
      • holiday_likely (US futures / equities calendar match)
      • daily_break (NYMEX 1h settlement break, 50-80 min)
      • suspicious_short (1-24h gap on a weekday, NOT a known break)
      • suspicious_multi_day (>24h, weekday, not a known holiday)

Outputs:
  data/quality/symbol_coverage.json   — full structured per-symbol report
  data/quality/symbol_coverage.csv    — flat table for Excel/dashboard import
  data/quality/symbol_gaps_top.csv    — top suspicious gaps across all symbols

Run:
  python3 scripts/analyze_symbol_coverage.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("error: pip install psycopg2-binary")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
OUT_DIR = ROOT / "data" / "quality"


def _load_env():
    if not ENV.exists():
        return
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()

PG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5433")),
    "dbname": os.environ.get("PGDATABASE", "risetrader"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("POSTGRES_PASSWORD",
                               os.environ.get("PGPASSWORD", "risetrader2024")),
}

# ─── US Futures / Equities holiday calendar (CME + NYSE) ─────────────────
# Comprehensive enough for any dataset 2009-2026.
# Each entry is (date, type) where type is 'full_close' or 'early_close'.
# Full closures = NO trading. Early closes = data may end midday.
US_FUTURES_HOLIDAYS = set()

def _add_holidays_for_year(yr: int) -> None:
    # Fixed: New Year's Day (or observed)
    US_FUTURES_HOLIDAYS.add(date(yr, 1, 1))
    if date(yr, 1, 1).weekday() == 5:  # Sat → observed Fri Dec 31
        US_FUTURES_HOLIDAYS.add(date(yr - 1, 12, 31))
    if date(yr, 1, 1).weekday() == 6:  # Sun → observed Mon Jan 2
        US_FUTURES_HOLIDAYS.add(date(yr, 1, 2))
    # MLK day (3rd Monday January)
    d = date(yr, 1, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    US_FUTURES_HOLIDAYS.add(d + timedelta(days=14))
    # Presidents Day (3rd Monday February)
    d = date(yr, 2, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    US_FUTURES_HOLIDAYS.add(d + timedelta(days=14))
    # Good Friday — varies, hardcode for 2009-2030
    GF = {
        2009: date(2009, 4, 10), 2010: date(2010, 4, 2),
        2011: date(2011, 4, 22), 2012: date(2012, 4, 6),
        2013: date(2013, 3, 29), 2014: date(2014, 4, 18),
        2015: date(2015, 4, 3),  2016: date(2016, 3, 25),
        2017: date(2017, 4, 14), 2018: date(2018, 3, 30),
        2019: date(2019, 4, 19), 2020: date(2020, 4, 10),
        2021: date(2021, 4, 2),  2022: date(2022, 4, 15),
        2023: date(2023, 4, 7),  2024: date(2024, 3, 29),
        2025: date(2025, 4, 18), 2026: date(2026, 4, 3),
        2027: date(2027, 3, 26), 2028: date(2028, 4, 14),
        2029: date(2029, 3, 30), 2030: date(2030, 4, 19),
    }
    if yr in GF:
        US_FUTURES_HOLIDAYS.add(GF[yr])
    # Memorial Day (last Monday May)
    d = date(yr, 5, 31)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    US_FUTURES_HOLIDAYS.add(d)
    # Juneteenth (since 2022)
    if yr >= 2022:
        d = date(yr, 6, 19)
        if d.weekday() == 5:
            d -= timedelta(days=1)
        elif d.weekday() == 6:
            d += timedelta(days=1)
        US_FUTURES_HOLIDAYS.add(d)
    # July 4 (or observed)
    d = date(yr, 7, 4)
    if d.weekday() == 5:
        d -= timedelta(days=1)
    elif d.weekday() == 6:
        d += timedelta(days=1)
    US_FUTURES_HOLIDAYS.add(d)
    # Labor Day (1st Monday September)
    d = date(yr, 9, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    US_FUTURES_HOLIDAYS.add(d)
    # Thanksgiving (4th Thursday November) + Black Friday (early close)
    d = date(yr, 11, 1)
    while d.weekday() != 3:
        d += timedelta(days=1)
    thanks = d + timedelta(days=21)
    US_FUTURES_HOLIDAYS.add(thanks)
    # Black Friday early close — count as full holiday since intraday is partial
    US_FUTURES_HOLIDAYS.add(thanks + timedelta(days=1))
    # Christmas Eve, Christmas, Day after Christmas (CME varies)
    US_FUTURES_HOLIDAYS.add(date(yr, 12, 24))
    US_FUTURES_HOLIDAYS.add(date(yr, 12, 25))
    US_FUTURES_HOLIDAYS.add(date(yr, 12, 26))

for _y in range(2008, 2031):
    _add_holidays_for_year(_y)

# ─── Gap classification ───────────────────────────────────────────────────
def classify_gap(prev_ts: datetime, curr_ts: datetime, gap_s: float) -> str:
    """Return one of: weekend / holiday_likely / daily_break / suspicious_short
    / suspicious_multi_day."""
    gap_h = gap_s / 3600
    if gap_s < 50 * 60:
        return "intra_session"
    # NYMEX 1-hour daily settlement break
    if 50 * 60 <= gap_s <= 80 * 60 and prev_ts.hour in (20, 21, 22):
        return "daily_break"
    # Weekend: Fri ≥ 20:00 UTC → Sun ≥ 21:00 UTC, lasts ~40-55 hours
    if prev_ts.weekday() == 4 and prev_ts.hour >= 19 and gap_h <= 60:
        return "weekend"
    if prev_ts.weekday() == 4 and gap_h > 50:
        return "weekend"
    # Holiday: check if EVERY date in gap window is weekend or holiday
    if gap_h >= 12:
        d = prev_ts.date()
        end = curr_ts.date()
        all_off = True
        cur = d
        # Check the day AFTER prev (gap interior)
        cur += timedelta(days=1)
        while cur <= end:
            if cur.weekday() < 5 and cur not in US_FUTURES_HOLIDAYS:
                all_off = False
                break
            cur += timedelta(days=1)
        if all_off and gap_h <= 100:
            return "holiday_likely"
    if gap_h <= 24:
        return "suspicious_short"
    return "suspicious_multi_day"


def main() -> int:
    print(f"connecting to {PG['host']}:{PG['port']}/{PG['dbname']} ...")
    conn = psycopg2.connect(**PG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    print("connected.\n")

    # 1. List every (symbol, timeframe) pair with bars
    print("[1/4] enumerating (symbol, timeframe) pairs with data ...")
    cur.execute(
        """
        SELECT symbol, timeframe::text AS tf, COUNT(*) AS bars,
               MIN(time)::text AS first_ts, MAX(time)::text AS last_ts
        FROM market_data GROUP BY 1, 2
        ORDER BY symbol, tf
        """
    )
    pairs = [dict(r) for r in cur.fetchall()]
    print(f"  → {len(pairs)} (symbol, timeframe) pairs\n")

    # 2. For each pair, get per-source breakdown + gap profile
    print("[2/4] per-pair per-source breakdown + gap analysis ...")
    report = []
    flat_rows = []  # for csv
    top_gaps_global = []
    for p in pairs:
        sym, tf = p["symbol"], p["tf"]
        # per-source
        cur.execute(
            """
            SELECT source::text AS source, COUNT(*) AS bars,
                   MIN(time)::text AS first_ts, MAX(time)::text AS last_ts
            FROM market_data WHERE symbol = %s AND timeframe::text = %s
            GROUP BY source ORDER BY source
            """,
            (sym, tf),
        )
        sources = [dict(r) for r in cur.fetchall()]
        # gaps via LAG window
        cur.execute(
            """
            WITH ordered AS (
              SELECT time, LAG(time) OVER (ORDER BY time) AS prev_time
              FROM (
                SELECT DISTINCT time FROM market_data
                WHERE symbol=%s AND timeframe::text=%s
              ) t
            )
            SELECT prev_time::text AS prev, time::text AS curr,
                   EXTRACT(EPOCH FROM (time - prev_time)) AS gap_s
            FROM ordered
            WHERE prev_time IS NOT NULL
              AND EXTRACT(EPOCH FROM (time - prev_time)) > 50*60
            """,
            (sym, tf),
        )
        all_gaps = cur.fetchall()
        cls_count = defaultdict(int)
        cls_total_h = defaultdict(float)
        susp_gaps = []
        for g in all_gaps:
            prev_dt = datetime.fromisoformat(g["prev"])
            curr_dt = datetime.fromisoformat(g["curr"])
            cls = classify_gap(prev_dt, curr_dt, float(g["gap_s"]))
            cls_count[cls] += 1
            cls_total_h[cls] += float(g["gap_s"]) / 3600
            if cls in ("suspicious_short", "suspicious_multi_day"):
                susp_gaps.append({
                    "prev": g["prev"],
                    "curr": g["curr"],
                    "hours": round(float(g["gap_s"]) / 3600, 2),
                    "class": cls,
                })
        susp_gaps.sort(key=lambda x: x["hours"], reverse=True)

        days_stale = (
            datetime.now(timezone.utc).date()
            - datetime.fromisoformat(p["last_ts"]).date()
        ).days

        entry = {
            "symbol": sym,
            "timeframe": tf,
            "first_ts": p["first_ts"],
            "last_ts": p["last_ts"],
            "total_bars": p["bars"],
            "days_stale": days_stale,
            "sources": sources,
            "gap_classes": dict(cls_count),
            "gap_classes_hours": {k: round(v, 1) for k, v in cls_total_h.items()},
            "top_suspicious_gaps": susp_gaps[:10],
        }
        report.append(entry)

        # Annotate global top suspicious
        for sg in susp_gaps[:5]:
            top_gaps_global.append({
                "symbol": sym, "timeframe": tf, **sg,
            })

        # Flat row for CSV
        susp_count = cls_count.get("suspicious_short", 0) + cls_count.get("suspicious_multi_day", 0)
        flat_rows.append({
            "symbol": sym,
            "timeframe": tf,
            "first_ts": p["first_ts"],
            "last_ts": p["last_ts"],
            "total_bars": p["bars"],
            "days_stale": days_stale,
            "sources": ",".join(s["source"] for s in sources),
            "weekend_gaps":          cls_count.get("weekend", 0),
            "holiday_gaps":          cls_count.get("holiday_likely", 0),
            "daily_break_gaps":      cls_count.get("daily_break", 0),
            "suspicious_short":      cls_count.get("suspicious_short", 0),
            "suspicious_multi_day":  cls_count.get("suspicious_multi_day", 0),
            "total_suspicious":      susp_count,
        })

    # 3. Print summary table
    print("\n[3/4] coverage summary (sorted by symbol, then timeframe):\n")
    print(f"{'symbol':<14} {'tf':<4} {'first':<11} {'last':<11} {'bars':>10} "
          f"{'stale':>5} {'wknd':>5} {'hol':>5} {'sb':>5} {'susp_S':>6} {'susp_M':>6}")
    print("-" * 100)
    for r in flat_rows:
        sym = r["symbol"][:14]
        tf = r["timeframe"]
        f = r["first_ts"][:10]
        l = r["last_ts"][:10]
        bars = r["total_bars"]
        stale = r["days_stale"]
        marker = "⚠" if stale > 7 else " "
        print(f"{sym:<14} {tf:<4} {f} {l} {bars:>10,} {stale:>4}{marker} "
              f"{r['weekend_gaps']:>5} {r['holiday_gaps']:>5} {r['daily_break_gaps']:>5} "
              f"{r['suspicious_short']:>6} {r['suspicious_multi_day']:>6}")

    # 4. Write outputs
    print("\n[4/4] writing outputs ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "symbol_coverage.json"
    out_csv = OUT_DIR / "symbol_coverage.csv"
    out_top = OUT_DIR / "symbol_gaps_top.csv"

    out_json.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_pairs": len(report),
        "pairs": report,
    }, indent=2, default=str))
    print(f"  wrote: {out_json}")

    if flat_rows:
        with open(out_csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(flat_rows[0].keys()))
            w.writeheader()
            for r in flat_rows:
                w.writerow(r)
        print(f"  wrote: {out_csv}")

    top_gaps_global.sort(key=lambda x: x["hours"], reverse=True)
    if top_gaps_global:
        with open(out_top, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(top_gaps_global[0].keys()))
            w.writeheader()
            for r in top_gaps_global[:200]:
                w.writerow(r)
        print(f"  wrote: {out_top}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
