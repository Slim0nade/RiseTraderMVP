# 2026-04-21 — Data Quality Assessment & Barchart Gap-Fill Pipeline

## Context

Pivoted mid-session from strategy-testing rigor (Monte Carlo / walk-forward
validation) to data hygiene after user directive: *"No first assess the gaps
AND FILL THEM WITH HIGHLY CLEAN DATA."*

Scope: 4 live symbols × 6 timeframes (CrudeOIL, USA500, GBPJPY, #TSLA ×
M1/M5/M15/H1/H4/D1). DB-normalized symbol forms: `GBPJPY` (no trailing dot),
`TSLA` (no `#`).

## Gap assessment findings (from `scripts/assess_data_gaps.py`)

### Critical holes

| Cell | State | Root cause |
|---|---|---|
| USA500 M5 | **0 bars** | M1→M5 aggregator never ran |
| GBPJPY M5 | **0 bars** | M1→M5 aggregator never ran |
| CrudeOIL M1 (2025) | ~330k missing across 5 gaps | Ingestion holes — BC imports stopped |
| CrudeOIL M5 | stale since 2024-12-06 (502d) | Aggregator stopped |
| TSLA M1 | only 54 days of history (since 2026-02-26) | Stream-only, no backfill |
| TSLA M5 | stale since 2026-02-10 | Aggregator stopped |
| CrudeOIL M1 | 34,201 duplicate timestamp buckets | No dedup policy applied |

### Specific CrudeOIL M1 2025 gaps (largest first)

- 2025-06-18 → 2025-11-25: ~229,669 missing bars (5-month hole)
- 2025-11-25 → 2025-12-29: ~49,552 missing (1-month)
- 2026-04-02 → 2026-04-19: ~24,624 missing (known MT4 outage)
- 2025-04-09 → 2025-04-22: ~19,445 missing
- 2026-01-23 → 2026-02-02: ~13,643 missing
- 2026-02-17 → 2026-02-27: ~13,598 missing

### Source inventory

| Symbol | Sources in DB |
|---|---|
| CrudeOIL | BC 5,869,307 + MT4 792,877 |
| GBPJPY  | DUKASCOPY 2,593,381 + MT4 288,429 |
| USA500  | DUKASCOPY 730,306 + MT4 96,212 |
| TSLA    | CSV 14,355 + MT4 8,311 |

`assess_data_gaps.py` had a markdown render bug (`None[:10]` TypeError when a
cell has zero bars — USA500 M5 / GBPJPY M5). Patched at
`scripts/assess_data_gaps.py:275` with `(cov.get('first_time') or '')[:10]`.
JSON report was written successfully; only the .md render crashed.

## Fill policy (user-confirmed)

| Question | Decision |
|---|---|
| CrudeOIL 2025 gaps → source? | **Barchart re-import** (user has Premier+) |
| TSLA M1 history → source? | **Barchart** (user renewed subscription) |
| Duplicates policy? | **Keep each source separate**: dedupe within-source only; keep both BC and MT4 rows at the same timestamp |
| Run order? | **Fill gaps first, then aggregates** |

## Scripts written (all in `RiseTraderMVP/scripts/`)

| Script | Purpose |
|---|---|
| `assess_data_gaps.py` | 5 checks per cell (coverage, dup buckets, OHLC sanity, volume sanity, gap detection via LAG). Writes `data/quality/gap_report.json` + `.md`. Idempotent — safe to re-run anytime. |
| `import_barchart_csvs.py` | Auto-detects Barchart CSV shapes (Time/Open/High/Low/Last/Volume variants), handles symbol-local timezones, `ON CONFLICT (time, source, timeframe, symbol) DO NOTHING`. Reads from `data/downloads/barchart/`. |
| `dedupe_within_source.py` | Removes rows sharing `(symbol, tf, time, source)`. Defaults to dry-run; `--execute` applies. Does NOT touch cross-source dupes. |
| `aggregate_m1_to_m5.py` | M1→M5 rollup with `to_timestamp(floor(epoch/300)*300)` bucketing. `ON CONFLICT DO UPDATE` = idempotent. Processes per-source so MT4 M1 → MT4 M5 and BC M1 → BC M5 stay distinct. |
| `scrape_barchart_gaps.py` | Range-driven Barchart scraper. Imports Selenium helpers from `../RiseTrader/download_crude_oil_data.py`. Walks backward in 20-day windows. CL contract resolver auto-picks front-month per window date. `--stop-on-empty` halts after 2 consecutive empty/blocked CSVs. |

