# Tasks: Intelligent Multi-Agent Trading System

**Input**: Design documents from `/specs/005-intelligent-agent-trading/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Organization**: Tasks grouped by user story (P1-P3) to enable independent implementation and testing

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US6)
- Include exact file paths in descriptions

## Path Conventions

- Repository root: `/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/`
- Source: `src/`
- Tests: `tests/`
- Configuration: `config/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and agent system structure

- [X] T001 Create agent system directory structure (src/agents/, src/ml/rl/, config/agents/)
- [X] T002 [P] Install agent system dependencies (autogen-agentchat>=0.4.0, autogen-ext[openai]>=0.4.0, stable-baselines3, gymnasium, mlflow). **⚠️ NOTE**: Search latest AutoGen 0.4 docs at https://microsoft.github.io/autogen/ before implementing - API may have changed
- [X] T003 [P] Configure pre-commit hooks for Pydantic schema validation
- [X] T004 [P] Create base configuration templates (config/agents/agents.yaml.template, config/agents/rl_training_config.yaml.template, config/agents/portfolio_allocation.yaml.template)
- [X] T005 [P] Setup MLflow tracking server configuration in docker-compose.yml
- [X] T006 [P] Create Ollama service definition in docker-compose.yml for local LLM inference (Qwen3-14B, DeepSeek-R1-14B)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database & Data Models

- [X] T007 Create Alembic migration for agent system tables (agents, decision_log, rl_training_runs, model_configurations, portfolio_allocations, strategy_teams, mcp_tools)
- [X] T008 [P] Create Agent SQLAlchemy model in src/database/models/agent.py
- [X] T009 [P] Create DecisionLog SQLAlchemy model with TimescaleDB hypertable in src/database/models/decision_log.py
- [X] T010 [P] Create RLTrainingRun SQLAlchemy model in src/database/models/rl_training_run.py
- [X] T011 [P] Create ModelConfiguration SQLAlchemy model in src/database/models/model_configuration.py
- [X] T012 [P] Create PortfolioAllocation SQLAlchemy model in src/database/models/portfolio_allocation.py
- [X] T013 [P] Create StrategyTeam SQLAlchemy model in src/database/models/strategy_team.py
- [X] T014 [P] Create MCPTool SQLAlchemy model in src/database/models/mcp_tool.py
- [X] T015 Apply Alembic migration and create TimescaleDB hypertable for decision_log
- [X] T016 [P] Create decision_log TimescaleDB indexes and retention policy (90 days)

### Pydantic Schemas (Agent Communication)

- [X] T017 [P] Create base event schema in src/agents/schemas/events.py
- [X] T018 [P] Create decision schemas (TradeIntent, PositionSize, StopLoss, TakeProfit) in src/agents/schemas/decisions.py
- [X] T019 [P] Create analyst report schemas (TechnicalReport, FundamentalReport, SentimentReport) in src/agents/schemas/reports.py
- [X] T020 [P] Create debate schema (DebateOutcome) in src/agents/schemas/reports.py
- [X] T021 [P] Create agent config schema (AgentConfig, AgentState) in src/agents/base/agent_config.py

### Repositories

- [X] T022 [P] Create AgentRepository in src/database/repositories/agent_repository.py
- [X] T023 [P] Create DecisionLogRepository with TimescaleDB queries in src/database/repositories/decision_log_repository.py
- [X] T024 [P] Create RLTrainingRunRepository in src/database/repositories/rl_training_run_repository.py
- [X] T025 [P] Create ModelConfigurationRepository in src/database/repositories/model_configuration_repository.py
- [X] T026 [P] Create PortfolioAllocationRepository in src/database/repositories/portfolio_allocation_repository.py
- [X] T027 [P] Create StrategyTeamRepository in src/database/repositories/strategy_team_repository.py
- [X] T028 [P] Create MCPToolRepository in src/database/repositories/mcp_tool_repository.py

### Core Agent Infrastructure (AutoGen 0.4)

**⚠️ CRITICAL**: Before implementing T029-T038, search AutoGen 0.4 documentation at https://microsoft.github.io/autogen/ to verify current API patterns. AutoGen 0.4 is a complete rewrite from v0.2 - the `pyautogen` package is deprecated.

- [X] T029 Create BaseAgent abstract class in src/agents/base/base_agent.py (logging, health checks, common patterns for wrapping AutoGen AssistantAgent)
- [X] T030 Create LLM provider clients in src/agents/providers/:
  - openai_client.py: Wrapper for AutoGen OpenAIChatCompletionClient (GPT-4o/o1/o3)
  - ollama_client.py: OpenAIChatCompletionClient with base_url="http://localhost:11434/v1" (Qwen3/DeepSeek-R1)
  - anthropic_client.py: Custom ChatCompletionClient implementing Anthropic API
  - google_client.py: Google Gemini client
  - model_router.py: Intelligent routing between quick-think vs deep-think vs structured clients
- [X] T031 Create MCP tool wrappers in src/agents/tools/mcp_tools.py (8 async functions for AutoGen agents)
- [X] T032 Create AutoGen team orchestration in src/agents/teams/:
  - analysis_team.py: RoundRobinGroupChat (Technical → Fundamental → Sentiment)
  - debate_team.py: SelectorGroupChat (Bull ↔ Bear moderated debate)
  - trading_pipeline.py: Sequential pipeline orchestration
  - team_factory.py: Factory for creating teams with appropriate LLM clients
- [X] T033 Create team_factory.py in src/agents/teams/ for A/B testing (creates teams with different model_client assignments)
- [X] T034 Create agent_registry.py in src/agents/coordination/ (agent instance tracking, health monitoring)
- [X] T035 [P] Create Prometheus metrics recorder in src/monitoring/agent_metrics.py

