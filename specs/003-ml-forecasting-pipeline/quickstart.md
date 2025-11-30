# Quickstart Guide: ML Forecasting Pipeline

**Feature**: 003-ml-forecasting-pipeline
**Created**: 2025-11-29
**Phase**: Phase 1 (Design)

## Purpose

This quickstart guide provides end-to-end integration scenarios for the ML Forecasting Pipeline. It demonstrates how trading agents, analysts, and system components interact with the ML services for training models and generating forecasts.

---

## Prerequisites

Before running these scenarios, ensure:

✅ PostgreSQL 15+ running with `forecasts`, `training_runs`, `model_metrics`, `exogenous_variables` tables
✅ Redis 7+ running for forecast caching
✅ MLflow server running for experiment tracking
✅ FastAPI server running on port 8003
✅ Historical market data available in `market_data` table (at least 30 days for CrudeOIL)
✅ Python dependencies installed: PyTorch, XGBoost, scikit-learn, MLflow, FastAPI, pandas

---

## Scenario 1: Complete Model Training Workflow

**Goal**: Train an LSTM model from scratch, evaluate performance, and promote to production

### Step 1.1: Prepare Configuration

Create LSTM configuration file at `config/ml/lstm_config.yaml`:

```yaml
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
  lookback_window: 60
  forecast_horizons: ["1h", "4h", "24h"]
  include_exogenous: true
  exogenous_variables: ["DXY", "VIX", "NEWS_EVENT"]
  use_technical_indicators: true
  indicators: ["rsi_14", "macd", "bb_upper", "bb_lower", "atr"]

data:
  train_window_days: 30
  val_window_days: 5
  test_window_days: 5
  slide_days: 5
```

### Step 1.2: Start Training via API

**Request**:
```bash
curl -X POST http://localhost:8003/api/v1/ml/train \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "run_name": "lstm_crudeOIL_1h_production_v1",
    "symbol": "CrudeOIL",
    "model_type": "lstm",
    "async_training": true
  }'
```

**Response**:
```json
{
  "training_run_id": 101,
  "run_name": "lstm_crudeOIL_1h_production_v1",
  "status": "running",
  "mlflow_run_id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "estimated_duration_minutes": 28,
  "message": "Training started successfully. Monitor progress at MLflow UI."
}
```

### Step 1.3: Monitor Training Progress

**Option A: Poll API for status**
```bash
curl http://localhost:8003/api/v1/ml/training-runs/101 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (in progress)**:
```json
{
  "id": 101,
  "run_name": "lstm_crudeOIL_1h_production_v1",
  "symbol": "CrudeOIL",
  "model_type": "lstm",
  "mlflow_run_id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "status": "running",
  "started_at": "2025-11-29T10:00:00Z",
  "duration_seconds": 1245,
  "created_at": "2025-11-29T09:59:45Z"
}
```

**Response (completed)**:
```json
{
  "id": 101,
  "run_name": "lstm_crudeOIL_1h_production_v1",
  "symbol": "CrudeOIL",
  "model_type": "lstm",
  "mlflow_run_id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "status": "completed",
  "started_at": "2025-11-29T10:00:00Z",
  "completed_at": "2025-11-29T10:28:35Z",
  "duration_seconds": 1715,
  "final_metrics": {
    "mpe": -0.52,
    "rmse": 0.38,
    "mae": 0.29,
    "mape": 2.1,
    "directional_accuracy": 61.5
  },
  "model_version": "v1.0.0",
  "created_at": "2025-11-29T09:59:45Z"
}
```

**Option B: View in MLflow UI**
```bash
# Navigate to MLflow UI
open http://localhost:5000

# Filter experiments by run_name: "lstm_crudeOIL_1h_production_v1"
# View real-time metrics, parameters, and artifacts
```

### Step 1.4: Evaluate Model Metrics

```bash
curl http://localhost:8003/api/v1/ml/models/v1.0.0/metrics?forecast_horizon=1h \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response**:
```json
[
  {
    "id": 501,
    "model_type": "lstm",
    "model_version": "v1.0.0",
    "symbol": "CrudeOIL",
    "forecast_horizon": "1h",
    "mpe": -0.52,
    "rmse": 0.38,
    "mae": 0.29,
    "mape": 2.1,
    "directional_accuracy": 61.5,
    "evaluation_date": "2025-11-29T10:28:35Z",
    "sample_size": 720
  }
]
```

### Step 1.5: Promote Model to Production

