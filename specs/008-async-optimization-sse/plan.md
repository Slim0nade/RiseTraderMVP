# Implementation Plan: Async Optimization Engine with SSE Notifications

**Branch**: `008-async-optimization-sse` | **Date**: 2026-01-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-async-optimization-sse/spec.md`

## Summary

Build an async job queue system for long-running strategy optimizations using Redis, with SSE (Server-Sent Events) for real-time progress notifications. Replace random parameter sampling with deterministic grid search, persist optimization history to PostgreSQL, and add price alert monitoring for open positions.

## Technical Context

**Language/Version**: Python 3.11+ (existing stack)  
**Primary Dependencies**: FastAPI 0.104.1, aioredis 2.0+, SQLAlchemy 2.0+ async, sse-starlette  
**Storage**: PostgreSQL 15+ (existing), Redis 7+ (existing)  
**Testing**: pytest with pytest-asyncio  
**Target Platform**: Linux server (Docker containers)
**Project Type**: web (backend API + frontend dashboard)  
**Performance Goals**: Job submission <2s, SSE latency <1s, handle 10 concurrent jobs  
**Constraints**: MCP tool timeout 2min (jobs must be async), max 10,000 grid combinations  
**Scale/Scope**: Single background worker, ~100 optimizations/day, 24h job retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution is a template without specific gates defined. Applying general best practices:

| Gate | Status | Notes |
|------|--------|-------|
| Test-First | ✅ Pass | Will use TDD with pytest |
| Reuse Patterns | ✅ Pass | Uses existing Redis, BacktestRun, ParameterGrid models |
| Real Data | ✅ Pass | Connects to existing database and Redis |
| Clean Code | ✅ Pass | Extends existing services, no new major patterns |

## Project Structure

### Documentation (this feature)

```text
specs/008-async-optimization-sse/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
# Existing structure - extend with new files
src/
├── database/
│   └── models/
│       └── optimization.py       # NEW: OptimizationRun, PriceAlert models
├── services/
│   ├── optimization_job_service.py   # NEW: Job queue management
│   └── price_alert_service.py        # NEW: Price level monitoring
├── api/
│   └── routes/
│       ├── optimizer.py              # MODIFY: Add async MCP tools
│       └── events.py                 # NEW: SSE endpoint
└── mcp/
    └── server.py                     # MODIFY: Add async optimization tools

tests/
├── unit/
│   └── test_optimization_job.py      # NEW
├── integration/
│   └── test_optimization_sse.py      # NEW
```

**Structure Decision**: Extend existing web application structure. New service files for job queue and price alerts. New SSE route for events. Extends existing optimizer routes and MCP server.

## Complexity Tracking

> No violations - feature uses existing patterns (Redis, SQLAlchemy, FastAPI) with minimal new dependencies (sse-starlette).

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
