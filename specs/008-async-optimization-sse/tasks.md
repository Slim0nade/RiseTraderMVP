# Tasks: Async Optimization Engine with SSE Notifications

**Input**: Design documents from `/specs/008-async-optimization-sse/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are included based on TDD approach specified in constitution check.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, new dependency, and shared utilities

- [X] T001 Add sse-starlette to requirements.txt
- [X] T002 [P] Create grid search utility with itertools.product in src/utils/grid_search.py
- [X] T003 [P] Create SSE event manager utility in src/utils/sse_events.py
- [X] T004 Verify Redis connectivity and update redis_client.py with job key patterns

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database models and migrations required by ALL user stories

**⚠️ CRITICAL**: User story work cannot begin until this phase is complete

- [X] T005 Create OptimizationRun model in src/database/models/optimization.py
- [X] T006 [P] Create PriceAlert model in src/database/models/optimization.py
- [X] T007 Create Alembic migration for optimization_runs and price_alerts tables in alembic/versions/
- [X] T008 Run migration and verify tables created: `alembic upgrade head`
- [X] T009 [P] Register models in src/database/models/__init__.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Async Job Queue (Priority: P1) 🎯 MVP

**Goal**: Start long-running optimizations asynchronously, get results later without MCP timeout

**Independent Test**: Call `optimize_strategy_async` → receive job_id immediately → poll status → get results

### Tests for User Story 1

- [X] T010 [P] [US1] Unit test for job submission in tests/unit/test_optimization_job.py
- [X] T011 [P] [US1] Unit test for job status retrieval in tests/unit/test_optimization_job.py
- [X] T012 [P] [US1] Unit test for job cancellation in tests/unit/test_optimization_job.py

### Implementation for User Story 1

- [X] T013 [US1] Create OptimizationJobService class in src/services/optimization_job_service.py
- [X] T014 [US1] Implement submit_job() with Redis state storage in src/services/optimization_job_service.py
- [X] T015 [US1] Implement get_job_status() in src/services/optimization_job_service.py
- [X] T016 [US1] Implement background worker run_optimization_worker() in src/services/optimization_job_service.py
- [X] T017 [US1] Implement cancel_job() in src/services/optimization_job_service.py
- [X] T018 [US1] Implement list_active_jobs() in src/services/optimization_job_service.py
- [X] T019 [US1] Implement get_job_results() in src/services/optimization_job_service.py
- [X] T020 [US1] Add async job endpoints to src/api/routes/optimizer.py (POST /jobs, GET /jobs, GET /jobs/{id}, DELETE /jobs/{id})
- [X] T021 [US1] Add MCP tools: optimize_strategy_async, get_optimization_status, cancel_optimization, list_active_jobs in src/mcp/server.py
- [X] T022 [US1] Add get_optimization_results MCP tool in src/mcp/server.py
- [X] T023 [US1] Integration test for full job lifecycle in tests/integration/test_optimization_async.py

**Checkpoint**: User Story 1 complete - async optimization works independently

---

## Phase 4: User Story 2 - Deterministic Grid Search (Priority: P1)

**Goal**: Test ALL parameter combinations systematically, reproducible results

**Independent Test**: Run optimization twice with same params → identical results, all combinations tested

### Tests for User Story 2

- [X] T024 [P] [US2] Unit test for generate_grid_combinations() in tests/unit/test_grid_search.py
- [X] T025 [P] [US2] Unit test for deterministic result ordering in tests/unit/test_grid_search.py
- [X] T026 [P] [US2] Unit test for grid size validation (max 10,000) in tests/unit/test_grid_search.py

### Implementation for User Story 2

- [X] T027 [US2] Implement generate_grid_combinations() in src/utils/grid_search.py
- [X] T028 [US2] Implement calculate_grid_size() with validation in src/utils/grid_search.py
- [X] T029 [US2] Integrate grid search into optimization worker in src/services/optimization_job_service.py
- [X] T030 [US2] Add progress tracking (current_params, combinations_tested) to job state in src/services/optimization_job_service.py
- [X] T031 [US2] Integration test for deterministic results in tests/integration/test_optimization_async.py

**Checkpoint**: User Story 2 complete - deterministic grid search verified

---

## Phase 5: User Story 3 - Optimization History Persistence (Priority: P1)

**Goal**: Save all optimization runs to database, query past results

**Independent Test**: Run optimization → restart API → query list_optimization_runs → results still available

### Tests for User Story 3

- [X] T032 [P] [US3] Unit test for save_optimization_run() in tests/unit/test_optimization_history.py
- [X] T033 [P] [US3] Unit test for list_optimization_runs() in tests/unit/test_optimization_history.py
- [X] T034 [P] [US3] Unit test for get_optimization_run() in tests/unit/test_optimization_history.py

### Implementation for User Story 3

- [X] T035 [US3] Add repository methods for OptimizationRun CRUD in src/database/repositories/optimization_repository.py
- [X] T036 [US3] Implement save_to_database() on job completion in src/services/optimization_job_service.py
- [X] T037 [US3] Add history endpoints to src/api/routes/optimizer.py (GET /history, GET /history/{id})
- [X] T038 [US3] Add MCP tools: list_optimization_runs, get_optimization_run in src/mcp/server.py
- [X] T039 [US3] Integration test for persistence across restart in tests/integration/test_optimization_history.py

**Checkpoint**: User Story 3 complete - optimization history persisted

---

## Phase 6: User Story 4 - SSE Event Stream (Priority: P2)

**Goal**: Real-time SSE notifications for job progress and completion

**Independent Test**: Connect to /events/stream → start optimization → receive job_progress and job_complete events

### Tests for User Story 4

- [X] T040 [P] [US4] Unit test for SSE event emission in tests/unit/test_sse_events.py
- [X] T041 [P] [US4] Unit test for event sequence numbering in tests/unit/test_sse_events.py

### Implementation for User Story 4

- [X] T042 [US4] Create SSE routes file src/api/routes/events.py
- [X] T043 [US4] Implement /events/stream SSE endpoint with EventSourceResponse in src/api/routes/events.py
- [X] T044 [US4] Implement /events/since/{timestamp} polling endpoint in src/api/routes/events.py
- [X] T045 [US4] Create SSEEventEmitter service in src/services/sse_event_service.py
- [X] T046 [US4] Integrate SSE emission into optimization worker (job_started, job_progress, job_complete, job_failed) in src/services/optimization_job_service.py
- [X] T047 [US4] Register events router in src/api/main.py
- [X] T048 [US4] Integration test for SSE event delivery in tests/integration/test_optimization_sse.py

**Checkpoint**: User Story 4 complete - SSE notifications working

---

## Phase 7: User Story 5 - Price Level Configuration (Priority: P2)

**Goal**: Set price alerts for positions, receive SSE events when price crosses levels

**Independent Test**: Set alert → price crosses level → receive price_alert SSE event

### Tests for User Story 5

- [X] T049 [P] [US5] Unit test for set_price_alert() in tests/unit/test_price_alerts.py
- [X] T050 [P] [US5] Unit test for check_level_breach() in tests/unit/test_price_alerts.py
- [X] T051 [P] [US5] Unit test for alert cleanup on position close in tests/unit/test_price_alerts.py

### Implementation for User Story 5

- [X] T052 [US5] Create PriceAlertService in src/services/price_alert_service.py
- [X] T053 [US5] Implement set_alert() with Redis cache in src/services/price_alert_service.py
- [X] T054 [US5] Implement get_alerts_for_ticket() in src/services/price_alert_service.py
- [X] T055 [US5] Implement clear_alerts_for_ticket() in src/services/price_alert_service.py
- [X] T056 [US5] Implement monitor_loop() with 5s polling in src/services/price_alert_service.py
- [X] T057 [US5] Integrate SSE emission on price_alert trigger in src/services/price_alert_service.py
- [X] T058 [US5] Add price alert endpoints to src/api/routes/alerts.py (POST /alerts, GET /alerts, DELETE /alerts/{id})
- [X] T059 [US5] Add batch alert endpoint POST /alerts/batch in src/api/routes/alerts.py
- [X] T060 [US5] Add position-specific endpoints in src/api/routes/alerts.py (GET /alerts/position/{ticket}, DELETE /alerts/position/{ticket})
- [X] T061 [US5] Register alerts router in src/api/main.py
- [X] T062 [US5] Add MCP tools: set_price_alerts, get_position_alerts, clear_position_alerts in src/mcp/server.py
- [X] T063 [US5] Start price alert monitoring on API startup in src/api/main.py
- [X] T064 [US5] Integration test for price alert lifecycle in tests/integration/test_price_alerts.py

**Checkpoint**: User Story 5 complete - price alerts working with SSE

---

## Phase 8: User Story 6 - Autonomous Position Monitoring (Priority: P3)

**Goal**: Detect significant events (fast moves, liquidity sweeps) and generate alerts

**Independent Test**: Open position → simulate fast move → receive fast_move alert

### Tests for User Story 6

- [X] T065 [P] [US6] Unit test for detect_fast_move() in tests/unit/test_autonomous_monitoring.py
- [X] T066 [P] [US6] Unit test for detect_liquidity_sweep() in tests/unit/test_autonomous_monitoring.py

### Implementation for User Story 6

- [X] T067 [US6] Add fast_move detection (>2× ATR in 5 min) to PriceAlertService in src/services/price_alert_service.py
- [X] T068 [US6] Add liquidity_sweep detection pattern in src/services/price_alert_service.py
- [X] T069 [US6] Add suggestion logging (no auto-execution) in src/services/price_alert_service.py
- [X] T070 [US6] Integration test for autonomous monitoring in tests/integration/test_autonomous_monitoring.py

**Checkpoint**: User Story 6 complete - autonomous monitoring functional

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T071 [P] Update quickstart.md with actual test commands in specs/008-async-optimization-sse/quickstart.md
- [X] T072 [P] Add error handling for Redis unavailable (fallback to sync) in src/services/optimization_job_service.py
- [X] T073 [P] Add logging throughout all new services
- [X] T074 Run full test suite: `pytest tests/unit/ tests/integration/ -v`
- [X] T075 Update CLAUDE.md with new MCP tools documentation

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ──► Phase 2 (Foundational) ──┬──► Phase 3 (US1) ──► Phase 4 (US2)
                                             │                          │
                                             │                          ▼
                                             │                    Phase 5 (US3)
                                             │                          │
                                             │                          ▼
                                             └──────────────────► Phase 6 (US4)
                                                                       │
                                                                       ▼
                                                                 Phase 7 (US5)
                                                                       │
                                                                       ▼
                                                                 Phase 8 (US6)
                                                                       │
                                                                       ▼
                                                                 Phase 9 (Polish)
```

