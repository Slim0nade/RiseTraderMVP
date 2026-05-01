# MEGA PROMPT — RiseTraderMVP: Close the Loop → Cross-Asset Features → Nightly Retrain
# Date: April 30, 2026
# Phase: 6 (post-Phase 5 baseline; assumes 6/6 fakes eliminated, premium-aware data metadata work landed)
# Version: V2 (negotiated cuts after review — see CHANGELOG)
# Delegation: PARALLEL agents on SHARED TREE — NO worktrees (PHASE5 lesson: merging worktrees = nightmare)

---

## CHANGELOG (V1 → V2)

V1 had 16 tasks across 4 workstreams running in parallel. Review correctly flagged that as a re-run of the parallel-rigor pattern that produced the loop-drought in the first place. V2 cuts to **11 tasks** with **explicit sequential gating** between workstreams.

**Cut from V1 (deferred to Phase 7):**
- **D3** Bayesian challenger spawner — premature; nightly retrain must work first
- **D4** Auto-retire when degraded — dangerous to automate before observing one full champion-degradation-retire cycle manually
- **D1** Leaderboard widget UI — replaced by a SQL view (`v_strategy_leaderboard`) that covers 80% of the value with no UI work
- **C2 multi-symbol** Optuna search — Phase 6 trains XGBoost challenger on **CrudeOIL only**. BRENT_OIL and USA500 land in Phase 7

**Sharpened from V1:**
- **A1 thresholds:** paper 0.35 / live 0.60 (was 0.40 / 0.60). Wider funnel during validation; live unchanged
- **A1 hard-assert:** `live_threshold ≥ paper_threshold + 0.20` (was 0.10)
- **A→B explicit gate:** Workstream B does not start until A delivers ≥ 7 resolved trades/week/symbol for 7 consecutive days. <5 = halt and diagnose
- **A2 closing rule:** when 6th paper signal fires for a symbol already at the 5-position cap, **skip the new signal** (do not FIFO-evict — preserves SL/TP integrity of existing positions); log `signal_skipped_concurrency_cap` for monitoring
- **B1 scope:** features computed only for the **3 live symbols** (CrudeOIL, USA500, GBPJPY) + their cross-asset proxies (DXY, VIX, BRENT for crude). 8 idle symbols defer to Phase 7
- **B1 NULL handling:** if `account_phase` is NULL (migration 014 not applied), the one-hot block is **dropped from the feature vector entirely** — no imputation, no zero-filling
- **C3 promotion gate:** Phase 6 mode is **recommendation only**, manual `lead` approval required for promotion. Auto-promote moves to Phase 7
- **D2 mutex:** nightly retrain skips and alerts if previous night's job has not posted `nightly_retrain_complete` within 23h

**Baseline clarification:** "Premium-aware data work landed" in V1 was muddy. Precise truth (April 30, 2026):
- ✅ MT4 phase **analysis** complete (6 phases, statistically validated as structural premiums)
- ✅ `2026-04-29-mt4-broker-premium-and-correct-training-architecture.md` memory written
- ✅ Migration 014 (`mt4_account_phases` table + `market_data_with_phase` view) **built**, model + repository **built**
- ❌ Migration **NOT applied to production DB**
- ❌ Backtest / training / live execution paths **not threaded** through `source` or `account_phase`
- **Decision:** apply migration 014 during Phase 6 **only after** Workstream A is green AND **only if** Task B1 wires the feature

---

## CRITICAL: AGENT DELEGATION RULES (CARRY OVER FROM PHASE5)
- ALL agents work on the SAME repo clone — NO worktree isolation
- Each agent works on its own BRANCH off `main`, merged back via PR
- Agents run IN PARALLEL **only within a workstream**, not across workstreams (V2 discipline)
- `lead` (Opus, plan-only) orchestrates — delegates, reviews, approves; **NEVER codes**
- Use the **EXISTING** agent configs in `.claude/agents/`: `quant-dev`, `risk-eng`, `mcp-verifier`, `ml-trainer`, `reviewer`, `spread-builder`, `flow-detector`
- **DO NOT create new agent definition files for this phase** — the 8-agent core covers every workstream below
- ALL fakes hooks enforced: `scripts/validate-no-fakes.sh` (PostToolUse on Edit|Write)
- ALL commits need `[integration-pass]` from `mcp-verifier` (TaskCompleted hook)
- 3-tier testing required: unit → integration (real candles) → e2e (paper account)
- NO mock data, NO `unittest.mock`/`MagicMock`/`@patch()` for MT4/MCP/market_data interactions
- File ownership boundaries from `docs/file-ownership.md` are HARD constraints — cross-cutting changes need `lead` approval + `reviewer` sign-off

---

## CURRENT BASELINE / OPERATIONAL TRUTH (April 30, 2026)

### What works
- **6/6 fakes eliminated** ✓ (ATR, ML score, ML confidence, correlation, VaR, Kelly inputs)
- **ML Reversal CrudeOIL_H1 backtest:** +156.62% return, Sharpe 12.63, PF 4.25, Win Rate 79.37%, Max DD −16.01%
- **Value Area (current best backtest):** +208.94% return, Sharpe 16.94
- **Database:** 13.5M market_data candles across 11 instruments; M5/M15/H1/H4/D1 aggregator validated
- **MT4 phase analysis complete:** 6 phases statistically validated as **structural broker premiums** (P2 r²=0.70 vs price level, lag-1 autocorr +0.79). NOT corrupt data
- **Account:** $7,403 (started $400)

### What's broken (the operational truth)
- **Live model F1: 0.089** (peak=0.090, valley=0.143) — model is dead in production
- **Paper signals last 17 days: 2** — the loop is producing essentially zero trades
- **`_signal_threshold = 0.45` and `_min_confidence = 0.45`** in `src/services/live_trading_service.py:691-692` are HARDCODED, no paper/live split
- **Current live signals (snapshot):** GBPJPY 0.415, USA500 0.257, CrudeOIL 0.037 — only GBPJPY would record at threshold 0.40; even at 0.35, USA500 + CrudeOIL stay silent in flat conditions
- **No paper auto-resolve** — paper signals stuck open indefinitely → no learning feedback
- **No signal tagging** — we cannot tell which model version, regime, or account_phase produced a trade
- **Migration 014 BUILT BUT NOT APPLIED** — defer until loop closes (see CHANGELOG)
- **Single-symbol features only** — `reversal_features.py` produces 43 features, none cross-asset

