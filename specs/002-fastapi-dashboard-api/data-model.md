# Data Model: Dashboard API Service

**Feature**: 002-fastapi-dashboard-api
**Date**: 2025-11-24
**Status**: Phase 1 Complete

## Overview

This document defines the data models (entities) used by the Dashboard API Service. The API serves data from existing database tables via SQLAlchemy ORM models and exposes them through Pydantic response models to the React dashboard.

**Note**: Most database models already exist at `src/database/models/`. This feature focuses on API response models and any required enhancements to existing models.

---

## Core Entities

### 1. MarketData
**Purpose**: OHLCV time-series price data for trading symbols
**Database Model**: `src/database/models/market_data.py` (EXISTS)
**Table**: `market_data` (13.5M+ records)

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| time | DateTime (TZ) | Yes | Candlestick timestamp | ISO 8601 |
| symbol | String | Yes | Trading symbol | Non-empty, alphanumeric |
| import_symbol | String | Yes | Original symbol name | Non-empty |
| timeframe | Enum | Yes | Timeframe | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| source | Enum | Yes | Data source | BARCHART, MT4 |
| open | Decimal | Yes | Opening price | > 0 |
| high | Decimal | Yes | Highest price | >= open, low |
| low | Decimal | Yes | Lowest price | <= high, >= 0 |
| last (close) | Decimal | Yes | Closing price | > 0 |
| change | Decimal | Yes | Price change | Can be negative |
| change_percent | Decimal | Yes | Percentage change | Can be negative |
| volume | Integer | Yes | Trading volume | >= 0 |
| created_at | DateTime (TZ) | Yes | Record creation time | Auto-set |
| updated_at | DateTime (TZ) | Yes | Last update time | Auto-update |

#### Relationships
- **Indicators** (1:N): One market data point can have multiple technical indicator values

#### Indexes (Existing)
- Composite: `(symbol, timeframe, time)` - Primary query pattern
- Individual: `time`, `symbol`, `timeframe`, `source`, `import_symbol`

#### State Transitions
None - Immutable records (historical data)

---

### 2. Indicators
**Purpose**: Technical indicator values calculated from market data
**Database Model**: `src/database/models/indicators.py` (EXISTS)
**Table**: `indicators`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| market_data_id | Integer | Yes | Foreign key to market_data | Valid FK |
| rsi_14 | Decimal | No | Relative Strength Index (14-period) | 0-100 |
| macd_line | Decimal | No | MACD line value | Any |
| macd_signal | Decimal | No | MACD signal line | Any |
| macd_histogram | Decimal | No | MACD histogram | Any |
| sma_20 | Decimal | No | Simple Moving Average (20-period) | > 0 |
| sma_50 | Decimal | No | Simple Moving Average (50-period) | > 0 |
| ema_12 | Decimal | No | Exponential Moving Average (12-period) | > 0 |
| ema_26 | Decimal | No | Exponential Moving Average (26-period) | > 0 |
| bollinger_upper | Decimal | No | Bollinger Bands upper | > 0 |
| bollinger_middle | Decimal | No | Bollinger Bands middle | > 0 |
| bollinger_lower | Decimal | No | Bollinger Bands lower | > 0 |
| atr_14 | Decimal | No | Average True Range (14-period) | > 0 |

#### Relationships
- **MarketData** (N:1): Many indicators belong to one market data point

---

### 3. Account
**Purpose**: MT4 trading account information
**Database Model**: `src/database/models/account.py` (EXISTS)
**Table**: `account`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| account_number | String | Yes | MT4 account number | Non-empty |
| broker | String | Yes | Broker name | Non-empty |
| balance | Decimal | Yes | Account balance | >= 0 |
| equity | Decimal | Yes | Current equity | >= 0 |
| margin | Decimal | Yes | Used margin | >= 0 |
| free_margin | Decimal | Yes | Available margin | >= 0 |
| margin_level | Decimal | No | Margin level percentage | >= 0 |
| currency | String | Yes | Account currency | USD, EUR, etc. |
| leverage | Integer | No | Account leverage | > 0 |
| profit | Decimal | Yes | Unrealized profit/loss | Any |
| last_updated | DateTime (TZ) | Yes | Last sync from MT4 | Auto-update |

#### State Transitions
- Balance changes on trade close
- Equity updates in real-time with position P&L
- Margin updates on position open/close

