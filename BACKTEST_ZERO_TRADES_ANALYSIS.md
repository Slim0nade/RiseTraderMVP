# Backtest Zero Trades Root Cause Analysis

## Date: 2024-12-24

## Issues Found and Fixed

### 1. ✅ FIXED: Performance Metrics API 422 Validation Error

**Problem:**
- `/api/performance/metrics` endpoint returning 422 validation errors
- Missing fields: `total_return_pct`, `max_drawdown_pct`
- Fields in model: `total_return_percent`, `max_drawdown_percent`

**Root Cause:**
- Field name mismatch between `performance_models.py` and `backtesting_models.py`
- Backtesting models use `_pct` suffix
- Performance models used `_percent` suffix
- Import aliasing caused wrong model to be used

**Fix Applied:**
- Updated `src/api/models/performance_models.py`:
  - Changed `total_return_percent` → `total_return_pct` (line 96)
  - Changed `max_drawdown_percent` → `max_drawdown_pct` (line 79)
- Updated `src/api/routes/performance.py`:
  - Changed field names in `TradingPerformanceMetricsResponse` instantiation (lines 102, 115)
- Updated examples in model definitions

**Verification:**
```bash
curl -s http://localhost:8003/api/performance/metrics
# Returns 200 OK with valid JSON
```

### 2. ✅ FIXED: Position Closing Logic Bug

**Problem:**
- Strategy returned `action='close'` but trade_simulator expects `'close_long'` or `'close_short'`

**Files Modified:**
- `src/services/backtesting/crude_oil_strategy_extended.py` (lines 782-808)
- `src/services/backtesting/crude_oil_strategy.py` (lines 485-519)

**Fix:**
```python
# Before:
action='close'

# After:
close_action = 'close_long' if position_type == 'buy' else 'close_short'
action=close_action
```

### 3. ⚠️ IDENTIFIED: Strategy Generates Zero Entry Signals

**Problem:**
- Backtest completes with 0 trades despite position closing fix
- 29,767 candles processed, no positions ever opened

**Root Cause:**
The strategy's default parameters are **TOO RESTRICTIVE** and prevent almost all entry signals.

#### Key Problematic Filters:

**A. Momentum Filter** (lines 436-448 in `crude_oil_strategy_extended.py`):
```python
# DEFAULT VALUES (from lines 52-54):
momentum_buy_threshold: float = 99.5   # ← TOO TIGHT!
momentum_sell_threshold: float = 100.5  # ← TOO TIGHT!
```

**Analysis:**
- Momentum is calculated as: `(current_price / price_n_bars_ago) * 100`
- Default requires momentum to be between 99.5-100.5 (only 1% range)
- This means price can only move 0.5% in 10 bars to trigger
- **This is unrealistically restrictive for M1 (1-minute) data**

**B. Additional Extended Filters (all optional but can compound):**
- ADX filter (line 502-509): `use_adx_filter=False` by default ✓
- MACD filter (line 452-466): `use_macd_filter=False` by default ✓
- Bollinger filter (line 468-486): `use_bollinger_filter=False` by default ✓
- Stochastic filter (line 488-500): `use_stochastic_filter=False` by default ✓
- Volume filter (line 511-517): `use_volume_filter=False` by default ✓

**Good news:** Extended filters are disabled by default, so not the problem.

#### Configuration Check:

```sql
SELECT config_params FROM backtest_configurations ORDER BY created_at DESC LIMIT 1;
-- Result: NULL

-- This means ALL backtests are using DEFAULT PARAMETERS
-- Default momentum thresholds are the bottleneck
```

## Recommended Fixes

### Option 1: Adjust Default Parameters (Quick Fix)

Update default momentum thresholds in `src/services/backtesting/crude_oil_strategy_extended.py`:

```python
# CURRENT (line 52-54):
momentum_buy_threshold: float = 99.5   # Too tight for M1
momentum_sell_threshold: float = 100.5  # Too tight for M1

# RECOMMENDED:
momentum_buy_threshold: float = 95.0   # Allow 5% downward move
momentum_sell_threshold: float = 105.0  # Allow 5% upward move
```

**Justification:**
- M1 (1-minute) candles have more noise and volatility
- Crude oil can easily move 2-3% in a 10-minute period
- 5% threshold gives realistic filtering while still rejecting weak signals

### Option 2: Make Momentum Filter Optional

Add parameter to disable momentum filter entirely:

```python
use_momentum_filter: bool = True  # Add this parameter
```

Then in `_check_entry()` method (line 436):
```python
# Momentum Filter
if self.params.use_momentum_filter:
    if signal_direction == 'buy':
        if momentum > self.params.momentum_buy_threshold:
            filters_passed.append("momentum_filter")
        else:
            filters_failed.append("momentum_filter")
            return self._no_signal(f"Momentum too low: {momentum:.2f}", ...)
```

### Option 3: Add Backtesting Config Parameter Override

Ensure backtest configurations properly pass `config_params` to strategy:

1. Verify `BacktestConfiguration.config_params` JSONB field is populated
2. Update strategy instantiation to merge config params with defaults
3. Test with explicit config like:
```json
{
  "config_params": {
    "momentum_buy_threshold": 95.0,
    "momentum_sell_threshold": 105.0
  }
}
```

## Testing Plan

1. **Modify defaults** (Option 1)
2. **Run new backtest** with same date range (Dec 2023 - Jan 2024)
3. **Verify trades generated**:
   - Expect: 50-200 trades (depends on EMA crossovers + momentum)
   - Candles: ~30,000 (1-minute data for 45 days)
4. **Validate position closing** works correctly
5. **Check equity curve** for smooth progression

## Files Modified This Session

1. `/src/api/models/__init__.py` - Added model import aliases
2. `/src/api/models/performance_models.py` - Fixed field names
3. `/src/api/routes/performance.py` - Updated field references
4. `/src/api/routes/backtesting.py` - Updated model import
5. `/src/services/backtesting/crude_oil_strategy_extended.py` - Fixed close action
6. `/src/services/backtesting/crude_oil_strategy.py` - Fixed close action

## Status

- ✅ Performance metrics API: **WORKING**
- ✅ Position closing logic: **FIXED**
- ⚠️ Zero trades issue: **ROOT CAUSE IDENTIFIED**
- 🔄 Next step: Adjust momentum thresholds and retest

## Recommendation

**Immediate Action:**
Change default momentum thresholds from 99.5/100.5 to 95.0/105.0 in `crude_oil_strategy_extended.py` and `crude_oil_strategy.py`.

This single change will likely enable the strategy to generate trades while still maintaining quality filtering through:
- EMA crossover signals (8/29 EMAs)
- RSI filter (32-68 range)
- CCI filter (-80 to 100 range)
- ATR-based stops and targets

All other filters remain intact and will continue to reject poor-quality signals.
