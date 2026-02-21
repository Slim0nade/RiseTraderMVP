# LLM Backtest Performance Crisis

**Date:** 2026-01-04
**Severity:** 🔴 CRITICAL
**Issue:** LLM-based agent backtests taking **3+ minutes per candle**, causing infinite loops and system lockup

## What Happened

Two backtests were running in parallel using the LLM-based trading agent (`mistral:7b-instruct`). Both got stuck in infinite HOLD loops and were blocking the entire system.

### The Numbers

**Processing Time per Candle:**
```
"processing_time_ms": 199736  // 199.7 seconds = 3.3 minutes
```

**At this rate:**
- **1 candle** = 3.3 minutes
- **1,000 candles** = 55 hours (2.3 days)
- **10,000 candles** = 23 days
- **150,000 candles** = **312 DAYS** ⚠️

**For comparison:**
- Synthetic strategies (no LLM): ~10-50ms per candle
- That's **4,000× to 20,000× faster**

## The Two Stuck Backtests

### Run 1: `f28eea9e-c95c-469d-b865-7b071eefc002`

**Portfolio State:**
- Starting capital: ~$10,000 (estimated)
- Cash balance: $172.96
- Total value: $7,219.05
- Unrealized P&L: -$6.26
- Realized P&L: **-$727.22** (lost 7.3%)
- Buying power: $166.70
- Status: Making HOLD decisions, but could still trade

**Problem:**
- Agent keeps making HOLD decisions even though it has buying power
- Possibly because positions are underwater (-$727 realized losses)
- Processing at 3 minutes per candle

### Run 2: `18aa075c-d8a1-4af7-95ed-b38169ebfa29`

**Portfolio State:**
- Starting capital: ~$10,000 (estimated)
- Cash balance: **-$1,020.17** ⚠️ (NEGATIVE - margin or bug?)
- Total value: $10,781.79
- Unrealized P&L: **+$783.99** (profitable! +7.8%)
- Realized P&L: $0.00 (no trades closed)
- Buying power: **$0.00** (100% deployed)
- Status: **Stuck in infinite HOLD loop**

**Problem:**
- 100% capital deployed in open positions
- No buying power to open new trades
- Agent correctly identifies this: `"insufficient_buying_power_for_long"`
- But has no exit strategy to close positions
- Keeps making HOLD decisions forever
- Each HOLD still calls LLM (3 minutes!)

**Agent's Rationale (from logs):**
```json
{
  "action": "hold",
  "conviction": 0.7,
  "direction": "LONG",
  "rationale": "The price is currently trading above the SMA_20 and SMA_50...",
  "key_factors": [
    "Price above SMA_20 and SMA_50",
    "RSI not overbought",
    "MACD line above signal line"
  ]
}
```

The agent is making **reasonable technical analysis**, but:
1. It takes 3 minutes to generate this decision
2. It never decides to close positions to free up capital
3. It just keeps saying HOLD forever

## Why It's So Slow

### LLM Call for Every Candle

```python
# agent_integrator.py (estimated flow)
async def get_agent_decision(tick):
    # Build context (indicators, portfolio state, etc.)
    context = build_agent_context(tick)

    # Call Ollama API (REMOTE SERVER at 75.154.254.174:11434)
    response = await ollama_client.chat(
        model="mistral:7b-instruct",
        messages=[...],
        context=context  # Huge JSON blob
    )

    # Parse decision
    return parse_decision(response)
```

**Bottlenecks:**
1. **Network latency** - Calling remote Ollama server (VPS)
2. **LLM inference** - Mistral 7B takes ~30-60s to generate response
3. **Large context** - Sending huge JSON with indicators, positions, etc.
4. **No caching** - Every candle calls the LLM from scratch

### Context Size

From the logs, the `input_data` is **26,055 characters**:
```json
{
  "symbol": "CrudeOIL",
  "current_price": 77.53,
  "cash_balance": -1020.17,
  "buying_power": 0.0,
  "indicators": {
    "SMA_20": 77.4615,
    "SMA_50": ...,
    "RSI_14": ...,
    "MACD": ...,
    "BB_upper": ...,
    "BB_lower": ...,
    "ATR_14": ...,
    "volume_sma_20": ...
  },
  "open_positions": [ /* Massive array of all positions */ ],
  "recent_trades": [ /* History */ ],
  "portfolio_summary": { /* Stats */ }
}
```

This **26KB context** gets sent to the LLM for **every single candle**.

## System Impact

### Resource Consumption

**CPU:**
- 2 backtests × 3 minutes per candle = **100% CPU usage**
- No CPU left for HTTP requests
- API health checks timing out

**Memory:**
- Each backtest loads all indicators, positions, history
- 2 backtests × ~500MB = ~1GB
- Plus LLM context caching

