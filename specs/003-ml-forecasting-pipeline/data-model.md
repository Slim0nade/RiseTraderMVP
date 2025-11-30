# Data Model: ML Forecasting Pipeline

**Feature**: 003-ml-forecasting-pipeline
**Created**: 2025-11-29
**Phase**: Phase 1 (Design)

## Purpose

This document defines the complete data model for the ML Forecasting Pipeline, including database entities, API models, configuration schemas, and data flow between components. All schemas support the functional requirements from [spec.md](./spec.md) and technical decisions from [research.md](./research.md).

---

## Entity Relationship Diagram

```
┌──────────────────┐         ┌────────────────────┐
│   TrainingRun    │ 1     * │  ForecastModel     │
│                  ├─────────┤                    │
│ - run_id         │  creates│ - model_id         │
│ - symbol         │         │ - model_type       │
│ - config         │         │ - version          │
│ - status         │         │ - stage            │
└──────────────────┘         │ - metrics          │
                             └─────────┬──────────┘
                                       │ generates
                                       │ *
                             ┌─────────▼──────────┐
                             │     Forecast       │
                             │                    │
                             │ - forecast_id      │
                             │ - symbol           │
                             │ - timestamp        │
                             │ - horizon          │
                             │ - predicted_value  │
                             │ - confidence       │
                             └────────────────────┘

┌──────────────────┐         ┌────────────────────┐
│  FeatureSet      │ 1     * │  ExogenousVariable │
│                  ├─────────┤                    │
│ - feature_set_id │ includes│ - variable_id      │
│ - name           │         │ - variable_name    │
│ - features       │         │ - timestamp        │
└──────────────────┘         │ - value            │
                             └────────────────────┘

┌──────────────────┐
│  ModelMetrics    │
│                  │
│ - metrics_id     │
│ - model_version  │
│ - horizon        │
│ - mpe            │
│ - rmse           │
│ - mae            │
│ - mape           │
│ - dir_accuracy   │
└──────────────────┘
```

---

## Database Entities (PostgreSQL + SQLAlchemy)

### Entity 1: `forecasts` Table

**Purpose**: Store all ML-generated price forecasts for retrieval by trading agents and performance tracking

**SQLAlchemy Model**:
```python
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Forecast(Base):
    """ML-generated price forecast"""
    __tablename__ = "forecasts"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    forecast_horizon = Column(String(10), nullable=False)  # "1h", "4h", "24h"

    # Model information
    model_type = Column(String(20), nullable=False)  # "lstm", "xgboost", "ensemble"
    model_version = Column(String(50), nullable=False)
    mlflow_run_id = Column(String(100))  # Reference to MLflow run

    # Prediction values
    predicted_value = Column(Float, nullable=False)
    lower_bound = Column(Float)  # 95% confidence interval lower
    upper_bound = Column(Float)  # 95% confidence interval upper
    confidence_score = Column(Float)  # Model confidence 0.0-1.0

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    inference_time_ms = Column(Float)  # Latency tracking

    # Composite indexes for fast lookups
    __table_args__ = (
        Index('idx_forecast_lookup', 'symbol', 'timestamp', 'forecast_horizon', 'model_version'),
        Index('idx_forecast_latest', 'symbol', 'forecast_horizon', 'created_at'),
    )
```

**Pydantic API Model**:
```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ForecastCreate(BaseModel):
    """Request to create a forecast"""
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: datetime
    forecast_horizon: str = Field(..., regex="^(1h|4h|24h)$")
    model_type: str = Field(..., regex="^(lstm|xgboost|ensemble)$")
    model_version: str
    predicted_value: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)

class ForecastResponse(BaseModel):
    """Forecast returned by API"""
    id: int
    symbol: str
    timestamp: datetime
    forecast_horizon: str
    model_type: str
    model_version: str
    predicted_value: float
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    confidence_score: Optional[float]
    created_at: datetime
    inference_time_ms: Optional[float]

    class Config:
        from_attributes = True
```

