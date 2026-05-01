# ML Training Pipeline Architecture & Phase 4 Integration

**Last Updated:** March 9, 2026
**Status:** SUPERSEDED — See `ml-pipeline-training-results-mar2026` for current state.

## Summary of Changes (Mar 4 → Mar 9)
- XGBoost trained for 4/5 symbols (XAUUSD failed — 99.9% zero volume)
- Real F1 scores are 0.09-0.14 (NOT the 0.62 originally estimated)
- Services extracted: `IndicatorComputeService` + `ReversalTrainingService`
- `compute_features_from_ohlcv()` extracted as standalone function for feature parity
- ml_reversal strategy created + registered in SyntheticEngine
- P&L backtest: ML Reversal +156.62% return, Sharpe 12.63, PF 4.25 (CrudeOIL H1)
- LSTM still blocked (Docker OOM + openblas)
- MLflow not used — models saved natively to disk
