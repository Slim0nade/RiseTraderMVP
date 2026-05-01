# ZigZag ML Labeling Implementation

**Date:** 2026-01-14 (created), 2026-03-09 (updated with training results)
**Status:** Complete — labels applied, models trained

## Label Values
- `1` = PEAK (short/sell signal)
- `0` = NEITHER (no trade)
- `-1` = VALLEY (long/buy signal)

## ZigZag Parameters
- depth: 12, deviation: 5, backstep: 3
- Point sizes: CrudeOIL=0.01, XAUUSD=0.01, GBPJPY=0.001, BRENT_OIL=0.01, USA500=0.01

## Labeling Results (H1, all symbols)
| Symbol | Valleys | Peaks | Total Indicators | Reversal % |
|--------|---------|-------|-----------------|------------|
| CrudeOIL | 3,072 | 3,071 | 95,109 | 6.5% |
| GBPJPY | 1,251 | 1,247 | 42,700 | 5.8% |
| XAUUSD | 1,237 | 1,240 | 42,179 | 5.9% |
| BRENT_OIL | 1,225 | 1,222 | 38,661 | 6.3% |
| USA500 | 415 | 421 | 13,105 | 6.4% |

## Key Files
- `src/ml/labeling/zigzag_labeler.py` — Core ZigZag algorithm (ported from MQL4)
- `src/ml/labeling/zigzag_label_service.py` — DB service (label_symbol, get_label_distribution)
- `src/ml/features/reversal_features.py` — 43 features + `compute_features_from_ohlcv()`
- `src/ml/training/train_reversal_classifier.py` — Walk-forward XGBoost + LSTM trainer

## Training Results
See `ml-pipeline-training-results-mar2026` for full details.
Best model: BRENT_OIL XGB-aggressive Rev F1=0.142
P&L verified: ML Reversal +156.62% return on CrudeOIL H1 backtest