**Example Data**:
```json
{
  "id": 12345,
  "symbol": "CrudeOIL",
  "timestamp": "2025-11-29T14:00:00Z",
  "forecast_horizon": "1h",
  "model_type": "lstm",
  "model_version": "v1.2.3",
  "predicted_value": 78.45,
  "lower_bound": 77.80,
  "upper_bound": 79.10,
  "confidence_score": 0.87,
  "created_at": "2025-11-29T13:59:55Z",
  "inference_time_ms": 42.5
}
```

---

### Entity 2: `training_runs` Table

**Purpose**: Track all model training executions for audit, debugging, and comparison

**SQLAlchemy Model**:
```python
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum
from sqlalchemy.dialects.postgresql import JSONB
import enum

class TrainingStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TrainingRun(Base):
    """Model training run record"""
    __tablename__ = "training_runs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    run_name = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    model_type = Column(String(20), nullable=False)
    mlflow_run_id = Column(String(100), unique=True)  # MLflow experiment run ID

    # Configuration (stored as JSON)
    hyperparameters = Column(JSONB, nullable=False)
    feature_config = Column(JSONB, nullable=False)
    training_config = Column(JSONB, nullable=False)

    # Execution status
    status = Column(Enum(TrainingStatus), default=TrainingStatus.PENDING, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)

    # Results
    final_metrics = Column(JSONB)  # {"mpe": -0.5, "rmse": 0.42, ...}
    model_version = Column(String(50))  # Resulting model version if successful
    error_message = Column(Text)  # Error details if failed

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100))  # User or system that triggered training

    __table_args__ = (
        Index('idx_training_status', 'status', 'created_at'),
        Index('idx_training_symbol', 'symbol', 'model_type'),
    )
```

**Pydantic API Model**:
```python
from enum import Enum
from typing import Dict, Any, Optional

class TrainingStatusEnum(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class TrainingRunCreate(BaseModel):
    """Request to start a training run"""
    run_name: str
    symbol: str
    model_type: str = Field(..., regex="^(lstm|xgboost)$")
    hyperparameters: Dict[str, Any]
    feature_config: Dict[str, Any]
    training_config: Dict[str, Any]

class TrainingRunResponse(BaseModel):
    """Training run returned by API"""
    id: int
    run_name: str
    symbol: str
    model_type: str
    mlflow_run_id: Optional[str]
    status: TrainingStatusEnum
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    final_metrics: Optional[Dict[str, float]]
    model_version: Optional[str]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
```

**Example Data**:
```json
{
  "id": 42,
  "run_name": "lstm_crudeOIL_1h_experiment_v5",
  "symbol": "CrudeOIL",
  "model_type": "lstm",
  "mlflow_run_id": "a3f8c9d2e1b4a5c6d7e8f9a0b1c2d3e4",
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
  "model_version": "v1.3.0",
  "created_at": "2025-11-29T09:59:45Z"
}
```

---

### Entity 3: `model_metrics` Table

**Purpose**: Store detailed evaluation metrics for each model version and forecast horizon

**SQLAlchemy Model**:
```python
class ModelMetrics(Base):
    """Model performance metrics"""
    __tablename__ = "model_metrics"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    model_type = Column(String(20), nullable=False)
    model_version = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    forecast_horizon = Column(String(10), nullable=False)

    # Metrics
    mpe = Column(Float, nullable=False)  # Mean Percentage Error
    rmse = Column(Float, nullable=False)  # Root Mean Squared Error
    mae = Column(Float, nullable=False)  # Mean Absolute Error
    mape = Column(Float, nullable=False)  # Mean Absolute Percentage Error
    directional_accuracy = Column(Float)  # % correct direction predictions

    # Metadata
    evaluation_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    sample_size = Column(Integer)  # Number of predictions evaluated
    mlflow_run_id = Column(String(100))

    __table_args__ = (
        Index('idx_metrics_lookup', 'model_version', 'forecast_horizon'),
    )
```

**Pydantic API Model**:
```python
class ModelMetricsResponse(BaseModel):
    """Model metrics returned by API"""
    id: int
    model_type: str
    model_version: str
    symbol: str
    forecast_horizon: str
    mpe: float
    rmse: float
    mae: float
    mape: float
    directional_accuracy: Optional[float]
    evaluation_date: datetime
    sample_size: Optional[int]

    class Config:
        from_attributes = True
```

