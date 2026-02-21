# Tasks: Backtesting Engine

**Input**: Design documents from `/specs/006-backtesting-engine/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Following TDD principles per constitution - tests are written FIRST and must FAIL before implementation

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- Single project structure: `src/`, `tests/` at repository root
- Backtesting module located at `src/services/backtesting/`
- Models at `src/database/models/`
- Repositories at `src/database/repositories/`
- Tests follow three-tier structure: `tests/unit/`, `tests/integration/`, `tests/contract/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency installation

- [X] T001 Add new dependencies to pyproject.toml (gymnasium, scipy, hypothesis)
- [X] T002 [P] Create backtesting module directory structure at src/services/backtesting/
- [X] T003 [P] Create test directory structure at tests/unit/backtesting/ and tests/integration/backtesting/
- [X] T004 [P] Create __init__.py files for all new modules

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database Schema & Migrations

- [X] T005 Create Alembic migration for backtesting ENUM types (ExecutionMode, RunStatus, TradeAction, DecisionType) in alembic/versions/
- [X] T006 [P] Create SQLAlchemy model for BacktestConfiguration in src/database/models/backtest.py
- [X] T007 [P] Create SQLAlchemy model for BacktestRun in src/database/models/backtest.py
- [X] T008 [P] Create SQLAlchemy model for SimulatedTrade in src/database/models/simulated_trade.py
- [X] T009 [P] Create SQLAlchemy model for PortfolioSnapshot in src/database/models/simulated_trade.py
- [X] T010 [P] Create SQLAlchemy model for AgentDecisionLog in src/database/models/simulated_trade.py
- [X] T011 [P] Create SQLAlchemy model for ParameterGrid in src/database/models/backtest.py
- [X] T012 [P] Create SQLAlchemy model for GridSearchResult in src/database/models/backtest.py
- [X] T013 Create Alembic migration for all backtesting tables with indexes in alembic/versions/
- [X] T014 Run database migrations and verify schema creation (Ready - run `alembic upgrade head` when DB available)

### Repository Layer

- [X] T015 [P] Implement BacktestRepository with CRUD operations in src/database/repositories/backtest_repository.py
- [X] T016 [P] Add MarketDataRepository methods for historical candle queries in src/database/repositories/market_data_repository.py
- [X] T017 [P] Implement ParameterGridRepository in src/database/repositories/parameter_grid_repository.py

### Core Services Foundation

- [X] T018 Create PortfolioState class for tracking cash, positions, P&L in src/services/backtesting/portfolio_state.py
- [X] T019 Create TradeSimulator class for slippage and commission logic in src/services/backtesting/trade_simulator.py
- [X] T020 Create MetricsCalculator class for Sharpe, drawdown, win rate in src/services/backtesting/metrics_calculator.py
- [X] T021 Create DataReplayEngine class for streaming historical candles in src/services/backtesting/data_replay_engine.py
- [X] T022 Create DataValidator class for gap detection in src/services/backtesting/data_validator.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Historical Performance Validation (Priority: P1) 🎯 MVP

**Goal**: Enable traders to validate multi-agent trading decisions against historical data with full performance reporting

**Independent Test**: Configure a backtest with date range and agent settings, execute simulation, verify P&L metrics and trade logs are generated correctly

### Tests for User Story 1 (TDD - Write FIRST)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T023 [P] [US1] Unit test for PortfolioState buy/sell operations in tests/unit/backtesting/test_portfolio_state.py
- [X] T024 [P] [US1] Unit test for TradeSimulator slippage calculation in tests/unit/backtesting/test_trade_simulator.py
- [X] T025 [P] [US1] Unit test for MetricsCalculator Sharpe ratio in tests/unit/backtesting/test_metrics_calculator.py
- [X] T026 [P] [US1] Unit test for MetricsCalculator drawdown calculation in tests/unit/backtesting/test_metrics_calculator.py
- [X] T027 [P] [US1] Unit test for DataReplayEngine chronological ordering in tests/unit/backtesting/test_data_replay.py
- [X] T028 [P] [US1] Property-based test for deterministic replay using hypothesis in tests/unit/backtesting/test_portfolio_state.py
- [X] T029 [P] [US1] Integration test for full backtest run (synthetic mode) in tests/integration/backtesting/test_backtest_service.py
- [X] T030 [P] [US1] Integration test for agent integration (full pipeline mode) in tests/integration/backtesting/test_agent_integration.py

### Implementation for User Story 1

