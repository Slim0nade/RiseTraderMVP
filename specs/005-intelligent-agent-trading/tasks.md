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

- [ ] T001 Create agent system directory structure (src/agents/, src/ml/rl/, config/agents/)
- [ ] T002 [P] Install agent system dependencies (litellm, stable-baselines3, gymnasium, mlflow)
- [ ] T003 [P] Configure pre-commit hooks for Pydantic schema validation
- [ ] T004 [P] Create base configuration templates (config/agents/agents.yaml.template, config/agents/rl_training_config.yaml.template, config/agents/portfolio_allocation.yaml.template)
- [ ] T005 [P] Setup MLflow tracking server configuration in docker-compose.yml
- [ ] T006 [P] Create MCP server Docker service definition in docker-compose.yml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database & Data Models

- [ ] T007 Create Alembic migration for agent system tables (agents, decision_log, rl_training_runs, model_configurations, portfolio_allocations, strategy_teams, mcp_tools)
- [ ] T008 [P] Create Agent SQLAlchemy model in src/database/models/agent.py
- [ ] T009 [P] Create DecisionLog SQLAlchemy model with TimescaleDB hypertable in src/database/models/decision_log.py
- [ ] T010 [P] Create RLTrainingRun SQLAlchemy model in src/database/models/rl_training_run.py
- [ ] T011 [P] Create ModelConfiguration SQLAlchemy model in src/database/models/model_configuration.py
- [ ] T012 [P] Create PortfolioAllocation SQLAlchemy model in src/database/models/portfolio_allocation.py
- [ ] T013 [P] Create StrategyTeam SQLAlchemy model in src/database/models/strategy_team.py
- [ ] T014 [P] Create MCPTool SQLAlchemy model in src/database/models/mcp_tool.py
- [ ] T015 Apply Alembic migration and create TimescaleDB hypertable for decision_log
- [ ] T016 [P] Create decision_log TimescaleDB indexes and retention policy (90 days)

### Pydantic Schemas (Agent Communication)

- [ ] T017 [P] Create base event schema in src/agents/schemas/events.py
- [ ] T018 [P] Create decision schemas (TradeIntent, PositionSize, StopLoss, TakeProfit) in src/agents/schemas/decisions.py
- [ ] T019 [P] Create analyst report schemas (TechnicalReport, FundamentalReport, SentimentReport) in src/agents/schemas/reports.py
- [ ] T020 [P] Create debate schema (DebateOutcome) in src/agents/schemas/reports.py
- [ ] T021 [P] Create agent config schema (AgentConfig, AgentState) in src/agents/base/agent_config.py

### Repositories

- [ ] T022 [P] Create AgentRepository in src/database/repositories/agent_repository.py
- [ ] T023 [P] Create DecisionLogRepository with TimescaleDB queries in src/database/repositories/decision_log_repository.py
- [ ] T024 [P] Create RLTrainingRunRepository in src/database/repositories/rl_training_run_repository.py
- [ ] T025 [P] Create ModelConfigurationRepository in src/database/repositories/model_configuration_repository.py
- [ ] T026 [P] Create PortfolioAllocationRepository in src/database/repositories/portfolio_allocation_repository.py
- [ ] T027 [P] Create StrategyTeamRepository in src/database/repositories/strategy_team_repository.py
- [ ] T028 [P] Create MCPToolRepository in src/database/repositories/mcp_tool_repository.py

### Core Agent Infrastructure

- [ ] T029 Create BaseAgent abstract class in src/agents/base/base_agent.py (event handling, logging, health checks)
- [ ] T030 Create LLMClient wrapper for LiteLLM in src/agents/tools/llm_client.py (quick-think vs deep-think routing)
- [ ] T031 Create MCPClient for tool invocations in src/agents/tools/mcp_client.py (circuit breaker, caching, retry logic)
- [ ] T032 Create MCP Server core in src/agents/coordination/mcp_server.py (event routing, Redis pub/sub, shared context)
- [ ] T033 Implement event bus with idempotency in src/agents/coordination/event_bus.py (deduplication, ordering, retry)
- [ ] T034 [P] Create Prometheus metrics recorder in src/monitoring/agent_metrics.py

