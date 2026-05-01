# 2026-04-28 — Data Quality Deep Audit, MT4 Phase Mapping, Source-Consistency Strategy

Massive data-quality session that closed out the Barchart gap-fill task and uncovered structural issues across the whole symbol universe. This memory consolidates findings + the proposed BC-as-canonical / MT4-as-live architecture plan.

## TL;DR

1. **CrudeOIL M1 gap-fill is DONE.** 187,636 BC bars added, all 10 historical gaps closed, OHLC integrity 100%, cross-file price agreement 100%. 5,728,704 total CrudeOIL M1 bars in DB.
2. **MT4 source is a chimera of 6 account phases**, three of which are too dirty for ML training. Phase tagging is the right answer, not deletion.
3. **Multiple deep-history feeds died silently months ago** (DXY 393d, VIX 392d, XAUUSD 60d, CrudeOIL M5 508d). Need a staleness watchdog.
4. **5 symbols (TSLA, MSFT, GASOLINE, WHEAT, CORN) have <2 weeks of MT4-only data** — useless for training, need BC backfill.
5. **DOLLAR_INDX has zero rows.** Either dupe of DXY or never wired up.
6. **Aggregation layer is broken**: M5 has only BC, M15 has only MT4, neither has both sources at every TF.
7. **The 377k MT4 M15 bars are a separate legacy bulk import**, not aggregated from M1. Untrusted, should be replaced by chunked M1→M15.
8. **Architecture decision**: BC = canonical historical for all symbols × timeframes; MT4 = live streaming only. Drop DUKASCOPY/CSV legacy sources.

---

## 1. CrudeOIL M1 gap-fill — completed

### What we did

- Scraped Barchart via patched `scripts/scrape_barchart_gaps.py` over 38 windows covering 2025-04-08 → 2026-04-19.
- Discovered Barchart needs a specific anti-bot dance: **(a) hard reload page, (b) wipe localStorage/sessionStorage, (c) clear BOTH date inputs first, (d) click "Today" in the picker, (e) THEN navigate to target month and click day.** Without this, picker click events don't commit. See script for full implementation.
- Fixed the importer's Barchart `Latest`-column alias (was rejecting all files looking for `close/last`).
- Fixed importer's row-counter bug: `execute_values(page_size=N)` only leaves `cur.rowcount` = LAST batch's count. Now manually batches and accumulates. Without this fix, "skipped" counts looked artificially round (5000s, 10000s) and were misleading.

### Validation results — `data/quality/post_import_validation.json`

| Check | Status | Detail |
|---|---|---|
| import_landed | ✓ PASS | 5,718,765 total CrudeOIL M1 (was 5,531,032) |
| bc_count | ✓ PASS | BC rows = 5,614,130 |
| ohlc_integrity | ✓ PASS | 0 violations across 5.6M BC rows |
| gap_closure | ✓ PASS | 0 suspicious gaps remain (was 10) |
| cross_source_agreement | ? REVIEW | median \|BC-MT4\|=$0.265, p95=$7.85 (real broker-vs-NYMEX disagreement, not data bug) |
| boundary_stitch | ? REVIEW | 9 of 10 gap heads stitch >$0.50 off (also broker-vs-NYMEX, not data bug) |

### Residual gaps after fill

380,607 minutes were missing originally → only **67 minutes residual** across all 10 gaps = **99.98% coverage**. Largest residual is 40 minutes on the 2025-04-09 gap (Barchart CSV starts at CT midnight while MT4 stopped 36min before that).

---

## 2. MT4 is 6 account phases, not one source

`scripts/analyze_mt4_segments.py` revealed the MT4 source is actually a stitched chimera of multiple account configurations. Daily mean-diff vs BC reveals clean step changes in price-level offset that exactly map to the user's account history (initial demo → live → demo paper).

### The 6 phases

