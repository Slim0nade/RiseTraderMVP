# Bugfix: Synthetic Mode Not Using config_params

**Date**: 2025-12-20
**File**: `src/services/backtesting/backtest_service.py`
**Function**: `_run_synthetic_mode()`

---

## 🐛 Bug Description

Synthetic backtests configured via `config_params` (e.g., from UI) generated **0 trades** because the `_run_synthetic_mode()` function did not instantiate a `SyntheticEngine` from the stored configuration.

### Root Cause

```python
# Line 289-290 (old code)
async def _run_synthetic_mode(..., decision_engine: Optional[callable], ...):
    # decision_engine was Optional and defaulted to None
    # ...
    if decision_engine:  # <-- This was always False when config_params was used
        decision = decision_engine(tick)
```

The function expected an external `decision_engine` callback but **never read `config.config_params`** to create one internally.

### Symptoms

| Path | Result |
|------|--------|
| API `/runs` with `synthetic_strategy` in request body | ✅ Works (API creates engine inline) |
| Config with `config_params.synthetic_strategy` | ❌ **0 trades** (engine never created) |

---

## ✅ Fix Applied

Added logic at the start of `_run_synthetic_mode()` to create a `SyntheticEngine` from `config.config_params` if no `decision_engine` is provided:

```python
# If no decision_engine provided, try to create from config_params
if decision_engine is None and config.config_params:
    synthetic_strategy = config.config_params.get("synthetic_strategy")
    synthetic_params = config.config_params.get("synthetic_params", {})
    
    # Also check for strategy params at root level of config_params
    if not synthetic_strategy:
        synthetic_strategy = config.config_params.get("strategy")
    
    if synthetic_strategy:
        from .synthetic_engine import SyntheticEngine
        
        # Merge params: synthetic_params takes precedence
        merged_params = {**config.config_params, **synthetic_params}
        merged_params.pop("synthetic_strategy", None)
        merged_params.pop("synthetic_params", None)
        merged_params.pop("strategy", None)
        
        synthetic_engine = SyntheticEngine(
            strategy=synthetic_strategy,
            params=merged_params if merged_params else None,
        )
        
        # Create decision_engine callable
        def decision_engine(tick):
            signal = synthetic_engine.process_tick(tick)
            if signal.action:
                return {
                    "action": signal.action,
                    "quantity": signal.quantity,
                }
            return None
```

### Supported config_params Formats

The fix handles multiple config_params formats:

**Format 1: Nested structure**
```json
{
  "synthetic_strategy": "crude_oil_v3",
  "synthetic_params": {
    "ema_fast": 8,
    "ema_slow": 29
  }
}
```

**Format 2: Flat structure**
```json
{
  "strategy": "crude_oil_v3",
  "ema_fast": 8,
  "ema_slow": 29
}
```

**Format 3: Mixed**
```json
{
  "synthetic_strategy": "crude_oil_v3",
  "ema_fast": 8,
  "ema_slow": 29
}
```

---

## 📊 Available Strategies

| Strategy | Description | Key Params |
|----------|-------------|------------|
| `ma_crossover` | MA crossover | `fast_period`, `slow_period` |
| `rsi` | RSI overbought/oversold | `rsi_period`, `oversold`, `overbought` |
| `trend_following` | Simple trend following | `trend_period` |
| `mean_reversion` | Mean reversion | `lookback`, `std_threshold` |
| `crude_oil_v3` | Full CrudeOIL Trader V3 | `ema_fast`, `ema_slow`, `rsi_period`, ... |

---

## 🧪 Testing

### Test via API

```bash
# 1. Create config with synthetic_strategy in config_params
curl -X POST http://localhost:8003/api/v1/backtesting/configurations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test V3 Fix",
    "symbol": "CrudeOIL",
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-03-01T00:00:00Z",
    "initial_capital": "10000.00",
    "execution_mode": "synthetic_fast",
    "config_params": {
      "synthetic_strategy": "crude_oil_v3",
      "synthetic_params": {
        "ema_fast": 8,
        "ema_slow": 29,
        "quantity": "1.0"
      }
    }
  }'

# 2. Run backtest (WITHOUT synthetic_strategy in request)
curl -X POST http://localhost:8003/api/v1/backtesting/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "<config_id_from_step_1>",
    "timeframe": "M5"
  }'

# 3. Check results - should now have trades!
curl http://localhost:8003/api/v1/backtesting/runs/<run_id>/trades
```

### Expected Logs

When fix works correctly, you should see:
```
creating_synthetic_engine_from_config run_id=... strategy=crude_oil_v3 params={...}
synthetic_engine_created run_id=... strategy=crude_oil_v3
```

---

## 📝 Related Files

- `src/services/backtesting/backtest_service.py` - Fixed
- `src/services/backtesting/synthetic_engine.py` - SyntheticEngine implementation
- `src/services/backtesting/crude_oil_strategy.py` - CrudeOIL V3 strategy
- `src/api/routes/backtesting.py` - API endpoints (unchanged)

---

## 🔄 Backwards Compatibility

The fix is backwards compatible:

| Scenario | Behavior |
|----------|----------|
| `decision_engine` passed from API | ✅ Uses provided engine (unchanged) |
| `config.config_params` has strategy | ✅ **NEW** Creates engine from config |
| Neither provided | ⚠️ Logs warning, processes candles but no trades |

---

## ✅ Status: FIXED

The synthetic backtest engine now properly reads `config.config_params` to instantiate the trading strategy. Backtests created via UI with V3 strategy parameters will now generate trades correctly.