### MCP Tools Implementation (FR-019)

- [ ] T035 [P] Implement get_tcn_forecast MCP tool in src/ml/tools/forecasting_tools.py
- [ ] T036 [P] Implement get_tft_prediction MCP tool in src/ml/tools/forecasting_tools.py
- [ ] T037 [P] Implement get_fedformer_regime MCP tool in src/ml/tools/forecasting_tools.py
- [ ] T038 [P] Implement calculate_kelly MCP tool in src/ml/tools/calculation_tools.py
- [ ] T039 [P] Implement calculate_atr MCP tool in src/ml/tools/calculation_tools.py
- [ ] T040 [P] Implement get_support_resistance MCP tool in src/ml/tools/market_structure_tools.py
- [ ] T041 [P] Implement detect_liquidity_clusters MCP tool in src/ml/tools/market_structure_tools.py
- [ ] T042 [P] Implement get_economic_events MCP tool in src/ml/tools/data_retrieval_tools.py
- [ ] T043 [P] Implement get_cot_data MCP tool in src/ml/tools/data_retrieval_tools.py
- [ ] T044 Register all MCP tools in mcp_tools table with schemas from contracts/mcp-tools.yaml
- [ ] T045 Implement MCP tool circuit breaker and caching in MCPClient

### Services

- [ ] T046 Create AgentOrchestrationService in src/services/agent_orchestration_service.py (start/stop agents, health monitoring)
- [ ] T047 Create MCPToolService in src/services/mcp_tool_service.py (tool registration, invocation)
- [ ] T048 Create RLTrainingService skeleton in src/services/rl_training_service.py (offline RL orchestration)

### API Endpoints

- [ ] T049 [P] Create agent management API routes in src/api/routes/agents.py (health, status, configuration)
- [ ] T050 [P] Create RL training API routes in src/api/routes/rl_training.py (trigger training, view metrics)

### Scripts

- [ ] T051 [P] Create start_agent_system.py script in scripts/agents/
- [ ] T052 [P] Create monitor_agents.py script in scripts/agents/
- [ ] T053 [P] Create run_rl_training.py skeleton in scripts/agents/

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Adaptive Position Sizing (Priority: P1) 🎯 MVP

**Goal**: Implement intelligent position sizing that varies based on Kelly criterion, market regime, trade conviction, portfolio correlation, and event risk—eliminating fixed percentage approaches

**Independent Test**: Execute trades across different scenarios (high volatility + drawdown, low volatility + favorable, high correlation exposure) and verify position sizes vary by 50%+ with documented reasoning

### Analysis Layer Agents (for US1 context)

- [ ] T054 [P] [US1] Create TechnicalAnalystAgent in src/agents/analysis/technical_analyst_agent.py (consumes ML forecasts, produces TechnicalReport)
- [ ] T055 [P] [US1] Create FundamentalAnalystAgent in src/agents/analysis/fundamental_analyst_agent.py (consumes economic calendar, produces FundamentalReport)
- [ ] T056 [P] [US1] Create SentimentAnalystAgent in src/agents/analysis/sentiment_analyst_agent.py (consumes COT data, produces SentimentReport)

### Decision Layer Agent - Trade Intent (for US1 flow)

- [ ] T057 [US1] Create TradeDecisionAgent in src/agents/decision/trade_decision_agent.py (evaluates reports, produces TradeIntent with conviction 0.0-1.0)

### Decision Layer Agent - Position Sizing (US1 Core)

