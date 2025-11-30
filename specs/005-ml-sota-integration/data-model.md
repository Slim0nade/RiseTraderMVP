# Data Model: SOTA Models Integration

**Feature**: 005-ml-sota-integration | **Date**: 2025-11-30
**Purpose**: Define database schema for multi-model orchestration, A/B testing, and intelligent model selection

## Overview

This feature introduces 6 new database tables to support SOTA model integration:
1. `model_performance_snapshots` - Real-time model performance metrics
2. `model_selection_rules` - Configurable selection logic
3. `market_regimes` - Market state classification
4. `agent_model_selections` - Audit log of agent decisions
5. `ab_test_configurations` - A/B test setup
6. `ab_test_metrics` - A/B test results

Existing tables (`forecasts`, `training_runs`, `model_metrics`) are extended but retain backward compatibility.

## Entity Relationship Diagram

```
┌─────────────────────────────┐
│  model_performance_snapshots│──┐
│  (real-time metrics)        │  │
└─────────────────────────────┘  │
                                 │
┌─────────────────────────────┐  │  ┌─────────────────────────────┐
│  model_selection_rules      │  ├─>│  agent_model_selections     │
│  (configurable logic)       │  │  │  (audit log)                │
└─────────────────────────────┘  │  └─────────────────────────────┘
                                 │             │
┌─────────────────────────────┐  │             │
│  market_regimes             │──┘             │
│  (trending/ranging/volatile)│                │
└─────────────────────────────┘                │
                                               ▼
                                 ┌─────────────────────────────┐
                                 │  forecasts (existing)       │
                                 │  + direction_prob           │
                                 │  + feature_importance       │
                                 └─────────────────────────────┘

┌─────────────────────────────┐     ┌─────────────────────────────┐
│  ab_test_configurations     │────>│  ab_test_metrics            │
│  (test setup)               │     │  (results)                  │
└─────────────────────────────┘     └─────────────────────────────┘
```

## Entity Definitions

### 1. ModelPerformanceSnapshot

**Purpose**: Track real-time model performance metrics over multiple time windows for intelligent selection.

**Table Name**: `model_performance_snapshots`

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Unique identifier |
| model_type | VARCHAR(50) | NOT NULL | Model type enum (lstm, xgboost, tcn, bigru, fedformer, tft, moe, ppo) |
| symbol | VARCHAR(20) | NOT NULL | Trading symbol (e.g., "CrudeOIL") |
| forecast_horizon | VARCHAR(10) | NOT NULL | Horizon (1h, 4h, 24h) |
| time_window | VARCHAR(10) | NOT NULL | Rolling window (1h, 24h, 7d) |
| mpe | DECIMAL(10, 4) | | Mean Percentage Error |
| rmse | DECIMAL(15, 6) | | Root Mean Squared Error |
| mae | DECIMAL(15, 6) | | Mean Absolute Error |
| mape | DECIMAL(10, 4) | | Mean Absolute Percentage Error |
| directional_accuracy | DECIMAL(5, 2) | CHECK (directional_accuracy BETWEEN 0 AND 100) | % correct direction predictions |
| latency_p95_ms | DECIMAL(10, 2) | | 95th percentile inference latency |
| sample_count | INTEGER | NOT NULL | Number of forecasts in window |
| last_updated | TIMESTAMP | NOT NULL DEFAULT NOW() | Last metric update |
| trend | VARCHAR(20) | CHECK (trend IN ('improving', 'stable', 'degrading')) | Performance trend |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Record creation time |

**Indexes**:
```sql
CREATE INDEX idx_perf_snapshot_lookup ON model_performance_snapshots(model_type, symbol, forecast_horizon, time_window);
CREATE INDEX idx_perf_snapshot_updated ON model_performance_snapshots(last_updated DESC);
```

**Unique Constraint**:
```sql
CONSTRAINT uq_perf_snapshot UNIQUE (model_type, symbol, forecast_horizon, time_window)
```

**Validation Rules**:
- `model_type` must be one of: lstm, xgboost, tcn, bigru, fedformer, tft, moe, ppo
- `forecast_horizon` must be one of: 1h, 4h, 24h
- `time_window` must be one of: 1h, 24h, 7d
- `sample_count` must be >= 1
- `directional_accuracy` must be between 0 and 100
- `last_updated` must be within last 10 minutes for active models

