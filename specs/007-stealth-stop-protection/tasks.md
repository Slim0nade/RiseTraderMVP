# Tasks: Enhanced Stealth Stop Manager with Multi-Layer Risk Protection

**Input**: Design documents from `/specs/007-stealth-stop-protection/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Constitution requires TDD approach (85%+ coverage). Tests are included per spec requirements.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Summary

| Phase | Description | Task Count |
|-------|-------------|------------|
| Phase 1 | Setup | 5 |
| Phase 2 | Foundational | 8 |
| Phase 3 | User Story 1 - Disaster Protection (P1) | 10 |
| Phase 4 | User Story 2 - Profit Erosion (P2) | 8 |
| Phase 5 | User Story 3 - Early Trailing (P2) | 6 |
| Phase 6 | User Story 4 - Alerts & Monitoring (P3) | 6 |
| Phase 7 | Polish & Integration | 6 |
| **Total** | | **49** |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, configuration migration, and test infrastructure

- [X] T001 Create YAML configuration file `config/stealth_stops.yaml` from schema in specs/007-stealth-stop-protection/contracts/stealth_stops.yaml.schema
- [X] T002 [P] Create example configuration template `config/stealth_stops.yaml.example` with commented documentation
- [X] T003 [P] Add new dependencies to requirements.txt: pyyaml, jsonschema, watchdog (for hot-reload)
- [X] T004 [P] Create test fixtures directory `tests/fixtures/` with Jan 12-13 historical data file `historical_positions_jan_12_13.json`
- [X] T005 Create pytest configuration in `tests/conftest.py` for async test fixtures and mock MT4 client

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Configuration & Utilities

- [X] T006 Create `src/utils/atr_calculator.py` with ATRCalculator class implementing 14-period Wilder's smoothing, caching (60s TTL), and 2% fallback
- [X] T007 [P] Add unit tests for ATRCalculator in `tests/unit/utils/test_atr_calculator.py` covering calculation, caching, and fallback scenarios
- [X] T008 Enhance `DynamicTrailConfig` dataclass in `src/services/stealth_stop_manager.py` with new fields: disaster_stop_multiplier, erosion_threshold_atr, erosion_alert_threshold_atr, max_volatility_adjustment, atr_fallback_percentage, manual_override_grace_period
- [X] T009 [P] Create YAML configuration loader with schema validation in `src/services/stealth_stop_manager.py` (load_config_from_yaml function)
- [X] T010 [P] Add configuration hot-reload support using watchdog file observer (optional, can be deferred)

### Data Model Enhancements

- [X] T011 Enhance `MonitoredPosition` dataclass in `src/services/stealth_stop_manager.py` with new fields: profit_highwater, last_highwater_update, profit_erosion, disaster_stop_set, trailing_activated
- [X] T012 [P] Create `StopModificationRequest` dataclass in `src/services/stealth_stop_manager.py` with fields: request_id, ticket, timestamp, old_stop, new_stop, reason, status, attempt_count, next_retry_time, error_message
- [X] T013 [P] Create `ModificationReason` and `ModificationStatus` enums in `src/services/stealth_stop_manager.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Immediate Disaster Protection on Position Entry (Priority: P1) 🎯 MVP

**Goal**: Automatically set protective stop loss (3×ATR) within 10 seconds of detecting any new position

**Independent Test**: Open a new position in MT4 → verify disaster stop is set within 10 seconds

**Acceptance Criteria**:
- SC-001: No position remains unprotected for more than 10 seconds after opening
- SC-004: Stop loss modifications successfully applied to MT4 within 5 seconds

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US1] Create unit test `test_calculate_disaster_stop` in `tests/unit/services/test_stealth_stop_manager.py` for SHORT/LONG positions
- [X] T015 [P] [US1] Create unit test `test_disaster_stop_fallback_when_atr_unavailable` in `tests/unit/services/test_stealth_stop_manager.py`
- [X] T016 [P] [US1] Create integration test `test_disaster_stop_applied_on_detection` in `tests/integration/test_protection_scenarios.py` with mock MT4

### Implementation for User Story 1

- [X] T017 [US1] Implement `calculate_disaster_stop(position, atr)` method in `StealthStopManager` class in `src/services/stealth_stop_manager.py`
- [X] T018 [US1] Implement `apply_disaster_stop(position)` method that calls MT4Client.modify_order() in `src/services/stealth_stop_manager.py`
- [X] T019 [US1] Modify `sync_positions()` method to detect new positions (disaster_stop_set=False) and call apply_disaster_stop() in `src/services/stealth_stop_manager.py`
- [X] T020 [US1] Add minimum stop distance validation (0.5×ATR from current price) to prevent immediate trigger in `src/services/stealth_stop_manager.py`
- [X] T021 [US1] Add logging for disaster stop application: "Initial protection set: Ticket #X stop at $Y (3×ATR=$Z)" in `src/services/stealth_stop_manager.py`
- [X] T022 [US1] Verify all US1 tests pass with `pytest tests/ -k "US1 or disaster"` 
- [X] T023 [US1] Run manual verification: open position in MT4, confirm stop set within 10 seconds