- [ ] T058 [US1] Create PositionSizingAgent in src/agents/decision/position_sizing_agent.py with Kelly criterion calculation
- [ ] T059 [US1] Implement regime adjustment logic in PositionSizingAgent (query get_fedformer_regime, apply multiplier 0.5-1.5)
- [ ] T060 [US1] Implement conviction adjustment logic in PositionSizingAgent (scale by TradeIntent.conviction)
- [ ] T061 [US1] Implement correlation adjustment logic in PositionSizingAgent (query open positions, calculate correlation penalty)
- [ ] T062 [US1] Implement event risk adjustment logic in PositionSizingAgent (query get_economic_events, reduce size if high-impact events within timeframe)
- [ ] T063 [US1] Implement portfolio allocation awareness in PositionSizingAgent (query allocated_capital from PortfolioAllocation, not total balance)

### Execution & Monitoring (for US1 flow)

- [ ] T064 [US1] Create RiskOverseerAgent in src/agents/execution/risk_overseer_agent.py (validates PositionSize against hard limits, produces trade_validated or trade_rejected event)

### Integration & Testing

- [ ] T065 [US1] Create unit tests for PositionSizingAgent Kelly logic in tests/unit/agents/test_position_sizing_agent.py
- [ ] T066 [US1] Create integration test for position sizing decision pipeline in tests/integration/test_position_sizing_pipeline.py
- [ ] T067 [US1] Create contract test for PositionSize schema validation in tests/contract/test_position_size_schema.py
- [ ] T068 [US1] Add decision logging for all PositionSizingAgent decisions to decision_log table
- [ ] T069 [US1] Implement Prometheus metrics for position sizing (decision latency, Kelly fraction distribution, adjustment counts)

**Checkpoint**: Position sizing varies intelligently - verify via quickstart.md paper trading mode with different scenarios

---

## Phase 4: User Story 2 - Intelligent Stop-Loss Placement (Priority: P1)

**Goal**: Implement structure-based stop-loss placement using market support/resistance, ATR with adaptive multipliers, liquidity cluster avoidance, and probability analysis—eliminating fixed ATR multiples

**Independent Test**: Compare stop placements across market conditions and verify 70%+ positioned relative to market structure (not just ATR distance), with documented structure reasoning

### Decision Layer Agent - Stop Loss (US2 Core)

- [ ] T070 [US2] Create StopLossAgent in src/agents/decision/stop_loss_agent.py with ATR-based baseline calculation
- [ ] T071 [US2] Implement market structure analysis in StopLossAgent (call get_support_resistance, position stop beyond key levels)
- [ ] T072 [US2] Implement volatility regime adjustment in StopLossAgent (query get_fedformer_regime, adjust ATR multiplier 1.0-3.0)
- [ ] T073 [US2] Implement liquidity cluster detection in StopLossAgent (call detect_liquidity_clusters, avoid predictable stop zones)
- [ ] T074 [US2] Implement probability analysis in StopLossAgent (use ML forecast uncertainty, estimate stop hit probability)
- [ ] T075 [US2] Implement stop placement type classification (STRUCTURE, ATR, HYBRID) with rationale generation

### Integration & Testing

- [ ] T076 [US2] Create unit tests for StopLossAgent structure logic in tests/unit/agents/test_stop_loss_agent.py
- [ ] T077 [US2] Create integration test for stop-loss decision pipeline in tests/integration/test_stop_loss_pipeline.py
- [ ] T078 [US2] Create contract test for StopLoss schema validation in tests/contract/test_stop_loss_schema.py
- [ ] T079 [US2] Add decision logging for all StopLossAgent decisions to decision_log table
- [ ] T080 [US2] Implement Prometheus metrics for stop-loss (structure-based percentage, ATR multiplier distribution, hit probability estimates)

**Checkpoint**: Stop-loss placements show structural intelligence - verify 70%+ structure-based via decision logs

---

## Phase 5: User Story 3 - Probabilistic Take-Profit Targeting (Priority: P1)

**Goal**: Implement ML-based take-profit targeting using forecast probability distributions, key resistance levels, and partial profit opportunities—eliminating fixed risk-reward ratios

