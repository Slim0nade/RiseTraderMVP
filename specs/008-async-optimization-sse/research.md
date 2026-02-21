# Research: Async Optimization Engine with SSE Notifications

**Date**: 2026-01-17  
**Feature**: 008-async-optimization-sse

## Research Tasks

### 1. SSE Implementation with FastAPI

**Question**: How to implement Server-Sent Events in FastAPI for real-time notifications?

**Decision**: Use `sse-starlette` library with FastAPI's StreamingResponse.

**Rationale**:
- `sse-starlette` is the de facto standard for SSE in FastAPI/Starlette
- Lightweight (no websocket complexity)
- Perfect for one-way server-to-client notifications
- Works well with MCP clients that can consume SSE streams

**Implementation Pattern**:
```python
from sse_starlette.sse import EventSourceResponse
import asyncio

async def event_generator():
    while True:
        if event := await get_next_event():
            yield {"event": event.type, "data": json.dumps(event.payload)}
        await asyncio.sleep(0.1)

@router.get("/events/stream")
async def stream_events():
    return EventSourceResponse(event_generator())
```

**Alternatives Considered**:
- WebSockets: Overkill for one-way notifications, more complex connection management
- Polling: Higher latency, more resource intensive
- Long-polling: More complex than SSE, no real advantages

---

### 2. Redis Job Queue Pattern

**Question**: How to implement async job queue for long-running optimizations?

**Decision**: Use Redis with asyncio background tasks (no external queue library).

**Rationale**:
- RiseTrader already uses Redis extensively (see `src/utils/redis_client.py`)
- Simple pattern: store job state in Redis hash, run as background task
- No new dependencies required beyond existing aioredis
- Suitable for single-worker, 10-100 jobs/day scale
- 24h TTL automatically cleans up old jobs

**Implementation Pattern**:
```python
# Job submission (returns immediately)
async def submit_optimization_job(params: dict) -> str:
    job_id = str(uuid4())
    await redis.hset(f"opt:job:{job_id}", mapping={
        "status": "pending",
        "params": json.dumps(params),
        "created_at": datetime.utcnow().isoformat()
    })
    await redis.expire(f"opt:job:{job_id}", 86400)  # 24h TTL
    
    # Fire-and-forget background task
    asyncio.create_task(run_optimization_worker(job_id))
    return job_id

# Background worker
async def run_optimization_worker(job_id: str):
    await redis.hset(f"opt:job:{job_id}", "status", "running")
    try:
        # Run optimization...
        for i, result in enumerate(run_grid_search()):
            await redis.hset(f"opt:job:{job_id}", mapping={
                "progress_pct": i / total * 100,
                "best_so_far": json.dumps(result)
            })
            await emit_sse_event("job_progress", {...})
        await redis.hset(f"opt:job:{job_id}", "status", "completed")
    except Exception as e:
        await redis.hset(f"opt:job:{job_id}", mapping={
            "status": "failed",
            "error": str(e)
        })
```

**Alternatives Considered**:
- Celery: Heavy dependency, overkill for our scale
- RQ (Redis Queue): Additional library, doesn't add value over raw Redis
- ARQ: Good option but adds dependency; native asyncio approach is simpler
- Database polling: Higher latency, Redis already available

---

### 3. Deterministic Grid Search

**Question**: How to implement exhaustive grid search without random sampling?

**Decision**: Use itertools.product for deterministic parameter enumeration.

**Rationale**:
- Standard Python library, no dependencies
- Guaranteed to test ALL combinations
- Predictable, reproducible results
- Natural progress tracking (index / total)

**Implementation Pattern**:
```python
from itertools import product

def generate_grid_combinations(param_grid: dict) -> list[dict]:
    """Generate all parameter combinations deterministically."""
    keys = list(param_grid.keys())
    values = [param_grid[k] for k in keys]
    
    combinations = []
    for combo in product(*values):
        combinations.append(dict(zip(keys, combo)))
    
    return combinations

# Example:
param_grid = {
    "fast_period": [5, 10, 15],
    "slow_period": [20, 30, 40],
    "threshold": [0.5, 0.7]
}
# Generates 3 × 3 × 2 = 18 combinations
combos = generate_grid_combinations(param_grid)
# combos[0] = {"fast_period": 5, "slow_period": 20, "threshold": 0.5}
# combos[1] = {"fast_period": 5, "slow_period": 20, "threshold": 0.7}
# ... deterministically ordered
```

