# Implementation Plan: Dashboard API Service

**Branch**: `002-fastapi-dashboard-api` | **Date**: 2025-11-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-fastapi-dashboard-api/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build a comprehensive FastAPI service to serve market data, price forecasts, account information, and strategy allocations from PostgreSQL database to React dashboard with real-time MT4 integration. The API will provide REST endpoints for historical data retrieval and WebSocket/SSE for real-time updates, ensuring sub-2 second response times for chart data and supporting 50+ concurrent users.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.104.1, SQLAlchemy 2.0.23 (async), Pydantic 2.5.2, asyncpg 0.29.0, Redis 5.0.1, PyZMQ 25.1.2, Structlog 23.2.0, Prometheus-client 0.19.0
**Storage**: PostgreSQL 15+ (async with asyncpg driver), Redis 7+ (pub/sub for real-time updates)
**Testing**: pytest 7.4.3, pytest-asyncio 0.21.1, pytest-cov 4.1.0, pytest-mock 3.12.0
**Target Platform**: Linux server (Docker container), exposed on port 8003
**Project Type**: Web API (backend service for React dashboard)
**Performance Goals**:
- Historical chart data (500 candlesticks): <2 seconds response time
- Current market prices: <1 second page load
- Account balance updates: <3 seconds after MT4 execution
- Real-time price updates: <5 seconds latency from MT4 to dashboard
- Support 50+ concurrent users without degradation
- 95% of API requests complete successfully

**Constraints**:
- API latency target: <200ms p95 (constitution requirement III)
- Database connection pooling required to handle concurrent requests
- CORS must be configured for dashboard access from localhost:3000 and production domains
- All responses must conform to existing dashboard API contracts
- MT4 standard timeframe notation (M1, M5, M15, M30, H1, H4, D1, W1, MN1)

**Scale/Scope**:
- 90 days historical data retention minimum
- Endpoints for 9 key entities (MarketData, Indicators, Account, Position, Trade, Forecast, Strategy, StrategyAllocation, StrategyPerformance)
- 7 route modules (market_data, trading, forecasts, strategies, performance, agents, system)
- Real-time streaming via WebSocket or Server-Sent Events (SSE) - requires Phase 0 research decision
- Integration with MT4 service via Redis pub/sub or ZeroMQ

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development (NON-NEGOTIABLE)
**Status**: ✅ **COMPLIANT**
- All API endpoints will have tests written FIRST following TDD red-green-refactor cycle
- Contract tests will verify API response schemas match dashboard expectations
- Integration tests will verify database queries and real-time streaming
- Unit tests for business logic in service layer with 85%+ coverage target
- Tests will be created before implementation begins (Phase 2 implementation)

### II. Security-First Design
**Status**: ⚠️ **PARTIAL - SECURITY GAPS ACKNOWLEDGED**
- **MT4 Connection Encryption**: NOT IN SCOPE for this feature (covered in 001-mt4-integration)
- **API Authentication**: ❌ NOT IMPLEMENTED YET - This feature focuses on API structure; authentication will be added in Phase 8-9 per FINAL_BUILD_PLAN.md
- **Rate Limiting**: ✅ ALREADY IMPLEMENTED - slowapi middleware is active in main.py:106-107
- **Secrets Management**: ✅ COMPLIANT - Environment variables used for all sensitive configuration
- **Input Validation**: ✅ COMPLIANT - Pydantic models enforce schema validation for all requests

**Production Blocker**: API authentication (JWT + API key) MUST be implemented before live deployment. Currently planned for Phase 8-9 (Week 8-9) per project timeline.

### III. Observability & Monitoring
**Status**: ✅ **COMPLIANT**
- Structured logging with structlog already configured (main.py:32, all route files use logger)
- Prometheus metrics endpoint mounted at /metrics (main.py:119-121)
- LoggingMiddleware and MetricsMiddleware active (main.py:99-100)
- All API operations log errors with context (symbol, error details, exc_info)
- Performance target: <200ms p95 API latency aligns with constitution requirement
- Health check endpoint exists at /health (main.py:143-160)

