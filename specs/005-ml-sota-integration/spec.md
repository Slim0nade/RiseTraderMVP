# Feature Specification: SOTA Models Integration

**Feature Branch**: `005-ml-sota-integration`
**Created**: 2025-11-30
**Status**: Draft
**Input**: User description: "Integrate SOTA forecasting models (TCN, BiGRU, FEDformer, TFT, MoE, PPO) with existing ML pipeline through adapter pattern. Enable A/B testing, gradual migration, and unified model registry."

## Overview

This feature integrates state-of-the-art (SOTA) forecasting models into the existing ML forecasting pipeline (feature 003) through an adapter pattern architecture. The system enables data scientists and system operators to deploy advanced models (TCN, BiGRU-Attention, FEDformer, TFT, MoE ensemble, and PPO reinforcement learning) alongside the existing LSTM and XGBoost models, compare their performance through A/B testing, and gradually migrate production traffic to superior models without service disruption.

The integration addresses the challenge of evolving from a simple MVP model architecture (dict-based configuration, numpy array outputs) to a sophisticated research-grade architecture (dataclass configuration, structured forecast results with uncertainty quantification) while maintaining backward compatibility with existing infrastructure (API endpoints, services, databases, and downstream consumers).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy SOTA Models Alongside MVP Models (Priority: P1)

A data scientist needs to deploy state-of-the-art forecasting models (TCN for short-term oil price predictions, FEDformer for weekly forecasts) into the production environment alongside existing LSTM/XGBoost models, with both model types using the same API endpoints, database storage, and monitoring infrastructure without conflicts or service disruption.

**Why this priority**: This is the foundational capability - without the ability to deploy SOTA models in production, none of the other features (A/B testing, migration) can function. It's the minimum viable integration.

**Independent Test**: Can be fully tested by training a SOTA model (e.g., TCN), deploying it to the production registry, making inference requests through the existing API, and verifying that results are stored in the database with the correct schema, all while MVP models continue to operate normally.

**Acceptance Scenarios**:

1. **Given** MVP models (LSTM, XGBoost) are running in production, **When** a data scientist trains and deploys a TCN model through the training API, **Then** the TCN model is available for inference requests and both TCN and LSTM models can serve predictions simultaneously without conflicts
2. **Given** a unified model registry exists, **When** querying available models via API, **Then** the response lists both MVP models (lstm, xgboost) and SOTA models (tcn, bigru, fedformer, tft, moe, ppo) with their respective versions and metadata
3. **Given** a SOTA model (FEDformer) is deployed, **When** making an inference request to `/api/v1/ml/predict` with `model_type=fedformer`, **Then** the forecast is generated successfully and returned in the same response format as MVP models, with additional SOTA-specific fields (direction_prob, feature_importance) populated when available
4. **Given** both MVP and SOTA models are deployed, **When** reviewing database forecasts table, **Then** forecasts from both model types are stored correctly with proper model_type and model_version differentiation

---

### User Story 2 - Compare Model Performance via A/B Testing (Priority: P1)

System operators and data scientists need to compare SOTA models against MVP models using A/B testing to measure accuracy improvements, latency impacts, and business metrics (trading performance) on live production traffic before making migration decisions.

**Why this priority**: Equally critical as deployment - making informed decisions about which models to promote requires quantitative evidence. A/B testing provides the scientific rigor needed for model selection in a trading system where incorrect predictions have financial consequences.

**Independent Test**: Can be fully tested by configuring an A/B test (e.g., 20% traffic to TCN, 80% to LSTM for crude oil 1h forecasts), collecting metrics over 7 days, and generating a comparison report showing MPE, RMSE, MAE, directional accuracy, and inference latency differences between the two models.

**Acceptance Scenarios**:

1. **Given** both LSTM and TCN models are deployed, **When** an A/B test is configured to route 20% of crude oil inference requests to TCN and 80% to LSTM, **Then** traffic is distributed according to the specified ratios and metrics are tracked separately for each model
2. **Given** an A/B test has been running for 7 days, **When** requesting the A/B test results report, **Then** the system returns comparative metrics showing MPE, RMSE, MAE, directional accuracy, inference latency p50/p95/p99, and statistical significance of differences
3. **Given** TCN demonstrates 18% better RMSE than LSTM in A/B testing, **When** the data scientist reviews the results, **Then** they can see detailed breakdowns by forecast horizon (1h, 4h, 24h) and time of day to understand when TCN performs best
4. **Given** an A/B test shows one model has significantly higher latency, **When** analyzing results, **Then** the report flags this as a potential concern and recommends optimization or infrastructure scaling before full migration

---

### User Story 3 - Dynamic Multi-Model Selection by Agents (Priority: P1)

Autonomous trading agents need to dynamically select the best-performing model for each forecast based on current market regime, recent model performance metrics, and contextual factors, enabling intelligent multi-model orchestration where all models (MVP and SOTA) remain active and the system automatically routes requests to the most appropriate model.

**Why this priority**: This is the core value proposition - intelligent model selection based on market context delivers better trading performance than any single model. Agents need this capability to optimize forecast quality across varying market conditions (trending, ranging, volatile). Elevated to P1 because this is the primary benefit of having multiple models.

**Independent Test**: Can be fully tested by deploying all 8 models (LSTM, XGBoost, TCN, BiGRU, FEDformer, TFT, MoE, PPO), configuring market regime detection rules, running simulated market scenarios (trending, ranging, volatile periods), verifying agents select appropriate models per regime, and confirming selection overhead adds <10ms to inference latency.

**Acceptance Scenarios**:

1. **Given** all 8 models are running in paralllel (LSTM, XGBoost, TCN, BiGRU, FEDformer, TFT, MoE, PPO) and market enters a trending regime, **When** an agent requests a forecast, **Then** the system selects models historically best for trending markets (e.g., TCN, LSTM) based on recent performance metrics
2. **Given** TCN & FEDFormer have achieved 15% better MPE than LSTM over the last 24 hours for 1h forecasts, **When** an agent requests a 1h forecast, **Then** TCN & PPO are both automatically selected and the selection reason is logged for audit
3. **Given** high market volatility is detected (VIX >30), **When** a forecast is needed, **Then** the system selects the ensemble model (MoE) or PPO for robustness and includes uncertainty bounds in the response
4. **Given** multiple models meet selection criteria with similar recent performance, **When** an agent requests a forecast, **Then** the system creates a weighted ensemble of the top 3 performers and returns combined prediction with confidence scores
5. **Given** model selection rules are configured per forecast horizon and symbol, **When** reviewing system behavior, **Then** agents can explain why each model was selected with reference to market regime, recent metrics (MPE, directional accuracy), and context (time of day, economic events)

---

### User Story 4 - Model Interoperability and Reproducibility (Priority: P2)

Data scientists need to ensure that SOTA models trained in research notebooks can be seamlessly deployed to production, that forecast results are reproducible across environments, and that models can be compared fairly regardless of whether they use the MVP or SOTA architecture.

**Why this priority**: Critical for research-to-production workflow and scientific reproducibility, but the core integration can function without perfect reproducibility initially. Can be enhanced after basic deployment works.

**Independent Test**: Can be fully tested by training a FEDformer model in a Jupyter notebook, saving it with the unified model registry, loading it in the production inference service, generating forecasts on identical input data, and verifying that predictions match between research and production environments within floating-point precision tolerances.

**Acceptance Scenarios**:

1. **Given** a data scientist trains a TFT model in a Jupyter notebook, **When** they save the model using the unified model registry, **Then** the model artifact includes all necessary metadata (hyperparameters, feature transformers, scalers, model architecture) for reproducible deployment
2. **Given** a SOTA model (MoE ensemble) is loaded from the registry in production, **When** making predictions on the same input data as during training, **Then** the forecasts are identical to those generated in the research environment (within 1e-6 tolerance)
3. **Given** both MVP and SOTA models are available, **When** comparing their forecasts on the same test dataset, **Then** the evaluation metrics (MPE, RMSE, MAE, MAPE, directional accuracy) are calculated using identical methodology regardless of model architecture
4. **Given** a model is promoted to production, **When** reviewing its lineage, **Then** the system shows the complete audit trail: training data version, hyperparameters used, validation metrics, promotion approval timestamp, and approver identity