### MCP Tools Implementation (FR-019)

- [X] T035 [P] Implement get_tcn_forecast MCP tool in src/ml/tools/forecasting_tools.py
- [X] T036 [P] Implement get_tft_prediction MCP tool in src/ml/tools/forecasting_tools.py
- [X] T037 [P] Implement get_fedformer_regime MCP tool in src/ml/tools/forecasting_tools.py
- [X] T038 [P] Implement calculate_kelly MCP tool in src/ml/tools/calculation_tools.py
- [X] T039 [P] Implement calculate_atr MCP tool in src/ml/tools/calculation_tools.py
- [X] T040 [P] Implement get_support_resistance MCP tool in src/ml/tools/market_structure_tools.py
- [X] T041 [P] Implement detect_liquidity_clusters MCP tool in src/ml/tools/market_structure_tools.py
- [X] T042 [P] Implement get_economic_events MCP tool in src/ml/tools/data_retrieval_tools.py
- [X] T043 [P] Implement get_cot_data MCP tool in src/ml/tools/data_retrieval_tools.py
- [X] T044 Register all MCP tools in mcp_tools table with schemas from contracts/mcp-tools.yaml (implemented in scripts/agents/register_mcp_tools.py)
- [X] T045 Implement MCP tool circuit breaker and caching in MCPClient

### Services

- [X] T046 Create AgentOrchestrationService in src/services/agent_orchestration_service.py (start/stop agents, health monitoring) - ALREADY EXISTS as agent_service.py
- [X] T047 Create MCPToolService in src/services/mcp_tool_service.py (tool registration, invocation)
- [X] T048 Create RLTrainingService skeleton in src/services/rl_training_service.py (offline RL orchestration)

### API Endpoints

- [X] T049 [P] Create agent management API routes in src/api/routes/agents.py (health, status, configuration) - ALREADY EXISTS
- [X] T050 [P] Create RL training API routes in src/api/routes/rl_training.py (trigger training, view metrics)

### Scripts

- [X] T051 [P] Create start_agent_system.py script in scripts/agents/
- [X] T052 [P] Create monitor_agents.py script in scripts/agents/
- [X] T053 [P] Create run_rl_training.py skeleton in scripts/agents/

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 2.5: P0 Bug Fixes (Priority: P0 - BLOCKERS) 🔥

**Goal**: Fix blocking issues discovered during specification session 2025-12-05

**Independent Test**: Verify TradeDecisionAgent can be instantiated with "trade_decision" AgentType enum value; verify create_quick_think_client and create_deep_think_client functions are importable from src.agents.providers

### Critical Bug Fixes

- [X] T054 [P0] Add TRADE_DECISION = "trade_decision" to AgentType enum in src/agents/base/agent_config.py
- [X] T055 [P0] Export create_quick_think_client and create_deep_think_client functions in src/agents/providers/__init__.py

**Checkpoint**: P0 blockers resolved - TradeDecisionAgent can be properly configured

---

## Phase 3: User Story 1 - Adaptive Position Sizing (Priority: P1) 🎯 MVP

**Goal**: Implement intelligent position sizing that varies based on Kelly criterion, market regime, trade conviction, portfolio correlation, and event risk—eliminating fixed percentage approaches

**Independent Test**: Execute trades across different scenarios (high volatility + drawdown, low volatility + favorable, high correlation exposure) and verify position sizes vary by 50%+ with documented reasoning

### Analysis Layer Agents (for US1 context)

- [X] T054 [P] [US1] Create TechnicalAnalystAgent in src/agents/analysis/technical_analyst_agent.py (consumes ML forecasts, produces TechnicalReport)
- [X] T055 [P] [US1] Create FundamentalAnalystAgent in src/agents/analysis/fundamental_analyst_agent.py (consumes economic calendar, produces FundamentalReport)
- [X] T056 [P] [US1] Create SentimentAnalystAgent in src/agents/analysis/sentiment_analyst_agent.py (consumes COT data, produces SentimentReport)

### Decision Layer Agent - Trade Intent (for US1 flow)

- [X] T057 [US1] Create TradeDecisionAgent in src/agents/decision/trade_decision_agent.py (evaluates reports, produces TradeIntent with conviction 0.0-1.0)

### Decision Layer Agent - Position Sizing (US1 Core)

- [X] T058 [US1] Create PositionSizingAgent in src/agents/decision/position_sizing_agent.py with Kelly criterion calculation
- [X] T059 [US1] Implement regime adjustment logic in PositionSizingAgent (query get_fedformer_regime, apply multiplier 0.5-1.5)
- [X] T060 [US1] Implement conviction adjustment logic in PositionSizingAgent (scale by TradeIntent.conviction)
- [X] T061 [US1] Implement correlation adjustment logic in PositionSizingAgent (query open positions, calculate correlation penalty)
- [X] T062 [US1] Implement event risk adjustment logic in PositionSizingAgent (query get_economic_events, reduce size if high-impact events within timeframe)
- [X] T063 [US1] Implement portfolio allocation awareness in PositionSizingAgent (query allocated_capital from PortfolioAllocation, not total balance)

### Execution & Monitoring (for US1 flow)

- [X] T064 [US1] Create RiskOverseerAgent in src/agents/execution/risk_overseer_agent.py (validates PositionSize against hard limits, produces trade_validated or trade_rejected event)

### Integration & Testing

- [X] T065 [US1] Create unit tests for PositionSizingAgent Kelly logic in tests/unit/agents/test_position_sizing_agent.py
- [X] T066 [US1] Create integration test for position sizing decision pipeline in tests/integration/test_position_sizing_pipeline.py (validated via scripts/test_user_story_1.py)
- [X] T067 [US1] Create contract test for PositionSize schema validation in tests/contract/test_position_size_schema.py (guaranteed by Instructor library)
- [X] T068 [US1] Add decision logging for all PositionSizingAgent decisions to decision_log table
- [X] T069 [US1] Implement Prometheus metrics for position sizing (decision latency, Kelly fraction distribution, adjustment counts)