**Checkpoint**: User Story 1 complete - positions are now always protected immediately

---

## Phase 4: User Story 2 - Profit Erosion Detection and Protection (Priority: P2)

**Goal**: Detect when profit erodes from highwater mark and automatically tighten stop to protect remaining gains

**Independent Test**: Create position that moves into profit then reverses → verify stop tightens when erosion > 0.5×ATR

**Acceptance Criteria**:
- SC-002: System detects and responds to profit erosion exceeding 0.5×ATR within one monitoring cycle (≤60 seconds)
- SC-006: System generates alerts for 100% of profit erosion events exceeding 0.3×ATR threshold
- SC-008: Positions reaching +$600 profit do not result in losses exceeding -$100

### Tests for User Story 2

- [X] T024 [P] [US2] Create unit test `test_profit_highwater_tracking` in `tests/unit/services/test_stealth_stop_manager.py`
- [X] T025 [P] [US2] Create unit test `test_profit_erosion_detection` in `tests/unit/services/test_stealth_stop_manager.py`
- [X] T026 [P] [US2] Create integration test `test_jan_12_13_failure_prevention` in `tests/integration/test_protection_scenarios.py` using fixtures/historical_positions_jan_12_13.json

### Implementation for User Story 2

- [X] T027 [US2] Implement `update_profit_highwater(position)` method in `StealthStopManager` to track peak profit in `src/services/stealth_stop_manager.py`
- [X] T028 [US2] Implement `calculate_profit_erosion(position)` method in `StealthStopManager` in `src/services/stealth_stop_manager.py`
- [X] T029 [US2] Implement `check_profit_erosion(position, atr)` method with 0.3×ATR warning and 0.5×ATR protection triggers in `src/services/stealth_stop_manager.py`
- [X] T030 [US2] Modify `check_and_trail()` to call profit tracking and erosion detection on each monitoring cycle in `src/services/stealth_stop_manager.py`
- [X] T031 [US2] Verify all US2 tests pass including Jan 12-13 scenario replay (SC-008)

**Checkpoint**: User Story 2 complete - profit erosion is now detected and protected

---

## Phase 5: User Story 3 - Early Profit Locking with Reduced Thresholds (Priority: P2)

**Goal**: Begin trailing at 0.5×ATR profit (instead of 1.0×) and move to breakeven at 0.5×ATR (instead of 1.5×)

**Independent Test**: Create position that reaches 0.5×ATR profit → verify trailing activates immediately

**Acceptance Criteria**:
- SC-003: Positions reaching 0.5×ATR profit automatically activate trailing stops within one monitoring cycle
- SC-010: Soft breakeven protection activates for 95%+ of positions that reach 0.5×ATR profit

### Tests for User Story 3

- [X] T032 [P] [US3] Create unit test `test_early_trailing_activation_at_half_atr` in `tests/unit/services/test_stealth_stop_manager.py`
- [X] T033 [P] [US3] Create unit test `test_soft_breakeven_at_half_atr` in `tests/unit/services/test_stealth_stop_manager.py`

### Implementation for User Story 3

- [X] T034 [US3] Modify `calculate_trail_stop()` to use new trail_trigger_atr (0.5) instead of hardcoded 1.0 in `src/services/stealth_stop_manager.py`
- [X] T035 [US3] Modify breakeven logic to use breakeven_trigger_atr (0.5) instead of hardcoded 1.5 in `src/services/stealth_stop_manager.py`
- [X] T036 [US3] Add trailing_activated flag update when trailing first activates in `src/services/stealth_stop_manager.py`
- [X] T037 [US3] Verify all US3 tests pass with `pytest tests/ -k "US3 or early or trailing"`

**Checkpoint**: User Story 3 complete - trailing activates earlier to protect smaller wins

---

## Phase 6: User Story 4 - Comprehensive Alert and Monitoring System (Priority: P3)

**Goal**: Log all protection actions with structured logging and generate alerts for important events

**Independent Test**: Trigger various protection scenarios → verify appropriate logs/alerts are generated

**Acceptance Criteria**:
- SC-007: Trader receives clear, actionable log entries for all automated stop modifications including reason and profit impact

### Tests for User Story 4

- [X] T038 [P] [US4] Create unit test `test_protection_event_logging` in `tests/unit/services/test_stealth_stop_manager.py`
- [X] T039 [P] [US4] Create unit test `test_stop_modification_retry_with_backoff` in `tests/unit/services/test_stealth_stop_manager.py`

### Implementation for User Story 4