| Phase | Period | Bars | Mean diff vs BC | Per-min overlap | Verdict |
|---|---|---:|---:|---:|---|
| **1** | 2024-08-19 → 2025-03-25 | ~26,000 | ±$0.10 | ±$0.03 | ✓ EXCELLENT — initial demo |
| **2** | 2025-04-08 → 2025-06-18 | ~22,000 | drifts -$0.4 → -$7.96 | drifts to -$8.59 | ✗ BAD — feed degraded |
| **3** | 2025-06-19 → 2025-11-24 | 0 | — | — | OUTAGE (5-month MT4 hole that BC filled) |
| **4** | 2025-11-25 → 2026-02-27 | ~12,000 | -$0.40 stable | -$0.40 stable | ✓ GOOD — live phase, 3 months |
| **5** | 2026-03-01 → 2026-04-02 | ~9,000 | -$1.27 → -$11.63 | up to -$14.76 | ✗ CATASTROPHIC — synthetic feed during Hormuz crisis |
| **6** | 2026-04-19 → present | ~3,000+ | ±$0.30 | ±$0.05 | ✓ EXCELLENT — current demo, cleanest yet |

### Key insight: Phase 6 is current and clean

User uploaded a fresh BC CSV on 2026-04-28; per-minute comparison vs MT4 confirmed `mean(BC-MT4) = +$0.05`, exact bid-ask spread level. Apparent daily-mean "drift" on partial-coverage days (Apr 22 had 27 MT4 bars, Apr 28 had 286) is sampling artifact — daily means computed over different minute-sets disagree even when the underlying minutes match.

### Account-tag plan (NOT YET IMPLEMENTED)

Add an `account_phase` column to MT4 rows. Backtests filter to `('phase_1', 'phase_4', 'phase_6')` for clean MT4-side training data. Phase 2 + Phase 5 stay quarantined.

---

## 3. Cross-source price agreement (BC vs MT4) — fundamental finding

5,000-sample comparison at exact-same minutes:
- mean(BC - MT4) = **-$1.49** (BC systematically lower than MT4)
- median |diff| = $0.27
- p95 |diff| = $7.85
- p99 |diff| = $11.03
- 33% of overlap minutes disagree by > $1

**This is NOT a data bug.** MT4 = broker CFD (with broker spread + occasional synthetic markup); BC = NYMEX CL*0 (real exchange). They cannot be blended for ML training without producing fake "regime change" features at the source boundaries.

### Implication for ML training

**Three options, ordered by recommendation:**

1. **Train on BC only, validate/execute on MT4** — best of both worlds, what every quant shop does
2. **Train on MT4 Phase 4 + 6 only** — smaller dataset but matches live execution exactly
3. **Treat as separate symbols** (`CrudeOIL_BC`, `CrudeOIL_MT4`) — cleanest but doubles infrastructure

---

## 4. Symbol coverage matrix (post-import) — `data/quality/symbol_coverage.csv`

### Earliest data per symbol

| Symbol | Earliest | Years | Best TF | Status |
|---|---|---:|---|---|
| **MSFT** | 1986-03-13 | 40.1 | D1 only | bulk-imported D1 from history |
| **DXY** | 2008-05-04 | 18.0 | M1 deep | ⚠ STALE 393 days |
| **CrudeOIL** | 2009-08-04 | 16.7 | all TFs | ✓ deep + current |
| **TSLA** | 2010-06-29 | 15.8 | D1 only | bulk D1 since IPO |
| **VIX** | 2014-03-17 | 12.1 | M1 deep | ⚠ STALE 392 days |
| **BRENT_OIL** | 2019-01-02 | 7.3 | all TFs | ✓ current |
| **GBPJPY** | 2019-01-01 | 7.3 | all TFs | ✓ current |
| **XAUUSD** | 2019-01-01 | 7.3 | all TFs | ⚠ STALE 60 days (DUKASCOPY died) |
| **TSLA / MSFT H1** | 2023-03-15 | 3.1 | H1 only | partial bulk import |
| **USA500** | 2024-01-01 | 2.3 | all TFs | ✓ current, 2 years |
| **TSLA / MSFT M30** | 2025-11-13 | 0.5 | M30 only | partial |
| **TSLA / MSFT** (M1, M15, H4) | 2026-02-26 | 0.2 | recent only | ⚠ TOO SHORT for ML |
| **CORN / WHEAT / GASOLINE** | 2026-02-27 | 0.2 | recent only | ⚠ TOO SHORT for ML |
| **DOLLAR_INDX** | — | 0 | nothing | ✗ MISSING |

