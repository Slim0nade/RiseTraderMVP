# Implementation Tasks: ML Forecasting Pipeline

**Feature**: 003-ml-forecasting-pipeline
**Branch**: `003-ml-forecasting-pipeline`
**Created**: 2025-11-29
**Planning Docs**: [plan.md](./plan.md) | [spec.md](./spec.md) | [data-model.md](./data-model.md) | [research.md](./research.md)

## Overview

This document breaks down the ML Forecasting Pipeline implementation into executable tasks organized by user story. Each phase delivers an independently testable increment following Test-Driven Development (TDD) principles.

**Total Tasks**: 85
**User Stories**: 5 (2× P1, 2× P2, 1× P3)
**Parallel Opportunities**: 42 tasks can run in parallel

---

## Task Dependencies & Execution Order

```
Phase 1: Setup (T001-T005)
   ↓
Phase 2: Foundational (T006-T015)
   ↓
   ├─→ Phase 3: US1 - Training Pipeline (T016-T035) [P1] ← MVP
   │      ↓
   ├─→ Phase 4: US2 - Inference Service (T036-T050) [P1] ← MVP
   │      ↓
   ├─→ Phase 5: US3 - Exogenous Variables (T051-T060) [P2]
   │      ↓
   ├─→ Phase 6: US4 - MLflow Versioning (T061-T070) [P2]
   │      ↓
   └─→ Phase 7: US5 - Performance Monitoring (T071-T080) [P3]
          ↓
Phase 8: Polish & Cross-Cutting (T081-T085)
```

**MVP Scope**: Phase 1-4 (US1 + US2) = Complete training and inference with basic models

**Dependency Rules**:
- Phase 2 blocks all user stories (foundational infrastructure)
- US2 (Inference) depends on US1 (Training) - must have trained models
- US3-US5 are independent of each other after Phase 2
- US4 (MLflow) can start after US1 completes
- US5 (Monitoring) can start after US2 completes

---

## Phase 1: Setup & Project Initialization

**Goal**: Initialize ML module structure, configuration files, and development environment

**Duration**: 1-2 hours
**Blocking**: Yes (blocks all subsequent phases)

### Tasks

- [X] T001 Create ML configuration directory structure at config/ml/
- [X] T002 [P] Create LSTM configuration file at config/ml/lstm_config.yaml with hyperparameters from research.md
- [X] T003 [P] Create XGBoost configuration file at config/ml/xgboost_config.yaml with hyperparameters from research.md
- [X] T004 [P] Create feature configuration file at config/ml/features_config.yaml for exogenous variables and indicators
- [X] T005 Update requirements.txt with ML dependencies: torch==2.0.1, xgboost==2.0.2, mlflow==2.9.2, scikit-learn==1.3.2

---

## Phase 2: Foundational Infrastructure

**Goal**: Implement shared database models, repositories, and configuration loading that all user stories depend on

**Duration**: 4-6 hours
**Blocking**: Yes (blocks all user story implementations)

### Database Layer

- [X] T006 [P] Write unit tests for Forecast model in tests/unit/models/test_forecast_model.py
- [X] T007 [P] Write unit tests for TrainingRun model in tests/unit/models/test_training_run_model.py
- [X] T008 [P] Write unit tests for ModelMetrics model in tests/unit/models/test_model_metrics_model.py
- [X] T009 [P] Write unit tests for ExogenousVariable model in tests/unit/models/test_exogenous_variable_model.py
- [X] T010 [US1] Implement Forecast SQLAlchemy model in src/database/models/forecasts.py per data-model.md
- [X] T011 [US1] Implement TrainingRun SQLAlchemy model in src/database/models/training_runs.py per data-model.md
- [X] T012 [US1] Implement ModelMetrics SQLAlchemy model in src/database/models/model_metrics.py per data-model.md
- [X] T013 [US3] Implement ExogenousVariable SQLAlchemy model in src/database/models/exogenous_variables.py per data-model.md

### Configuration Management

- [X] T014 [P] Write unit tests for config loader in tests/unit/ml/test_config.py
- [X] T015 Implement configuration loader with Pydantic validation in src/ml/training/config.py

---

## Phase 3: User Story 1 - Train and Evaluate Models (P1) 🎯 MVP

