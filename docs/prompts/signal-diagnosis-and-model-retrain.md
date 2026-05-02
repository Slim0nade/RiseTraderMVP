# Sprint: Signal Diagnosis + XGBoost Retrain + Git Commit

> **Priority:** EMERGENCY — paper gate is collecting 0/50 signals despite a $15 CrudeOIL rally
> **Context:** On April 2, CrudeOIL rallied from $98 → $113 (+15%) with H1 candles of +6.3%, +2.9%, +2.5%.
> The system ran through that entire move and generated ZERO actionable signals.
> Either the regime system is correctly classifying VOLATILE and halting,
> or a bug is silently eating signals. We need to know which.
> **Constraint:** Do NOT stop the live loop. All changes hot-patchable.

---

## Task 0: EMERGENCY — Commit All Uncommitted Work (DO THIS FIRST)

**Owner:** lead
**Priority:** ABSOLUTE FIRST — 30+ files at risk, zero commits since a8814d8

30+ files from the regime system, paper validation, ML pipeline, integration tests,
config YAML, Docker config, MCP server, and candle aggregator are ALL uncommitted.
One `git checkout .` or container rebuild accident destroys 3 sprints of work.

### Steps

1. Run `git status` to see all changes.
2. Verify no `.env`, credentials, or secrets are staged.
3. Commit in logical groups:

```bash
# Commit 1: Regime system core
git add src/trading/regime/ config/regime.yaml tests/unit/trading/regime/
git commit -m "feat(regime): regime classifier + strategy router + config YAML [integration-pass]"

# Commit 2: Filters (cross-asset + trend)
git add src/trading/filters/ tests/unit/trading/filters/
git commit -m "feat(filters): cross-asset filter + trend filter enhancements [integration-pass]"

# Commit 3: Paper validation gate (the critical safety net)
git add src/services/paper_validation_service.py tests/unit/services/test_paper_validation_service.py src/services/live_trading_service.py
git commit -m "feat(paper-gate): wire PaperValidationService into live trading loop [integration-pass]"

# Commit 4: ML pipeline (regime features + training + inference)
git add src/ml/ models/
git commit -m "feat(ml): add regime features to reversal feature pipeline [integration-pass]"

# Commit 5: Integration tests
git add tests/integration/
git commit -m "test(integration): regime pipeline tests with real PostgreSQL data [integration-pass]"

# Commit 6: Infrastructure (Docker, API, MCP, scripts, candle aggregator)
git add docker/ requirements*.txt scripts/ src/api/ src/mcp/ src/database/ src/services/candle_aggregator_service.py src/services/mt4_sync_service.py
git commit -m "feat(infra): Docker config, MCP server, candle aggregator, API routes [integration-pass]"

# Commit 7: Agents + strategies + risk
git add src/agents/ src/strategies/ src/trading/risk/ src/trading/execution/
git commit -m "feat(agents+risk): agent enhancements + risk pipeline updates [integration-pass]"

# Commit 8: Docs + Serena + remaining
git add .serena/ docs/ config/mt4_config.yaml
git add -A  # catch anything remaining — review first!
git commit -m "chore: docs, Serena memories, config updates [integration-pass]"
```

4. Verify: `git status` shows clean working tree.
5. Do NOT push — just local safety commits.

### Acceptance Criteria
- [ ] All 30+ files committed
- [ ] No secrets in any commit
- [ ] `git status` is clean
- [ ] Each commit has `[integration-pass]` tag

---

## Task 1: Signal Pipeline Diagnosis (BLOCKING)

**Owner:** mcp-verifier
**Priority:** DO THIS FIRST — everything depends on understanding why 0 signals

### Step 1: Read the logs

```bash
# Get ALL regime classifications from last 48 hours
docker logs risetrader-api 2>&1 | grep "regime_classified" | tail -100

# Get ALL signal decisions (including HOLD)
docker logs risetrader-api 2>&1 | grep -E "rl_decision_log|signal_generated|regime_trading_halted" | tail -50

# Get stale candle skips
docker logs risetrader-api 2>&1 | grep "stale_candles" | tail -50

# Get cycle timing
docker logs risetrader-api 2>&1 | grep "trading_cycle_complete" | tail -20

# Get paper validation status progression
docker logs risetrader-api 2>&1 | grep "paper_validation_status" | tail -20

# Get ANY errors or warnings
docker logs risetrader-api 2>&1 | grep -iE "error|exception|traceback|warning" | tail -30
```

### Step 2: Classify the failure mode

From the logs, determine WHICH of these is happening:

**A. Regime = VOLATILE → trading halted (expected for $15 move)**
- If the first H1 candle was +$6.19 (6.3%), that's likely >3× ATR → volatile trigger
- ATR(14) for CrudeOIL H1 is typically ~$1.00-1.50. A $6.19 bar = 4-6× ATR
- This would correctly classify as VOLATILE and halt trading
- **If this is the case:** The system is WORKING CORRECTLY. A $15/day move IS volatile.
  The problem is that the system won't generate signals until volatility subsides.
  This is by design but means paper signal collection will be slow.

**B. Regime = TRENDING but strategies score below threshold**
- Momentum (10/30 MA crossover) may lag behind a sharp move
- Breakout (20-period high/low) should fire on new 20-bar highs
- Check if individual strategy scores are close to 0.6 but not crossing it

**C. Stale candles — H1 only updates once/hour**
- System runs every 5 minutes but H1 candles only change hourly
- Fingerprint check correctly skips stale candles
- Result: only ~12 real evaluations per day, not 288
- **This is expected behavior** but means 50 signals will take weeks/months

**D. Cross-asset filter rejecting signals**
- If BRENT data is missing or stale, filter may reject everything
- Check: does CrossAssetFilter have recent BRENT_OIL H1 data?

**E. Processing error silently caught**
- The `_process_symbol()` method has a broad try/except
- An import error, DB error, or computation error could silently fail

### Step 3: Report findings

Create a diagnostic report at `docs/diagnostics/signal-diagnosis-2026-04-03.md`:
- Which failure mode (A-E) explains the 0/50
- Exact regime classifications seen
- Individual strategy scores if available
- Recommendation: is this expected behavior or a bug?

### Acceptance Criteria
- [ ] All 6 log queries executed and results documented
- [ ] Failure mode identified (A, B, C, D, or E)
- [ ] Diagnostic report written with evidence
- [ ] If bug found: fix documented with specific file + line number

---

## Task 2: Signal Visibility Enhancement

**Owner:** risk-eng
**Files:** `src/services/live_trading_service.py`
**Priority:** HIGH — we need visibility into WHY signals are HOLD

### Requirements

The current logging doesn't tell us enough. Add detailed logging at these decision points:

1. **After regime classification (line ~769):** Already logs regime, ADX, Hurst, ATR ratio — GOOD.

2. **Inside `_generate_signal()` — log individual strategy scores BEFORE combining:**
   ```python
   for name, result in strategy_results.items():
       logger.info("strategy_individual_score",
                   symbol=symbol, strategy=name,
                   score=round(result["score"], 4),
                   confidence=round(result["confidence"], 4),
                   regime=regime.value)
   ```

3. **After `_combine_signals()` — log the combined score and threshold:**
   ```python
   logger.info("signal_combined_result",
               symbol=symbol,
               combined_score=round(score, 4),
               confidence=round(confidence, 4),
               threshold=strategy_config["signal_threshold"],
               min_confidence=self._min_confidence,
               passed_threshold=abs(score) >= strategy_config["signal_threshold"],
               passed_confidence=confidence >= self._min_confidence,
               action=action)
   ```

4. **When signal is HOLD — log WHY:**
   ```python
   if action == "HOLD":
       logger.info("signal_hold_reason",
                   symbol=symbol,
                   combined_score=round(score, 4),
                   threshold=strategy_config["signal_threshold"],
                   gap_to_threshold=round(strategy_config["signal_threshold"] - abs(score), 4),
                   confidence=round(confidence, 4),
                   regime=regime.value)
   ```

5. **On stale candle skip — log how old the data is:**
   ```python
   logger.info("stale_candles_skipping", symbol=symbol,
               latest_candle_time=candles_raw[-1].get("time", "unknown"),
               fingerprint_unchanged=True)
   ```

### Also while in this file — CLEAN UP:
- Remove dead import line 24: `from decimal import Decimal`
- Remove dead import line 32: `ValueAreaStrategy, ValueAreaParams`
- Remove dead import line 33: `MarketTick`

### Acceptance Criteria
- [ ] 4 new structured log entries added (strategy_individual_score, signal_combined_result, signal_hold_reason, stale candle time)
- [ ] Dead imports removed (3 lines)
- [ ] Container rebuilt and logs show new entries within 1 cycle
- [ ] Can now see exactly WHY every signal is HOLD

---

## Task 3: XGBoost Model Retrain

**Owner:** quant-dev
**Environment:** Inside Docker container with PostgreSQL access
**Priority:** HIGH — ml_reversal is dead weight (peak_f1=0.089, gated at 0.30)

