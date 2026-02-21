# Feature Specification: Async Optimization Engine with SSE Notifications

**Feature Branch**: `008-async-optimization-sse`  
**Created**: 2026-01-17  
**Status**: Draft  
**Input**: User description: "Async job queue for long-running optimizations, SSE event stream for real-time updates, deterministic grid search, price level alerts"

## Problem Statement

The current optimization system has several critical limitations:
1. **MCP Tool Timeouts**: Long-running optimizations (1-10+ minutes) cause MCP tool timeouts
2. **Random Sampling**: Current optimizer uses random sampling instead of exhaustive grid search
3. **No History Persistence**: Optimization results are not stored in the database
4. **No Real-time Updates**: Users must manually poll for optimization status
5. **No Price Alerts**: No way to monitor open positions for key price levels (liquidity sweeps, breakeven)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Async Optimization Job Queue (Priority: P1)

As a trader, I want to start a long-running optimization and get results later, so that MCP tools don't timeout and I can continue working while optimizations run in the background.

**Why this priority**: This is the core blocker - MCP tools timeout after 2 minutes but optimizations take 10+ minutes. Without this, the optimization feature is unusable from Claude Code.

**Independent Test**: Can be fully tested by starting an optimization via MCP tool, immediately receiving a job_id, and later querying for results. Delivers value even without SSE notifications.

**Acceptance Scenarios**:

1. **Given** I call `optimize_strategy` MCP tool with valid parameters, **When** the optimization starts, **Then** the tool returns immediately (within 2 seconds) with a `job_id` and status `pending`

2. **Given** an optimization job is running, **When** I call `get_optimization_status(job_id)`, **Then** I receive progress info including `progress_pct`, `combinations_tested`, `total_combinations`, `best_params_so_far`

3. **Given** an optimization job has completed, **When** I call `get_optimization_results(job_id)`, **Then** I receive the full results including best parameters, all tested combinations, and performance metrics

4. **Given** an optimization job is stuck or taking too long, **When** I call `cancel_optimization(job_id)`, **Then** the job is cancelled and partial results are available

---

### User Story 2 - Deterministic Grid Search (Priority: P1)

As a trader, I want the optimizer to test ALL parameter combinations systematically, so that I can find the true optimal parameters without random sampling artifacts.

**Why this priority**: Random sampling means results are not reproducible and may miss the optimal configuration. This is critical for strategy validation.

**Independent Test**: Can be tested by running an optimization and verifying that `combinations_tested == total_combinations` and that results are identical across multiple runs with the same parameters.

**Acceptance Scenarios**:

1. **Given** a parameter grid with 100 combinations, **When** I run `optimize_strategy`, **Then** exactly 100 combinations are tested (no sampling, no skipping)

2. **Given** identical optimization parameters, **When** I run optimization twice, **Then** the results are identical (deterministic)

3. **Given** a grid with nested parameters (e.g., fast_period: [5,10,15], slow_period: [20,30,40]), **When** I view progress, **Then** I can see which specific combination is currently being tested

---

### User Story 3 - Optimization History Persistence (Priority: P1)

As a trader, I want all optimization runs to be saved to the database, so that I can review past results and compare different optimization runs.

**Why this priority**: Without persistence, optimization results are lost when the server restarts. This is essential for strategy development workflow.

**Independent Test**: Can be tested by running an optimization, restarting the API, and verifying results are still available via `list_optimization_runs`.

**Acceptance Scenarios**:

1. **Given** an optimization completes successfully, **When** I query the database, **Then** a record exists in `optimization_runs` table with all parameters and results

2. **Given** I have multiple past optimizations, **When** I call `list_optimization_runs(symbol, strategy)`, **Then** I receive a list of past runs with summary metrics

3. **Given** a specific optimization run, **When** I call `get_optimization_run(run_id)`, **Then** I receive the complete parameter grid tested and all results as JSONB

---

### User Story 4 - SSE Event Stream for MCP (Priority: P2)

As a trader using Claude Code, I want to receive real-time SSE events about jobs and positions, so that I can be notified when optimizations complete or positions hit key levels.

**Why this priority**: Improves UX but jobs can still be queried manually. Not strictly required for core functionality.

**Independent Test**: Can be tested by connecting to SSE endpoint, starting an optimization, and verifying events are received in real-time.

**Acceptance Scenarios**:

1. **Given** I connect to `/events/stream` SSE endpoint, **When** an optimization job completes, **Then** I receive an event with type `job_complete` and job details

2. **Given** I have price alerts configured, **When** a position crosses an alert level, **Then** I receive an event with type `price_alert` and position details

3. **Given** SSE connection drops, **When** I reconnect, **Then** I can query missed events via `get_events_since(timestamp)`

---

### User Story 5 - Price Level Configuration (Priority: P2)

As a trader, I want to set price alerts for my open positions (liquidity sweeps, breakeven, key levels), so that I get notified when price reaches these levels.

**Why this priority**: Enables proactive position monitoring without manual price checking. Complements the stealth stop system.

**Independent Test**: Can be tested by setting a price alert, waiting for price to cross the level, and verifying an alert is generated.

**Acceptance Scenarios**:

1. **Given** I call `set_price_alerts` MCP tool with ticket, liquidity_sweep_price, breakeven_price, and key_levels, **When** the configuration is saved, **Then** these levels are monitored continuously

2. **Given** price crosses a configured alert level, **When** the monitoring loop detects this, **Then** an SSE event is emitted with alert details