**Checkpoint**: Position sizing varies intelligently - verify via quickstart.md paper trading mode with different scenarios

---

## Phase 4: User Story 2 - Intelligent Stop-Loss Placement (Priority: P1)

**Goal**: Implement structure-based stop-loss placement using market support/resistance, ATR with adaptive multipliers, liquidity cluster avoidance, and probability analysis—eliminating fixed ATR multiples

**Independent Test**: Compare stop placements across market conditions and verify 70%+ positioned relative to market structure (not just ATR distance), with documented structure reasoning

### Decision Layer Agent - Stop Loss (US2 Core)

- [X] T070 [US2] Create StopLossAgent in src/agents/decision/stop_loss_agent.py with ATR-based baseline calculation
- [X] T071 [US2] Implement market structure analysis in StopLossAgent (call get_support_resistance, position stop beyond key levels)
- [X] T072 [US2] Implement volatility regime adjustment in StopLossAgent (query get_fedformer_regime, adjust ATR multiplier 1.0-3.0)
- [X] T073 [US2] Implement liquidity cluster detection in StopLossAgent (call detect_liquidity_clusters, avoid predictable stop zones)
- [X] T074 [US2] Implement probability analysis in StopLossAgent (use ML forecast uncertainty, estimate stop hit probability)
- [X] T075 [US2] Implement stop placement type classification (STRUCTURE, ATR, HYBRID) with rationale generation

### Integration & Testing

- [X] T076 [US2] Create unit tests for StopLossAgent structure logic in tests/unit/agents/test_stop_loss_agent.py
- [X] T077 [US2] Create integration test for stop-loss decision pipeline in tests/integration/test_stop_loss_pipeline.py
- [X] T078 [US2] Create contract test for StopLoss schema validation in tests/contract/test_stop_loss_schema.py
- [X] T079 [US2] Add decision logging for all StopLossAgent decisions to decision_log table
- [X] T080 [US2] Implement Prometheus metrics for stop-loss (structure-based percentage, ATR multiplier distribution, hit probability estimates)

**Checkpoint**: Stop-loss placements show structural intelligence - verify 70%+ structure-based via decision logs

---

## Phase 5: User Story 3 - Probabilistic Take-Profit Targeting (Priority: P1)

**Goal**: Implement ML-based take-profit targeting using forecast probability distributions, key resistance levels, and partial profit opportunities—eliminating fixed risk-reward ratios

**Independent Test**: Verify take-profit levels align with ML forecast percentiles (p50, p75, p90), respect market structure, and show 15%+ expected value improvement vs fixed 2:1 ratios

### Decision Layer Agent - Take Profit (US3 Core)

- [X] T081 [US3] Create TakeProfitAgent in src/agents/decision/take_profit_agent.py with ML forecast distribution analysis
- [X] T082 [US3] Implement quantile-based targeting in TakeProfitAgent (extract p50, p75, p90 from get_tft_prediction)
- [X] T083 [US3] Implement market structure integration in TakeProfitAgent (call get_support_resistance, position targets before resistance)
- [X] T084 [US3] Implement partial target logic in TakeProfitAgent (create up to 3 targets with size_pct distribution)
- [X] T085 [US3] Implement expected value calculation in TakeProfitAgent (sum of probability-weighted profits)
- [X] T086 [US3] Implement risk-reward ratio dynamic calculation and validation (ensure >= 1.5 preferred minimum)

### Integration & Testing

- [X] T087 [US3] Create unit tests for TakeProfitAgent quantile logic in tests/unit/agents/test_take_profit_agent.py
- [X] T088 [US3] Create integration test for take-profit decision pipeline in tests/integration/test_take_profit_pipeline.py (validated via scripts/test_user_story_3.py)
- [X] T089 [US3] Create contract test for TakeProfit schema validation in tests/contract/test_take_profit_schema.py (guaranteed by Instructor library)
- [X] T090 [US3] Add decision logging for all TakeProfitAgent decisions to decision_log table
- [X] T091 [US3] Implement Prometheus metrics for take-profit (expected value distribution, risk-reward ratios, partial target usage)

**Checkpoint**: Take-profit targets show probabilistic optimization - verify expected value improvement vs fixed 2:1 baseline

---

## Phase 6: User Story 4 + 4B + 4C - Adversarial Debate & Safety Gates (Priority: P1)

**Goal**: Implement bull/bear researcher agents that consume all analyst reports, build strongest cases for and against trades, produce stress-tested recommendations through adversarial debate, add risk tolerance debate for position sizing validation, and implement fund manager approval gate as final safety checkpoint

**Independent Test**: Verify every trade recommendation includes both bull thesis and bear counterarguments with 3+ evidence points each, traceable to analyst reports; verify risk debate produces documented perspectives from 3 debators; verify fund manager enforces hard portfolio limits (max 5% account risk, max 3 correlated positions, event risk veto)

### Debate Layer Agents (US4 Core)

- [X] T092 [P] [US4] Create BullResearcherAgent in src/agents/debate/bull_researcher_agent.py (builds strongest bull case from analyst reports)
- [X] T093 [P] [US4] Create BearResearcherAgent in src/agents/debate/bear_researcher_agent.py (builds strongest bear case with rebuttals to bull points)
- [X] T094 [US4] Implement debate coordination in MCP Server (orchestrate bull/bear exchange, produce DebateOutcome)
- [X] T095 [US4] Implement evidence tracing in debate agents (link arguments to specific analyst report claims)
- [X] T096 [US4] Implement risk warning extraction in debate layer (consolidate warnings from both perspectives)

