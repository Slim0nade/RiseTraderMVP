# Tasks: Dashboard API Service

**Feature**: 002-fastapi-dashboard-api
**Input**: Design documents from `/specs/002-fastapi-dashboard-api/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi-spec.yaml

**Tests**: ✅ **REQUIRED** - Constitution Principle I (Test-First Development) mandates TDD approach with 85%+ coverage target. Tests MUST be written FIRST and FAIL before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project structure**: `src/`, `tests/` at repository root
- Paths below use absolute references from repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and environment setup

- [X] T001 Verify Python 3.11+ installed and create virtual environment
- [X] T002 Install all dependencies from requirements.txt (FastAPI, SQLAlchemy async, Redis, etc.)
- [X] T003 [P] Create `.env` file with DATABASE_URL, REDIS_URL, CORS_ORIGINS per quickstart.md
- [X] T004 [P] Verify PostgreSQL 15+ is running and accessible
- [X] T005 [P] Verify Redis 7+ is running and accessible
- [X] T006 [P] Verify MT4 Integration Service (feature 001) is running
- [X] T007 Run database migrations with `alembic upgrade head` to ensure schema is current

**Checkpoint**: ✅ Environment ready - all services accessible

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database Optimization

- [X] T008 Create Alembic migration for composite index on market_data (symbol, timeframe, time DESC) per research.md
- [X] T009 Create Alembic migration for partial index on market_data recent 30 days per research.md (converted to no-op - composite index sufficient)
- [X] T010 [P] Run and verify database indexes using `EXPLAIN ANALYZE` for performance validation (achieved 1.849ms for 500 candlesticks)

### Pydantic Response Models (Shared Across Stories)

- [X] T011 [P] Create MarketDataResponse model in src/api/models/market_data.py with from_attributes=True
- [X] T012 [P] Create MarketDataListResponse model with pagination fields (data, total, page, page_size, next_cursor)
- [X] T013 [P] Create AccountResponse model in src/api/models/trading.py
- [X] T014 [P] Create PositionResponse model in src/api/models/trading.py
- [X] T015 [P] Create PositionListResponse model in src/api/models/trading.py
- [X] T016 [P] Create TradeResponse model in src/api/models/trading.py
- [X] T017 [P] Create TradeListResponse model in src/api/models/trading.py with pagination
- [X] T018 [P] Create ForecastResponse model in src/api/models/forecasts.py
- [X] T019 [P] Create ForecastListResponse model in src/api/models/forecasts.py
- [X] T020 [P] Create ErrorResponse model in src/api/models/common.py with error, detail, timestamp, request_id fields
- [X] T021 [P] Create HealthResponse model in src/api/models/system.py with status, dependencies dict

### Redis Caching Infrastructure

- [X] T022 Create Redis client wrapper in src/utils/redis_client.py with async connection pooling
- [X] T023 Implement cache-aside pattern helper functions (get_cached, set_cached, invalidate_cache) in src/utils/cache.py
- [X] T024 [P] Define cache key patterns as constants in src/utils/cache.py (price:latest:{symbol}, chart:{symbol}:{timeframe}, etc.)
- [X] T025 [P] Implement cache serialization/deserialization helpers (JSON with metadata: cached_at, source, version)

### Repository Enhancements

- [X] T026 Update MarketDataRepository in src/database/repositories/market_data_repository.py with keyset pagination support
- [X] T027 Add get_latest_by_symbol(symbol, timeframe) method to MarketDataRepository
- [X] T028 Add get_by_time_range(symbol, timeframe, start, end, cursor) method with keyset pagination to MarketDataRepository
- [X] T029 Update existing TradingRepository or create in src/database/repositories/trading_repository.py if not exists
- [X] T030 Add get_account_info() method to TradingRepository
- [X] T031 Add get_open_positions(symbol_filter) method to TradingRepository
- [X] T032 Add get_trading_history(symbol, start_date, end_date, trade_type, cursor) method with keyset pagination

**Checkpoint**: ✅ Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - View Real-Time Market Data (Priority: P1) 🎯 MVP

**Goal**: Traders can view live market prices and historical price data in the dashboard to make informed trading decisions based on current market conditions.

**Independent Test**: Open dashboard, select CrudeOIL symbol, verify current price and chart data for M5 timeframe with 500 candlesticks loads within 2 seconds. Verify data updates automatically via SSE stream without page refresh.

### Tests for User Story 1 (TDD - WRITE FIRST, ENSURE FAIL)

- [X] T033 [P] [US1] Contract test for GET /api/market-data/{symbol} schema validation in tests/contract/test_market_data_schemas.py
- [X] T034 [P] [US1] Contract test for GET /api/market-data/{symbol}/range schema validation in tests/contract/test_market_data_schemas.py
- [X] T035 [P] [US1] Contract test for GET /api/market-data/symbols schema validation in tests/contract/test_market_data_schemas.py
- [X] T036 [P] [US1] Contract test for SSE /api/stream/market-data event schema validation in tests/contract/test_market_data_schemas.py
- [X] T037 [P] [US1] Integration test for market data retrieval flow with pagination in tests/integration/test_market_data_api.py
- [X] T038 [P] [US1] Integration test for market data time range queries in tests/integration/test_market_data_api.py
- [X] T039 [P] [US1] Integration test for symbols listing with metadata in tests/integration/test_market_data_api.py
- [X] T040 [US1] Integration test for SSE market data streaming with Redis pub/sub in tests/integration/test_market_data_streaming.py
- [X] T041 [P] [US1] Unit test for MarketDataService caching logic in tests/unit/services/test_market_data_service.py
- [X] T042 [P] [US1] Unit test for keyset pagination cursor generation in tests/unit/repositories/test_market_data_repository.py

**✅ All US1 tests written (378 lines, 15 test methods) - verified FAIL before implementation**

### Implementation for User Story 1

- [X] T043 [P] [US1] Create SymbolInfoResponse model in src/api/models/market_data.py
- [X] T044 [P] [US1] Create SymbolListResponse model in src/api/models/market_data.py
- [X] T045 [US1] Create MarketDataService in src/services/market_data_service.py with caching logic (290 lines, cache-aside pattern)
- [X] T046 [US1] Implement get_market_data(symbol, timeframe, limit, cursor) in MarketDataService with Redis cache (5s TTL)
- [X] T047 [US1] Implement get_market_data_range(symbol, start, end, cursor) in MarketDataService
- [X] T048 [US1] Implement get_symbols() in MarketDataService with latest price and metadata
- [X] T049 [US1] Enhance GET /api/market-data/{symbol} endpoint in src/api/routes/market_data.py to use MarketDataService
- [X] T050 [US1] Enhance GET /api/market-data/{symbol}/range endpoint in src/api/routes/market_data.py
- [X] T051 [US1] Enhance GET /api/market-data/symbols endpoint in src/api/routes/market_data.py
- [X] T052 [US1] Create RedisSubscriberService in src/services/redis_subscriber_service.py for pub/sub listening (177 lines)
- [X] T053 [US1] Implement SSE background task in src/api/routes/market_data.py that subscribes to Redis channel `market_data:{symbol}:{timeframe}`
- [X] T054 [US1] Implement SSE GET /api/stream/market-data endpoint using FastAPI StreamingResponse with EventSource format
- [X] T055 [US1] Add error handling for "no data available" scenario with 404 response
- [X] T056 [US1] Add error handling for invalid timeframe with 400 response
- [X] T057 [US1] Add structured logging for all market data operations using structlog
- [X] T058 [US1] Implement cache invalidation on Redis `market_data:*` events

**✅ All US1 tests PASS - Performance: 1.849ms for 500 candlesticks (1082x faster than 2s target)**

**Checkpoint**: ✅ User Story 1 complete - traders can view market data with <2s load time and real-time updates

---

## Phase 4: User Story 2 - Monitor Account Balance and Trading Activity (Priority: P2)

**Goal**: Traders can view current account balance, open positions, and recent trading history to track portfolio performance and manage risk.

**Independent Test**: Connect to demo MT4 account, execute a test trade, verify dashboard shows updated balance, open positions list includes new position with unrealized P&L, and trade history shows completed trades.

### Tests for User Story 2 (TDD - WRITE FIRST, ENSURE FAIL)

- [X] T059 [P] [US2] Contract test for GET /api/trading/account schema validation in tests/contract/test_trading_schemas.py
- [X] T060 [P] [US2] Contract test for GET /api/trading/positions schema validation in tests/contract/test_trading_schemas.py
- [X] T061 [P] [US2] Contract test for GET /api/trading/history schema validation in tests/contract/test_trading_schemas.py
- [X] T062 [P] [US2] Contract test for SSE /api/stream/account event schema validation in tests/contract/test_trading_schemas.py
- [X] T063 [P] [US2] Integration test for account info retrieval in tests/integration/test_trading_api.py
- [X] T064 [P] [US2] Integration test for open positions with symbol filter in tests/integration/test_trading_api.py
- [X] T065 [P] [US2] Integration test for trading history with date range and pagination in tests/integration/test_trading_api.py
- [X] T066 [US2] Integration test for SSE account updates stream with balance changes in tests/integration/test_account_streaming.py
- [X] T067 [P] [US2] Unit test for TradingService caching logic in tests/unit/services/test_trading_service.py
- [X] T068 [P] [US2] Unit test for position profit calculation in tests/unit/services/test_trading_service.py

**✅ All US2 tests written (322 lines, 17 test methods) - verified FAIL before implementation**

### Implementation for User Story 2

- [X] T069 [US2] Create TradingService in src/services/trading_service.py with caching for account and positions (330 lines)
- [X] T070 [US2] Implement get_account_info() in TradingService with Redis cache (10s TTL)
- [X] T071 [US2] Implement get_open_positions(symbol_filter) in TradingService with Redis cache (5s TTL)
- [X] T072 [US2] Implement get_trading_history(symbol, start_date, end_date, trade_type, cursor) in TradingService with pagination
- [X] T073 [US2] Implement GET /api/trading/account endpoint in src/api/routes/trading.py using TradingService (545 lines total)
- [X] T074 [US2] Implement GET /api/trading/positions endpoint in src/api/routes/trading.py with optional symbol filter
- [X] T075 [US2] Implement GET /api/trading/history endpoint in src/api/routes/trading.py with date range and trade_type filters
- [X] T076 [US2] Implement SSE background task for account updates subscribing to Redis channels: account:balance, positions:updates, trades:executed
- [X] T077 [US2] Implement SSE GET /api/stream/account endpoint with account balance and position updates
- [X] T078 [US2] Add cache invalidation on trade execution events (invalidate account:*:balance and positions:open:*)
- [X] T079 [US2] Add error handling for account not found with 404 response
- [X] T080 [US2] Add structured logging for all trading operations

**✅ All US2 tests PASS - 8 trading endpoints operational with caching and keyset pagination**

**Checkpoint**: ✅ User Stories 1 AND 2 complete - traders can view market data AND monitor account/positions independently

---

## Phase 5: User Story 3 - View Price Forecasts and Strategy Allocations (Priority: P3)

**Goal**: Traders can see AI-generated price forecasts and current strategy allocations to understand system predictions and capital distribution across trading strategies.

**Independent Test**: View Forecasts page and verify predicted price movements for next 1h, 4h, 24h are displayed with confidence levels. View Strategies page and verify capital allocation percentages and performance metrics for active strategies.

### Tests for User Story 3 (TDD - WRITE FIRST, ENSURE FAIL)

- [ ] T081 [P] [US3] Contract test for GET /api/forecasts/latest schema validation in tests/contract/test_forecast_schemas.py
- [ ] T082 [P] [US3] Contract test for GET /api/forecasts/{symbol} schema validation in tests/contract/test_forecast_schemas.py
- [ ] T083 [P] [US3] Contract test for GET /api/strategies schema validation in tests/contract/test_strategy_schemas.py
- [ ] T084 [P] [US3] Contract test for GET /api/strategies/{id}/allocations schema validation in tests/contract/test_strategy_schemas.py
- [ ] T085 [P] [US3] Contract test for GET /api/strategies/{id}/performance schema validation in tests/contract/test_strategy_schemas.py
- [ ] T086 [P] [US3] Integration test for latest forecasts retrieval in tests/integration/test_forecasts_api.py
- [ ] T087 [P] [US3] Integration test for symbol forecasts with pagination in tests/integration/test_forecasts_api.py
- [ ] T088 [P] [US3] Integration test for strategies listing in tests/integration/test_strategies_api.py
- [ ] T089 [P] [US3] Integration test for strategy allocations history in tests/integration/test_strategies_api.py
- [ ] T090 [P] [US3] Integration test for strategy performance metrics by period in tests/integration/test_strategies_api.py
- [ ] T091 [P] [US3] Unit test for ForecastService caching in tests/unit/services/test_forecast_service.py
- [ ] T092 [P] [US3] Unit test for StrategyService allocation calculation in tests/unit/services/test_strategy_service.py

**Run all US3 tests - verify they FAIL before proceeding to implementation**

### Database Migrations for New Entities

- [ ] T093 [P] [US3] Create Alembic migration for strategies table (name, description, status ENUM, allocated_capital, parameters JSON)
- [ ] T094 [P] [US3] Create Alembic migration for strategy_allocations table with FK to strategies
- [ ] T095 [P] [US3] Create Alembic migration for strategy_performance table with FK to strategies
- [ ] T096 [US3] Run migrations with `alembic upgrade head` and verify new tables exist

### New Database Models

- [ ] T097 [P] [US3] Create Strategy model in src/database/models/strategy.py with status ENUM (ACTIVE, PAUSED, DISABLED)
- [ ] T098 [P] [US3] Create StrategyAllocation model in src/database/models/strategy_allocation.py with FK to Strategy
- [ ] T099 [P] [US3] Create StrategyPerformance model in src/database/models/strategy_performance.py with FK to Strategy

### New Repositories

- [ ] T100 [P] [US3] Create ForecastRepository in src/database/repositories/forecast_repository.py (if not exists)
- [ ] T101 [US3] Add get_latest_forecasts(symbol_filter, horizon_filter) method to ForecastRepository
- [ ] T102 [US3] Add get_forecasts_by_symbol(symbol, cursor) method to ForecastRepository with pagination
- [ ] T103 [P] [US3] Create StrategyRepository in src/database/repositories/strategy_repository.py
- [ ] T104 [US3] Add get_all_strategies() method to StrategyRepository
- [ ] T105 [US3] Add get_strategy_allocations(strategy_id) method to StrategyRepository
- [ ] T106 [US3] Add get_strategy_performance(strategy_id, period) method to StrategyRepository

### Pydantic Response Models

- [ ] T107 [P] [US3] Create StrategyResponse model in src/api/models/strategies.py
- [ ] T108 [P] [US3] Create StrategyListResponse model in src/api/models/strategies.py
- [ ] T109 [P] [US3] Create StrategyAllocationResponse model in src/api/models/strategies.py
- [ ] T110 [P] [US3] Create StrategyAllocationListResponse model in src/api/models/strategies.py
- [ ] T111 [P] [US3] Create StrategyPerformanceResponse model in src/api/models/strategies.py

### Services

- [ ] T112 [US3] Create ForecastService in src/services/forecast_service.py with Redis caching (1h TTL)
- [ ] T113 [US3] Implement get_latest_forecasts(symbol, horizon) in ForecastService
- [ ] T114 [US3] Implement get_forecasts_by_symbol(symbol, cursor) in ForecastService
- [ ] T115 [US3] Create StrategyService in src/services/strategy_service.py with Redis caching for allocations (1h TTL)
- [ ] T116 [US3] Implement get_all_strategies() in StrategyService
- [ ] T117 [US3] Implement get_strategy_allocations(strategy_id) in StrategyService
- [ ] T118 [US3] Implement get_strategy_performance(strategy_id, period) in StrategyService with win_rate, sharpe_ratio calculations

### API Endpoints

- [ ] T119 [US3] Create forecasts.py router in src/api/routes/forecasts.py (if not fully implemented)
- [ ] T120 [US3] Implement GET /api/forecasts/latest endpoint with symbol and horizon query filters
- [ ] T121 [US3] Implement GET /api/forecasts/{symbol} endpoint with pagination
- [ ] T122 [US3] Create strategies.py router in src/api/routes/strategies.py (if not fully implemented)
- [ ] T123 [US3] Implement GET /api/strategies endpoint listing all strategies
- [ ] T124 [US3] Implement GET /api/strategies/{strategy_id}/allocations endpoint
- [ ] T125 [US3] Implement GET /api/strategies/{strategy_id}/performance endpoint with period query parameter (daily, weekly, monthly, all_time)
- [ ] T126 [US3] Add cache invalidation on forecast generation events (invalidate forecasts:*)
- [ ] T127 [US3] Add error handling for strategy not found with 404 response
- [ ] T128 [US3] Add structured logging for forecast and strategy operations

**Run all US3 tests - verify they PASS**

**Checkpoint**: All user stories complete - traders can view market data, monitor account/trading, AND view forecasts/strategies independently

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories and production readiness

### Performance Optimization

- [ ] T129 [P] Run load testing with Locust (50 concurrent users) per quickstart.md and verify <200ms p95 latency
- [ ] T130 [P] Optimize database queries using EXPLAIN ANALYZE and add additional indexes if needed
- [ ] T131 [P] Tune SQLAlchemy connection pool settings (pool_size=20, max_overflow=10) in src/database/config.py
- [ ] T132 [P] Verify Redis cache hit rates and adjust TTLs if needed for optimal performance

### Monitoring & Observability

- [ ] T133 [P] Add Prometheus custom metrics for cache hit/miss rates in src/monitoring/metrics.py
- [ ] T134 [P] Add Prometheus custom metrics for SSE connection count
- [ ] T135 [P] Add Prometheus custom metrics for API endpoint response times by endpoint
- [ ] T136 [P] Verify all endpoints log errors with correlation IDs for request tracing

### Error Handling & Validation

- [ ] T137 [P] Add comprehensive input validation for all query parameters using Pydantic validators
- [ ] T138 [P] Add rate limiting verification - ensure slowapi middleware is active and limits are enforced
- [ ] T139 [P] Test error scenarios: database down, Redis down, MT4 service down - verify 503 responses
- [ ] T140 [P] Test edge case: request data for symbol with no database records - verify clear error message

### Health Checks

- [ ] T141 [US3] Enhance GET /api/system/health endpoint in src/api/routes/system.py to check database, Redis, MT4 service status
- [ ] T142 [US3] Add dependency health check functions in src/utils/health.py (check_database, check_redis, check_mt4_service)
- [ ] T143 [US3] Return 503 status code if any critical dependency is unhealthy

### Documentation

- [ ] T144 [P] Verify OpenAPI spec at /docs matches all implemented endpoints
- [ ] T145 [P] Add example responses to all endpoints in OpenAPI spec for better docs
- [ ] T146 [P] Update README.md with API quickstart examples if project has README
- [ ] T147 [P] Verify quickstart.md instructions work end-to-end (run through setup, test commands)

### Code Quality

- [ ] T148 [P] Run black formatter on all src/ and tests/ files
- [ ] T149 [P] Run isort to organize imports
- [ ] T150 [P] Run mypy type checking and fix any type errors
- [ ] T151 [P] Run flake8 linting and fix any violations
- [ ] T152 [P] Verify test coverage with pytest --cov=src --cov-report=html and confirm 85%+ coverage

### Security Hardening (Deferred to Phase 8-9 per Constitution)

- [ ] T153 **[DEFERRED]** Implement JWT authentication middleware (Phase 8-9)
- [ ] T154 **[DEFERRED]** Implement API key validation (Phase 8-9)
- [ ] T155 **[DEFERRED]** Add Jaeger distributed tracing (Phase 8-9)

**Final Checkpoint**: All user stories tested independently, performance validated, monitoring active, code quality confirmed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) - No dependencies on other stories (can run parallel with US1)
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) - No dependencies on other stories (can run parallel with US1/US2)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1 - Market Data)**: Can start after Foundational (Phase 2) ✅ Independent
- **User Story 2 (P2 - Account/Trading)**: Can start after Foundational (Phase 2) ✅ Independent
- **User Story 3 (P3 - Forecasts/Strategies)**: Can start after Foundational (Phase 2) ✅ Independent

**All user stories are designed to be independently testable and deliverable**

### Within Each User Story

1. Tests MUST be written FIRST and FAIL before implementation (TDD)
2. Database migrations (if needed) before models
3. Models before repositories
4. Repositories before services
5. Services before API endpoints
6. Core implementation before streaming/caching enhancements
7. Verify all tests PASS before moving to next priority

### Parallel Opportunities

- **Setup tasks**: T003-T006 can run in parallel
- **Foundational Phase**:
  - Database indexes: T008-T010 can run in parallel
  - Pydantic models: T011-T021 can all run in parallel
  - Repository enhancements: T026-T032 can run in parallel (different repositories)
- **Within User Story 1**:
  - All tests: T033-T042 can run in parallel
  - Models: T043-T044 can run in parallel
  - Cache infrastructure is prerequisite, then service implementation
- **Within User Story 2**:
  - All tests: T059-T068 can run in parallel
  - Service implementation can proceed once tests written
- **Within User Story 3**:
  - All tests: T081-T092 can run in parallel
  - Migrations: T093-T095 can run in parallel
  - Models: T097-T099 can run in parallel
  - Repositories: T100, T103 can run in parallel
  - Pydantic models: T107-T111 can run in parallel
- **Polish Phase**: T129-T132 (performance), T133-T136 (monitoring), T137-T140 (error handling), T148-T152 (code quality) can all run in parallel

**User Stories 1, 2, and 3 can be developed in parallel by different team members once Foundational phase is complete**

---

## Parallel Example: User Story 1 - Market Data

```bash
# Step 1: Write all tests in parallel (TDD - FAIL first)
Task: "Contract test for GET /api/market-data/{symbol} schema validation in tests/contract/test_market_data_schemas.py"
Task: "Contract test for GET /api/market-data/{symbol}/range schema validation in tests/contract/test_market_data_schemas.py"
Task: "Contract test for GET /api/market-data/symbols schema validation in tests/contract/test_market_data_schemas.py"
Task: "Integration test for market data retrieval flow with pagination in tests/integration/test_market_data_api.py"
Task: "Unit test for MarketDataService caching logic in tests/unit/services/test_market_data_service.py"

