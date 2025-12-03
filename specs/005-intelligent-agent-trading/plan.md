# Implementation Plan: Intelligent Multi-Agent Trading System

**Branch**: `005-intelligent-agent-trading` | **Date**: 2025-12-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-intelligent-agent-trading/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build an autonomous AI trading system where ALL trading decisions (position sizing, stop-loss placement, take-profit targets) are made by intelligent agents that learn and adapt from data—eliminating hardcoded formulas. The system uses 12 specialized agents organized in 5 layers (Analysis, Debate, Decision, Execution, Supervisory) with reinforcement learning training for continuous improvement. Key innovations: (1) Adaptive position sizing based on Kelly criterion, regime, conviction, and correlation; (2) Intelligent stop-loss using market structure and probability analysis; (3) Probabilistic take-profit targeting based on ML forecast distributions; (4) Adversarial debate layer producing stress-tested trade ideas; (5) Multi-LLM support with cost optimization using quick-think/deep-think tiers.

**Technical Approach**: Multi-agent architecture using AutoGen 0.4 for agent orchestration (Swarm for sequential pipelines, SelectorGroupChat for debate, RoundRobinGroupChat for analysis), MCP (Model Context Protocol) for ML tool integration, MT4/ZMQ bridge for execution, PostgreSQL for persistence, Redis for state caching, dual-LLM allocation (Qwen3-14B for routine + DeepSeek-R1-14B for reasoning), RL training via PPO/SAC algorithms with walk-forward validation, structured Pydantic schemas for all inter-agent communication, portfolio-level capital allocation supporting 2-3 instruments simultaneously (Gold, Crude Oil).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**:
- Agent Framework: AutoGen 0.4 (autogen-agentchat>=0.4.0, autogen-ext[openai]>=0.4.0)
- LLM Integration: AutoGen OpenAIChatCompletionClient (unified interface for OpenAI, Anthropic, Google, Ollama via OpenAI-compatible API)
- Tool Protocol: MCP (Model Context Protocol) for ML model and calculator tool access
- RL Training: Stable-Baselines3 (PPO/SAC), Gymnasium (envs)
- Data/ML: Pydantic 2.5+, pandas, numpy
- Existing: FastAPI 0.104.1, SQLAlchemy 2.0.23 (async), asyncpg 0.29.0, Redis 5.0.1, PyZMQ 25.1.2

**⚠️ IMPORTANT FOR DEVELOPERS**: AutoGen 0.4 is a complete rewrite from v0.2. The `pyautogen` package is deprecated. Before implementation, search the latest AutoGen 0.4 documentation at https://microsoft.github.io/autogen/ to verify current API patterns for:
- `AssistantAgent` (agent definition with model_client injection)
- `Swarm` (sequential hand-off orchestration)
- `SelectorGroupChat` (dynamic agent selection)
- `RoundRobinGroupChat` (deterministic turn-taking)
- `OpenAIChatCompletionClient` (works with both OpenAI and Ollama)
- `@function_tool` decorator (MCP tool registration)
**Storage**:
- PostgreSQL 15+ (agent decision logs, trading history, RL training runs, model configurations, portfolio allocations)
- Redis 7+ (pub/sub events, agent state, cached ML forecasts)
- MLflow (RL model checkpoints, experiment tracking)
**Testing**: pytest 7.4+, pytest-asyncio, pytest-mock, httpx (async client testing), Hypothesis (property-based testing for agent logic)
**Target Platform**: Linux server (Docker containers), local development on macOS
**Project Type**: Backend service with multi-agent orchestration
**Performance Goals**:
- Decision latency: <5s (INTRADAY), <30s (SWING), <5min (POSITION)
- ML tool calls (MCP): <100ms p95
- Agent-to-agent event propagation: <50ms p95
- RL training throughput: 100k environment steps/hour
**Constraints**:
- No real-time online learning (RL offline only for safety)
- English language only for agent reasoning
- Synchronous decision pipeline per signal (no parallel agent execution within one signal)
- Paper trading validation required before live deployment
**Scale/Scope**:
- 12 specialized agents × 2-3 instruments = ~30-36 agent instances
- 10k+ trading decisions per month per instrument
- 2+ years historical data for RL training
- Event throughput: 100+ events/sec during high-volatility periods

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ Principle I: Test-First Development (TDD)

