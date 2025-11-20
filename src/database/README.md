# RiseTrader Database Layer

Complete async database abstraction for the RiseTrader algorithmic trading platform.

## Overview

This module provides:
- **11 SQLAlchemy models** for all database tables
- **5 specialized repositories** with optimized queries
- **Async database configuration** with connection pooling
- **Type-safe operations** with full type hints
- **Production-ready** error handling and transactions

## Database Stats

- **PostgreSQL 17** on port 5433
- **13.5M+ market data records** (time-series optimized)
- **70K+ indicator records**
- **1,130 open positions**
- **8,171 backtest trades**

## Quick Start

### 1. Initialize Database

```python
from database import initialize_database, get_session

# Initialize with default settings
db = initialize_database()

# Or with custom configuration
db = initialize_database(
    database_url="postgresql+asyncpg://user:pass@localhost:5433/risetrader",
    echo=True,  # Enable SQL logging
    pool_size=20,
    max_overflow=10
)
```

### 2. Use with Repositories

```python
from database import MarketDataRepository, get_database

async def get_latest_prices():
    db = get_database()

    async with db.get_session() as session:
        repo = MarketDataRepository(session)

        # Get latest tick
        latest = await repo.get_latest_tick(
            symbol="CrudeOIL",
            timeframe="1m"
        )

        print(f"Price: ${latest.close}")
```

### 3. Use with FastAPI

```python
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_session, MarketDataRepository

app = FastAPI()

@app.get("/market/{symbol}/latest")
async def get_latest_price(
    symbol: str,
    session: AsyncSession = Depends(get_session)
):
    repo = MarketDataRepository(session)
    tick = await repo.get_latest_tick(symbol=symbol, timeframe="1m")
    return tick.to_dict()
```

## Models

All models use SQLAlchemy 2.0 async syntax with type hints.

### MarketData
OHLCV time-series data with 13.5M+ records.

```python
from database import MarketData

# Fields
tick.time          # datetime
tick.symbol        # str
tick.timeframe     # str ('1m', '5m', '1h', etc.)
tick.open          # Decimal
tick.high          # Decimal
tick.low           # Decimal
tick.close         # Decimal (alias for 'last')
tick.volume        # int
```

### Indicators
Technical indicators (RSI, MACD, Bollinger Bands, etc.)

```python
from database import Indicators

# Fields
indicators.rsi          # Decimal
indicators.macd         # Decimal
indicators.macd_signal  # Decimal
indicators.atr          # Decimal
indicators.bb_upper     # Decimal
indicators.bb_middle    # Decimal
indicators.bb_lower     # Decimal
indicators.ma_20        # Decimal
indicators.ma_50        # Decimal
indicators.ma_200       # Decimal
```

### OpenPosition
Currently active trading positions (1,130 records).

```python
from database import OpenPosition

# Fields
position.number        # str (order number)
position.symbol        # str
position.type          # str ('BUY' or 'SELL')
position.size          # Decimal
position.price         # Decimal
position.stop_loss     # Decimal
position.take_profit   # Decimal
position.last_profit   # Decimal

# Helpers
position.is_long       # bool
position.is_short      # bool
```

### TradingHistory
Completed trades with P&L tracking.

```python
from database import TradingHistory

# Fields
trade.symbol       # str
trade.order_type   # str
trade.volume       # Decimal
trade.price        # Decimal
trade.profit       # Decimal
trade.commission   # Decimal
trade.swap         # Decimal

# Helpers
trade.net_profit      # Decimal (after fees)
trade.is_profitable   # bool
```

### Forecast
ML model predictions with validation.

```python
from database import Forecast

# Fields
forecast.model_type          # str
forecast.model_version       # str
forecast.symbol              # str
forecast.forecast_horizon    # str ('1h', '4h', '1d')
forecast.predicted_price     # Decimal
forecast.confidence_lower    # Decimal
forecast.confidence_upper    # Decimal
forecast.actual_price        # Decimal (after validation)
forecast.is_validated        # bool

# Methods
forecast.validate_prediction(actual_price)
```

