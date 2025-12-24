# Backtesting Examples

This directory contains example scripts demonstrating all four backtesting user stories.

## Prerequisites

1. **Database Setup**:
   ```bash
   # Ensure PostgreSQL is running
   # Ensure database has historical market data
   ```

2. **Environment Variables**:
   ```bash
   export DATABASE_URL="postgresql+asyncpg://localhost/risetrader"
   ```

3. **Python Dependencies**:
   ```bash
   pip install -r requirements.txt

   # For RL example (optional)
   pip install stable-baselines3
   ```

## Examples

### 1. Simple Backtest (`01_simple_backtest.py`)

**What it demonstrates**:
- Basic backtest configuration
- Running a single backtest
- Interpreting results

**Run it**:
```bash
python examples/backtesting/01_simple_backtest.py
```

**Expected output**:
```
Running backtest...
============================================================
BACKTEST RESULTS
============================================================
Symbol:          EURUSD
Period:          2024-01-01 to 2024-01-31
Initial Capital: $10,000.00
------------------------------------------------------------
Total Return:    12.50%
Sharpe Ratio:    1.85
Max Drawdown:    -8.20%
Win Rate:        62.00%
------------------------------------------------------------
Total Trades:    45
✅ EXCELLENT - Sharpe > 1.5
```

### 2. Batch Optimization (`02_batch_optimization.py`)

**What it demonstrates**:
- Parameter grid definition
- Parallel optimization (4 workers)
- Ranking results by composite score
- Best vs worst comparison

**Run it**:
```bash
python examples/backtesting/02_batch_optimization.py
```

**Expected output**:
```
Creating parameter grid...
Total combinations: 48
Running optimization with 4 parallel workers...
Completed 48 backtests

TOP 10 PARAMETER COMBINATIONS
#1
  Parameters:
    - EMA Fast:   8
    - EMA Slow:   25
    - RSI Period: 14
  Performance:
    - Sharpe:     1.95
    - Return:     14.20%
    - Drawdown:   -6.50%
...
```

### 3. RL Training (`03_rl_training.py`)

**What it demonstrates**:
- Creating Gymnasium environment
- Training PPO agent
- Comparing trained vs random policy
- Environment validation

**Run it**:
```bash
python examples/backtesting/03_rl_training.py
```

**Expected output**:
```
Creating RL environment...
✅ Environment passes Gymnasium checks

BASELINE: Random Policy
Random Policy - Avg Reward: -245.67

TRAINING PPO AGENT
Training for 50,000 timesteps...
✅ Training complete

EVALUATING TRAINED AGENT
Trained Agent - Avg Reward: 152.34

COMPARISON
Random Policy:  -245.67 ± 89.23
Trained Agent:  152.34 ± 45.67
✅ Trained agent improved by 162.0%!
```

### 4. A/B Testing (`04_ab_testing.py`)

**What it demonstrates**:
- Running two configurations
- Statistical comparison (Welch's t-test)
- Trade overlap analysis
- Data-driven decision making

**Run it**:
```bash
python examples/backtesting/04_ab_testing.py
```

**Expected output**:
```
Running backtest A (Conservative)...
  Return: 10.50%
  Sharpe: 1.65
  Trades: 32

Running backtest B (Aggressive)...
  Return: 15.30%
  Sharpe: 1.45
  Trades: 78

STATISTICAL A/B COMPARISON
Side-by-Side Metrics:
Metric               Conservative    Aggressive      Difference
-----------------------------------------------------------------
Total Return               10.50%        15.30%          -4.80%
Sharpe Ratio                 1.65          1.45            0.20
...

Statistical Significance (Welch's t-test):
  P-value:          0.0234
  Significant:      True (p < 0.05)

RECOMMENDATION
✅ Choose CONSERVATIVE configuration
   Statistically superior performance
```

## Modifying Examples

### Change Symbol/Timeframe

Edit the config dict:
```python
config = {
    "symbol": "GBPUSD",  # Change symbol
    "timeframe": "H1",   # Change timeframe (M1, M5, M15, M30, H1, H4, D1)
    ...
}
```

### Change Date Range

```python
config = {
    "start_date": datetime(2024, 6, 1, tzinfo=timezone.utc),
    "end_date": datetime(2024, 12, 1, tzinfo=timezone.utc),  # 6 months
    ...
}
```

### Use Different Strategy

```python
config = {
    "synthetic_strategy": "crude_oil_extended",  # More indicators
    "strategy_params": {
        "ema_fast": 5,
        "ema_slow": 13,
        "macd_fast": 12,
        "macd_slow": 26,
        ...
    },
}
```

## Troubleshooting

### "Insufficient historical data"

**Problem**: Not enough candles in date range.

**Solution**:
- Check database has data: `SELECT COUNT(*) FROM market_data WHERE symbol = 'EURUSD'`
- Use longer date range
- Import more historical data

### "Database connection failed"

**Problem**: Cannot connect to PostgreSQL.

**Solution**:
- Verify PostgreSQL is running: `psql -U postgres -l`
- Check DATABASE_URL is correct
- Ensure database exists: `createdb risetrader`

### RL example: "stable-baselines3 not installed"

**Problem**: Optional dependency missing.

**Solution**:
```bash
pip install stable-baselines3
```

### Optimization too slow

**Problem**: 48+ combinations taking too long.

**Solution**:
- Reduce grid size: fewer parameter values
- Increase `max_workers` (up to CPU count)
- Use shorter date ranges for optimization
- Enable early stopping:
  ```python
  optimizer.run(early_stop_threshold=2.0)  # Stop when Sharpe > 2.0
  ```

## Next Steps

After running these examples:

1. **Read the full documentation**: `src/services/backtesting/README.md`
2. **Review the quickstart guide**: `specs/006-backtesting-engine/quickstart.md`
3. **Explore REST API**: `POST /api/v1/backtesting/runs`
4. **Customize strategies**: Create your own strategy logic

## Support

For issues:
- Check `src/services/backtesting/README.md` troubleshooting section
- Review test files for more usage examples
- Open GitHub issue with error logs