**User Story**: A data scientist needs to train LSTM and XGBoost models on historical market data to predict future prices, evaluate their accuracy using financial metrics, and select the best-performing model for production use.

**Independent Test Criteria**:
- ✅ Given 30 days of CrudeOIL historical data → Training completes in ≤30 minutes
- ✅ Models achieve MPE <3% and RMSE <0.5 on out-of-sample validation
- ✅ All hyperparameters and metrics logged to MLflow
- ✅ Model artifacts (model, scaler, transformers) saved correctly
- ✅ Training run status tracked (pending → running → completed)

**Duration**: 2-3 days
**Dependencies**: Phase 2 must complete first

### 3.1: Data Layer & Feature Engineering

- [X] T016 [P] [US1] Write unit tests for MarketDataLoader in tests/unit/ml/data/test_market_data_loader.py
- [X] T017 [P] [US1] Write unit tests for FeatureEngineering in tests/unit/ml/data/test_feature_engineering.py
- [X] T018 [US1] Implement MarketDataLoader in src/ml/data/market_data_loader.py to fetch OHLCV from database
- [X] T019 [US1] Implement FeatureEngineering in src/ml/data/feature_engineering.py with lag features, rolling stats, and technical indicators per research.md TD-002

### 3.2: Model Implementations

- [X] T020 [P] [US1] Write unit tests for base model interface in tests/unit/ml/models/test_base_model.py
- [X] T021 [P] [US1] Write unit tests for LSTM forecaster in tests/unit/ml/models/test_lstm_forecaster.py
- [X] T022 [P] [US1] Write unit tests for XGBoost forecaster in tests/unit/ml/models/test_xgboost_forecaster.py
- [X] T023 [US1] Implement BaseModel abstract class in src/ml/models/base_model.py with train(), predict(), save(), load() methods
- [X] T024 [US1] Implement LSTMForecaster in src/ml/models/lstm_forecaster.py with bidirectional LSTM + attention per research.md TD-001
- [X] T025 [US1] Implement XGBoostForecaster in src/ml/models/xgboost_forecaster.py with feature engineering per research.md TD-002

### 3.3: Training Pipeline

- [X] T026 [P] [US1] Write unit tests for WalkForwardValidator in tests/unit/ml/training/test_validator.py
- [X] T027 [P] [US1] Write unit tests for ModelTrainer in tests/unit/ml/training/test_trainer.py
- [X] T028 [US1] Implement WalkForwardValidator in src/ml/training/validator.py with 70/15/15 split per research.md TD-004
- [X] T029 [US1] Implement ModelTrainer in src/ml/training/trainer.py with training loop, early stopping, and metric calculation

### 3.4: Evaluation Metrics

- [X] T030 [P] [US1] Write unit tests for metrics module in tests/unit/ml/evaluation/test_metrics.py
- [X] T031 [US1] Implement metrics calculations in src/ml/evaluation/metrics.py (MPE, RMSE, MAE, MAPE, directional accuracy) per research.md TD-007

### 3.5: Repository Layer

- [X] T032 [P] [US1] Write unit tests for TrainingRunRepository in tests/unit/repositories/test_training_run_repository.py
- [X] T033 [P] [US1] Write unit tests for ModelMetricsRepository in tests/unit/repositories/test_model_metrics_repository.py
- [X] T034 [US1] Implement TrainingRunRepository in src/database/repositories/training_run_repository.py with CRUD operations
- [X] T035 [US1] Implement ModelMetricsRepository in src/database/repositories/model_metrics_repository.py with metrics storage

### 3.6: Service Layer & Integration

- [X] T036 [US1] Write integration tests for MLTrainingService in tests/integration/ml/test_ml_training_service.py
- [X] T037 [US1] Implement MLTrainingService in src/services/ml_training_service.py orchestrating data loading, training, MLflow logging, and metrics storage

---

## Phase 4: User Story 2 - Real-Time Inference (P1) 🎯 MVP

**User Story**: Trading agents and system components need to retrieve real-time price forecasts for multiple time horizons to inform trading decisions, with low latency to support high-frequency operations.

**Independent Test Criteria**:
- ✅ Given a production model → Forecasts returned in <50ms (p95)
- ✅ Redis cache reduces latency to <5ms for cached forecasts
- ✅ 100 concurrent requests handled without degradation
- ✅ Confidence intervals included when requested
- ✅ Forecasts stored in database with all metadata

