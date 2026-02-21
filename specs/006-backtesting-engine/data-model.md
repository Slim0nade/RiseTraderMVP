# Data Model: Backtesting Engine

**Feature**: 006-backtesting-engine
**Date**: 2025-12-11
**Status**: Phase 1 Design

## Overview

This document defines the data entities, relationships, and validation rules for the backtesting engine. All entities are implemented as SQLAlchemy async models with Alembic migrations for schema management.

## Entity Relationship Diagram

```text
┌─────────────────────────┐
│ BacktestConfiguration   │
│─────────────────────────│
│ PK: id (UUID)           │
│    name                 │
│    date_range           │
│    initial_capital      │
│    execution_mode       │
│    config_params (JSON) │
│    created_at           │
└─────────┬───────────────┘
          │
          │ 1:N
          ▼
┌─────────────────────────┐        ┌──────────────────────┐
│ BacktestRun             │   1:N  │ SimulatedTrade       │
│─────────────────────────│◄───────┤──────────────────────┤
│ PK: id (UUID)           │        │ PK: id (UUID)        │
│ FK: config_id           │        │ FK: backtest_run_id  │
│    status               │        │    symbol            │
│    start_time           │        │    action            │
│    end_time             │        │    entry_timestamp   │
│    total_return_pct     │        │    entry_price       │
│    sharpe_ratio         │        │    quantity          │
│    max_drawdown_pct     │        │    exit_timestamp    │
│    metrics (JSON)       │        │    exit_price        │
│    equity_curve (JSON)  │        │    gross_pnl         │
└─────────┬───────────────┘        │    fees_paid         │
          │                        │    net_pnl           │
          │ 1:N                    │    holding_duration  │
          ▼                        │    decision_context  │
┌─────────────────────────┐        └──────────────────────┘
│ PortfolioSnapshot       │
│─────────────────────────│        ┌──────────────────────┐
│ PK: id (UUID)           │   1:N  │ AgentDecisionLog     │
│ FK: backtest_run_id     │◄───────┤──────────────────────┤
│    timestamp            │        │ PK: id (UUID)        │
│    cash_balance         │        │ FK: backtest_run_id  │
│    positions (JSON)     │        │    timestamp         │
│    total_value          │        │    agent_identifier  │
│    unrealized_pnl       │        │    decision_type     │
│    realized_pnl         │        │    input_data (JSON) │
└─────────────────────────┘        │    output_decision   │
                                   │    execution_outcome │
                                   └──────────────────────┘

┌─────────────────────────┐
│ ParameterGrid           │
│─────────────────────────│
│ PK: id (UUID)           │
│    name                 │
│    base_config_id (FK)  │
│    parameters (JSON)    │
│    created_at           │
└─────────┬───────────────┘
          │
          │ 1:N
          ▼
┌─────────────────────────┐
│ GridSearchResult        │
│─────────────────────────│
│ PK: id (UUID)           │
│ FK: grid_id             │
│ FK: backtest_run_id     │
│    parameter_values     │
│    rank_by_sharpe       │
│    rank_by_return       │
│    statistical_sig      │
└─────────────────────────┘
```

## Core Entities

### 1. BacktestConfiguration

**Purpose**: Defines all parameters for a backtest run. Reusable across multiple executions.

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| name | VARCHAR(255) | NOT NULL | Human-readable name (e.g., "Q1 2023 Conservative") |
| symbol | VARCHAR(50) | NOT NULL | Trading symbol (e.g., "EURUSD", "BTC-USD") |
| start_date | TIMESTAMP | NOT NULL | Backtest start (UTC, inclusive) |
| end_date | TIMESTAMP | NOT NULL | Backtest end (UTC, inclusive) |
| initial_capital | NUMERIC(18,2) | NOT NULL, > 0 | Starting account balance |
| execution_mode | ENUM | NOT NULL | 'full_pipeline' or 'synthetic_fast' |
| agent_config_ref | VARCHAR(255) | NULL | Reference to agent configuration (for full mode) |
| slippage_pct | NUMERIC(8,6) | DEFAULT 0.001 | Slippage percentage (0.1% default) |
| commission_pct | NUMERIC(8,6) | DEFAULT 0.0005 | Commission percentage (0.05% default) |
| commission_fixed | NUMERIC(10,2) | DEFAULT 0.0 | Fixed commission per trade |
| max_leverage | NUMERIC(5,2) | DEFAULT 1.0 | Maximum leverage allowed (1.0 = no leverage) |
| allow_short_selling | BOOLEAN | DEFAULT FALSE | Whether short positions are allowed |
| config_params | JSONB | NULL | Mode-specific config (synthetic rules, agent settings) |
| created_at | TIMESTAMP | NOT NULL | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL | Last update timestamp |

