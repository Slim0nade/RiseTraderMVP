#!/usr/bin/env python3
"""
Thorough MT4 data analysis for CrudeOIL|M1.

Purpose: the `source='MT4'` rows are a chimera of (initial-demo, live, current-demo)
account phases that were stitched into one stream. This script slices the MT4 stream
along multiple dimensions to detect phase boundaries, characterize each phase, and
flag periods unfit for ML training.

Analyses performed:
  A. Daily coverage  — bars/day, first/last bar timestamps, distinct hours covered
  B. Daily price offset vs BC — mean/std (BC.close − MT4.close) per day
  C. Daily volatility profile — bar-return std, intraday ranges
  D. Tick granularity — what price increments does MT4 use? (broker tick-size signature)
  E. Volume profile — mean/median volume per day (broker-specific)
  F. Trading hours — first/last UTC hour with bars per day (account-config signature)
  G. Inferred phase boundaries — day-to-day changepoints in offset, granularity, volume
  H. Per-segment summary — for each detected segment, full statistics

Outputs:
  data/quality/mt4_analysis.json   — full structured report
  data/quality/mt4_daily.csv       — one row per day, all metrics, easy to chart in Excel
  data/quality/mt4_segments.csv    — final inferred segments with date ranges
  stdout                           — top-line findings + transition dates

Run:
  python3 scripts/analyze_mt4_segments.py
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
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
OUT_JSON = OUT_DIR / "mt4_analysis.json"
OUT_DAILY = OUT_DIR / "mt4_daily.csv"
OUT_SEGS = OUT_DIR / "mt4_segments.csv"


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


def fetch_daily_metrics(conn) -> list:
    """One row per UTC day where MT4 has any data. Each row carries all metrics
    needed for changepoint detection and segment characterization."""
    sql = """
    WITH mt4_day AS (
      SELECT
        date_trunc('day', time)::date                AS day,
        COUNT(*)                                     AS bars,
        MIN(EXTRACT(HOUR FROM time))::int            AS first_hour,
        MAX(EXTRACT(HOUR FROM time))::int            AS last_hour,
        COUNT(DISTINCT EXTRACT(HOUR FROM time))::int AS distinct_hours,
        AVG(last)::numeric(10,4)                     AS mean_close,
        STDDEV(last)::numeric(10,4)                  AS std_close,
        MIN(last)::numeric(10,4)                     AS min_close,
        MAX(last)::numeric(10,4)                     AS max_close,
        AVG(high - low)::numeric(10,4)               AS mean_range,
        AVG(volume)::numeric(20,4)                   AS mean_volume,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume)::numeric(20,4) AS median_volume,
        MAX(volume)::numeric(20,4)                   AS max_volume,
        SUM(volume)::numeric(20,4)                   AS total_volume,
        COUNT(*) FILTER (WHERE last <> ROUND(last, 2))  AS non_2dp_count,
        COUNT(*) FILTER (WHERE (last * 100)::numeric % 1 = 0)
                                                     AS even_2dp_count
      FROM market_data
      WHERE symbol='CrudeOIL' AND timeframe='M1' AND source='MT4'
      GROUP BY 1
    ),
    bc_day AS (
      SELECT
        date_trunc('day', time)::date                AS day,
        AVG(last)::numeric(10,4)                     AS bc_mean_close,
        COUNT(*)                                     AS bc_bars
      FROM market_data
      WHERE symbol='CrudeOIL' AND timeframe='M1' AND source='BC'
      GROUP BY 1
    ),
    overlap_day AS (
      -- For days where BOTH have bars at the same minute, compute mean (BC - MT4) at those minutes
      SELECT
        date_trunc('day', mt4.time)::date            AS day,
        COUNT(*)                                     AS overlap_bars,
        AVG(bc.last - mt4.last)::numeric(10,4)       AS mean_overlap_diff,
        STDDEV(bc.last - mt4.last)::numeric(10,4)    AS std_overlap_diff,
        MAX(ABS(bc.last - mt4.last))::numeric(10,4)  AS max_abs_overlap_diff
      FROM market_data mt4
      JOIN market_data bc
        ON bc.time = mt4.time
       AND bc.symbol = mt4.symbol
       AND bc.timeframe = mt4.timeframe
      WHERE mt4.symbol='CrudeOIL' AND mt4.timeframe='M1'
        AND mt4.source='MT4' AND bc.source='BC'
      GROUP BY 1
    )
    SELECT
      d.day::text,
      d.bars, d.first_hour, d.last_hour, d.distinct_hours,
      d.mean_close, d.std_close, d.min_close, d.max_close, d.mean_range,
      d.mean_volume, d.median_volume, d.max_volume, d.total_volume,
      d.non_2dp_count, d.even_2dp_count,
      b.bc_mean_close, b.bc_bars,
      o.overlap_bars, o.mean_overlap_diff, o.std_overlap_diff, o.max_abs_overlap_diff,
      (b.bc_mean_close - d.mean_close)::numeric(10,4)  AS daily_mean_diff
    FROM mt4_day d
    LEFT JOIN bc_day b USING (day)
    LEFT JOIN overlap_day o USING (day)
    ORDER BY d.day
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql)
    rows = []
    for r in cur.fetchall():
        # Decimal → float so json/csv don't choke
        d = {}
        for k, v in r.items():
            if v is not None and not isinstance(v, (int, float, str, bool)):
                d[k] = float(v)
            else:
                d[k] = v
        rows.append(d)
    cur.close()
    return rows


