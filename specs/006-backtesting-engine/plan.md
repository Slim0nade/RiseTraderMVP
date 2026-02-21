# Implementation Plan: Backtesting Engine

**Branch**: `006-backtesting-engine` | **Date**: 2025-12-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-backtesting-engine/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build a backtesting engine that validates multi-agent trading decisions against historical market data. The engine supports two execution modes: (1) full agent pipeline mode with actual LLM-powered agent decisions for realistic validation, and (2) synthetic fast mode using rule-based logic for rapid hyperparameter search (100x+ faster). Core capabilities include realistic trade simulation with slippage and commissions, comprehensive P&L tracking, standard performance metrics (Sharpe ratio, drawdown, win rate), and a Gymnasium-compatible interface for reinforcement learning training.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing RiseTrader stack (SQLAlchemy 2.0+ async, asyncpg, pandas/numpy for metrics), Gymnasium (for RL environment interface), scipy (for statistical tests in A/B comparison)
**Storage**: PostgreSQL 15+ (existing 13.5M candle database from 001-mt4-integration)
**Testing**: pytest with async support, hypothesis for property-based testing of metrics calculations
**Target Platform**: Linux server (Docker containerized)
**Project Type**: Single backend service (backtesting engine module within existing src/ structure)
**Performance Goals**: 30 minutes for 6-month full-mode backtest (single symbol), 100x speedup for synthetic mode, 10,000+ RL episodes without memory leaks
**Constraints**: <100MB memory overhead per backtest run, deterministic replay (same config + date range = identical results), correlation 0.7+ between synthetic and full mode
**Scale/Scope**: Support 100+ parallel parameter configurations, handle years of historical data, process 13.5M candle database efficiently

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development ✅
- **Status**: COMPLIANT
- **Plan**: Backtesting engine requires comprehensive testing due to financial decision validation
  - Unit tests for portfolio state tracking, P&L calculations, metrics (Sharpe, drawdown, win rate)
  - Property-based tests (hypothesis) for deterministic replay and metric accuracy
  - Integration tests for historical data replay, agent integration (full/synthetic modes)
  - Contract tests for Gymnasium environment interface
  - E2E tests for complete backtest runs with known results
- **Target**: 85%+ coverage with tests written first before implementation

### II. Security-First Design ✅
- **Status**: COMPLIANT (backtesting is read-only simulation)
- **Assessment**: Backtesting engine is non-trading functionality - it simulates but never executes real trades
  - No MT4 connection required (uses historical data from database)
  - No external API exposure planned (used internally by agents/researchers)
  - Read-only database access for historical candle data
  - No secrets or sensitive data beyond existing database credentials
- **Note**: If API endpoints are added later for web dashboard, standard JWT + API key auth will be required

### III. Observability & Monitoring ✅
- **Status**: COMPLIANT
- **Plan**: Full observability for backtest execution and performance tracking
  - Structured logging (JSON) for backtest lifecycle events (start, progress, completion, errors)
  - Metrics tracking: backtest duration, candles processed/sec, memory usage, agent decision latency
  - Correlation IDs linking backtest runs to generated reports and trade logs
  - Agent decision logs in full pipeline mode (timestamp, agent, inputs, decision, rationale)
  - Performance monitoring: ensure 30min target for 6-month backtests, 100x synthetic speedup
- **Performance Targets**: Full mode 30min (6 months), synthetic mode <20sec, RL env <1ms per step

### IV. Agent Autonomy with Guardrails ✅
- **Status**: COMPLIANT
- **Plan**: Backtesting integrates with existing agent system with proper isolation
  - Full pipeline mode: uses actual configured agents via MCP event system
  - Synthetic mode: bypasses agents entirely (rule-based logic for speed)
  - Portfolio state validation: enforces capital limits, prevents impossible trades
  - Data validation: checks for gaps in historical data before backtest starts
  - Circuit breakers: timeout limits for long-running backtests, memory limits per run
  - Clear separation: backtest engine never modifies live trading state

### V. Paper Trading Before Live Trading ✅
- **Status**: COMPLIANT (N/A - backtesting is simulation, not live trading)
- **Assessment**: Backtesting engine validates strategies before paper/live deployment
  - This feature IS the validation layer mentioned in constitution principle V
  - Successful backtest results are prerequisite for paper trading approval
  - Enables evidence-based go/no-go decisions for strategy deployment