**Validation Rules**:
- `end_date > start_date`
- `initial_capital > 0`
- `slippage_pct >= 0 AND slippage_pct < 1.0`
- `commission_pct >= 0 AND commission_pct < 1.0`
- `max_leverage >= 1.0 AND max_leverage <= 10.0`
- If `execution_mode == 'full_pipeline'`, `agent_config_ref` MUST NOT be NULL

**Indexes**:
- `idx_backtest_config_name` on `(name)`
- `idx_backtest_config_symbol` on `(symbol, start_date, end_date)`

**Example**:
```python
config = BacktestConfiguration(
    name="Q1_2023_Conservative_RSI",
    symbol="EURUSD",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 3, 31, tzinfo=timezone.utc),
    initial_capital=Decimal("10000.00"),
    execution_mode=ExecutionMode.SYNTHETIC_FAST,
    slippage_pct=Decimal("0.001"),
    commission_pct=Decimal("0.0005"),
    config_params={
        "ma_short": 10,
        "ma_long": 50,
        "rsi_oversold": 30,
        "rsi_overbought": 70
    }
)
```

---

### 2. BacktestRun

**Purpose**: Represents a single execution of a backtest configuration. Stores results and performance metrics.

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| config_id | UUID | FK, NOT NULL | References BacktestConfiguration.id |
| status | ENUM | NOT NULL | 'running', 'completed', 'failed', 'timeout' |
| start_time | TIMESTAMP | NOT NULL | Backtest execution start time |
| end_time | TIMESTAMP | NULL | Backtest completion time (NULL if running) |
| random_seed | INTEGER | NULL | Random seed for deterministic replay |
| total_return_pct | NUMERIC(10,4) | NULL | Total return percentage (NULL if not completed) |
| sharpe_ratio | NUMERIC(10,4) | NULL | Annualized Sharpe ratio |
| max_drawdown_pct | NUMERIC(10,4) | NULL | Maximum drawdown percentage |
| max_drawdown_duration_days | INTEGER | NULL | Drawdown duration in days |
| win_rate | NUMERIC(5,4) | NULL | Percentage of winning trades (0-1) |
| total_trades | INTEGER | DEFAULT 0 | Total number of trades executed |
| avg_trade_duration_hours | NUMERIC(10,2) | NULL | Average holding period |
| profit_factor | NUMERIC(10,4) | NULL | Gross profit / gross loss |
| final_capital | NUMERIC(18,2) | NULL | Ending account balance |
| metrics | JSONB | NULL | Full metrics dict (equity curve, trade stats) |
| error_message | TEXT | NULL | Error details if status='failed' |
| candles_processed | INTEGER | DEFAULT 0 | Number of candles replayed |
| agent_decisions_count | INTEGER | DEFAULT 0 | Number of agent decisions logged (full mode) |

**Validation Rules**:
- `end_time > start_time` (if end_time is not NULL)
- If `status == 'completed'`, all metric fields MUST NOT be NULL
- `win_rate >= 0.0 AND win_rate <= 1.0`
- `total_trades >= 0`

**Indexes**:
- `idx_backtest_run_config_status` on `(config_id, status)`
- `idx_backtest_run_start_time` on `(start_time DESC)`

**State Transitions**:
```text
NULL ──────────► running ──────────► completed
                    │                    │
                    ├──────────► failed  │
                    │                    │
                    └──────────► timeout │
```

**Example**:
```python
run = BacktestRun(
    config_id=config.id,
    status=RunStatus.COMPLETED,
    start_time=datetime(2025, 12, 11, 10, 0, 0, tzinfo=timezone.utc),
    end_time=datetime(2025, 12, 11, 10, 28, 45, tzinfo=timezone.utc),
    random_seed=42,
    total_return_pct=Decimal("15.75"),
    sharpe_ratio=Decimal("1.85"),
    max_drawdown_pct=Decimal("8.50"),
    win_rate=Decimal("0.62"),
    total_trades=47,
    final_capital=Decimal("11575.00"),
    candles_processed=132000
)
```

---

### 3. SimulatedTrade