### User Story Dependencies

| Story | Depends On | Can Start After |
|-------|------------|-----------------|
| US1 (Async Job Queue) | Foundational | Phase 2 complete |
| US2 (Deterministic Grid) | US1 | Phase 3 complete |
| US3 (History Persistence) | US1 | Phase 3 complete (or parallel with US2) |
| US4 (SSE Events) | Foundational | Phase 2 complete (or after US1 for integration) |
| US5 (Price Alerts) | US4 | Phase 6 complete |
| US6 (Autonomous Monitoring) | US5 | Phase 7 complete |

### Within Each User Story

1. Tests written and FAIL first (T0xx tests)
2. Core service implementation
3. API endpoints
4. MCP tools
5. Integration tests
6. Checkpoint validation

### Parallel Opportunities

**Phase 1 (all [P] tasks):**
- T002, T003 can run in parallel

**Phase 2 (models):**
- T005, T006 can run in parallel

**Phase 3 (US1 tests):**
- T010, T011, T012 can run in parallel

**Phase 4 (US2 tests):**
- T024, T025, T026 can run in parallel

**Phase 5 (US3 tests):**
- T032, T033, T034 can run in parallel

**Phase 6 (US4 tests):**
- T040, T041 can run in parallel

**Phase 7 (US5 tests):**
- T049, T050, T051 can run in parallel

**Phase 8 (US6 tests):**
- T065, T066 can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests together:
Task: "Unit test for job submission in tests/unit/test_optimization_job.py"
Task: "Unit test for job status retrieval in tests/unit/test_optimization_job.py"
Task: "Unit test for job cancellation in tests/unit/test_optimization_job.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (Async Job Queue)
4. Complete Phase 4: User Story 2 (Deterministic Grid)
5. Complete Phase 5: User Story 3 (History Persistence)
6. **STOP and VALIDATE**: Test US1-3 independently - MCP optimization works!
7. Deploy/demo MVP

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Async jobs work → First value!
3. Add US2 → Deterministic grid → Reproducible results
4. Add US3 → History saved → Complete P1 scope
5. Add US4 → SSE events → Real-time updates
6. Add US5 → Price alerts → Position monitoring
7. Add US6 → Autonomous alerts → Full feature

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story is independently testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story
- US1 + US2 + US3 = MVP (core functionality without real-time updates)
