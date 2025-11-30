# Feature Specification: ML Forecasting Pipeline

**Feature Branch**: `003-ml-forecasting-pipeline`
**Created**: 2025-11-29
**Status**: Draft
**Input**: User description: "ML forecasting pipeline with LSTM and XGBoost models, model versioning, exogenous variables support (DXY, VIX, news), MLflow experiment tracking, training pipeline, inference service, and evaluation metrics (MPE, RMSE, MAE)"

## Overview

The ML Forecasting Pipeline provides the trading system with price predictions for financial instruments (primarily crude oil) using multiple machine learning models. The system enables data scientists and quantitative analysts to train, version, evaluate, and deploy forecasting models that incorporate both historical price data and exogenous market variables. This capability is foundational for the autonomous trading agents to make informed trading decisions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Train and Evaluate Price Forecasting Models (Priority: P1)

A data scientist needs to train LSTM and XGBoost models on historical market data to predict future prices, evaluate their accuracy using financial metrics, and select the best-performing model for production use.

**Why this priority**: This is the core functionality - without trained models, the entire forecasting system cannot function. All other features depend on having working models.

**Independent Test**: Can be fully tested by providing historical market data, triggering a training run, and verifying that models are trained, evaluated with MPE/RMSE/MAE metrics, and stored with version tracking.

**Acceptance Scenarios**:

1. **Given** historical market data for CrudeOIL exists in the database, **When** the analyst initiates model training with specified parameters (lookback window, forecast horizon, features), **Then** both LSTM and XGBoost models are trained and evaluation metrics are calculated and displayed
2. **Given** multiple model versions have been trained, **When** the analyst views model performance metrics, **Then** they can compare MPE, RMSE, MAE, and MAPE across all versions ranked by accuracy
3. **Given** a training run has completed, **When** the analyst reviews the results, **Then** they can see detailed metrics for each forecast horizon (1h, 4h, 24h) and make an informed decision on model selection
4. **Given** training fails due to insufficient data or configuration errors, **When** the error occurs, **Then** clear error messages indicate the issue and suggest corrective actions

---

### User Story 2 - Generate Real-time Price Forecasts (Priority: P1)

Trading agents and system components need to retrieve real-time price forecasts for multiple time horizons to inform trading decisions, with low latency to support high-frequency operations.

**Why this priority**: Equally critical as training - this is what the trading agents consume. Without inference, models are useless.

**Independent Test**: Can be fully tested by loading a trained model, sending inference requests with current market data, and verifying forecasts are returned within latency requirements.

**Acceptance Scenarios**:

1. **Given** a production model is deployed, **When** an inference request is made with current market data, **Then** forecasts for 1h, 4h, and 24h horizons are returned within 50ms
2. **Given** the inference service is running, **When** multiple concurrent requests arrive, **Then** all requests receive forecasts within SLA without degradation
3. **Given** new market data has been received, **When** the forecast is generated, **Then** the prediction incorporates the latest tick data and reflects current market conditions
4. **Given** a model inference fails, **When** the error occurs, **Then** a fallback mechanism provides the last known forecast with a staleness indicator and logs the failure

---

### User Story 3 - Incorporate Exogenous Variables (Priority: P2)

Analysts want to enhance forecast accuracy by including external market indicators (DXY, VIX) and economic news events as input features to the models.

**Why this priority**: While important for accuracy improvement, models can function with just price data. This is an enhancement that can be added after core functionality works.

**Independent Test**: Can be fully tested by training models with and without exogenous variables and demonstrating improved accuracy metrics when exogenous data is included.

**Acceptance Scenarios**:

1. **Given** DXY and VIX data is available, **When** training a model with exogenous variables enabled, **Then** the model incorporates these features and shows impact analysis in the training report
2. **Given** an economic news event occurs, **When** this event is marked in the system, **Then** forecasts around that time period reflect increased uncertainty or adjusted predictions
3. **Given** exogenous data sources are temporarily unavailable, **When** training or inference is requested, **Then** the system falls back to price-only models without failure
4. **Given** new exogenous variables are added, **When** retraining models, **Then** feature importance analysis shows the contribution of each exogenous variable

---

### User Story 4 - Track and Version Model Experiments (Priority: P2)

Data scientists need to track all model training experiments, compare hyperparameters, reproduce past results, and maintain a registry of production-ready models.

**Why this priority**: Important for model governance and reproducibility, but the system can operate with manual versioning initially.

**Independent Test**: Can be fully tested by running multiple training experiments with different hyperparameters, verifying all runs are logged, and demonstrating model reproducibility.

**Acceptance Scenarios**:

1. **Given** a model training run is initiated, **When** the training completes, **Then** all hyperparameters, metrics, artifacts, and training configuration are logged to the experiment tracker
2. **Given** multiple experiments have been run, **When** viewing the experiment tracking interface, **Then** experiments can be filtered, sorted, and compared by metrics, parameters, or tags
3. **Given** a past experiment ID, **When** requesting model reproduction, **Then** the exact model can be reloaded and produces identical predictions on the same input data
4. **Given** a model is promoted to production, **When** it is registered, **Then** it receives a production tag, version number, and approval timestamp for audit trails

---

### User Story 5 - Monitor Model Performance Degradation (Priority: P3)

The system automatically detects when production models' accuracy degrades over time and alerts analysts to retrain with fresh data.

**Why this priority**: Nice to have for operational excellence, but manual monitoring can suffice initially. Can be implemented after core functionality is stable.

**Independent Test**: Can be fully tested by simulating prediction errors exceeding thresholds and verifying alerts are generated.

**Acceptance Scenarios**:

1. **Given** a production model is deployed, **When** actual prices deviate from forecasts beyond error thresholds for 3 consecutive hours, **Then** an alert is triggered to retrain the model
2. **Given** forecast accuracy metrics are being tracked, **When** MPE exceeds 5% or RMSE exceeds defined limits, **Then** the model is automatically flagged for review
3. **Given** model performance degradation is detected, **When** the alert is sent, **Then** it includes specific metrics, time period, and suggested retraining parameters
4. **Given** retraining is recommended, **When** analysts review the alert, **Then** they can trigger retraining with one click using recommended parameters

---

### Edge Cases

- What happens when training data has gaps or missing values (market holidays, system downtime)?
- How does the system handle extreme market volatility periods (flash crashes, circuit breaker events)?
- What occurs when exogenous data sources (DXY, VIX feeds) become unavailable during training or inference?
- How are forecasts adjusted when a model hasn't been retrained for an extended period (model staleness)?
- What happens when inference requests exceed system capacity?
- How does the system handle competing model versions being promoted to production simultaneously?
- What occurs when a forecast horizon's actual data is not yet available for validation?

## Requirements *(mandatory)*

### Functional Requirements

**Model Training:**

- **FR-001**: System MUST support training LSTM and XGBoost models on historical OHLCV market data with configurable lookback windows
- **FR-002**: System MUST allow configuration of forecast horizons (1 hour, 4 hours, 24 hours) independently or in combination
- **FR-003**: System MUST support inclusion of exogenous variables (DXY index, VIX volatility index, economic news events) as optional model features
- **FR-004**: System MUST validate training data completeness and data quality before initiating model training
- **FR-005**: System MUST handle missing data through configurable strategies (forward fill, interpolation, or exclusion)
- **FR-006**: Training pipeline MUST be executable via automated scheduler, API trigger, or manual command

**Model Evaluation:**

- **FR-007**: System MUST calculate and report Mean Percentage Error (MPE), Root Mean Squared Error (RMSE), Mean Absolute Error (MAE), and Mean Absolute Percentage Error (MAPE) for all trained models
- **FR-008**: System MUST perform walk-forward validation to test model performance on out-of-sample data
- **FR-009**: System MUST generate forecast vs. actual comparison visualizations for model evaluation
- **FR-010**: System MUST support A/B testing between model versions on live data
- **FR-011**: System MUST calculate separate metrics for each forecast horizon when multiple horizons are trained

**Model Versioning & Registry:**

- **FR-012**: System MUST integrate with experiment tracking tool for model versioning
- **FR-013**: System MUST log all hyperparameters, training metrics, model artifacts, and training datasets for each experiment
- **FR-014**: System MUST support tagging models with stages (development, staging, production, archived)
- **FR-015**: System MUST maintain a model registry that allows querying models by version, accuracy metrics, training date, or tags
- **FR-016**: System MUST enable model rollback to previous versions in case of degraded performance

**Inference Service:**

- **FR-017**: System MUST provide a real-time inference API that accepts current market state and returns price forecasts
- **FR-018**: Inference API MUST support batch predictions for multiple symbols simultaneously
- **FR-019**: System MUST cache recent forecasts with configurable TTL to reduce redundant computation
- **FR-020**: System MUST serve forecasts within acceptable latency for trading operations
- **FR-021**: System MUST handle concurrent inference requests without latency degradation
- **FR-022**: System MUST return confidence intervals or prediction ranges alongside point forecasts

**Data Management:**