### VI. Repository Pattern & Service Layer ✅
- **Status**: COMPLIANT
- **Plan**: Clean architectural layers for backtesting functionality
  - Repository: `BacktestRepository` for storing/retrieving backtest configurations and results
  - Service: `BacktestService` orchestrates backtest execution, data replay, metrics calculation
  - Models: SQLAlchemy models for `BacktestConfiguration`, `BacktestRun`, `SimulatedTrade`
  - No direct DB access from backtesting engine logic - all through repositories
  - Async operations throughout (data streaming from PostgreSQL, parallel backtests)

### VII. Event-Driven Agent Communication ✅
- **Status**: COMPLIANT
- **Plan**: Integration with existing MCP event system for full pipeline mode
  - Full mode: backtesting engine emits synthetic market events → agents respond via MCP
  - Engine subscribes to agent decision events (signals, risk validation, execution)
  - Synthetic mode: bypasses MCP entirely (no agent events needed)
  - All agent interactions logged for post-backtest analysis
  - Idempotent event handling (backtest replay must be deterministic)

### VIII. Version Control & Backward Compatibility ✅
- **Status**: COMPLIANT
- **Plan**: Careful versioning for backtest configurations and result schemas
  - Database migrations (Alembic) for new tables: `backtest_configs`, `backtest_runs`, `simulated_trades`
  - Reversible migrations with down() methods
  - Configuration schema versioning: support multiple config formats as system evolves
  - Result format stability: existing backtests remain queryable after upgrades
  - Gymnasium environment interface follows standard API (widely stable)

### Pre-Production Security Blockers ✅
- **Status**: N/A (internal tool, not exposed)
- **Assessment**: Backtesting is development/research tool, not production trading system
  - No MT4 connection (uses historical data only)
  - No API authentication required initially (internal use)
  - If dashboard exposure added: will implement JWT + API key per constitution
  - Secrets management: uses existing database credentials (already in env vars)

### Gates Summary
**Result**: ✅ ALL GATES PASSED

No constitution violations. Backtesting engine is a validation/research tool that complements the existing trading system without exposing new security risks. Architecture follows repository pattern, event-driven design, and test-first principles. Ready to proceed to Phase 0 research.

## Project Structure

### Documentation (this feature)

```text
specs/006-backtesting-engine/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── backtesting-service.yaml  # OpenAPI spec for backtest endpoints (if exposed)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── database/
│   ├── models/
│   │   ├── backtest.py              # BacktestConfiguration, BacktestRun models
│   │   └── simulated_trade.py       # SimulatedTrade, PortfolioSnapshot models
│   └── repositories/
│       ├── backtest_repository.py   # CRUD for backtest configs and runs
│       └── market_data_repository.py # Historical candle queries (read-only)
│
├── services/
│   └── backtesting/
│       ├── __init__.py
│       ├── backtest_service.py      # Main orchestration service
│       ├── data_replay.py           # Historical data streaming engine
│       ├── portfolio_state.py       # Portfolio tracking and P&L calculation
│       ├── trade_simulator.py       # Order execution simulation (slippage, fills)
│       ├── metrics_calculator.py    # Sharpe, drawdown, win rate, profit factor
│       ├── agent_integrator.py      # Full pipeline mode - MCP event integration
│       ├── synthetic_engine.py      # Fast mode - rule-based decision logic
│       └── gymnasium_env.py         # RL environment wrapper
│
├── agents/
│   └── # No changes - existing agents used in full pipeline mode
│
└── utils/
    └── performance/
        └── batch_optimizer.py       # Parallel backtest execution for parameter grids

tests/
├── unit/
│   └── backtesting/
│       ├── test_portfolio_state.py       # Portfolio tracking logic
│       ├── test_trade_simulator.py       # Slippage, commission, fill logic
│       ├── test_metrics_calculator.py    # Sharpe, drawdown calculations
│       └── test_data_replay.py           # Historical replay correctness
│
├── integration/
│   └── backtesting/
│       ├── test_backtest_service.py      # Full backtest run integration
│       ├── test_agent_integration.py     # Full pipeline mode with MCP
│       ├── test_gymnasium_env.py         # RL environment contract tests
│       └── test_batch_optimization.py    # Parallel execution
│
└── contract/
    └── test_gymnasium_interface.py       # Gymnasium API compliance tests
```

**Structure Decision**: Single project structure (Option 1). Backtesting engine is a new module within the existing RiseTrader `src/` tree, specifically under `src/services/backtesting/`. This aligns with the repository pattern where backtesting service orchestrates repositories, models, and existing agents. No frontend changes required initially (research/internal tool). Tests follow existing three-tier structure (unit/integration/contract).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations - this section intentionally left empty. All constitution principles are satisfied.