**Update Pattern**:
- UPSERT (INSERT ... ON CONFLICT DO UPDATE) on unique constraint
- Updated by background worker within 1 minute of forecast vs actual comparison
- Uses running statistics for incremental updates (no full recalculation)

---

### 2. ModelSelectionRule

**Purpose**: Configure model selection logic based on market regime, performance thresholds, and contextual factors.

**Table Name**: `model_selection_rules`

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Unique identifier |
| rule_name | VARCHAR(100) | NOT NULL UNIQUE | Human-readable rule name |
| priority | INTEGER | NOT NULL DEFAULT 100 | Evaluation priority (lower = higher priority) |
| condition | TEXT | NOT NULL | SQL-like condition string |
| recommended_models | TEXT[] | NOT NULL | Ordered list of model types |
| fallback_models | TEXT[] | | Fallback if recommended unavailable |
| enabled | BOOLEAN | NOT NULL DEFAULT TRUE | Rule active/inactive |
| created_by | VARCHAR(100) | | User/system that created rule |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Creation timestamp |
| last_modified | TIMESTAMP | NOT NULL DEFAULT NOW() | Last update timestamp |
| description | TEXT | | Rule purpose and context |

**Indexes**:
```sql
CREATE INDEX idx_rule_priority ON model_selection_rules(priority ASC) WHERE enabled = TRUE;
CREATE INDEX idx_rule_enabled ON model_selection_rules(enabled, priority);
```

**Validation Rules**:
- `priority` must be between 1 and 1000
- `condition` must be valid expression (validated at creation)
- `recommended_models` array must contain at least 1 model type
- All models in `recommended_models` and `fallback_models` must be valid ModelType enum values
- Rule name must be unique across all rules

**Example Conditions**:
```
"market_regime='trending_up' AND tcn_mpe_24h < 3.0"
"symbol='CrudeOIL' AND forecast_horizon='1h' AND volatility > 0.03"
"market_regime IN ('volatile', 'crisis')"
```

**Evaluation Order**:
1. Filter to enabled rules
2. Sort by priority ascending
3. Evaluate conditions in order
4. Return first matching rule's recommended models
5. If no match, use default rule (priority 1000)

---

### 3. MarketRegime

**Purpose**: Track current market state classification for model selection context.

**Table Name**: `market_regimes`

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Unique identifier |
| symbol | VARCHAR(20) | NOT NULL | Trading symbol |
| regime_type | VARCHAR(20) | NOT NULL CHECK (regime_type IN ('trending_up', 'trending_down', 'ranging', 'volatile', 'crisis')) | Market state |
| confidence_score | DECIMAL(5, 4) | NOT NULL CHECK (confidence_score BETWEEN 0 AND 1) | Confidence (0-1) |
| indicators_used | JSONB | | Indicator values (ADX, ATR, etc.) |
| detected_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Detection timestamp |
| duration_hours | DECIMAL(10, 2) | | Hours in current regime |
| previous_regime | VARCHAR(20) | | Previous regime type |
| transition_at | TIMESTAMP | | Last regime change time |

**Indexes**:
```sql
CREATE INDEX idx_regime_symbol ON market_regimes(symbol, detected_at DESC);
CREATE INDEX idx_regime_current ON market_regimes(symbol) WHERE duration_hours < 24;
CREATE INDEX idx_regime_transition ON market_regimes(transition_at DESC) WHERE transition_at IS NOT NULL;
```

**Unique Constraint**:
```sql
CONSTRAINT uq_latest_regime UNIQUE (symbol)
-- Only keep latest regime per symbol, update in place
```

**Validation Rules**:
- `regime_type` must be one of the 5 defined types
- `confidence_score` must be between 0 and 1
- `detected_at` must be within last 10 minutes (stale regime detection = error)
- `duration_hours` auto-calculated as NOW() - transition_at

**Update Pattern**:
- Background worker updates every 5 minutes
- UPSERT on (symbol) - overwrites previous regime
- Log regime transitions to separate audit table (optional)

---

### 4. AgentModelSelection

**Purpose**: Audit log of all agent model selection decisions with complete context for analysis and debugging.