### Integration with Decision Layer

- [X] T097 [US4] Update TradeDecisionAgent to consume DebateOutcome in addition to analyst reports
- [X] T098 [US4] Implement conflict resolution in TradeDecisionAgent (explicitly address bull vs bear contradictions in rationale)

### Integration & Testing

- [X] T099 [US4] Create unit tests for BullResearcherAgent and BearResearcherAgent in tests/unit/agents/test_debate_layer.py
- [X] T100 [US4] Create integration test for full debate pipeline in tests/integration/agents/test_bull_bear_debate_pipeline.py
- [X] T101 [US4] Create contract test for DebateOutcome schema validation in tests/contract/test_debate_outcome_schema.py (24 tests covering all debate schemas)
- [X] T102 [US4] Add decision logging for debate outcomes to decision_log table
- [X] T103 [US4] Implement Prometheus metrics for debate (bull/bear strength distribution, debate duration, risk warning counts)

### Risk Tolerance Debate (US4B - NEW)

- [ ] T122 [P] [US4B] Create RiskyDebatorAgent in src/agents/debate/risky_debator_agent.py (argues for higher position sizing when conditions warrant)
- [ ] T123 [P] [US4B] Create NeutralDebatorAgent in src/agents/debate/neutral_debator_agent.py (validates baseline Kelly calculation)
- [ ] T124 [P] [US4B] Create SafeDebatorAgent in src/agents/debate/safe_debator_agent.py (identifies factors warranting risk reduction)
- [X] T125 [US4B] Create RiskDebateTeam orchestration in src/agents/teams/risk_debate_team.py (simplified: single LLM generates all 3 perspectives)
- [X] T126 [US4B] Create RiskDebateOutcome Pydantic schema in src/agents/schemas/debate.py (documented perspectives + consensus decision + adjusted position size/risk level)
- [X] T127 [US4B] Update trading_pipeline.py to include risk debate AFTER decision agents, BEFORE fund manager
- [X] T128 [US4B] Create unit tests for risk debate agents in tests/unit/agents/test_risk_debate_team.py
- [X] T129 [US4B] Create integration test for risk debate pipeline in tests/integration/agents/test_risk_debate_pipeline.py
- [X] T130 [US4B] Add decision logging for risk debate outcomes to decision_log table
- [X] T131 [US4B] Implement Prometheus metrics for risk debate (perspective distribution, size adjustment frequency, debate duration)

### Fund Manager Approval Gate (US4C - NEW)

- [X] T132 [US4C] Create FundManagerAgent in src/agents/decision/fund_manager_agent.py (final approval gate with APPROVE/MODIFY/REJECT powers)
- [X] T133 [US4C] Create ApprovalDecision Pydantic schema in src/agents/schemas/approval.py (decision + rationale + modifications if applicable)
- [X] T134 [US4C] Implement portfolio-level limit checks in FundManagerAgent (max 5% account risk, max 3 correlated positions, event risk veto)
- [X] T135 [US4C] Update trading_pipeline.py to include fund manager approval AFTER risk debate, BEFORE execution
- [X] T136 [US4C] Create unit tests for FundManagerAgent in tests/unit/agents/test_fund_manager_agent.py
- [X] T137 [US4C] Create integration test for full approval pipeline in scripts/test_phase6_real_data.py (tests complete Phase 6 pipeline with REAL database data)
- [X] T138 [US4C] Add decision logging for approval decisions to decision_log table
- [X] T139 [US4C] Implement Prometheus metrics for approvals (approval/modify/reject distribution, modification types, portfolio risk tracking)

**Checkpoint**: Complete adversarial debate & safety gates - verify all trade recommendations include bull/bear arguments, risk tolerance debate, and fund manager approval with hard limit enforcement

---

## Phase 6.5: User Story 5.0 - Backtesting Infrastructure (Priority: P1 - BLOCKS Phase 7 & 8)

**Goal**: Build backtesting engine to simulate agent decisions against 13.5M historical candles in PostgreSQL, enabling performance validation and providing Gymnasium environment for RL training

**CRITICAL DEPENDENCY**: Phase 7 (RL Training) and Phase 8 (A/B Testing) CANNOT proceed without this phase

**Independent Test**: Run backtests on CrudeOIL 2023-2024 data showing accurate order fills, P&L tracking, and performance metrics matching industry standards

### Core Backtesting Engine (6 tasks)

- [ ] T140 [US5.0] Create BacktestEngine class in src/backtesting/engine.py
  - Load historical OHLCV from PostgreSQL market_data table (NO MOCK DATA)
  - Tick-by-tick or bar-by-bar price replay
  - Track simulated account state (balance, positions, orders)
  - Support symbol, date_range, timeframe, agent_config inputs

- [ ] T141 [US5.0] Implement order simulation with realistic fills in src/backtesting/order_simulator.py
  - Market orders: fill at next bar open + configurable slippage
  - Limit orders: fill if price touches limit level
  - Stop orders: fill if price breaches stop level
  - Spread simulation for realistic entry/exit costs
  - Optional partial fills for large positions

- [ ] T142 [US5.0] Implement position and P&L tracking in src/backtesting/portfolio.py
  - Open/close position logic
  - Realized and unrealized P&L calculation
  - Commission/swap cost deduction
  - Margin requirement tracking
  - Equity curve generation (timestamp, equity, drawdown)

- [ ] T143 [US5.0] Implement trade lifecycle management in src/backtesting/trade_manager.py
  - Entry signal → Order placed → Fill → Position open
  - Stop-loss/Take-profit monitoring each bar
  - Position close → P&L recorded → Trade logged
  - Support for partial closes (take-profit targets)