**Status**: COMPLIANT
**Plan**:
- Unit tests for each agent's decision logic (mock dependencies)
- Integration tests for agent communication via MCP events
- Contract tests for MCP tool schemas
- E2E tests for full decision pipeline (analysis → debate → decision → execution)
- RL training tests with deterministic environment seeds
- Target: 85%+ coverage per constitution

### ⚠️ Principle II: Security-First Design

**Status**: PARTIAL - Pre-production blockers identified
**Blocking Requirements** (from constitution):
1. **MT4 Connection Encryption**: Currently exposed without encryption (Feature 001). MUST implement CurveZMQ or VPN before live trading. FR-020 references existing MT4/ZMQ bridge - security enhancement required but not in this feature scope.
2. **API Authentication**: Agent management API requires JWT + API key auth (not in this feature scope - system-level concern).
3. **Rate Limiting**: Agent system internal communication via MCP doesn't expose public endpoints - N/A for this feature.
4. **Secrets Management**: LLM API keys, database credentials in environment variables (already enforced project-wide).

**Compliance Plan**:
- Agent decision audit logs (FR implements full context logging per constitution)
- Input validation for all MCP tool responses
- Security testing for agent logic (no unauthorized trade decisions)
- Note: MT4 encryption and API auth are system-level concerns outside this feature's scope. Flagged for Phase 4 (Weeks 8-9) per project timeline.

### ✅ Principle III: Observability & Monitoring

**Status**: COMPLIANT
**Plan**:
- Structured JSON logging with correlation IDs for all agent decisions
- Prometheus metrics for agent latency, decision counts, RL training progress
- Agent decision audit logs with timestamp, agent ID, inputs, decision, rationale, outcome
- Distributed tracing for decision pipeline flows
- Performance targets align with SC-009: <5s INTRADAY, <30s SWING, <5min POSITION

### ✅ Principle IV: Agent Autonomy with Guardrails

**Status**: COMPLIANT
**Plan**:
- FR-011: Risk Overseer Agent enforces portfolio-level limits (circuit breakers)
- FR-005: Position sizing within allocated capital envelope (hard limits)
- FR-018: Portfolio allocation constrains per-strategy capital
- Agent decisions logged with full rationale for auditability
- Emergency stop via Risk Overseer (can halt all trading)
- Layered risk checks: Position Sizing Agent → Risk Overseer Agent → hard limits

### ✅ Principle V: Paper Trading Before Live Trading

**Status**: COMPLIANT
**Plan**:
- Assumptions section specifies paper trading mode for A/B testing and validation
- FR-016: A/B tests run in paper trading mode
- Backtesting environment (FR-012) provides deterministic replay for validation
- Gradual rollout: Enable strategies one instrument at a time (Gold first, then Crude Oil)
- Success criteria validation in paper mode before live deployment

### ✅ Principle VI: Repository Pattern & Service Layer

**Status**: COMPLIANT
**Plan**:
- Agents interact with data via service layer (never direct DB access)
- New repositories: `AgentDecisionLogRepository`, `RLTrainingRunRepository`, `ModelConfigurationRepository`, `PortfolioAllocationRepository`
- Services: `AgentOrchestrationService`, `RLTrainingService`, `MCPToolService`
- Async operations using SQLAlchemy 2.0+ (already established project pattern)

### ✅ Principle VII: Event-Driven Agent Communication

**Status**: COMPLIANT
**Plan**:
- FR-017: Typed schemas for all inter-agent events (Pydantic)
- MCP server routes events between agents (no direct calls)
- Redis pub/sub for async message delivery
- Event example: `new_tick` → `signal_generated` → `trade_validated` → `trade_executed`
- Idempotent event handlers (safe to replay)
- Circuit breakers in MCP server prevent event storms

### ✅ Principle VIII: Version Control & Backward Compatibility

**Status**: COMPLIANT
**Plan**:
- Alembic migrations for new tables (reversible down migrations)
- Pydantic schema versioning for agent events (breaking changes require new version)
- Configuration defaults for existing deployments (portfolio allocation starts with single strategy)
- Zero-downtime deployment: Agents can be restarted independently

## Project Structure

### Documentation (this feature)