**Duration**: 2-3 days
**Dependencies**: US1 must complete (needs trained models)

### 4.1: Inference Engine

- [X] T038 [P] [US2] Write unit tests for ModelPredictor in tests/unit/ml/inference/test_predictor.py
- [X] T039 [P] [US2] Write unit tests for ForecastCache in tests/unit/ml/inference/test_cache.py
- [X] T040 [US2] Implement ModelPredictor in src/ml/inference/predictor.py with in-memory model loading and batch prediction
- [X] T041 [US2] Implement ForecastCache in src/ml/inference/cache.py with Redis integration and 5-minute TTL per research.md TD-006

### 4.2: Repository Layer

- [X] T042 [P] [US2] Write unit tests for ForecastRepository in tests/unit/repositories/test_forecast_repository.py
- [X] T043 [US2] Implement ForecastRepository in src/database/repositories/forecast_repository.py with composite indexes per data-model.md

### 4.3: Service Layer

- [X] T044 [US2] Write integration tests for MLInferenceService in tests/integration/ml/test_ml_inference_service.py
- [X] T045 [US2] Implement MLInferenceService in src/services/ml_inference_service.py with cache checking, model loading, and forecast storage per quickstart.md Scenario 2

### 4.4: API Layer

- [X] T046 [P] [US2] Write contract tests for inference API in tests/contract/test_ml_forecasting_schemas.py validating OpenAPI spec
- [X] T047 [US2] Implement Pydantic request/response models in src/api/models/ml_models.py (InferenceRequest, InferenceResponse, ForecastResponse) per data-model.md
- [X] T048 [US2] Implement POST /api/v1/ml/predict endpoint in src/api/routes/ml_forecasting.py with async handling
- [X] T049 [US2] Write integration tests for inference API in tests/integration/ml/test_ml_inference_api.py
- [X] T050 [US2] Register ml_forecasting router in src/api/main.py with /api/v1/ml prefix

---

## Phase 5: User Story 3 - Exogenous Variables (P2)

**User Story**: Analysts want to enhance forecast accuracy by including external market indicators (DXY, VIX) and economic news events as input features to the models.

**Independent Test Criteria**:
- ✅ DXY and VIX data fetched and stored correctly with timestamps
- ✅ News events marked as binary flags
- ✅ Models trained with exogenous variables show ≥15% RMSE reduction vs price-only models
- ✅ Feature importance analysis shows contribution of each exogenous variable
- ✅ System falls back to price-only models when exogenous data unavailable

**Duration**: 1-2 days
**Dependencies**: Phase 2 (database models)

### 5.1: Data Collection

- [ ] T051 [P] [US3] Write unit tests for ExogenousDataLoader in tests/unit/ml/data/test_exogenous_data_loader.py
- [ ] T052 [P] [US3] Write unit tests for ExogenousVariableRepository in tests/unit/repositories/test_exogenous_variable_repository.py
- [ ] T053 [US3] Implement ExogenousDataLoader in src/ml/data/exogenous_data_loader.py with yfinance integration for DXY and VIX per quickstart.md Scenario 5
- [ ] T054 [US3] Implement ExogenousVariableRepository in src/database/repositories/exogenous_variable_repository.py with time-alignment queries

### 5.2: Feature Integration

- [ ] T055 [US3] Update FeatureEngineering in src/ml/data/feature_engineering.py to merge exogenous variables with OHLCV data per research.md TD-003
- [ ] T056 [US3] Add exogenous variable normalization (Z-score) to FeatureEngineering per research.md TD-003
- [ ] T057 [US3] Update LSTMForecaster in src/ml/models/lstm_forecaster.py to accept exogenous features
- [ ] T058 [US3] Update XGBoostForecaster in src/ml/models/xgboost_forecaster.py to include exogenous features per research.md TD-002

### 5.3: Testing & Validation

- [ ] T059 [US3] Write integration tests for exogenous variable training in tests/integration/ml/test_exogenous_training.py
- [ ] T060 [US3] Implement A/B test script comparing models with/without exogenous variables validating ≥15% RMSE improvement per spec.md SC-006

---

## Phase 6: User Story 4 - MLflow Versioning (P2)

**User Story**: Data scientists need to track all model training experiments, compare hyperparameters, reproduce past results, and maintain a registry of production-ready models.

