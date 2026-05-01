# Phase 4: ML Integration Exploration

**Last Updated:** March 9, 2026
**Status:** SUPERSEDED — See `ml-pipeline-training-results-mar2026` for current state.

Key items from this exploration that remain relevant:
- MLPredictionAgent fake formulas at lines 338-339 have been REPLACED with ReversalPredictor
- Signal generator ML weights: high_vol=0.15, trending=0.25, ranging=0.20, low_vol=0.10
- `_ml_forecast_strategy()` maps reversal probs: valley_prob>0.65→BUY, peak_prob>0.65→SELL
- Kelly Criterion position sizing is DECOUPLED from ML confidence (uses real trade stats)
- Graceful degradation: missing model → ML weight stays 0.0, no crash