**Purpose**: Records every trade executed during a backtest. Provides trade-by-trade audit trail.

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| backtest_run_id | UUID | FK, NOT NULL | References BacktestRun.id |
| symbol | VARCHAR(50) | NOT NULL | Trading symbol |
| action | ENUM | NOT NULL | 'buy', 'sell', 'close_long', 'close_short' |
| entry_timestamp | TIMESTAMP | NOT NULL | Trade entry time (UTC) |
| entry_price | NUMERIC(18,8) | NOT NULL | Entry price |
| quantity | NUMERIC(18,8) | NOT NULL, > 0 | Trade quantity/lot size |
| exit_timestamp | TIMESTAMP | NULL | Trade exit time (NULL if still open) |
| exit_price | NUMERIC(18,8) | NULL | Exit price (NULL if still open) |
| gross_pnl | NUMERIC(18,2) | NULL | P&L before fees (NULL if open) |
| fees_paid | NUMERIC(18,2) | NOT NULL | Total fees (slippage + commission) |
| net_pnl | NUMERIC(18,2) | NULL | P&L after fees (NULL if open) |
| holding_duration_seconds | INTEGER | NULL | Time between entry and exit |
| decision_context | JSONB | NULL | Agent decision rationale (full mode) |
| slippage_applied | NUMERIC(18,8) | NOT NULL | Actual slippage on entry |

**Validation Rules**:
- `quantity > 0`
- If `exit_timestamp` is NOT NULL:
  - `exit_timestamp > entry_timestamp`
  - `exit_price` MUST NOT be NULL
  - `gross_pnl` MUST NOT be NULL
  - `net_pnl = gross_pnl - fees_paid`
- `fees_paid >= 0`

**Indexes**:
- `idx_simulated_trade_run` on `(backtest_run_id, entry_timestamp)`
- `idx_simulated_trade_symbol` on `(symbol, entry_timestamp)`

**Derived Fields** (calculated on query, not stored):
- `is_profitable`: `net_pnl > 0`
- `return_pct`: `net_pnl / (entry_price * quantity) * 100`

**Example**:
```python
trade = SimulatedTrade(
    backtest_run_id=run.id,
    symbol="EURUSD",
    action=TradeAction.BUY,
    entry_timestamp=datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
    entry_price=Decimal("1.08450"),
    quantity=Decimal("10000"),  # 0.1 lot
    exit_timestamp=datetime(2023, 1, 16, 9, 15, 0, tzinfo=timezone.utc),
    exit_price=Decimal("1.08720"),
    gross_pnl=Decimal("27.00"),
    fees_paid=Decimal("1.62"),  # Slippage + commission
    net_pnl=Decimal("25.38"),
    holding_duration_seconds=67500,  # ~18.75 hours
    decision_context={"agent": "SignalGenerator", "rsi": 28.5}
)
```

---

### 4. PortfolioSnapshot

**Purpose**: Periodic snapshots of portfolio state during backtest. Enables equity curve generation and state reconstruction.

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| backtest_run_id | UUID | FK, NOT NULL | References BacktestRun.id |
| timestamp | TIMESTAMP | NOT NULL | Snapshot time (UTC) |
| cash_balance | NUMERIC(18,2) | NOT NULL | Available cash |
| positions | JSONB | NOT NULL | List of open positions [{symbol, qty, entry_price}] |
| total_value | NUMERIC(18,2) | NOT NULL | Cash + unrealized position value |
| unrealized_pnl | NUMERIC(18,2) | NOT NULL | Mark-to-market P&L on open positions |
| realized_pnl | NUMERIC(18,2) | NOT NULL | Cumulative P&L from closed trades |
| buying_power | NUMERIC(18,2) | NOT NULL | Available capital for new trades |

**Validation Rules**:
- `cash_balance >= 0` (unless margin trading enabled)
- `total_value = cash_balance + sum(position_value for each position)`
- `buying_power <= total_value * max_leverage`

**Snapshot Frequency**:
- **Full mode**: Snapshot after each trade execution
- **Synthetic mode**: Snapshot every N candles (configurable, default 1000)
- **RL environment**: Snapshot at every `step()` call

**Indexes**:
- `idx_portfolio_snapshot_run_time` on `(backtest_run_id, timestamp)`

**Example**:
```python
snapshot = PortfolioSnapshot(
    backtest_run_id=run.id,
    timestamp=datetime(2023, 1, 20, 10, 0, 0, tzinfo=timezone.utc),
    cash_balance=Decimal("9500.00"),
    positions=[
        {"symbol": "EURUSD", "quantity": 10000, "entry_price": 1.0845, "current_price": 1.0872}
    ],
    total_value=Decimal("10027.00"),
    unrealized_pnl=Decimal("27.00"),
    realized_pnl=Decimal("0.00"),
    buying_power=Decimal("10027.00")
)
```