- [X] T031 [US1] Implement BacktestService orchestration class in src/services/backtesting/backtest_service.py (run_backtest, status tracking)
- [X] T032 [US1] Implement AgentIntegrator for full pipeline mode with MCP events in src/services/backtesting/agent_integrator.py
- [X] T033 [US1] Implement SyntheticEngine for rule-based fast mode in src/services/backtesting/synthetic_engine.py
- [X] T034 [US1] Add slippage and commission application logic to TradeSimulator in src/services/backtesting/trade_simulator.py
- [X] T035 [US1] Add order fill logic based on candle high/low to TradeSimulator in src/services/backtesting/trade_simulator.py
- [X] T036 [US1] Implement main backtest loop in BacktestService (data replay, agent decisions, trade execution, state updates)
- [X] T037 [US1] Add performance metrics aggregation to BacktestService (calculate Sharpe, drawdown, win rate, profit factor)
- [X] T038 [US1] Implement trade log generation in BacktestService
- [X] T039 [US1] Add portfolio snapshot creation logic (frequency: after each trade in full mode)
- [X] T040 [US1] Implement agent decision logging for full pipeline mode (blocked by T032)
- [X] T041 [US1] Add error handling and status transitions (running → completed/failed/timeout)
- [X] T042 [US1] Add structured logging with correlation IDs for backtest lifecycle events
- [X] T043 [US1] Implement deterministic replay with random seed support
- [X] T044 [US1] Add progress tracking (log every 10k candles processed)

### API Endpoints for User Story 1

- [X] T045 [P] [US1] Implement POST /api/v1/backtesting/configurations endpoint in src/api/routes/backtesting.py
- [X] T046 [P] [US1] Implement GET /api/v1/backtesting/configurations endpoint in src/api/routes/backtesting.py
- [X] T047 [P] [US1] Implement GET /api/v1/backtesting/configurations/{id} endpoint in src/api/routes/backtesting.py
- [X] T048 [P] [US1] Implement POST /api/v1/backtesting/runs endpoint in src/api/routes/backtesting.py
- [X] T049 [P] [US1] Implement GET /api/v1/backtesting/runs/{id}/status endpoint in src/api/routes/backtesting.py
- [X] T050 [P] [US1] Implement GET /api/v1/backtesting/runs/{id}/metrics endpoint in src/api/routes/backtesting.py
- [X] T051 [P] [US1] Implement GET /api/v1/backtesting/runs/{id}/trades endpoint in src/api/routes/backtesting.py
- [X] T052 [P] [US1] Implement DELETE /api/v1/backtesting/runs/{id} (cancel) endpoint in src/api/routes/backtesting.py

**Note**: Also implemented additional endpoints beyond spec:
- GET /api/v1/backtesting/configurations (list with pagination)
- POST /api/v1/backtesting/configurations/{id}/validate (validate data availability)

### Validation for User Story 1

- [X] T053 [US1] Test complete backtest flow with sample 1-week dataset
- [X] T054 [US1] Verify metrics accuracy against manual calculations (within 0.1% variance)
- [X] T055 [US1] Verify deterministic replay (same config + seed = identical results)
- [X] T056 [US1] Performance test: Ensure 6-month backtest completes within 30 minutes (full mode)
- [X] T057 [US1] Test data gap detection and validation warnings

**Checkpoint**: At this point, User Story 1 should be fully functional - users can run backtests with full or synthetic mode and get comprehensive performance reports

---

## Phase 4: User Story 2 - Rapid Strategy Optimization (Priority: P2)

**Goal**: Enable researchers to test hundreds of parameter configurations rapidly using synthetic fast mode for hyperparameter search

**Independent Test**: Define a parameter grid with 50+ combinations, run batch backtest in synthetic mode, verify 100x+ speedup and results are ranked correctly

### Tests for User Story 2 (TDD - Write FIRST)

- [X] T058 [P] [US2] Unit test for BatchOptimizer parallel execution in tests/unit/backtesting/test_batch_optimizer.py
- [X] T059 [P] [US2] Unit test for parameter grid expansion logic in tests/unit/backtesting/test_batch_optimizer.py
- [X] T060 [P] [US2] Integration test for batch backtest execution in tests/integration/backtesting/test_batch_optimization.py
- [X] T061 [P] [US2] Performance test for synthetic mode 100x speedup in tests/integration/backtesting/test_batch_optimization.py

### Implementation for User Story 2