```text
specs/005-intelligent-agent-trading/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0: Agent framework selection, RL algorithms, LLM integration patterns
├── data-model.md        # Phase 1: Agent state, decision logs, RL training runs, portfolio allocations
├── quickstart.md        # Phase 1: Running agent system, paper trading mode, RL training
├── contracts/           # Phase 1: MCP tool schemas, agent event schemas
│   ├── mcp-tools.yaml   # MCP tool contracts (get_tcn_forecast, calculate_kelly, etc.)
│   └── agent-events.yaml # Agent event schemas (TradeIntent, PositionSize, etc.)
└── tasks.md             # Phase 2: Task breakdown (/speckit.tasks - not created yet)
```

### Source Code (repository root)

```text
src/
├── agents/                          # NEW: Intelligent agent system (AutoGen 0.4)
│   ├── base/
│   │   ├── base_agent.py           # Abstract agent with logging, health checks, common patterns
│   │   └── agent_config.py         # Agent configuration schema (Pydantic)
│   ├── providers/                        # LLM client abstractions (AutoGen ChatCompletionClient)
│   │   ├── openai_client.py              # OpenAIChatCompletionClient for GPT-4o/o1/o3
│   │   ├── anthropic_client.py           # Custom ChatCompletionClient for Claude
│   │   ├── ollama_client.py              # OpenAIChatCompletionClient with Ollama base_url
│   │   └── client_factory.py             # Creates clients from config (quick-think vs deep-think)
│   ├── analysis/
│   │   ├── technical_analyst_agent.py    # FR-001: Consumes ML forecasts, produces TechnicalReport
│   │   ├── fundamental_analyst_agent.py  # FR-002: Economic calendar, correlations, FundamentalReport
│   │   └── sentiment_analyst_agent.py    # FR-003: Positioning data, SentimentReport
│   ├── debate/
│   │   ├── bull_researcher_agent.py      # FR-008: Builds bull case with evidence
│   │   └── bear_researcher_agent.py      # FR-008: Builds bear case with rebuttals (uses deep-think LLM)
│   ├── decision/
│   │   ├── trade_decision_agent.py       # FR-004: LONG/SHORT/NO_TRADE with conviction
│   │   ├── position_sizing_agent.py      # FR-005: Dynamic sizing (Kelly, regime, correlation)
│   │   ├── stop_loss_agent.py            # FR-006: Structure-based stop placement
│   │   └── take_profit_agent.py          # FR-007: Probabilistic targets from ML distributions
│   ├── execution/
│   │   ├── execution_agent.py            # FR-009: Order placement via MT4/ZMQ
│   │   ├── position_monitor_agent.py     # FR-010: Trailing stops, target adjustments
│   │   └── risk_overseer_agent.py        # FR-011: Portfolio limits, circuit breakers
│   ├── teams/                            # AutoGen 0.4 team orchestration patterns
│   │   ├── analysis_team.py              # RoundRobinGroupChat: Technical → Fundamental → Sentiment
│   │   ├── debate_team.py                # SelectorGroupChat: Bull ↔ Bear moderated debate
│   │   ├── trading_pipeline.py           # Swarm: Analysis → Debate → Decision → Execution
│   │   ├── strategy_team.py              # Manages full agent team per instrument
│   │   └── team_factory.py               # Creates teams from model_config for A/B testing
│   ├── coordination/
│   │   ├── portfolio_allocator_agent.py  # FR-018: Dynamic capital allocation (optional)
│   │   └── agent_registry.py             # Agent instance tracking, health monitoring
│   ├── schemas/                          # FR-017: Pydantic schemas for structured communication
│   │   ├── events.py                     # Event schemas (agent-to-agent)
│   │   ├── decisions.py                  # TradeIntent, PositionSize, StopLoss, TakeProfit
│   │   └── reports.py                    # TechnicalReport, FundamentalReport, SentimentReport
│   └── tools/                            # MCP tool integration (for ML models/calculators only)
│       ├── mcp_tools.py                  # @function_tool decorated MCP calls for AutoGen
│       └── tool_registry.py              # Registers MCP tools with AutoGen agents
├── services/                        # Business logic services
│   ├── agent_orchestration_service.py    # Start/stop agents, health monitoring
│   ├── mcp_tool_service.py               # MCP tool registration and invocation
│   └── rl_training_service.py            # Offline RL training orchestration
├── database/
│   ├── models/
│   │   ├── agent_decision_log.py         # Audit log: timestamp, agent, inputs, decision, rationale
│   │   ├── rl_training_run.py            # RL training metadata, checkpoints, metrics
│   │   ├── model_configuration.py        # A/B test configs (model assignments per agent)
│   │   ├── portfolio_allocation.py       # Strategy allocations (FR-018)
│   │   └── strategy_team.py              # Agent team assignments per instrument
│   └── repositories/
│       ├── agent_decision_log_repository.py
│       ├── rl_training_run_repository.py
│       ├── model_configuration_repository.py
│       └── portfolio_allocation_repository.py
├── ml/
│   ├── rl/                          # NEW: Reinforcement learning training
│   │   ├── environments/
│   │   │   ├── trading_env.py            # Gymnasium environment for backtesting
│   │   │   └── position_sizing_env.py    # Specific env for position sizing agent
│   │   ├── agents/                       # RL agents (not to confuse with trading agents)
│   │   │   ├── ppo_trainer.py            # PPO for discrete actions
│   │   │   └── sac_trainer.py            # SAC for continuous actions
│   │   ├── rewards/
│   │   │   └── reward_functions.py       # Agent-specific reward signals
│   │   └── validation/
│   │       └── walk_forward.py           # FR-014: Walk-forward validation
│   └── tools/                       # MCP tool implementations
│       ├── forecasting_tools.py          # get_tcn_forecast, get_tft_prediction, get_fedformer_regime
│       ├── calculation_tools.py          # calculate_kelly, calculate_atr
│       └── market_structure_tools.py     # get_support_resistance, detect_liquidity_clusters
├── api/
│   └── routes/
│       ├── agents.py                     # Agent management API (health, status, configuration)
│       └── rl_training.py                # Trigger RL training runs, view metrics
└── monitoring/
    └── agent_metrics.py                  # Prometheus metrics for agents

tests/
├── unit/
│   ├── agents/                      # Agent logic tests (mocked dependencies)
│   │   ├── test_position_sizing_agent.py
│   │   ├── test_stop_loss_agent.py
│   │   └── test_trade_decision_agent.py
│   ├── rl/
│   │   ├── test_trading_env.py           # Environment tests
│   │   └── test_reward_functions.py      # Reward function tests
│   └── tools/
│       └── test_mcp_tools.py             # MCP tool unit tests
├── integration/
│   ├── test_agent_communication.py       # Agent-to-agent via MCP
│   ├── test_decision_pipeline.py         # Full pipeline: analysis → decision → execution
│   └── test_rl_training.py               # RL training with deterministic seeds
├── contract/
│   ├── test_mcp_tool_schemas.py          # MCP tool input/output validation
│   └── test_agent_event_schemas.py       # Agent event schema validation
└── e2e/
    └── test_trading_workflow.py          # End-to-end: signal → decision → execution → audit

config/
├── agents/                          # NEW: Agent configuration
│   ├── agents.yaml                       # Agent registry, LLM assignments, risk limits
│   ├── portfolio_allocation.yaml         # Static portfolio allocations
│   └── rl_training_config.yaml           # RL hyperparameters, training schedules
└── ml/
    └── mcp_tools.yaml                    # MCP tool registration and schemas

scripts/
├── agents/                          # NEW: Agent management scripts
│   ├── start_agent_system.py             # Start all agents for an instrument
│   ├── run_rl_training.py                # Trigger offline RL training
│   └── evaluate_agent_performance.py     # Analyze agent decision logs
└── monitoring/
    └── check_agent_health.sh             # Health check for all agents
```

**Structure Decision**: Backend service with new `src/agents/` directory containing 5 layers of specialized agents. Follows existing RiseTrader patterns (repository pattern, service layer, async SQLAlchemy). Adds RL training infrastructure under `src/ml/rl/` and MCP tool implementations under `src/ml/tools/`. Configuration-driven agent system using YAML files in `config/agents/`.

## Complexity Tracking

No constitution violations requiring justification. All principles compliant with implementation plan.

**Note on Security Blockers**: MT4 connection encryption (Principle II, requirement 1) and API authentication (Principle II, requirement 2) are **system-level concerns** outside this feature's scope. These are tracked in the project-wide security roadmap (CLAUDE.md Phase 4: Weeks 8-9). This feature implements agent-specific security (decision audit logs, input validation, risk limits) as specified in FR-005, FR-011, and Principle IV compliance.