## Key design decisions & gotchas

### 1. CL contract resolver is expiry-math, not actual-roll

`cl_contract_for(date)` returns the contract whose expiry is the first on-or-after
the given date. Expiry = 3 business days before the 25th of the delivery-prior
month (correct NYMEX rule). BUT Barchart's quoted front-month often rolls 5-7
days before expiry due to liquidity collapse. If we scrape a mid-month boundary
date and Barchart serves the next contract instead of what we resolve,
`--dry-run` will reveal it before a real run burns bandwidth. Patch if needed:
change `_business_days_before(anchor, 3)` to `_business_days_before(anchor, 7)`
or add a `--ticker` override flag.

### 2. TSLA M1 depth on Barchart is ~6-12 months, NOT 2010

Despite D1 going back to 2010, Barchart Premier caps equity intraday at roughly
6-12 months. Script uses `--stop-on-empty` to halt once two consecutive windows
return empty — expect the cutoff around mid-2025, not deep history. For proper
TSLA M1 ML training history we'd need Polygon.io or Alpaca as a supplementary
source.

### 3. Throttling vs. end-of-history distinction

`inspect_csv()` detects Cloudflare/CAPTCHA HTML-page dumps vs. valid CSV
responses. Each downloaded file now logs `rows=N first=TS last=TS size=B`.
HTML-looking downloads get flagged as `!! CAPTCHA / block` and labeled
`likely rate-limited` when they trip the stop — so you can tell a natural
end-of-history from a throttle in the log without opening files manually.
Re-running after a rate-limit pause is idempotent via the importer's
`ON CONFLICT DO NOTHING`.

### 4. Barchart Selenium helpers — only stable ones imported; date/frequency embedded locally (V9 parity)

After reviewing the sibling repo's `download_crude_oil_dataV9.py` and
`download_crude_oil_dataV9_missing_data.py`, we discovered the base
`../RiseTrader/download_crude_oil_data.py` ships an **older** date picker
that fails in two ways:

1. Uses `str(target_date.day)` (no zero padding) — fails to match DOM
   labels like `"05"` in the Barchart calendar.
2. No dual-occurrence handling — for days > 20 the calendar shows the
   current month's XX and the next month's XX both un-muted, and V9
   correctly picks `matching_buttons[1]`; the base file picks [0] and
   lands in the wrong month.

The MVP scraper therefore only imports the **stable** helpers:
`login`, `set_total_volume_checkbox`, `click_download_button`,
`wait_for_downloads_to_complete`. Everything date/frequency/notification
related is embedded locally in `scrape_barchart_gaps.py` as `_`-prefixed
V9-equivalent functions:

- `_set_single_date` — zero-padded day, dual-occurrence fix, JS click.
- `_set_start_date` / `_set_end_date` — separate setters with
  `window.scrollTo(0, 0)` between them; `max_retries=5` on end date.
- `_set_frequency_intraday(minutes)` — selects `"Intraday"` (NOT
  `"Intraday Nearby"`) and re-types the aggregation. Called **every
  window**, because Barchart's UI occasionally reverts to Daily after a
  download and would silently serve daily bars for the rest of the run.
- `_click_on_historical_download_div` + `_click_center_of_screen`
  (lazy-import pyautogui, no-op if missing) — dismiss the post-download
  notification overlay that otherwise intercepts the next click.

Credentials still come from `.env`: `BARCHART_USERNAME`,
`BARCHART_PASSWORD`. Default path is `MVP_ROOT.parent / "RiseTrader"`;
`--risetrader-path` overrides.

### 4b. Span-sanity check + span-in-logs (V9-parity)

`inspect_csv()` now drops the last row before timestamp aggregation
(mirrors V9's `iloc[-2]`, which avoids Barchart's "Downloaded from…"
footer row) and returns `span_days` alongside rows/first/last.

