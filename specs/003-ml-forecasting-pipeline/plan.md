# Implementation Plan: ML Forecasting Pipeline

**Branch**: `003-ml-forecasting-pipeline` | **Date**: 2025-11-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-ml-forecasting-pipeline/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

The ML Forecasting Pipeline provides price predictions for financial instruments using LSTM and XGBoost models. The system enables training, versioning, evaluation, and deployment of forecasting models with support for exogenous variables (DXY, VIX, news events). Models are trained on historical OHLCV data with MLflow experiment tracking and served via a FastAPI inference service with <50ms p95 latency. The pipeline calculates financial metrics (MPE, RMSE, MAE, MAPE) and supports multiple forecast horizons (1h, 4h, 24h) for autonomous trading agent decision-making.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: PyTorch 2.0+, XGBoost, scikit-learn, MLflow, FastAPI 0.104.1, pandas, numpy
**Storage**: PostgreSQL 15+ (forecasts table, time-series optimizations), MLflow Model Registry (model artifacts, scalers, feature transformers)
**Testing**: pytest with 85% minimum coverage target
**Target Platform**: Linux server (Docker containers)
**Project Type**: Single backend project (src/ structure)
**Performance Goals**: 30min training time for 1-month datasets (13.5M data points), 50ms p95 inference latency, 100 concurrent requests without degradation
**Constraints**: <50ms p95 inference latency, 99% API uptime during market hours (24/5), MPE <3% for 1-hour forecasts
**Scale/Scope**: 13.5M historical market data points, multiple symbols (initially CrudeOIL), 3 forecast horizons (1h, 4h, 24h), exogenous variables (DXY, VIX, news events)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Test-First Development**: ✅ PASS
- Will follow TDD approach with tests written before implementation
- Target 85% test coverage minimum
- Unit tests for model training, evaluation, inference
- Integration tests for MLflow integration and API endpoints
- Contract tests for inference API schemas

**II. Security-First Design**: ✅ PASS
- No new authentication requirements (uses existing API auth)
- Input validation for training parameters and inference requests
- Model artifact integrity validation (checksums, version verification)
- No external attack surface (internal ML service)

**III. Observability & Monitoring**: ✅ PASS
- Prometheus metrics for training duration, inference latency, model accuracy
- Structured logging (structlog) for training runs and predictions
- MLflow experiment tracking for complete audit trail
- Model performance degradation alerts

**IV. Agent Autonomy with Guardrails**: ⚠️ NOT APPLICABLE
- This feature does not implement autonomous agents
- MLPredictionAgent will consume this pipeline in 004-autonomous-trading-agents

**V. Repository Pattern & Service Layer**: ✅ PASS
- ForecastRepository for database operations (forecasts table)
- MLTrainingService for training orchestration
- MLInferenceService for prediction serving
- Clear separation between data access and business logic

**VI. Event-Driven Architecture**: ⚠️ PARTIAL
- No events emitted yet (will be added in 004-autonomous-trading-agents)
- Inference service can be integrated with Redis pub/sub later
- Current focus: synchronous training and inference

**VII. Configuration Over Code**: ✅ PASS
- Training hyperparameters in YAML config files
- Model selection via configuration (LSTM vs XGBoost)
- Feature sets defined in configuration
- Environment-specific settings in config/environments/

**VIII. Dependency Injection**: ✅ PASS
- Repository dependencies injected into services
- MLflow client injected for experiment tracking
- Database session management via dependency injection
- Testable service layer with mockable dependencies

**Overall Status**: ✅ PASS (6 of 6 applicable principles met)

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/ml/                              # ML forecasting pipeline (existing)
├── data/                           # Data loaders and preprocessors
│   ├── __init__.py
│   ├── feature_engineering.py     # Technical indicators, transformations
│   ├── market_data_loader.py      # Load OHLCV from database
│   └── exogenous_data_loader.py   # DXY, VIX, news events loader
├── models/                         # Model implementations
│   ├── __init__.py
│   ├── lstm_forecaster.py         # LSTM architecture
│   ├── xgboost_forecaster.py      # XGBoost implementation
│   └── base_model.py              # Abstract base class
├── training/                       # Training infrastructure
│   ├── __init__.py
│   ├── trainer.py                 # Training orchestration
│   ├── validator.py               # Walk-forward validation
│   └── config.py                  # Training configuration
├── inference/                      # Real-time prediction service
│   ├── __init__.py
│   ├── predictor.py               # Inference engine
│   └── cache.py                   # Forecast caching layer
└── evaluation/                     # Model evaluation metrics
    ├── __init__.py
    ├── metrics.py                 # MPE, RMSE, MAE, MAPE
    └── visualization.py           # Forecast vs actual plots

src/database/models/                # Database ORM models (existing)
└── forecasts.py                    # Forecast table model (new)

src/database/repositories/          # Data access layer (existing)
└── forecast_repository.py          # Forecast CRUD operations (new)

src/services/                       # Business logic services (existing)
├── ml_training_service.py          # Training orchestration service (new)
└── ml_inference_service.py         # Inference serving service (new)

src/api/routes/                     # FastAPI endpoints (existing)
└── ml_forecasting.py               # ML forecasting API routes (new)

config/ml/                          # ML configuration files (new)
├── lstm_config.yaml               # LSTM hyperparameters
├── xgboost_config.yaml            # XGBoost hyperparameters
└── features_config.yaml           # Feature set definitions

tests/
├── unit/ml/                        # Unit tests for ML components
│   ├── test_lstm_forecaster.py
│   ├── test_xgboost_forecaster.py
│   ├── test_feature_engineering.py
│   ├── test_metrics.py
│   └── test_trainer.py
├── integration/ml/                 # Integration tests
│   ├── test_ml_training_service.py
│   ├── test_ml_inference_service.py
│   └── test_mlflow_integration.py
└── contract/                       # Contract tests for API
    └── test_ml_forecasting_schemas.py
```

**Structure Decision**: Using the existing RiseTrader single backend project structure (Option 1) with `src/ml/` as the dedicated ML module. The directory structure already exists with the required subdirectories (data, models, training, inference, evaluation). This feature will populate these directories with implementations and add supporting repositories, services, and API routes.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