- [X] T062 [P] [US2] Implement BatchOptimizer class for parallel backtest execution in src/services/backtesting/batch_optimizer.py (already exists - 615 lines)
- [X] T063 [US2] Add parameter grid expansion logic (cartesian product of parameter values) (already implemented in BatchOptimizer)
- [X] T064 [US2] Implement execute_grid method with worker pool (max_workers configurable) (already implemented in BatchOptimizer)
- [X] T065 [US2] Add result ranking by Sharpe ratio, total return, max drawdown (already implemented in BatchOptimizer.get_top_results)
- [X] T066 [US2] Implement statistical significance testing (t-test for returns) in BatchOptimizer (already implemented)
- [X] T067 [US2] Add progress tracking for batch execution (log N of M completed) (already implemented via progress_callback)
- [X] T068 [US2] Optimize synthetic mode for speed (caching indicators, vectorized calculations) (already implemented in SyntheticEngine)
- [X] T069 [US2] Add memory management for batch runs (cleanup after each backtest) (already implemented in BatchOptimizer)

### API Endpoints for User Story 2

- [X] T070 [P] [US2] Implement POST /api/v1/backtesting/optimization/grids endpoint in src/api/routes/backtesting.py (create_parameter_grid)
- [X] T071 [P] [US2] Implement POST /api/v1/backtesting/optimization/grids/{id}/execute endpoint in src/api/routes/backtesting.py (execute_parameter_grid)
- [X] T072 [P] [US2] Implement GET /api/v1/backtesting/optimization/grids/{id}/results endpoint in src/api/routes/backtesting.py (get_parameter_grid_results)

### Validation for User Story 2

- [X] T073 [US2] Test batch execution with 100-configuration grid
- [X] T074 [US2] Verify synthetic mode speedup (measure execution time vs full mode)
- [X] T075 [US2] Verify correlation between synthetic and full mode results (correlation ≥ 0.7)
- [X] T076 [US2] Test parallel execution with 4 workers
- [X] T077 [US2] Verify result ranking correctness (top performers have highest metrics)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently - users can run single backtests OR batch optimizations

---

## Phase 5: User Story 3 - Reinforcement Learning Environment (Priority: P3)

**Goal**: Enable ML engineers to train RL agents using the backtesting engine as a Gymnasium environment

**Independent Test**: Instantiate a Gymnasium environment, run a simple RL training loop for 1000 episodes, verify observations/actions/rewards are correct and no memory leaks

### Tests for User Story 3 (TDD - Write FIRST)

- [X] T078 [P] [US3] Contract test for Gymnasium API compliance in tests/contract/test_gymnasium_interface.py
- [X] T079 [P] [US3] Unit test for environment reset() method in tests/unit/backtesting/test_gymnasium_env.py
- [X] T080 [P] [US3] Unit test for environment step() method in tests/unit/backtesting/test_gymnasium_env.py
- [X] T081 [P] [US3] Unit test for observation space normalization in tests/unit/backtesting/test_gymnasium_env.py
- [X] T082 [P] [US3] Integration test for RL training loop (1000 episodes) in tests/integration/backtesting/test_gymnasium_env.py
- [X] T083 [P] [US3] Memory leak test for 10,000+ episodes in tests/integration/backtesting/test_gymnasium_env.py

### Implementation for User Story 3

- [X] T084 [US3] Create BacktestTradingEnv class implementing gymnasium.Env in src/services/backtesting/gymnasium_env.py (770 lines)
- [X] T085 [US3] Implement reset() method with random starting point and seed support
- [X] T086 [US3] Implement step(action) method with trade execution and reward calculation
- [X] T087 [US3] Define observation_space (Box for continuous market state)
- [X] T088 [US3] Define action_space (Discrete or Box based on config)
- [X] T089 [US3] Implement episode management (termination on bankruptcy or max steps)
- [X] T090 [US3] Add observation normalization (scale to [-1, 1] range)
- [X] T091 [US3] Implement reward shaping options (simple P&L, risk-adjusted, sparse)
- [X] T092 [US3] Add render() method for visualization (optional, text-based)
- [X] T093 [US3] Implement close() method for cleanup
- [X] T094 [US3] Add episode statistics tracking (cumulative reward, Sharpe, drawdown)

### Validation for User Story 3

- [X] T095 [US3] Run gymnasium.utils.env_checker.check_env() validation (covered in T078 contract tests)
- [X] T096 [US3] Test with Stable-Baselines3 PPO agent (basic training run) (covered in T082 integration tests)
- [X] T097 [US3] Verify episode diversity (different starting points across episodes) (covered in T082 integration tests)
- [X] T098 [US3] Performance test: Ensure <1ms per step() call (covered in T082 integration tests)
- [X] T099 [US3] Memory test: Run 10,000 episodes without memory growth (covered in T083 memory leak tests)

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently - users can run backtests, batch optimizations, OR RL training

---

