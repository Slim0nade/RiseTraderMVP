# RiseTrader Backtesting Engine Analysis

## Current Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT BACKTEST FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

Step 1: Configuration Creation
┌──────────────┐     POST /configurations     ┌──────────────┐
│    Client    │ ──────────────────────────► │   FastAPI    │
│              │ ◄─ 201 + config_id ───────── │   Router     │
└──────────────┘                              └──────┬───────┘
                                                     │
                                                     ▼
                                              ┌──────────────┐
                                              │  PostgreSQL  │
                                              │   (configs)  │
                                              └──────────────┘

Step 2: Run Creation (Returns Immediately)
┌──────────────┐     POST /runs               ┌──────────────┐
│    Client    │ ──────────────────────────► │   FastAPI    │
│              │ ◄─ 202 + run_id ──────────── │   Router     │
└──────────────┘                              └──────┬───────┘
                                                     │
                                    Creates BacktestRun record
                                    Spawns BackgroundTask
                                                     │
                                                     ▼
                                              ┌──────────────┐
                                              │  Background  │
                                              │    Task      │
                                              └──────────────┘

Step 3: Background Execution (THE BOTTLENECK)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   BacktestService._run_synthetic_mode()                                        │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │  FOR EACH CANDLE (500,000+ iterations):                                 │  │
│   │                                                                         │  │
│   │    1. DB Query (chunked 1000 at a time)                                │  │
│   │       └─► async for chunk in repository.get_historical_candles_streamed│  │
│   │                                                                         │  │
│   │    2. Python Object Creation (SLOW)                                    │  │
│   │       └─► MarketTick.from_market_data(candle)                          │  │
│   │       └─► Creates dataclass for EACH candle                            │  │
│   │                                                                         │  │
│   │    3. Strategy Processing (ROW BY ROW)                                 │  │
│   │       └─► self.price_history.append(tick.close)  # List append         │  │
│   │       └─► np.array([float(p) for p in self.price_history])  # REBUILD! │  │
│   │       └─► np.mean(prices[-fast_period:])  # Calculate MA               │  │
│   │       └─► np.mean(prices[-slow_period:])  # Calculate MA again         │  │
│   │                                                                         │  │
│   │    4. Portfolio Update                                                 │  │
│   │       └─► portfolio.update_market_price(tick.symbol, tick.close)       │  │
│   │                                                                         │  │
│   │    5. Trade Execution (if signal)                                      │  │
│   │       └─► simulator.execute_entry()                                    │  │
│   │       └─► DB INSERT for each trade                                     │  │
│   │                                                                         │  │
│   │    6. Periodic Snapshot (every 100 candles)                            │  │
│   │       └─► DB INSERT snapshot                                           │  │
│   │                                                                         │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│   Time: ~10-60 seconds for 500K candles (depends on strategy complexity)       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

Step 4: Metrics Calculation
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   MetricsCalculator.calculate_all_metrics()                                    │
│                                                                                 │
│   1. Load all snapshots from DB                                                │
│   2. Load all trades from DB                                                   │
│   3. Calculate Sharpe, Sortino, Max Drawdown, etc.                            │
│   4. Update run record with final metrics                                      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Performance Bottlenecks Identified

### 1. Row-by-Row Processing (CRITICAL)
```python
# CURRENT: O(n) Python interpreter overhead
async for tick, processed, total in self.data_replay.replay_with_progress(...):
    candles_processed += 1
    portfolio.update_market_price(tick.symbol, tick.close)
    decision = decision_engine(tick)  # Python function call per candle
```

**Problem**: Each of the 500K+ candles goes through Python's interpreter individually.

### 2. Repeated NumPy Array Creation (CRITICAL)
```python
# CURRENT: Creates new array EVERY tick
def _ma_crossover_strategy(self, tick: MarketTick):
    prices = np.array([float(p) for p in self.price_history])  # NEW ARRAY!
    fast_ma = np.mean(prices[-fast_period:])  # Slice + mean
    slow_ma = np.mean(prices[-slow_period:])  # Slice + mean again
```

**Problem**: 500K array creations + 1M+ array slicing operations.

### 3. Database Roundtrips
```python
# CURRENT: 1000 candles per query = 500 queries for 500K candles
async for chunk in repository.get_historical_candles_streamed(..., chunk_size=1000):
```