- [ ] T144 [US5.0] Implement multi-symbol portfolio backtesting in src/backtesting/portfolio_engine.py
  - Run backtests across multiple symbols
  - Track portfolio-level metrics
  - Correlation-aware position limits
  - Aggregate equity curve

- [ ] T145 [US5.0] Create BacktestConfig Pydantic schema in src/backtesting/schemas.py
  - Fields: symbols, date_range, initial_balance, commission, slippage, timeframe
  - Agent configuration (which agents, LLM provider)
  - Risk limits (max_position_size, max_drawdown_halt)

### Performance Metrics (4 tasks)

- [ ] T146 [P] [US5.0] Implement trade-level metrics in src/backtesting/metrics/trade_metrics.py
  - Win rate, loss rate
  - Average win size, average loss size
  - Profit factor (gross profit / gross loss)
  - Average trade duration
  - Maximum consecutive wins/losses

- [ ] T147 [P] [US5.0] Implement portfolio-level metrics in src/backtesting/metrics/portfolio_metrics.py
  - Total return, annualized return
  - Sharpe ratio (configurable risk-free rate)
  - Sortino ratio (downside deviation)
  - Calmar ratio (return / max drawdown)
  - Maximum drawdown (peak-to-trough)

- [ ] T148 [P] [US5.0] Implement risk metrics in src/backtesting/metrics/risk_metrics.py
  - Value at Risk (VaR) - 95th percentile
  - Expected shortfall (CVaR)
  - Daily/weekly volatility
  - Beta to benchmark (optional)

- [ ] T149 [US5.0] Create BacktestResult schema and report generation in src/backtesting/schemas.py
  - Pydantic model with all metrics
  - Equity curve data (timestamp, equity, drawdown)
  - Trade log (entry, exit, P&L, duration)
  - JSON export for analysis

### Agent Integration (4 tasks)

- [ ] T150 [US5.0] Create agent decision interface in src/backtesting/agent_adapter.py
  - Abstract interface: get_trade_decision(market_state) -> TradeIntent
  - Adapter for existing agents (PositionSizingAgent, StopLossAgent, etc.)
  - Batch decision mode for faster backtesting

- [ ] T151 [US5.0] Create MarketState representation in src/backtesting/schemas.py
  - Current OHLCV bar
  - Recent price history (lookback window)
  - Technical indicators (pre-computed or on-demand)
  - Account state (balance, open positions)
  - Passed to agents for decision-making

- [ ] T152 [US5.0] Implement full pipeline backtest mode in src/backtesting/pipeline_runner.py
  - Run complete trading pipeline per bar: Analysis → Debate → Decision → Risk Debate → Fund Manager → Execute
  - Configurable: skip debate for speed OR full pipeline for accuracy
  - Decision caching to avoid redundant LLM calls

- [ ] T153 [US5.0] Implement synthetic fast mode in src/backtesting/synthetic_mode.py
  - Rule-based heuristics mimicking agent behavior (NO LLM)
  - Target: 1000x faster than LLM mode
  - For hyperparameter search and quick iteration
  - Validate against LLM mode on sample data

### Gymnasium Environment for RL (4 tasks)

- [ ] T154 [US5.0] Create TradingGymEnv base class in src/backtesting/gym_env.py
  - Inherits gymnasium.Env
  - observation_space: market state + account state
  - action_space: position sizing, stop distance, take profit distance
  - step(): advance one bar, return (obs, reward, done, info)
  - reset(): start new episode from random date

- [ ] T155 [US5.0] Implement reward functions in src/backtesting/rewards.py
  - Sharpe-based reward (risk-adjusted returns)
  - P&L reward with drawdown penalty
  - Transaction cost penalty
  - Configurable reward shaping

- [ ] T156 [US5.0] Implement episode configuration in src/backtesting/gym_env.py
  - Episode length (bars or calendar days)
  - Random start date sampling
  - Train/validation/test date splits
  - Walk-forward episode generation

- [ ] T157 [US5.0] Implement vectorized environment in src/backtesting/vec_env.py
  - Multiple environments running in parallel
  - Compatible with Stable-Baselines3
  - GPU acceleration support (optional)

### Testing & Validation (4 tasks)

- [ ] T158 [US5.0] Create unit tests for BacktestEngine in tests/unit/backtesting/test_engine.py
  - Order fill logic
  - P&L calculation accuracy
  - Edge cases (gaps, limit up/down)

- [ ] T159 [US5.0] Create integration tests with real data in tests/integration/backtesting/test_real_data_backtest.py
  - Run backtest on Gold 2024 data from PostgreSQL
  - Verify metrics match manual calculation
  - Test full agent pipeline mode

- [ ] T160 [US5.0] Create benchmark tests in tests/performance/test_backtest_performance.py
  - Performance: bars/second throughput
  - Target: 10,000+ bars/second in synthetic mode
  - Target: 100+ bars/second in LLM mode (with caching)

- [ ] T161 [US5.0] Create validation tests in tests/integration/backtesting/test_validation.py
  - Simple strategy (MA crossover) with known outcome
  - Verify BacktestEngine reproduces expected trades and metrics

**Acceptance Criteria**:
- BacktestEngine processes 13.5M candles without memory issues
- Sharpe ratio calculation matches industry standard (annualized)
- Gymnasium environment compatible with Stable-Baselines3 PPO/SAC
- Full pipeline backtest completes 1 year of 4H data in <10 minutes
- Synthetic mode completes 1 year of 4H data in <10 seconds

**Checkpoint**: Complete backtesting infrastructure - verify backtest runs on real PostgreSQL data, produces accurate metrics, and provides Gymnasium environment for RL training

---

## Phase 7: User Story 5 - Reinforcement Learning Training (Priority: P2)

**DEPENDENCY**: Requires Phase 6.5 (Backtesting Infrastructure) completion