---

### Entity 4: `exogenous_variables` Table

**Purpose**: Store external market indicators (DXY, VIX, news events) for model input

**SQLAlchemy Model**:
```python
class ExogenousVariable(Base):
    """External market indicators"""
    __tablename__ = "exogenous_variables"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    variable_name = Column(String(50), nullable=False, index=True)  # "DXY", "VIX", "NFP_EVENT"
    timestamp = Column(DateTime, nullable=False, index=True)

    # Value
    value = Column(Float)  # Continuous variables (DXY, VIX)
    is_event = Column(Boolean, default=False)  # Binary flag for news events

    # Metadata
    source = Column(String(100))  # Data source (e.g., "yahoo_finance", "alpha_vantage")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_exogenous_lookup', 'variable_name', 'timestamp'),
    )
```

---

## Configuration Schemas (YAML + Pydantic)

### Configuration 1: LSTM Model Configuration

**File**: `config/ml/lstm_config.yaml`

```yaml
model:
  type: "lstm"
  num_layers: 2
  hidden_size: 128
  dropout: 0.2
  bidirectional: true
  attention: true
  output_size: 1  # Single value prediction

training:
  learning_rate: 0.001
  batch_size: 64
  max_epochs: 100
  early_stopping_patience: 10
  optimizer: "adam"
  loss_function: "mse"
  gradient_clip: 1.0

features:
  lookback_window: 60  # 60 minutes for 1-hour forecast
  forecast_horizons: ["1h", "4h", "24h"]
  include_exogenous: true
  exogenous_variables: ["DXY", "VIX", "NEWS_EVENT"]

  # Feature engineering
  use_technical_indicators: true
  indicators: ["rsi_14", "macd", "bb_upper", "bb_lower", "atr"]

data:
  train_window_days: 30
  val_window_days: 5
  test_window_days: 5
  slide_days: 5
  min_data_points: 1000
```

**Pydantic Validation Schema**:
```python
from pydantic import BaseModel, Field
from typing import List

class LSTMModelConfig(BaseModel):
    type: str = "lstm"
    num_layers: int = Field(ge=1, le=5)
    hidden_size: int = Field(ge=32, le=512)
    dropout: float = Field(ge=0.0, le=0.5)
    bidirectional: bool
    attention: bool
    output_size: int = 1

class TrainingConfig(BaseModel):
    learning_rate: float = Field(gt=0.0, le=0.1)
    batch_size: int = Field(ge=8, le=256)
    max_epochs: int = Field(ge=1, le=500)
    early_stopping_patience: int = Field(ge=1, le=50)
    optimizer: str = Field(regex="^(adam|sgd|rmsprop)$")
    loss_function: str = Field(regex="^(mse|mae|huber)$")
    gradient_clip: float = Field(gt=0.0)

class FeaturesConfig(BaseModel):
    lookback_window: int = Field(ge=10, le=200)
    forecast_horizons: List[str]
    include_exogenous: bool
    exogenous_variables: List[str]
    use_technical_indicators: bool
    indicators: List[str]

class DataConfig(BaseModel):
    train_window_days: int = Field(ge=7, le=180)
    val_window_days: int = Field(ge=1, le=30)
    test_window_days: int = Field(ge=1, le=30)
    slide_days: int = Field(ge=1, le=30)
    min_data_points: int = Field(ge=100)

class LSTMFullConfig(BaseModel):
    model: LSTMModelConfig
    training: TrainingConfig
    features: FeaturesConfig
    data: DataConfig
```

---

### Configuration 2: XGBoost Model Configuration

**File**: `config/ml/xgboost_config.yaml`