# Step 2: Run tests - verify FAIL
pytest tests/contract/test_market_data_schemas.py tests/integration/test_market_data_api.py tests/unit/services/test_market_data_service.py

# Step 3: Create Pydantic models in parallel
Task: "Create SymbolInfoResponse model in src/api/models/market_data.py"
Task: "Create SymbolListResponse model in src/api/models/market_data.py"

# Step 4: Implement service (sequential - depends on cache infrastructure)
Task: "Create MarketDataService in src/services/market_data_service.py with caching logic"
Task: "Implement get_market_data(symbol, timeframe, limit, cursor) in MarketDataService"
Task: "Implement get_market_data_range(symbol, start, end, cursor) in MarketDataService"

# Step 5: Implement endpoints (can be parallel per endpoint)
Task: "Enhance GET /api/market-data/{symbol} endpoint in src/api/routes/market_data.py"
Task: "Enhance GET /api/market-data/{symbol}/range endpoint in src/api/routes/market_data.py"
Task: "Enhance GET /api/market-data/symbols endpoint in src/api/routes/market_data.py"

# Step 6: Run tests - verify PASS
pytest tests/contract/test_market_data_schemas.py tests/integration/test_market_data_api.py tests/unit/services/test_market_data_service.py --cov=src
```

---

## Parallel Example: Foundational Phase

```bash
# All Pydantic models can be created in parallel:
Task: "Create MarketDataResponse model in src/api/models/market_data.py"
Task: "Create AccountResponse model in src/api/models/trading.py"
Task: "Create PositionResponse model in src/api/models/trading.py"
Task: "Create ForecastResponse model in src/api/models/forecasts.py"
Task: "Create ErrorResponse model in src/api/models/common.py"
Task: "Create HealthResponse model in src/api/models/system.py"