### Context

`src/ml/features/reversal_features.py` already has 3 new regime features:
- `regime_adx` (line 366)
- `regime_hurst` (line 368-376)
- `regime_atr_ratio` (line 378-383)

But the deployed model at `models/reversal_classifier/CrudeOIL_H1/` was trained
2026-03-06 with only 43 features. It does NOT include the regime features.

### Requirements

1. **Pull training data from PostgreSQL:**
   ```python
   # CrudeOIL H1, 2024-01-01 to 2026-03-31
   # DB has 95,414 total CrudeOIL H1 candles (confirmed via API)
   ```

2. **Run training with regime features:**
   ```bash
   docker exec -it risetrader-api python -m src.ml.training.train_reversal_classifier \
       --symbol CrudeOIL --timeframe H1 \
       --start-date 2024-01-01 --end-date 2026-03-31
   ```
   Or invoke the MCP tool:
   ```
   train_reversal_models(symbol="CrudeOIL", timeframe="H1")
   ```

3. **Verify new feature count is 46 (43 original + 3 regime).**

4. **Evaluate results:**
   - Target: `peak_f1 >= 0.30` (clears quality gate)
   - If F1 still < 0.30:
     a. Try `scale_pos_weight` = count(class_0) / count(class_1)
     b. Reduce `max_depth` from 6 to 4
     c. Try focal loss or SMOTE oversampling for minority classes
     d. If still < 0.30 after 3 attempts: document results, keep gated, move on

5. **Update model artifacts:**
   - `models/reversal_classifier/CrudeOIL_H1/model.json` (retrained weights)
   - `models/reversal_classifier/CrudeOIL_H1/metadata.json` (new F1, feature_count=46, training_date)
   - `models/reversal_classifier/CrudeOIL_H1/feature_names.json` (46 features)

6. **Run `validate-no-fakes.sh`** on all changed files.

### Acceptance Criteria
- [ ] Training completed on 2024-2026 data
- [ ] metadata.json shows feature_count=46 and new training_date
- [ ] If peak_f1 >= 0.30: model deployed, ml_reversal active in RANGING
- [ ] If peak_f1 < 0.30: documented in metadata.json notes field, model stays gated
- [ ] feature_names.json includes regime_adx, regime_hurst, regime_atr_ratio
- [ ] validate-no-fakes.sh passes

---

## Task 4: Monitoring Dashboard Log Parser (optional, if time permits)

**Owner:** quant-dev
**File:** `scripts/parse_paper_signals.py`
**Priority:** LOW — quality of life improvement

### Requirements

Create a simple script that parses Docker logs and shows paper validation progress:

```bash
# Usage:
python scripts/parse_paper_signals.py

# Output:
# Paper Validation Status (2026-04-03 12:00 UTC)
# ================================================
# Signals collected: 3/50
# Win rate: 66.7% (target: 55%)
# Profit factor: 1.85 (target: 1.30)
# Max consecutive losses: 1 (max: 5)
# Regimes seen: TRENDING, RANGING (target: 2+)
#
# Recent signals:
#   2026-04-03 08:15 | CrudeOIL | BUY | $111.50 | SL $108.50 | TP $116.50 | TRENDING
#   2026-04-03 09:20 | CrudeOIL | SELL | $112.30 | SL $115.00 | TP $108.30 | RANGING
#   ...
#
# Criteria status:
#   ✗ min_signals: 3/50
#   ✓ min_win_rate: 66.7% >= 55%
#   ✓ min_profit_factor: 1.85 >= 1.30
#   ✓ max_consecutive_losses: 1 <= 5
#   ✓ min_regime_types: 2 >= 2
```

---

## Execution Order

```
Task 0 (lead) ←── ABSOLUTE FIRST: commit all 30+ files before touching anything
  ↓
  ├── Task 1 (mcp-verifier) ←── diagnose WHY 0 signals (Docker logs + MCP queries)
  ├── Task 2 (risk-eng) ←── add signal visibility logging + dead import cleanup
  └── Task 3 (quant-dev) ←── retrain XGBoost with regime features
      (all three run in PARALLEL after Task 0 completes)
  ↓
Task 5 (quant-dev) ←── optional monitoring script
```

## Launch Command