---

### User Story 5 - Handle SOTA Model Failures Gracefully (Priority: P3)

The system must handle SOTA model unavailability (missing dependencies, import errors, GPU memory exhaustion) gracefully by falling back to MVP models and providing clear diagnostics to operators, ensuring that inference requests never fail due to SOTA model issues.

**Why this priority**: Important for operational resilience, but the system can operate with manual intervention initially. Graceful degradation is a maturity feature that can be added after core functionality is stable.

**Independent Test**: Can be fully tested by simulating a SOTA model import failure (e.g., missing pytorch-forecasting library), verifying that inference requests fall back to MVP models automatically, confirming that diagnostic logs identify the specific missing dependency, and ensuring that the degraded state is visible in monitoring dashboards.

**Acceptance Scenarios**:

1. **Given** the `pytorch-forecasting` library is not installed, **When** attempting to load a TFT model, **Then** the system falls back to the MVP XGBoost model for the same forecast horizon and logs a warning with installation instructions
2. **Given** a SOTA model (PPO) fails during inference due to GPU memory exhaustion, **When** the next inference request arrives, **Then** the system retries with CPU inference or falls back to a lighter model (TCN) and alerts operators to scale GPU resources
3. **Given** a SOTA model is unavailable, **When** monitoring the system health dashboard, **Then** the degraded state is clearly visible with details about which models are affected and which fallback models are being used
4. **Given** SOTA model dependencies are restored, **When** the system detects the fix, **Then** it automatically resumes using SOTA models and clears the degraded state alert without requiring manual intervention

---

### Edge Cases

- **Adapter Conversion Failures**: What happens when converting between numpy arrays (MVP) and pandas DataFrames (SOTA) fails due to incompatible shapes or missing features?
- **Model Version Conflicts**: How does the system handle inference requests that specify a model version that exists in both MVP and SOTA registries with different architectures?
- **Mixed Batch Requests**: How are batch inference requests handled when some symbols should use MVP models and others should use SOTA models?
- **Partial SOTA Deployment**: What happens when only some SOTA models are deployed (e.g., TCN and FEDformer available, but TFT and MoE not yet installed)?
- **A/B Test Conflicts**: How does the system resolve conflicts when multiple A/B tests are running simultaneously for different forecast horizons on the same symbol?
- **Migration Interruption**: What happens if a scheduled migration is interrupted due to system maintenance or failure?
- **Concurrent Training**: How does the system handle concurrent training of MVP and SOTA models that may compete for GPU resources?
- **Forecast Result Mismatches**: What happens when SOTA models provide uncertainty bounds but downstream consumers expect only point forecasts?

## Requirements *(mandatory)*

### Functional Requirements

**Integration Infrastructure**

- **FR-001**: System MUST provide adapter classes that allow SOTA models (BaseForecaster interface) to work seamlessly with existing infrastructure expecting MVP models (BaseModel interface) without modifications to services, repositories, or API endpoints
- **FR-002**: System MUST provide reverse adapters that allow MVP models to be used in SOTA workflows when needed for comparison or migration testing
- **FR-003**: System MUST maintain a unified model registry that supports both MVP model types (lstm, xgboost) and SOTA model types (tcn, bigru, fedformer, tft, moe, ppo) with proper type discrimination
- **FR-004**: Adapters MUST convert between data formats (numpy arrays ↔ pandas DataFrames) preserving feature semantics and handling both 2D and 3D array shapes correctly

**Model Deployment**

- **FR-005**: System MUST allow data scientists to train and deploy SOTA models through the same training API (`POST /api/v1/ml/train`) used for MVP models, with model type specified in the request
- **FR-006**: System MUST support inference requests for any registered model type (MVP or SOTA) through the unified prediction API (`POST /api/v1/ml/predict`) with the same request/response schema
- **FR-007**: System MUST store forecasts from both MVP and SOTA models in the same database table (forecasts) with proper model_type and model_version differentiation
- **FR-008**: SOTA model inference responses MUST include additional fields (direction_prob, feature_importance) when available, while maintaining backward compatibility with MVP-only consumers