### Stale feeds — silent deaths

| Feed | Last bar | Days stale | What broke |
|---|---|---:|---|
| CrudeOIL M5 | 2024-12-06 | 508 | M1→M5 aggregator never re-ran |
| DXY M1 | 2025-03-31 | 393 | BC scrape stopped |
| VIX M1 | 2025-04-01 | 392 | BC scrape stopped |
| MSFT/TSLA M5 | 2026-02-10 | 77 | Partial M5 ingest stopped |
| XAUUSD all TFs | 2026-02-27 | 60 | DUKASCOPY feed died |

**Root cause: nothing alerts on staleness.** Phase 5 (March 2026 crisis) ran for a month with bad MT4 data because there was no health check. Same pattern killed DXY/VIX silently a year ago.

### Multi-day suspicious gaps at M1 (after weekend/holiday filtering)

| Symbol | Multi-day gaps | Short gaps |
|---|---:|---:|
| VIX | 30 | 2,199 |
| BRENT_OIL | 17 | 1,519 |
| XAUUSD | 10 | 63 |
| DXY | 7 | 3,479 |
| GBPJPY | 7 | 44 |
| USA500 | 6 | 494 |
| TSLA, MSFT, CORN, WHEAT, GASOLINE | 4-5 each | 30-65 each |
| **CrudeOIL M1** | **0** | 378 |

CrudeOIL is the cleanest M1 stream we have. Everything else has work.

---

## 5. Aggregation layer is broken

| TF | BC | MT4 | Issue |
|---|---:|---:|---|
| M1 | 5.6M | 106k | ✓ both sources |
| M5 | 442k | **0** | BC stale since Dec 2024; MT4 never aggregated |
| M15 | **0** | 377k | BC never aggregated; MT4 is a SEPARATE legacy bulk import (not from M1) |
| H1 | similar | similar | likely same |
| H4 | similar | similar | likely same |
| D1 | partial | partial | likely same |

**MT4 M15's 377k bars is suspicious** — MT4 M1 only has 106k bars. M1→M15 aggregation should yield ~7k M15 bars, not 377k. The 377k is a separate legacy bulk import from when MT4 was first wired up, with its own undocumented account/broker mix. **Cannot be trusted for backtesting.**

### Fix