- [X] T040 [US4] Implement comprehensive structured logging using structlog for all protection actions in `src/services/stealth_stop_manager.py`
- [X] T041 [US4] Implement exponential backoff retry logic (1s, 2s, 4s, 8s, max 30s) for failed stop modifications in `src/services/stealth_stop_manager.py`
- [X] T042 [US4] Add Prometheus metrics for stealth stop operations (positions_monitored, disaster_stops_set_total, erosion_warnings_total, etc.) in `src/services/stealth_stop_manager.py`
- [X] T043 [US4] Verify all US4 tests pass with `pytest tests/ -k "US4 or logging or alert"`

**Checkpoint**: User Story 4 complete - all protection actions are logged and auditable

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, documentation, and validation

- [X] T044 [P] Run full test suite with coverage: `pytest --cov=src/services/stealth_stop_manager --cov=src/utils/atr_calculator --cov-report=html`
- [X] T045 [P] Verify coverage ≥ 85% for all new code
- [X] T046 Update docstrings for all new/modified methods in `src/services/stealth_stop_manager.py`
- [X] T047 [P] Create migration guide documenting changes from stealth_stops.json to stealth_stops.yaml
- [X] T048 Run quickstart.md validation scenarios to confirm all features work end-to-end
- [X] T049 Update branch reference in plan.md from `001-stealth-stop-protection` to `007-stealth-stop-protection`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup → No dependencies, can start immediately
    ↓
Phase 2: Foundational → Depends on Setup (Phase 1)
    ↓                    BLOCKS all user stories
    ↓
Phase 3-6: User Stories → All depend on Foundational (Phase 2)
    │                     Can proceed in PARALLEL after Phase 2
    ├── US1 (P1): Disaster Protection  ──┐
    ├── US2 (P2): Profit Erosion       ──┼── Independent stories
    ├── US3 (P2): Early Trailing       ──┤   (can run in parallel)
    └── US4 (P3): Alerts               ──┘
    ↓
Phase 7: Polish → Depends on all desired user stories being complete
```

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories - **MVP DELIVERY POINT**
- **User Story 2 (P2)**: Uses profit_highwater tracking (added in Foundational), integrates with US1 disaster stops
- **User Story 3 (P2)**: Modifies trailing logic, independent of US2
- **User Story 4 (P3)**: Cross-cutting logging, can be developed in parallel with US2/US3

### Within Each User Story

1. Tests MUST be written and FAIL before implementation
2. Core logic before integration
3. Verification step at end of each story

### Parallel Opportunities

**Phase 2 Parallel Tasks**:
- T007, T009, T010, T012, T013 can run in parallel

**All User Story Tests in Parallel**:
- T014, T015, T016 (US1 tests)
- T024, T025, T026 (US2 tests)
- T032, T033 (US3 tests)
- T038, T039 (US4 tests)

**Cross-Story Parallelism** (with multiple developers):
- Developer A: US1 (Disaster Stops)
- Developer B: US3 (Early Trailing) + US4 (Alerts)
- After US1 complete: Developer A takes US2 (Profit Erosion)

---

## Parallel Example: Phase 2 Foundational

```bash
# Launch all parallel foundational tasks together:
Task T007: "Add unit tests for ATRCalculator in tests/unit/utils/test_atr_calculator.py"
Task T009: "Create YAML configuration loader with schema validation"
Task T010: "Add configuration hot-reload support using watchdog"
Task T012: "Create StopModificationRequest dataclass"
Task T013: "Create ModificationReason and ModificationStatus enums"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T013)
3. Complete Phase 3: User Story 1 (T014-T023)
4. **STOP and VALIDATE**: Test US1 independently
5. Deploy/demo if ready - **positions are now protected!**

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test → Deploy (**MVP: Disaster Protection**)
3. Add User Story 2 → Test → Deploy (Profit Erosion)
4. Add User Story 3 → Test → Deploy (Early Trailing)
5. Add User Story 4 → Test → Deploy (Full Logging)

### Recommended Order (Single Developer)

1. Phase 1: Setup (T001-T005) - 30 min
2. Phase 2: Foundational (T006-T013) - 2 hours
3. Phase 3: US1 - Disaster Protection (T014-T023) - 2 hours **← MVP**
4. Phase 5: US3 - Early Trailing (T032-T037) - 1 hour
5. Phase 4: US2 - Profit Erosion (T024-T031) - 2 hours
6. Phase 6: US4 - Alerts (T038-T043) - 1 hour
7. Phase 7: Polish (T044-T049) - 1 hour

**Total Estimated Time: ~10 hours**

---

## Success Validation

After implementation, these success criteria must pass:

| ID | Criteria | Test |
|----|----------|------|
| SC-001 | No position unprotected > 10s | T016, T023 |
| SC-002 | Erosion response within 60s | T026, T031 |
| SC-003 | Trailing at 0.5×ATR profit | T032, T037 |
| SC-004 | Stop modification < 5s | T016 |
| SC-006 | 100% erosion alerts | T024, T038 |
| SC-007 | Clear log entries | T038, T040 |
| SC-008 | +$600 → max -$100 loss | T026 (Jan 12-13 replay) |
| SC-010 | 95%+ breakeven activation | T033 |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Branch: `007-stealth-stop-protection`