# All repository enhancements can run in parallel (different files):
Task: "Update MarketDataRepository in src/database/repositories/market_data_repository.py with keyset pagination"
Task: "Update TradingRepository in src/database/repositories/trading_repository.py"
Task: "Add get_account_info() method to TradingRepository"
Task: "Add get_open_positions(symbol_filter) method to TradingRepository"
```

---

## Parallel Example: Multiple User Stories (Team Strategy)

```bash
# Once Foundational phase completes, launch all 3 user stories in parallel:

# Developer A focuses on User Story 1 (Market Data):
Task: "Write all US1 tests (T033-T042) → Implement MarketDataService → Enhance endpoints → Verify tests pass"

# Developer B focuses on User Story 2 (Account/Trading):
Task: "Write all US2 tests (T059-T068) → Implement TradingService → Implement endpoints → Verify tests pass"

# Developer C focuses on User Story 3 (Forecasts/Strategies):
Task: "Write all US3 tests (T081-T092) → Create migrations → Implement models → Create repositories → Implement services → Implement endpoints → Verify tests pass"

# All 3 developers working independently - no blocking dependencies
```

---

## Implementation Strategy

### MVP First (User Story 1 Only) - RECOMMENDED

1. **Complete Phase 1: Setup** (T001-T007) - ~30 minutes
2. **Complete Phase 2: Foundational** (T008-T032) - CRITICAL prerequisite - ~4 hours
3. **Complete Phase 3: User Story 1** (T033-T058) - Full TDD cycle - ~6 hours
4. **STOP and VALIDATE**: Test User Story 1 independently using quickstart.md curl examples
5. **SUCCESS CRITERIA**:
   - Traders can view CrudeOIL market data in <2 seconds
   - SSE stream delivers real-time price updates within 5 seconds
   - All US1 tests pass with 85%+ coverage
6. **Deploy/Demo MVP** ✅

**Total MVP Timeline**: ~10-12 hours of focused development

### Incremental Delivery (Recommended Approach)

1. **Foundation Ready** → Complete Setup + Foundational (Phases 1-2) - ~4.5 hours
2. **MVP Delivery** → Add User Story 1 → Test independently → Deploy/Demo - +6 hours (Total: ~10.5 hours)
3. **Second Increment** → Add User Story 2 → Test independently → Deploy/Demo - +5 hours (Total: ~15.5 hours)
4. **Third Increment** → Add User Story 3 → Test independently → Deploy/Demo - +8 hours (Total: ~23.5 hours)
5. **Production Ready** → Add Polish → Final validation → Deploy - +4 hours (Total: ~27.5 hours)

Each increment adds measurable value without breaking previous functionality.

### Parallel Team Strategy (Maximum Speed)

With 3 developers:

1. **Team completes Setup + Foundational together** (Phases 1-2) - ~4.5 hours
2. **Parallel user story development** (once Foundational complete):
   - **Developer A**: User Story 1 (Market Data) - 6 hours
   - **Developer B**: User Story 2 (Account/Trading) - 5 hours
   - **Developer C**: User Story 3 (Forecasts/Strategies) - 8 hours
   - **All work independently** - no blocking dependencies
3. **Integration & Polish**: Team regroups for Phase 6 - 4 hours

**Total Timeline with 3 developers**: ~12.5 hours (vs 27.5 hours sequential)

---

## Task Summary

**Total Tasks**: 155
- **Setup (Phase 1)**: 7 tasks
- **Foundational (Phase 2)**: 25 tasks (CRITICAL - blocks all user stories)
- **User Story 1 (Phase 3)**: 26 tasks (10 tests + 16 implementation)
- **User Story 2 (Phase 4)**: 22 tasks (10 tests + 12 implementation)
- **User Story 3 (Phase 5)**: 48 tasks (12 tests + 36 implementation including new models)
- **Polish (Phase 6)**: 27 tasks

**Test Coverage**: 32 test tasks across all user stories (TDD approach)
- Contract tests: 12
- Integration tests: 12
- Unit tests: 8

**Parallel Opportunities**:
- Phase 1: 4 tasks can run in parallel
- Phase 2: 19 tasks can run in parallel
- Phase 3: 10 tests + 2 models can run in parallel
- Phase 4: 10 tests can run in parallel
- Phase 5: 12 tests + 3 migrations + 3 models + 5 Pydantic models can run in parallel
- Phase 6: 24 tasks can run in parallel

**Independent Stories**: All 3 user stories are independently testable and deliverable

**MVP Scope**: Phases 1-3 only (Setup + Foundational + User Story 1) = 58 tasks = ~10-12 hours

---

## Notes

- **[P] tasks** = Different files, no dependencies, can run in parallel
- **[Story] label** = Maps task to specific user story for traceability (US1, US2, US3)
- **TDD Required**: Constitution Principle I mandates tests FIRST, FAIL, then implement, PASS
- **Each user story is independently completable and testable** - can deliver incrementally
- **Verify tests fail before implementing** - critical for TDD compliance
- **Commit after each task or logical group** for clear history
- **Stop at any checkpoint to validate story independently** before proceeding
- **Foundational phase (Phase 2) is BLOCKING** - no user story work can start until complete
- **User Stories 1, 2, 3 can all run in parallel** once Foundation is complete
- **Avoid**: Vague tasks, same file conflicts, cross-story dependencies that break independence
- **Security Note**: Authentication/authorization deferred to Phase 8-9 per constitution-approved deferral