- **FR-023**: System MUST store forecast outputs in the database with timestamps, model version, symbol, horizon, and predicted values
- **FR-024**: System MUST retain historical forecasts for performance validation and backtesting
- **FR-025**: System MUST support feature engineering pipelines to generate technical indicators from raw OHLCV data
- **FR-026**: System MUST normalize and denormalize data using consistent scaling strategies across training and inference

**Monitoring & Alerts:**

- **FR-027**: System MUST track forecast accuracy metrics continuously by comparing predictions to actual outcomes
- **FR-028**: System MUST alert when forecast error metrics exceed configurable thresholds
- **FR-029**: System MUST provide dashboards showing model performance trends over time
- **FR-030**: System MUST log all training runs, inference requests, and errors for audit and debugging

### Key Entities

- **TrainingRun**: Represents a single model training execution with configuration (hyperparameters, features, horizon), start/end timestamps, and status (running, completed, failed)
- **ForecastModel**: A trained ML model with version identifier, model type (LSTM/XGBoost), training metrics, hyperparameters, and stage (dev/staging/production)
- **Forecast**: A prediction generated by a model, containing symbol, timestamp, horizon, predicted value, confidence interval, model version used
- **ModelMetrics**: Performance measurements including MPE, RMSE, MAE, MAPE calculated for a specific model version and forecast horizon
- **ExogenousVariable**: External market indicators or events (DXY, VIX, news events) with timestamps and values used as model features
- **FeatureSet**: A configuration defining which features (price data, technical indicators, exogenous variables) are used for a specific model
- **ModelArtifact**: Serialized model files, scalers, feature transformers, and metadata stored for a specific model version

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Analysts can train LSTM and XGBoost models on 13.5M historical data points and complete training within 30 minutes for 1-month datasets
- **SC-002**: Trained models achieve MPE under 3% and RMSE under 0.5 (normalized price scale) on out-of-sample validation data for 1-hour forecasts
- **SC-003**: Inference service returns price forecasts within 50ms (p95 latency) for single requests and handles 100 concurrent requests without degradation
- **SC-004**: System maintains 99% inference API uptime during market hours (24/5 operation)
- **SC-005**: Model performance degradation is detected within 3 hours of accuracy dropping below thresholds
- **SC-006**: Exogenous variables improve forecast accuracy by at least 15% compared to price-only models as measured by RMSE reduction
- **SC-007**: Data scientists can compare and reproduce any past experiment within 5 minutes using experiment tracking data
- **SC-008**: 90% of training runs complete successfully without manual intervention or error recovery
- **SC-009**: Model versioning system maintains complete audit trail with zero loss of experiment data over 6 months of operation
- **SC-010**: Forecasts for all configured horizons (1h, 4h, 24h) are generated and stored for every market data update within 60 seconds

## Assumptions & Dependencies

### Assumptions

- Historical market data (OHLCV) for CrudeOIL and other symbols is available and complete in the PostgreSQL database
- Data scientists have expertise in time series forecasting and understand financial metrics
- Initial training will focus on CrudeOIL but infrastructure must support multiple symbols
- GPU availability is not required; CPU-based training is acceptable with defined time budgets
- Forecast horizons of 1h, 4h, and 24h are sufficient for trading agent decision-making
- Exogenous data sources (DXY, VIX, news events) will be provided by external integrations or manual input initially

### Dependencies

- **Data Pipeline**: Continuous market data ingestion from MT4 must be operational (001-mt4-integration)
- **Database**: PostgreSQL with `forecasts` table schema available (002-fastapi-dashboard-api)
- **Experiment Tracking**: MLflow or similar tracking server deployed and accessible for experiment logging
- **Python ML Stack**: PyTorch, XGBoost, scikit-learn, pandas libraries installed in execution environment
- **API Infrastructure**: FastAPI endpoint infrastructure available for inference service integration
- **Caching Layer**: Redis available for forecast caching (optional but recommended)

## Out of Scope

- Advanced deep learning architectures beyond LSTM (e.g., Transformer, Temporal Fusion Transformer) - future enhancement
- Automated hyperparameter tuning with Optuna - future enhancement
- Real-time model retraining based on streaming data - future enhancement
- Multi-asset portfolio-level forecasting - future enhancement
- Sentiment analysis from news text - future enhancement
- Custom loss functions for asymmetric prediction errors - future enhancement

## Related Documentation

- [001-mt4-integration spec](../001-mt4-integration/spec.md) - Market data source
- [002-fastapi-dashboard-api spec](../002-fastapi-dashboard-api/spec.md) - Database schema and API infrastructure
- CLAUDE.md - Overall project architecture and ML stack requirements
- PROJECT_REBUILD_SPECIFICATION.md - Phase 6: ML forecasting pipeline details