### Strategic verdict (from this session's review, ratified)
> "Architecturally complete, operationally silent. We've been building parallel rigor without closing the loop."

**Phase 6 mission: close the loop FIRST, layer sophistication SECOND, automate THIRD.**

---

## ERRORS TO AVOID (LEARNED THIS SESSION — DO NOT REPEAT)

1. **Premature architectural scaffolding.** Building phase tagging migration + model + repository before the loop produces trades. Result: parallel rigor with zero output. **Rule: every workstream below must trace to either (a) more trades being resolved per week or (b) measurable model improvement on resolved trades.**
2. **"Bad data" misdiagnosis.** Calling MT4 Phase 2 / Phase 5 "dirty, drop them" without statistical tests. Reality: structural broker premiums, fully usable for training. **Rule: any decision to exclude data must show p-value, autocorrelation, or r² evidence.**
3. **Rule 4 over-conservatism.** "Spread widens → pull back / pause entries." Reality: those are exactly the moments we want to trade with conviction overrides. Correct posture: **NYMEX-anchored stops + spread-volatility-scaled sizing**, not pulled entries.
4. **Container over-engineering.** Reaching for new Docker workers when an asyncio background task in the existing FastAPI process suffices. **Rule: prefer in-process asyncio. Justify any new container with measured contention or isolation requirement.**
5. **Hardcoded ML values regression.** `score = 0.5 + features[0]*0.3` and confidence=0.75 were the original sin. **Rule: `validate-no-fakes.sh` must pass on every PR. Any new ML scoring path passes through a calibrated model output or skips entirely.**
6. **Worktree merging.** PHASE5 explicitly rejected this. **Rule: shared tree, branches off `main`, PR merges. Period.**
7. **Skipping the Karpathy floor.** Jumping straight to XGBoost+Optuna without a Ridge baseline. Without a baseline, we cannot tell whether a complex model is winning on signal or on overfit. **Rule: every champion candidate ships with a Ridge floor in the same MLflow experiment.**
8. **Backtest bliss / live drought disconnect.** +156% backtest, F1=0.089 live. The gap is real and is mostly threshold + label distribution + regime mismatch. **Rule: every model artifact must be evaluated on a paper-mode trading-KPI dashboard, not just F1.**
9. **NEW (V2): Big-bang parallel plans don't ship.** PHASE5 cadence at 16 tasks across 4 simultaneous workstreams was painful and exited late. V2 cuts to 11 tasks with explicit gates. **Rule: A→B gate is a hard checkpoint. Do not start B until A produces measurable trade flow.**
10. **NEW (V2): Automating before observing.** Auto-retire and adaptive challenger spawning sound elegant on paper. They are also the most error-prone code paths if the human team has never watched a single full champion-degrades-and-gets-retired cycle play out. **Rule: Phase 6 retains manual approval on every promotion and every retire decision. Auto- moves to Phase 7.**

---

## TARGET (PHASE 6 EXIT GATE)

All four must hold for ≥ 14 consecutive days before declaring Phase 6 complete:

| # | Metric | Threshold | Why |
|---|--------|-----------|-----|
| 1 | Resolved paper trades / week / symbol | ≥ 10 | Loop is alive |
| 2 | Champion model trading-PF (paper) | ≥ 1.3 | Model has edge after costs |
| 3 | Champion vs Ridge baseline trading-PF delta | ≥ +0.2 | Sophistication is paying for itself |
| 4 | Nightly retrain runs unattended for 7 nights | yes | Loop is self-sustaining (with manual promotion gate) |

**If we hit (1) but not (2):** stop adding features, fix labeling.
**If we hit (2) but not (1):** thresholds are still too tight; widen paper.
**If we hit (1) + (2) but not (3):** the complex model is overfit; revert to Ridge as champion.
**If we hit (1)+(2)+(3) but not (4):** finish the orchestrator before claiming Phase 6.

---

## WORKSTREAM A — LOOP THROUGHPUT (UNBLOCK SIGNALS)
**Owners:** `risk-eng` (lead), `quant-dev` (support)
**Branch root:** `phase6/loop-throughput`
**Why first:** without resolved trades, every other workstream is blind. This is the critical path.

### Task A1 — Split paper/live thresholds
**Branch:** `phase6/threshold-split`
**Owner:** `risk-eng`
**Files:** `src/services/live_trading_service.py:691-692`, `config/risk.yaml` (or equivalent)
**Scope:**
1. Replace hardcoded `_signal_threshold = 0.45`, `_min_confidence = 0.45` with mode-aware values:
   - **Paper:** `signal_threshold = 0.35`, `min_confidence = 0.35`  *(V2: was 0.40 — wider funnel during validation)*
   - **Live:** `signal_threshold = 0.60`, `min_confidence = 0.60`
2. Read mode from existing `ENABLE_PAPER_TRADING` / `ENABLE_LIVE_TRADING` env flags
3. Expose via `/api/admin/thresholds` GET endpoint for observability
4. Hard assert: `live_threshold >= paper_threshold + 0.20` (V2: anti-fat-finger gap widened from 0.10)
**Done when:** paper backtest replays the last 17 days and produces ≥ 30 signals (vs current 2), live config unchanged, integration test asserts the gap.