**Grid Size Validation**:
```python
def calculate_grid_size(param_grid: dict) -> int:
    size = 1
    for values in param_grid.values():
        size *= len(values)
    return size

MAX_COMBINATIONS = 10000

if calculate_grid_size(param_grid) > MAX_COMBINATIONS:
    raise ValueError(f"Grid too large: {size} > {MAX_COMBINATIONS}")
```

**Alternatives Considered**:
- Random sampling: Not reproducible, may miss optimal parameters
- Bayesian optimization: More complex, better for very large grids (>10k)
- Latin hypercube: Good for continuous spaces, overkill for discrete grids

---

### 4. Database Schema for Optimization History

**Question**: How to structure optimization_runs table?

**Decision**: Extend existing pattern from `backtest.py` with JSONB for flexibility.

**Rationale**:
- Existing `ParameterGrid` and `GridSearchResult` models provide a good base
- JSONB allows flexible storage of varying parameter schemas
- Aligns with existing SQLAlchemy patterns in the codebase

**Schema Design**:
```python
class OptimizationRun(Base):
    __tablename__ = "optimization_runs"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id = Column(String(36), nullable=False, unique=True, index=True)
    strategy = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    
    # Flexible JSONB storage
    param_grid = Column(JSONB, nullable=False)
    results = Column(JSONB, nullable=True)  # Populated on completion
    
    # Metadata
    status = Column(String(20), nullable=False, default="pending")
    total_combinations = Column(Integer, nullable=False)
    combinations_tested = Column(Integer, nullable=False, default=0)
    best_params = Column(JSONB, nullable=True)
    best_metric_value = Column(Numeric(10, 4), nullable=True)
    optimization_target = Column(String(50), nullable=False, default="sharpe_ratio")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    error_message = Column(Text, nullable=True)
```

**Alternatives Considered**:
- Separate table per result: Too complex for our needs
- Flat columns for all parameters: Not flexible enough
- MongoDB-style document store: PostgreSQL JSONB is sufficient

---

### 5. Price Alert Monitoring

**Question**: How to efficiently monitor price levels for alerts?

**Decision**: Use polling loop with Redis cache for alert configurations.

**Rationale**:
- Fits existing architecture (stealth_stop_manager uses similar pattern)
- 5-second polling is acceptable for price alerts
- Redis stores active alerts for fast lookup
- Database persists alert history

**Implementation Pattern**:
```python
class PriceAlertService:
    def __init__(self, redis_client, trading_service):
        self.redis = redis_client
        self.trading = trading_service
        self._running = False
    
    async def set_alert(self, ticket: int, alert_type: str, price_level: float):
        key = f"alert:{ticket}:{alert_type}"
        await self.redis.hset(key, mapping={
            "ticket": ticket,
            "type": alert_type,
            "price": price_level,
            "created_at": datetime.utcnow().isoformat()
        })
    
    async def monitor_loop(self):
        self._running = True
        while self._running:
            positions = await self.trading.get_open_positions()
            for pos in positions:
                alerts = await self.get_alerts_for_ticket(pos.ticket)
                for alert in alerts:
                    if self._check_level_breach(pos.current_price, alert):
                        await self._trigger_alert(pos, alert)
            await asyncio.sleep(5)  # 5-second poll interval
```

**Alternatives Considered**:
- WebSocket streaming: More complex, not needed at 5s granularity
- MT4 price callbacks: Would require EA modification
- Database triggers: PostgreSQL triggers not suitable for real-time

---

### 6. SSE Event Types and Payloads

**Decision**: Standardized event types with JSON payloads.

**Event Types**:
```python
# Job events
{
    "event": "job_started",
    "data": {"job_id": "...", "strategy": "...", "total_combinations": 100}
}
{
    "event": "job_progress", 
    "data": {"job_id": "...", "progress_pct": 45, "combinations_tested": 45, "best_so_far": {...}}
}
{
    "event": "job_complete",
    "data": {"job_id": "...", "best_params": {...}, "best_metric": 1.5}
}
{
    "event": "job_failed",
    "data": {"job_id": "...", "error": "..."}
}

# Price events
{
    "event": "price_alert",
    "data": {"ticket": 12345, "alert_type": "liquidity_sweep", "price": 58.50, "level": 58.00}
}
```

---

## Summary of Decisions

| Topic | Decision | Key Dependency |
|-------|----------|----------------|
| SSE | sse-starlette | New: sse-starlette |
| Job Queue | Redis + asyncio.create_task | Existing: aioredis |
| Grid Search | itertools.product | Built-in |
| DB Schema | JSONB columns | Existing: SQLAlchemy |
| Price Monitoring | Polling loop (5s) | Existing: trading_service |

## NEEDS CLARIFICATION

None - all technical decisions resolved.
