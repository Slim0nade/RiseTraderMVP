# Requirements Checklist: 008-async-optimization-sse

## User Stories

| Priority | Story | Status |
|----------|-------|--------|
| P1 | US1 - Async Optimization Job Queue | ⬜ Not Started |
| P1 | US2 - Deterministic Grid Search | ⬜ Not Started |
| P1 | US3 - Optimization History Persistence | ⬜ Not Started |
| P2 | US4 - SSE Event Stream for MCP | ⬜ Not Started |
| P2 | US5 - Price Level Configuration | ⬜ Not Started |
| P3 | US6 - Autonomous Position Monitoring | ⬜ Not Started |

## Functional Requirements

### R1: Async Job Queue

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Return job_id within 2 seconds | ⬜ |
| FR-002 | Persist job state to Redis (24h TTL) | ⬜ |
| FR-003 | MCP tools: optimize_strategy, get_optimization_status, get_optimization_results, cancel_optimization, list_active_jobs | ⬜ |
| FR-004 | Background worker process for job execution | ⬜ |
| FR-005 | Handle worker crashes with job state recovery | ⬜ |

### R2: Deterministic Grid Search

| ID | Requirement | Status |
|----|-------------|--------|
| FR-006 | Test ALL parameter combinations (no random sampling) | ⬜ |
| FR-007 | Produce identical results for identical inputs | ⬜ |
| FR-008 | Report progress as combinations_tested / total_combinations | ⬜ |
| FR-009 | Limit grid size to 10,000 combinations max | ⬜ |

### R3: Optimization History

| ID | Requirement | Status |
|----|-------------|--------|
| FR-010 | Create optimization_runs table with JSONB columns | ⬜ |
| FR-011 | Persist all results to database on completion | ⬜ |
| FR-012 | Query endpoints: list_optimization_runs, get_optimization_run | ⬜ |

### R4: SSE Event Stream

| ID | Requirement | Status |
|----|-------------|--------|
| FR-013 | /events/stream SSE endpoint | ⬜ |
| FR-014 | Emit events: job_started, job_progress, job_complete, job_failed, price_alert | ⬜ |
| FR-015 | Include timestamp and sequence number | ⬜ |
| FR-016 | /events/since/{timestamp} for missed events | ⬜ |

### R5: Price Level Configuration

| ID | Requirement | Status |
|----|-------------|--------|
| FR-017 | set_price_alerts MCP tool | ⬜ |
| FR-018 | Monitor levels with ≤5s polling | ⬜ |
| FR-019 | Emit SSE event on level breach | ⬜ |
| FR-020 | Clean up alerts when positions close | ⬜ |

### R6: Autonomous Monitoring (Phase 2)

| ID | Requirement | Status |
|----|-------------|--------|
| FR-021 | Detect fast moves (>2× ATR in 5 min) | ⬜ |
| FR-022 | Detect liquidity sweep patterns | ⬜ |
| FR-023 | Log suggestions without auto-execution | ⬜ |

## Success Criteria

| ID | Criterion | Status |
|----|-----------|--------|
| SC-001 | MCP optimize_strategy returns within 2 seconds | ⬜ |
| SC-002 | All parameter combinations tested (0 random sampling) | ⬜ |
| SC-003 | Results persist across API restarts | ⬜ |
| SC-004 | SSE events delivered within 1 second | ⬜ |
| SC-005 | Price alerts trigger within 5 seconds | ⬜ |
| SC-006 | Handle 10 concurrent optimization jobs | ⬜ |

## Legend

- ⬜ Not Started
- 🔄 In Progress
- ✅ Complete
- ❌ Blocked