1. Audit & quarantine the 377k legacy MT4 M15 (move to `market_data_legacy_mt4_m15` or hard-delete after confirmation)
2. Drop stale BC M5 (442k rows, missing recent BC fills)
3. Run **chunked** M1→M5/M15/H1/H4/D1 aggregator per source per month (the previous one OOM'd; needs ~120 monthly chunks at ~10s each)

---

## 6. Source consistency architecture (DECISION)

**Decision: BC = canonical historical source for ALL instruments × ALL timeframes; MT4 = live streaming only.** Drop DUKASCOPY and CSV legacy sources for non-FX (FX still needs DUKASCOPY because BC FX quotes are provider-dependent).

### Symbol mapping caveats (CRITICAL)

| MT4 symbol | What it is | BC equivalent | Same instrument? |
|---|---|---|---|
| CrudeOIL | CFD on WTI front | `CL*0` | Close (cents apart) |
| BRENT_OIL | CFD on Brent | `BZ*0` | Close |
| GASOLINE | CFD on RBOB | `RB*0` | Close |
| WHEAT | CFD on ZW | `ZW*0` | Close |
| CORN | CFD on ZC | `ZC*0` | Close |
| **USA500** | CFD on S&P 500 (cash or future?) | `$SPX` cash OR `ES*0` futures | **DIFFERENT** — basis $5-10 |
| **XAUUSD** | Spot gold | `GC*0` futures | **DIFFERENT** — futures-spot basis $10-30 |
| GBPJPY | Spot FX | `^GBPJPY` (BC's quote) | provider-dependent |
| DXY | Cash dollar index | `$DXY` | Same |
| VIX | Cash VIX | `$VIX` | Same |
| TSLA, MSFT | Stock CFD | TSLA, MSFT (NASDAQ) | provider-dependent CFDs vary |

**For USA500 / XAUUSD, the structural offset means you cannot blend MT4 and BC as one continuous price.** Keep them as separate `source` rows; pick the right one per use case.

### Barchart Premier rate limit

**250 file downloads / day.** Full intraday backfill at scale:

| Tier | Files | Days at cap |
|---|---:|---:|
| D1 (1 file/symbol) | 174 | <1 |
| H4 (1 file/symbol) | 174 | <1 |
| H1 (~3 chunks) | 522 | 2-3 |
| M30 (~3 chunks) | 522 | 2-3 |
| M15 (~5 chunks) | 870 | 4 |
| M5 (~15 chunks) | 2,610 | 11 |
| M1 stocks (~10 chunks, capped 6-12mo) | 800 | 4 |
| M1 futures (full ~290 chunks for 16yr) | 8,700 | **35** |
| **Total full backfill** | **~14,000** | **~56 days** |

Full M1 backfill is a 2-month project. Need to prioritize.

---

## 7. Phased plan to BC-canonical

### Phase 0 — `bc_symbol_universe` table (~30 min)

Schema:
```sql
CREATE TABLE bc_symbol_universe (
  mt4_symbol     text PRIMARY KEY,
  bc_symbol      text NOT NULL,
  bc_url_path    text NOT NULL,
  bc_profile     text NOT NULL,   -- futures_continuous|stock|etf|forex|index_cash
  timezone       text NOT NULL,
  earliest_m1    date,
  earliest_d1    date,
  notes          text
);
```

### Phase 1 — Extend scraper (1 day)

Refactor `scripts/scrape_barchart_gaps.py` to dispatch on `bc_profile`. Add URL templates for stocks (`/stocks/quotes/`), ETFs/indices (`/etfs/quotes/`), forex (`/forex/quotes/`). The current futures profile is fully working post the V9-hardening + anti-bot dance fixes.

### Phase 2 — Tier 1 backfill (~3 days)

All 174 symbols × {D1, H4, H1} = 870 files = 3 days at cap.
Result: deep daily/hourly coverage on every instrument. Sufficient for swing/position strategies and most ML feature engineering.

### Phase 3 — Tier 2 backfill (~10 days)

All 174 × {M30, M15} + top-30 × M5 + top-10 × M1.
Result: minute-level coverage on the actively-traded subset.

### Phase 4 — Daily refresh cron (~50 files/day continuous)

Daily job pulling last 24-48h per symbol/TF. Costs ~50 files/day, leaves 200 budget for ad-hoc deeper backfills. **Prevents the silent-feed-death pattern entirely.**

### Phase 5 — Source cleanup

- DUKASCOPY → migrate to BC where possible (forex stays mixed; spot gold stays separate from futures)
- Legacy CSV TSLA imports → replace with BC
- Tag MT4 rows with `account_phase` (phase_1..phase_6)

### Phase 6 — MT4 streaming hardening (separate)

- EA heartbeat + auto-reconnect
- Catch-up handshake on reconnect (request missing minutes from MT4 history)
- Daily reconciliation: cross-check today's MT4 vs broker-history dump
- Anomaly detector: reject 5σ+low-volume bars (signal of stale tick)
- Eventually: tick-level capture for full reconstructibility

### Pending decisions before Phase 0

1. **Top 30 actively-traded symbols** — get M5 + M1 priority. Rest get H1/D1 only.
2. **Spot vs futures for USA500 / XAUUSD** — maintain BOTH (`$SPX` + `ES*0`, `XAU=` + `GC*0`) or futures-only?

---

## 8. Scripts created this session

In `RiseTraderMVP/scripts/`:

| Script | Purpose |
|---|---|
| `scrape_barchart_gaps.py` | Hardened to V9-parity + anti-bot unlock dance (Today click + clear-both-dates + hard reload + storage wipe). 4-strategy day-click commit (native → ActionChains → keyboard → JS native setter). Multi-attempt picker open with retries. Files name `SYMBOL_TF_YYYYMMDD_YYYYMMDD.csv`. |
| `import_barchart_csvs.py` | Fixed: now accepts Barchart's `Latest` column. Fixed row-counter bug (was reporting last-batch count instead of total). |
| `validate_post_import.py` | 6-step post-import validation: per-source counts, per-gap fill verification, cross-source overlap, gap recompute, OHLC integrity, summary verdicts. |
| `analyze_mt4_segments.py` | Daily-resolution MT4-vs-BC offset analysis. Detects phase boundaries via changepoint heuristics. Outputs daily CSV + segments CSV + JSON. |
| `analyze_symbol_coverage.py` | Comprehensive per-(symbol,timeframe) coverage report. Classifies gaps as weekend/holiday/daily_break/suspicious. Knows US futures+equities holiday calendar 2008-2030. Outputs symbol_coverage.{json,csv} + symbol_gaps_top.csv. |

In `RiseTraderMVP/data/quality/`:

| File | Contents |
|---|---|
| `gap_report.json` / `.md` | Pre-import gap audit (45 suspicious gaps in CrudeOIL M1, of which 10 were real fillable gaps) |
| `post_import_validation.json` | Full 6-step validation report; PASS on 4, REVIEW on cross-source-agreement and boundary-stitch (both = real broker-vs-NYMEX, not bugs) |
| `mt4_analysis.json` / `mt4_daily.csv` / `mt4_segments.csv` | Daily MT4-vs-BC offsets + segment characterization |
| `symbol_coverage.json` / `.csv` | Per-(symbol,tf) earliest, latest, gap classification |
| `symbol_gaps_top.csv` | Top 200 suspicious gaps across all symbols |
| `fresh_bc_vs_mt4_daily.csv` | Daily comparison from the Apr 28 fresh BC CSV upload |

---

## 9. What's next (priority order)

1. **`scripts/check_staleness.py`** + cron — 30 lines, alerts on any symbol with `days_stale > 2`. **Highest ROI of anything pending.** Without it we'll be back here in 6 months.
2. **Restart DXY + VIX feeds** with 13-month BC backfill. Critical regressors for oil model.
3. **XAUUSD 60-day backfill**.
4. **Chunked M1→M5/M15 aggregator** (per-source, per-month, no OOM). Rebuild CrudeOIL M5/M15 first as proof.
5. **Quarantine 377k legacy MT4 M15**.
6. **Tag MT4 rows with `account_phase`**.
7. **Phase 0+1 of BC-canonical plan**: `bc_symbol_universe` table + scraper profile dispatch.

After 1-7, the system has consistent training data, no silent feed deaths, MT4 phase-aware backtesting, and a clear path to full BC-canonical coverage.

---

## 10. Carried forward from prior session

- Task #20: Rebalance SYMBOL_WEIGHTS (value_area dominant per 60-day backtest)
- Task #16: Persist BRENT_OIL / USA500 / GBPJPY XGBoost models
- Live trading items still pending in earlier memory `2026-04-21-data-quality-and-barchart-fill.md`