def detect_changepoints(daily: list) -> list:
    """Return indices in `daily` where a likely phase boundary occurs.

    Heuristics (any of):
      1. Day-to-day jump in `daily_mean_diff` > $0.50 with neighborhood stable
      2. Day-to-day jump in `mean_volume` > 5x with neighborhood stable
      3. Sustained ≥3-day shift in `daily_mean_diff` baseline > $0.50
    """
    cps = []
    n = len(daily)
    if n < 5:
        return cps

    # 1+3: rolling mean of daily_mean_diff over 5-day windows; flag where window-mean shifts
    diffs = [d.get("daily_mean_diff") for d in daily]
    valid = [(i, x) for i, x in enumerate(diffs) if x is not None]
    if len(valid) < 6:
        return cps

    # Compute 5-day trailing & leading window means; difference > $0.50 → changepoint
    for i in range(3, len(valid) - 3):
        idx, _ = valid[i]
        trail = [valid[j][1] for j in range(max(0, i - 3), i)]
        lead = [valid[j][1] for j in range(i, min(len(valid), i + 3))]
        if not trail or not lead:
            continue
        m_trail = statistics.mean(trail)
        m_lead = statistics.mean(lead)
        if abs(m_lead - m_trail) > 0.50:
            cps.append({
                "day_index": idx,
                "day": daily[idx]["day"],
                "type": "diff_shift",
                "trailing_mean_diff": round(m_trail, 3),
                "leading_mean_diff": round(m_lead, 3),
                "magnitude": round(m_lead - m_trail, 3),
            })

    # 2: volume regime shifts
    vols = [d.get("mean_volume") for d in daily]
    valid_v = [(i, x) for i, x in enumerate(vols) if x is not None and x > 0]
    for i in range(3, len(valid_v) - 3):
        idx, _ = valid_v[i]
        trail = [valid_v[j][1] for j in range(max(0, i - 3), i)]
        lead = [valid_v[j][1] for j in range(i, min(len(valid_v), i + 3))]
        if not trail or not lead:
            continue
        m_trail = statistics.mean(trail)
        m_lead = statistics.mean(lead)
        if m_trail > 0 and (m_lead / m_trail > 5 or m_trail / m_lead > 5):
            cps.append({
                "day_index": idx,
                "day": daily[idx]["day"],
                "type": "volume_shift",
                "trailing_mean_volume": round(m_trail, 2),
                "leading_mean_volume": round(m_lead, 2),
                "ratio": round(m_lead / m_trail if m_trail else 0, 2),
            })

    # Dedupe by day; keep the first signal per day
    seen = set()
    deduped = []
    for cp in cps:
        if cp["day"] not in seen:
            seen.add(cp["day"])
            deduped.append(cp)
    return deduped


