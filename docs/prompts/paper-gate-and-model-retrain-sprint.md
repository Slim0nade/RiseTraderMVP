# Sprint: Paper Validation Gate + XGBoost Retrain + Integration Tests

> **Priority:** CRITICAL — system is live-capable but unvalidated
> **Prerequisite:** Regime-aware system deployed (Tasks 1-4, 6 code complete)
> **Constraint:** Do NOT stop the live loop. All changes hot-patchable.

---

## Context

The regime-aware strategy system is deployed with RegimeClassifier, StrategyRouter,
CrossAssetFilter, TieredPositionSizer (volatility-adjusted), and dual cooldowns.
Three critical gaps remain:

1. **PaperValidationService exists but is NOT wired into live_trading_service.py.**
   The class at `src/services/paper_validation_service.py` (201 lines, fully tested)
   is never imported or called. Zero references in the live loop. The 50-signal
   paper gate that protects against unvalidated live execution does not function.

2. **XGBoost model is dead.** `models/reversal_classifier/CrudeOIL_H1/metadata.json`
   shows `peak_f1=0.089`, trained 2026-03-06. The quality gate (MIN_REVERSAL_F1=0.30)
   correctly blocks it. Result: `ml_reversal` strategy returns None every cycle.
   In RANGING regime, only value_area + mean_reversion run (no ML contribution).

3. **Zero integration tests with real DB data.** All 2,100+ lines of unit tests use
   synthetic OHLCV. No test verifies the full pipeline against actual PostgreSQL candles.

---

## Task 1: Wire PaperValidationService into Live Loop

**Owner:** risk-eng
**File:** `src/services/live_trading_service.py`
**Priority:** BLOCKING — nothing else matters until this works

### Requirements

1. Add env var `PAPER_VALIDATION_MODE` (default: `true`).
   When true, ALL signals feed into PaperValidationService instead of execution.

2. In `__init__()`:
   ```python
   from src.services.paper_validation_service import PaperValidationService
   self._paper_mode = os.getenv("PAPER_VALIDATION_MODE", "true").lower() == "true"
   self._paper_validator = PaperValidationService() if self._paper_mode else None
   ```

3. In `_process_symbol()`, after signal generation + all filters pass + risk validation:
   ```python
   if self._paper_validator and not self._paper_validator.get_validation_status()["criteria_met"]:
       # Record signal for paper tracking instead of executing
       self._paper_validator.record_signal(
           symbol=symbol, action=action,
           entry_price=current_price,
           stop_loss=stop_loss, take_profit=take_profit,
           regime=regime.value, lots=position_size_lots,
       )
       logger.info("paper_signal_recorded", symbol=symbol, action=action,
                    price=current_price, regime=regime.value)
       return  # Do NOT execute
   ```

4. In the main cycle (every 5-min iteration), BEFORE processing symbols, check
   paper outcomes against current prices:
   ```python
   if self._paper_validator:
       for sym in self._symbols:
           latest_price = <fetch latest close for sym>
           result = self._paper_validator.check_outcomes(sym, latest_price)
           if result:
               logger.info("paper_trade_resolved", symbol=sym,
                           outcome=result.outcome, pnl=result.pnl)
       status = self._paper_validator.get_validation_status()
       logger.info("paper_validation_status",
                   total=status["total_signals"],
                   wins=status["wins"], losses=status["losses"],
                   win_rate=round(status["win_rate"], 3),
                   profit_factor=round(status["profit_factor"], 3),
                   criteria_met=status["criteria_met"])
       if status["criteria_met"] and self._paper_mode:
           logger.warning("PAPER_VALIDATION_PASSED — criteria met. "
                          "Set PAPER_VALIDATION_MODE=false to enable live execution.")
   ```

5. When `criteria_met` becomes True AND operator sets `PAPER_VALIDATION_MODE=false`,
   the system transitions to real execution naturally (no restart needed if using
   env reload, otherwise restart required).

### Acceptance Criteria
- [ ] `PAPER_VALIDATION_MODE=true` → zero MT4 orders placed, signals logged to paper service
- [ ] Paper outcomes checked every cycle using real prices
- [ ] Status logged every cycle: total signals, win rate, profit factor, criteria_met
- [ ] When criteria_met=True, warning log instructs operator to disable paper mode
- [ ] When PAPER_VALIDATION_MODE=false + criteria_met=True → normal execution resumes
- [ ] 5 unit tests covering: paper mode on/off, signal recording, outcome checking, criteria transition