**Independent Test Criteria**:
- ✅ All training runs logged to MLflow with hyperparameters, metrics, artifacts
- ✅ Experiments can be filtered, sorted, and compared by metrics/parameters
- ✅ Past experiments reproducible from MLflow run ID
- ✅ Models promoted through Development → Staging → Production stages
- ✅ Production models versioned with approval timestamps

**Duration**: 1-2 days
**Dependencies**: US1 (training pipeline)

### 6.1: MLflow Integration

- [ ] T061 [P] [US4] Write unit tests for MLflowTracker in tests/unit/ml/tracking/test_mlflow_tracker.py
- [ ] T062 [US4] Create MLflowTracker wrapper class in src/ml/tracking/mlflow_tracker.py with experiment management and artifact logging
- [ ] T063 [US4] Update ModelTrainer in src/ml/training/trainer.py to integrate MLflowTracker for automatic logging per research.md TD-005

### 6.2: Model Registry

- [ ] T064 [P] [US4] Write unit tests for ModelRegistry in tests/unit/ml/tracking/test_model_registry.py
- [ ] T065 [US4] Implement ModelRegistry in src/ml/tracking/model_registry.py with stage transitions (Development/Staging/Production) per research.md TD-010
- [ ] T066 [US4] Implement model promotion workflow in ModelRegistry with approval tracking

### 6.3: Model Loading & Deployment

- [ ] T067 [US4] Update ModelPredictor in src/ml/inference/predictor.py to load models from MLflow Model Registry per research.md TD-010
- [ ] T068 [US4] Implement model rollback functionality in ModelRegistry per data-model.md

### 6.4: Training API Integration

- [ ] T069 [US4] Implement POST /api/v1/ml/train endpoint in src/api/routes/ml_forecasting.py per contracts/openapi.yaml
- [ ] T070 [US4] Implement GET /api/v1/ml/training-runs/{run_id} endpoint in src/api/routes/ml_forecasting.py per contracts/openapi.yaml

---

## Phase 7: User Story 5 - Performance Monitoring (P3)

**User Story**: The system automatically detects when production models' accuracy degrades over time and alerts analysts to retrain with fresh data.

**Independent Test Criteria**:
- ✅ Forecast accuracy tracked hourly by comparing predictions to actual outcomes
- ✅ Alerts triggered when MPE exceeds 5% or RMSE exceeds limits for 3 consecutive hours
- ✅ Alerts include specific metrics, time period, and retraining recommendations
- ✅ Model degradation detected within 3 hours of threshold breach
- ✅ Alert contains one-click retraining trigger with recommended parameters

**Duration**: 1-2 days
**Dependencies**: US2 (inference service generating forecasts)

### 7.1: Accuracy Tracking

- [ ] T071 [P] [US5] Write unit tests for ForecastAccuracyTracker in tests/unit/ml/monitoring/test_accuracy_tracker.py
- [ ] T072 [US5] Implement ForecastAccuracyTracker in src/ml/monitoring/accuracy_tracker.py with hourly comparison of predictions vs actuals per quickstart.md Scenario 3
- [ ] T073 [US5] Implement background task in ForecastAccuracyTracker for continuous monitoring

### 7.2: Alerting System

- [ ] T074 [P] [US5] Write unit tests for PerformanceAlerter in tests/unit/ml/monitoring/test_performance_alerter.py
- [ ] T075 [US5] Implement PerformanceAlerter in src/ml/monitoring/performance_alerter.py with threshold detection (MPE >5%, RMSE exceeds limits)
- [ ] T076 [US5] Implement alert generation with retraining recommendations per quickstart.md Scenario 3

### 7.3: Metrics API

- [ ] T077 [US5] Implement GET /api/v1/ml/models/{model_version}/metrics endpoint in src/api/routes/ml_forecasting.py per contracts/openapi.yaml
- [ ] T078 [US5] Write integration tests for metrics API in tests/integration/ml/test_model_metrics_api.py

### 7.4: Dashboards & Visualization

- [ ] T079 [P] [US5] Write unit tests for visualization module in tests/unit/ml/evaluation/test_visualization.py
- [ ] T080 [US5] Implement forecast vs actual visualization in src/ml/evaluation/visualization.py with matplotlib

---