**Table Name**: `agent_model_selections`

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Unique identifier |
| selection_timestamp | TIMESTAMP | NOT NULL DEFAULT NOW() | When selection occurred |
| agent_id | VARCHAR(100) | | Requesting agent identifier |
| requested_symbol | VARCHAR(20) | NOT NULL | Trading symbol |
| requested_horizon | VARCHAR(10) | NOT NULL | Forecast horizon |
| market_regime | VARCHAR(20) | | Market regime at selection time |
| selected_model | VARCHAR(50) | NOT NULL | Model type selected |
| selection_reason | TEXT | | Human-readable rationale |
| matched_rule_id | BIGINT | REFERENCES model_selection_rules(id) | Rule that matched |
| override_flag | BOOLEAN | NOT NULL DEFAULT FALSE | Manual override vs automatic |
| performance_metrics_at_selection | JSONB | | Snapshot of all model metrics |
| forecast_result_summary | JSONB | | Forecast output (value, confidence, etc.) |
| latency_ms | DECIMAL(10, 2) | | Selection latency |

**Indexes**:
```sql
CREATE INDEX idx_selection_timestamp ON agent_model_selections(selection_timestamp DESC);
CREATE INDEX idx_selection_agent ON agent_model_selections(agent_id, selection_timestamp DESC);
CREATE INDEX idx_selection_model ON agent_model_selections(selected_model, selection_timestamp DESC);
CREATE INDEX idx_selection_symbol ON agent_model_selections(requested_symbol, requested_horizon);
```

**Validation Rules**:
- `selected_model` must be valid ModelType enum value
- `performance_metrics_at_selection` should contain metrics for all available models
- `latency_ms` should be < 10ms for automatic selection

**Retention**:
- Keep 90 days of detailed logs
- Archive older records with aggregation (daily summaries)

**Analysis Queries**:
- Model selection frequency by agent
- Average selection latency by market regime
- Override rate (manual vs automatic)
- Winning model by symbol/horizon/regime combination

---

### 5. ABTestConfiguration

**Purpose**: Define A/B test parameters for comparing models or features.

**Table Name**: `ab_test_configurations`

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Unique identifier |
| test_name | VARCHAR(200) | NOT NULL UNIQUE | Test name/description |
| test_type | VARCHAR(50) | NOT NULL CHECK (test_type IN ('model', 'feature', 'horizon')) | Dimension being tested |
| symbol | VARCHAR(20) | NOT NULL | Trading symbol |
| forecast_horizon | VARCHAR(10) | NOT NULL | Forecast horizon |
| model_a | VARCHAR(50) | NOT NULL | Reference/baseline model |
| model_b | VARCHAR(50) | NOT NULL | Challenger model |
| traffic_split_pct | INTEGER | NOT NULL CHECK (traffic_split_pct BETWEEN 0 AND 100) | % traffic to model_b |
| feature_config_a | JSONB | | Feature config for A (for feature tests) |
| feature_config_b | JSONB | | Feature config for B (for feature tests) |
| start_date | TIMESTAMP | NOT NULL | Test start time |
| end_date | TIMESTAMP | | Planned test end time |
| actual_end_date | TIMESTAMP | | Actual test completion |
| status | VARCHAR(20) | NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed', 'failed')) | Test status |
| success_criteria | JSONB | | Auto-promotion thresholds |
| auto_promote_threshold | DECIMAL(5, 2) | | MPE improvement % for auto-promotion |
| created_by | VARCHAR(100) | | User who created test |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Creation time |

**Indexes**:
```sql
CREATE INDEX idx_ab_test_active ON ab_test_configurations(symbol, forecast_horizon, status) WHERE status = 'active';
CREATE INDEX idx_ab_test_dates ON ab_test_configurations(start_date, end_date);
```

**Validation Rules**:
- `model_a` and `model_b` must be different
- Both models must be valid ModelType enum values
- `traffic_split_pct` typically 10-50% (configurable)
- `end_date` must be > `start_date`
- Cannot have overlapping active tests for same (symbol, horizon) pair

**State Transitions**:
```
draft → active → completed
  ↓       ↓
paused ← paused
  ↓
failed
```

---

### 6. ABTestMetrics

**Purpose**: Store aggregated metrics for each model in an A/B test.

