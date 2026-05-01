# ML Pipeline Training Results & Status (Mar 9, 2026)

## Executive Summary
Phase 4 ML pipeline is **partially complete**. XGBoost models trained for 4/5 symbols. LSTM blocked by Docker issues. Models need P&L evaluation via backtesting before production use.

## Training Results (Walk-Forward 5-Fold, SMOTE, H1 timeframe)

### Best XGBoost Models Per Symbol
| Symbol | Config | Rev F1 | Peak F1 | Valley F1 | Macro F1 | Status |
|--------|--------|--------|---------|-----------|----------|--------|
| BRENT_OIL | XGB-aggressive | **0.142** | 0.169 | 0.115 | 0.416 | Best overall |
| CrudeOIL | XGB-default | **0.132** | 0.099 | 0.165 | 0.411 | Best valley |
| USA500 | XGB-aggressive | **0.122** | 0.106 | 0.138 | 0.403 | OK |
| GBPJPY | XGB-default | **0.094** | 0.052 | 0.137 | 0.386 | Weakest |
| XAUUSD | ALL FAILED | — | — | — | — | 99.9% zero volume |

### Why F1 Scores Are Low (~0.09-0.14)
- Class imbalance: peaks+valleys are only ~6% of candles (94% "neither")
- SMOTE helps but reversal detection is inherently hard
- Low F1 ≠ unprofitable — need P&L backtest to evaluate trading value

### Training Infrastructure
- **231,754 indicator rows** computed for 5 symbols on H1
- **22 training runs** recorded in `training_runs` PostgreSQL table
- ZigZag labels: ~6% reversal rate across all symbols
- Walk-forward validation prevents look-ahead bias

## Models Saved to Disk
- **CrudeOIL_H1 ONLY**: `models/reversal_classifier/CrudeOIL_H1/`
  - `model.json` (456KB XGBoost native format)
  - `feature_names.json` (43 feature names)
  - `metadata.json` (training config + metrics)
- **BRENT_OIL, GBPJPY, USA500**: Trained successfully but models NOT persisted to disk
- **Fix needed**: Re-run training with save for remaining symbols

## Backtest P&L Results (CrudeOIL H1, Jan 2024 – Mar 2025)
| Strategy | Return | Sharpe | Win Rate | Profit Factor | Max DD |
|----------|--------|--------|----------|---------------|--------|
| ML Reversal (XGB) | **+156.62%** | **12.63** | **79.37%** | **4.25** | -16.01% |
| Value Area | +208.94% | 16.94 | 83.95% | 3.42 | -7.16% |
| MA Crossover | -17.47% | -2.61 | 33.06% | 0.74 | -24.77% |
| Crude Oil v3 | +3.48% | 1.13 | 31.34% | 1.16 | -8.13% |
| RSI | -8.89% | -1.08 | 63.83% | 0.81 | -22.62% |

**ML Reversal is the 2nd best strategy** — very profitable with highest profit factor (4.25) but more drawdown than Value Area.

## Bugs Fixed During Pipeline Build
1. **TrainingStatus ENUM**: Python uppercase vs Postgres lowercase → recreated with uppercase
2. **ENUM↔VARCHAR JOIN**: `market_data.timeframe` (ENUM) vs `indicators.timeframe` (Text) → `cast(MarketData.timeframe, Text)`
3. **Missing imblearn**: `imbalanced-learn` not in Docker image → pip installed
4. **XGBoost load_model()**: `XGBClassifier().load_model()` doesn't restore `n_classes_` → must use raw `xgb.Booster()` API with `xgb.DMatrix`
5. **LSTM BLAS error**: Docker `python:3.11-slim` lacks openblas → needs `libopenblas-dev` in Dockerfile

## XAUUSD Failure Root Cause
- 99.9% of H1 candles have zero tick volume
- `volume_spike = volume / volume_ma` → NaN (0/0)
- `dropna()` eliminates almost all rows → only 180 samples survive
- SMOTE needs ≥4 minority samples per fold → crashes with 2-3
- **Fix options**: Skip volume features for XAUUSD, or fill zeros with 1

## LSTM Status: BLOCKED
- Docker OOM kills training (SMOTE expands dataset per fold)
- oneDNN matmul error with default PyTorch → fixed with CPU wheel
- Still OOM after fix → needs either:
  - Train on host machine (not in Docker)
  - Disable SMOTE for LSTM
  - Increase Docker memory limit

## Feature Parity Architecture
- `compute_features_from_ohlcv(df)` in `src/ml/features/reversal_features.py`
- Single source of truth for all feature computation
- Called by both DB-backed `ReversalFeatureExtractor` and tick-buffer `MLReversalStrategy`
- 43 features: RSI, MACD, ATR, BB, MA + derived (divergence, volume spike, patterns, temporal)

## Services Created (Reusable from API/MCP)
1. `src/services/indicator_compute_service.py` — `IndicatorComputeService` + `compute_indicators_df()`
2. `src/services/reversal_training_service.py` — `ReversalTrainingService.train_pipeline()`
3. Scripts simplified to thin CLI wrappers calling these services

## MCP Tools Added
1. `compute_indicators` — compute RSI/MACD/ATR/BB/MA for symbols
2. `train_reversal_models` — full pipeline: indicators → labels → train → save
3. `run_ml_backtest` — backtest ML model predictions for P&L evaluation

## ml_reversal Strategy
- Registered in both SyntheticEngine (12th strategy) and VectorizedEngine
- Loads XGBoost model from disk on first tick
- Uses `compute_features_from_ohlcv()` for feature parity
- ATR-based stops (2×ATR) with anti-stop-hunt random offset
- min_confidence threshold (default 0.55) gates signal quality

## Next Steps
1. Save models for BRENT_OIL, GBPJPY, USA500 (re-run training with persist)
2. Fix LSTM (train on host or increase Docker memory)
3. Backtest ML Reversal on other symbols (BRENT_OIL, GBPJPY, USA500)
4. Optimize min_confidence threshold via parameter grid
5. Wire ReversalPredictor for live inference (already done for CrudeOIL)