New helper `is_csv_span_suspicious(info, window_days)` flags files where
`span > 2*window AND rows < window*10` — the classic "served Daily
instead of Intraday" signature (20 rows spanning 20 days). Flagged
files get renamed to `*.DAILY_SUSPECTED.csv` so the importer skips them
and the user can eyeball them in `data/downloads/barchart/`.

### 4c. Wait times randomized (V9-parity anti-rate-limit)

- Pre-download wait: `random.randint(10, 15)` seconds.
- Post-download wait between windows: `random.randint(15, 20)` seconds.
- Firefox prefs expanded to suppress the download panel, alert,
  notification bubble, and auto-focus; MIME list now includes
  `application/octet-stream`.

### 5. Corrected run order (TSLA probe before CL scrape)

Reviewer caught this: 90 seconds of CL scraping burns cleanly, but if auth
has broken we want to know in the first 20-day window. Revised order:

1. CL dry-run — verify resolver picks sane contracts
2. **TSLA small probe (real scrape, 20-day window) — validates auth + CSV flow**
3. TSLA probe ingest via `import_barchart_csvs.py --dry-run`
4. CL gaps real scrape (2025-06-18 → 2026-04-19)
5. CL ingest
6. TSLA full backfill with `--stop-on-empty`
7. TSLA ingest
8. `dedupe_within_source.py --execute`
9. `aggregate_m1_to_m5.py`
10. Re-run `assess_data_gaps.py` to verify

### 6. MCP DB tool is blocked in Cowork

`mcp__risetrader-db__query` is enabled in the project `.claude/settings.json`
but blocked by a Cowork runtime-level PreToolUse hook regardless of the
connector-panel toggle. Workaround: run scripts from terminal via Claude
Code (where the project allowlist applies) or execute them directly with
`python3`. The sandbox can't reach `localhost:5433` either, so everything
DB-touching must run on the host.

## Live trading items still pending (carried forward)

- Task #20: Rebalance SYMBOL_WEIGHTS based on 12-month backtest (value_area
  dominant across all 4 symbols: CrudeOIL +217%/Sharpe 16.2, USA500 +71%/21.2,
  GBPJPY +35%/22.2, TSLA +142%/17.9)
- Task #16: Persist BRENT_OIL / USA500 / GBPJPY XGBoost models
- Deploy pending threshold changes (TRENDING/RANGING 0.60→0.45, UNKNOWN
  0.75→0.55 in `src/trading/regime/strategy_router.py`) via `docker-compose
  restart api`
- Debug `trend_following` engine `NoneType` error on CrudeOIL/USA500/GBPJPY
  (works on TSLA) — persistent, not transient
- Run Monte Carlo validation + walk-forward on value_area winners once data
  is clean

## Useful invocation reference

```bash
# Baseline assessment (safe to re-run anytime)
python3 scripts/assess_data_gaps.py

# Step 1 — verify CL resolver
python3 scripts/scrape_barchart_gaps.py --symbol CrudeOIL --interval 1 \
    --start 2025-08-15 --end 2025-08-22 --dry-run

# Step 2 — TSLA auth probe (small, real)
python3 scripts/scrape_barchart_gaps.py --symbol TSLA --interval 1 \
    --start 2026-03-01 --end 2026-04-21

# Step 3 — validate import plumbing
python3 scripts/import_barchart_csvs.py --dry-run

# Step 4 — CL gaps (fills all 5 holes in one backward walk)
python3 scripts/scrape_barchart_gaps.py --symbol CrudeOIL --interval 1 \
    --start 2025-06-18 --end 2026-04-19

# Step 5 — ingest
python3 scripts/import_barchart_csvs.py

# Step 6 — TSLA full backfill (auto-stops at Barchart's history limit)
python3 scripts/scrape_barchart_gaps.py --symbol TSLA --interval 1 \
    --start 2010-06-29 --end 2025-12-31 --stop-on-empty

# Step 7 — ingest
python3 scripts/import_barchart_csvs.py

# Step 8 — dedupe within source (dry-run first)
python3 scripts/dedupe_within_source.py
python3 scripts/dedupe_within_source.py --execute

# Step 9 — rebuild M5 from M1
python3 scripts/aggregate_m1_to_m5.py

# Step 10 — verify
python3 scripts/assess_data_gaps.py
```