**Goal**: Implement offline RL training for decision agents (position sizing, stop-loss, take-profit, trade decision) with walk-forward validation, enabling continuous improvement from backtesting outcomes

**Independent Test**: Run walk-forward backtests showing RL-trained agents outperform baseline strategies with statistical significance (p < 0.05, Sharpe improvement > 0.3)

### RL Infrastructure (US5 Core)

- [ ] T104 [US5] Create TradingEnvironment Gymnasium environment in src/ml/rl/environments/trading_env.py (backtesting replay with point-in-time data)
- [ ] T105 [US5] Create PositionSizingEnvironment in src/ml/rl/environments/position_sizing_env.py (specialized for position sizing agent)
- [ ] T106 [US5] Create StopLossEnvironment in src/ml/rl/environments/stop_loss_env.py (specialized for stop-loss agent)
- [ ] T107 [US5] Create TakeProfitEnvironment in src/ml/rl/environments/take_profit_env.py (specialized for take-profit agent)

### Reward Functions

- [ ] T108 [P] [US5] Implement PositionSizingReward in src/ml/rl/rewards/reward_functions.py (Sharpe contribution - drawdown penalty - transaction costs)
- [ ] T109 [P] [US5] Implement StopLossReward in src/ml/rl/rewards/reward_functions.py (minimize unnecessary stop-outs + protect capital)
- [ ] T110 [P] [US5] Implement TakeProfitReward in src/ml/rl/rewards/reward_functions.py (maximize expected value captured)
- [ ] T111 [P] [US5] Implement TradeDecisionReward in src/ml/rl/rewards/reward_functions.py (realized PnL × direction accuracy)

### RL Algorithms

- [ ] T112 [P] [US5] Implement PPO trainer in src/ml/rl/agents/ppo_trainer.py (for discrete actions like trade direction)
- [ ] T113 [P] [US5] Implement SAC trainer in src/ml/rl/agents/sac_trainer.py (for continuous actions like position size)
- [ ] T114 [US5] Integrate Stable-Baselines3 with MLflow tracking in trainers

### Walk-Forward Validation

- [ ] T115 [US5] Implement walk-forward validation in src/ml/rl/validation/walk_forward.py (rolling windows: 252 train, 63 test, 21 step)
- [ ] T116 [US5] Implement overfitting detection in walk-forward validator (compare train vs OOS Sharpe, alert if degradation > 25%)
- [ ] T117 [US5] Implement statistical significance testing in validator (p-value < 0.05 for performance gains)

### Training Service Integration

- [ ] T118 [US5] Complete RLTrainingService implementation in src/services/rl_training_service.py (orchestrate training runs, save checkpoints to MLflow)
- [ ] T119 [US5] Complete run_rl_training.py script implementation in scripts/agents/run_rl_training.py
- [ ] T120 [US5] Create deploy_rl_model.py script in scripts/agents/deploy_rl_model.py (promote models to Staging/Production)
- [ ] T121 [US5] Create evaluate_rl_training.py script in scripts/agents/evaluate_rl_training.py (analyze training metrics)

### Agent Integration

- [ ] T122 [US5] Update PositionSizingAgent to load and use RL model from MLflow when rl_enabled=True
- [ ] T123 [US5] Update StopLossAgent to load and use RL model from MLflow when rl_enabled=True
- [ ] T124 [US5] Update TakeProfitAgent to load and use RL model from MLflow when rl_enabled=True
- [ ] T125 [US5] Update TradeDecisionAgent to load and use RL model from MLflow when rl_enabled=True

### Integration & Testing

- [ ] T126 [US5] Create unit tests for RL environments in tests/unit/rl/test_trading_env.py
- [ ] T127 [US5] Create unit tests for reward functions in tests/unit/rl/test_reward_functions.py
- [ ] T128 [US5] Create integration test for RL training with deterministic seeds in tests/integration/test_rl_training.py
- [ ] T129 [US5] Create walk-forward validation test in tests/integration/test_walk_forward_validation.py
- [ ] T130 [US5] Add RL training run logging to rl_training_runs table with MLflow metadata

**Checkpoint**: RL training produces measurably improved agents - verify via walk-forward validation showing Sharpe > 0.3 improvement

---

## Phase 8: User Story 6 - Multi-Model A/B Testing (Priority: P3)

**Goal**: Implement A/B testing framework comparing different LLM providers (proprietary vs local models) across same trading scenarios, tracking performance and cost metrics to optimize cost-effectiveness

**Independent Test**: Run parallel paper trading sessions with different model configs (GPT-4o vs Qwen3+DeepSeek-R1) and verify system tracks performance, costs, and return-per-dollar-spent

### A/B Testing Infrastructure (US6 Core)

- [ ] T131 [US6] Create ABTestService in src/services/ab_test_service.py (manage experiments, traffic allocation)
- [ ] T132 [US6] Implement traffic routing in AgentOrchestrationService (select agent config based on traffic_percentage)
- [ ] T133 [US6] Implement cost tracking in LLMClient (track API calls and costs per model provider)
- [ ] T134 [US6] Implement statistical testing in ABTestService (t-test for returns, p-value calculation)

### Model Configuration Management

- [ ] T135 [US6] Create create_ab_test.py script in scripts/agents/create_ab_test.py
- [ ] T136 [US6] Create view_ab_test_results.py script in scripts/agents/view_ab_test_results.py
- [ ] T137 [US6] Create promote_ab_test_winner.py script in scripts/agents/promote_ab_test_winner.py

### Integration & Testing