### Also fix while in this file
- Remove dead imports: `Decimal`, `ValueAreaStrategy`, `ValueAreaParams`, `MarketTick`
- Verify all existing imports are used

---

## Task 2: Retrain XGBoost with Regime Features

**Owner:** quant-dev (in Docker container or worktree)
**Files:** `src/ml/features/reversal_features.py`, training scripts
**Priority:** HIGH — ml_reversal is dead weight until model improves

### Context

Current model: 43 features, peak_f1=0.089, trained 2026-03-06.
The model was trained before the regime system existed. Adding regime-context
features should improve peak/valley detection because reversals behave differently
in trending vs ranging markets.

### Requirements

1. Add 3 new features to `compute_features_from_ohlcv()` in `reversal_features.py`:
   - `regime_adx`: ADX(14) value (continuous, not thresholded)
   - `regime_hurst`: Hurst exponent from R/S analysis (reuse RegimeClassifier._compute_hurst logic)
   - `regime_atr_ratio`: ATR(14) / SMA(ATR, 50)

   These give the model context about WHAT regime it's predicting in, which should
   help it learn that reversals in trending markets look different from ranging markets.

2. Retrain on 2024-01-01 to 2026-03-31 CrudeOIL H1 data from PostgreSQL.
   - Use the existing training pipeline
   - ZigZag labeling: depth=12, deviation=5, backstep=3 (unchanged)
   - Target: peak_f1 >= 0.30 (must clear quality gate)
   - If F1 still < 0.30 after regime features, try:
     a. Increase `scale_pos_weight` for minority classes
     b. Reduce `max_depth` to 4 (prevent overfitting on 43+3 features)
     c. Use SMOTE or class-weight balancing
   - If still < 0.30 after tuning: document results, keep model gated, do NOT fake scores

3. Update `feature_names.json` to include the 3 new features.

4. Run `validate-no-fakes.sh` against all changed files.

### Acceptance Criteria
- [ ] 3 new features added to reversal_features.py (regime_adx, regime_hurst, regime_atr_ratio)
- [ ] Feature parity: training and inference use identical feature computation
- [ ] Model retrained on 2024-2026 data
- [ ] metadata.json updated with new metrics
- [ ] If peak_f1 >= 0.30: model deployed, ml_reversal strategy active in RANGING regime
- [ ] If peak_f1 < 0.30: model stays gated, document why in metadata.json notes field
- [ ] No hardcoded values introduced (validate-no-fakes.sh passes)

---

## Task 3: Integration Tests with Real DB Data

**Owner:** mcp-verifier
**Files:** `tests/integration/`
**Priority:** HIGH — validates the full pipeline against actual market data

### Requirements

Create `tests/integration/test_regime_pipeline_real_data.py`:

1. **test_regime_classification_real_candles**:
   - Fetch 300 real CrudeOIL H1 candles from PostgreSQL
   - Run RegimeClassifier.classify()
   - Assert: returns valid MarketRegime enum, metadata has all expected keys
   - Assert: ADX is float > 0, Hurst is float in [0,1], ATR ratio is float > 0
   - Print actual regime + metadata for manual inspection

2. **test_strategy_routing_from_real_regime**:
   - Use regime from test 1 → StrategyRouter.get_strategy_config()
   - Assert: returned strategies are non-empty (unless VOLATILE)
   - Assert: weights sum to 1.0 (±0.01)
   - Assert: signal_threshold is 0.60 or 0.75

3. **test_cross_asset_real_data**:
   - Run CrossAssetFilter.check_confirmation("CrudeOIL", "BUY")
   - Assert: returns (float, str) tuple
   - Assert: score is in [-1.0, 1.0] range
   - Run again with "SELL" — score should differ from BUY

4. **test_full_signal_pipeline**:
   - Instantiate LiveTradingService (dry_run=True)
   - Call _process_symbol("CrudeOIL") with real candles
   - Assert: no exceptions raised
   - Assert: structured logs contain regime_classified, signal decision
   - This is the E2E smoke test

5. **test_paper_validation_with_real_prices**:
   - Create PaperValidationService
   - Record 5 signals using recent CrudeOIL prices
   - Advance price to hit SL/TP
   - Assert: outcomes resolve correctly
   - Assert: validation status updates