3. **Given** a position is closed, **When** the monitoring loop runs, **Then** associated price alerts are automatically cleaned up

---

### User Story 6 - Autonomous Position Monitoring (Priority: P3)

As a trader, I want the system to autonomously monitor my open positions and alert me about significant events (liquidity sweeps, fast moves, breakeven opportunities), so that I can take action when needed.

**Why this priority**: This is a Phase 2 enhancement that builds on the price alerts system. Can be deferred to a later iteration.

**Independent Test**: Can be tested by opening a position, configuring monitoring thresholds, and verifying alerts are generated when conditions are met.

**Acceptance Scenarios**:

1. **Given** a position is open and monitoring is enabled, **When** price moves more than 2× ATR in 5 minutes, **Then** a "fast_move" alert is generated

2. **Given** a position is in profit, **When** price sweeps a key liquidity level and reverses, **Then** a "liquidity_sweep" alert is generated

3. **Given** autonomous monitoring is enabled, **When** optimal entry/exit conditions are detected, **Then** suggestions are logged (not auto-executed)

---

### Edge Cases

- What happens when Redis is unavailable? System should fall back to synchronous execution with appropriate timeout warnings.
- How does system handle partially completed optimizations (server restart)? Job state should be marked as `failed` with partial results preserved.
- What happens when SSE client disconnects during optimization? Events should be queued and available via polling endpoint.
- How does system handle duplicate price alerts for the same level? Should deduplicate and only alert once.
- What happens when optimization parameters exceed memory limits? Should validate grid size before starting and reject if > 10,000 combinations.

## Requirements *(mandatory)*

### Functional Requirements

**Async Job Queue (R1)**
- **FR-001**: System MUST return a job_id within 2 seconds of starting an optimization
- **FR-002**: System MUST persist job state to Redis with TTL of 24 hours
- **FR-003**: System MUST provide MCP tools: `optimize_strategy` (async), `get_optimization_status`, `get_optimization_results`, `cancel_optimization`, `list_active_jobs`
- **FR-004**: System MUST support background worker process for job execution
- **FR-005**: System MUST handle worker crashes gracefully with job state recovery

**Deterministic Grid Search (R2)**
- **FR-006**: System MUST test ALL parameter combinations without random sampling
- **FR-007**: System MUST produce identical results for identical inputs (deterministic)
- **FR-008**: System MUST report progress as `combinations_tested / total_combinations`
- **FR-009**: System MUST limit grid size to 10,000 combinations maximum

**Optimization History (R3)**
- **FR-010**: System MUST create `optimization_runs` table with columns: id, strategy, symbol, timeframe, start_date, end_date, param_grid (JSONB), results (JSONB), status, created_at, completed_at
- **FR-011**: System MUST persist all optimization results to database on completion
- **FR-012**: System MUST provide query endpoints: `list_optimization_runs`, `get_optimization_run`

**SSE Event Stream (R4)**
- **FR-013**: System MUST provide `/events/stream` SSE endpoint
- **FR-014**: System MUST emit events for: job_started, job_progress, job_complete, job_failed, price_alert
- **FR-015**: System MUST include event timestamp and sequence number for ordering
- **FR-016**: System MUST provide `/events/since/{timestamp}` for missed event recovery

**Price Level Configuration (R5)**
- **FR-017**: System MUST provide `set_price_alerts` MCP tool accepting ticket, alert levels
- **FR-018**: System MUST monitor configured levels with polling interval ≤ 5 seconds
- **FR-019**: System MUST emit SSE event when price crosses alert level
- **FR-020**: System MUST clean up alerts when positions are closed

**Autonomous Monitoring (R6 - Phase 2)**
- **FR-021**: System SHOULD detect fast moves (> 2× ATR in 5 min)
- **FR-022**: System SHOULD detect liquidity sweep patterns
- **FR-023**: System SHOULD log suggestions without auto-execution

### Key Entities

- **OptimizationJob**: Represents a running or completed optimization. Key attributes: job_id, status (pending/running/complete/failed/cancelled), progress_pct, param_grid, results, created_at
- **OptimizationRun**: Database record of a completed optimization. Key attributes: id, strategy, symbol, timeframe, date_range, param_grid (JSONB), results (JSONB)
- **PriceAlert**: A configured price level to monitor. Key attributes: ticket, alert_type, price_level, triggered, triggered_at
- **SSEEvent**: A real-time event. Key attributes: type, payload, timestamp, sequence

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: MCP `optimize_strategy` tool returns within 2 seconds (no timeout)
- **SC-002**: All parameter combinations are tested (0 random sampling)
- **SC-003**: Optimization results persist across API restarts
- **SC-004**: SSE events delivered within 1 second of occurrence
- **SC-005**: Price alerts trigger within 5 seconds of level breach
- **SC-006**: System handles 10 concurrent optimization jobs without degradation

## Out of Scope

- Auto-execution of trades based on monitoring (suggestions only)
- Multi-node worker distribution (single worker is sufficient)
- Historical SSE event replay beyond 24 hours
- WebSocket alternative to SSE (SSE is sufficient for MCP)

## Technical Notes

- Use Redis for job queue (already available in stack)
- Use asyncio background tasks for worker (avoid new dependencies)
- SSE endpoint should support multiple concurrent connections
- Database table should use JSONB for flexible param/result storage
- Integrate with existing backtesting infrastructure
