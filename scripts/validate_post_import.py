#!/usr/bin/env python3
"""
Post-import validation for the BC gap-fill.

Runs every check we'd want before trusting the merged MT4+BC market_data table
for ML training, and writes the result to data/quality/post_import_validation.json
so it can be read off-disk by other tools / agents.

Validations performed:
  1. Per-source row counts (BC vs MT4) for CrudeOIL|M1.
  2. Per-gap fill verification: for each of the original 10 real gaps, count BC bars
     inside the gap window, find first/last BC bar inside it.
  3. Boundary stitching: MT4 last close before each gap vs BC first close inside,
     and BC last close inside vs MT4 first close after — should agree to within ~$0.50.
  4. Cross-source price agreement at overlap minutes: sample 5000 timestamps where
     BOTH MT4 and BC have a row; report distribution of (BC.close − MT4.close).
  5. Gap density post-import: recompute suspicious gaps in the merged stream using
     the same threshold the original assessor used (>= 100 hours).
  6. OHLC integrity in BC rows (ought to be 0 violations — already validated on disk
     but re-run against DB to catch any insert corruption).

Run: `python3 scripts/validate_post_import.py`
Reads: PG creds from .env (POSTGRES_PASSWORD), defaults to localhost:5433/risetrader.
Writes: data/quality/post_import_validation.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("error: psycopg2 not installed. Run: python3 -m pip install psycopg2-binary")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
OUT = ROOT / "data" / "quality" / "post_import_validation.json"

# Read PG creds from .env if present (matches existing scripts).
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
    "password": os.environ.get("POSTGRES_PASSWORD", os.environ.get("PGPASSWORD", "risetrader2024")),
}

# Original 10 real MT4 gaps (from data/quality/gap_report.json baseline)
ORIGINAL_GAPS = [
    ("2025-06-18 20:58:00+00", "2025-11-25 08:48:00+00"),
    ("2025-11-25 09:14:01+00", "2025-12-29 19:08:00+00"),
    ("2026-04-02 20:58:00+00", "2026-04-19 23:23:00+00"),
    ("2025-04-09 04:28:00+00", "2025-04-22 16:34:00+00"),
    ("2026-01-23 17:44:00+00", "2026-02-02 05:08:00+00"),
    ("2026-02-17 20:33:00+00", "2026-02-27 07:12:00+00"),
    ("2026-01-14 19:41:00+00", "2026-01-22 00:47:00+00"),
    ("2026-03-11 01:06:00+00", "2026-03-15 23:42:00+00"),
    ("2026-03-04 17:35:00+00", "2026-03-09 02:49:00+00"),
    ("2026-02-02 13:45:00+00", "2026-02-06 21:58:00+00"),
]


def main() -> int:
    print(f"connecting to {PG['host']}:{PG['port']}/{PG['dbname']} as {PG['user']} ...")
    try:
        conn = psycopg2.connect(**PG)
    except Exception as exc:
        print(f"!! connect failed: {exc}")
        return 2
    print("connected.\n")

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pg": {k: v for k, v in PG.items() if k != "password"},
        "checks": {},
    }
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ── 1. per-source counts ──────────────────────────────────────────
    print("[1/6] per-source row counts ...")
    cur.execute(
        """
        SELECT source, COUNT(*) AS bars,
               MIN(time)::text AS first_ts, MAX(time)::text AS last_ts
        FROM market_data
        WHERE symbol='CrudeOIL' AND timeframe='M1'
        GROUP BY source ORDER BY source
        """
    )
    sources = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT COUNT(*) AS n FROM market_data WHERE symbol='CrudeOIL' AND timeframe='M1'"
    )
    total = cur.fetchone()["n"]
    report["checks"]["per_source"] = {
        "total_crudeoil_m1": total,
        "by_source": sources,
    }
    for s in sources:
        print(f"   {s['source']:>4}  {s['bars']:>10,}  {s['first_ts'][:19]} → {s['last_ts'][:19]}")
    print(f"   TOTAL: {total:,}")

    # ── 2. per-gap fill verification ──────────────────────────────────
    print("\n[2/6] per-gap BC fill verification ...")
    gap_results = []
    for prev_ts, curr_ts in ORIGINAL_GAPS:
        cur.execute(
            """
            SELECT COUNT(*) AS bc_bars,
                   MIN(time)::text AS first_bc, MAX(time)::text AS last_bc,
                   (SELECT last FROM market_data
                     WHERE symbol='CrudeOIL' AND timeframe='M1' AND source='BC'
                       AND time >= %s::timestamptz AND time <= %s::timestamptz
                     ORDER BY time ASC LIMIT 1) AS first_bc_close,
                   (SELECT last FROM market_data
                     WHERE symbol='CrudeOIL' AND timeframe='M1' AND source='BC'
                       AND time >= %s::timestamptz AND time <= %s::timestamptz
                     ORDER BY time DESC LIMIT 1) AS last_bc_close
            FROM market_data
            WHERE symbol='CrudeOIL' AND timeframe='M1' AND source='BC'
              AND time > %s::timestamptz AND time < %s::timestamptz
            """,
            (prev_ts, curr_ts, prev_ts, curr_ts, prev_ts, curr_ts),
        )
        row = dict(cur.fetchone())
        # MT4 boundaries: last MT4 row at <= prev_ts, first MT4 row at >= curr_ts.
        # NB: column is `last` (Barchart-style); aliased to `close` for code clarity.
        cur.execute(
            "SELECT last AS close FROM market_data WHERE symbol='CrudeOIL' AND timeframe='M1' "
            "AND source='MT4' AND time <= %s::timestamptz ORDER BY time DESC LIMIT 1",
            (prev_ts,),
        )
        r = cur.fetchone()
        row["mt4_last_close_before"] = float(r["close"]) if r else None
        cur.execute(
            "SELECT last AS close FROM market_data WHERE symbol='CrudeOIL' AND timeframe='M1' "
            "AND source='MT4' AND time >= %s::timestamptz ORDER BY time ASC LIMIT 1",
            (curr_ts,),
        )
        r = cur.fetchone()
        row["mt4_first_close_after"] = float(r["close"]) if r else None
        if row["first_bc_close"] is not None and row["mt4_last_close_before"] is not None:
            row["head_stitch_diff"] = float(row["first_bc_close"]) - row["mt4_last_close_before"]
        if row["last_bc_close"] is not None and row["mt4_first_close_after"] is not None:
            row["tail_stitch_diff"] = row["mt4_first_close_after"] - float(row["last_bc_close"])
        row["gap"] = f"{prev_ts} → {curr_ts}"
        gap_results.append(row)
        head = row.get("head_stitch_diff")
        tail = row.get("tail_stitch_diff")
        head_s = f"{head:+.2f}" if head is not None else "n/a"
        tail_s = f"{tail:+.2f}" if tail is not None else "n/a"
        print(
            f"   {prev_ts[:10]} → {curr_ts[:10]}  "
            f"BC_bars={row['bc_bars']:>5}  head_stitch={head_s}  tail_stitch={tail_s}"
        )
    report["checks"]["per_gap_fill"] = gap_results

    # ── 3. cross-source price agreement at overlap minutes ────────────
    print("\n[3/6] cross-source price agreement (sample 5000 overlap minutes) ...")
    cur.execute(
        """
        WITH overlap AS (
          SELECT mt4.time, mt4.last AS mt4_close, bc.last AS bc_close
          FROM market_data mt4
          JOIN market_data bc
            ON bc.time = mt4.time
           AND bc.symbol = mt4.symbol
           AND bc.timeframe = mt4.timeframe
          WHERE mt4.symbol='CrudeOIL' AND mt4.timeframe='M1'
            AND mt4.source='MT4' AND bc.source='BC'
        ),
        sampled AS (
          SELECT * FROM overlap ORDER BY random() LIMIT 5000
        )
        SELECT
          COUNT(*) AS n,
          AVG(bc_close - mt4_close)::numeric(20,5) AS mean_diff,
          STDDEV(bc_close - mt4_close)::numeric(20,5) AS stddev_diff,
          MIN(bc_close - mt4_close)::numeric(20,5) AS min_diff,
          MAX(bc_close - mt4_close)::numeric(20,5) AS max_diff,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(bc_close - mt4_close))::numeric(20,5) AS median_abs_diff,
          PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ABS(bc_close - mt4_close))::numeric(20,5) AS p95_abs_diff,
          PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ABS(bc_close - mt4_close))::numeric(20,5) AS p99_abs_diff,
          SUM(CASE WHEN ABS(bc_close - mt4_close) > 0.50 THEN 1 ELSE 0 END) AS n_disagree_gt_0_50,
          SUM(CASE WHEN ABS(bc_close - mt4_close) > 1.00 THEN 1 ELSE 0 END) AS n_disagree_gt_1_00
        FROM sampled
        """
    )
    row = dict(cur.fetchone())
    # Convert Decimals → floats so json.dumps doesn't choke
    for k, v in list(row.items()):
        if v is not None and not isinstance(v, (int, float, str, bool)):
            row[k] = float(v)
    report["checks"]["cross_source_overlap"] = row
    if row["n"]:
        print(
            f"   sampled={row['n']}  median_abs_diff=${row['median_abs_diff']:.4f}  "
            f"p95=${row['p95_abs_diff']:.4f}  p99=${row['p99_abs_diff']:.4f}  "
            f">$0.50: {row['n_disagree_gt_0_50']}  >$1.00: {row['n_disagree_gt_1_00']}"
        )
    else:
        print("   no overlapping minutes found (BC and MT4 share no timestamps?)")

    # ── 4. recompute suspicious gaps in merged stream ─────────────────
    print("\n[4/6] recomputing suspicious gaps (merged MT4 + BC stream) ...")
    cur.execute(
        """
        WITH ordered AS (
          SELECT time, LAG(time) OVER (ORDER BY time) AS prev_time
          FROM (
            SELECT DISTINCT time FROM market_data
            WHERE symbol='CrudeOIL' AND timeframe='M1'
          ) t
        ),
        gaps AS (
          SELECT prev_time, time AS curr_time,
                 EXTRACT(EPOCH FROM (time - prev_time)) AS gap_s
          FROM ordered WHERE prev_time IS NOT NULL
        )
        SELECT
          SUM(CASE WHEN gap_s > 100*3600 THEN 1 ELSE 0 END) AS suspicious_5plus_days,
          SUM(CASE WHEN gap_s > 24*3600 AND gap_s <= 100*3600 THEN 1 ELSE 0 END) AS gap_1_to_4_days,
          SUM(CASE WHEN gap_s > 60 AND gap_s <= 24*3600 THEN 1 ELSE 0 END) AS gap_under_1_day,
          MAX(gap_s)/3600.0 AS max_gap_hours
        FROM gaps
        """
    )
    row = dict(cur.fetchone())
    for k, v in list(row.items()):
        if v is not None and not isinstance(v, (int, float, str, bool)):
            row[k] = float(v)
    report["checks"]["suspicious_gaps_post_import"] = row
    print(
        f"   suspicious (>100h): {row['suspicious_5plus_days']}   "
        f"1-4d: {row['gap_1_to_4_days']}   "
        f"under 1d: {row['gap_under_1_day']}   "
        f"max gap: {row['max_gap_hours']:.1f}h"
    )

    # Top 10 remaining suspicious gaps for inspection
    cur.execute(
        """
        WITH ordered AS (
          SELECT time, LAG(time) OVER (ORDER BY time) AS prev_time
          FROM (
            SELECT DISTINCT time FROM market_data
            WHERE symbol='CrudeOIL' AND timeframe='M1'
          ) t
        )
        SELECT prev_time::text AS prev, time::text AS curr,
               EXTRACT(EPOCH FROM (time - prev_time))/3600 AS hours
        FROM ordered
        WHERE prev_time IS NOT NULL AND time - prev_time > INTERVAL '24 hours'
        ORDER BY (time - prev_time) DESC LIMIT 15
        """
    )
    top = [dict(r) for r in cur.fetchall()]
    for r in top:
        if r.get("hours") is not None:
            r["hours"] = float(r["hours"])
    report["checks"]["top_remaining_gaps"] = top
    print("   top remaining gaps (>24h):")
    for r in top[:10]:
        print(f"     {r['prev'][:19]} → {r['curr'][:19]}   {r['hours']:.1f}h")

    # ── 5. OHLC integrity on the BC rows in DB ────────────────────────
    print("\n[5/6] OHLC integrity on BC rows in DB ...")
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE high < low)            AS high_lt_low,
          COUNT(*) FILTER (WHERE open > high)           AS open_gt_high,
          COUNT(*) FILTER (WHERE open < low)            AS open_lt_low,
          COUNT(*) FILTER (WHERE last > high)           AS close_gt_high,
          COUNT(*) FILTER (WHERE last < low)            AS close_lt_low,
          COUNT(*) FILTER (WHERE open  <= 0)            AS nonpos_open,
          COUNT(*) FILTER (WHERE high  <= 0)            AS nonpos_high,
          COUNT(*) FILTER (WHERE low   <= 0)            AS nonpos_low,
          COUNT(*) FILTER (WHERE last  <= 0)            AS nonpos_close,
          COUNT(*) FILTER (WHERE volume < 0)            AS neg_volume,
          COUNT(*)                                      AS total_bc
        FROM market_data
        WHERE symbol='CrudeOIL' AND timeframe='M1' AND source='BC'
        """
    )
    row = dict(cur.fetchone())
    report["checks"]["bc_ohlc_integrity"] = row
    violations = sum(
        v for k, v in row.items()
        if k != "total_bc" and isinstance(v, int)
    )
    print(f"   total BC rows: {row['total_bc']:,}   violations: {violations}")
    if violations:
        for k, v in row.items():
            if k != "total_bc" and v:
                print(f"     {k} = {v}")

    # ── 6. summary verdict ────────────────────────────────────────────
    print("\n[6/6] summary verdict ...")
    verdicts = []
    if total >= 5_700_000:
        verdicts.append(("import_landed", "PASS", f"total {total:,} >= 5.7M expected"))
    else:
        verdicts.append(("import_landed", "FAIL", f"total {total:,} < 5.7M"))
    bc_count = next((s["bars"] for s in sources if s["source"] == "BC"), 0)
    if bc_count >= 180_000:
        verdicts.append(("bc_count", "PASS", f"BC rows = {bc_count:,}"))
    else:
        verdicts.append(("bc_count", "FAIL", f"BC rows = {bc_count:,}"))
    if violations == 0:
        verdicts.append(("ohlc_integrity", "PASS", "0 violations"))
    else:
        verdicts.append(("ohlc_integrity", "FAIL", f"{violations} violations"))
    susp = report["checks"]["suspicious_gaps_post_import"]["suspicious_5plus_days"]
    if susp <= 5:
        verdicts.append(("gap_closure", "PASS", f"{susp} suspicious gaps remain (was 10)"))
    else:
        verdicts.append(("gap_closure", "PARTIAL", f"{susp} suspicious gaps remain"))
    cs = report["checks"]["cross_source_overlap"]
    if cs.get("n") and cs["median_abs_diff"] < 0.10:
        verdicts.append(
            ("cross_source_agreement", "PASS",
             f"median |BC-MT4|=${cs['median_abs_diff']:.4f}"))
    else:
        verdicts.append(
            ("cross_source_agreement", "REVIEW",
             f"median |BC-MT4|=${cs.get('median_abs_diff','n/a')}, p95=${cs.get('p95_abs_diff','n/a')}"))
    stitch_failures = [
        g for g in gap_results
        if g.get("head_stitch_diff") is not None and abs(g["head_stitch_diff"]) > 0.50
    ]
    if not stitch_failures:
        verdicts.append(("boundary_stitch", "PASS", "all 10 gap heads stitch within $0.50"))
    else:
        verdicts.append(("boundary_stitch", "REVIEW", f"{len(stitch_failures)} gap heads stitch > $0.50 off"))
    report["verdicts"] = [{"check": c, "status": s, "detail": d} for c, s, d in verdicts]
    print()
    for c, s, d in verdicts:
        marker = "✓" if s == "PASS" else "?" if s in ("REVIEW", "PARTIAL") else "✗"
        print(f"   {marker} {c:<28}  {s:<7}  {d}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nwrote: {OUT}")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
