# Backtest Max Candles Limit Implementation

**Date:** 2025-12-31
**Issue:** Backtests getting stuck in infinite loops, blocking FastAPI event loop and making API unresponsive
**Solution:** Implemented max_candles limit to prevent runaway backtest execution

## Problem Summary

Backtests were running indefinitely due to:
1. Agent opening positions but never closing them (100% capital deployed)
2. Agent making endless HOLD decisions with no exit strategy
3. No timeout mechanism for backtest execution
4. No maximum candles limit

This caused:
- API becoming unresponsive (timeout after 30s)
- Backtest runs stuck in RUNNING status
- Need to manually mark as FAILED and restart API

## Solution Implemented

Added a **max_candles** parameter to backtest configurations with a default limit of **150,000 candles**.

### Changes Made

#### 1. Database Model (`src/database/models/backtest.py`)
```python
max_candles = Column(Integer, nullable=False, default=150000)  # Prevent infinite loops
```

#### 2. Backtest Service (`src/services/backtesting/backtest_service.py`)

Added limit check in main replay loop:
```python
# Check max candles limit to prevent infinite loops
if candles_processed > config.max_candles:
    logger.warning(
        "max_candles_limit_reached",
        run_id=str(run.id),
        candles_processed=candles_processed,
        max_candles=config.max_candles,
    )
    # Mark run as TIMEOUT and break
    run.status = RunStatus.TIMEOUT
    run.error_message = f"Exceeded max candles limit ({config.max_candles})"
    break
```

#### 3. API Models (`src/api/models/backtesting_models.py`)

Added parameter to request/response models:
```python
max_candles: int = Field(
    default=150000, gt=0, description="Maximum candles to process (prevents infinite loops)"
)
```

#### 4. API Route (`src/api/routes/backtesting.py`)

Updated configuration creation to pass max_candles:
```python
config = await service.create_configuration(
    # ... other params ...
    max_candles=request.max_candles,
    config_params=request.config_params,
)
```

#### 5. Database Migration

Added column via SQL:
```sql
ALTER TABLE backtest_configurations
ADD COLUMN IF NOT EXISTS max_candles INTEGER NOT NULL DEFAULT 150000;
```

Created migration file: `alembic/versions/003_add_max_candles_to_backtest_config.py`

## Testing

1. **Database Verification:**
   ```bash
   docker-compose exec postgres psql -U postgres -d risetrader -c "\d backtest_configurations"
   ```
   Result: `max_candles | integer | not null | 150000`

2. **API Health Check:**
   ```bash
   curl http://localhost:8003/health
   ```
   Result: `{"status":"healthy","version":"1.0.0"}`

## Impact

- **Existing configurations:** All get default value of 150,000 candles
- **New configurations:** Can specify custom limit via API
- **Stuck backtests:** Will now timeout after processing max_candles
- **API stability:** No more infinite loops blocking event loop

## Limits

**Default: 150,000 candles**

At 5-minute candles:
- 150,000 candles = ~520 days (~1.4 years)
- This is reasonable for most backtests

At 1-minute candles:
- 150,000 candles = ~104 days (~3.5 months)

Users can adjust this limit when creating configurations if needed.

## Related Issues Fixed

This also addresses:
- API timeout errors ("timeout of 30000ms exceeded")
- Stuck backtest runs in RUNNING status
- Need to manually restart API when backtests hang

## Future Enhancements

Still needed:
1. **Graceful shutdown handler** - Mark RUNNING backtests as FAILED on API shutdown
2. **Agent exit strategy** - Improve agent logic to close positions appropriately
3. **Capital rebalancing** - Prevent 100% deployment blocking all trades
4. **Time-based timeout** - Add maximum execution time in addition to candle limit

## Files Changed

1. `/src/database/models/backtest.py`
2. `/src/services/backtesting/backtest_service.py`
3. `/src/api/models/backtesting_models.py`
4. `/src/api/routes/backtesting.py`
5. `/alembic/versions/003_add_max_candles_to_backtest_config.py` (new)

## Deployment Notes

- ✅ Database migration applied successfully
- ✅ API restarted and healthy
- ✅ Existing configurations updated with default value
- ⚠️ No code changes needed for existing backtest runs - they will pick up the limit automatically

## Example Usage

When creating a backtest configuration, users can now specify:

```json
{
  "name": "Long-term Backtest",
  "symbol": "CrudeOIL",
  "start_date": "2020-01-01T00:00:00Z",
  "end_date": "2024-12-31T23:59:59Z",
  "initial_capital": "10000.00",
  "execution_mode": "synthetic_fast",
  "max_candles": 200000,  // Custom limit for longer backtests
  // ... other params ...
}
```

For shorter backtests or testing:
```json
{
  "max_candles": 10000,  // Limit to ~35 days at M5 timeframe
}
```
