# Quickstart: Async Optimization Engine with SSE Notifications

**Feature**: 008-async-optimization-sse  
**Branch**: `008-async-optimization-sse`

## Overview

This feature adds:
1. **Async Job Queue**: Long-running optimizations run in background, no MCP timeout
2. **Deterministic Grid Search**: Tests ALL parameter combinations, reproducible results
3. **Optimization History**: Results persist to database across sessions
4. **SSE Events**: Real-time notifications for job progress and price alerts
5. **Price Alerts**: Monitor positions for key price levels

## Prerequisites

- RiseTrader API running (`docker-compose up api`)
- PostgreSQL database with migrations applied
- Redis running (`docker-compose up redis`)
- MCP server connected to Claude Code

## New Dependencies

Add to `requirements.txt`:
```
sse-starlette>=1.6.0
```

## Database Migration

Run the migration to create new tables:
```bash
docker-compose exec api alembic upgrade head
```

New tables:
- `optimization_runs` - Persisted optimization results
- `price_alerts` - Configured price level monitors

## MCP Tools

### Submit Async Optimization

```python
# Via MCP tool
result = await mcp.optimize_strategy_async(
    symbol="CrudeOIL",
    timeframe="H1",
    start_date="2024-01-01",
    end_date="2024-12-31",
    strategy="crude_oil_v3",
    param_grid={
        "atr_threshold": [0.5, 1.0, 1.5],
        "risk_reward": [1.5, 2.0, 2.5]
    },
    optimization_target="sharpe_ratio"
)
# Returns: {"job_id": "abc123", "status": "pending", "total_combinations": 9}
```

### Poll Job Progress

```python
# Check status periodically
status = await mcp.get_optimization_status(job_id="abc123")
# Returns: {
#   "status": "running",
#   "progress_pct": 55.5,
#   "combinations_tested": 5,
#   "total_combinations": 9,
#   "best_params": {"atr_threshold": 1.0, "risk_reward": 2.0},
#   "best_metric_value": 1.45
# }
```

### Get Final Results

```python
# After status == "completed"
results = await mcp.get_optimization_results(job_id="abc123")
# Returns full results with all tested combinations
```

### Set Price Alerts

```python
# Monitor position for key levels
await mcp.set_price_alerts(
    ticket=12345,
    liquidity_sweep_price=58.50,
    breakeven_price=59.00,
    key_levels=[
        {"price": 57.00, "direction": "below", "label": "Support"}
    ]
)
```

## SSE Event Stream

Connect to receive real-time events:

```bash
curl -N "http://localhost:8003/api/events/stream"
```

Event types:
- `job_started` - Optimization began
- `job_progress` - Progress update (every 5%)
- `job_complete` - Optimization finished
- `job_failed` - Optimization error
- `price_alert` - Price crossed alert level
- `fast_move` - Rapid price movement detected (>2× ATR in 5 min)
- `liquidity_sweep` - Stop hunting pattern detected

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/optimizer/jobs` | Submit new job |
| GET | `/api/optimizer/jobs` | List jobs |
| GET | `/api/optimizer/jobs/{id}` | Get job status |
| DELETE | `/api/optimizer/jobs/{id}` | Cancel job |
| GET | `/api/optimizer/jobs/{id}/results` | Get results |
| GET | `/api/optimizer/history` | List past runs |
| GET | `/api/optimizer/history/{id}` | Get specific run details |
| GET | `/api/events/stream` | SSE event stream |
| GET | `/api/events/since/{timestamp}` | Polling fallback for events |
| POST | `/api/alerts` | Create price alert |
| POST | `/api/alerts/batch` | Create multiple alerts |
| GET | `/api/alerts` | List all alerts |
| GET | `/api/alerts/{id}` | Get alert by ID |
| DELETE | `/api/alerts/{id}` | Delete specific alert |
| GET | `/api/alerts/position/{ticket}` | Get position alerts |
| DELETE | `/api/alerts/position/{ticket}` | Clear position alerts |

## Testing

### Run All Feature 008 Tests

```bash
# Run all unit tests for this feature
pytest tests/unit/test_optimization_job.py \
       tests/unit/test_grid_search.py \
       tests/unit/test_optimization_history.py \
       tests/unit/test_sse_events.py \
       tests/unit/test_price_alerts.py \
       tests/unit/test_autonomous_monitoring.py -v

# Run all integration tests for this feature
pytest tests/integration/test_optimization_async.py \
       tests/integration/test_optimization_history.py \
       tests/integration/test_optimization_sse.py \
       tests/integration/test_price_alerts.py \
       tests/integration/test_autonomous_monitoring.py -v

# Run everything together
pytest tests/unit/test_optimization*.py \
       tests/unit/test_grid_search.py \
       tests/unit/test_sse_events.py \
       tests/unit/test_price_alerts.py \
       tests/unit/test_autonomous_monitoring.py \
       tests/integration/test_optimization*.py \
       tests/integration/test_price_alerts.py \
       tests/integration/test_autonomous_monitoring.py -v
```

### Run by User Story

```bash
# User Story 1: Async Job Queue
pytest tests/unit/test_optimization_job.py tests/integration/test_optimization_async.py -v

# User Story 2: Deterministic Grid Search
pytest tests/unit/test_grid_search.py -v

# User Story 3: History Persistence
pytest tests/unit/test_optimization_history.py tests/integration/test_optimization_history.py -v

# User Story 4: SSE Event Stream
pytest tests/unit/test_sse_events.py tests/integration/test_optimization_sse.py -v

# User Story 5: Price Alerts
pytest tests/unit/test_price_alerts.py tests/integration/test_price_alerts.py -v

# User Story 6: Autonomous Monitoring
pytest tests/unit/test_autonomous_monitoring.py tests/integration/test_autonomous_monitoring.py -v
```

### Run with Coverage

```bash
# Coverage for all feature 008 services
pytest tests/unit/test_optimization*.py \
       tests/unit/test_grid_search.py \
       tests/unit/test_sse_events.py \
       tests/unit/test_price_alerts.py \
       tests/unit/test_autonomous_monitoring.py \
       --cov=src/services/optimization_job_service \
       --cov=src/services/sse_event_service \
       --cov=src/services/price_alert_service \
       --cov=src/utils/grid_search \
       --cov=src/utils/sse_events \
       --cov-report=term-missing -v
```

## Key Files

| File | Purpose |
|------|---------|
| `src/database/models/optimization.py` | OptimizationRun, PriceAlert models |
| `src/services/optimization_job_service.py` | Job queue and worker |
| `src/services/price_alert_service.py` | Price monitoring |
| `src/api/routes/events.py` | SSE endpoint |
| `src/api/routes/optimizer.py` | Updated with async endpoints |
| `src/mcp/server.py` | New MCP tools |

## Troubleshooting

**Job stuck at "pending"**:
- Check Redis is running: `redis-cli ping`
- Check API logs for errors: `docker-compose logs api`

**SSE not receiving events**:
- Verify connection: `curl -v http://localhost:8003/api/events/stream`
- Check Redis pub/sub: `redis-cli subscribe sse:events`

**Optimization too slow**:
- Reduce grid size (max 10,000 combinations)
- Use larger timeframe (H4 instead of M5)
- Shorten date range for initial testing

## Next Steps

1. Run database migration
2. Test with small optimization (9 combinations)
3. Connect SSE stream in Claude Code
4. Verify price alerts with open position