### Other Models
- `TradingSimulation` - Backtest results
- `OptimalTrade` - Backtest trades
- `NewsEvent` - Economic calendar
- `AccountInfo` - Account snapshots
- `ModelPerformance` - ML metrics

## Repositories

### BaseRepository

Generic CRUD operations for all models.

```python
from database import BaseRepository, MarketData

async with session:
    repo = BaseRepository(MarketData, session)

    # Get by ID
    record = await repo.get(123)

    # Get all with pagination
    records = await repo.get_all(limit=100, offset=0)

    # Create
    new_record = await repo.create({"symbol": "EURUSD", ...})

    # Update
    updated = await repo.update(123, {"volume": 5000})

    # Delete
    deleted = await repo.delete(123)

    # Count
    total = await repo.count(symbol="EURUSD")
```

### MarketDataRepository

Time-series optimized queries for 13.5M+ records.

```python
from database import MarketDataRepository

async with session:
    repo = MarketDataRepository(session)

    # Get latest tick
    latest = await repo.get_latest_tick("CrudeOIL", timeframe="1m")

    # Get recent ticks
    ticks = await repo.get_latest_ticks("CrudeOIL", limit=100)

    # Get time range
    from datetime import datetime, timedelta
    end = datetime.utcnow()
    start = end - timedelta(hours=24)

    data = await repo.get_by_timeframe_range(
        symbol="CrudeOIL",
        timeframe="1h",
        start_time=start,
        end_time=end
    )

    # Get OHLCV aggregates
    agg = await repo.get_ohlcv_aggregates(
        symbol="CrudeOIL",
        start_time=start,
        end_time=end,
        timeframe="1m"
    )
    # Returns: {open, high, low, close, volume}

    # Bulk insert (optimized)
    count = await repo.bulk_insert_ticks([...])

    # Get symbols/timeframes
    symbols = await repo.get_symbols()
    timeframes = await repo.get_timeframes()
```

### IndicatorsRepository

Technical indicator queries.

```python
from database import IndicatorsRepository

async with session:
    repo = IndicatorsRepository(session)

    # Get latest indicators
    indicators = await repo.get_latest_indicators(
        symbol="CrudeOIL",
        timeframe="1h"
    )

    # Get indicator history
    rsi_history = await repo.get_rsi_history(
        symbol="CrudeOIL",
        timeframe="1h",
        limit=100
    )
    # Returns: [(time, rsi), ...]

    macd_history = await repo.get_macd_history(...)
    bb_history = await repo.get_bollinger_bands(...)
    ma_history = await repo.get_moving_averages(...)
```

### PositionsRepository

Position management and exposure tracking.

```python
from database import PositionsRepository

async with session:
    repo = PositionsRepository(session)

    # Get all open positions
    positions = await repo.get_open_positions()

    # Get by symbol
    crude_pos = await repo.get_positions_by_symbol("CrudeOIL")

    # Get by order number
    position = await repo.get_position_by_number("12345")

    # Close position
    closed = await repo.close_position(position.id)

    # Get summary
    summary = await repo.get_position_summary()
    # Returns: {total_positions, total_long, total_short, total_profit, symbols}

    # Calculate exposure
    exposure = await repo.get_total_exposure(symbol="CrudeOIL")
```

### ForecastsRepository

ML predictions and validation.

```python
from database import ForecastsRepository

async with session:
    repo = ForecastsRepository(session)

    # Get latest forecast
    forecast = await repo.get_latest_forecast(
        symbol="CrudeOIL",
        horizon="1h",
        model_type="XGBoost"
    )

    # Save forecast
    new_forecast = await repo.save_forecast({
        "model_type": "XGBoost",
        "symbol": "CrudeOIL",
        "predicted_price": Decimal("73.45"),
        ...
    })

    # Validate forecast
    validated = await repo.validate_forecast(
        forecast_id=123,
        actual_price=Decimal("73.50")
    )

    # Get ensemble prediction
    ensemble = await repo.get_ensemble_prediction(
        symbol="CrudeOIL",
        target_timestamp=target_time,
        horizon="1h"
    )

    # Get accuracy stats
    stats = await repo.get_forecast_accuracy_stats(
        model_type="XGBoost",
        symbol="CrudeOIL"
    )
    # Returns: {total_validated, mean_absolute_error, mean_percentage_error, ...}
```