```yaml
model:
  type: "xgboost"
  max_depth: 6
  learning_rate: 0.1
  n_estimators: 100
  objective: "reg:squarederror"
  booster: "gbtree"
  gamma: 0
  min_child_weight: 1
  subsample: 0.8
  colsample_bytree: 0.8
  reg_alpha: 0
  reg_lambda: 1

training:
  early_stopping_rounds: 10
  eval_metric: "rmse"
  verbose: true

features:
  lookback_window: 60
  forecast_horizons: ["1h", "4h", "24h"]
  include_exogenous: true
  exogenous_variables: ["DXY", "VIX", "NEWS_EVENT"]

  # Feature engineering (XGBoost-specific)
  lag_periods: [1, 2, 3, 5, 10, 20, 60]
  rolling_windows: [5, 10, 20]
  use_technical_indicators: true
  indicators: ["rsi_14", "macd", "bb_upper", "bb_lower", "atr"]

data:
  train_window_days: 30
  val_window_days: 5
  test_window_days: 5
  slide_days: 5
  min_data_points: 1000
```

---

## API Request/Response Models

### API Model 1: Inference Request

**Endpoint**: `POST /api/v1/ml/predict`

**Request Schema**:
```python
class InferenceRequest(BaseModel):
    """Request for ML forecast prediction"""
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: Optional[datetime] = None  # Defaults to current time
    forecast_horizons: List[str] = Field(..., min_items=1)  # ["1h", "4h", "24h"]
    model_type: Optional[str] = Field("ensemble", regex="^(lstm|xgboost|ensemble)$")
    include_confidence_intervals: bool = True
```

**Response Schema**:
```python
class InferenceResponse(BaseModel):
    """Response containing ML forecasts"""
    symbol: str
    timestamp: datetime
    forecasts: List[ForecastResponse]
    inference_time_ms: float
    cache_hit: bool
```

**Example Request**:
```json
{
  "symbol": "CrudeOIL",
  "forecast_horizons": ["1h", "4h", "24h"],
  "model_type": "ensemble",
  "include_confidence_intervals": true
}
```

**Example Response**:
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
      "model_version": "v1.3.0",
      "predicted_value": 78.45,
      "lower_bound": 77.80,
      "upper_bound": 79.10,
      "confidence_score": 0.87,
      "created_at": "2025-11-29T13:59:55Z",
      "inference_time_ms": 42.5
    },
    {
      "forecast_horizon": "4h",
      "predicted_value": 78.90,
      "lower_bound": 77.95,
      "upper_bound": 79.85,
      "confidence_score": 0.79
    },
    {
      "forecast_horizon": "24h",
      "predicted_value": 79.80,
      "lower_bound": 77.50,
      "upper_bound": 82.10,
      "confidence_score": 0.65
    }
  ],
  "inference_time_ms": 48.2,
  "cache_hit": false
}
```

---

### API Model 2: Training Request

**Endpoint**: `POST /api/v1/ml/train`

**Request Schema**:
```python
class TrainingRequest(BaseModel):
    """Request to start model training"""
    run_name: str = Field(..., min_length=1, max_length=100)
    symbol: str = Field(..., min_length=1, max_length=20)
    model_type: str = Field(..., regex="^(lstm|xgboost)$")
    config_override: Optional[Dict[str, Any]] = None  # Override default config
    async_training: bool = True  # Run in background
```

**Response Schema**:
```python
class TrainingResponse(BaseModel):
    """Response after starting training"""
    training_run_id: int
    run_name: str
    status: TrainingStatusEnum
    mlflow_run_id: Optional[str]
    estimated_duration_minutes: Optional[int]
    message: str
```

**Example Request**:
```json
{
  "run_name": "lstm_crudeOIL_1h_experiment_v6",
  "symbol": "CrudeOIL",
  "model_type": "lstm",
  "config_override": {
    "training": {
      "learning_rate": 0.0005,
      "max_epochs": 150
    }
  },
  "async_training": true
}
```

**Example Response**:
```json
{
  "training_run_id": 43,
  "run_name": "lstm_crudeOIL_1h_experiment_v6",
  "status": "running",
  "mlflow_run_id": "b4g9d0e3f2c5b6d7e8f9a0b1c2d3e4f5",
  "estimated_duration_minutes": 28,
  "message": "Training started successfully. Monitor progress at MLflow UI."
}
```

---

## Data Flow Diagrams

### Data Flow 1: Training Pipeline

```
┌───────────────┐
│ Training API  │
│   Request     │
└───────┬───────┘
        │
        ▼