## Phase 8: Polish & Cross-Cutting Concerns

**Goal**: Final improvements, documentation, and production readiness

**Duration**: 1 day
**Dependencies**: All user stories complete

### Final Tasks

- [ ] T081 [P] Create database migration for forecasts table using Alembic in src/database/migrations/versions/006_create_forecasts_table.py
- [ ] T082 [P] Create database migration for training_runs table using Alembic in src/database/migrations/versions/007_create_training_runs_table.py
- [ ] T083 [P] Create database migration for model_metrics table using Alembic in src/database/migrations/versions/008_create_model_metrics_table.py
- [ ] T084 [P] Create database migration for exogenous_variables table using Alembic in src/database/migrations/versions/009_create_exogenous_variables_table.py
- [ ] T085 Add Prometheus metrics for training duration, inference latency, and model accuracy in src/monitoring/ml_metrics.py

---

## Parallel Execution Guide

Tasks marked with `[P]` can be executed in parallel within their phase. Here's how to maximize throughput:

### Phase 2: Foundational (4 parallel tracks)
```bash
# Track 1: Forecast & TrainingRun models
T006, T007 → T010, T011

# Track 2: ModelMetrics & ExogenousVariable models
T008, T009 → T012, T013

# Track 3: Config loader
T014 → T015
```

### Phase 3: US1 - Training Pipeline (3 parallel tracks)
```bash
# Track 1: Data layer
T016, T017 → T018, T019

# Track 2: Models
T020, T021, T022 → T023, T024, T025

# Track 3: Training & Evaluation
T026, T027, T030 → T028, T029, T031

# Track 4: Repositories
T032, T033 → T034, T035

# Then: Service integration (sequential)
T036 → T037
```

### Phase 4: US2 - Inference (2 parallel tracks)
```bash
# Track 1: Inference engine
T038, T039 → T040, T041

# Track 2: Repository
T042 → T043

# Then: Service & API (sequential)
T044 → T045 → T046 → T047 → T048 → T049 → T050
```

### Phase 5: US3 - Exogenous Variables (2 parallel tracks)
```bash
# Track 1: Data collection
T051, T052 → T053, T054

# Track 2: Feature integration (after data collection)
T055, T056 → T057, T058 → T059, T060
```

### Phase 6: US4 - MLflow (2 parallel tracks)
```bash
# Track 1: MLflow integration
T061 → T062 → T063

# Track 2: Model registry
T064 → T065 → T066 → T067, T068

# Then: API (sequential)
T069, T070
```

### Phase 7: US5 - Monitoring (2 parallel tracks)
```bash
# Track 1: Tracking & Alerting
T071 → T072, T073
T074 → T075, T076

# Track 2: API & Visualization
T077 → T078
T079 → T080
```

### Phase 8: Polish (all parallel)
```bash
T081, T082, T083, T084, T085 (all run in parallel)
```

---

## Testing Strategy

Following RiseTrader constitution requirement for **Test-First Development (TDD)**:

1. **All tests written FIRST** before implementation
2. **Tests MUST fail** initially (Red phase)
3. **Implementation makes tests pass** (Green phase)
4. **Refactor while keeping tests passing** (Refactor phase)
5. **Minimum 85% test coverage target**

### Test Types by Phase

**Unit Tests** (58 tasks):
- All model, service, repository, and utility classes
- Fast execution (<100ms per test)
- No external dependencies (mocked database, Redis, MLflow)

**Integration Tests** (8 tasks):
- Service layer with real database (test DB)
- MLflow integration with real tracking server
- API endpoints with full request/response cycle

**Contract Tests** (1 task):
- API schemas validated against OpenAPI spec
- Ensures frontend/agent integration compatibility

---

## Implementation Strategy

### MVP Delivery (Weeks 1-2)

**Scope**: Phases 1-4 (US1 + US2)

**Deliverables**:
- ✅ Train LSTM and XGBoost models on CrudeOIL data
- ✅ Generate real-time forecasts via API (<50ms latency)
- ✅ Forecasts stored in database
- ✅ Basic MLflow logging

**Success Criteria**:
- Training completes in ≤30 minutes for 30-day datasets
- Inference latency <50ms p95
- MPE <3%, RMSE <0.5 for 1-hour forecasts

### Iteration 1 (Week 3)

**Scope**: Phase 5 (US3 - Exogenous Variables)