---

### 4. Position
**Purpose**: Open trading positions
**Database Model**: `src/database/models/positions.py` (EXISTS)
**Table**: `open_positions`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| ticket | Integer | Yes | MT4 ticket number | Unique |
| symbol | String | Yes | Trading symbol | Non-empty |
| type | Enum | Yes | Position type | BUY, SELL |
| lots | Decimal | Yes | Position size (lots) | > 0 |
| open_price | Decimal | Yes | Entry price | > 0 |
| current_price | Decimal | Yes | Current market price | > 0 |
| stop_loss | Decimal | No | Stop loss price | > 0 or null |
| take_profit | Decimal | No | Take profit price | > 0 or null |
| open_time | DateTime (TZ) | Yes | Position open time | ISO 8601 |
| profit | Decimal | Yes | Unrealized profit/loss | Any |
| commission | Decimal | No | Broker commission | Any |
| swap | Decimal | No | Overnight swap | Any |
| comment | String | No | Position comment | Max 255 chars |

#### State Transitions
1. **Opened**: Position created in MT4 → Inserted into database
2. **Updated**: Price changes → Recalculate profit, update current_price
3. **Closed**: Position closed in MT4 → Moved to `trading_history`, deleted from `open_positions`

---

### 5. Trade
**Purpose**: Completed trading transactions
**Database Model**: `src/database/models/trading_history.py` (EXISTS)
**Table**: `trading_history`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| ticket | Integer | Yes | MT4 ticket number | Unique |
| symbol | String | Yes | Trading symbol | Non-empty |
| type | Enum | Yes | Trade type | BUY, SELL |
| lots | Decimal | Yes | Position size | > 0 |
| entry_price | Decimal | Yes | Entry price | > 0 |
| exit_price | Decimal | Yes | Exit price | > 0 |
| entry_time | DateTime (TZ) | Yes | Trade open time | ISO 8601 |
| exit_time | DateTime (TZ) | Yes | Trade close time | ISO 8601 |
| profit | Decimal | Yes | Realized profit/loss | Any |
| commission | Decimal | No | Total commission | Any |
| swap | Decimal | No | Total swap | Any |
| duration_seconds | Integer | No | Trade duration | >= 0 |
| comment | String | No | Trade comment | Max 255 chars |

#### Validation Rules
- `exit_time` must be >= `entry_time`
- `duration_seconds` = `exit_time` - `entry_time` (auto-calculated)
- For BUY: `profit` = (`exit_price` - `entry_price`) * `lots` * contract_size
- For SELL: `profit` = (`entry_price` - `exit_price`) * `lots` * contract_size

---

### 6. Forecast
**Purpose**: AI-generated price predictions
**Database Model**: `src/database/models/forecasts.py` (EXISTS)
**Table**: `forecasts`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| model_type | String | Yes | ML model name | XGBoost, TFT, LSTM, etc. |
| model_version | String | Yes | Model version | Semantic version |
| model_config_hash | String | No | Config hash for reproducibility | SHA256 |
| symbol | String | Yes | Target symbol | Non-empty |
| forecast_horizon | String | Yes | Prediction horizon | 1h, 4h, 24h |
| prediction_timestamp | DateTime (TZ) | Yes | When prediction was made | ISO 8601 |
| target_timestamp | DateTime (TZ) | Yes | When prediction is for | ISO 8601 |
| predicted_price | Decimal | Yes | Predicted price | > 0 |
| confidence_lower | Decimal | No | Lower confidence bound | > 0 |
| confidence_upper | Decimal | No | Upper confidence bound | > 0 |
| confidence_level | Decimal | No | Confidence interval (e.g., 0.95) | 0-1 |
| model_confidence | Decimal | No | Model's confidence score | 0-1 |
| actual_price | Decimal | No | Actual price (if known) | > 0 |
| prediction_error | Decimal | No | Error (actual - predicted) | Any |
| absolute_error | Decimal | No | Absolute error | >= 0 |
| percentage_error | Decimal | No | Percentage error | Any |
| is_validated | Boolean | No | Whether actual price is known | True/False |

#### State Transitions
1. **Created**: Forecast generated → `is_validated=False`, `actual_price=null`
2. **Validated**: Target time reached → `is_validated=True`, `actual_price` filled, errors calculated