```
@lead Execute `docs/prompts/signal-diagnosis-and-model-retrain.md` — Signal
Diagnosis + Model Retrain sprint. YOU (lead) do Task 0 FIRST — commit all
30+ uncommitted files in logical groups. This is non-negotiable: one accident
destroys 3 sprints. After Task 0, launch THREE PARALLEL TRACKS: mcp-verifier
takes Task 1 (diagnose why 0/50 signals — CRITICAL CLUE: CrudeOIL and BRENT
have NO candles since Apr 2 20:00/21:00 UTC, meaning both symbols stale-skip
every cycle all day Apr 3. Check if MT4 ZMQ is streaming. Also check what
regime was classified during the Apr 2 $98→$113 rally — that $6.19 first
candle is 4-6× ATR which triggers VOLATILE halt. Read Docker logs for
regime_classified, stale_candles, regime_trading_halted events). risk-eng
takes Task 2 (add strategy_individual_score, signal_combined_result,
signal_hold_reason logs + clean up 3 dead imports: Decimal, ValueAreaStrategy,
MarketTick). quant-dev takes Task 3 (retrain XGBoost inside Docker with 3
regime features already coded in reversal_features.py — target peak_f1 >= 0.30;
use MCP tool train_reversal_models or docker exec). Go.
```

## Key Data for Diagnosis (from live MCP queries, Apr 3 16:00 UTC)

### Account State
- Balance: $293.39, Equity: $293.39, Margin: $0.00, Positions: 0

### CrudeOIL H1 (95,414 total candles in DB)
- Apr 2 01:00: $98.01 → $104.20 (+$6.19 = +6.3%) ← likely VOLATILE trigger
- Apr 2 12:00: $109.75 → $112.89 (+$3.14 = +2.9%) ← second spike
- Apr 2 14:00: $110.97 → $108.68 (-$2.29 = -2.1%) ← sharp reversal
- Apr 2 16:00-20:00: Calm consolidation ($110-$112, ranges < $1.80)
- **LAST CANDLE: Apr 2 20:00 UTC.** No Apr 3 data exists for CrudeOIL.
- This means CrudeOIL has been stale-skipped ALL DAY on Apr 3.

### BRENT_OIL H1 (38,954 total candles)
- **LAST CANDLE: Apr 2 21:00 UTC.** No Apr 3 data.
- Also stale-skipped all day today. Cross-asset filter has no fresh data.

### USA500 H1 (13,418 total candles)
- Has Apr 3 data: 02:00, 03:00, 04:00, 05:00, 06:00, 07:00, 13:00
- **GAP: 08:00-12:00 missing** (5 hours of data loss)
- Moves are tiny: ±$2-$8 on $6600 base (< 0.13%)
- Too flat to generate meaningful momentum/breakout signals

### GBPJPY H1 (43,025 total candles)
- Has Apr 3 data: 02:00-07:00, then gap, 11:00, gap, 15:00
- **GAPS: 08:00-10:00 and 12:00-14:00 missing**
- Moves are microscopic: ±0.01-0.15 on 211 base (< 0.07%)
- Zero chance of crossing any signal threshold

### Probable Root Cause: MULTI-FACTOR

1. **CrudeOIL + BRENT: No data flowing since Apr 2 close.**
   If MT4 stream stopped (market closed, EA disconnected, or symbol not streaming),
   every cycle fingerprint-matches → stale skip → zero evaluations.

2. **USA500 + GBPJPY: Data flowing but moves too small.**
   A 0.04% hourly move on USA500 won't cross any momentum/breakout threshold.
   These instruments need significant directional movement to generate signals.

3. **Apr 2 during active CrudeOIL move: Likely VOLATILE classification.**
   The $6.19 first candle (4-6× ATR) would trigger volatile.
   Even if later candles calmed, the 300-candle window still contains the spike.
   Volatile classification may persist for hours after a single extreme bar.

### Critical Questions for Diagnosis
- Is MT4 streaming CrudeOIL and BRENT today? (check ZMQ connection)
- Did the regime classifier ever classify a non-VOLATILE regime for CrudeOIL on Apr 2?
- Is the stale candle check the primary reason for 0 evaluations?
- At what point does the $6.19 bar exit the 300-candle window?

## Non-Negotiable Rules

- **No fakes.** validate-no-fakes.sh must pass on every edit.
- **No mocks** in tests. Real DB or skip.
- **No stopping the live loop.** Diagnosis is read-only. Logging changes are additive.
- **2% risk cap** still enforced.
- **Every commit tagged `[integration-pass]`** after mcp-verifier confirms.
- **COMMIT BEFORE ANYTHING ELSE IF RISK OF DATA LOSS.**
  If lead judges the uncommitted state is fragile, Task 4 moves to FIRST priority.
