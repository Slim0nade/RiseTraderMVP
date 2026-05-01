# ML Pipeline Refactor — COMPLETE (Mar 9, 2026)

## What Was Done
Full 4-part refactor: extract services, fix Docker, create ML strategy, add MCP tools, run P&L backtest.

## Part A: Services Extracted
- **`src/services/indicator_compute_service.py`** (NEW) — `IndicatorComputeService(session)` + module-level `compute_indicators_df(df)`
- **`src/services/reversal_training_service.py`** (NEW) — `ReversalTrainingService(session)` with `train_pipeline()` orchestrator
- Scripts `compute_indicators.py` and `train_and_compare.py` simplified to thin CLI wrappers

## Part B: Docker Fixes
- Added `libopenblas-dev` to `docker/api/Dockerfile.simple`
- Commented out `autogen-agentchat`, `autogen-ext`, `stable-baselines3`, `gymnasium` in requirements.txt (caused 20hr pip resolution spiral)
- Updated `fastapi>=0.115.0` (was pinned ==0.104.1)
- Installed `torch==2.5.1` CPU wheel (`--index-url https://download.pytorch.org/whl/cpu`) to fix oneDNN matmul error

## Part C: ML Reversal Strategy
- **`src/strategies/ml/ml_reversal.py`** (NEW) — `MLReversalParams + MLReversalSignal + MLReversalStrategy + create_ml_reversal_strategy()`
- **`src/ml/features/reversal_features.py`** (MODIFIED) — added `compute_features_from_ohlcv(df)` and `get_feature_columns()` as standalone functions
- **Registered in SyntheticEngine** (6 places: import, init, default_params, process_tick, handler, reset)
- **Registered in VectorizedEngine** (`_calculate_indicators` + `_generate_signals` blocks)
- **Registered in optimizer** (`DEFAULT_PARAM_GRIDS["ml_reversal"]`)

## Part D: MCP Tools
3 new tools in `src/mcp/server.py`:
- `compute_indicators` → `_compute_indicators()`
- `train_reversal_models` → `_train_reversal_models()`
- `run_ml_backtest` → `_run_ml_backtest()` (delegates to vectorized engine)

## Critical Technical Details

### XGBoost Loading (MUST use Booster API)
- `XGBClassifier().load_model()` does NOT restore `n_classes_` → crashes on `predict_proba()`
- **Correct approach**: `booster = xgb.Booster(); booster.load_model(path); booster.predict(xgb.DMatrix(X))`
- `multi:softprob` returns `(n_samples, 3)` array: [valley_prob, neutral_prob, peak_prob]
- Class mapping: 0=valley→BUY, 1=neutral→HOLD, 2=peak→SELL

### Feature Parity
- `compute_features_from_ohlcv(df)` is single source of truth — combines indicators + reversal features + temporal + candle patterns
- Both training path (DB) and inference path (tick buffer / vectorized) must use this function
- 43 features total; `get_feature_columns()` returns the exclusion-filtered list

### Vectorized ML Backtest
- In `_calculate_indicators()`: calls `compute_features_from_ohlcv(df.reset_index())` 
- In `_generate_signals()`: loads Booster, creates DMatrix, batch predicts all rows
- Execution: 2.7s for 6,901 H1 candles (feature computation dominates)

## Backtest Results (CrudeOIL H1, Jan 2024 – Mar 2025, $10K)

| Strategy | Return | Sharpe | Win Rate | Profit Factor | Max DD | Avg P&L |
|----------|--------|--------|----------|---------------|--------|---------|
| **ML Reversal (XGB)** | **+156.62%** | **12.63** | **79.37%** | **4.25** | -16.01% | $103.11 |
| Value Area | +208.94% | 16.94 | 83.95% | 3.42 | -7.16% | $50.88 |
| MA Crossover | -17.47% | -2.61 | 33.06% | 0.74 | -24.77% | -$13.75 |
| Crude Oil v3 | +3.48% | 1.13 | 31.34% | 1.16 | -8.13% | $4.67 |
| RSI | -8.89% | -1.08 | 63.83% | 0.81 | -22.62% | -$10.07 |

**Key insight**: ML Reversal has highest profit factor (4.25) and avg P&L ($103), but fewer trades (63 vs 162 for value_area). Value Area leads on absolute return due to trade frequency.

## Model Used
- XGB-conservative: max_depth=4, lr=0.2, 100 estimators
- Walk-forward 5-fold TimeSeriesSplit + SMOTE
- 43 features, reversal_f1=0.116 (low F1 but profitable in backtest)
- Path: `models/reversal_classifier/CrudeOIL_H1/model.json`

## LSTM Status: BLOCKED
- Docker OOM kills LSTM training (SMOTE expands dataset per fold × 5 folds)
- Options: train on host machine, disable SMOTE (use class_weight), increase Docker memory

## Files Modified/Created
| Action | File |
|--------|------|
| CREATE | `src/services/indicator_compute_service.py` |
| CREATE | `src/services/reversal_training_service.py` |
| CREATE | `src/strategies/ml/__init__.py` |
| CREATE | `src/strategies/ml/ml_reversal.py` |
| MODIFY | `src/ml/features/reversal_features.py` |
| MODIFY | `src/services/backtesting/vectorized_engine.py` |
| MODIFY | `src/services/backtesting/synthetic_engine.py` |
| MODIFY | `src/services/backtesting/optimizer.py` |
| MODIFY | `src/mcp/server.py` |
| MODIFY | `docker/api/Dockerfile.simple` |
| MODIFY | `requirements.txt` |
| MODIFY | `requirements-api.txt` |
| MODIFY | `scripts/compute_indicators.py` |
| MODIFY | `scripts/train_and_compare.py` |

## Strategy Count
- **12 total in SyntheticEngine**: 6 Phase 1 + 5 Phase 2 + ml_reversal
- **6 in VectorizedEngine**: ma_crossover, rsi, crude_oil_v3, mean_reversion, value_area, ml_reversal

## What's Next
- Retrain models for other symbols (BRENT_OIL, GBPJPY, USA500 — trained but not saved to disk)
- Fix LSTM training (train on host or disable SMOTE)
- Optimize ml_reversal params via grid search (min_confidence, ATR multipliers)
- Paper trading evaluation with real-time signals
