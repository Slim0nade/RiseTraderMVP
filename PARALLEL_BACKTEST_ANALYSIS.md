# Parallel Backtest Execution Analysis

**Date:** 2025-12-31
**Question:** What happens when 2 backtests run in parallel?

## Current Implementation

### How Backtests Are Executed

1. **FastAPI BackgroundTasks** - Uses `background_tasks.add_task(run_backtest_task)`
2. **Async Implementation** - Each backtest runs as an async function
3. **Separate Database Sessions** - Each backtest gets its own `AsyncSession`
4. **Chunked Data Loading** - Loads market data in chunks of 1,000 candles

### Code Flow

```python
# API Route (src/api/routes/backtesting.py:361)
async def run_backtest(
    request: RunBacktestRequest,
    background_tasks: BackgroundTasks,
    ...
):
    # Create run record (RUNNING status)
    run = BacktestRun(...)
    await db.commit()

    # Schedule background task
    background_tasks.add_task(run_backtest_task)

    # Return immediately to client
    return BacktestRunStatusResponse(run_id=...)
```

```python
# Data Replay (src/database/repositories/market_data_repository.py:636)
async def get_historical_candles_streamed(...):
    while cursor_time < end_time:
        # Async database query (yields control)
        result = await self.session.execute(query)
        chunk = list(result.scalars().all())  # 1000 candles
        yield chunk  # Process chunk
        cursor_time = chunk[-1].time
```

```python
# Backtest Loop (src/services/backtesting/backtest_service.py:412)
async for tick, processed, total in self.data_replay.replay_with_progress(...):
    candles_processed += 1

    # Synchronous processing (does NOT yield)
    portfolio.update_market_price(...)
    decision = decision_engine(tick)
    simulator.execute_entry(...)

    # Async database writes (yields control)
    await self.backtest_repo.create_trade(...)
    await self.backtest_repo.create_snapshot(...)
```

## What Happens with 2 Parallel Backtests

### ✅ **Good News: They CAN Run Concurrently**

1. **Separate Database Sessions** - No conflicts between backtests
2. **Async Database Queries** - Every 1,000 candles, the event loop can switch
3. **Async Database Writes** - Trade/snapshot writes yield control
4. **FastAPI Remains Responsive** - HTTP requests can be handled between yields

### ⚠️ **Potential Issues**

#### 1. **CPU-Bound Processing Between Yields**

Between database calls (every 1,000 candles), backtests run synchronously:
```python
for candle in chunk:  # 1000 iterations
    # All synchronous operations:
    portfolio.update_market_price(tick.symbol, tick.close)
    decision = decision_engine(tick)  # Can be expensive (indicators)
    simulator.execute_entry(...)
    # No await here - blocks for 1000 candles
```

**Impact:**
- If decision engine is complex (technical indicators, ML), this can take **seconds**
- Other backtest must wait for those seconds
- HTTP requests can queue up during this time

#### 2. **Memory Consumption**

Each backtest loads:
- Portfolio state
- All open positions
- Trade simulator state
- Indicator buffers (EMA, RSI, etc.)

**With 2 backtests:**
- 2× memory usage
- Could cause OOM if backtests are large

#### 3. **Database Connection Pool Exhaustion**

Each backtest uses a database session. FastAPI also needs sessions for HTTP requests.

**PostgreSQL Connection Settings:**
```python
# Default async pool in SQLAlchemy
pool_size = 5          # Maximum connections in pool
max_overflow = 10      # Additional connections when pool full
# Total max = 15 connections
```

**Usage:**
- Backtest 1: 1 connection
- Backtest 2: 1 connection
- HTTP requests: 1-3 connections
- **Risk:** If you run 10+ backtests, you hit connection limits

#### 4. **No Concurrency Limits**

There's **NO limit** on how many backtests can be started simultaneously.

```python
# User can POST 10 backtest requests at once
# All will start, all will compete for resources
```

## Real-World Scenarios

### Scenario 1: 2 Fast Backtests (10,000 candles each)

**Timeline:**
```
T+0ms:   Backtest A starts, loads chunk 1 (1000 candles)
T+50ms:  Backtest B starts, loads chunk 1 (1000 candles)
T+100ms: A processes chunk 1 synchronously
T+150ms: B processes chunk 1 synchronously (waits for A)
T+200ms: A loads chunk 2 (await - yields)
T+250ms: B loads chunk 2 (await - yields)
...continues alternating...
T+5s:    Both complete
```

**Result:** ✅ Works fine, alternates efficiently

### Scenario 2: 2 Long Backtests (150,000 candles each)

**Timeline:**
```
T+0s:    Backtest A starts
T+1s:    Backtest B starts
T+0-60s: Both run, alternating every 1-3 seconds
T+60s:   HTTP health check takes 2-3 seconds to respond
T+120s:  Both still running...
T+300s:  Backtest A completes
T+450s:  Backtest B completes
```

**Result:** ⚠️ Works but:
- API feels sluggish
- Dashboard shows delays
- Takes 2× time vs sequential

### Scenario 3: 5+ Backtests Simultaneously

**Problems:**
```
Connection pool exhausted → New HTTP requests fail
Memory usage spikes → Potential OOM
CPU maxed out → System crawls
Database under heavy load → Queries timeout
```

**Result:** 🔴 **System becomes unstable**