**Using MLflow Python Client**:
```python
from mlflow.tracking import MlflowClient

client = MlflowClient()

# Transition model to staging
client.transition_model_version_stage(
    name="lstm_forecaster_CrudeOIL_1h",
    version=1,
    stage="Staging"
)

# After validation in staging, promote to production
client.transition_model_version_stage(
    name="lstm_forecaster_CrudeOIL_1h",
    version=1,
    stage="Production"
)
```

**Verification**:
```python
# Verify production model is loaded in inference service
import mlflow

production_model = mlflow.pytorch.load_model(
    f"models:/lstm_forecaster_CrudeOIL_1h/Production"
)
print(f"Production model loaded: {production_model}")
```

**Expected Metrics**:
- Training completion time: ≤30 minutes (FR-SC-001)
- MPE: <3% (FR-SC-002)
- RMSE: <0.5 normalized scale (FR-SC-002)

---

## Scenario 2: Real-Time Forecast Generation for Trading Agents

**Goal**: Trading agents request ML forecasts for decision-making with <50ms latency

### Step 2.1: MLPredictionAgent Requests Forecast

**Python Code (Agent Integration)**:
```python
import httpx
from datetime import datetime

async def get_forecast_for_trading_decision(symbol: str, horizons: list[str]) -> dict:
    """
    Called by MLPredictionAgent to get forecasts for trading signal generation
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8003/api/v1/ml/predict",
            json={
                "symbol": symbol,
                "forecast_horizons": horizons,
                "model_type": "ensemble",
                "include_confidence_intervals": True
            },
            headers={"Authorization": f"Bearer {JWT_TOKEN}"}
        )
        return response.json()

# Usage in MLPredictionAgent
forecast_data = await get_forecast_for_trading_decision("CrudeOIL", ["1h", "4h"])
```

**API Request**:
```bash
curl -X POST http://localhost:8003/api/v1/ml/predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "symbol": "CrudeOIL",
    "forecast_horizons": ["1h", "4h", "24h"],
    "model_type": "ensemble",
    "include_confidence_intervals": true
  }'
```

**API Response (First Request - Cache Miss)**:
```json
{
  "symbol": "CrudeOIL",
  "timestamp": "2025-11-29T14:00:00Z",
  "forecasts": [
    {
      "id": 12345,
      "symbol": "CrudeOIL",
      "timestamp": "2025-11-29T14:00:00Z",
      "forecast_horizon": "1h",
      "model_type": "ensemble",
      "model_version": "v1.0.0",
      "predicted_value": 78.45,
      "lower_bound": 77.80,
      "upper_bound": 79.10,
      "confidence_score": 0.87,
      "created_at": "2025-11-29T13:59:55Z",
      "inference_time_ms": 42.5
    },
    {
      "id": 12346,
      "forecast_horizon": "4h",
      "predicted_value": 78.90,
      "confidence_score": 0.79,
      "inference_time_ms": 45.2
    },
    {
      "id": 12347,
      "forecast_horizon": "24h",
      "predicted_value": 79.80,
      "confidence_score": 0.65,
      "inference_time_ms": 48.0
    }
  ],
  "inference_time_ms": 48.2,
  "cache_hit": false
}
```

**API Response (Subsequent Request - Cache Hit)**:
```json
{
  "symbol": "CrudeOIL",
  "timestamp": "2025-11-29T14:00:00Z",
  "forecasts": [...],
  "inference_time_ms": 2.1,
  "cache_hit": true
}
```

### Step 2.2: Agent Decision Logic Using Forecast

```python
def generate_trading_signal(forecast_data: dict) -> str:
    """
    SignalGeneratorAgent uses forecast to determine trading signal
    """
    forecast_1h = next(f for f in forecast_data["forecasts"] if f["forecast_horizon"] == "1h")

    # Get current price
    current_price = get_latest_price("CrudeOIL")

    # Calculate expected return
    predicted_return = (forecast_1h["predicted_value"] - current_price) / current_price

    # Decision logic
    if predicted_return > 0.005 and forecast_1h["confidence_score"] > 0.75:
        return "BUY"
    elif predicted_return < -0.005 and forecast_1h["confidence_score"] > 0.75:
        return "SELL"
    else:
        return "HOLD"

signal = generate_trading_signal(forecast_data)
print(f"Trading signal: {signal}")
```

**Expected Performance**:
- Inference latency: ≤50ms p95 (FR-SC-003)
- Cache hit latency: <5ms
- Concurrent requests: 100 without degradation (FR-SC-003)

---

## Scenario 3: Model Performance Monitoring and Degradation Detection

**Goal**: Automatically detect when production models require retraining

### Step 3.1: Continuous Forecast Tracking