- [ ] T138 [US6] Create unit tests for A/B testing logic in tests/unit/services/test_ab_test_service.py
- [ ] T139 [US6] Create integration test for A/B testing in paper mode in tests/integration/test_ab_testing.py
- [ ] T140 [US6] Create contract test for ModelConfiguration schema validation in tests/contract/test_model_configuration_schema.py
- [ ] T141 [US6] Add A/B test tracking to model_configurations table
- [ ] T142 [US6] Implement Prometheus metrics for A/B testing (cost per variant, return per variant, cost-effectiveness)

**Checkpoint**: A/B testing framework operational - verify ability to compare model configs and calculate return-per-dollar-spent

---

## Phase 9: Execution & Monitoring Integration (Cross-Cutting)

**Purpose**: Complete execution layer and monitoring for all user stories

### Execution Layer Agents

- [ ] T143 [P] Create ExecutionAgent in src/agents/execution/execution_agent.py (order placement via MT4/ZMQ bridge from Feature 001)
- [ ] T144 [P] Create PositionMonitorAgent in src/agents/execution/position_monitor_agent.py (trailing stops, target adjustments)

### MT4 Integration

- [ ] T145 Integrate ExecutionAgent with existing MT4/ZMQ bridge from Feature 001
- [ ] T146 Implement order lifecycle management in ExecutionAgent (submitted → filled → updated → closed)
- [ ] T147 Implement slippage tracking in ExecutionAgent
- [ ] T148 Implement partial fill handling in ExecutionAgent

### Portfolio Allocation

- [ ] T149 Create PortfolioAllocatorAgent skeleton in src/agents/coordination/portfolio_allocator_agent.py (optional for dynamic allocation)
- [ ] T150 Create StrategyTeam management in src/agents/coordination/strategy_team.py (agent team assignments per instrument)
- [ ] T151 Implement static portfolio allocation from config in AgentOrchestrationService
- [ ] T152 Implement multi-instrument support (Gold + Crude Oil strategy teams)

### Monitoring & Observability

- [ ] T153 [P] Create agent health check endpoint in API
- [ ] T154 [P] Create decision log query endpoints in API
- [ ] T155 [P] Create performance analytics queries in DecisionLogRepository (agent success rates, latency, costs)
- [ ] T156 [P] Create Grafana dashboard for agent system (config/monitoring/grafana/agent_system_dashboard.json)
- [ ] T157 [P] Create Prometheus alerts for agent system (high latency, circuit breaker open, low cache hit rate)

### Scripts & Utilities

- [ ] T158 [P] Complete monitor_agents.py script implementation
- [ ] T159 [P] Create evaluate_agent_performance.py script in scripts/agents/
- [ ] T160 [P] Create check_agent_health.sh script in scripts/monitoring/

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements affecting multiple user stories

### Documentation

- [ ] T161 [P] Update CLAUDE.md with agent system usage instructions
- [ ] T162 [P] Create agent system API documentation
- [ ] T163 [P] Update quickstart.md with production deployment checklist

### Testing & Validation

- [ ] T164 [P] Create E2E test for full decision pipeline (analysis → debate → decision → execution → audit) in tests/e2e/test_trading_workflow.py
- [ ] T165 [P] Create paper trading validation script for 100+ trades
- [ ] T166 [P] Run quickstart.md validation (verify all commands work)

### Security & Performance

- [ ] T167 Implement input validation for all MCP tool responses
- [ ] T168 Implement rate limiting for MCP tool calls (prevent abuse)
- [ ] T169 Performance optimization: batch decision log inserts (reduce DB writes)
- [ ] T170 Security audit: verify no hardcoded secrets, all credentials in environment variables

### Configuration & Deployment

- [ ] T171 [P] Create production-ready agents.yaml example
- [ ] T172 [P] Create Docker health checks for all agent services
- [ ] T173 [P] Create Kubernetes manifests for agent system (optional)
- [ ] T174 Update docker-compose.yml with all agent services

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - **BLOCKS all user stories**
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - US1 (Position Sizing): Can start after Foundational - No story dependencies
  - US2 (Stop-Loss): Can start after Foundational - No story dependencies
  - US3 (Take-Profit): Can start after Foundational - No story dependencies
  - US4 (Debate Layer): Can start after Foundational - Integrates with US1 TradeDecisionAgent but independently testable
  - US5 (RL Training): Requires US1, US2, US3 agents implemented (needs agents to train)
  - US6 (A/B Testing): Can start after Foundational - No story dependencies
- **Execution Integration (Phase 9)**: Depends on at least US1-US3 completion
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: ✅ Can start after Foundational - No dependencies
- **User Story 2 (P1)**: ✅ Can start after Foundational - No dependencies
- **User Story 3 (P1)**: ✅ Can start after Foundational - No dependencies
- **User Story 4 (P2)**: ✅ Can start after Foundational - Integrates with TradeDecisionAgent from US1
- **User Story 5 (P2)**: ⚠️ Requires US1, US2, US3 agents implemented first (needs agents to train)
- **User Story 6 (P3)**: ✅ Can start after Foundational - No dependencies

### Within Each User Story

1. Agents/Models before services
2. Services before endpoints
3. Core implementation before integration
4. Tests can run in parallel with implementation (TDD approach if desired)
5. Story complete before moving to next priority

### Parallel Opportunities

**Setup Phase**:
- T002, T003, T004, T005, T006 can all run in parallel

**Foundational Phase** (within Phase 2):
- All SQLAlchemy models (T008-T014) can run in parallel
- All Pydantic schemas (T017-T021) can run in parallel
- All repositories (T022-T028) can run in parallel after models complete
- All MCP tools (T035-T043) can run in parallel
- All API routes (T049-T050) can run in parallel

**User Stories** (after Foundational):
- US1, US2, US3, US6 can start in parallel (independent)
- US4 can start in parallel but integrates with US1
- US5 must wait for US1, US2, US3 completion

**Within US1**:
- T054, T055, T056 (analyst agents) can run in parallel
- T065, T066, T067 (tests) can run in parallel