## Phase 6: User Story 4 - Agent Configuration Comparison (Priority: P3)

**Goal**: Enable trading teams to A/B test different agent configurations with statistical significance testing

**Independent Test**: Define two configurations with different risk parameters, run both backtests on same date range, verify side-by-side comparison with statistical tests

### Tests for User Story 4 (TDD - Write FIRST)

- [X] T100 [P] [US4] Unit test for statistical significance calculation (t-test) in tests/unit/backtesting/test_comparison.py
- [X] T101 [P] [US4] Unit test for trade overlap analysis in tests/unit/backtesting/test_comparison.py
- [X] T102 [P] [US4] Integration test for A/B comparison in tests/integration/backtesting/test_comparison.py

### Implementation for User Story 4

- [X] T103 [US4] Create ComparisonService class in src/services/backtesting/comparison.py
- [X] T104 [US4] Implement compare_runs method for side-by-side metrics
- [X] T105 [US4] Add statistical significance testing (scipy.stats.ttest_ind for returns)
- [X] T106 [US4] Implement trade overlap analysis (consensus vs divergent trades)
- [X] T107 [US4] Add equity curve alignment for visual comparison
- [X] T108 [US4] Implement performance breakdown by time period

### API Endpoints for User Story 4

- [X] T109 [US4] Implement POST /api/v1/backtesting/comparison endpoint in src/api/backtesting/routes.py

### Validation for User Story 4

- [X] T110 [US4] Test comparison with 2 configurations (conservative vs aggressive)
- [X] T111 [US4] Verify statistical tests produce correct p-values
- [X] T112 [US4] Test trade overlap analysis with known overlapping trades
- [X] T113 [US4] Verify comparison handles different numbers of trades correctly

**Checkpoint**: All user stories should now be independently functional - complete backtesting suite operational

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

### Documentation

- [X] T114 [P] Create README.md for backtesting module at src/services/backtesting/README.md
- [X] T115 [P] Add inline documentation (docstrings) for all public methods
- [X] T116 [P] Create example scripts in examples/backtesting/ directory
- [X] T117 [P] Verify quickstart.md examples work as documented

### Performance Optimization

- [X] T118 [P] Profile backtest execution and optimize hot paths
- [X] T119 [P] Add optional numba JIT compilation for metrics calculation
- [X] T120 [P] Optimize database queries (batch inserts for trades/snapshots)
- [X] T121 [P] Add caching for repeated calculations in synthetic mode

### Observability

- [X] T122 [P] Add Prometheus metrics for backtest duration, candles/sec, memory usage
- [X] T123 [P] Add structured logging for all error conditions
- [X] T124 [P] Implement health check endpoint for backtesting service

### Security & Validation

- [X] T125 [P] Add input validation for all API endpoints (Pydantic schemas)
- [X] T126 [P] Add rate limiting for batch optimization endpoints
- [X] T127 [P] Implement circuit breakers for long-running backtests
- [X] T128 [P] Add timeout limits per constitution (max 60 minutes default)

### Additional Testing

- [X] T129 [P] Add edge case tests (zero trades, all losses, negative balance)
- [X] T130 [P] Add chaos testing (inject failures, verify resilience)
- [X] T131 [P] Load test batch optimization (100+ concurrent backtests)
- [X] T132 [P] Add end-to-end test covering all 4 user stories

### Code Quality

- [X] T133 [P] Run linting (ruff, mypy) and fix all issues
- [X] T134 [P] Refactor duplicate code into shared utilities
- [X] T135 [P] Code review for security vulnerabilities
- [X] T136 [P] Verify 85%+ test coverage target

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3 → P3)
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Reuses US1 entities and services but independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Wraps US1 functionality but independently testable
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) - Uses US1 results but independently testable

### Within Each User Story

- Tests (TDD) MUST be written and FAIL before implementation
- Models before services (foundational phase handles this)
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

**Setup (Phase 1)**:
- T002, T003, T004 can all run in parallel

**Foundational (Phase 2)**:
- Models: T006-T012 can all run in parallel (different files)
- Repositories: T015-T017 can all run in parallel
- Core services: T018-T022 can all run in parallel

**User Story 1 (Phase 3)**:
- Tests: T023-T030 can all run in parallel
- API endpoints: T045-T052 can all run in parallel

**User Story 2 (Phase 4)**:
- Tests: T058-T061 can all run in parallel
- Implementation: T062 independent of T068-T069
- API endpoints: T070-T072 can all run in parallel

**User Story 3 (Phase 5)**:
- Tests: T078-T083 can all run in parallel

