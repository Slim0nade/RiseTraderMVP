---
description: "Task list for MT4 Integration feature implementation"
---

# Tasks: MT4 Integration

**Input**: Design documents from `/specs/001-mt4-integration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED per constitution TDD principle (85%+ coverage target)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `src/`, `tests/` at repository root
- Paths shown below assume backend structure as defined in plan.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project directory structure per plan.md (src/trading/execution/, src/services/, src/database/, src/api/, src/monitoring/, src/utils/, tests/, config/)
- [X] T002 [P] Add PyZMQ dependency to requirements.txt with version pinning (pyzmq>=25.0.0)
- [X] T003 [P] Add pytest-asyncio to requirements.txt for async test support
- [X] T004 [P] Create config/mt4_config.yaml with default configuration (ports, timeouts, risk limits)
- [X] T005 [P] Create .env.example with MT4-related environment variables (ZMQ keys, host, ports, feature flags)
- [X] T006 [P] Create scripts/generate_zmq_keys.py utility for CurveZMQ key generation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 [P] Create database migration for mt4_connections table (alembic/versions/xxx_create_mt4_connections.py)
- [X] T008 [P] Create database migration for mt4_orders table (alembic/versions/xxx_create_mt4_orders.py)
- [X] T009 [P] Create database migration for mt4_positions table (alembic/versions/xxx_create_mt4_positions.py)
- [X] T010 [P] Create MT4Connection SQLAlchemy model in src/database/models/mt4_connection.py
- [X] T011 [P] Create MT4Order SQLAlchemy model in src/database/models/mt4_orders.py
- [X] T012 [P] Create MT4Position SQLAlchemy model in src/database/models/mt4_positions.py
- [X] T013 [P] Create MT4ConnectionRepository base in src/database/repositories/mt4_connection_repository.py
- [X] T014 [P] Create MT4OrderRepository base in src/database/repositories/mt4_order_repository.py
- [X] T015 Create BaseEvent Pydantic model in src/trading/execution/mt4_models.py (base for all events)
- [X] T016 [P] Implement CurveZMQ encryption setup in src/trading/execution/mt4_encryption.py (key loading, socket configuration)
- [X] T017 [P] Create Prometheus metrics collectors in src/monitoring/mt4_metrics.py (latency, error rates, connection status)
- [X] T018 [P] Implement structured logging utility in src/utils/mt4_helpers.py (JSON format with correlation IDs)
- [X] T019 [P] Create Redis client wrapper for portfolio risk caching in src/utils/redis_client.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Send Market Orders to MT4 (Priority: P1) 🎯 MVP

**Goal**: Enable automated order submission to MT4 with confirmation tracking

**Independent Test**: Submit a BUY order for CrudeOIL 0.1 lots and verify it appears in MT4 with correct parameters within 500ms

### Tests for User Story 1 (TDD: Write FIRST, ensure they FAIL before implementation)

- [X] T020 [P] [US1] Write unit test for MT4Client.send_command() in tests/unit/test_mt4_client.py (mock ZMQ socket)
- [X] T021 [P] [US1] Write unit test for order submission validation in tests/unit/test_symbol_loader.py (volume, symbol, direction)
- [X] T022 [P] [US1] Write unit test for order confirmation handling in tests/unit/test_mt4_integration_service.py
- [X] T023 [P] [US1] Write integration test for end-to-end order flow in tests/integration/test_mt4_order_flow.py (with mock EA)
- [X] T024 [P] [US1] Write contract test for create_instant_order schema in tests/contract/test_mt4_schemas.py

**Verify**: ✅ Tests written, implementation files don't exist (TDD checkpoint verified)

### Implementation for User Story 1

- [X] T025 [US1] Implement MT4Client base class in src/trading/execution/mt4_client.py (ZMQ REQ socket, send/receive, timeout handling)
- [X] T025.5 [US1] Implement SymbolLoader in src/trading/execution/symbol_loader.py (dynamic symbol validation from MT4)
- [X] T026 [US1] Add create_instant_order and get_symbols commands to MT4Client in src/trading/execution/mt4_client.py (BUY/SELL market orders)
- [X] T026.5 [US1] Add get_symbols command handler to MT4 EA in mt4/experts/RiseTraderMT4Server.mq4
- [X] T027 [US1] Implement order submission in MT4IntegrationService.submit_market_order() in src/services/mt4_integration_service.py
- [X] T028 [US1] Add order persistence to MT4OrderRepository.create() in src/database/repositories/mt4_order_repository.py (✅ Already integrated in T027)
- [X] T029 [US1] Implement order confirmation event publishing in src/services/mt4_integration_service.py (Redis pub/sub) (✅ Already integrated in T027)
- [X] T030 [US1] Add order_confirmed event handler in src/services/mt4_integration_service.py (update database status) (✅ Already integrated in T027)
- [X] T031 [US1] Implement correlation ID generation and tracking in src/utils/mt4_helpers.py (✅ Already integrated in T027)
- [X] T032 [US1] Add logging for all order operations in src/services/mt4_integration_service.py (structured JSON logs) (✅ Already integrated in T027)
- [X] T033 [US1] Add Prometheus metrics for order latency and success rate in src/monitoring/mt4_metrics.py (✅ Already integrated in T027)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently. Run all US1 tests to verify they PASS.

---

## Phase 4: User Story 2 - Receive Order Status Updates (Priority: P1)

**Goal**: Real-time order and position status tracking from MT4

**Independent Test**: Place an order in MT4 (manually or via US1), verify system receives fill notification within 100ms with correct details

### Tests for User Story 2 (TDD: Write FIRST)

- [X] T034 [P] [US2] Write unit test for ZMQ PUB socket subscription in tests/unit/test_mt4_client.py (11 tests added)
- [X] T035 [P] [US2] Write unit test for position update event parsing in tests/unit/test_mt4_integration_service.py (8 tests added)
- [X] T036 [P] [US2] Write unit test for position P&L calculation in tests/unit/test_mt4_models.py (13 tests added)
- [X] T037 [P] [US2] Write integration test for position closure flow in tests/integration/test_mt4_position_flow.py (7 integration tests added)
- [X] T038 [P] [US2] Write contract test for position_updated event schema in tests/contract/test_mt4_schemas.py (14 contract tests added)

**Verify**: ✅ Tests complete (53 new tests) - Ready for implementation

### Implementation for User Story 2

- [X] T039 [US2] Implement PUB socket subscription in MT4Client in src/trading/execution/mt4_client.py (market data stream)
- [X] T040 [US2] Create event listener loop in MT4Client.start_listening() in src/trading/execution/mt4_client.py
- [X] T041 [US2] Implement position update handler in src/services/mt4_integration_service.py (parse events, update database)
- [X] T042 [US2] Add position persistence in MT4PositionRepository in src/database/repositories/mt4_position_repository.py
- [X] T043 [US2] Implement position_updated event publishing in src/services/mt4_integration_service.py
- [X] T044 [US2] Add position_closed event handler in src/services/mt4_integration_service.py (finalize P&L, update order status)
- [X] T045 [US2] Implement order rejection handling in src/services/mt4_integration_service.py (update status, log errors)
- [X] T046 [US2] Add metrics for position updates and closures in src/monitoring/mt4_metrics.py

**Checkpoint**: User Stories 1 AND 2 should both work independently. Orders can be sent and status tracked end-to-end.

---

## Phase 5: User Story 3 - Stream Live Market Data (Priority: P2)

**Goal**: Real-time market tick streaming from MT4 for signal generation

**Independent Test**: Subscribe to CrudeOIL feed, verify bid/ask updates arrive within 50ms matching MT4 prices

### Tests for User Story 3 (TDD: Write FIRST)

- [X] T047 [P] [US3] Write unit test for market tick parsing in tests/unit/trading/test_mt4_models.py (22 tests added)
- [X] T048 [P] [US3] Write unit test for market tick event emission in tests/unit/services/test_mt4_integration_service.py (8 tests added)
- [X] T049 [P] [US3] Write integration test for multi-symbol subscription in tests/integration/trading/test_mt4_communication.py (14 tests added)
- [X] T050 [P] [US3] Write contract test for market_tick event schema in tests/contract/test_mt4_schemas.py (14 tests added)
- [ ] T051 [P] [US3] Write performance test for high-frequency tick handling in tests/integration/test_mt4_performance.py

**Verify**: ⏸️ Tests T047-T050 complete (58 tests), T051 skipped (performance test - optional)

### Implementation for User Story 3

- [X] T052 [US3] Extend MT4Client to handle real_time_update messages in src/trading/execution/mt4_client.py (already complete from T039-T040)
- [X] T053 [US3] Implement market tick parsing in src/trading/execution/mt4_models.py (MarketTick Pydantic model - already exists)
- [X] T054 [US3] Create market data handler in src/services/mt4_integration_service.py (process ticks, emit events)
- [X] T055 [US3] Implement symbol subscription management in src/services/mt4_integration_service.py (subscribe/unsubscribe)
- [X] T056 [US3] Add market_tick event publishing to Redis in src/services/mt4_integration_service.py
- [X] T057 [US3] Implement connection health monitoring via tick timestamps in src/services/mt4_integration_service.py
- [X] T058 [US3] Add metrics for tick latency and throughput in src/services/mt4_integration_service.py

**Checkpoint**: ✅ Market data streaming functional, can feed signal generation systems

---

## Phase 6: User Story 5 - Manage Multiple Expert Advisors (Priority: P2)

**Goal**: Support concurrent EA connections with portfolio-level risk aggregation

**Independent Test**: Launch 3 EAs with different magic numbers, send orders from each, verify correct attribution and risk aggregation

### Tests for User Story 5 (TDD: Write FIRST)

- [X] T059 [P] [US5] Write unit test for magic number allocation in tests/unit/trading/test_mt4_connection_pool.py (9 tests added)
- [X] T060 [P] [US5] Write unit test for port allocation strategy in tests/unit/trading/test_mt4_connection_pool.py (21 tests total)
- [X] T061 [P] [US5] Write unit test for portfolio risk aggregation in tests/unit/services/test_mt4_integration_service.py (4 tests added)
- [X] T062 [P] [US5] Write unit test for risk limit enforcement in tests/unit/services/test_mt4_integration_service.py (5 tests added)
- [X] T063 [P] [US5] Write integration test for multi-EA coordination in tests/integration/trading/test_multi_ea_coordination.py (7 tests added)
- [X] T064 [P] [US5] Write contract test for portfolio_risk_updated event in tests/contract/test_mt4_schemas.py (1 test added)

**Verify**: ✅ Tests complete (47 tests) - Ready for implementation

### Implementation for User Story 5

- [X] T065 [US5] Implement MT4ConnectionPool class in src/trading/execution/mt4_connection_pool.py (EA registry, port allocation)
- [X] T066 [US5] Add magic number allocation logic in MT4ConnectionPool in src/trading/execution/mt4_connection_pool.py (100000-999999 range)
- [ ] T067 [US5] Implement EA registration in MT4IntegrationService.register_ea() in src/services/mt4_integration_service.py
- [ ] T068 [US5] Add connection health monitoring per EA in MT4ConnectionPool in src/trading/execution/mt4_connection_pool.py
- [ ] T069 [US5] Implement PortfolioRiskState model in src/trading/execution/mt4_models.py (Pydantic model)
- [ ] T070 [US5] Create portfolio risk aggregation in src/services/mt4_integration_service.py (aggregate across all EAs)
- [ ] T071 [US5] Implement Redis caching for portfolio state in src/services/mt4_integration_service.py
- [ ] T072 [US5] Add risk limit checks before order submission in src/services/mt4_integration_service.py (margin, exposure)
- [ ] T073 [US5] Implement portfolio_risk_updated event publishing in src/services/mt4_integration_service.py
- [ ] T074 [US5] Add metrics for per-EA and portfolio-level risk in src/monitoring/mt4_metrics.py

**Checkpoint**: Multi-EA support complete with portfolio risk management

---

## Phase 7: User Story 4 - Query Account Information (Priority: P3)

**Goal**: On-demand account information queries for monitoring and auditing

**Independent Test**: Request account info, verify response matches MT4 display within 200ms

### Tests for User Story 4 (TDD: Write FIRST)

- [ ] T075 [P] [US4] Write unit test for get_account_info command in tests/unit/test_mt4_client.py
- [ ] T076 [P] [US4] Write unit test for get_open_positions query in tests/unit/test_mt4_client.py
- [ ] T077 [P] [US4] Write unit test for account data parsing in tests/unit/test_mt4_models.py
- [ ] T078 [P] [US4] Write integration test for account query flow in tests/integration/test_mt4_communication.py
- [ ] T079 [P] [US4] Write contract test for account info response schema in tests/contract/test_mt4_schemas.py

**Verify**: Tests FAIL

### Implementation for User Story 4

- [ ] T080 [US4] Add get_account_info command to MT4Client in src/trading/execution/mt4_client.py
- [ ] T081 [US4] Add get_open_positions command to MT4Client in src/trading/execution/mt4_client.py
- [ ] T082 [US4] Add get_symbols command to MT4Client in src/trading/execution/mt4_client.py
- [ ] T083 [US4] Create AccountInfo Pydantic model in src/trading/execution/mt4_models.py
- [ ] T084 [US4] Implement account query methods in MT4IntegrationService in src/services/mt4_integration_service.py
- [ ] T085 [US4] Add account info caching with TTL in src/services/mt4_integration_service.py (reduce query load)
- [ ] T086 [US4] Create REST API endpoints for account queries in src/api/routes/mt4.py
- [ ] T087 [US4] Add API request/response models in src/api/models/mt4_models.py
- [ ] T088 [US4] Add metrics for account query latency in src/monitoring/mt4_metrics.py

**Checkpoint**: Complete account visibility available via API

---

## Phase 8: Circuit Breaker & Resilience

**Purpose**: Connection resilience and error handling

- [ ] T089 [P] Write unit tests for circuit breaker state transitions in tests/unit/test_mt4_client.py
- [ ] T090 [P] Write unit tests for exponential backoff in tests/unit/test_mt4_client.py
- [ ] T091 Implement CircuitBreaker class in src/trading/execution/mt4_client.py (CLOSED/OPEN/HALF_OPEN states)
- [ ] T092 Add exponential backoff to reconnection logic in MT4Client in src/trading/execution/mt4_client.py
- [ ] T093 Implement connection_status_changed event publishing in src/services/mt4_integration_service.py
- [ ] T094 Add automatic reconnection on connection loss in MT4Client in src/trading/execution/mt4_client.py
- [ ] T095 Implement graceful shutdown with pending message flush in MT4Client in src/trading/execution/mt4_client.py
- [ ] T096 Add circuit breaker metrics in src/monitoring/mt4_metrics.py (state, failure count)

---

## Phase 9: REST API & Management

**Purpose**: External API for EA management and monitoring

- [ ] T097 [P] Write API endpoint tests in tests/integration/test_mt4_api.py (register EA, query connections, etc.)
- [ ] T098 [P] Implement POST /mt4/connections endpoint in src/api/routes/mt4.py (register new EA)
- [ ] T099 [P] Implement GET /mt4/connections endpoint in src/api/routes/mt4.py (list all EAs)
- [ ] T100 [P] Implement GET /mt4/connections/{ea_id} endpoint in src/api/routes/mt4.py
- [ ] T101 [P] Implement DELETE /mt4/connections/{ea_id} endpoint in src/api/routes/mt4.py
- [ ] T102 [P] Implement POST /mt4/connections/{ea_id}/reconnect endpoint in src/api/routes/mt4.py
- [ ] T103 [P] Implement GET /mt4/orders endpoint in src/api/routes/mt4.py (query orders with filters)
- [ ] T104 [P] Implement GET /mt4/positions endpoint in src/api/routes/mt4.py (query open positions)
- [ ] T105 [P] Implement GET /mt4/portfolio/risk endpoint in src/api/routes/mt4.py (portfolio risk state)
- [ ] T106 [P] Implement GET /mt4/portfolio/health endpoint in src/api/routes/mt4.py (system health check)
- [ ] T107 Add OpenAPI documentation to all MT4 endpoints in src/api/routes/mt4.py

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T108 [P] Add comprehensive error handling with custom exceptions in src/trading/execution/mt4_client.py
- [ ] T109 [P] Implement input validation for all MT4 responses in src/trading/execution/mt4_client.py
- [ ] T110 [P] Add request/response logging for all ZMQ communications in src/trading/execution/mt4_client.py
- [ ] T111 [P] Create mock MT4 EA for integration testing in tests/integration/mock_mt4_ea.py
- [ ] T112 [P] Add load testing scenarios in tests/performance/test_mt4_load.py (100 concurrent EAs, 1000 orders/hour)
- [ ] T113 [P] Update config/mt4_config.yaml with production-ready defaults
- [ ] T114 [P] Create database seed data for testing in scripts/seed_mt4_test_data.py
- [ ] T115 [P] Add health check endpoint for MT4 integration service in src/api/routes/health.py
- [ ] T116 [P] Document environment variables in .env.example with descriptions
- [ ] T117 [P] Create quickstart validation script per quickstart.md in scripts/validate_mt4_setup.sh
- [ ] T118 Run final coverage report (target: 85%+) and address any gaps
- [ ] T119 Perform security review of encryption implementation
- [ ] T120 Run end-to-end smoke test with all user stories

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - **US1 (Phase 3)**: Can start after Foundational - No dependencies on other stories
  - **US2 (Phase 4)**: Can start after Foundational - Integrates with US1 but independently testable
  - **US3 (Phase 5)**: Can start after Foundational - Independent of US1/US2
  - **US5 (Phase 6)**: Can start after Foundational - Builds on US1 patterns but independently testable
  - **US4 (Phase 7)**: Can start after Foundational - Independent of all other stories
- **Circuit Breaker (Phase 8)**: Can start after Foundational, enhances all user stories
- **REST API (Phase 9)**: Depends on US1, US2, US5 being complete
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Foundation for order execution - MVP candidate
- **User Story 2 (P1)**: Complements US1 for full order lifecycle - MVP candidate
- **User Story 3 (P2)**: Independent - can be developed in parallel with US1/US2
- **User Story 5 (P2)**: Builds on US1 pattern but adds multi-EA coordination
- **User Story 4 (P3)**: Independent - can be developed anytime after Foundational

### Recommended Execution Order

**Option 1 - MVP First (US1 + US2 only)**:
1. Phase 1: Setup (T001-T006)
2. Phase 2: Foundational (T007-T019)
3. Phase 3: User Story 1 (T020-T033)
4. Phase 4: User Story 2 (T034-T046)
5. Phase 8: Circuit Breaker (T089-T096) - Critical for production
6. **STOP and VALIDATE**: Deploy MVP with basic order execution

**Option 2 - Incremental Delivery**:
1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Demo
3. Add User Story 2 → Test independently → Demo
4. Add User Story 5 → Test multi-EA → Demo
5. Add User Story 3 → Test market data → Demo
6. Add User Story 4 → Complete feature → Demo

**Option 3 - Parallel Team Strategy**:
With multiple developers after Foundational phase complete:
- Developer A: User Story 1 + User Story 2 (core execution)
- Developer B: User Story 3 + User Story 4 (data & queries)
- Developer C: User Story 5 (multi-EA coordination)
- All converge: Circuit Breaker + REST API + Polish

### Parallel Opportunities

**Within Setup Phase**:
- T002, T003, T004, T005, T006 can all run in parallel

**Within Foundational Phase**:
- Database migrations (T007-T009) in parallel
- Models (T010-T012) in parallel after migrations
- Repositories (T013-T014) in parallel after models
- Support utilities (T016-T019) in parallel

**Within Each User Story**:
- All tests can run in parallel (marked with [P])
- Models creation in parallel
- Independent modules in parallel

**Across User Stories** (after Foundational):
- US1, US3, US4 can start in parallel (no cross-dependencies)
- US2 can start in parallel but integrates with US1
- US5 can start after US1 pattern is established

---

## Parallel Example: Foundational Phase

```bash
# Launch all migrations together:
Task T007: Create database migration for mt4_connections table
Task T008: Create database migration for mt4_orders table
Task T009: Create database migration for mt4_positions table