**Python Service (Background Task)**:
```python
import asyncio
from datetime import datetime, timedelta

async def track_forecast_accuracy():
    """
    Background task that compares forecasts to actual prices
    Runs every hour to evaluate recent forecasts
    """
    while True:
        await asyncio.sleep(3600)  # Run every hour

        # Get forecasts from 1 hour ago
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        forecasts = await forecast_repository.get_forecasts_by_timestamp(
            symbol="CrudeOIL",
            timestamp=one_hour_ago,
            horizon="1h"
        )

        # Get actual prices
        actual_prices = await market_data_repository.get_ohlc_at_timestamp(
            symbol="CrudeOIL",
            timestamp=datetime.utcnow()
        )

        # Calculate errors
        errors = []
        for forecast in forecasts:
            error = abs(forecast.predicted_value - actual_prices.close) / actual_prices.close
            errors.append(error)

        # Calculate MAPE
        mape = sum(errors) / len(errors) * 100

        # Alert if degraded
        if mape > 5.0:  # Threshold from FR-SC-005
            await send_alert(
                message=f"Model performance degraded! MAPE: {mape:.2f}% (threshold: 5%)",
                model_version=forecasts[0].model_version,
                symbol="CrudeOIL"
            )
```

### Step 3.2: Alert Handler

```python
async def send_alert(message: str, model_version: str, symbol: str):
    """
    Send alert to analysts when model performance degrades
    """
    alert_data = {
        "severity": "WARNING",
        "message": message,
        "model_version": model_version,
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "recommended_action": "Trigger model retraining",
        "retraining_config": {
            "run_name": f"lstm_{symbol}_1h_retrain_{datetime.utcnow().strftime('%Y%m%d')}",
            "symbol": symbol,
            "model_type": "lstm"
        }
    }

    # Send to monitoring system
    await monitoring_client.send_alert(alert_data)

    # Log to database
    await alert_repository.create_alert(alert_data)
```

**Expected Behavior**:
- Detection time: ≤3 hours (FR-SC-005)
- Automated alert with retraining recommendation
- Alert includes specific metrics exceeding thresholds

---

## Scenario 4: A/B Testing Multiple Model Versions

**Goal**: Compare LSTM and XGBoost models in production before promoting best performer

### Step 4.1: Deploy Both Models to Staging

```python
from mlflow.tracking import MlflowClient

client = MlflowClient()

# Promote LSTM to staging
client.transition_model_version_stage(
    name="lstm_forecaster_CrudeOIL_1h",
    version=2,
    stage="Staging"
)

# Promote XGBoost to staging
client.transition_model_version_stage(
    name="xgboost_forecaster_CrudeOIL_1h",
    version=1,
    stage="Staging"
)
```

### Step 4.2: Run Parallel Predictions

```python
async def ab_test_models(symbol: str, horizon: str, num_predictions: int = 100):
    """
    Generate predictions from both models and compare performance
    """
    lstm_model = mlflow.pytorch.load_model("models:/lstm_forecaster_CrudeOIL_1h/Staging")
    xgb_model = mlflow.xgboost.load_model("models:/xgboost_forecaster_CrudeOIL_1h/Staging")

    lstm_errors = []
    xgb_errors = []

    for _ in range(num_predictions):
        # Get current market data
        market_data = await get_latest_market_data(symbol)

        # Generate forecasts
        lstm_forecast = await generate_forecast(lstm_model, market_data)
        xgb_forecast = await generate_forecast(xgb_model, market_data)

        # Wait for actual price
        await asyncio.sleep(3600)  # Wait 1 hour
        actual_price = await get_latest_price(symbol)

        # Calculate errors
        lstm_error = abs(lstm_forecast - actual_price) / actual_price
        xgb_error = abs(xgb_forecast - actual_price) / actual_price

        lstm_errors.append(lstm_error)
        xgb_errors.append(xgb_error)

    # Compare performance
    lstm_mape = sum(lstm_errors) / len(lstm_errors) * 100
    xgb_mape = sum(xgb_errors) / len(xgb_errors) * 100

    print(f"LSTM MAPE: {lstm_mape:.2f}%")
    print(f"XGBoost MAPE: {xgb_mape:.2f}%")

    # Promote better model to production
    if lstm_mape < xgb_mape:
        client.transition_model_version_stage(
            name="lstm_forecaster_CrudeOIL_1h",
            version=2,
            stage="Production"
        )
        print("LSTM promoted to production")
    else:
        client.transition_model_version_stage(
            name="xgboost_forecaster_CrudeOIL_1h",
            version=1,
            stage="Production"
        )
        print("XGBoost promoted to production")
```