**A/B Testing**

- **FR-009**: System MUST support configuring A/B tests that route a specified percentage of traffic (0-100%) to different model types for the same symbol and forecast horizon
- **FR-010**: System MUST track metrics separately for each model in an A/B test: accuracy metrics (MPE, RMSE, MAE, MAPE, directional accuracy), latency metrics (p50, p95, p99 inference time), and request counts
- **FR-011**: System MUST generate A/B test comparison reports showing metric differences, statistical significance (using appropriate tests for sample sizes), and actionable recommendations
- **FR-012**: A/B test configurations MUST support multiple test dimensions simultaneously: model-level comparisons (LSTM vs TCN vs FEDformer) AND feature-level comparisons (with/without exogenous variables) across all models
- **FR-013**: System MUST support parallel execution of multiple A/B tests across different dimensions (model type, forecast horizon, exogenous features) with independent metric tracking for each test

**Multi-Model Orchestration & Dynamic Selection**

- **FR-014**: System MUST maintain all 8 models (LSTM, XGBoost, TCN, BiGRU, FEDformer, TFT, MoE, PPO) in active production status with no deprecation - enabling permanent coexistence for intelligent selection
- **FR-015**: System MUST provide real-time model performance metrics API that returns MPE, RMSE, MAE, directional accuracy, and latency for each model over configurable time windows (1h, 24h, 7d)
- **FR-016**: System MUST support configurable model selection rules based on market regime (trending, ranging, volatile), recent performance thresholds, forecast horizon, and contextual factors (time of day, economic events)
- **FR-017**: Model selection logic MUST execute in <10ms to maintain overall inference latency budget (<50ms p95)

**Agent Integration & API**

- **FR-018**: System MUST expose model selection API endpoint that accepts forecast request parameters (symbol, horizon, context) and returns recommended model(s) with selection rationale
- **FR-019**: Agents MUST be able to query real-time model performance metrics via API to make informed selection decisions
- **FR-020**: Agents MUST be able to override automatic model selection by explicitly specifying model_type in forecast requests for testing or specific strategies
- **FR-021**: System MUST log all agent model selections including: agent_id, selected_model, selection_reason, market_regime, recent_metrics_snapshot, override_flag for audit trail and learning
- **FR-022**: Model selection rules MUST be configurable via API or configuration file with schema validation (e.g., "if trending market AND TCN_MPE <3% then prefer TCN")

**Interoperability & Reproducibility**

- **FR-023**: Model artifacts saved by SOTA models MUST include complete metadata for reproducibility: hyperparameters, feature transformers, scalers, model architecture, training data version, and random seeds
- **FR-024**: System MUST verify that forecasts generated in research environments match production forecasts on identical input data (within configurable floating-point tolerance, default 1e-6)
- **FR-025**: Evaluation metrics MUST be calculated identically for MVP and SOTA models to enable fair comparison
- **FR-026**: Model lineage tracking MUST capture complete audit trail: training environment, data sources, hyperparameters, validation metrics, promotion approvals, and deployment history

**Error Handling & Fallback**

- **FR-027**: System MUST detect SOTA model import failures (missing dependencies, incompatible versions) at startup and fall back to MVP models with clear diagnostic logging
- **FR-028**: System MUST handle SOTA model inference failures (GPU OOM, timeout, numerical errors) by retrying with degraded configuration (CPU mode, smaller batch size) or falling back to alternative models from the same performance tier
- **FR-029**: System MUST expose model availability status in health check endpoints, indicating which models are operational and which are in degraded/fallback mode
- **FR-030**: Diagnostic logs for SOTA model failures MUST include actionable information: specific missing dependency with version, required GPU memory vs available, configuration suggestions
- **FR-031**: When a model fails, system MUST automatically exclude it from selection pool and redistribute its traffic to next-best performing models without manual intervention

**Configuration & Management**

