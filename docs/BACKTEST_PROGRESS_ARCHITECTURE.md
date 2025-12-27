# RiseTrader Backtest Progress Architecture

## Overview

Long-running backtests now support real-time progress updates through multiple channels:

```
┌──────────────┐     POST /runs      ┌──────────────┐     Background Task     ┌─────────────┐
│    Client    │ ──────────────────► │     API      │ ─────────────────────► │  Backtest   │
│  (MCP/Web)   │ ◄── 202 + run_id ── │  (FastAPI)   │                        │   Engine    │
└──────────────┘                     └──────────────┘                        └─────────────┘
       │                                    │                                       │
       │                                    │           Progress Updates            │
       ▼                                    ▼                                       ▼
┌──────────────┐                     ┌──────────────┐     Redis Pub/Sub      ┌─────────────┐
│   Poll or    │ ◄───────────────── │     SSE      │ ◄──────────────────── │  Publisher  │
│   Stream     │    (real-time)      │  Endpoint    │                        │  Service    │
└──────────────┘                     └──────────────┘                        └─────────────┘
```

## Client Options

### 1. MCP Tools (Claude Desktop)

**For quick backtests (<3 months):**
```
run_backtest_and_wait(
    name="Test Strategy",
    symbol="CrudeOIL", 
    start_date="2024-11-01",
    end_date="2024-11-10",
    strategy="crude_oil_v3",
    timeframe="M5",
    timeout_seconds=120
)
```
- Polls internally until complete
- Returns full results when done
- Timeout returns run_id for manual polling

**For long backtests (manual polling):**
```
# Step 1: Create backtest (returns immediately)
create_backtest(...) → run_id

# Step 2: Poll for status
get_backtest_status(run_id) → status, progress

# Step 3: Get results when complete
get_backtest_results(run_id) → metrics
```

### 2. Web Dashboard (SSE)

```javascript
const eventSource = new EventSource('/api/backtesting/runs/{run_id}/stream');

eventSource.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    console.log(`Progress: ${data.progress_pct}%`);
});

eventSource.addEventListener('complete', (e) => {
    const data = JSON.parse(e.data);
    console.log('Backtest complete!', data.metrics);
    eventSource.close();
});
```

### 3. Direct API (REST polling)

```bash
# Create
curl -X POST /api/backtesting/runs -d '{"config_id": "..."}'
# Returns: {"id": "run-uuid", "status": "running"}

# Poll
curl /api/backtesting/runs/{run_id}/status
# Returns: {"status": "running", "candles_processed": 50000, ...}

# Get results
curl /api/backtesting/runs/{run_id}/metrics
# Returns: {"metrics": {...}, "final_capital": 10234.56}
```

## Implementation Files

### Backend Services
- `src/services/backtest_progress_service.py` - Redis pub/sub publisher/subscriber
- `src/services/backtesting/backtest_service.py` - Progress publishing during execution
- `src/utils/redis_client.py` - Redis connection management

### API Routes
- `src/api/routes/backtesting.py` - SSE streaming endpoint (`/runs/{run_id}/stream`)

### MCP Server
- `src/mcp/server.py` - New `run_backtest_and_wait` tool with internal polling

## Event Types (SSE/Redis)

| Event | Description | Fields |
|-------|-------------|--------|
| `connected` | Client connected to stream | run_id, status |
| `progress` | Periodic progress update | progress_pct, candles_processed, trades_count |
| `complete` | Backtest finished successfully | final_capital, metrics, trades_count |
| `error` | Backtest failed | error_message |
| `heartbeat` | Keep-alive ping (every 30s) | timestamp |

## Configuration

### Redis
```bash
REDIS_URL=redis://localhost:6379/0
```

### Progress Publishing
- Publish interval: Every 1000 candles
- Snapshot interval: Every 100 candles
- Heartbeat interval: 30 seconds

## Graceful Degradation

If Redis is unavailable:
- SSE streaming returns 503 with polling fallback message
- Progress publishing silently disabled (backtest continues)
- MCP tools fall back to REST polling