**Problem**: Even with chunking, hundreds of DB queries.

### 4. No Cancellation Support
```python
# CURRENT: Background task runs to completion
async def run_backtest_task():
    # No way to interrupt mid-execution!
    await task_service.run_backtest(...)
```

**Problem**: Can't cancel a running backtest.

### 5. No Checkpointing
```python
# CURRENT: Failure = start over
except Exception as e:
    await task_backtest_repo.update_run(run_id=run_id, status=FAILED)
```

**Problem**: 30-minute backtest fails at 90%? Start over.

---

## Best-of-Breed Comparison

### Backtrader / VectorBT / Zipline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         VECTORIZED BACKTEST FLOW                                │
└─────────────────────────────────────────────────────────────────────────────────┘

Step 1: Load ALL Data (Once)
┌──────────────┐                              ┌──────────────┐
│   Pandas     │ ◄──── Single Query ───────── │   Database   │
│  DataFrame   │      SELECT * FROM candles   │              │
│  (500K rows) │      WHERE date BETWEEN      │              │
└──────┬───────┘                              └──────────────┘
       │
       │ In-memory: ~200MB for 500K candles
       ▼

Step 2: Vectorized Indicator Calculation (INSTANT)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   # Calculate ALL moving averages in ONE operation                             │
│   df['fast_ma'] = df['close'].rolling(10).mean()   # 500K values at once      │
│   df['slow_ma'] = df['close'].rolling(30).mean()   # 500K values at once      │
│   df['rsi'] = ta.RSI(df['close'], 14)              # 500K values at once      │
│                                                                                 │
│   # Generate ALL signals vectorized                                            │
│   df['signal'] = np.where(                                                     │
│       (df['fast_ma'] > df['slow_ma']) &                                       │
│       (df['fast_ma'].shift(1) <= df['slow_ma'].shift(1)),                     │
│       1,  # BUY                                                                │
│       np.where(                                                                │
│           (df['fast_ma'] < df['slow_ma']) &                                   │
│           (df['fast_ma'].shift(1) >= df['slow_ma'].shift(1)),                 │
│           -1,  # SELL                                                          │
│           0   # HOLD                                                           │
│       )                                                                        │
│   )                                                                            │
│                                                                                 │
│   Time: ~100ms for 500K candles (vs 30+ seconds row-by-row)                   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

Step 3: Vectorized P&L Calculation
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   # Calculate position changes                                                 │
│   df['position'] = df['signal'].replace(0, np.nan).ffill().fillna(0)          │
│                                                                                 │
│   # Calculate returns vectorized                                               │
│   df['returns'] = df['close'].pct_change() * df['position'].shift(1)          │
│                                                                                 │
│   # Cumulative equity curve                                                    │
│   df['equity'] = (1 + df['returns']).cumprod() * initial_capital              │
│                                                                                 │
│   Time: ~50ms                                                                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

Step 4: Vectorized Metrics
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   sharpe = df['returns'].mean() / df['returns'].std() * np.sqrt(252)          │
│   max_dd = (df['equity'] / df['equity'].cummax() - 1).min()                   │
│   total_return = df['equity'].iloc[-1] / initial_capital - 1                  │
│                                                                                 │
│   Time: ~10ms                                                                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: ~200-500ms for 500K candles (vs 30-60 seconds current)
           100x-300x FASTER