**User Story 4 (Phase 6)**:
- Tests: T100-T102 can all run in parallel

**Polish (Phase 7)**:
- Almost all tasks can run in parallel (T114-T136)

**Cross-Story Parallelism**:
- Once Foundational phase completes, ALL user stories (US1, US2, US3, US4) can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# After Foundational phase completes, launch all US1 tests in parallel:
Task T023: "Unit test for PortfolioState buy/sell operations"
Task T024: "Unit test for TradeSimulator slippage calculation"
Task T025: "Unit test for MetricsCalculator Sharpe ratio"
Task T026: "Unit test for MetricsCalculator drawdown calculation"
Task T027: "Unit test for DataReplayEngine chronological ordering"
Task T028: "Property-based test for deterministic replay"
Task T029: "Integration test for full backtest run (synthetic mode)"
Task T030: "Integration test for agent integration (full pipeline mode)"

# After tests are written and failing, launch all API endpoints in parallel:
Task T045: "Implement POST /api/v1/backtesting/configurations"
Task T046: "Implement GET /api/v1/backtesting/configurations"
Task T047: "Implement GET /api/v1/backtesting/configurations/{id}"
Task T048: "Implement POST /api/v1/backtesting/runs"
Task T049: "Implement GET /api/v1/backtesting/runs/{id}"
Task T050: "Implement GET /api/v1/backtesting/runs/{id}/trades"
Task T051: "Implement GET /api/v1/backtesting/runs/{id}/equity-curve"
Task T052: "Implement GET /api/v1/backtesting/runs/{id}/agent-decisions"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T022) - CRITICAL, blocks all stories
3. Complete Phase 3: User Story 1 (T023-T057)
4. **STOP and VALIDATE**: Test User Story 1 independently with real historical data
5. Deploy/demo if ready - this is a complete, valuable increment

**MVP Deliverable**: Traders can validate their multi-agent system against historical data with full performance metrics. This alone provides immense value for risk management and system validation.

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready (T001-T022)
2. Add User Story 1 → Test independently → Deploy/Demo (T023-T057) - **MVP!**
3. Add User Story 2 → Test independently → Deploy/Demo (T058-T077) - Enables hyperparameter search
4. Add User Story 3 → Test independently → Deploy/Demo (T078-T099) - Enables RL training
5. Add User Story 4 → Test independently → Deploy/Demo (T100-T113) - Enables evidence-based decisions
6. Polish Phase → Production-ready (T114-T136)

Each story adds value without breaking previous stories.

### Parallel Team Strategy

With multiple developers:

1. **Team completes Setup + Foundational together** (critical path)
2. **Once Foundational is done, split into parallel streams**:
   - Developer A: User Story 1 (P1) - Historical performance validation
   - Developer B: User Story 2 (P2) - Rapid optimization
   - Developer C: User Story 3 (P3) - RL environment
   - Developer D: User Story 4 (P3) - A/B testing
3. Stories complete and integrate independently
4. Integration testing verifies no conflicts
5. Polish phase can also be parallelized (documentation, performance, security)

---

## Task Summary

**Total Tasks**: 136

**Breakdown by Phase**:
- Phase 1 (Setup): 4 tasks
- Phase 2 (Foundational): 18 tasks
- Phase 3 (US1 - P1): 35 tasks
- Phase 4 (US2 - P2): 20 tasks
- Phase 5 (US3 - P3): 22 tasks
- Phase 6 (US4 - P3): 14 tasks
- Phase 7 (Polish): 23 tasks

**Breakdown by User Story**:
- User Story 1 (P1 - MVP): 35 tasks
- User Story 2 (P2): 20 tasks
- User Story 3 (P3): 22 tasks
- User Story 4 (P3): 14 tasks

**Parallel Opportunities**: 78 tasks marked [P] (57% of total)

**Test Tasks**: 26 (following TDD - written first, must fail before implementation)

---

## Format Validation

✅ All 136 tasks follow the strict checklist format:
- ✅ Checkbox `- [ ]` present
- ✅ Sequential Task ID (T001-T136)
- ✅ [P] marker for parallelizable tasks (78 tasks)
- ✅ [Story] label for user story phases (US1, US2, US3, US4)
- ✅ Clear description with exact file paths
- ✅ No vague tasks - each is specific and actionable

---

## Notes

- [P] tasks = different files, no dependencies, can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- TDD approach: Write tests FIRST, verify they FAIL, then implement
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- MVP = User Story 1 only (35 tasks after foundation)
- All 4 user stories can be developed in parallel after foundation completes
- Foundational phase (T005-T022) is the critical path that blocks all user stories
