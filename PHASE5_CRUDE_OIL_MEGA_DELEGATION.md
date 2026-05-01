# MEGA PROMPT — RiseTraderMVP: CrudeOil Prediction Optimization + Automated Trading
# Date: March 21, 2026
# Delegation: PARALLEL agents on SHARED TREE — NO worktrees

## CRITICAL: AGENT DELEGATION RULES
- ALL agents work on the SAME repo clone — NO worktree isolation (merging worktrees is a nightmare)
- Each agent works on its own BRANCH off main, merged back via PR
- Agents run IN PARALLEL on separate branches
- `lead` (Opus) orchestrates — delegates only, never codes
- Use agent configs from `.claude/agents/`: quant-dev, risk-eng, mcp-verifier, ml-trainer, reviewer
- ALL fakes hooks enforced: `scripts/validate-no-fakes.sh`
- ALL changes need `[integration-pass]` from mcp-verifier
- NO mock data, NO hardcoded values — real candles, real models, real backtests

## CURRENT BASELINE (from Mar 9, 2026 session)
- **ML Reversal (XGB) on CrudeOIL H1**: +156.62% return, Sharpe 12.63, Win Rate 79.37%, Profit Factor 4.25, Max DD -16.01%
- **Value Area** (current best): +208.94% return, Sharpe 16.94
- **Model**: XGB-conservative (max_depth=4, lr=0.2, 100 estimators), 43 features, walk-forward 5-fold + SMOTE
- **Only CrudeOIL_H1 model saved to disk** — BRENT_OIL/GBPJPY/USA500 trained but NOT persisted
- **LSTM**: BLOCKED (Docker OOM)
- **6/6 fakes eliminated** ✓

## TARGET: 10× PROFIT = +1,566% return or equivalent risk-adjusted improvement

---

## WORKSTREAM A: MODEL ACCURACY IMPROVEMENT (ml-trainer + quant-dev)

### Agent 1 — ml-trainer: Retrain + Hyperparameter Optimization
**Branch:** `crude/ml-hyperparam-sweep`
**Tools:** `train_reversal_models`, `compute_indicators`, `run_ml_backtest`
**Scope:**
1. Retrain CrudeOIL with expanded param grids:
   - XGB: max_depth [3,4,5,6,8], lr [0.01,0.05,0.1,0.2], estimators [100,200,500,1000]
   - min_child_weight [1,3,5], subsample [0.7,0.8,0.9], colsample_bytree [0.7,0.8,0.9]
2. Try XGB-aggressive config (beat XGB-conservative on BRENT_OIL)
3. Feature engineering: add volume profile, order flow imbalance, multi-TF RSI/MACD
4. Try different SMOTE ratios and class weights instead of SMOTE
5. Walk-forward with more folds (8-fold, 10-fold)
6. Save ALL resulting models to `models/reversal_classifier/CrudeOIL_H1/`
**Done when:** Best model beats current 0.132 reversal F1 AND improves backtest P&L

### Agent 2 — quant-dev: Multi-Timeframe + Feature Engineering
**Branch:** `crude/multi-tf-features`
**Scope:**
1. Compute indicators for M30 timeframe (aggregation code exists, needs data)
2. Add H4/D1 context features to H1 model (trend direction, S/R levels)
3. Add volume profile features (POC, value area high/low)
4. Add session-based features (London open, NY open, overlap period)
5. Add spread/volatility regime features
6. Ensure `compute_features_from_ohlcv()` remains single source of truth
**Files:** `src/ml/features/reversal_features.py`, `src/services/indicator_compute_service.py`
**Done when:** Feature set expanded and model retrained with new features

### Agent 3 — quant-dev: Ensemble Strategy
**Branch:** `crude/ensemble-strategy`
**Scope:**
1. Create ensemble combining ML Reversal + Value Area signals
   - ML Reversal: best profit factor (4.25), fewer but higher-quality trades
   - Value Area: best absolute return (+208%), high trade frequency
   - Ensemble: signals where BOTH agree, or ML confidence weights Value Area