**Independent Test**: Verify take-profit levels align with ML forecast percentiles (p50, p75, p90), respect market structure, and show 15%+ expected value improvement vs fixed 2:1 ratios

### Decision Layer Agent - Take Profit (US3 Core)

- [ ] T081 [US3] Create TakeProfitAgent in src/agents/decision/take_profit_agent.py with ML forecast distribution analysis
- [ ] T082 [US3] Implement quantile-based targeting in TakeProfitAgent (extract p50, p75, p90 from get_tft_prediction)
- [ ] T083 [US3] Implement market structure integration in TakeProfitAgent (call get_support_resistance, position targets before resistance)
- [ ] T084 [US3] Implement partial target logic in TakeProfitAgent (create up to 3 targets with size_pct distribution)
- [ ] T085 [US3] Implement expected value calculation in TakeProfitAgent (sum of probability-weighted profits)
- [ ] T086 [US3] Implement risk-reward ratio dynamic calculation and validation (ensure >= 1.5 preferred minimum)

### Integration & Testing

- [ ] T087 [US3] Create unit tests for TakeProfitAgent quantile logic in tests/unit/agents/test_take_profit_agent.py
- [ ] T088 [US3] Create integration test for take-profit decision pipeline in tests/integration/test_take_profit_pipeline.py
- [ ] T089 [US3] Create contract test for TakeProfit schema validation in tests/contract/test_take_profit_schema.py
- [ ] T090 [US3] Add decision logging for all TakeProfitAgent decisions to decision_log table
- [ ] T091 [US3] Implement Prometheus metrics for take-profit (expected value distribution, risk-reward ratios, partial target usage)

**Checkpoint**: Take-profit targets show probabilistic optimization - verify expected value improvement vs fixed 2:1 baseline

---

## Phase 6: User Story 4 - Adversarial Debate Layer (Priority: P2)

**Goal**: Implement bull/bear researcher agents that consume all analyst reports, build strongest cases for and against trades, and produce stress-tested recommendations through adversarial debate

**Independent Test**: Verify every trade recommendation includes both bull thesis and bear counterarguments with 3+ evidence points each, traceable to analyst reports

### Debate Layer Agents (US4 Core)

- [ ] T092 [P] [US4] Create BullResearcherAgent in src/agents/debate/bull_researcher_agent.py (builds strongest bull case from analyst reports)
- [ ] T093 [P] [US4] Create BearResearcherAgent in src/agents/debate/bear_researcher_agent.py (builds strongest bear case with rebuttals to bull points)
- [ ] T094 [US4] Implement debate coordination in MCP Server (orchestrate bull/bear exchange, produce DebateOutcome)
- [ ] T095 [US4] Implement evidence tracing in debate agents (link arguments to specific analyst report claims)
- [ ] T096 [US4] Implement risk warning extraction in debate layer (consolidate warnings from both perspectives)

### Integration with Decision Layer

- [ ] T097 [US4] Update TradeDecisionAgent to consume DebateOutcome in addition to analyst reports
- [ ] T098 [US4] Implement conflict resolution in TradeDecisionAgent (explicitly address bull vs bear contradictions in rationale)

### Integration & Testing

- [ ] T099 [US4] Create unit tests for BullResearcherAgent and BearResearcherAgent in tests/unit/agents/test_debate_agents.py
- [ ] T100 [US4] Create integration test for full debate pipeline in tests/integration/test_debate_pipeline.py
- [ ] T101 [US4] Create contract test for DebateOutcome schema validation in tests/contract/test_debate_outcome_schema.py
- [ ] T102 [US4] Add decision logging for debate outcomes to decision_log table
- [ ] T103 [US4] Implement Prometheus metrics for debate (bull/bear strength distribution, debate duration, risk warning counts)

**Checkpoint**: Debate layer produces balanced perspectives - verify all trade recommendations include both bull and bear arguments

---

## Phase 7: User Story 5 - Reinforcement Learning Training (Priority: P2)

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
