# Data Model: Async Optimization Engine with SSE Notifications

**Feature**: 008-async-optimization-sse  
**Date**: 2026-01-17

## Entities

### 1. OptimizationRun (PostgreSQL)

Persistent record of optimization runs with results.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto | Unique identifier |
| job_id | String(36) | UNIQUE, INDEX | Redis job ID for correlation |
| strategy | String(100) | NOT NULL, INDEX | Strategy name (e.g., "crude_oil_v3") |
| symbol | String(50) | NOT NULL, INDEX | Trading symbol (e.g., "CrudeOIL") |
| timeframe | String(10) | NOT NULL | Candle timeframe (e.g., "H1") |
| start_date | DateTime(tz) | NOT NULL | Optimization period start |
| end_date | DateTime(tz) | NOT NULL | Optimization period end |
| param_grid | JSONB | NOT NULL | Full parameter grid tested |
| results | JSONB | NULL | Complete results (populated on completion) |
| status | String(20) | NOT NULL | pending/running/completed/failed/cancelled |
| total_combinations | Integer | NOT NULL | Total parameter combinations |
| combinations_tested | Integer | DEFAULT 0 | Progress counter |
| best_params | JSONB | NULL | Best performing parameters |
| best_metric_value | Decimal(10,4) | NULL | Best metric value achieved |
| optimization_target | String(50) | DEFAULT "sharpe_ratio" | Target metric |
| initial_capital | Decimal(18,2) | DEFAULT 10000 | Starting capital |
| created_at | DateTime(tz) | auto | Creation timestamp |
| started_at | DateTime(tz) | NULL | Execution start time |
| completed_at | DateTime(tz) | NULL | Execution end time |
| error_message | Text | NULL | Error details if failed |

**Relationships**:
- None (standalone entity)

**Indexes**:
- `idx_optimization_runs_job_id` UNIQUE on job_id
- `idx_optimization_runs_strategy_symbol` on (strategy, symbol)
- `idx_optimization_runs_status` on status
- `idx_optimization_runs_created_at` on created_at DESC

---

### 2. PriceAlert (PostgreSQL)

Configured price levels to monitor for open positions.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto | Unique identifier |
| ticket | Integer | NOT NULL, INDEX | MT4 position ticket |
| alert_type | String(50) | NOT NULL | Type: liquidity_sweep, breakeven, key_level, custom |
| price_level | Decimal(18,6) | NOT NULL | Price to monitor |
| direction | String(10) | NOT NULL | above/below - trigger when price crosses |
| triggered | Boolean | DEFAULT false | Whether alert has fired |
| triggered_at | DateTime(tz) | NULL | When alert was triggered |
| created_at | DateTime(tz) | auto | Creation timestamp |
| metadata | JSONB | NULL | Additional alert data |

**Relationships**:
- Logical link to MT4 positions via ticket (no FK due to external system)

**Indexes**:
- `idx_price_alerts_ticket` on ticket
- `idx_price_alerts_triggered` on triggered WHERE triggered = false
- `idx_price_alerts_active` on (ticket, triggered) WHERE triggered = false

**Constraints**:
- Unique on (ticket, alert_type, price_level) to prevent duplicates

---

### 3. OptimizationJob (Redis)

In-flight job state for active optimizations.

**Key Pattern**: `opt:job:{job_id}`

| Field | Type | Description |
|-------|------|-------------|
| status | String | pending/running/completed/failed/cancelled |
| params | JSON String | Serialized optimization parameters |
| progress_pct | Float | 0-100 completion percentage |
| combinations_tested | Integer | Number tested so far |
| total_combinations | Integer | Total to test |
| best_params | JSON String | Best parameters found so far |
| best_metric | Float | Best metric value so far |
| current_params | JSON String | Currently testing parameters |
| created_at | ISO DateTime | Job creation time |
| started_at | ISO DateTime | Execution start time |
| error | String | Error message if failed |

**TTL**: 86400 seconds (24 hours)

---

### 4. ActiveAlert (Redis)

Fast-lookup cache for active price alerts.

**Key Pattern**: `alert:{ticket}:{alert_type}:{id}`

| Field | Type | Description |
|-------|------|-------------|
| ticket | Integer | Position ticket |
| alert_type | String | Alert type |
| price_level | Float | Price to monitor |
| direction | String | above/below |
| db_id | UUID | Database record ID |
| created_at | ISO DateTime | Creation time |

**TTL**: No TTL (cleaned up when position closes or alert triggers)

---

### 5. SSEEvent (In-Memory / Redis Pub/Sub)

Real-time event for SSE streaming.

| Field | Type | Description |
|-------|------|-------------|
| event | String | Event type (job_started, job_progress, etc.) |
| data | JSON Object | Event payload |
| id | String | Unique event ID |
| timestamp | ISO DateTime | Event creation time |
| sequence | Integer | Monotonic sequence number |

**Event Types**:
- `job_started`: Optimization job began execution
- `job_progress`: Progress update (every 5% or 10 combinations)
- `job_complete`: Optimization finished successfully
- `job_failed`: Optimization failed with error
- `job_cancelled`: Optimization was cancelled
- `price_alert`: Price crossed configured level

**Redis Channel**: `sse:events`

---

## State Transitions

### OptimizationRun Status

```
pending ──► running ──► completed
    │           │
    │           └──► failed
    │           │
    └───────────┴──► cancelled
```

### PriceAlert Lifecycle

```
created (triggered=false)
    │
    ├──► triggered (triggered=true, triggered_at set)
    │
    └──► deleted (position closed, cleanup)
```

---

## Validation Rules

### OptimizationRun

1. `end_date` > `start_date`
2. `total_combinations` <= 10000
3. `param_grid` must be valid JSON with array values
4. `optimization_target` in ["sharpe_ratio", "total_return_pct", "profit_factor", "risk_adjusted_return"]
5. `initial_capital` > 0

### PriceAlert

1. `price_level` > 0
2. `direction` in ["above", "below"]
3. `alert_type` in ["liquidity_sweep", "breakeven", "key_level", "custom"]
4. No duplicate (ticket, alert_type, price_level) combinations

---

## Migration Notes

New Alembic migration required:
1. Create `optimization_runs` table
2. Create `price_alerts` table
3. Add indexes as specified above
4. Add unique constraint on price_alerts

No changes to existing tables.
