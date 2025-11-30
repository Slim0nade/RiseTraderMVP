# Technical Research: ML Forecasting Pipeline

**Feature**: 003-ml-forecasting-pipeline
**Created**: 2025-11-29
**Phase**: Phase 0 (Research & Technical Decisions)

## Purpose

This document captures all technical decisions and research findings that inform the implementation of the ML Forecasting Pipeline. It resolves uncertainties from the specification and provides concrete technical choices for model architectures, hyperparameters, feature engineering, and system integration.

## Technical Decisions

### TD-001: LSTM Architecture Selection

**Decision**: Use stacked bidirectional LSTM with attention mechanism

**Rationale**:
- **Bidirectional**: Captures both forward and backward temporal dependencies in price data
- **Stacked layers**: 2-3 layers provide sufficient depth without overfitting on financial time series
- **Attention mechanism**: Helps model focus on relevant historical time steps for prediction
- **Dropout**: Regularization between LSTM layers (0.2-0.3) prevents overfitting

**Implementation Details**:
```python
# Architecture configuration
num_layers = 2
hidden_size = 128
dropout = 0.2
bidirectional = True
attention = True
```

**Alternatives Considered**:
- Simple unidirectional LSTM: Insufficient for complex price patterns
- GRU: Similar performance but LSTM more established for financial forecasting
- Transformer: Requires more data and compute, reserved for future enhancement

**References**:
- PyTorch LSTM documentation
- Financial time series forecasting literature (Temporal Fusion Transformer paper as inspiration)

---

### TD-002: XGBoost Feature Engineering Strategy

**Decision**: Use lag features, rolling statistics, and technical indicators as XGBoost inputs

**Rationale**:
- XGBoost excels with engineered tabular features
- Lag features (t-1, t-2, ..., t-60) capture recent price momentum
- Rolling statistics (mean, std, min, max over 5/10/20 windows) capture volatility regimes
- Technical indicators (RSI, MACD, Bollinger Bands) encode domain knowledge

**Implementation Details**:
```python
# Feature groups
lag_periods = [1, 2, 3, 5, 10, 20, 60]  # minutes for 1h data
rolling_windows = [5, 10, 20]
technical_indicators = ['rsi_14', 'macd', 'bb_upper', 'bb_lower', 'atr']
```

**Alternatives Considered**:
- Raw OHLCV only: Insufficient for XGBoost to learn complex patterns
- Deep feature engineering (100+ features): Risk of overfitting, longer training time

**References**:
- XGBoost documentation on feature engineering
- TA-Lib for technical indicator calculations

---

### TD-003: Exogenous Variable Integration

**Decision**: Include DXY, VIX as normalized time-aligned features; news events as binary flags

**Rationale**:
- DXY (Dollar Index): Inverse correlation with commodity prices (crude oil)
- VIX (Volatility Index): Market fear indicator, affects risk-on/risk-off sentiment
- News events: Binary flag (0/1) for scheduled economic releases (NFP, CPI, FOMC)
- Time-alignment: Exogenous data synchronized to same timestamp as OHLCV data
- Normalization: Z-score normalization to match price feature scales

**Implementation Details**:
```python
# Exogenous features
exogenous_features = {
    'dxy_close': 'continuous',  # Z-score normalized
    'vix_close': 'continuous',  # Z-score normalized
    'is_news_event': 'binary'   # 0 or 1
}
```

**Alternatives Considered**:
- Sentiment analysis from news text: Too complex, reserved for future enhancement
- Additional macro indicators (oil inventory, interest rates): Causes data availability issues

**References**:
- Economic calendar APIs (Alpha Vantage, Financial Modeling Prep)
- DXY and VIX data sources (Yahoo Finance, Alpha Vantage)

---

### TD-004: Training Data Preparation Strategy

**Decision**: Use walk-forward cross-validation with 70/15/15 train/val/test split per window

**Rationale**:
- Walk-forward: Prevents look-ahead bias, simulates realistic deployment
- Window size: 30 days training, 5 days validation, 5 days test
- Rolling window: Slide by 5 days to create multiple train/val/test sets
- Data leakage prevention: No future information in feature engineering (no global normalization)

**Implementation Details**:
```python
# Walk-forward configuration
train_window_days = 30
val_window_days = 5
test_window_days = 5
slide_days = 5

# Per-window normalization to prevent leakage
scaler = StandardScaler()
scaler.fit(train_window_data)  # Fit only on training data
```

**Alternatives Considered**:
- Simple 70/30 split: Doesn't account for temporal ordering, causes data leakage
- K-fold cross-validation: Inappropriate for time series (shuffles temporal order)