### TradingHistoryRepository

Trade analytics and performance metrics.

```python
from database import TradingHistoryRepository

async with session:
    repo = TradingHistoryRepository(session)

    # Get performance metrics
    metrics = await repo.get_performance_metrics(
        symbol="CrudeOIL",
        start_date=start,
        end_date=end
    )
    # Returns: {
    #   total_trades, winning_trades, losing_trades,
    #   win_rate, total_profit, average_profit,
    #   profit_factor, ...
    # }

    # Get daily P&L
    daily_pnl = await repo.get_daily_pnl(start, end)

    # Get by symbol
    symbol_perf = await repo.get_symbol_performance()

    # Get recent trades
    recent = await repo.get_recent_trades(limit=50)

    # Calculate total P&L
    total_pnl = await repo.get_total_pnl(symbol="CrudeOIL")
```

## Configuration

### Environment Variables

```bash
# .env
DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader
```

### Connection Pooling

```python
db = initialize_database(
    pool_size=20,        # Maintain 20 connections
    max_overflow=10,     # Allow 10 extra connections
    pool_pre_ping=True,  # Test connection before use
    pool_recycle=3600    # Recycle after 1 hour
)
```

### Health Check

```python
is_healthy = await db.health_check()
```

## Performance Optimization

### Indexes

All tables have appropriate indexes:
- `market_data`: time, symbol, timeframe (composite)
- `indicators`: symbol, timeframe, time
- `forecasts`: symbol, model_type, target_timestamp
- `trading_history`: symbol, time

### Query Optimization

```python
# ✅ GOOD - Use indexes
data = await repo.get_by_timeframe_range(
    symbol="CrudeOIL",
    timeframe="1m",
    start_time=start,
    end_time=end
)

# ❌ BAD - Full table scan
all_data = await repo.get_all(limit=1000000)
```

### Bulk Operations

```python
# ✅ GOOD - Batch insert
await repo.bulk_insert_ticks(ticks_list)

# ❌ BAD - Individual inserts
for tick in ticks_list:
    await repo.create(tick)
```

## Error Handling

```python
from sqlalchemy.exc import IntegrityError, OperationalError

async with session:
    try:
        await repo.create(data)
    except IntegrityError:
        # Handle duplicate key errors
        pass
    except OperationalError:
        # Handle connection errors
        pass
```

## Testing

Run the example script:

```bash
cd src/database
python example_usage.py
```

## Migration (Alembic)

Generate migration:

```bash
alembic revision --autogenerate -m "Add new column"
```

Apply migration:

```bash
alembic upgrade head
```

## Architecture

```
src/database/
├── models/              # SQLAlchemy models
│   ├── base.py         # Base class and mixins
│   ├── market_data.py  # 13.5M records
│   ├── indicators.py   # 70K records
│   ├── positions.py    # 1,130 records
│   ├── forecasts.py    # ML predictions
│   └── ...
├── repositories/        # Data access layer
│   ├── base.py         # Generic CRUD
│   ├── market_data_repository.py
│   ├── indicators_repository.py
│   ├── positions_repository.py
│   ├── forecasts_repository.py
│   └── trading_history_repository.py
├── config.py           # Database configuration
├── example_usage.py    # Usage examples
└── README.md           # This file
```

## Best Practices

1. **Always use async/await** - All operations are async
2. **Use context managers** - Ensures proper session cleanup
3. **Leverage repositories** - Don't write raw SQL
4. **Batch operations** - Use bulk_insert for multiple records
5. **Filter early** - Use indexes (symbol, time, timeframe)
6. **Close connections** - Call `await db.close()` on shutdown
7. **Type hints** - Models and repos are fully typed

## Connection String Format

```
postgresql+asyncpg://[user]:[password]@[host]:[port]/[database]
```

Example:
```
postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader
```

## See Also

- [SQLAlchemy 2.0 Docs](https://docs.sqlalchemy.org/en/20/)
- [asyncpg Docs](https://magicstack.github.io/asyncpg/)
- [FastAPI Database Guide](https://fastapi.tiangolo.com/tutorial/sql-databases/)