## Current Safeguards

### ✅ What We Have

1. **Max Candles Limit (150,000)** - Prevents infinite loops
2. **Async Database Operations** - Allows interleaving
3. **Chunked Loading** - Yields every 1,000 candles
4. **Separate Sessions** - No data corruption

### ❌ What We DON'T Have

1. **Concurrency Limit** - No cap on simultaneous backtests
2. **Resource Monitoring** - No check for available memory/CPU
3. **Queue System** - No proper task queue (Celery, RQ, etc.)
4. **Priority System** - All backtests equal priority
5. **CPU Yield Points** - Synchronous processing blocks

## Recommendations

### Short-Term Fixes (Easy)

#### 1. **Add Concurrency Limit**

```python
# In backtest service or API route
MAX_CONCURRENT_BACKTESTS = 2

async def run_backtest(...):
    # Check active backtests
    active_count = await db.execute(
        select(func.count(BacktestRun.id)).where(
            BacktestRun.status == RunStatus.RUNNING
        )
    )

    if active_count >= MAX_CONCURRENT_BACKTESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many active backtests ({active_count}). Max allowed: {MAX_CONCURRENT_BACKTESTS}"
        )
```

#### 2. **Add asyncio.sleep() in Processing Loop**

```python
async for tick, processed, total in self.data_replay.replay_with_progress(...):
    candles_processed += 1

    # Yield control every 100 candles
    if candles_processed % 100 == 0:
        await asyncio.sleep(0)  # Yield to event loop

    # ... rest of processing
```

This forces the event loop to check for other tasks every 100 candles.

### Medium-Term Fixes (Moderate Effort)

#### 3. **Implement Proper Task Queue**

Use **Celery** or **RQ** (Redis Queue):

```python
# In celery_worker.py
@celery_app.task
def run_backtest_task(run_id, config_id, ...):
    # Runs in separate worker process
    # Can scale workers independently
    # Built-in retry, monitoring, etc.
```

**Benefits:**
- True parallel processing (separate processes)
- Can run on different machines
- Built-in monitoring (Flower UI)
- Retry logic
- Priority queues

#### 4. **Resource-Based Throttling**

```python
import psutil

async def run_backtest(...):
    # Check system resources
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)

    if mem.percent > 80 or cpu > 80:
        raise HTTPException(
            status_code=503,
            detail="System resources exhausted. Try again later."
        )
```

### Long-Term Fixes (Architectural)

#### 5. **Separate Backtest Workers**

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│ Redis Queue  │────▶│  Worker 1   │
│  (API only) │     │              │     │ (backtests) │
└─────────────┘     └──────────────┘     └─────────────┘
                           │              ┌─────────────┐
                           └─────────────▶│  Worker 2   │
                                          │ (backtests) │
                                          └─────────────┘
```

**Benefits:**
- API never blocks
- Scale workers independently
- Restart workers without affecting API
- Run workers on different machines

## Testing Your System

### How to Test Parallel Backtests

```bash
# Terminal 1: Start backtest 1
curl -X POST http://localhost:8003/api/v1/backtesting/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "YOUR_CONFIG_ID",
    "timeframe": "M5",
    "synthetic_strategy": "ma_crossover"
  }'

# Terminal 2: Immediately start backtest 2
curl -X POST http://localhost:8003/api/v1/backtesting/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "YOUR_CONFIG_ID",
    "timeframe": "M5",
    "synthetic_strategy": "rsi"
  }'

# Terminal 3: Monitor API health
watch -n 1 'curl -s http://localhost:8003/health'
```

**Watch for:**
- ✅ Both backtests start (status: RUNNING)
- ✅ API health responds within 1-2 seconds
- ⚠️ If health takes >5 seconds → CPU blocking issue
- 🔴 If health times out → Critical blocking

### Check Database Connections

```sql
-- See active connections
SELECT count(*) as active_connections
FROM pg_stat_activity
WHERE datname = 'risetrader';

-- See backtest sessions
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity
WHERE datname = 'risetrader'
AND state = 'active';
```

## Summary

### Current State: ⚠️ **Works but Limited**

| Aspect | Status | Notes |
|--------|--------|-------|
| 2 backtests | ✅ Works | May slow API |
| 3-4 backtests | ⚠️ Risky | API becomes sluggish |
| 5+ backtests | 🔴 Fails | Resource exhaustion |
| API responsiveness | ⚠️ Degraded | Depends on backtest complexity |
| Data safety | ✅ Safe | Separate sessions |

### Recommended Configuration

**For current architecture (no changes):**
- **Max concurrent backtests:** 2
- **Max candles per backtest:** 150,000 (already implemented)
- **Monitor API health:** If response time >2s, stop new backtests

**For production:**
- Implement Celery workers
- Add concurrency limit (2-4)
- Add resource monitoring
- Scale workers on separate machines

## Immediate Action Items

1. ✅ **Already Done:** Max candles limit (150,000)
2. ⏳ **Next:** Add concurrency limit (MAX_CONCURRENT_BACKTESTS = 2)
3. ⏳ **Next:** Add `await asyncio.sleep(0)` every 100 candles
4. 🔮 **Future:** Migrate to Celery workers

---

**Bottom Line:** Your system CAN handle 2 parallel backtests, but with degraded performance. For production, you need proper task queuing.