---

## Scenario 5: Exogenous Variable Integration

**Goal**: Train model with DXY, VIX, and news events to improve forecast accuracy

### Step 5.1: Populate Exogenous Variables Table

```python
import asyncio
import yfinance as yf
from datetime import datetime, timedelta

async def fetch_and_store_exogenous_data():
    """
    Fetch DXY, VIX data and store in database
    """
    # Fetch DXY (Dollar Index)
    dxy = yf.Ticker("DX-Y.NYB")
    dxy_data = dxy.history(period="1mo", interval="1h")

    for index, row in dxy_data.iterrows():
        await exogenous_repository.create_or_update(
            variable_name="DXY",
            timestamp=index,
            value=row['Close'],
            source="yahoo_finance"
        )

    # Fetch VIX (Volatility Index)
    vix = yf.Ticker("^VIX")
    vix_data = vix.history(period="1mo", interval="1h")

    for index, row in vix_data.iterrows():
        await exogenous_repository.create_or_update(
            variable_name="VIX",
            timestamp=index,
            value=row['Close'],
            source="yahoo_finance"
        )

    print("Exogenous data stored successfully")
```

### Step 5.2: Mark News Events

```python
async def mark_news_event(event_name: str, event_time: datetime):
    """
    Mark economic calendar events (NFP, CPI, FOMC) as binary flags
    """
    await exogenous_repository.create_or_update(
        variable_name="NEWS_EVENT",
        timestamp=event_time,
        value=None,  # Binary flag, value not needed
        is_event=True,
        source="economic_calendar"
    )

# Example: Mark NFP (Non-Farm Payrolls) release
await mark_news_event("NFP", datetime(2025, 11, 29, 13, 30))
```

### Step 5.3: Train Model with Exogenous Variables

```bash
curl -X POST http://localhost:8003/api/v1/ml/train \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "run_name": "lstm_crudeOIL_1h_with_exogenous_v1",
    "symbol": "CrudeOIL",
    "model_type": "lstm",
    "config_override": {
      "features": {
        "include_exogenous": true,
        "exogenous_variables": ["DXY", "VIX", "NEWS_EVENT"]
      }
    },
    "async_training": true
  }'
```

**Expected Improvement**:
- RMSE reduction: ≥15% compared to price-only models (FR-SC-006)

---

## Testing Checklist

Use this checklist to validate all integration scenarios:

### Training Pipeline
- [ ] LSTM model training completes in ≤30 minutes for 30-day dataset
- [ ] XGBoost model training completes in ≤30 minutes
- [ ] Training metrics logged to MLflow with all hyperparameters
- [ ] Model artifacts (model, scaler, transformers) saved correctly
- [ ] Training run status updates correctly (pending → running → completed)
- [ ] Failed training runs save error messages

### Inference Service
- [ ] Forecast generation returns results in ≤50ms (p95)
- [ ] Redis cache reduces latency to <5ms for cached forecasts
- [ ] Concurrent 100 requests handled without degradation
- [ ] Confidence intervals included when requested
- [ ] Forecasts stored in database with all metadata

### Model Evaluation
- [ ] Metrics (MPE, RMSE, MAE, MAPE, directional accuracy) calculated correctly
- [ ] Model comparison API returns sorted results by performance
- [ ] Walk-forward validation prevents data leakage

### Monitoring & Alerts
- [ ] Forecast accuracy tracked hourly
- [ ] Alerts triggered when MAPE >5% for 3 consecutive hours
- [ ] Alert includes retraining recommendations

### Exogenous Variables
- [ ] DXY and VIX data fetched and stored correctly
- [ ] News events marked as binary flags
- [ ] Models trained with exogenous variables show improved accuracy

---

## Next Steps

After completing these integration scenarios:

1. **Run `/speckit.tasks`** to generate implementation task breakdown
2. **Follow TDD approach**: Write tests for each scenario before implementation
3. **Implement in phases**:
   - Phase 1: Training pipeline (FR-001 to FR-006)
   - Phase 2: Inference service (FR-017 to FR-022)
   - Phase 3: Metrics and monitoring (FR-027 to FR-030)
   - Phase 4: Exogenous variables (FR-003, FR-023)
4. **Validate against success criteria** from [spec.md](./spec.md)

---

## Support

- **API Documentation**: http://localhost:8003/docs (Swagger UI)
- **MLflow UI**: http://localhost:5000
- **OpenAPI Spec**: [contracts/openapi.yaml](./contracts/openapi.yaml)
- **Data Model**: [data-model.md](./data-model.md)
- **Technical Decisions**: [research.md](./research.md)