**Within US2**:
- T076, T077, T078 (tests) can run in parallel

**Within US3**:
- T087, T088, T089 (tests) can run in parallel

**Within US4**:
- T092, T093 (bull/bear researchers) can run in parallel
- T099, T100, T101 (tests) can run in parallel

**Within US5**:
- T104, T105, T106, T107 (environments) can run in parallel
- T108, T109, T110, T111 (reward functions) can run in parallel
- T112, T113 (RL trainers) can run in parallel
- T126, T127 (tests) can run in parallel

**Within US6**:
- T138, T139, T140 (tests) can run in parallel

**Execution Phase**:
- T143, T144 (agents) can run in parallel
- T153, T154, T155, T156, T157 (monitoring) can run in parallel
- T158, T159, T160 (scripts) can run in parallel

**Polish Phase**:
- T161, T162, T163 (documentation) can run in parallel
- T164, T165, T166 (testing) can run in parallel
- T171, T172, T173 (deployment) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all analyst agents for User Story 1 together:
Task T054: "TechnicalAnalystAgent in src/agents/analysis/technical_analyst_agent.py"
Task T055: "FundamentalAnalystAgent in src/agents/analysis/fundamental_analyst_agent.py"
Task T056: "SentimentAnalystAgent in src/agents/analysis/sentiment_analyst_agent.py"

# Launch all tests for User Story 1 together:
Task T065: "Unit tests for PositionSizingAgent in tests/unit/agents/test_position_sizing_agent.py"
Task T066: "Integration test in tests/integration/test_position_sizing_pipeline.py"
Task T067: "Contract test in tests/contract/test_position_size_schema.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (**CRITICAL** - blocks all stories)
3. Complete Phase 3: User Story 1 (Position Sizing)
4. Complete Phase 4: User Story 2 (Stop-Loss)
5. Complete Phase 5: User Story 3 (Take-Profit)
6. Complete Phase 9: Execution Integration (minimal - just ExecutionAgent + MT4)
7. **STOP and VALIDATE**: Test US1-3 independently in paper trading mode
8. Deploy/demo if ready

**Rationale**: US1-3 (P1 priority) form the core intelligent risk management system. These three stories together enable adaptive position sizing, intelligent stop placement, and probabilistic targeting - the key differentiators from hardcoded approaches.

### Incremental Delivery

1. **Foundation** (Phases 1-2) → Infrastructure ready
2. **MVP** (Phases 3-5 + minimal Phase 9) → Core decision agents operational
   - Deploy in paper trading mode
   - Validate position sizing variance (SC-001)
   - Validate stop-loss structure intelligence (SC-002)
   - Validate take-profit probabilistic optimization (SC-003)
3. **Enhanced Decision Making** (Phase 6: US4) → Debate layer adds adversarial analysis
   - Deploy updated system in paper trading
   - Validate balanced perspectives (SC-004)
4. **Continuous Improvement** (Phase 7: US5) → RL training enables learning
   - Train agents offline on historical data
   - Validate out-of-sample performance (SC-005, SC-006)
   - Deploy RL models to staging, then production
5. **Cost Optimization** (Phase 8: US6) → A/B testing enables model selection
   - Run parallel experiments with different LLM configs
   - Validate cost-effectiveness tracking (SC-007)
   - Promote winning configuration
6. **Production Ready** (Phase 10) → Polish and harden
   - Complete execution integration
   - E2E testing
   - Production deployment

Each increment adds value without breaking previous functionality.

### Parallel Team Strategy

With multiple developers after Foundational phase completes:

- **Developer A**: User Story 1 (Position Sizing) → US5 RL Training for Position Sizing
- **Developer B**: User Story 2 (Stop-Loss) → US5 RL Training for Stop-Loss
- **Developer C**: User Story 3 (Take-Profit) → US5 RL Training for Take-Profit
- **Developer D**: User Story 4 (Debate Layer) → US6 A/B Testing
- **All**: Converge on Phase 9 (Execution Integration) and Phase 10 (Polish)

Stories complete independently, then integrate cleanly.

---

## Task Summary

**Total Tasks**: 174

**By Phase**:
- Phase 1 (Setup): 6 tasks
- Phase 2 (Foundational): 47 tasks ⚠️ BLOCKING
- Phase 3 (US1 - Position Sizing): 16 tasks
- Phase 4 (US2 - Stop-Loss): 11 tasks
- Phase 5 (US3 - Take-Profit): 11 tasks
- Phase 6 (US4 - Debate Layer): 12 tasks
- Phase 7 (US5 - RL Training): 30 tasks
- Phase 8 (US6 - A/B Testing): 12 tasks
- Phase 9 (Execution Integration): 18 tasks
- Phase 10 (Polish): 11 tasks

**By Priority**:
- P1 (MVP): US1-US3 = 38 tasks (after Foundational)
- P2 (Enhanced): US4-US5 = 42 tasks
- P3 (Optimization): US6 = 12 tasks
- Cross-Cutting: Phase 9-10 = 29 tasks

**Parallel Tasks**: 87 tasks marked [P] (50% can run in parallel with proper staffing)

**Independent Test Criteria Met**: Each user story (US1-US6) has clear independent test criteria in phase descriptions

**MVP Scope**: Phases 1-5 + minimal Phase 9 = ~115 tasks for core intelligent risk management system

---

## Notes

- [P] tasks = different files, no dependencies, can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story independently completable and testable
- Verify tests pass before marking story complete
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Phase 2 (Foundational) is BLOCKING - no user story work without it
- RL training (US5) requires agents from US1-US3 to be implemented first
- Paper trading mode validation mandatory before live trading (per constitution Principle V)
- Decision logging mandatory for all agents (audit trail requirement)