**Action Required**: Ensure distributed tracing (Jaeger) integration is added for request correlation across services

### IV. Agent Autonomy with Guardrails
**Status**: ✅ **COMPLIANT**
- API serves as read-only data interface - no trading decisions made at API layer
- Integration with agent system via agent coordinator (dependencies.py init_agent_coordinator)
- Agents operate independently; API provides observability through /api/agents/* endpoints
- Circuit breakers and risk limits enforced at agent and service layers (not API responsibility)

### V. Paper Trading Before Live Trading
**Status**: ✅ **COMPLIANT (NOT APPLICABLE)**
- This is a data serving API with no trading execution capabilities
- Read-only operations: market data retrieval, account viewing, forecast display
- Trading execution out of scope (spec.md line 214-215)
- No strategy modification via API (spec.md line 216)

### VI. Repository Pattern & Service Layer
**Status**: ✅ **COMPLIANT**
- Repository pattern already established at `src/database/repositories/`
- Service layer at `src/services/` separates business logic from API routes
- Async SQLAlchemy 2.0+ operations (main.py dependencies, routes use AsyncSession)
- API routes orchestrate through services/repositories, no direct ORM in routes
- Database models defined at `src/database/models/` with proper abstractions

### VII. Event-Driven Agent Communication
**Status**: ✅ **COMPLIANT**
- API integrates with MCP server via agent coordinator
- Real-time updates will use Redis pub/sub or WebSocket (research.md will determine approach)
- API does not directly communicate with agents - goes through MCP server
- Streaming endpoints (market_data.py:214-281) will integrate with MarketDataAgent via events

### VIII. Version Control & Backward Compatibility
**Status**: ✅ **COMPLIANT**
- Database migrations use Alembic with reversible migrations
- API endpoints will maintain backward compatibility through versioning if needed
- Breaking changes require migration path and deprecation notice
- Pydantic models provide schema versioning capabilities

---

### Pre-Production Blockers (From Constitution)

| Blocker | Status | This Feature | Plan |
|---------|--------|--------------|------|
| MT4 Connection Encryption | ❌ Not Implemented | Out of Scope | Covered in 001-mt4-integration |
| API Authentication & Authorization | ❌ Not Implemented | **DEFERRED** | Phase 8-9 (Week 8-9) per FINAL_BUILD_PLAN.md |
| Rate Limiting | ✅ Implemented | In Scope | Already active via slowapi |
| Secrets Management | ✅ Implemented | In Scope | Environment variables in use |

**GATE VERDICT**: ✅ **PASS WITH SECURITY DEFERRAL**

Justification: API authentication is explicitly deferred to Phase 8-9 per the project's phased rollout plan (RiseTrader_FINAL_BUILD_PLAN.md). This feature (002-fastapi-dashboard-api) is Phase 2 work focused on API structure and data serving. Authentication will be added before production deployment in Week 8-9.

All other principles compliant. Test-first development will be enforced during implementation. Observability instrumentation is present. Repository pattern is followed.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── api/                         # FastAPI application (THIS FEATURE)
│   ├── routes/                 # API endpoint handlers
│   │   ├── market_data.py      # Market data endpoints
│   │   ├── trading.py          # Trading account & positions endpoints
│   │   ├── forecasts.py        # Price forecast endpoints
│   │   ├── strategies.py       # Strategy allocation endpoints
│   │   ├── performance.py      # Performance metrics endpoints
│   │   ├── agents.py           # Agent status endpoints
│   │   └── system.py           # Health & system endpoints
│   ├── models/                 # Pydantic request/response models
│   ├── middleware/             # Custom middleware (logging, metrics, exceptions)
│   ├── main.py                 # Application entry point
│   ├── config.py               # Settings and configuration
│   └── dependencies.py         # Dependency injection helpers
│
├── database/                    # Database layer (EXISTING)
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── market_data.py      # MarketData entity
│   │   ├── indicators.py       # Indicators entity
│   │   ├── account.py          # Account entity
│   │   ├── positions.py        # Position entity
│   │   ├── trading_history.py  # Trade entity
│   │   ├── forecasts.py        # Forecast entity
│   │   └── ...                 # Other entities
│   ├── repositories/           # Repository pattern implementations
│   │   ├── market_data_repository.py
│   │   ├── trading_repository.py
│   │   ├── forecast_repository.py
│   │   └── ...
│   └── migrations/             # Alembic database migrations
│
├── services/                    # Business logic layer (EXISTING)
│   ├── market_data_service.py
│   ├── trading_service.py
│   ├── forecast_service.py
│   └── mt4_integration_service.py
│
├── agents/                      # Agent system (EXISTING - integration point)
│   ├── mcp_server.py
│   └── ...
│
├── monitoring/                  # Observability (EXISTING)
│   └── metrics.py
│
└── utils/                       # Shared utilities (EXISTING)
    └── ...

tests/
├── contract/                    # API contract tests (THIS FEATURE)
│   ├── test_market_data_schemas.py
│   ├── test_trading_schemas.py
│   └── ...
├── integration/                 # Integration tests (THIS FEATURE)
│   ├── test_market_data_api.py
│   ├── test_trading_api.py
│   ├── test_real_time_streaming.py
│   └── ...
└── unit/                        # Unit tests (THIS FEATURE)
    ├── api/
    │   ├── test_market_data_route.py
    │   └── ...
    ├── services/
    │   ├── test_market_data_service.py
    │   └── ...
    └── repositories/
        └── ...
```

**Structure Decision**:

This project follows **Option 1 (Single Project)** structure with a well-established layered architecture already in place:

1. **API Layer** (`src/api/`): FastAPI routes, Pydantic models, middleware - THIS FEATURE extends existing structure
2. **Service Layer** (`src/services/`): Business logic orchestration - Some services exist, will add/enhance for this feature
3. **Repository Layer** (`src/database/repositories/`): Data access abstraction - Existing repositories will be used/enhanced
4. **Database Models** (`src/database/models/`): SQLAlchemy ORM models - Already exist for most entities
5. **Agent System** (`src/agents/`): Integration point for real-time updates via MCP server

**Key Integration Points for This Feature**:
- Extend existing `src/api/routes/` with enhanced endpoints
- Utilize existing `src/database/repositories/` for data access
- Integrate with `src/services/mt4_integration_service.py` for real-time updates
- Connect to agent system via `src/agents/mcp_server.py` for streaming data
- Add comprehensive test coverage in `tests/contract/`, `tests/integration/`, `tests/unit/`

**Real-time Streaming Architecture** (to be finalized in Phase 0 research.md):
- Option A: FastAPI WebSocket endpoint in `src/api/routes/streaming.py`
- Option B: Server-Sent Events (SSE) endpoint for unidirectional updates
- Integration: Subscribe to Redis pub/sub or MCP server events → push to dashboard clients

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| API Authentication Deferred | Project follows phased rollout: Phase 2 (API structure), Phase 8-9 (security hardening) | Implementing auth now would block core functionality development; auth requires complete API surface to secure; team resources focused on foundational features first per FINAL_BUILD_PLAN.md timeline |

**No other violations**. All constitution principles are followed or have justified deferrals aligned with project timeline.

---

## Post-Design Constitution Re-Evaluation

*Re-checked after Phase 1 design (research.md, data-model.md, contracts/ complete)*

### Changes After Design Phase

**Research Decisions Made**:
1. ✅ **Real-time Technology**: Server-Sent Events (SSE) selected over WebSocket
2. ✅ **MT4 Integration**: Redis Pub/Sub selected over direct ZeroMQ
3. ✅ **Database Optimization**: Composite indexes + keyset pagination
4. ✅ **Caching Strategy**: Redis caching with TTL + event-driven invalidation

**Design Artifacts Created**:
- `research.md`: All technical unknowns resolved
- `data-model.md`: 9 entities defined (6 exist, 3 new)
- `contracts/openapi-spec.yaml`: Complete OpenAPI 3.0 specification
- `quickstart.md`: Developer setup and testing guide

### Re-Evaluation Against Constitution

#### I. Test-First Development ✅ **STILL COMPLIANT**
- Tests will be written FIRST in Phase 2 implementation (per `/speckit.tasks` command)
- Contract tests will validate OpenAPI spec conformance
- Integration tests for SSE streaming, Redis caching, database queries
- Unit tests for service layer, repositories, route handlers
- Target: 85%+ coverage

#### II. Security-First Design ⚠️ **STILL PARTIAL (NO CHANGE)**
- Authentication deferred to Phase 8-9 - unchanged from initial evaluation
- Rate limiting active (slowapi) - verified in existing code
- Input validation via Pydantic - design confirmed
- Secrets management via environment variables - confirmed in quickstart.md

#### III. Observability & Monitoring ✅ **ENHANCED BY DESIGN**
- Structured logging confirmed in implementation plan
- Prometheus metrics endpoint confirmed
- **Action Item Addressed**: Distributed tracing (Jaeger) to be added in Phase 8-9 alongside authentication
- Performance targets validated in OpenAPI spec and success criteria

#### IV. Agent Autonomy with Guardrails ✅ **STILL COMPLIANT**
- API is read-only data interface - confirmed in design
- Agent integration via Redis Pub/Sub (event-driven) - research.md decision
- No trading decisions at API layer

#### V. Paper Trading Before Live Trading ✅ **STILL COMPLIANT (N/A)**
- Read-only API, no trading execution

#### VI. Repository Pattern & Service Layer ✅ **VALIDATED IN DESIGN**
- Repository pattern confirmed in data-model.md
- Existing repositories to be used (market_data_repository.py, trading_repository.py)
- New repositories needed for Strategy entities
- Service layer orchestration confirmed in architecture

#### VII. Event-Driven Agent Communication ✅ **STRENGTHENED BY DESIGN**
- **Research Decision**: Redis Pub/Sub selected for MT4 integration
- SSE endpoints subscribe to Redis channels (event-driven)
- Event schema standardized in data-model.md
- No direct MT4 coupling - API subscribes to events via Redis

#### VIII. Version Control & Backward Compatibility ✅ **STILL COMPLIANT**
- API versioning via OpenAPI spec (v1.0.0)
- Keyset pagination maintains backward compatibility
- Database migrations use Alembic (reversible)

---

### Design Validation Summary

| Principle | Initial Status | Post-Design Status | Change |
|-----------|----------------|-------------------|--------|
| I. Test-First | ✅ Compliant | ✅ Compliant | None - Tests planned for Phase 2 |
| II. Security-First | ⚠️ Partial | ⚠️ Partial | None - Auth deferred to Phase 8-9 |
| III. Observability | ✅ Compliant | ✅ Enhanced | Tracing plan clarified |
| IV. Agent Guardrails | ✅ Compliant | ✅ Compliant | None |
| V. Paper Trading | ✅ N/A | ✅ N/A | None |
| VI. Repository Pattern | ✅ Compliant | ✅ Validated | Design confirms architecture |
| VII. Event-Driven | ✅ Compliant | ✅ Strengthened | Redis Pub/Sub decision |
| VIII. Version Control | ✅ Compliant | ✅ Compliant | None |

**GATE VERDICT (POST-DESIGN)**: ✅ **PASS - DESIGN STRENGTHENS COMPLIANCE**

Research decisions align with constitution principles. Event-driven architecture (VII) strengthened by Redis Pub/Sub choice. Repository pattern (VI) validated in data model design. All design artifacts complete and compliant.

**Ready for Phase 2 Implementation** (via `/speckit.tasks` command to generate tasks.md)