#### Validation Rules
- `target_timestamp` must be > `prediction_timestamp`
- If `is_validated=True`, then `actual_price`, `prediction_error`, `absolute_error`, `percentage_error` must be non-null
- `absolute_error` = |`actual_price` - `predicted_price`|
- `percentage_error` = (`actual_price` - `predicted_price`) / `actual_price` * 100

---

### 7. Strategy
**Purpose**: Trading strategy configurations
**Database Model**: To be created at `src/database/models/strategy.py` (NEW)
**Table**: `strategies`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| name | String | Yes | Strategy name | Unique, non-empty |
| description | String | No | Strategy description | Max 500 chars |
| status | Enum | Yes | Current status | ACTIVE, PAUSED, DISABLED |
| allocated_capital | Decimal | Yes | Allocated capital | >= 0 |
| max_position_size | Decimal | No | Max position size | > 0 |
| max_daily_trades | Integer | No | Max trades per day | > 0 |
| risk_per_trade | Decimal | No | Risk per trade (%) | 0-100 |
| symbols | String | No | Allowed symbols (JSON array) | Valid JSON |
| parameters | String | No | Strategy parameters (JSON) | Valid JSON |
| created_at | DateTime (TZ) | Yes | Creation time | Auto-set |
| updated_at | DateTime (TZ) | Yes | Last update time | Auto-update |

#### State Transitions
- **ACTIVE**: Strategy is running and generating signals
- **PAUSED**: Strategy temporarily stopped, can be resumed
- **DISABLED**: Strategy permanently disabled, requires re-configuration to activate

---

### 8. StrategyAllocation
**Purpose**: Capital distribution across strategies
**Database Model**: To be created at `src/database/models/strategy_allocation.py` (NEW)
**Table**: `strategy_allocations`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| strategy_id | Integer | Yes | Foreign key to strategies | Valid FK |
| allocated_percentage | Decimal | Yes | Percentage of total capital | 0-100 |
| allocated_amount | Decimal | Yes | Absolute amount allocated | >= 0 |
| allocation_date | DateTime (TZ) | Yes | When allocation was set | ISO 8601 |
| notes | String | No | Allocation notes | Max 500 chars |

#### Relationships
- **Strategy** (N:1): Many allocations (history) belong to one strategy

#### Validation Rules
- Sum of all active `allocated_percentage` across strategies <= 100
- `allocated_amount` should match `allocated_percentage` of total account balance

---

### 9. StrategyPerformance
**Purpose**: Performance metrics for strategies
**Database Model**: To be created at `src/database/models/strategy_performance.py` (NEW)
**Table**: `strategy_performance`

#### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| id | Integer | Yes | Primary key | Auto-increment |
| strategy_id | Integer | Yes | Foreign key to strategies | Valid FK |
| period_start | DateTime (TZ) | Yes | Performance period start | ISO 8601 |
| period_end | DateTime (TZ) | Yes | Performance period end | ISO 8601 |
| total_trades | Integer | Yes | Number of trades | >= 0 |
| winning_trades | Integer | Yes | Number of winning trades | >= 0 |
| losing_trades | Integer | Yes | Number of losing trades | >= 0 |
| win_rate | Decimal | Yes | Win rate percentage | 0-100 |
| total_return | Decimal | Yes | Total return | Any |
| total_return_percentage | Decimal | Yes | Return percentage | Any |
| sharpe_ratio | Decimal | No | Risk-adjusted return | Any |
| max_drawdown | Decimal | No | Maximum drawdown | <= 0 |
| average_win | Decimal | No | Average winning trade | >= 0 |
| average_loss | Decimal | No | Average losing trade | <= 0 |
| profit_factor | Decimal | No | Gross profit / Gross loss | >= 0 |

#### Relationships
- **Strategy** (N:1): Many performance records (by time period) belong to one strategy

#### Validation Rules
- `period_end` >= `period_start`
- `total_trades` = `winning_trades` + `losing_trades`
- `win_rate` = (`winning_trades` / `total_trades`) * 100 (if total_trades > 0)
- `profit_factor` = `gross_profit` / `gross_loss` (if gross_loss != 0)

---

## API Response Models (Pydantic)

All API responses use Pydantic models at `src/api/models/`. These provide:
- Automatic validation
- OpenAPI schema generation
- Type safety for frontend consumers