**Database:**
- 2 active connections (one per backtest)
- Inserting snapshots every 10 candles
- Inserting decision logs every candle
- At 3 min/candle, that's **48 inserts per hour per backtest**

### Why API Became Unresponsive

```
Timeline:
T+0s:   User makes HTTP request (health check)
T+0s:   FastAPI tries to handle request
T+0s:   Event loop is blocked by Backtest 1 (processing candle, 3 min wait)
T+180s: Backtest 1 yields (await database write)
T+180s: HTTP request FINALLY gets handled
T+180s: Returns "healthy" after 3-minute timeout!
```

The **async event loop was starved** because:
1. LLM calls are synchronous (blocking)
2. No yield points during 3-minute LLM call
3. Other tasks (HTTP requests) must wait

## Root Causes

### 1. No Exit Strategy

The agent has no logic to close positions when:
- Buying power is zero
- Positions are profitable (Run 2 had +$783 unrealized)
- Positions are underwater (Run 1 had -$727 realized)
- Market conditions change

**The agent prompt needs:**
```python
if buying_power == 0 and has_open_positions:
    # Consider closing some positions to free capital
    # Especially if profitable or stop-loss hit
    return {"action": "close", "position_id": ...}
```

### 2. LLM Called for Every Candle

There's no optimization:
- No decision caching ("if market hasn't changed much, reuse last decision")
- No batching (process multiple candles before deciding)
- No early exit ("if clearly no trade, skip LLM call")

**Should be:**
```python
# Check if we even need to call LLM
if buying_power == 0 and not should_exit_positions():
    return {"action": "hold"}  # Skip LLM call

# Only call LLM for real decisions
if significant_market_change or can_open_position:
    decision = await call_llm(...)
```

### 3. Remote LLM Server

Calling Ollama on remote VPS adds **network latency**:
- Local: ~10-30s for Mistral 7B
- Remote: ~60-180s (network + inference)

**Should use:**
- Local Ollama instance (if possible)
- Smaller/faster model (Llama 3.2 3B)
- Or synthetic strategies for backtesting

### 4. No Concurrency Limits

System allowed 2 LLM backtests to start simultaneously:
- Each takes 100% CPU for 3 minutes
- They fight for resources
- System crawls to a halt

## Immediate Fixes Applied

✅ **Stopped both backtests** - Marked as FAILED in database
✅ **Restarted API** - Killed background tasks
✅ **Verified clean state** - No RUNNING backtests remain

## Required Fixes

### Priority 1: Prevent LLM Backtest Chaos

#### A. Add Execution Mode Validation

```python
# In backtest API route
@router.post("/runs")
async def run_backtest(request: RunBacktestRequest, ...):
    config = await get_config(request.config_id)

    # BLOCK LLM backtests with large datasets
    if config.execution_mode == ExecutionMode.FULL_PIPELINE:
        total_candles = await estimate_candles(
            config.symbol,
            config.start_date,
            config.end_date,
            request.timeframe
        )

        if total_candles > 1000:  # Limit LLM backtests to 1000 candles max
            raise HTTPException(
                status_code=400,
                detail=f"LLM backtests limited to 1,000 candles. "
                       f"Your range has {total_candles:,} candles. "
                       f"Use synthetic_fast mode or reduce date range."
            )
```

#### B. Add Concurrency Limit

```python
# Before starting any backtest
active_backtests = await db.scalar(
    select(func.count(BacktestRun.id)).where(
        BacktestRun.status == RunStatus.RUNNING
    )
)

if active_backtests >= MAX_CONCURRENT_BACKTESTS:
    raise HTTPException(
        status_code=429,
        detail=f"Maximum concurrent backtests ({MAX_CONCURRENT_BACKTESTS}) reached. "
               f"Please wait for existing runs to complete."
    )
```

#### C. Add Decision Caching

```python
# In agent integrator
class AgentIntegrator:
    def __init__(self):
        self.last_decision = None
        self.last_decision_candle = None
        self.decision_cache_candles = 10  # Reuse decision for 10 candles

    async def get_decision(self, tick, candle_num):
        # If market hasn't changed much, reuse last decision
        if (self.last_decision and
            candle_num - self.last_decision_candle < self.decision_cache_candles):

            # Simple check: price within 0.5% of last decision
            price_change_pct = abs(
                (tick.close - self.last_decision_price) / self.last_decision_price
            )

            if price_change_pct < 0.005:  # <0.5% change
                logger.info("reusing_cached_decision")
                return self.last_decision

        # Otherwise, call LLM
        decision = await self._call_llm_agent(tick)
        self.last_decision = decision
        self.last_decision_candle = candle_num
        self.last_decision_price = tick.close

        return decision
```

### Priority 2: Add Agent Exit Logic

Update the agent prompt to include exit conditions:

```python
AGENT_PROMPT_TEMPLATE = """
You are a trading agent managing a portfolio. Your current state:

Portfolio:
- Cash: ${cash_balance}
- Buying Power: ${buying_power}
- Open Positions: {num_positions}
- Unrealized P&L: ${unrealized_pnl}

IMPORTANT EXIT RULES:
1. If buying_power is $0 or negative:
   - You MUST consider closing profitable positions to free capital
   - Look for positions with profit > 2%
   - Return: {{"action": "close", "position_id": "...", "reason": "Free capital"}}

2. If a position has unrealized P&L < -5%:
   - Close it to prevent further losses
   - Return: {{"action": "close", "position_id": "...", "reason": "Stop loss"}}

3. If a position has unrealized P&L > 10%:
   - Consider taking profit
   - Return: {{"action": "close", "position_id": "...", "reason": "Take profit"}}

4. Only return "hold" if:
   - No positions need closing
   - No clear entry signal
   - Buying power is available but market conditions are unclear

Current market: ...
"""
```

### Priority 3: Performance Optimizations

#### A. Use Faster Model

```yaml
# config/agents/trading_agent.yaml
model: "llama3.2:3b"  # Instead of mistral:7b-instruct
# Llama 3.2 3B is 2-3× faster and almost as good
```

#### B. Reduce Context Size

```python
# Only send last 5 positions, not all
context = {
    "symbol": symbol,
    "price": current_price,
    "indicators": indicators,  # Keep full indicators
    "open_positions": positions[-5:],  # Only last 5
    "recent_trades": trades[-10:],  # Only last 10
    # Remove verbose fields
}
```

#### C. Skip LLM When Obvious

```python
async def get_decision(self, tick):
    # Fast path: If no buying power and no exit conditions
    if self.portfolio.buying_power <= 0:
        # Check if any positions should be closed
        if not self._should_close_any_position():
            return {"action": "hold"}  # Skip LLM

    # Otherwise call LLM
    return await self._call_llm(tick)
```

## Recommendations

### For Backtesting

**DON'T use LLM agents for backtesting unless:**
1. ✅ Testing on **< 1,000 candles** (small sample)
2. ✅ You have **local Ollama** instance (not remote)
3. ✅ You implement **decision caching** (reuse for 10+ candles)
4. ✅ You use **fast model** (3B params, not 7B+)

**DO use synthetic strategies for backtesting:**
- MA crossover
- RSI
- Trend following
- Mean reversion
- **1,000-10,000× faster**

### For Live Trading

LLM agents are fine for live trading because:
- New candles come every 1-5 minutes
- 30-60 seconds to generate decision is acceptable
- Only 1 decision per candle (not 150,000)

### Hybrid Approach

```python
# Synthetic strategy for backtesting
backtest_config = {
    "execution_mode": "synthetic_fast",
    "strategy": "ma_crossover",
    "params": {"fast_period": 10, "slow_period": 30}
}

# LLM agent for live trading
live_config = {
    "execution_mode": "full_pipeline",
    "agent": "trading_agent_llama3.2:3b"
}
```

## Configuration Changes Needed

### 1. Set Max Candles for LLM Backtests

```python
# In config or environment
LLM_BACKTEST_MAX_CANDLES = 1000  # Hard limit
SYNTHETIC_BACKTEST_MAX_CANDLES = 150000  # Current limit
```

### 2. Set Concurrency Limits

```python
MAX_CONCURRENT_BACKTESTS = 2
MAX_CONCURRENT_LLM_BACKTESTS = 1  # Only 1 LLM backtest at a time
```

### 3. Add Timeout

```python
# In backtest service
BACKTEST_TIMEOUT_HOURS = 2  # Kill after 2 hours

if time_elapsed > BACKTEST_TIMEOUT_HOURS:
    run.status = RunStatus.TIMEOUT
    run.error_message = "Execution timeout"
    break
```

## Testing LLM Performance

Before running large LLM backtests, test performance:

```bash
# Test 100 candles first
curl -X POST http://localhost:8003/api/v1/backtesting/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "YOUR_CONFIG",
    "timeframe": "M5",
    "synthetic_strategy": null
  }'

# Monitor processing time
# If >1 min per candle, DON'T scale to 150k candles
```

## Summary

| Aspect | Issue | Fix |
|--------|-------|-----|
| **Performance** | 3+ min/candle | Use synthetic strategies for backtesting |
| **Exit strategy** | No position closing | Update agent prompt with exit rules |
| **Concurrency** | Unlimited parallel runs | Limit to 2 total, 1 LLM max |
| **Validation** | No candle count check | Block LLM backtests >1000 candles |
| **Optimization** | No caching | Cache decisions for 10 candles |
| **Model** | Slow 7B model | Use 3B model or local inference |

---

**Bottom Line:** LLM agents are **NOT suitable for backtesting** large datasets. Use synthetic strategies for backtesting, save LLMs for live trading where latency is acceptable.