---

### 5. AgentDecisionLog

**Purpose**: Detailed audit log of all agent decisions during full pipeline mode. Critical for debugging and compliance.

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| backtest_run_id | UUID | FK, NOT NULL | References BacktestRun.id |
| timestamp | TIMESTAMP | NOT NULL | Decision timestamp (UTC) |
| agent_identifier | VARCHAR(255) | NOT NULL | Agent name (e.g., "SignalGeneratorAgent") |
| decision_type | ENUM | NOT NULL | 'signal', 'risk', 'execution', 'other' |
| input_data | JSONB | NOT NULL | All inputs to agent decision (market data, state) |
| output_decision | JSONB | NOT NULL | Agent's decision output |
| execution_outcome | VARCHAR(50) | NULL | Result: 'accepted', 'rejected', 'timeout', etc. |
| processing_time_ms | INTEGER | NULL | Time taken for agent to decide |
| correlation_id | UUID | NULL | Links related decisions (same market event) |

**Validation Rules**:
- `processing_time_ms >= 0` (if not NULL)
- `agent_identifier` MUST match known agent names (validated at application layer)

**Indexes**:
- `idx_agent_log_run_time` on `(backtest_run_id, timestamp)`
- `idx_agent_log_agent` on `(agent_identifier, timestamp)`
- `idx_agent_log_correlation` on `(correlation_id)`

**Example**:
```python
log = AgentDecisionLog(
    backtest_run_id=run.id,
    timestamp=datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
    agent_identifier="SignalGeneratorAgent",
    decision_type=DecisionType.SIGNAL,
    input_data={
        "candles": [...],
        "rsi": 28.5,
        "ma_short": 1.0840,
        "ma_long": 1.0855
    },
    output_decision={
        "action": "BUY",
        "confidence": 0.85,
        "rationale": "RSI oversold + MA crossover"
    },
    execution_outcome="accepted",
    processing_time_ms=120,
    correlation_id=UUID("...")
)
```

---

### 6. ParameterGrid

**Purpose**: Defines a grid of parameter combinations for batch optimization (hyperparameter search).

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| name | VARCHAR(255) | NOT NULL | Grid name (e.g., "RSI Threshold Sweep") |
| base_config_id | UUID | FK, NOT NULL | Base configuration to vary |
| parameters | JSONB | NOT NULL | Parameter definitions: {param: [values]} |
| total_combinations | INTEGER | NOT NULL | Total number of configs to test |
| created_at | TIMESTAMP | NOT NULL | Creation timestamp |

**Parameter Schema** (in `parameters` JSONB):
```json
{
  "ma_short": [5, 10, 15, 20],
  "ma_long": [30, 50, 100],
  "rsi_oversold": [20, 25, 30],
  "rsi_overbought": [70, 75, 80]
}
// Total combinations: 4 * 3 * 3 * 3 = 108
```

**Validation Rules**:
- `parameters` MUST be valid JSON dict with list values
- `total_combinations = product(len(values) for each param)`
- `total_combinations <= 1000` (safety limit for reasonable execution time)

**Indexes**:
- `idx_parameter_grid_name` on `(name)`

**Example**:
```python
grid = ParameterGrid(
    name="RSI_Threshold_Optimization",
    base_config_id=config.id,
    parameters={
        "rsi_oversold": [20, 25, 30, 35],
        "rsi_overbought": [65, 70, 75, 80]
    },
    total_combinations=16  # 4 * 4
)
```

---

### 7. GridSearchResult

**Purpose**: Links parameter grid combinations to their backtest results. Enables ranking and comparison.

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique identifier |
| grid_id | UUID | FK, NOT NULL | References ParameterGrid.id |
| backtest_run_id | UUID | FK, NOT NULL | References BacktestRun.id |
| parameter_values | JSONB | NOT NULL | Specific parameter values for this run |
| rank_by_sharpe | INTEGER | NULL | Rank by Sharpe ratio (1 = best) |
| rank_by_return | INTEGER | NULL | Rank by total return (1 = best) |
| rank_by_drawdown | INTEGER | NULL | Rank by max drawdown (1 = lowest) |
| is_statistically_significant | BOOLEAN | DEFAULT FALSE | Whether results differ significantly from baseline |

**Validation Rules**:
- `rank_by_sharpe > 0` (if not NULL)
- `rank_by_return > 0` (if not NULL)
- `rank_by_drawdown > 0` (if not NULL)

**Indexes**:
- `idx_grid_result_grid_rank` on `(grid_id, rank_by_sharpe)`
- `idx_grid_result_run` on `(backtest_run_id)`