- **FR-032**: SOTA model configurations MUST support both YAML-based configuration files (for compatibility with MVP models) and dataclass-based ModelConfig objects
- **FR-033**: System MUST provide CLI commands or API endpoints for common operations: list available models, check model compatibility, validate adapter conversions, test model loading, query current model selection rules
- **FR-034**: API request validation MUST accept all model types (MVP: lstm, xgboost | SOTA: tcn, bigru, fedformer, tft, moe, ppo) in the `model_type` field with appropriate error messages for unsupported types

### Key Entities *(include if feature involves data)*

- **ModelType (Enum)**: Enumeration of all supported model types (MVP: lstm, xgboost; SOTA: tcn, bigru, fedformer, tft, moe, ppo) used for model registry and request routing

- **AdapterInterface**: Wrapper that translates between MVP interface (train/predict methods accepting numpy arrays) and SOTA interface (fit/predict methods accepting pandas DataFrames with ForecastResult outputs)

- **ABTestConfiguration**: Defines an A/B test with fields: test_id, symbol, forecast_horizon, model_a (reference), model_b (challenger), traffic_split_pct, start_date, end_date, success_criteria, auto_promote_threshold

- **ABTestMetrics**: Aggregated metrics for an A/B test including: model_type, request_count, avg_mpe, avg_rmse, avg_mae, avg_directional_accuracy, latency_p50_ms, latency_p95_ms, latency_p99_ms, sample_start_time, sample_end_time

- **ModelRegistry**: Unified registry tracking both MVP and SOTA models with fields: model_id, model_type, model_name, architecture_version (mvp | sota), model_artifact_uri, deployment_status (dev | staging | production | active), created_at, promoted_at, promoted_by, performance_tier (experimental | standard | premium)

- **ModelPerformanceSnapshot**: Real-time performance metrics for each model including: model_type, symbol, forecast_horizon, time_window (1h | 24h | 7d), mpe, rmse, mae, mape, directional_accuracy, latency_p95_ms, sample_count, last_updated, trend (improving | stable | degrading)

- **ModelSelectionRule**: Configurable rule for model selection with fields: rule_id, priority, condition (market_regime=trending AND mpe_threshold<3%), recommended_models (ordered list), fallback_models, enabled, created_by, last_modified

- **MarketRegime**: Current market state classification with fields: regime_type (trending_up | trending_down | ranging | volatile | crisis), confidence_score, indicators_used (volatility, trend_strength, volume), detected_at, duration_hours

- **AgentModelSelection**: Audit log of agent model selections with fields: selection_id, timestamp, agent_id, requested_symbol, requested_horizon, market_regime, selected_model, selection_reason, override_flag, performance_metrics_at_selection, forecast_result_summary

## Success Criteria *(mandatory)*

### Measurable Outcomes

**Integration Success**

- **SC-001**: Both MVP and SOTA models can be deployed to production simultaneously without conflicts or service disruption
- **SC-002**: Inference requests can be served by any registered model type (MVP or SOTA) through a single unified API endpoint
- **SC-003**: Forecasts from both model types are stored in the same database schema with proper type differentiation
- **SC-004**: 100% of existing MVP model functionality remains operational after SOTA integration (backward compatibility verified)

**Performance & Reliability**

- **SC-005**: SOTA model inference latency is within acceptable bounds (p95 under 100ms for simple models like TCN, p95 under 200ms for complex models like FEDformer)
- **SC-006**: Adapter conversion overhead adds less than 5ms to inference latency
- **SC-007**: System handles SOTA model failures gracefully with less than 1% increase in overall error rate during degraded mode
- **SC-008**: A/B test traffic routing adds less than 2ms latency overhead

**A/B Testing Capabilities**

- **SC-009**: A/B tests can run for any symbol and forecast horizon combination with configurable traffic splits
- **SC-010**: System supports parallel execution of both model-level tests (LSTM vs TCN) and feature-level tests (with/without exogenous variables) simultaneously
- **SC-011**: A/B test results reports are generated within 10 seconds for tests with up to 100,000 inference requests
- **SC-012**: Statistical significance calculations are accurate (verified against manual calculation on sample datasets)
- **SC-013**: A/B test configurations can be updated dynamically without restarting services

