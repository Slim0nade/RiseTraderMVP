# Research Report: Dashboard API Service

**Feature**: 002-fastapi-dashboard-api
**Date**: 2025-11-24
**Status**: Phase 0 Complete

## Overview

This research document resolves key technical unknowns identified during planning for the Dashboard API Service. The primary unknowns are:

1. **Real-time Streaming Technology**: WebSocket vs Server-Sent Events (SSE) vs Long Polling
2. **MT4 Integration Approach**: Redis pub/sub vs Direct ZeroMQ subscription
3. **Database Query Optimization**: Best practices for serving 500+ candlestick chart data
4. **Caching Strategy**: Redis caching patterns for frequently accessed data

---

## 1. Real-Time Streaming Technology Decision

### Research Question
Which technology should be used for delivering real-time market data updates to the React dashboard: WebSocket, Server-Sent Events (SSE), or Long Polling?

### Options Evaluated

#### Option A: WebSocket (Bi-directional)
**Pros**:
- Full duplex communication (both client and server can send messages)
- Low latency for real-time updates
- Efficient for high-frequency updates
- Native browser support
- FastAPI provides built-in WebSocket support via Starlette

**Cons**:
- More complex to implement than SSE
- Requires connection state management on server
- Can be harder to debug
- May face proxy/firewall issues in some corporate networks
- Overkill if communication is primarily server → client

**Use Case Fit**: Moderate - Dashboard needs server → client updates primarily, but bidirectional could enable client commands (e.g., subscribe/unsubscribe to symbols)

#### Option B: Server-Sent Events (SSE) (Uni-directional)
**Pros**:
- Simple to implement (HTTP-based, uses EventSource API)
- Automatic reconnection with built-in retry
- Efficient for one-way server → client updates
- HTTP/2 compatible
- Lower overhead than WebSocket for unidirectional data
- Built into browsers (EventSource API)
- Works well behind proxies/firewalls

**Cons**:
- Only server → client (no client → server messages over same channel)
- Limited to 6 concurrent connections per domain (HTTP/1.1) - not an issue with HTTP/2
- Less browser dev tools support than WebSocket

**Use Case Fit**: **HIGH** - Dashboard needs real-time price updates, account balance changes, position updates - all server → client. Client commands can use separate REST endpoints.

#### Option C: Long Polling
**Pros**:
- Universal compatibility
- Simple fallback mechanism

**Cons**:
- High latency compared to WebSocket/SSE
- Inefficient (constant HTTP request/response overhead)
- Server resource intensive
- Not suitable for high-frequency updates

**Use Case Fit**: Low - Only as fallback if SSE/WebSocket unavailable

### Decision: **Server-Sent Events (SSE)**

**Rationale**:
1. **Communication Pattern Match**: Dashboard consumption is primarily unidirectional (server → client). Client actions (e.g., selecting a symbol) can use REST endpoints.
2. **Simplicity**: SSE is simpler to implement and maintain than WebSocket while providing the same real-time performance for our use case.
3. **Automatic Reconnection**: Built-in retry mechanism ensures dashboard reconnects after temporary network issues.
4. **HTTP/2 Compatibility**: Modern deployment infrastructure supports HTTP/2, eliminating connection limit concerns.
5. **Resource Efficiency**: Lower server overhead than WebSocket for one-way streaming.
6. **Firewall Friendly**: HTTP-based, works through corporate proxies without special configuration.

**Implementation Approach**:
- FastAPI endpoint `/api/stream/market-data` using `StreamingResponse` with `text/event-stream` content type
- Redis pub/sub listener in background task feeding SSE stream
- Client subscribes via `EventSource` API in React dashboard
- Separate SSE channels for different data types:
  - `/api/stream/market-data` - Price updates
  - `/api/stream/account` - Account balance and positions
  - `/api/stream/forecasts` - New forecast availability

**Fallback Strategy**: If browser doesn't support EventSource (rare), fall back to long polling via REST endpoint with `?poll=true` query parameter.

**References**:
- FastAPI SSE: https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
- EventSource MDN: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
- SSE vs WebSocket: https://stackoverflow.com/questions/5195452/websockets-vs-server-sent-events-eventsource

---

## 2. MT4 Integration Approach

### Research Question
How should the Dashboard API receive real-time updates from MT4: Direct ZeroMQ subscription or Redis pub/sub?

### Options Evaluated

#### Option A: Direct ZeroMQ Subscription
**Pros**:
- Lower latency (direct connection to MT4 service)
- No intermediate broker
- Simple architecture

