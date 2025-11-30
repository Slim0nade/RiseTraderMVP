# Quickstart: SOTA Models Integration

**Feature**: 005-ml-sota-integration | **Date**: 2025-11-30
**Purpose**: Developer guide for setting up, deploying, and using SOTA forecasting models

## Prerequisites

Before starting, ensure you have:
- ✅ Feature 003-ml-forecasting-pipeline fully operational
- ✅ Python 3.11+ environment
- ✅ PostgreSQL 15+ with existing schema
- ✅ Redis 7+ for caching
- ✅ Docker and Docker Compose installed
- ✅ GPU with CUDA support (optional, CPU fallback available)

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Install SOTA Dependencies](#2-install-sota-dependencies)
3. [Database Migration](#3-database-migration)
4. [Train Your First SOTA Model](#4-train-your-first-sota-model)
5. [Deploy Model to Production](#5-deploy-model-to-production)
6. [Configure Model Selection](#6-configure-model-selection)
7. [Run A/B Test](#7-run-ab-test)
8. [Monitor Performance](#8-monitor-performance)

---

## 1. Environment Setup

### Clone and Activate Branch

```bash
cd /path/to/RiseTraderMVP
git checkout 005-ml-sota-integration
git pull origin 005-ml-sota-integration
```

### Activate Virtual Environment

```bash
# Create virtual environment (if not exists)
python3.11 -m venv venv

# Activate
source venv/bin/activate  # Linux/macOS
# OR
venv\Scripts\activate  # Windows
```

### Verify Existing Infrastructure

```bash
# Check PostgreSQL connection
docker-compose exec postgres psql -U risetrader -c "SELECT version();"

# Check Redis connection
docker-compose exec redis redis-cli ping
# Expected output: PONG

# Check API service
curl http://localhost:8003/health
# Expected: {"status": "healthy"}
```

---

## 2. Install SOTA Dependencies

### Update Requirements

Add SOTA model dependencies to `requirements.txt`:

```bash
# SOTA Models (005-ml-sota-integration)
pytorch-forecasting>=1.0.0      # TFT model
neuralforecast>=1.6.0           # TCN, BiGRU utilities
stable-baselines3>=2.1.0        # PPO reinforcement learning
gymnasium>=0.29.0               # RL environment
PyWavelets>=1.4.0               # FEDformer signal decomposition
EMD-signal>=1.4.0               # Empirical Mode Decomposition
einops>=0.7.0                   # Tensor operations
rotary-embedding-torch>=0.3.0  # Rotary positional encoding
```

### Install Dependencies

```bash
pip install -r requirements.txt

# Verify installation
python -c "import pytorch_forecasting; print('pytorch-forecasting:', pytorch_forecasting.__version__)"
python -c "import stable_baselines3; print('stable-baselines3:', stable_baselines3.__version__)"
```

### GPU Support (Optional)

```bash
# Check GPU availability
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"

# If False and you have NVIDIA GPU, install CUDA toolkit
# See: https://pytorch.org/get-started/locally/
```

---

## 3. Database Migration

### Run Alembic Migration

```bash
# Generate migration for new tables
alembic revision --autogenerate -m "Add SOTA integration tables"

# Review migration file
cat alembic/versions/*_add_sota_integration_tables.py

# Apply migration
alembic upgrade head

# Verify new tables
docker-compose exec postgres psql -U risetrader -d risetrader -c "\dt model_*"
```

**Expected New Tables**:
- `model_performance_snapshots`
- `model_selection_rules`
- `market_regimes`
- `agent_model_selections`
- `ab_test_configurations`
- `ab_test_metrics`

### Seed Default Selection Rules

```bash
# Create default model selection rules
python scripts/seed_default_selection_rules.py

# Verify
curl http://localhost:8003/api/v1/model-selection/rules | jq .
```

**Example Default Rules**:
1. **trending_short_term_tcn** (Priority: 10): Use TCN for trending markets + 1h forecasts
2. **volatile_ensemble** (Priority: 20): Use MoE for volatile/crisis regimes
3. **default_best_overall** (Priority: 1000): Fallback to best-performing model overall

---

## 4. Train Your First SOTA Model

### Example: Train TCN Model for CrudeOIL

Create training script `scripts/train_tcn_crude_oil.py`:

```python
import asyncio
from datetime import datetime, timedelta
from src.ml.models import ModelType, create_model
from src.services.ml_training_service import MLTrainingService
from src.database.repositories.training_run_repository import TrainingRunRepository
from src.database.repositories.model_metrics_repository import ModelMetricsRepository
from src.ml.data.market_data_loader import MarketDataLoader

async def main():
    # Initialize services
    data_loader = MarketDataLoader()
    training_run_repo = TrainingRunRepository()
    metrics_repo = ModelMetricsRepository()

    service = MLTrainingService(
        data_loader=data_loader,
        training_run_repo=training_run_repo,
        metrics_repo=metrics_repo
    )

    # Training configuration
    config = {
        'model': {
            'num_layers': 4,
            'num_filters': 64,
            'kernel_size': 3,
            'dropout': 0.1
        },
        'data': {
            'train_window_days': 90,
            'sequence_length': 168  # 1 week of hourly data
        },
        'features': {
            'lag_periods': [1, 2, 3, 6, 12, 24],
            'use_technical_indicators': True
        },
        'training': {
            'epochs': 50,
            'batch_size': 32,
            'learning_rate': 0.001,
            'early_stopping_patience': 10
        }
    }

    # Train model
    print("Training TCN model for CrudeOIL...")
    result = await service.train_model(
        symbol='CrudeOIL',
        model_type='tcn',
        config=config,
        run_name='tcn_crude_oil_1h_v1'
    )

    print(f"Training complete!")
    print(f"Training run ID: {result['training_run_id']}")
    print(f"Model version: {result['model_version']}")
    print(f"Metrics: {result['metrics']}")

if __name__ == '__main__':
    asyncio.run(main())
```

### Run Training

```bash
python scripts/train_tcn_crude_oil.py
```

**Expected Output**:
```
Training TCN model for CrudeOIL...
Epoch 1/50: loss=2.456, val_loss=2.123
Epoch 2/50: loss=1.987, val_loss=1.856
...
Training complete!
Training run ID: 42
Model version: v1.0.0
Metrics: {'mpe': 2.89, 'rmse': 1.24, 'mae': 0.98, 'directional_accuracy': 68.7}
```

### View Training in MLflow

```bash
# Start MLflow UI
mlflow ui --backend-store-uri sqlite:///mlflow.db

# Open browser
open http://localhost:5000
```

Navigate to Experiments → tcn_crude_oil_1h_v1 → View metrics and artifacts

---

## 5. Deploy Model to Production

### Verify Model Available in Registry

```bash
# List available models
curl http://localhost:8003/api/v1/ml/models | jq '.[] | select(.model_type == "tcn")'
```

### Test Inference

```bash
# Make inference request
curl -X POST http://localhost:8003/api/v1/ml/predict \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "CrudeOIL",
    "model_type": "tcn",
    "forecast_horizons": ["1h"],
    "include_confidence_intervals": true
  }' | jq .
```

**Expected Response**:
```json
{
  "symbol": "CrudeOIL",
  "timestamp": "2025-11-30T10:00:00Z",
  "forecasts": [
    {
      "forecast_horizon": "1h",
      "model_type": "tcn",
      "model_version": "v1.0.0",
      "predicted_value": 75.32,
      "lower_bound": 74.12,
      "upper_bound": 76.52,
      "confidence_score": 0.87,
      "inference_time_ms": 32.5
    }
  ],
  "inference_time_ms": 35.2,
  "cache_hit": false
}
```

### Promote Model to Active Status

```bash
# Update model status
curl -X PUT http://localhost:8003/api/v1/ml/models/tcn/v1.0.0/status \
  -H "Content-Type: application/json" \
  -d '{"status": "active"}' | jq .
```

---

## 6. Configure Model Selection

### Create Selection Rule for TCN

```bash
curl -X POST http://localhost:8003/api/v1/model-selection/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "tcn_trending_1h",
    "priority": 10,
    "condition": "market_regime IN ('\'trending_up\'', '\'trending_down\'') AND forecast_horizon='\''1h'\''",
    "recommended_models": ["tcn", "lstm"],
    "fallback_models": ["xgboost"],
    "enabled": true,
    "description": "Use TCN for trending markets with 1h forecasts, fallback to LSTM/XGBoost"
  }' | jq .
```

### Test Model Selection

```bash
# Request recommendation
curl -X POST http://localhost:8003/api/v1/model-selection/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "CrudeOIL",
    "forecast_horizon": "1h",
    "agent_id": "test_agent"
  }' | jq .
```

**Expected Response**:
```json
{
  "recommended_model": "tcn",
  "fallback_models": ["lstm", "xgboost"],
  "selection_reason": "Market regime is trending_up (confidence: 0.87). TCN has 15% better MPE than LSTM over last 24h for 1h forecasts. Matched rule: tcn_trending_1h",
  "market_regime": {
    "regime_type": "trending_up",
    "confidence_score": 0.87,
    "detected_at": "2025-11-30T10:00:00Z"
  },
  "performance_snapshot": {
    "tcn": {
      "mpe": 2.89,
      "rmse": 1.24,
      "directional_accuracy": 68.7,
      "latency_p95_ms": 32
    },
    "lstm": {
      "mpe": 3.42,
      "rmse": 1.58,
      "directional_accuracy": 64.3,
      "latency_p95_ms": 28
    }
  },
  "matched_rule": {
    "rule_id": 42,
    "rule_name": "tcn_trending_1h",
    "condition": "market_regime IN ('trending_up', 'trending_down') AND forecast_horizon='1h'"
  },
  "selection_latency_ms": 6.2
}
```

---

## 7. Run A/B Test

### Create A/B Test: TCN vs LSTM

```bash
curl -X POST http://localhost:8003/api/v1/ab-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_name": "TCN vs LSTM for CrudeOIL 1h - Week 1",
    "test_type": "model",
    "symbol": "CrudeOIL",
    "forecast_horizon": "1h",
    "model_a": "lstm",
    "model_b": "tcn",
    "traffic_split_pct": 20,
    "success_criteria": {
      "min_sample_size": 1000,
      "min_duration_days": 7,
      "mpe_improvement_threshold": 10
    },
    "auto_promote_threshold": 15
  }' | jq .
```

**Response**:
```json
{
  "id": 1,
  "test_name": "TCN vs LSTM for CrudeOIL 1h - Week 1",
  "status": "draft",
  "created_at": "2025-11-30T10:00:00Z",
  ...
}
```

### Start A/B Test

```bash
# Activate test
TEST_ID=1
curl -X POST http://localhost:8003/api/v1/ab-tests/$TEST_ID/start | jq .
```

### Monitor Real-Time Metrics

```bash
# View current metrics
curl http://localhost:8003/api/v1/ab-tests/$TEST_ID/metrics | jq .
```

**Expected Output**:
```json
{
  "test_id": 1,
  "status": "active",
  "metrics": [
    {
      "model_type": "lstm",
      "request_count": 8123,
      "avg_mpe": 3.42,
      "avg_rmse": 1.58,
      "latency_p95_ms": 28.5,
      "error_rate": 0.12
    },
    {
      "model_type": "tcn",
      "request_count": 2031,
      "avg_mpe": 2.89,
      "avg_rmse": 1.24,
      "latency_p95_ms": 32.1,
      "error_rate": 0.08
    }
  ]
}
```

### View Results After 7 Days

```bash
# Get statistical analysis
curl http://localhost:8003/api/v1/ab-tests/$TEST_ID/results | jq .
```

**Expected Output**:
```json
{
  "test_id": 1,
  "status": "active",
  "duration_days": 7.2,
  "model_a": {
    "model_type": "lstm",
    "request_count": 8452,
    "avg_mpe": 3.42,
    ...
  },
  "model_b": {
    "model_type": "tcn",
    "request_count": 2113,
    "avg_mpe": 2.89,
    ...
  },
  "comparison": {
    "mpe_improvement_pct": 15.5,
    "rmse_improvement_pct": 21.5
  },
  "statistical_significance": {
    "mpe_p_value": 0.0012,
    "mpe_significant": true,
    "test_method": "mann_whitney_u",
    "confidence_level": 0.95
  },
  "recommendation": "PROMOTE",
  "recommendation_reason": "Model B (TCN) shows statistically significant improvement in MPE (15.5%) and RMSE (21.5%) with acceptable latency tradeoff (+12.6%). Exceeds auto-promotion threshold of 15%."
}
```

### Complete Test

```bash
# Mark test as complete
curl -X POST http://localhost:8003/api/v1/ab-tests/$TEST_ID/complete | jq .
```

---

## 8. Monitor Performance

### View Model Performance Dashboard

```bash
# Get performance for all models
curl "http://localhost:8003/api/v1/model-selection/performance?symbol=CrudeOIL&forecast_horizon=1h&time_window=24h" | jq .
```

**Expected Output**:
```json
{
  "symbol": "CrudeOIL",
  "forecast_horizon": "1h",
  "time_window": "24h",
  "models": {
    "lstm": {
      "mpe": 3.42,
      "rmse": 1.58,
      "directional_accuracy": 64.3,
      "latency_p95_ms": 28,
      "sample_count": 1432
    },
    "xgboost": {
      "mpe": 3.78,
      "rmse": 1.67,
      "directional_accuracy": 62.1,
      "latency_p95_ms": 15,
      "sample_count": 1398
    },
    "tcn": {
      "mpe": 2.89,
      "rmse": 1.24,
      "directional_accuracy": 68.7,
      "latency_p95_ms": 32,
      "sample_count": 1521
    }
  },
  "last_updated": "2025-11-30T10:15:00Z"
}
```

### View Agent Selection Audit Log

```bash
# Get recent selections
curl "http://localhost:8003/api/v1/model-selection/audit?agent_id=signal_generator_001&limit=10" | jq .
```

### Grafana Dashboards

Access real-time monitoring dashboards:

```bash
# Open Grafana
open http://localhost:3001

# Default credentials
# Username: admin
# Password: admin
```

**Available Dashboards**:
- **Model Performance Comparison**: MPE, RMSE, MAE trends by model
- **Model Selection Frequency**: Which models are selected most often
- **Inference Latency**: p50, p95, p99 latency by model
- **A/B Test Progress**: Live metrics for active tests
- **Agent Decisions**: Model selection patterns by agent and market regime

---

## Troubleshooting

### Issue: SOTA Model Import Fails

**Error**: `ImportError: No module named 'pytorch_forecasting'`

**Solution**:
```bash
pip install pytorch-forecasting>=1.0.0
```

### Issue: GPU Out of Memory

**Error**: `RuntimeError: CUDA out of memory`

**Solution**:
```python
# Reduce batch size in training config
config = {
    'training': {
        'batch_size': 16  # Instead of 32
    }
}

# OR use CPU fallback
import torch
torch.device('cpu')
```

### Issue: Model Selection Returns Default Model

**Symptom**: Always returns LSTM despite TCN rule configured

**Solution**:
```bash
# Check market regime detection
curl "http://localhost:8003/api/v1/market-regime?symbol=CrudeOIL" | jq .

# Verify rule condition matches current regime
curl "http://localhost:8003/api/v1/model-selection/rules" | jq '.[] | select(.rule_name == "tcn_trending_1h")'

# Check rule priority (lower = higher priority)
# Ensure your rule has lower priority than default (< 1000)
```

### Issue: A/B Test Shows Overlapping Error

**Error**: `Active test already exists for CrudeOIL:1h`

**Solution**:
```bash
# List active tests
curl "http://localhost:8003/api/v1/ab-tests?status=active&symbol=CrudeOIL" | jq .

# Pause conflicting test
curl -X POST http://localhost:8003/api/v1/ab-tests/{conflicting_test_id}/pause
```

---

## Next Steps

After completing this quickstart, you can:

1. **Train Additional Models**
   - BiGRU: `scripts/train_bigru_crude_oil.py`
   - FEDformer: `scripts/train_fedformer_crude_oil.py`
   - TFT: `scripts/train_tft_crude_oil.py`

2. **Configure Advanced Selection Rules**
   - Combine multiple conditions (regime + time of day + economic events)
   - Use performance thresholds (e.g., "tcn_mpe_24h < 3.0")
   - Create fallback chains for robustness

3. **Run Multi-Dimensional A/B Tests**
   - Feature-level: Test exogenous variables impact
   - Horizon-level: Compare model performance across 1h, 4h, 24h

4. **Integrate with Trading Agents**
   - Update agents to use model selection API
   - Implement agent-specific selection preferences
   - Monitor agent decision patterns

5. **Optimize Performance**
   - Enable Redis caching for selection rules
   - Tune database indexes for query performance
   - Profile inference latency bottlenecks

---

## Resources

- **API Documentation**: http://localhost:8003/docs
- **MLflow UI**: http://localhost:5000
- **Grafana Dashboards**: http://localhost:3001
- **Spec Document**: [spec.md](./spec.md)
- **Implementation Plan**: [plan.md](./plan.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Contracts**: [contracts/](./contracts/)

---

**Quickstart Complete!** You're now ready to develop and deploy SOTA forecasting models in RiseTrader.