**Multi-Model Orchestration**

- **SC-014**: All 8 models (LSTM, XGBoost, TCN, BiGRU, FEDformer, TFT, MoE, PPO) can run simultaneously in production serving forecasts for CrudeOIL
- **SC-015**: Model selection logic executes in under 10ms to maintain overall inference latency budget
- **SC-016**: Model performance metrics are updated in real-time (within 1 minute of forecast vs actual comparison) and accessible via API
- **SC-017**: Agent model selection achieves measurably better accuracy than any single fixed model (validated over 30-day period showing at least 10% MPE improvement through intelligent selection)
- **SC-018**: System maintains 99.9% uptime even when individual models fail (traffic automatically redistributed to remaining operational models)
- **SC-019**: Model selection audit trail captures 100% of agent decisions with complete context (market regime, metrics snapshot, selection rationale)

**Operational Excellence**

- **SC-020**: Model deployment process takes under 10 minutes from training completion to production availability (for pre-validated models)
- **SC-021**: Diagnostic logs for failures provide actionable information that operators can resolve within 15 minutes
- **SC-022**: Model compatibility can be validated before deployment using automated checks (catches 95% of common integration issues)
- **SC-023**: System provides real-time visibility into which models are serving traffic, their health status, and current selection frequency

## Assumptions