2. Backtest ensemble vs individual strategies
3. Optimize ensemble weights via grid search
**Files:** New `src/strategies/ensemble/` directory
**Done when:** Ensemble backtested with results > either individual strategy

---

## WORKSTREAM B: AUTOMATED ORDER EXECUTION (risk-eng + quant-dev)

### Agent 4 — risk-eng: Wire ML Predictions to Live Orders
**Branch:** `crude/ml-live-orders`
**Scope:**
1. Pipeline: ML prediction → signal validation → risk check → order placement
2. MCP flow: `get_latest_candles` → `compute_indicators` → inference → `place_market_order`
3. Confidence threshold gating (only trade when > optimized threshold)
4. ATR stop-loss with anti-stop-hunt offset (existing risk-eng code)
5. Kelly position sizing with real win_rate + avg_win/avg_loss
6. Start PAPER TRADING mode — no live trades until validated
**Files:** `src/agents/`, `src/execution/`, `src/services/stealth_stop_manager.py`
**Done when:** Paper trading pipeline runs autonomously on ML signals

### Agent 5 — risk-eng: Pending Orders Strategy
**Branch:** `crude/pending-orders`
**Tools:** `place_pending_order`, `save_pending_orders_strategy`, `load_pending_orders_strategy`
**Scope:**
1. Pending order strategy based on ML-identified reversal zones
2. BUY_STOP/SELL_STOP at predicted reversal levels
3. Order management: cancel stale, update on new signals
4. Risk: max 3 pending per symbol, max 2% risk per order
**Done when:** Pending orders placed automatically at ML reversal zones

---

## WORKSTREAM C: CONTINUOUS OPTIMIZATION LOOP (mcp-verifier + lead)

### Agent 6 — mcp-verifier: Backtest Validation + Monte Carlo
**Branch:** `crude/validation-loop`
**Tools:** `run_backtest_and_wait`, `monte_carlo_validate`, `sensitivity_analysis`, `rolling_window_optimize`
**Scope:**
1. Every new model/strategy through full validation:
   - Walk-forward backtest (out-of-sample)
   - Monte Carlo simulation (1000 runs)
   - Sensitivity analysis on key params
   - Rolling window optimization for stability
2. Reject any strategy failing validation
3. Track results in `docs/phase-gates/`
4. ITERATE: Feed results back to ml-trainer + quant-dev
**Done when:** Validated strategy achieves 10× profit with Monte Carlo confirmation

### Agent 7 — reviewer: Continuous Code Review [READ-ONLY]
**Scope:** 5-lens review on all PRs: security, performance, architecture, regression, fakes

---

## ITERATION CYCLE (CONTINUOUS UNTIL 10×)
```
ROUND N:
  1. ml-trainer: Train new model variant (branch)
  2. quant-dev: Add features / create ensemble (branch)
  3. mcp-verifier: Backtest + Monte Carlo validate
  4. IF profit < 10× → analyze failures → adjust → ROUND N+1
  5. IF profit ≥ 10× → risk-eng wires to paper trading → 24hr validation → DONE
```

## KEY MCP TOOLS
- `compute_indicators` — compute features for any symbol/timeframe
- `train_reversal_models` — full training pipeline
- `run_ml_backtest` — P&L evaluation of ML model
- `run_backtest_and_wait` — backtest any strategy
- `optimize_strategy` — grid search optimization
- `monte_carlo_validate` — robustness testing
- `sensitivity_analysis` — param sensitivity
- `rolling_window_optimize` — walk-forward optimization
- `place_market_order` / `place_pending_order` — order execution
- `get_open_positions` / `get_account_info` — monitor positions

## SUCCESS CRITERIA
- CrudeOIL strategy ≥ +1,500% return (10× current 156%)
- OR Sharpe > 20 with > +500% return (risk-adjusted 10×)
- OR ensemble collectively achieves 10× over baseline
- Monte Carlo: > 80% of runs profitable
- Paper trading confirms backtest in real-time
- All code passes validate-no-fakes.sh + reviewer approval