def segment_from_changepoints(daily: list, cps: list) -> list:
    """Given changepoint days, slice `daily` into contiguous segments and summarize each."""
    if not daily:
        return []
    boundaries = sorted({cp["day_index"] for cp in cps})
    starts = [0] + [b for b in boundaries]
    segments = []
    for i, s in enumerate(starts):
        e = starts[i + 1] - 1 if i + 1 < len(starts) else len(daily) - 1
        seg = daily[s : e + 1]
        if not seg:
            continue
        diffs = [d["daily_mean_diff"] for d in seg if d.get("daily_mean_diff") is not None]
        vols = [d["mean_volume"] for d in seg if d.get("mean_volume") is not None]
        bars = [d["bars"] for d in seg if d.get("bars") is not None]
        gran = []
        for d in seg:
            ev = d.get("even_2dp_count") or 0
            n2 = d.get("non_2dp_count") or 0
            tot = (d.get("bars") or 0)
            if tot:
                gran.append(ev / tot)
        segments.append({
            "start_day": seg[0]["day"],
            "end_day": seg[-1]["day"],
            "n_days": len(seg),
            "total_bars": sum(bars),
            "mean_diff_vs_bc":  round(statistics.mean(diffs), 3) if diffs else None,
            "stdev_diff_vs_bc": round(statistics.stdev(diffs), 3) if len(diffs) > 1 else None,
            "median_volume":    round(statistics.median(vols), 2) if vols else None,
            "mean_volume":      round(statistics.mean(vols), 2) if vols else None,
            "even_2dp_share":   round(statistics.mean(gran), 3) if gran else None,
            "median_bars_per_day": int(statistics.median(bars)) if bars else 0,
        })
    return segments


def main() -> int:
    print(f"connecting to {PG['host']}:{PG['port']}/{PG['dbname']} ...")
    conn = psycopg2.connect(**PG)
    print("connected.\n")

    print("[A-F] aggregating daily MT4 + BC overlap metrics  (~5-15s) ...")
    daily = fetch_daily_metrics(conn)
    print(f"  → {len(daily)} days with MT4 data\n")

    print("[G] running changepoint detection ...")
    cps = detect_changepoints(daily)
    print(f"  → {len(cps)} candidate phase boundaries\n")

    print("[H] segment characterization ...")
    segments = segment_from_changepoints(daily, cps)
    for i, s in enumerate(segments):
        print(
            f"  Segment {i+1}: {s['start_day']} → {s['end_day']}  "
            f"({s['n_days']:>3}d, {s['total_bars']:>6,} bars)  "
            f"diff_vs_BC={s['mean_diff_vs_bc']}  "
            f"med_vol={s['median_volume']}  "
            f"med_bars/day={s['median_bars_per_day']}"
        )

    if cps:
        print(f"\n=== INFERRED PHASE BOUNDARY DATES ===")
        for cp in cps:
            print(
                f"  {cp['day']}  type={cp['type']}  "
                f"detail={ {k:v for k,v in cp.items() if k not in ('day','day_index','type')} }"
            )

    # ── Write outputs ─────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_days": len(daily),
        "total_mt4_bars": sum(d.get("bars", 0) for d in daily),
        "first_day": daily[0]["day"] if daily else None,
        "last_day":  daily[-1]["day"] if daily else None,
        "changepoints": cps,
        "segments": segments,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nwrote: {OUT_JSON}")

    # CSV per-day for charting
    if daily:
        keys = list(daily[0].keys())
        with open(OUT_DAILY, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for r in daily:
                w.writerow(r)
        print(f"wrote: {OUT_DAILY}")

    # CSV segments
    if segments:
        keys = list(segments[0].keys())
        with open(OUT_SEGS, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for r in segments:
                w.writerow(r)
        print(f"wrote: {OUT_SEGS}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