┌───────────────────┐
│ MLTrainingService │
│                   │
│ 1. Validate config│
│ 2. Create run     │
│ 3. Start MLflow   │
└────────┬──────────┘
         │
         ▼
┌────────────────────┐         ┌──────────────────┐
│ MarketDataLoader   │────────▶│  PostgreSQL      │
│                    │  fetch  │  market_data     │
│ - Load OHLCV       │◀────────│  exogenous_vars  │
│ - Load exogenous   │         └──────────────────┘
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ FeatureEngineering │
│                    │
│ - Lag features     │
│ - Rolling stats    │
│ - Indicators       │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  Model Trainer     │
│                    │
│ - Walk-forward CV  │
│ - Train LSTM/XGB   │
│ - Calculate metrics│
└────────┬───────────┘
         │
         ▼
┌────────────────────┐         ┌──────────────────┐
│  MLflow Logging    │────────▶│  MLflow Server   │
│                    │  log    │  - Experiments   │
│ - Log params       │         │  - Model Registry│
│ - Log metrics      │         │  - Artifacts     │
│ - Save artifacts   │         └──────────────────┘
└────────┬───────────┘
         │
         ▼
┌────────────────────┐         ┌──────────────────┐
│ TrainingRepository │────────▶│  PostgreSQL      │
│                    │  save   │  training_runs   │
│ - Update status    │         │  model_metrics   │
│ - Save metrics     │         └──────────────────┘
└────────────────────┘
```

### Data Flow 2: Inference Pipeline

```
┌───────────────┐
│ Inference API │
│   Request     │
└───────┬───────┘
        │
        ▼
┌────────────────────┐         ┌──────────────────┐
│ MLInferenceService │────────▶│  Redis Cache     │
│                    │  check  │                  │
│ 1. Check cache     │◀────────│  forecast:{key}  │
└────────┬───────────┘  hit?   └──────────────────┘
         │ (miss)
         ▼
┌────────────────────┐         ┌──────────────────┐
│ MarketDataLoader   │────────▶│  PostgreSQL      │
│                    │  fetch  │  market_data     │
│ - Latest OHLCV     │◀────────│  exogenous_vars  │
│ - Exogenous vars   │  latest └──────────────────┘
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ FeatureEngineering │
│                    │
│ - Transform inputs │
│ - Normalize        │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐         ┌──────────────────┐
│  Model Predictor   │────────▶│  In-Memory       │
│                    │  load   │  Loaded Models   │
│ - Load model       │◀────────│  - LSTM          │
│ - Generate forecast│         │  - XGBoost       │
└────────┬───────────┘         └──────────────────┘
         │
         ▼
┌────────────────────┐         ┌──────────────────┐
│ ForecastRepository │────────▶│  PostgreSQL      │
│                    │  save   │  forecasts       │
│ - Save forecast    │         └──────────────────┘
└────────┬───────────┘
         │
         ▼
┌────────────────────┐         ┌──────────────────┐
│ Redis Cache Update │────────▶│  Redis Cache     │
│                    │  set    │                  │
│ - Cache forecast   │         │  forecast:{key}  │
│ - TTL: 5 minutes   │         │  TTL: 300s       │
└────────┬───────────┘         └──────────────────┘
         │
         ▼
┌────────────────────┐
│ API Response       │
│                    │
│ - Forecast values  │
│ - Confidence       │
│ - Latency metrics  │
└────────────────────┘
```

---

## Summary

This data model specification defines:

✅ **4 Database Entities**: forecasts, training_runs, model_metrics, exogenous_variables
✅ **2 Configuration Schemas**: LSTM config, XGBoost config
✅ **2 API Request/Response Models**: Inference, Training
✅ **2 Data Flow Diagrams**: Training pipeline, Inference pipeline
✅ **Pydantic Validation**: Type safety and input validation
✅ **Database Indexes**: Optimized query performance
✅ **ERD**: Clear entity relationships

All schemas support the 30 functional requirements from [spec.md](./spec.md) and align with technical decisions from [research.md](./research.md). The data model is ready for implementation with SQLAlchemy ORM and FastAPI integration.