### Common Response Patterns

#### 1. Single Entity Response
```python
class MarketDataResponse(BaseModel):
    id: int
    time: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    change: float
    change_percent: float

    class Config:
        from_attributes = True  # SQLAlchemy ORM mode
```

#### 2. List Response with Pagination
```python
class MarketDataListResponse(BaseModel):
    data: List[MarketDataResponse]
    total: int
    page: int
    page_size: int
    next_cursor: Optional[str] = None  # Keyset pagination
    symbol: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
```

#### 3. Error Response
```python
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime
    request_id: str
```

---

## Cache Models (Redis)

### Cache Key Patterns

| Data Type | Key Pattern | TTL | Example |
|-----------|-------------|-----|---------|
| Latest Price | `price:latest:{symbol}` | 5s | `price:latest:CrudeOIL` |
| Chart Data | `chart:{symbol}:{timeframe}:{start}:{end}` | 1h | `chart:CrudeOIL:M5:2024-11-24T10:00:00:2024-11-24T11:00:00` |
| Account Balance | `account:{account_id}:balance` | 10s | `account:12345:balance` |
| Open Positions | `positions:open:{account_id}` | 5s | `positions:open:12345` |
| Forecasts | `forecasts:{symbol}:{horizon}` | 1h | `forecasts:CrudeOIL:1h` |
| Strategy Allocations | `strategy:allocations:all` | 1h | `strategy:allocations:all` |

### Cache Value Format
All cached values stored as JSON strings with metadata:

```json
{
  "data": { ... },  // Actual data
  "cached_at": "2024-11-24T10:30:00Z",
  "source": "database",
  "version": "1"
}
```

---

## Event Models (Redis Pub/Sub)

### Event Schema

All events published to Redis channels follow standardized schema:

```python
class MarketDataEvent(BaseModel):
    event_type: Literal["new_tick"]
    timestamp: datetime
    source: str  # "MT4", "MarketDataAgent"
    symbol: str
    timeframe: str
    data: MarketDataResponse  # Nested Pydantic model
```

### Event Channels

| Channel | Event Type | Publisher | Subscriber |
|---------|------------|-----------|------------|
| `market_data:{symbol}:{timeframe}` | new_tick | MT4 Integration Service | Dashboard API (SSE) |
| `account:balance` | balance_updated | MT4 Integration Service | Dashboard API (SSE) |
| `positions:updates` | position_opened, position_closed, position_modified | MT4 Integration Service | Dashboard API (SSE) |
| `forecasts:new` | forecast_generated | MLPredictionAgent | Dashboard API (SSE) |

---

## Summary

### Entities Overview

| Entity | Database Model | API Model | Caching | Real-time Updates |
|--------|----------------|-----------|---------|-------------------|
| MarketData | ✅ EXISTS | ✅ EXISTS | ✅ YES (5s TTL) | ✅ SSE |
| Indicators | ✅ EXISTS | ✅ EXISTS | ✅ YES (1h TTL) | ❌ NO |
| Account | ✅ EXISTS | ✅ EXISTS | ✅ YES (10s TTL) | ✅ SSE |
| Position | ✅ EXISTS | ✅ EXISTS | ✅ YES (5s TTL) | ✅ SSE |
| Trade | ✅ EXISTS | ✅ EXISTS | ❌ NO | ❌ NO |
| Forecast | ✅ EXISTS | ✅ EXISTS | ✅ YES (1h TTL) | ✅ SSE |
| Strategy | ❌ NEW | ❌ NEW | ❌ NO | ❌ NO |
| StrategyAllocation | ❌ NEW | ❌ NEW | ✅ YES (1h TTL) | ❌ NO |
| StrategyPerformance | ❌ NEW | ❌ NEW | ❌ NO | ❌ NO |

### Implementation Priority

**Phase 1** (Core Data Serving):
1. MarketData endpoints with caching and SSE
2. Account endpoints with real-time balance updates
3. Position endpoints with real-time position updates
4. Trade history endpoints with pagination

**Phase 2** (Forecasting & Strategy):
5. Forecast endpoints with caching
6. Create Strategy, StrategyAllocation, StrategyPerformance models
7. Strategy endpoints

**All data models defined and validated. Proceeding to API contract generation.**