**Table Name**: `ab_test_metrics`

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Unique identifier |
| test_id | BIGINT | NOT NULL REFERENCES ab_test_configurations(id) ON DELETE CASCADE | Associated test |
| model_type | VARCHAR(50) | NOT NULL | Model being evaluated (model_a or model_b) |
| request_count | INTEGER | NOT NULL DEFAULT 0 | Total requests served |
| avg_mpe | DECIMAL(10, 4) | | Average MPE |
| avg_rmse | DECIMAL(15, 6) | | Average RMSE |
| avg_mae | DECIMAL(15, 6) | | Average MAE |
| avg_directional_accuracy | DECIMAL(5, 2) | | Avg directional accuracy % |
| latency_p50_ms | DECIMAL(10, 2) | | 50th percentile latency |
| latency_p95_ms | DECIMAL(10, 2) | | 95th percentile latency |
| latency_p99_ms | DECIMAL(10, 2) | | 99th percentile latency |
| error_count | INTEGER | NOT NULL DEFAULT 0 | Failed inferences |
| error_rate | DECIMAL(5, 2) | | Error % |
| sample_start_time | TIMESTAMP | | First sample timestamp |
| sample_end_time | TIMESTAMP | | Last sample timestamp |
| statistical_significance | JSONB | | t-test results, p-values |
| last_updated | TIMESTAMP | NOT NULL DEFAULT NOW() | Last metric update |

**Indexes**:
```sql
CREATE INDEX idx_ab_metrics_test ON ab_test_metrics(test_id, model_type);
CREATE INDEX idx_ab_metrics_updated ON ab_test_metrics(last_updated DESC);
```

**Unique Constraint**:
```sql
CONSTRAINT uq_test_model UNIQUE (test_id, model_type)
```

**Validation Rules**:
- `model_type` must match either `model_a` or `model_b` from referenced test
- `request_count` must be >= 0
- `error_rate` = (error_count / request_count) * 100
- Metrics updated every 1 minute during active test

**Aggregation**:
- Running statistics (incremental updates, not full recalculation)
- Statistical significance calculated when sample_count >= 1000 for both models

---

## Existing Table Extensions

### forecasts (Enhanced)

**New Optional Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| direction_prob | DECIMAL(5, 4) | CHECK (direction_prob BETWEEN 0 AND 1) | Probability of price increase (0-1) |
| feature_importance | JSONB | | Feature importance scores from model |

**Notes**:
- These fields are NULL for MVP models (LSTM, XGBoost)
- Populated by SOTA models when available (TFT, MoE)
- Backward compatible: existing consumers ignore unknown fields

**Migration**:
```sql
ALTER TABLE forecasts
  ADD COLUMN direction_prob DECIMAL(5, 4) CHECK (direction_prob BETWEEN 0 AND 1),
  ADD COLUMN feature_importance JSONB;
```

---

### training_runs (No changes)

Already supports `model_type` field that includes SOTA models. No schema changes required.

---

### model_metrics (No changes)

Already supports `model_type` field. SOTA models use same metrics schema.

---

## Relationships

```
model_selection_rules.id → agent_model_selections.matched_rule_id (FK)
ab_test_configurations.id → ab_test_metrics.test_id (FK, CASCADE DELETE)

model_performance_snapshots.model_type ─┐
market_regimes.regime_type ─────────────┼─> Used by selection logic (no FK)
agent_model_selections.selected_model ──┘
```

## Data Retention Policies

| Table | Retention | Archival Strategy |
|-------|-----------|-------------------|
| model_performance_snapshots | 30 days | Archive daily snapshots, delete intraday |
| model_selection_rules | Indefinite | Soft delete (enabled=FALSE) |
| market_regimes | 30 days | Archive daily aggregates |
| agent_model_selections | 90 days | Archive to cold storage, keep daily summaries |
| ab_test_configurations | Indefinite | Keep all test configs |
| ab_test_metrics | 1 year | Aggregate to monthly summaries after 1 year |

## Performance Considerations

### Query Optimization Targets

- Model selection query (performance snapshots + regime): **< 5ms**
- A/B test routing decision (active test lookup): **< 1ms**
- Metrics aggregation (test results report): **< 10s** (even for 100k samples)

### Partitioning Strategy

```sql
-- Partition agent_model_selections by month for efficient time-based queries
CREATE TABLE agent_model_selections (
    ...
) PARTITION BY RANGE (selection_timestamp);

CREATE TABLE agent_model_selections_2025_11 PARTITION OF agent_model_selections
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
```

### Caching Strategy

- **model_selection_rules**: Cache all enabled rules in Redis (invalidate on update)
- **market_regimes**: Cache latest regime per symbol (5-minute TTL)
- **model_performance_snapshots**: Cache latest window per (model, symbol, horizon)
- **ab_test_configurations**: Cache active tests only (invalidate on status change)

---

**Data Model Complete**: Ready for migration scripts and repository implementation.