**References**:
- scikit-learn TimeSeriesSplit
- Financial forecasting best practices (Rob Hyndman's "Forecasting: Principles and Practice")

---

### TD-005: MLflow Experiment Tracking Integration

**Decision**: Log all training runs to MLflow with hyperparameters, metrics, and model artifacts

**Rationale**:
- Centralized experiment tracking for reproducibility
- Model registry for production model versioning
- Artifact storage (model checkpoints, scalers, feature transformers)
- Comparison UI for hyperparameter tuning
- Audit trail for model governance

**Implementation Details**:
```python
# MLflow logging structure
import mlflow

with mlflow.start_run(run_name=f"{model_type}_{symbol}_{horizon}"):
    # Log hyperparameters
    mlflow.log_params(hyperparameters)

    # Log metrics during training
    mlflow.log_metrics({"mpe": mpe, "rmse": rmse, "mae": mae, "mape": mape})

    # Log model artifacts
    mlflow.pytorch.log_model(lstm_model, "lstm_model")
    mlflow.xgboost.log_model(xgb_model, "xgboost_model")
    mlflow.sklearn.log_model(scaler, "scaler")
```

**Alternatives Considered**:
- Weights & Biases: More features but adds external dependency
- TensorBoard: Limited to metrics visualization, no model registry
- Custom logging: Reinventing the wheel, MLflow is production-ready

**References**:
- MLflow documentation (https://mlflow.org/docs/latest/index.html)
- MLflow Model Registry

---

### TD-006: Inference Service Architecture

**Decision**: FastAPI endpoint with Redis caching and in-memory model loading

**Rationale**:
- FastAPI: Asynchronous, high-performance, automatic OpenAPI docs
- Redis caching: Cache forecasts with 5-minute TTL to reduce redundant computation
- In-memory models: Load models into memory on service startup (avoid disk I/O per request)
- Batch prediction: Support multiple symbols in single request for efficiency

**Implementation Details**:
```python
# Service initialization
class MLInferenceService:
    def __init__(self):
        self.models = self._load_production_models()  # Load once at startup
        self.redis_client = redis.Redis()
        self.cache_ttl = 300  # 5 minutes

    async def predict(self, symbol: str, horizon: str) -> Forecast:
        # Check cache first
        cached = await self._get_cached_forecast(symbol, horizon)
        if cached:
            return cached

        # Generate new forecast
        forecast = await self._generate_forecast(symbol, horizon)

        # Cache result
        await self._cache_forecast(symbol, horizon, forecast)
        return forecast
```

**Alternatives Considered**:
- Load models per request: Too slow (100-500ms model loading overhead)
- No caching: Wasteful recomputation for frequent requests
- Separate inference service: Over-engineering for initial implementation

**References**:
- FastAPI documentation
- Redis caching patterns

---

### TD-007: Model Evaluation Metrics

**Decision**: Use MPE, RMSE, MAE, MAPE with directional accuracy as primary metrics

**Rationale**:
- **MPE (Mean Percentage Error)**: Detects systematic bias (over/under-prediction)
- **RMSE (Root Mean Squared Error)**: Penalizes large errors more than MAE
- **MAE (Mean Absolute Error)**: Easy to interpret in price units
- **MAPE (Mean Absolute Percentage Error)**: Scale-independent comparison across symbols
- **Directional Accuracy**: % of predictions with correct direction (up/down) - critical for trading

**Implementation Details**:
```python
# Metric calculations
def calculate_metrics(y_true, y_pred):
    mpe = np.mean((y_true - y_pred) / y_true) * 100
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100

    # Directional accuracy
    direction_true = np.sign(y_true - y_true_lagged)
    direction_pred = np.sign(y_pred - y_true_lagged)
    directional_accuracy = np.mean(direction_true == direction_pred) * 100

    return {"mpe": mpe, "rmse": rmse, "mae": mae, "mape": mape, "dir_acc": directional_accuracy}
```

**Alternatives Considered**:
- R-squared: Not appropriate for time series forecasting (assumes IID residuals)
- Custom loss functions: Reserved for future optimization

**References**:
- scikit-learn metrics module
- Financial forecasting evaluation literature

---

### TD-008: Hyperparameter Configuration Management

**Decision**: YAML configuration files per model type with environment overrides

**Rationale**:
- Configuration over code: Easy to modify hyperparameters without code changes
- Version control: Track hyperparameter changes in git
- Environment-specific: Development vs production settings
- Validation: Pydantic schemas validate config structure

**Implementation Details**:
```yaml
# config/ml/lstm_config.yaml
model:
  type: "lstm"
  num_layers: 2
  hidden_size: 128
  dropout: 0.2
  bidirectional: true
  attention: true

training:
  learning_rate: 0.001
  batch_size: 64
  max_epochs: 100
  early_stopping_patience: 10

features:
  lookback_window: 60  # 60 minutes = 1 hour
  forecast_horizons: [1, 4, 24]  # hours
  include_exogenous: true
```

**Alternatives Considered**:
- Hardcoded hyperparameters: Inflexible, requires code changes
- Database storage: Over-engineering, YAML files sufficient

**References**:
- Pydantic for config validation
- PyYAML for parsing

---

### TD-009: Database Schema for Forecasts

**Decision**: PostgreSQL table with composite indexes on (symbol, timestamp, horizon, model_version)

**Rationale**:
- Composite index: Fast queries for latest forecast per symbol/horizon
- Model version tracking: Essential for A/B testing and rollback
- Confidence intervals: Store prediction ranges for uncertainty quantification
- Time-series optimized: Partition by date for query performance

**Implementation Details**:
```python
# SQLAlchemy model
class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    forecast_horizon = Column(String(10), nullable=False)  # "1h", "4h", "24h"
    model_type = Column(String(20), nullable=False)  # "lstm", "xgboost"
    model_version = Column(String(50), nullable=False)

    predicted_value = Column(Float, nullable=False)
    lower_bound = Column(Float)  # Confidence interval lower
    upper_bound = Column(Float)  # Confidence interval upper
    confidence_score = Column(Float)  # Model confidence 0-1

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_forecast_lookup', 'symbol', 'timestamp', 'forecast_horizon', 'model_version'),
    )
```

**Alternatives Considered**:
- Separate table per horizon: Over-normalized, complicates queries
- Time-series database (TimescaleDB): Not needed for forecast data volume

**References**:
- SQLAlchemy documentation
- PostgreSQL indexing best practices

---

### TD-010: Model Deployment Strategy

**Decision**: Promote models to production via MLflow Model Registry with stage transitions

**Rationale**:
- Controlled promotion: Development → Staging → Production stages
- Rollback capability: Archive previous production models
- A/B testing: Run multiple production models simultaneously
- Audit trail: Track who promoted which model and when

**Implementation Details**:
```python
# Model promotion workflow
from mlflow.tracking import MlflowClient

client = MlflowClient()

# Promote model to staging
client.transition_model_version_stage(
    name="lstm_forecaster_crudeOIL_1h",
    version=5,
    stage="Staging"
)

# After validation, promote to production
client.transition_model_version_stage(
    name="lstm_forecaster_crudeOIL_1h",
    version=5,
    stage="Production"
)

# Load production model in inference service
production_model = mlflow.pytorch.load_model(
    f"models:/lstm_forecaster_crudeOIL_1h/Production"
)
```

**Alternatives Considered**:
- Manual file copying: Error-prone, no audit trail
- Database flags: Doesn't leverage MLflow's built-in capabilities

**References**:
- MLflow Model Registry documentation

---

## Open Questions & Future Research

### FQ-001: Ensemble Method Selection
**Question**: How should we combine LSTM and XGBoost predictions?

**Options**:
1. Simple average (equal weight)
2. Weighted average (based on validation performance)
3. Stacking (meta-model learns combination)

**Recommendation**: Start with weighted average based on RMSE, implement stacking in Phase 2 if needed

---

### FQ-002: Automated Hyperparameter Tuning
**Question**: Should we implement automated hyperparameter optimization with Optuna?

**Options**:
1. Manual tuning with fixed hyperparameters
2. Grid search (exhaustive but slow)
3. Bayesian optimization with Optuna

**Recommendation**: Manual tuning for MVP, add Optuna in future enhancement (marked as Out of Scope in spec)

---

### FQ-003: Model Retraining Frequency
**Question**: How often should production models be retrained?

**Options**:
1. Daily (fresh data, high compute cost)
2. Weekly (balanced approach)
3. On-demand (when performance degrades)

**Recommendation**: Weekly scheduled retraining + on-demand when MPE exceeds 5% threshold

---

## References

1. **PyTorch Documentation**: https://pytorch.org/docs/stable/index.html
2. **XGBoost Documentation**: https://xgboost.readthedocs.io/
3. **MLflow Documentation**: https://mlflow.org/docs/latest/
4. **Forecasting: Principles and Practice** (Rob Hyndman): https://otexts.com/fpp3/
5. **Temporal Fusion Transformer Paper**: https://arxiv.org/abs/1912.09363
6. **Time Series Cross-Validation**: https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split

---

## Summary

This research document resolves 10 critical technical decisions for the ML Forecasting Pipeline:

1. ✅ LSTM architecture (bidirectional, attention, 2 layers)
2. ✅ XGBoost feature engineering (lag, rolling, indicators)
3. ✅ Exogenous variable integration (DXY, VIX, news)
4. ✅ Walk-forward validation strategy
5. ✅ MLflow experiment tracking
6. ✅ FastAPI + Redis inference service
7. ✅ Evaluation metrics (MPE, RMSE, MAE, MAPE, directional accuracy)
8. ✅ YAML configuration management
9. ✅ PostgreSQL forecast schema
10. ✅ MLflow Model Registry deployment

All technical decisions are informed by financial forecasting best practices, production system requirements, and the RiseTrader constitution principles. Implementation can now proceed with confidence that these choices align with the feature specification and overall system architecture.
