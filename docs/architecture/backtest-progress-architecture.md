# Backtest Progress Architecture

## Problem Statement

Backtests process 100k-500k+ candles, taking 1-10+ minutes. Different clients have different capabilities:

| Client | Streaming Support | Timeout Handling | Best Approach |
|--------|------------------|------------------|---------------|
| MCP | ❌ No | Has timeouts | Polling |
| Web Dashboard | ✅ SSE/WebSocket | N/A | Real-time SSE |
| CLI | ✅ Both | User-controlled | SSE or Polling |

## Solution: Multi-Channel Progress Reporting

```
┌──────────────┐     ┌─────────────────────────────────────────────────────┐
│   MCP Tool   │     │                    API SERVER                        │
│              │     │                                                      │
│ create_      │────▶│  POST /runs                                          │
│ backtest()   │◀────│   └─▶ Creates run, spawns task, returns 202 + run_id │
│              │     │                                                      │
│ Returns      │     │                         │                            │
│ immediately! │     │                         ▼                            │
│              │     │  ┌─────────────────────────────────────────────────┐ │
│              │     │  │ BACKGROUND TASK                                 │ │
│ poll with    │     │  │                                                 │ │
│ get_backtest │────▶│  │  for candle in data:                            │
│ _status()    │◀────│  │    process(candle)                              │ │
│              │     │  │    if n % 100:  UPDATE PostgreSQL               │ │
└──────────────┘     │  │    if n % 1000: PUBLISH to Redis                │ │
                     │  │                                                 │ │
┌──────────────┐     │  └─────────────────────────────────────────────────┘ │
│ Web Dashboard│     │                         │                            │
│              │     │           ┌─────────────┴─────────────┐              │
│ EventSource  │────▶│           ▼                           ▼              │
│ /stream      │◀────│    ┌──────────────┐          ┌──────────────┐        │
│              │     │    │  PostgreSQL  │          │    Redis     │        │
└──────────────┘     │    │  (durable)   │          │  (pub/sub)   │        │
                     │    └──────────────┘          └──────────────┘        │
                     └──────────────────────────────────────────────────────┘
```

## Implementation Components

### 1. Database Updates (Every 100 candles)
- Update `candles_processed` in BacktestRun table
- Calculate and store `progress_pct`
- Source of truth for polling clients

### 2. Redis Pub/Sub (Every 1000 candles)
- Channel: `backtest:progress:{run_id}`
- Real-time updates for streaming clients
- Graceful degradation if Redis unavailable

### 3. SSE Endpoint
- `GET /api/backtesting/runs/{run_id}/stream`
- Subscribes to Redis channel
- Returns `text/event-stream` content type
- Heartbeat every 30 seconds

### 4. MCP Tools (Polling-based)
- `create_backtest`: Returns immediately with run_id
- `get_backtest_status`: Polls database for current state
- `wait_for_backtest`: Optional convenience tool with internal polling

## Redis Event Schema

### Progress Event
```json
{
    "type": "progress",
    "run_id": "uuid",
    "timestamp": "2024-01-15T10:30:00Z",
    "status": "running",
    "candles_processed": 50000,
    "total_candles": 125000,
    "progress_pct": 40.0,
    "trades_count": 15,
    "current_capital": 10234.56
}
```

### Complete Event
```json
{
    "type": "complete",
    "run_id": "uuid",
    "status": "completed",
    "total_candles": 125000,
    "trades_count": 42,
    "final_capital": 11234.56,
    "metrics": {
        "total_return_pct": 12.35,
        "sharpe_ratio": 1.45,
        "max_drawdown_pct": 5.2
    }
}
```

## MCP Tool Behavior

### Current Problem
```
MCP create_backtest() ──▶ API ──▶ Background task starts
         │                              │
         ▼                              │
    ⏱️ Timeout (30s)                    │
         │                              ▼
    ❌ "No result"              Backtest completes (5 min)
```

### Fixed Behavior
```
MCP create_backtest() ──▶ API ──▶ Background task starts
         │                              │
         ▼                              │
    ✅ Returns immediately:             │
    {                                   │
      "run_id": "abc-123",              │
      "status": "running",              │
      "message": "Backtest started..."  │
    }                                   │
                                        ▼
User calls get_backtest_status() ◀─── Backtest completes
         │
         ▼
    ✅ Returns final results
```

## Files Modified

1. `src/services/backtest_progress_service.py` - Redis pub/sub publisher/subscriber
2. `src/api/routes/backtesting.py` - SSE streaming endpoint
3. `src/services/backtesting/backtest_service.py` - Progress publishing in main loop
4. `src/mcp/server.py` - Updated create_backtest tool behavior
5. `src/utils/redis_client.py` - Added get_redis_client() helper