### Rules
- NO `unittest.mock`, NO `@patch()`, NO `MagicMock`
- All tests connect to real PostgreSQL (use test DB or guard with `@pytest.mark.integration`)
- Tests must handle "no data available" gracefully (skip, don't fail)
- Print regime metadata so humans can sanity-check

### Acceptance Criteria
- [ ] 5 integration tests created
- [ ] All pass against real PostgreSQL data
- [ ] No mocks used
- [ ] Tagged with `@pytest.mark.integration`
- [ ] CI-safe: tests skip cleanly if DB unavailable

---

## Task 4: Regime Config Externalization

**Owner:** quant-dev
**Files:** `config/regime.yaml`, `src/trading/regime/regime_classifier.py`
**Priority:** MEDIUM — enables tuning without code deploys

### Requirements

1. Create `config/regime.yaml`:
   ```yaml
   regime_classifier:
     adx_period: 14
     adx_trend_threshold: 25
     adx_ranging_threshold: 20
     atr_period: 14
     atr_sma_period: 50
     atr_volatile_ratio: 2.5
     spike_atr_multiple: 3.0
     return_sigma_multiple: 4.0
     hurst_max_lag: 20
     hurst_trend_threshold: 0.95
     hurst_ranging_low: 0.35
     hurst_ranging_high: 0.95
     ma50_consec_threshold: 10
     ma20_cross_threshold: 3

   strategy_router:
     trending:
       strategies: {momentum: 0.40, breakout: 0.35, trend_following: 0.25}
       signal_threshold: 0.60
     ranging:
       strategies: {value_area: 0.45, mean_reversion: 0.35, ml_reversal: 0.20}
       signal_threshold: 0.60
     volatile:
       allow_trading: false
     unknown:
       strategies: {momentum: 0.20, breakout: 0.20, trend_following: 0.20, value_area: 0.20, mean_reversion: 0.20}
       signal_threshold: 0.75
   ```

2. Update `RegimeClassifier.__init__()` to accept optional `config_path` parameter.
   If provided, load YAML and override defaults. If not provided, use current defaults.

3. Update `StrategyRouter.__init__()` similarly.

4. `LiveTradingService.__init__()` passes `config/regime.yaml` to both.

### Acceptance Criteria
- [ ] config/regime.yaml created with all current defaults
- [ ] RegimeClassifier loads from YAML when path provided
- [ ] StrategyRouter loads from YAML when path provided
- [ ] Existing unit tests still pass (backward compatible)
- [ ] Changing YAML values changes behavior without code change

---

## Task 5: Documentation Update

**Owner:** reviewer
**Files:** `docs/`
**Priority:** LOW — after all code tasks complete

### Requirements
1. Update `docs/architecture.md` (or create) with regime pipeline flow diagram
2. Document paper validation gate: what it tracks, activation criteria, how to transition to live
3. Document regime YAML config: what each threshold does, how to tune
4. Update CLAUDE.md "6 Known Fakes" section — mark which are eliminated vs remaining

---

## Execution Order

```
Task 1 (risk-eng) ←── BLOCKING, do first
  ↓
Task 2 (quant-dev) ←── can start in parallel with Task 1
  ↓
Task 3 (mcp-verifier) ←── after Tasks 1+2 merge
  ↓
Task 4 (quant-dev) ←── after Task 3 confirms pipeline works
  ↓
Task 5 (reviewer) ←── after all code lands
```

## Launch Command

```
@lead Execute `docs/prompts/paper-gate-and-model-retrain-sprint.md` — Paper Gate
+ Model Retrain sprint. Task 1 (wire PaperValidationService) goes to risk-eng FIRST
— this is BLOCKING. quant-dev starts Task 2 (XGBoost retrain with regime features)
in parallel. After both land, mcp-verifier runs Task 3 (integration tests with real
DB data). Then quant-dev does Task 4 (regime config YAML). Reviewer closes with
Task 5 (docs). Set PAPER_VALIDATION_MODE=true in .env BEFORE deploying Task 1 —
system must collect 50 validated signals before ANY live execution resumes. Go.
```

## Success Criteria

The sprint is DONE when:
1. PaperValidationService is wired and logging every signal + outcome
2. XGBoost is either retrained above 0.30 F1 or documented as insufficient
3. Integration tests pass against real PostgreSQL data
4. Regime config is externalized to YAML
5. Operator can monitor paper validation status in logs and transition to live
   when criteria_met=True

## Non-Negotiable Rules

- **No fakes.** validate-no-fakes.sh must pass on every edit.
- **No mocks** in integration tests. Real DB or skip.
- **No stopping the live loop.** All changes are additive — paper mode wraps
  around existing execution, it doesn't replace it.
- **2% risk cap** still enforced. Paper signals must respect same risk rules
  as live signals (validates realistic position sizing).
- **Every commit tagged `[integration-pass]`** after mcp-verifier confirms.