**Example**:
```python
result = GridSearchResult(
    grid_id=grid.id,
    backtest_run_id=run.id,
    parameter_values={"rsi_oversold": 30, "rsi_overbought": 70},
    rank_by_sharpe=1,  # Best Sharpe in this grid
    rank_by_return=3,  # Third best return
    rank_by_drawdown=2,  # Second lowest drawdown
    is_statistically_significant=True
)
```

---

## Database Migrations

**Migration**: `001_create_backtesting_tables`

**Up**:
```sql
-- Create ENUM types
CREATE TYPE execution_mode AS ENUM ('full_pipeline', 'synthetic_fast');
CREATE TYPE run_status AS ENUM ('running', 'completed', 'failed', 'timeout');
CREATE TYPE trade_action AS ENUM ('buy', 'sell', 'close_long', 'close_short');
CREATE TYPE decision_type AS ENUM ('signal', 'risk', 'execution', 'other');

-- Create tables in dependency order
CREATE TABLE backtest_configurations (...);
CREATE TABLE backtest_runs (...);
CREATE TABLE simulated_trades (...);
CREATE TABLE portfolio_snapshots (...);
CREATE TABLE agent_decision_logs (...);
CREATE TABLE parameter_grids (...);
CREATE TABLE grid_search_results (...);

-- Create indexes
CREATE INDEX ... ;
```

**Down**:
```sql
-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS grid_search_results CASCADE;
DROP TABLE IF EXISTS parameter_grids CASCADE;
DROP TABLE IF EXISTS agent_decision_logs CASCADE;
DROP TABLE IF EXISTS portfolio_snapshots CASCADE;
DROP TABLE IF EXISTS simulated_trades CASCADE;
DROP TABLE IF EXISTS backtest_runs CASCADE;
DROP TABLE IF EXISTS backtest_configurations CASCADE;

-- Drop ENUM types
DROP TYPE IF EXISTS decision_type;
DROP TYPE IF EXISTS trade_action;
DROP TYPE IF EXISTS run_status;
DROP TYPE IF EXISTS execution_mode;
```

---

## Data Access Patterns

### Common Queries

**1. Get all backtest runs for a configuration**:
```sql
SELECT * FROM backtest_runs
WHERE config_id = :config_id
ORDER BY start_time DESC;
```

**2. Get trade log for a specific run**:
```sql
SELECT * FROM simulated_trades
WHERE backtest_run_id = :run_id
ORDER BY entry_timestamp ASC;
```

**3. Build equity curve from snapshots**:
```sql
SELECT timestamp, total_value
FROM portfolio_snapshots
WHERE backtest_run_id = :run_id
ORDER BY timestamp ASC;
```

**4. Find top-performing parameter combinations**:
```sql
SELECT gs.parameter_values, br.sharpe_ratio, br.total_return_pct
FROM grid_search_results gs
JOIN backtest_runs br ON gs.backtest_run_id = br.id
WHERE gs.grid_id = :grid_id
ORDER BY gs.rank_by_sharpe ASC
LIMIT 10;
```

**5. Agent decision audit trail**:
```sql
SELECT agent_identifier, decision_type, input_data, output_decision
FROM agent_decision_logs
WHERE backtest_run_id = :run_id
  AND timestamp BETWEEN :start_time AND :end_time
ORDER BY timestamp ASC;
```

---

## Data Retention Policy

| Table | Retention | Archival Strategy |
|-------|-----------|-------------------|
| BacktestConfiguration | Indefinite | N/A (small table) |
| BacktestRun | 90 days (completed) | Archive to S3/cold storage after 90 days |
| SimulatedTrade | 90 days | Archive with parent BacktestRun |
| PortfolioSnapshot | 30 days | Keep only key snapshots (start, end, extremes) after 30 days |
| AgentDecisionLog | 30 days (full mode) | Archive or delete (large volume) |
| ParameterGrid | Indefinite | N/A |
| GridSearchResult | 90 days | Archive with parent grid |

**Rationale**: Backtesting generates high data volume (especially agent logs). Aggressive retention prevents database bloat while preserving key results for analysis.

---

## Summary

- **7 core entities** with clear relationships and validation rules
- **Async SQLAlchemy models** with full migration support
- **Comprehensive indexing** for performance (time-series queries, joins)
- **Audit trail** via AgentDecisionLog and SimulatedTrade
- **Extensible design** via JSONB columns for flexible configuration and metrics
- **Data retention** policy to manage database size

Ready for contract generation (Phase 1 continued).