### Task A2 — Multi-paper-per-symbol with explicit closing rule
**Branch:** `phase6/multi-paper`
**Owner:** `risk-eng`
**Files:** `src/services/live_trading_service.py`, `src/risk/`
**Scope:**
1. Allow up to **5 concurrent paper positions per symbol** (configurable, default 5); live remains capped at 1 per symbol
2. Enforce 2% account-risk cap **per position** AND ≤ 8% aggregate per symbol in paper mode
3. Each paper position gets independent SL/TP — no shared management
4. **Closing rule (V2):** if a 6th paper signal fires while symbol is at the 5-position cap, **skip the new signal** — do **NOT** FIFO-evict (would invalidate the SL/TP discipline of existing positions). Log `signal_skipped_concurrency_cap` event with `(symbol, candidate_score, oldest_position_age, oldest_position_unrealized_pl)` for monitoring
5. ATR, correlation, Kelly inputs all stay real — no fakes regressions
**Done when:** integration test confirms 5 simultaneous paper positions on CrudeOIL with independent stops, total exposure ≤ 8%, and the 6th-signal-skip path emits the monitoring event.

### Task A3 — Signal tagging (every signal, no exceptions)
**Branch:** `phase6/signal-tagging`
**Owner:** `quant-dev`
**Files:** `src/database/models/decision_log.py`, `src/database/repositories/decision_log_repository.py`, signal-emitter call sites
**Scope:**
1. Every emitted signal logs: `strategy_version`, `model_artifact_hash`, `regime` (from RegimeDetectionAgent), `feature_hash` (sha256 of feature vector), `account_phase` (NULL if migration 014 not yet applied — column reserved)
2. Add columns to `decision_log` via reversible Alembic migration (number after the highest currently in `versions/`)
3. Backfill existing logs with `strategy_version='legacy'`, others NULL
**Done when:** new signals carry all 5 tags; query `SELECT strategy_version, COUNT(*) FROM decision_log GROUP BY 1` returns at least one non-legacy row from a live run.