```

---

## Feature Comparison Matrix

| Feature | RiseTrader (Current) | VectorBT | Backtrader | Zipline |
|---------|---------------------|----------|------------|---------|
| **Processing** | Row-by-row (Python) | Vectorized (NumPy) | Event-driven | Vectorized |
| **Speed (500K candles)** | 30-60s | 0.2-0.5s | 5-10s | 1-2s |
| **Memory** | Low (streaming) | High (all in RAM) | Medium | High |
| **Multi-asset** | ❌ Single | ✅ Full | ✅ Full | ✅ Full |
| **Live trading** | ✅ MT4 | ❌ No | ✅ Yes | ❌ No |
| **Cancellation** | ❌ No | N/A (fast) | ✅ Yes | N/A |
| **Checkpointing** | ❌ No | N/A | ✅ Yes | ✅ Yes |
| **Walk-forward** | ❌ No | ✅ Built-in | ✅ Plugin | ✅ Built-in |
| **Monte Carlo** | ❌ No | ✅ Built-in | ❌ No | ❌ No |
| **Progress streaming** | ✅ Redis/SSE | N/A | ❌ No | ❌ No |
| **Slippage models** | ✅ Basic | ✅ Advanced | ✅ Advanced | ✅ Advanced |
| **Commission models** | ✅ Basic | ✅ Advanced | ✅ Advanced | ✅ Advanced |

---

## What's Missing (Priority Order)

### 1. 🔴 CRITICAL: Vectorized Processing Engine
**Impact**: 100-300x speedup
**Effort**: Medium (2-3 days)

```python
# NEW: VectorizedBacktestEngine
class VectorizedBacktestEngine:
    async def run(self, config: BacktestConfig) -> BacktestResult:
        # 1. Load all data at once
        df = await self._load_data_to_dataframe(config)
        
        # 2. Calculate indicators vectorized
        df = self._calculate_indicators(df, config.strategy)
        
        # 3. Generate signals vectorized
        df = self._generate_signals(df, config.strategy)
        
        # 4. Calculate P&L vectorized
        df = self._calculate_pnl(df, config)
        
        # 5. Calculate metrics
        metrics = self._calculate_metrics(df)
        
        return BacktestResult(metrics=metrics, trades=df[df['signal'] != 0])
```

### 2. 🟡 HIGH: Graceful Cancellation
**Impact**: UX improvement
**Effort**: Low (1 day)

```python
# NEW: Cancellation token
class BacktestRunner:
    def __init__(self):
        self._cancel_event = asyncio.Event()
    
    async def run(self, config):
        for chunk in data_stream:
            if self._cancel_event.is_set():
                raise BacktestCancelled()
            # Process chunk
    
    def cancel(self):
        self._cancel_event.set()
```

### 3. 🟡 HIGH: Hybrid Mode (Fast + Accurate)
**Impact**: Best of both worlds
**Effort**: Medium (2 days)

```python
# NEW: Hybrid execution
class HybridBacktestEngine:
    async def run(self, config):
        # Phase 1: Vectorized pre-scan (find signal points)
        signal_timestamps = await self._vectorized_signal_scan(config)
        
        # Phase 2: Row-by-row only for signal points
        for timestamp in signal_timestamps:
            result = await self._detailed_execution(timestamp)
            trades.append(result)
```

### 4. 🟢 MEDIUM: Checkpointing
**Impact**: Resilience
**Effort**: Medium (2 days)

```python
# NEW: Checkpoint support
class CheckpointedBacktest:
    async def run(self, config, checkpoint_interval=10000):
        checkpoint = await self._load_checkpoint(config.run_id)
        
        for i, candle in enumerate(data_stream):
            if i < checkpoint.last_index:
                continue  # Skip already processed
            
            # Process candle
            
            if i % checkpoint_interval == 0:
                await self._save_checkpoint(i, portfolio_state)
```

### 5. 🟢 MEDIUM: Pre-computed Indicators
**Impact**: Faster repeated runs
**Effort**: Low (1 day)

```python
# NEW: Materialized indicator views
CREATE MATERIALIZED VIEW candles_with_indicators AS
SELECT 
    *,
    AVG(close) OVER (ORDER BY time ROWS 10 PRECEDING) as ema_10,
    AVG(close) OVER (ORDER BY time ROWS 30 PRECEDING) as ema_30
FROM market_data;
```

---

## Recommended Implementation Path

### Phase 1: Quick Wins (This Week)
1. ✅ Add `run_backtest_and_wait` MCP tool (Done)
2. ⬜ Add cancellation token to BacktestService
3. ⬜ Pre-compute indicator columns in pandas before loop

### Phase 2: Vectorized Engine (Next Week)
1. ⬜ Create `VectorizedBacktestEngine` class
2. ⬜ Implement vectorized MA crossover strategy
3. ⬜ Add hybrid mode for complex strategies

### Phase 3: Production Hardening
1. ⬜ Checkpointing support
2. ⬜ Walk-forward optimization
3. ⬜ Multi-asset support

---

## Performance Targets

| Metric | Current | Target | Best-in-Class |
|--------|---------|--------|---------------|
| 500K candles | 30-60s | <5s | 0.5s |
| 1M candles | 60-120s | <10s | 1s |
| Memory (500K) | ~100MB | ~500MB | ~500MB |
| Startup time | 2-3s | 2-3s | <1s |