**Cons**:
- Tight coupling between API and MT4 service
- API must maintain ZMQ connection state
- Harder to scale horizontally (multiple API instances competing for messages)
- Violates separation of concerns (API shouldn't know about MT4 protocol)

**Use Case Fit**: Low - Creates architectural coupling

#### Option B: Redis Pub/Sub
**Pros**:
- Loose coupling - API subscribes to Redis channels, doesn't know about MT4
- Multiple API instances can subscribe to same channel (broadcast)
- Aligns with event-driven architecture (constitution principle VII)
- Redis already in stack for caching
- Easy to add more subscribers (agents, other services)
- Message replay capability if needed (Redis Streams upgrade path)

**Cons**:
- Additional network hop (MT4 → Redis → API → Dashboard)
- Slightly higher latency (typically 1-5ms overhead)

**Use Case Fit**: **HIGH** - Aligns with architecture principles, enables scalability

### Decision: **Redis Pub/Sub**

**Rationale**:
1. **Architecture Alignment**: Constitution principle VII requires event-driven communication. MT4 service publishes to Redis, API subscribes.
2. **Decoupling**: API doesn't need to know MT4 connection details, protocols, or state.
3. **Scalability**: Multiple API instances can run behind load balancer, all receiving broadcast updates.
4. **Future-Proof**: Easy to add more subscribers (e.g., MLPredictionAgent, PerformanceMonitorAgent) without changing MT4 service.
5. **Operational Simplicity**: Redis pub/sub is battle-tested, well-understood, and monitored.

**Implementation Approach**:
- MT4 Integration Service publishes to Redis channels:
  - `market_data:{symbol}:{timeframe}` - Price updates
  - `account:balance` - Account balance changes
  - `positions:updates` - Position open/close/modify events
  - `trades:executed` - Trade execution confirmations
- Dashboard API subscribes to relevant channels in background task
- Background task feeds SSE streams to connected dashboard clients
- Use `asyncio` with `aioredis` for non-blocking Redis subscription

**Latency Estimate**: MT4 → Redis → API → SSE → Dashboard: ~5-10ms total (well within 5 second requirement from spec.md line 168)

**References**:
- Redis Pub/Sub: https://redis.io/docs/interact/pubsub/
- aioredis: https://aioredis.readthedocs.io/en/latest/

---

## 3. Database Query Optimization for Chart Data

### Research Question
What are the best practices for efficiently querying and serving 500+ candlestick chart data points with <2 second response time?

### Key Findings

#### Database Indexing Strategy
**Requirement**: Query `market_data` table for specific symbol, timeframe, and date range efficiently.

**Recommended Indexes**:
```sql
-- Composite index for common query pattern
CREATE INDEX idx_market_data_symbol_timeframe_time
ON market_data (symbol, timeframe, time DESC);

-- Partial index for recent data (hot data)
CREATE INDEX idx_market_data_recent
ON market_data (symbol, timeframe, time DESC)
WHERE time >= NOW() - INTERVAL '30 days';
```

**Rationale**:
- Composite index covers WHERE clause (symbol, timeframe) and ORDER BY clause (time DESC)
- Partial index optimizes most common queries (recent 30 days) - faster, smaller index
- PostgreSQL can use index-only scans for count queries

#### Query Pattern Best Practices
**Recommended SQLAlchemy Query**:
```python
# Efficient query using indexed columns
query = (
    select(MarketData)
    .where(MarketData.symbol == symbol)
    .where(MarketData.timeframe == timeframe)
    .where(MarketData.time >= start_time)
    .where(MarketData.time <= end_time)
    .order_by(desc(MarketData.time))
    .limit(500)
)
```

**Optimization Techniques**:
1. **Limit First**: Apply LIMIT early (500 candlesticks is typical chart view)
2. **Avoid SELECT ***: Select only needed columns for chart (time, open, high, low, close, volume) - reduces data transfer
3. **Use Connection Pooling**: SQLAlchemy connection pool (already configured in project)
4. **Prepared Statements**: SQLAlchemy uses prepared statements by default - reduces parsing overhead

#### Pagination Strategy
**Problem**: Large datasets (e.g., 1 year of M1 data = 525,600 rows) need pagination without timeout.

**Recommended Approach - Keyset Pagination**:
```python
# Better than offset-based pagination for large datasets
query = (
    select(MarketData)
    .where(MarketData.symbol == symbol)
    .where(MarketData.timeframe == timeframe)
    .where(MarketData.time < last_seen_time)  # Keyset cursor
    .order_by(desc(MarketData.time))
    .limit(500)
)
```

**Advantages over OFFSET-based**:
- Consistent performance regardless of page number (OFFSET scans all skipped rows)
- No missing/duplicate records when data is inserted during pagination
- Database can use index efficiently

**References**:
- PostgreSQL Index Types: https://www.postgresql.org/docs/15/indexes-types.html
- Keyset Pagination: https://use-the-index-luke.com/no-offset

### Decision: **Composite Indexing + Keyset Pagination**

**Implementation**:
- Create Alembic migration adding recommended indexes
- Update repository methods to use keyset pagination
- API returns `next_cursor` (last time value) in response for pagination
- Dashboard passes cursor in next request: `?cursor=2024-11-24T10:30:00Z`

**Expected Performance**: <500ms for 500 candlesticks from indexed query (well under 2 second requirement)

---

## 4. Caching Strategy

### Research Question
Should frequently accessed data (latest prices, account balance) be cached in Redis? What patterns should be used?

### Options Evaluated

#### Option A: No Caching (Always Query PostgreSQL)
**Pros**:
- Always fresh data
- Simple implementation

**Cons**:
- Higher database load
- Slower response times for frequently accessed data
- Unnecessary database hits for data that changes infrequently

**Use Case Fit**: Low - Performance requirement (<200ms p95) demands optimization

#### Option B: Redis Caching with TTL
**Pros**:
- Fast retrieval (sub-millisecond from Redis)
- Reduces database load
- Configurable TTL for different data types
- Redis already in stack

**Cons**:
- Cache invalidation complexity
- Potential stale data if TTL too long

**Use Case Fit**: **HIGH** - Standard solution for read-heavy API

#### Option C: Application-Level Caching (Python dictionaries)
**Pros**:
- Fastest (in-memory, no network)

**Cons**:
- Not shared across API instances (horizontal scaling issue)
- Memory consumption per instance
- No TTL management built-in

**Use Case Fit**: Low - Doesn't scale horizontally

### Decision: **Redis Caching with TTL + Cache-Aside Pattern**

**Rationale**:
1. **Performance**: Sub-millisecond Redis reads meet <200ms p95 latency target
2. **Scalability**: Shared cache across multiple API instances
3. **Freshness Control**: Configurable TTL per data type balances freshness vs performance

**Caching Strategy by Data Type**:

| Data Type | TTL | Invalidation | Rationale |
|-----------|-----|--------------|-----------|
| Latest Symbol Price | 5 seconds | None (TTL-based) | Real-time data, short TTL acceptable |
| Historical Chart Data (500 candles) | 1 hour | None | Historical data rarely changes |
| Account Balance | 10 seconds | Event-driven (on trade execution) | Changes infrequently, invalidate on update |
| Open Positions | 5 seconds | Event-driven (on position change) | Real-time tracking needed |
| Forecasts | 1 hour | Event-driven (on new forecast) | Updated hourly per spec |
| Strategy Allocations | 1 hour | Event-driven (on allocation change) | Changes infrequently |

**Cache Key Patterns**:
```python
# Latest price
f"price:latest:{symbol}"

# Chart data
f"chart:{symbol}:{timeframe}:{start_time}:{end_time}"

# Account
f"account:{account_id}:balance"

# Positions
f"positions:open:{account_id}"
```

**Implementation Pattern (Cache-Aside)**:
```python
async def get_latest_price(symbol: str) -> MarketData:
    # Try cache first
    cache_key = f"price:latest:{symbol}"
    cached = await redis.get(cache_key)
    if cached:
        return deserialize(cached)

    # Cache miss - query database
    data = await market_data_repository.get_latest(symbol)

    # Populate cache
    await redis.setex(cache_key, 5, serialize(data))

    return data
```

**Cache Invalidation Strategy**:
- **TTL-based**: Automatic expiration for time-sensitive data
- **Event-driven**: Redis pub/sub listener invalidates cache on MT4 events
  - On `trades:executed` event → invalidate `account:*:balance` and `positions:open:*`
  - On new forecast → invalidate `forecasts:*`

**References**:
- Redis Caching Patterns: https://redis.io/docs/manual/patterns/
- Cache-Aside Pattern: https://docs.microsoft.com/en-us/azure/architecture/patterns/cache-aside

---

## 5. FastAPI Best Practices for Trading API

### Research Question
What FastAPI-specific patterns and best practices apply to building a high-performance trading data API?

### Key Findings

#### Async/Await Consistently
**Requirement**: All database operations must be truly asynchronous to handle 50+ concurrent users.

**Best Practice**:
- Use `AsyncSession` from SQLAlchemy (already in project)
- All route handlers declared as `async def`
- Use `await` for all I/O operations (database, Redis, HTTP calls)
- Avoid blocking operations in async context

**Anti-pattern to Avoid**:
```python
# BAD - Blocks event loop
@router.get("/data")
async def get_data():
    data = sync_database_call()  # Blocks!
    return data
```

**Correct Pattern**:
```python
# GOOD - Non-blocking
@router.get("/data")
async def get_data(db: AsyncSession = Depends(get_db)):
    data = await async_database_call(db)  # Non-blocking
    return data
```

#### Dependency Injection for Shared Resources
**Best Practice**: Use FastAPI's dependency injection for database sessions, Redis connections, configuration.

**Already Implemented in Project**:
```python
# src/api/dependencies.py
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session
```

**Usage in Routes**:
```python
@router.get("/data")
async def get_data(db: AsyncSession = Depends(get_db)):
    # db session automatically managed (commit/rollback/close)
    ...
```

#### Response Models for Type Safety
**Best Practice**: Use Pydantic response models for all endpoints (already in project at `src/api/models/`).

**Benefits**:
- Automatic OpenAPI schema generation
- Response validation
- Type hints for frontend developers
- Documentation clarity

#### Background Tasks for Non-Blocking Operations
**Use Case**: Send cache invalidation, log events, trigger webhooks without blocking response.

**Pattern**:
```python
from fastapi import BackgroundTasks

@router.post("/trade")
async def execute_trade(
    background_tasks: BackgroundTasks,
    ...
):
    # Blocking operation
    result = await execute_trade_logic()

    # Non-blocking operation
    background_tasks.add_task(invalidate_cache, key)
    background_tasks.add_task(log_to_analytics, result)

    return result  # Response sent immediately
```

#### Connection Pooling Configuration
**Requirement**: Handle 50+ concurrent connections efficiently.

**Recommended SQLAlchemy Pool Settings**:
```python
# For AsyncEngine
engine = create_async_engine(
    database_url,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=20,         # Base pool size
    max_overflow=10,      # Additional connections if needed
    pool_timeout=30,      # Wait for connection
    pool_recycle=3600,    # Recycle connections hourly
    pool_pre_ping=True,   # Verify connection before use
)
```

**Rationale**:
- `pool_size=20` handles 20 concurrent requests
- `max_overflow=10` allows bursts up to 30 total connections
- `pool_pre_ping=True` prevents "connection lost" errors from idle connections
- `pool_recycle=3600` prevents PostgreSQL idle connection timeouts

#### Error Handling and HTTP Status Codes
**Best Practice**: Use appropriate HTTP status codes and structured error responses.

**Pattern**:
```python
from fastapi import HTTPException, status

@router.get("/data/{symbol}")
async def get_data(symbol: str):
    data = await repository.get(symbol)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for symbol {symbol}"
        )

    return data
```

**Standard Status Codes for API**:
- `200 OK` - Successful GET
- `201 Created` - Successful POST (if creating resource)
- `400 Bad Request` - Invalid input (Pydantic validation)
- `404 Not Found` - Resource doesn't exist
- `500 Internal Server Error` - Unexpected server error
- `503 Service Unavailable` - Dependency failure (database down)

**References**:
- FastAPI Best Practices: https://github.com/zhanymkanov/fastapi-best-practices
- SQLAlchemy Async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

---

## Summary of Decisions

| Research Area | Decision | Key Rationale |
|---------------|----------|---------------|
| Real-time Streaming | **Server-Sent Events (SSE)** | Unidirectional fit, simplicity, HTTP/2 compatible, auto-reconnect |
| MT4 Integration | **Redis Pub/Sub** | Decoupling, scalability, event-driven architecture alignment |
| Database Optimization | **Composite Indexes + Keyset Pagination** | Performance, consistent query times, large dataset handling |
| Caching Strategy | **Redis with TTL + Event Invalidation** | Performance, shared cache, configurable freshness |
| FastAPI Patterns | **Async/await, Dependency Injection, Response Models** | Non-blocking I/O, type safety, maintainability |

---

## Implementation Checklist

Based on research findings, the following must be implemented:

- [ ] Create SSE endpoint for market data streaming (`/api/stream/market-data`)
- [ ] Create SSE endpoint for account updates (`/api/stream/account`)
- [ ] Implement Redis pub/sub listener in background task
- [ ] Create Alembic migration for database indexes
- [ ] Implement keyset pagination in repositories
- [ ] Implement Redis caching with cache-aside pattern
- [ ] Configure SQLAlchemy connection pool settings
- [ ] Add cache invalidation logic on MT4 events
- [ ] Update API response models with cursor-based pagination
- [ ] Add comprehensive error handling with appropriate HTTP status codes

**All research unknowns resolved. Proceeding to Phase 1 (Design & Contracts).**