1. **Existing Infrastructure**: Feature 003-ml-forecasting-pipeline is implemented and operational with MVP models (LSTM, XGBoost) already deployed
2. **SOTA Model Availability**: SOTA model implementations (TCN, BiGRU, FEDformer, TFT, MoE, PPO) exist in codebase but are not yet integrated with production infrastructure
3. **Database Schema Compatibility**: Existing forecasts table schema can accommodate SOTA model outputs without migrations (additional fields like direction_prob, feature_importance are optional)
4. **API Versioning**: API endpoints support optional fields in responses (SOTA-specific fields won't break existing consumers that ignore unknown fields)
5. **Dependency Management**: SOTA model dependencies (pytorch-forecasting, neuralforecast, stable-baselines3, gymnasium, etc.) can be installed in production environment or gracefully handled when missing
6. **Traffic Routing**: Infrastructure supports request-level routing decisions (can route inference requests to different models based on A/B test configuration)
7. **Monitoring Infrastructure**: Prometheus and Grafana are available for metrics tracking, MLflow for experiment tracking, and structured logging for diagnostics
8. **GPU Resources**: GPU resources are available for SOTA models that require them (TFT, FEDformer) or that CPU-based inference is acceptable for initial deployment
9. **Authentication**: Existing API authentication mechanisms apply to SOTA model endpoints (no new security requirements)
10. **Forecast Horizon Consistency**: Forecast horizons (1h, 4h, 24h) are consistent across MVP and SOTA models (both use the same time intervals)

## Non-Functional Requirements

### Performance

- **NFR-001**: Adapter conversion between numpy arrays and pandas DataFrames MUST complete in under 5ms for typical batch sizes (up to 100 samples)
- **NFR-002**: Model registry lookups MUST complete in under 10ms to avoid adding latency to inference requests
- **NFR-003**: A/B test traffic routing decision MUST add under 2ms latency overhead per inference request
- **NFR-004**: SOTA model inference latency MUST meet or exceed MVP model latency for equivalent accuracy (acceptable tradeoff: +50ms latency for over 20% accuracy improvement)

### Scalability

- **NFR-005**: System MUST support up to 20 registered models total (combination of MVP and SOTA) without performance degradation
- **NFR-006**: A/B testing infrastructure MUST handle up to 10 concurrent A/B tests across different symbols and forecast horizons
- **NFR-007**: Model registry MUST efficiently handle queries when catalog grows to 100+ model versions across all types

### Reliability

- **NFR-008**: Adapter conversion failures MUST NOT cause inference request failures (fall back to alternative model or return cached forecast with staleness indicator)
- **NFR-009**: SOTA model unavailability MUST NOT prevent MVP models from serving requests (isolation guarantee)
- **NFR-010**: System uptime MUST remain at or above 99.9% even during model deployments, configuration updates, or individual model failures

### Maintainability

- **NFR-011**: Adapter code MUST be thoroughly tested with over 90% coverage to ensure reliable conversion logic
- **NFR-012**: Model registry API MUST provide clear versioning and deprecation paths for evolving model interfaces
- **NFR-013**: Configuration files for SOTA models MUST follow consistent structure and include validation schemas

### Observability

- **NFR-014**: All adapter conversions MUST be logged with input/output shapes and timing for debugging
- **NFR-015**: A/B test metrics MUST be updated in real-time (visible in dashboards within 30 seconds of metric collection)
- **NFR-016**: Model selection events MUST be logged with full context: selected_model, selection_rationale, market_regime, performance_metrics_snapshot, agent_id, timestamp
- **NFR-017**: System MUST provide dashboards showing model selection frequency, performance trends, and agent decision patterns for operational visibility

## Dependencies

### Internal Dependencies

- **003-ml-forecasting-pipeline**: Requires MVP models (LSTM, XGBoost) to be implemented, deployed, and operational
- **004-autonomous-trading-agents** (soft dependency): Model selection API designed for agent consumption, though can work with rule-based selection initially. Full intelligent selection requires agent integration in Phase 004
- **Database Schema (forecasts table)**: Requires existing schema to support optional fields for SOTA-specific outputs
- **API Endpoints**: Requires `/api/v1/ml/predict` and `/api/v1/ml/train` endpoints to be functional
- **MLflow Integration**: Requires MLflow model registry to be configured and accessible
- **Monitoring Infrastructure**: Requires Prometheus metrics endpoint and Grafana dashboards for MVP models
- **Market Regime Detection**: Requires some form of market regime classification (can be simple rule-based initially, enhanced with ML later)

### External Dependencies

- **SOTA Model Libraries**: pytorch-forecasting >=1.0.0, neuralforecast >=1.6.0, stable-baselines3 >=2.1.0 (for PPO), gymnasium >=0.29.0
- **Signal Processing**: PyWavelets >=1.4.0 (for FEDformer decomposition), EMD-signal >=1.4.0
- **Transformer Utilities**: einops >=0.7.0, rotary-embedding-torch >=0.3.0
- **Compute Resources**: GPU support (CUDA) for optimal performance of transformer-based models (TFT, FEDformer)

### Technical Constraints

- Must maintain backward compatibility with existing MVP model consumers
- SOTA models must conform to adapter interface requirements (fit/predict methods)
- A/B testing infrastructure must not introduce over 2ms latency overhead
- Model selection logic must execute in under 10ms to maintain overall latency budget
- All 8 models running simultaneously must fit within available GPU memory (or use CPU fallback)

## Out of Scope

- **Retraining MVP models with SOTA architecture**: This feature integrates existing SOTA models, it does not refactor LSTM/XGBoost to use BaseForecaster interface
- **New SOTA model development**: Adding new SOTA models beyond the 6 specified (TCN, BiGRU, FEDformer, TFT, MoE, PPO) is out of scope
- **Model deprecation or retirement**: All models remain permanently active (no migration to single "best" model) - this is a multi-model orchestration system
- **AutoML for SOTA models**: Automatic hyperparameter tuning, neural architecture search, or automated model discovery is not included
- **Real-time model updates**: Hot-swapping models without reloading or online learning is out of scope
- **Cross-asset model deployment**: Initial release supports CrudeOIL only - expanding to Gold, Forex, other instruments is deferred to future phases
- **Frontend dashboard enhancements**: Updates to React dashboard to visualize model selection patterns, performance comparisons, and A/B test results is a separate feature (requires frontend work)
- **Cost optimization**: Automatic selection of cheaper models (CPU vs GPU) based on cost constraints, or shutting down underutilized models, is deferred
- **Advanced agent intelligence**: Sophisticated machine learning for model selection (meta-learning, reinforcement learning for selection policy) is deferred to 004-autonomous-trading-agents