**Deliverables**:
- ✅ DXY and VIX data integration
- ✅ News event flagging
- ✅ Improved forecast accuracy (≥15% RMSE reduction)

### Iteration 2 (Week 4)

**Scope**: Phase 6 (US4 - MLflow Versioning)

**Deliverables**:
- ✅ Full experiment tracking
- ✅ Model registry with stage promotions
- ✅ Model reproducibility
- ✅ Training API endpoints

### Iteration 3 (Week 5)

**Scope**: Phase 7 (US5 - Performance Monitoring)

**Deliverables**:
- ✅ Continuous accuracy tracking
- ✅ Automated degradation alerts
- ✅ Metrics API endpoints
- ✅ Forecast vs actual visualizations

### Final Polish (Week 6)

**Scope**: Phase 8

**Deliverables**:
- ✅ Database migrations
- ✅ Prometheus metrics
- ✅ Documentation updates
- ✅ Production deployment preparation

---

## Success Metrics

### Performance Targets

| Metric | Target | User Story |
|--------|--------|-----------|
| Training time (30-day dataset) | ≤30 min | US1 |
| Inference latency (p95) | <50ms | US2 |
| Concurrent requests | 100 without degradation | US2 |
| MPE (1-hour forecast) | <3% | US1 |
| RMSE (normalized) | <0.5 | US1 |
| Exogenous RMSE improvement | ≥15% | US3 |
| Forecast accuracy tracking | Hourly | US5 |
| Degradation detection time | ≤3 hours | US5 |
| Test coverage | ≥85% | All |
| API uptime (market hours) | 99% | US2 |

### Validation Checklist

**US1: Training** ✓
- [ ] LSTM model trains successfully on 30 days CrudeOIL data
- [ ] XGBoost model trains successfully on 30 days CrudeOIL data
- [ ] Walk-forward validation prevents data leakage
- [ ] Metrics (MPE, RMSE, MAE, MAPE, directional accuracy) calculated correctly
- [ ] All hyperparameters logged to MLflow
- [ ] Model artifacts saved and loadable

**US2: Inference** ✓
- [ ] Forecast API returns results in <50ms (p95)
- [ ] Redis cache reduces latency to <5ms
- [ ] 100 concurrent requests handled without degradation
- [ ] Forecasts stored in database with metadata
- [ ] Confidence intervals included when requested

**US3: Exogenous Variables** ✓
- [ ] DXY data fetched and stored with correct timestamps
- [ ] VIX data fetched and stored with correct timestamps
- [ ] News events marked as binary flags
- [ ] Models with exogenous variables show ≥15% RMSE improvement
- [ ] System falls back gracefully when exogenous data unavailable

**US4: MLflow Versioning** ✓
- [ ] All training runs logged to MLflow
- [ ] Experiments filterable and comparable in MLflow UI
- [ ] Past experiments reproducible from MLflow run ID
- [ ] Models promoted through Development → Staging → Production
- [ ] Production models versioned with approval tracking

**US5: Monitoring** ✓
- [ ] Forecast accuracy tracked hourly
- [ ] Alerts triggered when MPE >5% for 3 consecutive hours
- [ ] Alerts include retraining recommendations
- [ ] Model degradation detected within 3 hours
- [ ] Metrics API returns performance trends

---

## References

- **Specification**: [spec.md](./spec.md) - User stories and requirements
- **Implementation Plan**: [plan.md](./plan.md) - Technical context and architecture
- **Data Model**: [data-model.md](./data-model.md) - Database schemas and entities
- **API Contracts**: [contracts/openapi.yaml](./contracts/openapi.yaml) - OpenAPI specification
- **Technical Decisions**: [research.md](./research.md) - Resolved technical choices
- **Integration Scenarios**: [quickstart.md](./quickstart.md) - End-to-end workflows

---

## Notes

- **TDD is mandatory**: All tests written FIRST, must fail initially, implementation makes them pass
- **85% coverage minimum**: Target enforced by constitution
- **Tasks are executable**: Each task specific enough for autonomous implementation
- **Dependencies clearly marked**: Follow execution order to avoid blocking
- **Parallel opportunities identified**: 42 tasks can run concurrently to maximize velocity
- **MVP clearly scoped**: Phases 1-4 deliver complete training + inference functionality