### Task A4 — 24-hour paper auto-resolve watchdog
**Branch:** `phase6/paper-watchdog`
**Owner:** `risk-eng`
**Files:** `src/services/paper_resolution_service.py` (NEW), wired into FastAPI startup as asyncio task (per error-to-avoid #4: in-process asyncio, no new container)
**Scope:**
1. Every 5 minutes, scan paper positions older than 24h with no SL/TP hit
2. Resolve at current market price, tag `resolution_reason='watchdog_24h'`
3. Update `trading_history` with realized P&L
4. Emit `paper_resolved` event for downstream learning loop
**Done when:** unit test simulates a 25h-old paper position and asserts auto-resolution; integration test on real paper account confirms.

### Task A5 — Daily throughput-monitor script
**Branch:** `phase6/throughput-monitor`
**Owner:** `mcp-verifier`
**Files:** `scripts/check_loop_throughput.py` (NEW)
**Scope:**
1. Print last-7-day rollup: signals emitted, signals filtered (with reason), positions opened, positions resolved (by reason: SL/TP/watchdog), realized P&L per symbol
2. Print A→B gate status: ✅ if ≥7 resolved/week/symbol for 7 consecutive days; ⚠️ if 5-6/week/symbol; ❌ if <5/week/symbol
3. Alert (exit code 1) if any symbol at ❌ status
4. Wire into a daily cron line in `scripts/cron/daily_health.sh` (commented; user adds to crontab manually)
**Done when:** script runs to completion in <5s on the live DB, output shows correct counts + gate status, exit code reflects threshold breach.

### A — Done When
- All 5 tasks merged to `main` with `[integration-pass]` tags
- 7-day live paper run produces ≥ 70 resolved trades aggregated across the 3 live symbols
- `decision_log` shows tagged signals from at least 3 distinct `strategy_version` values

---

## ⛔ A → B GATE (V2: EXPLICIT BLOCKING CHECKPOINT)

**Workstream B does not start until ALL conditions hold:**
1. Tasks A1–A5 merged to `main`
2. **For 7 consecutive days**, `scripts/check_loop_throughput.py` reports ≥ 7 resolved trades/week/symbol for each of the 3 live symbols
3. `validate-no-fakes.sh` passes on `main`

**If after 7 days any symbol is below 5/week/symbol:** halt B/C/D, diagnose. Likely causes (in order of probability):
- Threshold still too tight → re-tune A1 to paper 0.30
- Strategy logic disagreement (signal sources never converge at any threshold) → investigate signal source diversity
- Regime mismatch (current regime doesn't fit any of our strategies) → spawn `flow-detector` to characterize current regime

**If a symbol is between 5–6/week/symbol:** B can start, but flag the symbol for B1 priority (its features get computed first).

**Ownership of the gate:** `lead` reviews the throughput script output every Monday during Phase 6. `lead` decides green/amber/red.

---

## WORKSTREAM B — FEATURE + LABEL PIPELINE (FEED THE LOOP)
**Owners:** `quant-dev` (lead)
**Branch root:** `phase6/features`
**Prereq:** A→B gate green.

### Task B1 — Cross-asset feature pipeline (SCOPED TO 3 LIVE SYMBOLS)
**Branch:** `phase6/cross-asset-features`
**Owner:** `quant-dev`
**Files:** `src/ml/features/cross_asset_features.py` (NEW), `src/ml/features/reversal_features.py` (extend, do not replace)
**Scope (V2: scoped):** Tier-1 features pulled from existing `market_data` (no new ingest). Computed for:
- **CrudeOIL_H1** uses proxies: DXY, VIX, BRENT
- **USA500_H1** uses proxies: VIX, DXY, USA500-internal-breadth-proxy (if available, else skip)
- **GBPJPY_H1** uses proxies: DXY, VIX

Feature blocks:
1. `dxy_zscore_20`, `dxy_return_1h`, `dxy_return_24h`
2. `vix_level`, `vix_zscore_20`, `vix_regime` (low/mid/high based on quantile)
3. `brent_wti_spread`, `brent_wti_spread_zscore_20` (CrudeOIL only)
4. `usa500_return_1h`, `usa500_return_24h`, `usa500_regime` (trend/range/breakout) (CrudeOIL + GBPJPY only)
5. `account_phase` one-hot — **V2 NULL handling: if `account_phase` is NULL (migration 014 not applied), the entire one-hot block is OMITTED from the feature vector. No imputation, no zero-fill, no dead features.** Feature vector length is variable; `feature_set_version` tag tracks the variant
6. **Single source of truth rule:** `compute_features_from_ohlcv()` remains canonical; new fn `compute_cross_asset_features(symbol, ts, lookback)` joins via timestamps
7. Cache: feature vectors keyed by `(symbol, ts, feature_set_version)` in Redis with 1h TTL
8. **Phase 7 deferred:** features for the 8 idle symbols (BRENT_OIL traded as a proxy is fine; trading BRENT directly is Phase 7)
**Done when:** for any (symbol, timestamp) in {CrudeOIL_H1, USA500_H1, GBPJPY_H1} the feature vector is reproducible byte-for-byte; integration test on 100 random timestamps from 2025-Q4 confirms; NULL-`account_phase` path explicitly tested.

### Task B2 — ForwardReturnLabeler
**Branch:** `phase6/forward-return-labeler`
**Owner:** `quant-dev`
**Files:** `src/ml/labeling/forward_return_labeler.py` (NEW); leave `zigzag_labeler.py` in place for backward compat
**Scope:**
1. Label = sign of forward log-return at horizon ∈ {1h, 4h, 24h}
2. Continuous and 3-class versions: `{up, flat, down}` with flat band = ±0.5 × ATR(20)
3. Class balancer that does NOT use SMOTE for time-series (use class weights instead — SMOTE leaks across time folds)
4. Cost-aware variant: net of typical broker spread (use account_phase pct_premium if available)
5. Backwards-compat shim that lets existing training pipelines opt in via `--labeler=forward_return` flag
**Done when:** unit test verifies that labeling a known synthetic series produces the expected label distribution; end-to-end run produces a labeled dataset on CrudeOIL_H1 2024-2025 with class balance documented.

### Task B3 — M1→{M5,M15,H1,H4,D1} aggregator with `--validate` (FINISH, DO NOT REDO)
**Branch:** `phase6/aggregator-validate`
**Owner:** `quant-dev`
**Files:** `scripts/aggregate_timeframes.py` (extend the existing in-progress work from earlier this session), `tests/integration/test_aggregator_parity.py` (NEW)
**Scope:**
1. **V2 framing:** earlier in this session we partially scoped this. **Finish the existing branch — don't redo from scratch.** Pull whatever is already merged or in a draft branch, extend
2. `--validate` flag: pulls Barchart M5/H1 reference files (already downloaded earlier this session), aggregates from M1, asserts cent-level parity (tolerance: ≤ 0.01 USD per OHLC field)
3. Report mismatches with `(symbol, timeframe, ts, field, expected, actual, diff)` rows
4. Run for **all 11 instruments** × {M5, M15, H1, H4, D1} (this is a one-time validation — fine to cover all symbols even though we're only training on 3)
**Done when:** validation report shows ≥ 99.9% parity per (symbol, TF) pair; mismatches enumerated and explained (broker rounding vs feed difference).

### B — Done When
- B1 + B2 + B3 merged to `main` with `[integration-pass]`
- Cross-asset feature vector reproducible for the 3 live symbols
- Forward-return labels available end-to-end on CrudeOIL_H1
- Aggregator parity report attached to PR

---

## WORKSTREAM C — CHAMPION MODEL (KARPATHY DISCIPLINE)
**Owners:** `ml-trainer` (lead, Opus), `mcp-verifier` (validator)
**Branch root:** `phase6/champion`
**Prereq:** B1 + B2 merged. Begin C1 the day B1 lands; do not wait for B3.

### Task C1 — Ridge baseline (THE FLOOR)
**Branch:** `phase6/ridge-baseline`
**Owner:** `ml-trainer`
**Files:** `src/ml/models/ridge_baseline.py` (NEW), `mlflow` experiment `phase6_champion_search`
**Scope:**
1. Closed-form Ridge regression on forward 1h log-return, 43 single-symbol features + cross-asset features from B1
2. Walk-forward CV: 8 folds, 2024-01 → 2025-12 train, 2026-01-Q1 holdout
3. Log: in-sample R², OOS R², direction accuracy, **trading-KPIs (PF, Sharpe, Calmar, Sortino) computed on the holdout via mcp-verifier's backtest harness**
4. Ablation: drop each feature group (price, indicators, cross-asset, account_phase if present) and re-train; rank features by Sharpe-loss when removed
5. Save artifact + metadata.json with `feature_set_version`, `train_window`, `test_window`, `git_sha`
**Done when:** MLflow run logs all KPIs; ablation table committed to `docs/phase6/ridge_ablation.md`.

### Task C2 — XGBoost + Optuna challenger (CRUDEOIL ONLY)
**Branch:** `phase6/xgb-optuna-crude`
**Owner:** `ml-trainer`
**Tools:** `train_reversal_models`, `optimize_strategy`
**Scope (V2: scoped):**
1. Bayesian search over: `max_depth ∈ [3,8]`, `lr ∈ [0.01,0.2]`, `n_estimators ∈ [100,1000]`, `min_child_weight ∈ [1,10]`, `subsample ∈ [0.6,1.0]`, `colsample_bytree ∈ [0.6,1.0]`, `reg_alpha`, `reg_lambda`
2. Optuna TPE sampler, 200 trials, walk-forward 8-fold inside the objective
3. Objective: maximize OOS Sharpe (NOT F1) on holdout
4. Class weighting (NOT SMOTE — see B2)
5. **CrudeOIL_H1 only.** BRENT_OIL_H1 and USA500_H1 land in Phase 7
6. Save all top-10 trial artifacts; promote candidate to challenger slot
7. **V2 acceptance:** team must agree upfront that this can legitimately fail (XGBoost may not beat Ridge by ≥ 0.5 OOS Sharpe with stat-sig). If it fails, **Ridge becomes champion** and Phase 6 still ships
**Done when:** challenger beats Ridge baseline on OOS Sharpe by ≥ 0.5 with stat-sig p < 0.05 (paired t-test across folds), OR fails the gate and is rejected with reason logged. MLflow run shows full study either way.

### Task C3 — Champion/challenger promotion gate (RECOMMENDATION-ONLY MODE FOR PHASE 6)
**Branch:** `phase6/promotion-gate`
**Owner:** `mcp-verifier`
**Files:** `scripts/promote_challenger.py` (NEW), `src/services/model_registry_service.py` (extend)
**Scope (V2: manual approval):**
1. Gate logic (unchanged from V1):
   - Challenger must beat current champion on **paper trading-PF** by ≥ 0.2 over a rolling 14-day window
   - Stat-sig: bootstrap 1000 resamples, 95% CI of (challenger PF − champion PF) must exclude 0
   - Drawdown sanity: challenger max-DD ≤ 1.5 × champion max-DD
2. **V2 mode:** script outputs a `promotion_recommendation.json` with the gate evaluation (passed/failed, all stats). It does NOT auto-promote. `lead` runs `python scripts/promote_challenger.py --apply` after manually reviewing
3. On approval: update `model_configurations` table, emit `champion_promoted` event, archive old champion (do not delete — kept for ablation)
4. On rejection: log `challenger_rejected` event with reason, ml-trainer retries with adjusted search space
5. **Phase 7 path:** flip the `--apply` default from off to on once we've watched 3 manual cycles
**Done when:** dry-run promotion script on synthetic data passes; live run produces a recommendation file; `lead` performs at least 1 manual approval-or-rejection cycle.

### Task C4 — MLflow trading-KPI integration
**Branch:** `phase6/mlflow-trading-kpis`
**Owner:** `mcp-verifier`
**Files:** `src/ml/evaluation/trading_kpi_logger.py` (NEW)
**Scope:**
1. Custom MLflow autolog hook that, after training, runs the model through the existing backtest harness on the holdout window
2. Logs as MLflow metrics: `trading_pf`, `trading_sharpe`, `trading_calmar`, `trading_sortino`, `trading_max_dd`, `trading_avg_trade_pl`, `trading_win_rate`, `trading_n_trades`
3. Logs as MLflow tags: `feature_set_version`, `labeler_version`, `train_window`, `holdout_window`, `account_phase_distribution`
4. Backtest must use same broker/spread assumptions as paper mode (no zero-cost backtests)
**Done when:** every Phase 6 MLflow run shows trading KPIs alongside ML KPIs; F1 alone is not sufficient evidence for promotion.

### C — Done When
- Ridge baseline ships with full ablation
- XGBoost CrudeOIL challenger either beats Ridge with stat-sig OR is formally rejected
- Promotion gate operational in recommendation mode; `lead` has run ≥ 1 cycle
- Every model artifact has trading-KPI sidecar in MLflow

---

## WORKSTREAM D — NIGHTLY RETRAIN ONLY (V2: SHARPLY CUT)
**Owners:** `quant-dev` (lead), `lead` (orchestration)
**Branch root:** `phase6/nightly-retrain`
**Prereq:** C1 + C3 + C4 merged.

V2 cuts D1 (leaderboard widget UI), D3 (challenger spawner), D4 (auto-retire). All three move to Phase 7. The minimum viable autonomous loop is: nightly retrain + manual promotion + SQL view for monitoring.

### Task D1-LITE — Leaderboard SQL view (replaces V1 leaderboard widget)
**Branch:** `phase6/leaderboard-view`
**Owner:** `quant-dev`
**Files:** new SQL view `v_strategy_leaderboard` via Alembic migration
**Scope:**
1. Materialized view (or regular view if performance allows) over `decision_log` + `trading_history`
2. Columns: `strategy_version`, `symbol`, `timeframe`, `account_phase` (if column populated), `n_trades_7d`, `n_trades_30d`, `pf_7d`, `pf_30d`, `sharpe_30d`, `max_dd_30d`, `avg_pl`, `hit_rate`
3. Refresh nightly via the same job that runs D2
4. **No UI work.** Operators query with `psql` or the existing API's generic query endpoint. Dashboard widget moves to Phase 7
**Done when:** view returns sane numbers for current `decision_log`; refresh completes < 30s; documented in `docs/phase6/leaderboard_view.md`.

### Task D2 — Nightly retrain cron with mutex
**Branch:** `phase6/nightly-retrain`
**Owner:** `quant-dev`
**Files:** `scripts/cron/nightly_retrain.sh` (NEW), `src/services/training_orchestrator.py` (NEW — asyncio in-process job, NOT a new container — see error-to-avoid #4)
**Scope:**
1. Runs at 02:00 UTC: pull last-30d data, retrain all active model slots (champion + challenger), evaluate via Workstream C harness
2. **V2 mutex:** before starting, check that the previous night's run posted `nightly_retrain_complete` within the last 23h. If not, **skip this night's run**, alert (Slack/email/log), and emit `nightly_retrain_skipped_stale_lock` event. This prevents stacked retrains corrupting MLflow
3. Lock file: `/tmp/nightly_retrain.lock` with PID + start_ts; cleared on completion or on detection of stale lock (> 23h old)
4. Generate promotion recommendation via C3 (does NOT auto-apply); emit `nightly_retrain_complete` event with summary (n_models, n_recommendations, alert if any flagged for promotion)
5. Failure mode: log + alert (existing alerting), do NOT silently skip non-mutex failures
**Done when:** 7 consecutive nightly runs complete with full summary in `docs/phase6/retrain_log.md`; mutex behavior tested by manually leaving a stale lock.

### D — Done When
- Leaderboard SQL view live and refreshing
- Nightly retrain cron has run unattended for 7 nights with mutex working
- `lead` has manually approved at least 1 promotion via the recommendation file

**Phase 7 territory (cut from V2):** D1 widget UI, D3 challenger spawner, D4 auto-retire, C2 multi-symbol expansion.

---

## WORKSTREAM E — CONTINUOUS REVIEW
**Owner:** `reviewer` (read-only)
**Branch:** N/A (PR comments only)
**Scope:**
1. **5-lens review on every PR:** security, performance, architecture, regression, fakes
2. Block merge if `validate-no-fakes.sh` fails
3. Block merge if `[integration-pass]` tag missing from commit message
4. Block merge if file ownership crossed without `lead` approval comment
5. Special vigilance for: hardcoded thresholds, mocked MT4/market_data, SMOTE on time-series, container-creep, premature DB migrations, **V2-specific: any code path that would auto-apply a champion promotion without `lead` approval — block it**
**Done when:** N/A — runs continuously through Phase 6.

---

## ITERATION CYCLE (CONTINUOUS UNTIL EXIT GATE)

```
NIGHTLY (autonomous after Task D2 lands):
  02:00 UTC: nightly_retrain.sh
    → mutex check (skip if stale lock)
    → ml-trainer trains champion + challenger
    → mcp-verifier evaluates via trading-KPI harness
    → promotion RECOMMENDATION written to file (no auto-apply)
    → leaderboard view refreshed
    → digest event emitted

WEEKLY (during Phase 6 dev):
  Mon 09:00 UTC: lead reads scripts/check_loop_throughput.py output + reviews promotion recommendations
    → Approve/reject pending promotions manually via `python scripts/promote_challenger.py --apply`
    → IF resolved trades / week / symbol < 7 → reopen Workstream A
    → IF champion PF < 1.3 paper → review Workstream C decisions
    → IF cross-asset features ablation says they don't help → quant-dev refines (Workstream B1)

DAILY (during Phase 6 dev):
  Engineers review: PR queue, MLflow runs, decision_log tag distribution
  reviewer signs off; mcp-verifier runs the integration suite
```

**Round-by-round flow during dev (V2: sequential, not big-bang parallel):**
```
ROUND 1 (Week 1):
  risk-eng + quant-dev: Workstream A all 5 tasks land
  reviewer: 5-lens on every PR
  EXIT: A complete, gate metrics start being measured

ROUND 2 (Week 2):
  Wait. Measure. Lead checks A→B gate every Monday.
  No B/C/D work until gate green for 7 consecutive days.

ROUND 3 (Week 3, IF A→B gate green):
  quant-dev: B1 + B2 in parallel (independent files)
  ml-trainer: C1 starts day B1 lands
  EXIT: B + C1 + C4 complete

ROUND 4 (Week 4):
  ml-trainer: C2 (CrudeOIL only) — may pass or fail; both outcomes are fine
  mcp-verifier: C3 promotion gate in recommendation mode
  quant-dev: D1-LITE (SQL view) + D2 (nightly retrain)
  EXIT: D complete

ROUND 5 (Weeks 5-7):
  Monitor exit-gate metrics. Run nightly. Promote manually.
  Phase 6 declared complete when all 4 metrics hold for 14 consecutive days.
```

---

## KEY MCP TOOLS (CARRY OVER FROM PHASE5)
- `compute_indicators` — feature computation
- `train_reversal_models` — full training pipeline
- `run_ml_backtest` — model P&L on holdout
- `run_backtest_and_wait` — strategy backtest
- `optimize_strategy` — Optuna search wrapper
- `monte_carlo_validate` — robustness testing
- `sensitivity_analysis` — param sensitivity
- `rolling_window_optimize` — walk-forward optimization
- `place_market_order` / `place_pending_order` — paper/live execution
- `get_open_positions` / `get_account_info` — monitoring
- `get_latest_candles` / `get_symbols` — data
- `submit_optimization_job` / `get_optimization_job_status` / `get_optimization_job_results` — async optimization (Feature 008)

**SSE events to subscribe to:** `job_started`, `job_progress`, `job_complete`, `job_failed`, `champion_promoted` (NEW, fired by manual approval), `challenger_rejected` (NEW), `paper_resolved` (NEW), `nightly_retrain_complete` (NEW), `nightly_retrain_skipped_stale_lock` (NEW), `signal_skipped_concurrency_cap` (NEW)

---

## SUCCESS CRITERIA (PHASE 6 EXIT)

All four sustained for ≥ 14 consecutive days:

| # | Metric | Threshold |
|---|--------|-----------|
| 1 | Resolved paper trades / week / symbol | ≥ 10 |
| 2 | Champion paper trading-PF | ≥ 1.3 |
| 3 | Champion vs Ridge baseline PF delta | ≥ +0.2 (or Ridge **is** the champion, in which case this row N/A) |
| 4 | Nightly retrain runs unattended for 7 nights with mutex working | yes |

**Plus structural:**
- 6/6 fakes still eliminated (no regression)
- Migration 014 (`mt4_account_phases`) **may** be applied during Phase 6, but only after Workstream A is green; if applied, B1 must wire the `account_phase` feature
- All 8 existing agents still in `.claude/agents/` (no new agent files)
- `validate-no-fakes.sh` passing on every commit in `main`
- Manual promotion approval workflow exercised by `lead` at least once

---

## QUICK START — SEQUENTIAL AGENT COMMANDS (V2: NO PASTE-ALL-AT-ONCE)

**V2 discipline: paste these commands one at a time, in order, waiting for `[integration-pass]` from the previous before kicking off the next within the same workstream.**

### Step 0 — Branch hygiene
```bash
git checkout main
git pull
git checkout -b phase6/integration  # cherry-pick branch for end-of-phase merges
```

### Round 1: Workstream A (Week 1)

Paste FIRST and wait for merge:
```bash
/agent risk-eng Implement Phase 6 Task A1 (paper/live threshold split). Read PHASE6_LOOP_TO_AUTONOMY_MEGA_DELEGATION.md "Task A1" section first. Branch: phase6/threshold-split. Files: src/services/live_trading_service.py:691-692, config/risk.yaml. Paper threshold = 0.35, live = 0.60. Hard assert live >= paper + 0.20. NO new fakes. Add unit test + integration test that replays last 17 days of paper signals and asserts >=30 signals fire. Commit with [integration-pass] tag from mcp-verifier.
```

Then in parallel (independent files):
```bash
/agent quant-dev Implement Phase 6 Task A3 (signal tagging in decision_log). Read Task A3. Branch: phase6/signal-tagging. New Alembic migration (number after current head). Backfill legacy. Tags: strategy_version, model_artifact_hash, regime, feature_hash, account_phase (placeholder if migration 014 not applied). Write integration test that asserts a real signal carries all 5 tags.
```

After A1 and A3 land, paste these in parallel:
```bash
/agent risk-eng Implement Phase 6 Task A2 (multi-paper-per-symbol, max 5 paper / 1 live, with 6th-signal SKIP rule — do NOT FIFO-evict). Read Task A2. Branch: phase6/multi-paper. Real ATR + Kelly + correlation only — no fakes regressions. Aggregate 8% cap per symbol enforced. Log signal_skipped_concurrency_cap event for skipped 6th signals.
```

```bash
/agent risk-eng Implement Phase 6 Task A4 (24h paper auto-resolve watchdog). Read Task A4. Branch: phase6/paper-watchdog. NEW file src/services/paper_resolution_service.py wired as asyncio task in FastAPI startup — DO NOT add a new container. Unit test on synthetic 25h-old position. Integration test on real paper account.
```

```bash
/agent mcp-verifier Implement Phase 6 Task A5 (daily throughput monitor with A→B gate status). Read Task A5. Branch: phase6/throughput-monitor. New script scripts/check_loop_throughput.py + commented cron line in scripts/cron/daily_health.sh. Output must include A→B gate status (✅/⚠️/❌). Exit code 1 when any symbol at ❌. Run on the live DB and paste the output in the PR description.
```

### Round 2: WAIT (Week 2)

**Do not start B/C/D yet.** `lead` runs the throughput monitor every Monday and reports the A→B gate status.

```bash
/agent lead Run the A→B gate check. Execute scripts/check_loop_throughput.py. Read the gate status. If green for 7 consecutive days, approve Round 3 to start. If amber, flag the symbols for B1 priority. If red, halt and diagnose with risk-eng.
```

### Round 3: Workstream B (Week 3, only after A→B gate green)

Paste in parallel (independent files):
```bash
/agent quant-dev Implement Phase 6 Task B1 (cross-asset feature pipeline, SCOPED to 3 live symbols + proxies). Read Task B1. Branch: phase6/cross-asset-features. NEW src/ml/features/cross_asset_features.py + extend reversal_features.py (do not replace). Compute features ONLY for CrudeOIL_H1, USA500_H1, GBPJPY_H1. Tier-1 features per the table in B1. **Critical V2 rule: if account_phase is NULL, DROP the entire one-hot block — no imputation, no zero-fill.** Reproducibility test on 100 random 2025-Q4 timestamps. Redis cache 1h TTL.
```

```bash
/agent quant-dev Implement Phase 6 Task B2 (ForwardReturnLabeler). Read Task B2. Branch: phase6/forward-return-labeler. NEW src/ml/labeling/forward_return_labeler.py. NO SMOTE — use class weights. Cost-aware variant uses account_phase pct_premium when available. Backwards-compat shim: --labeler=forward_return CLI flag. Leave zigzag_labeler.py in place.
```

```bash
/agent quant-dev FINISH Phase 6 Task B3 (M1→multi-TF aggregator with --validate). Read Task B3. **Pull the existing partially-scoped branch from earlier this session — do NOT redo from scratch.** Extend scripts/aggregate_timeframes.py. NEW tests/integration/test_aggregator_parity.py. Cent-level parity tolerance 0.01 USD. Run for all 11 instruments x {M5, M15, H1, H4, D1}. Attach parity report to PR.
```

### Round 4: Workstream C + D (Week 3-4, only after B1 + B2 land)

Paste C1 first (it's the floor):
```bash
/agent ml-trainer Implement Phase 6 Task C1 (Ridge baseline as the floor). Read Task C1. Branch: phase6/ridge-baseline. NEW src/ml/models/ridge_baseline.py. MLflow experiment phase6_champion_search. Walk-forward 8-fold. Log trading-KPIs (PF/Sharpe/Calmar/Sortino) on holdout via mcp-verifier harness. Ablation table: drop each feature group and measure Sharpe-loss. Commit ablation as docs/phase6/ridge_ablation.md.
```

Then C4 (autolog hook is needed by everyone):
```bash
/agent mcp-verifier Implement Phase 6 Task C4 (MLflow trading-KPI autolog). Read Task C4. Branch: phase6/mlflow-trading-kpis. NEW src/ml/evaluation/trading_kpi_logger.py. After every training run, replay holdout via existing backtest harness with paper-mode broker assumptions and log trading_pf/sharpe/calmar/sortino/max_dd/avg_trade_pl/win_rate/n_trades to MLflow. Tag with feature_set_version, labeler_version, train/holdout windows, account_phase distribution.
```

Then C2 (CrudeOIL only, accept that it may fail):
```bash
/agent ml-trainer Implement Phase 6 Task C2 (XGBoost+Optuna challenger, **CrudeOIL only for Phase 6**). Read Task C2. Branch: phase6/xgb-optuna-crude. Optuna TPE 200 trials. Walk-forward 8-fold inside objective. Objective: maximize OOS Sharpe (NOT F1). Class weighting (NOT SMOTE). Save top-10 artifacts. **Acceptance: this may legitimately fail to beat Ridge by ≥0.5 OOS Sharpe with p<0.05. If so, Ridge stays champion and Phase 6 ships anyway.** Log full study to MLflow either way.
```

Then C3 (recommendation-only mode):
```bash
/agent mcp-verifier Implement Phase 6 Task C3 (champion/challenger promotion gate, RECOMMENDATION-ONLY MODE). Read Task C3. Branch: phase6/promotion-gate. NEW scripts/promote_challenger.py + extend src/services/model_registry_service.py. 3-gate logic: paper-PF delta >=0.2 over 14d, bootstrap 95% CI excludes 0, max-DD <=1.5x champion. **Phase 6 mode: outputs promotion_recommendation.json. Does NOT auto-promote. lead runs --apply manually after review.** Auto-apply default flips ON in Phase 7.
```

Then D1-LITE and D2 in parallel:
```bash
/agent quant-dev Implement Phase 6 Task D1-LITE (leaderboard SQL view, NO UI). Read D1-LITE. Branch: phase6/leaderboard-view. New SQL view v_strategy_leaderboard via Alembic migration. Columns per spec. Refresh nightly. Operators query via psql — dashboard widget is Phase 7.
```

```bash
/agent quant-dev Implement Phase 6 Task D2 (nightly retrain cron with mutex). Read D2. Branch: phase6/nightly-retrain. NEW scripts/cron/nightly_retrain.sh + src/services/training_orchestrator.py. Asyncio in-process — DO NOT add a new container. 02:00 UTC. **V2 mutex: skip + alert if previous night's nightly_retrain_complete event hasn't fired in 23h.** Generate promotion recommendation via C3, do NOT auto-apply. Failure -> alert, never silent skip (except the documented mutex skip).
```

### Continuous: Workstream E

```bash
/agent reviewer Run 5-lens review on every Phase 6 PR. Block merge if validate-no-fakes.sh fails, [integration-pass] tag missing, or file ownership crossed without lead approval. Special vigilance: hardcoded thresholds, mocked MT4, SMOTE on time-series, container-creep, premature DB migrations, **and any code path that would auto-apply a champion promotion without lead approval — block it.**
```

### Phase gate

```bash
/agent lead Review Phase 6 exit gate. Verify all 4 success metrics held for >=14 consecutive days: (1) resolved paper trades >=10/week/symbol, (2) champion paper PF >=1.3, (3) champion-vs-Ridge PF delta >=+0.2 (or Ridge is the champion), (4) nightly retrain unattended for 7 nights with mutex working. Verify 6/6 fakes still eliminated, validate-no-fakes.sh passing, all 8 existing agents intact, manual promotion workflow exercised at least once. Decide: Phase 7 spawn vs reopen workstreams.
```

---

## FILE OWNERSHIP MAP (PHASE 6 ADDITIONS)

| Path | Owner | Notes |
|------|-------|-------|
| `src/services/live_trading_service.py` | risk-eng | A1, A2 |
| `src/services/paper_resolution_service.py` (NEW) | risk-eng | A4 |
| `src/database/models/decision_log.py` | quant-dev | A3 |
| `src/ml/features/cross_asset_features.py` (NEW) | quant-dev | B1 |
| `src/ml/labeling/forward_return_labeler.py` (NEW) | quant-dev | B2 |
| `src/services/training_orchestrator.py` (NEW) | quant-dev | D2 |
| `src/ml/models/ridge_baseline.py` (NEW) | ml-trainer | C1 |
| `src/ml/evaluation/trading_kpi_logger.py` (NEW) | mcp-verifier | C4 |
| `scripts/check_loop_throughput.py` (NEW) | mcp-verifier | A5 |
| `scripts/promote_challenger.py` (NEW) | mcp-verifier | C3 |
| `scripts/aggregate_timeframes.py` (extend) | quant-dev | B3 (FINISH, not redo) |
| `tests/integration/test_aggregator_parity.py` (NEW) | mcp-verifier | B3 |
| `scripts/cron/nightly_retrain.sh` (NEW) | quant-dev | D2 |
| Alembic migration for `decision_log` columns | quant-dev | A3 |
| Alembic migration for `v_strategy_leaderboard` view | quant-dev | D1-LITE |

Cross-cutting: any change to `live_trading_service.py` and `model_registry_service.py` in the same PR requires `lead` approval comment.

---

## DEFERRED FROM PHASE 6 (PHASE 7 TERRITORY)

V2 cuts (do not start in Phase 6):
- **D1 leaderboard widget UI** — SQL view (D1-LITE) covers it for now
- **D3 Bayesian challenger spawner** — premature; nightly retrain must work first
- **D4 auto-retire when degraded** — observe one full manual cycle before automating
- **C2 multi-symbol expansion** — BRENT_OIL_H1 and USA500_H1 challenger searches in Phase 7
- **C3 auto-apply** — flips ON in Phase 7 after 3 manual cycles observed

Other deferrals (carried from V1):
- Migration 014 APPLY — only after Workstream A is green, and only if B1 is wired to consume it
- LSTM training (Docker OOM, parked from Phase 5)
- Ensemble strategy (Phase 5 Workstream A Agent 3)
- New container deployments (asyncio in-process is the rule for Phase 6 — see error-to-avoid #4)
- Crisis-automator specialist
- Real-money live trading scaling (paper only until exit gate cleared)

---

## ENTRY POINT

**Lead**, paste this prompt to begin Phase 6:
```bash
/agent lead Begin Phase 6 V2 (close the loop -> cross-asset features -> nightly retrain). Read PHASE6_LOOP_TO_AUTONOMY_MEGA_DELEGATION.md end-to-end including the CHANGELOG. Confirm understanding of: errors-to-avoid (10 items), exit gate (4 metrics x 14 days), workstream sequencing (A first; A→B gate; then B+C; then D), 11 tasks total (V2 cut from 16). Spawn risk-eng on Task A1 immediately. Spawn quant-dev on Task A3 in parallel (independent files). Hold A2/A4/A5 until A1 lands. Hold ALL of B/C/D until A→B gate green. Daily roll-up to me until exit gate is cleared.
```

---

## REFERENCE
- PHASE5_CRUDE_OIL_MEGA_DELEGATION.md — prior format precedent
- .claude/INFORMED_FLOW_DELEGATION_PLAN.md — agent-command format precedent
- CLAUDE.md — absolute rules, no-fakes policy, file ownership, testing tiers
- .serena/memories/2026-04-29-mt4-broker-premium-and-correct-training-architecture.md — premium architecture
- docs/file-ownership.md — full ownership boundaries