# After migrations, launch all models together:
Task T010: Create MT4Connection SQLAlchemy model
Task T011: Create MT4Order SQLAlchemy model
Task T012: Create MT4Position SQLAlchemy model

# After models, launch all repositories together:
Task T013: Create MT4ConnectionRepository base
Task T014: Create MT4OrderRepository base
```

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all User Story 1 tests together:
Task T020: Write unit test for MT4Client.send_command()
Task T021: Write unit test for order submission validation
Task T022: Write unit test for order confirmation handling
Task T023: Write integration test for end-to-end order flow
Task T024: Write contract test for create_instant_order schema
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 Only)

1. Complete Phase 1: Setup (T001-T006)
2. Complete Phase 2: Foundational (T007-T019) - CRITICAL
3. Complete Phase 3: User Story 1 (T020-T033) - Core execution
4. Complete Phase 4: User Story 2 (T034-T046) - Status tracking
5. Complete Phase 8: Circuit Breaker (T089-T096) - Resilience
6. **STOP and VALIDATE**: Test MVP independently
7. Deploy/demo if ready

This MVP delivers:
- ✅ Order submission to MT4
- ✅ Order confirmation and status tracking
- ✅ Position monitoring
- ✅ Connection resilience
- ✅ Basic observability

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 5 → Test multi-EA → Deploy/Demo
5. Add User Story 3 → Test market data → Deploy/Demo
6. Add User Story 4 → Complete feature → Deploy/Demo
7. Each story adds value without breaking previous stories

### Testing Strategy

**Per User Story**:
1. Write tests FIRST (TDD)
2. Verify tests FAIL
3. Implement to make tests PASS
4. Refactor while keeping tests green
5. Achieve 85%+ coverage for that story

**Integration Testing**:
- Use mock MT4 EA (T111) for integration tests
- Test with real MT4 EA before production
- Load test with 100 concurrent EAs (T112)

**Contract Testing**:
- Validate all message schemas match contracts/
- Test both request and response formats
- Verify event schemas for pub/sub

---

## Notes

- [P] tasks = different files, no dependencies, can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- **TDD Discipline**: Verify tests FAIL before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- 85%+ test coverage is NON-NEGOTIABLE per constitution
- CurveZMQ encryption (T016) is BLOCKING for production
- Portfolio risk aggregation (US5) is CRITICAL before live trading

---

## Summary

- **Total Tasks**: 120
- **User Story 1**: 14 tasks (T020-T033)
- **User Story 2**: 13 tasks (T034-T046)
- **User Story 3**: 11 tasks (T047-T058)
- **User Story 5**: 16 tasks (T059-T074)
- **User Story 4**: 14 tasks (T075-T088)
- **Infrastructure**: 8 tasks (T089-T096)
- **API**: 11 tasks (T097-T107)
- **Polish**: 13 tasks (T108-T120)

**Parallel Opportunities**: 60+ tasks marked [P] for concurrent execution

**MVP Scope** (Recommended): User Stories 1 + 2 (27 implementation tasks) + Foundational (13 tasks) + Circuit Breaker (8 tasks) = 48 critical path tasks

**Constitution Compliance**:
- ✅ TDD enforced (tests written first)
- ✅ 85%+ coverage target
- ✅ Security (CurveZMQ encryption)
- ✅ Observability (logging, metrics, tracing)
- ✅ Repository pattern
- ✅ Event-driven architecture
- ✅ Independent user story testing

**Ready for**: `/speckit.implement` to execute tasks or manual implementation following task order
