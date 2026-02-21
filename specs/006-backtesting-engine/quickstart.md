# Quickstart: Backtesting Engine

**Feature**: 006-backtesting-engine
**Date**: 2025-12-11
**Audience**: Developers implementing the backtesting engine

## Overview

This quickstart guide provides concrete examples and usage patterns for the backtesting engine. It covers the most common workflows: running a single backtest, batch parameter optimization, and RL environment integration.

## Prerequisites

- RiseTrader development environment setup (Docker, PostgreSQL, Python 3.11+)
- Historical market data loaded in database (13.5M candles from 001-mt4-integration)
- Agent system configured (for full pipeline mode)

## Installation

```bash
# Add new dependencies to pyproject.toml
poetry add gymnasium scipy hypothesis

# Run database migrations
docker-compose exec api alembic upgrade head

# Verify tables created
docker-compose exec api python -c "from src.database.models.backtest import BacktestConfiguration; print('Models imported successfully')"
```

## Quick Examples

### 1. Run a Simple Backtest (Synthetic Mode)

**Use case**: Validate a simple MA crossover strategy on 3 months of data.

```python
from datetime import datetime, timezone
from decimal import Decimal
from src.services.backtesting.backtest_service import BacktestService
from src.database.models.backtest import BacktestConfiguration, ExecutionMode

# Create configuration
config = BacktestConfiguration(
    name="MA_Crossover_Q1_2023",
    symbol="EURUSD",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 3, 31, tzinfo=timezone.utc),
    initial_capital=Decimal("10000.00"),
    execution_mode=ExecutionMode.SYNTHETIC_FAST,
    config_params={
        "ma_short": 10,
        "ma_long": 50,
        "rsi_oversold": 30,
        "rsi_overbought": 70
    }
)

# Save configuration
async with get_db_session() as session:
    backtest_repo = BacktestRepository(session)
    saved_config = await backtest_repo.create(config)

# Run backtest
backtest_service = BacktestService()
run = await backtest_service.run_backtest(saved_config.id, random_seed=42)

# Wait for completion (or poll status)
while run.status == RunStatus.RUNNING:
    await asyncio.sleep(5)
    run = await backtest_repo.get_run(run.id)

# Print results
print(f"Total Return: {run.total_return_pct:.2f}%")
print(f"Sharpe Ratio: {run.sharpe_ratio:.2f}")
print(f"Max Drawdown: {run.max_drawdown_pct:.2f}%")
print(f"Win Rate: {run.win_rate * 100:.1f}%")
print(f"Total Trades: {run.total_trades}")
```

**Expected output** (example):
```
Total Return: 12.45%
Sharpe Ratio: 1.67
Max Drawdown: 7.20%
Win Rate: 58.3%
Total Trades: 42
```

---

### 2. Full Pipeline Mode with Agent Integration

**Use case**: Validate actual agent decisions on historical data.

```python
from src.services.backtesting.backtest_service import BacktestService
from src.database.models.backtest import ExecutionMode

# Create configuration referencing existing agent setup
config = BacktestConfiguration(
    name="Agent_Validation_Q2_2023",
    symbol="BTCUSD",
    start_date=datetime(2023, 4, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 6, 30, tzinfo=timezone.utc),
    initial_capital=Decimal("50000.00"),
    execution_mode=ExecutionMode.FULL_PIPELINE,
    agent_config_ref="production_agents_v1",  # Reference to agent config
    slippage_pct=Decimal("0.002"),  # Higher slippage for crypto
    commission_pct=Decimal("0.001")
)

await backtest_repo.create(config)

# Run with full agent pipeline
backtest_service = BacktestService()
run = await backtest_service.run_backtest(config.id, validate_data=True)

# Monitor progress
print(f"Backtest started: {run.id}")
print("This will take ~30 minutes for 3 months of data with LLM agents...")

# After completion, analyze agent decisions
agent_logs = await backtest_repo.get_agent_decisions(
    run.id,
    agent_identifier="SignalGeneratorAgent"
)

for log in agent_logs[:5]:  # First 5 decisions
    print(f"{log.timestamp}: {log.output_decision}")
```

---

### 3. Batch Parameter Optimization

**Use case**: Find optimal RSI thresholds across 16 combinations.

```python
from src.services.backtesting.batch_optimizer import BatchOptimizer
from src.database.models.backtest import ParameterGrid

# Define parameter grid
grid = ParameterGrid(
    name="RSI_Threshold_Optimization",
    base_config_id=base_config.id,  # Existing config to vary
    parameters={
        "rsi_oversold": [20, 25, 30, 35],
        "rsi_overbought": [65, 70, 75, 80]
    },
    total_combinations=16  # 4 * 4
)

await backtest_repo.create_grid(grid)

# Execute all combinations in parallel
optimizer = BatchOptimizer(max_workers=4)
results = await optimizer.execute_grid(grid.id)

print(f"Executed {len(results)} backtests")

# Get top performers ranked by Sharpe
top_results = await backtest_repo.get_grid_results(
    grid.id,
    rank_by="sharpe",
    top_n=5
)

for i, result in enumerate(top_results, 1):
    print(f"{i}. Params: {result.parameter_values}")
    print(f"   Sharpe: {result.run_metrics.sharpe_ratio:.2f}")
    print(f"   Return: {result.run_metrics.total_return_pct:.2f}%")
    print(f"   Drawdown: {result.run_metrics.max_drawdown_pct:.2f}%")
    print()
```

**Expected output** (example):
```
Executed 16 backtests

1. Params: {'rsi_oversold': 30, 'rsi_overbought': 70}
   Sharpe: 2.15
   Return: 18.50%
   Drawdown: 6.20%

2. Params: {'rsi_oversold': 25, 'rsi_overbought': 70}
   Sharpe: 2.03
   Return: 16.80%
   Drawdown: 7.10%

...
```

---

### 4. Gymnasium RL Environment Integration

**Use case**: Train a PPO agent to make trading decisions.

```python
from src.services.backtesting.gymnasium_env import BacktestTradingEnv
from stable_baselines3 import PPO

# Create Gymnasium environment
env = BacktestTradingEnv(
    symbol="EURUSD",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 12, 31, tzinfo=timezone.utc),
    initial_capital=10000.0,
    episode_length=1000,  # 1000 candles per episode
    lookback_window=50,   # Observe last 50 candles
    action_type="discrete",  # {0: hold, 1: buy, 2: sell}
    reward_type="simple_pnl"  # Reward = P&L change
)

# Verify environment
from gymnasium.utils.env_checker import check_env
check_env(env)  # Validates Gymnasium API compliance

# Train RL agent
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=100_000)

# Evaluate trained agent
obs, info = env.reset(seed=42)
total_reward = 0
for _ in range(1000):
    action, _states = model.predict(obs, deterministic=True)
    obs, reward, terminated, truncated, info = env.step(action)
    total_reward += reward
    if terminated or truncated:
        break

print(f"Episode reward: {total_reward:.2f}")
print(f"Final account value: {info['total_value']:.2f}")
```

---

### 5. A/B Testing Two Configurations

**Use case**: Compare conservative vs aggressive risk settings.

```python
# Configuration A: Conservative
config_a = BacktestConfiguration(
    name="Conservative_Strategy",
    symbol="EURUSD",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 6, 30, tzinfo=timezone.utc),
    initial_capital=Decimal("10000.00"),
    execution_mode=ExecutionMode.SYNTHETIC_FAST,
    max_leverage=Decimal("1.0"),  # No leverage
    config_params={
        "risk_per_trade_pct": 0.01,  # 1% risk per trade
        "rsi_oversold": 25,
        "rsi_overbought": 75
    }
)

# Configuration B: Aggressive
config_b = BacktestConfiguration(
    name="Aggressive_Strategy",
    symbol="EURUSD",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 6, 30, tzinfo=timezone.utc),
    initial_capital=Decimal("10000.00"),
    execution_mode=ExecutionMode.SYNTHETIC_FAST,
    max_leverage=Decimal("2.0"),  # 2x leverage
    config_params={
        "risk_per_trade_pct": 0.03,  # 3% risk per trade
        "rsi_oversold": 30,
        "rsi_overbought": 70
    }
)

# Run both
run_a = await backtest_service.run_backtest(config_a.id)
run_b = await backtest_service.run_backtest(config_b.id)

# Wait for completion...

# Compare results
from src.services.backtesting.comparison import compare_runs
comparison = await compare_runs([run_a.id, run_b.id])

print("Side-by-side comparison:")
print(f"{'Metric':<25} {'Conservative':<15} {'Aggressive':<15}")
print("-" * 55)
print(f"{'Total Return %':<25} {run_a.total_return_pct:<15.2f} {run_b.total_return_pct:<15.2f}")
print(f"{'Sharpe Ratio':<25} {run_a.sharpe_ratio:<15.2f} {run_b.sharpe_ratio:<15.2f}")
print(f"{'Max Drawdown %':<25} {run_a.max_drawdown_pct:<15.2f} {run_b.max_drawdown_pct:<15.2f}")
print(f"{'Win Rate %':<25} {run_a.win_rate*100:<15.1f} {run_b.win_rate*100:<15.1f}")
print()
print(f"Statistical significance (returns): p={comparison.return_ttest_pvalue:.4f}")
if comparison.return_ttest_pvalue < 0.05:
    print("✅ Difference is statistically significant")
else:
    print("⚠️  Difference is NOT statistically significant")
```

**Expected output** (example):
```
Side-by-side comparison:
Metric                    Conservative    Aggressive
-------------------------------------------------------
Total Return %            12.45           18.75
Sharpe Ratio              1.85            1.52
Max Drawdown %            7.20            14.50
Win Rate %                58.3            52.1

Statistical significance (returns): p=0.0123
✅ Difference is statistically significant
```

---

## Common Workflows

### Pre-Flight Data Validation

Before running a backtest, validate historical data completeness:

```python
from src.services.backtesting.data_validator import validate_historical_data

validation_result = await validate_historical_data(
    symbol="EURUSD",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2023, 12, 31, tzinfo=timezone.utc)
)

if validation_result.has_gaps:
    print("⚠️  Data gaps detected:")
    for gap in validation_result.gaps:
        print(f"  - {gap.start_date} to {gap.end_date}: {gap.missing_candles} candles")
    print("Proceed anyway? (y/n)")
else:
    print("✅ Data is complete, ready for backtesting")
```

---

### Monitoring Long-Running Backtests

For full pipeline mode backtests that take 30+ minutes:

```python
import asyncio

async def monitor_backtest(run_id: str):
    """Poll backtest status and print progress."""
    last_candles = 0
    while True:
        run = await backtest_repo.get_run(run_id)

        if run.status == RunStatus.COMPLETED:
            print(f"✅ Backtest completed successfully")
            break
        elif run.status == RunStatus.FAILED:
            print(f"❌ Backtest failed: {run.error_message}")
            break
        elif run.status == RunStatus.TIMEOUT:
            print(f"⏱️  Backtest timed out after max duration")
            break

        # Show progress
        candles_delta = run.candles_processed - last_candles
        print(f"Progress: {run.candles_processed} candles processed (+{candles_delta})")
        last_candles = run.candles_processed

        await asyncio.sleep(30)  # Check every 30 seconds

await monitor_backtest(run.id)
```

---

### Exporting Results for Analysis

Export backtest results to CSV for external analysis:

```python
import pandas as pd

# Export trade log
trades = await backtest_repo.get_trades(run_id)
df_trades = pd.DataFrame([
    {
        "timestamp": t.entry_timestamp,
        "symbol": t.symbol,
        "action": t.action,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "quantity": t.quantity,
        "net_pnl": t.net_pnl,
        "holding_hours": t.holding_duration_seconds / 3600 if t.holding_duration_seconds else None
    }
    for t in trades
])
df_trades.to_csv(f"backtest_{run_id}_trades.csv", index=False)

# Export equity curve
snapshots = await backtest_repo.get_snapshots(run_id)
df_equity = pd.DataFrame([
    {"timestamp": s.timestamp, "total_value": s.total_value}
    for s in snapshots
])
df_equity.to_csv(f"backtest_{run_id}_equity.csv", index=False)

print(f"Exported trades and equity curve to CSV files")
```

---

## Testing Examples

### Unit Test: Portfolio State Tracking

```python
# tests/unit/backtesting/test_portfolio_state.py
import pytest
from decimal import Decimal
from src.services.backtesting.portfolio_state import PortfolioState

@pytest.mark.asyncio
async def test_portfolio_buy_trade():
    """Test portfolio state after executing a buy trade."""
    portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

    # Execute buy
    portfolio.execute_trade(
        symbol="EURUSD",
        action="buy",
        price=Decimal("1.0850"),
        quantity=Decimal("1000"),  # 0.01 lot
        fees=Decimal("1.50")
    )

    assert portfolio.cash_balance == Decimal("8998.50")  # 10000 - 1000 - 1.50
    assert len(portfolio.open_positions) == 1
    assert portfolio.open_positions[0].symbol == "EURUSD"
    assert portfolio.open_positions[0].quantity == Decimal("1000")
```

### Integration Test: Full Backtest Run

```python
# tests/integration/backtesting/test_backtest_service.py
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from src.services.backtesting.backtest_service import BacktestService

@pytest.mark.asyncio
async def test_full_backtest_run_synthetic_mode(db_session):
    """Test complete backtest execution in synthetic mode."""
    config = BacktestConfiguration(
        name="Test_Run",
        symbol="EURUSD",
        start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2023, 1, 7, tzinfo=timezone.utc),  # 1 week
        initial_capital=Decimal("10000.00"),
        execution_mode=ExecutionMode.SYNTHETIC_FAST,
        config_params={"ma_short": 10, "ma_long": 50}
    )

    repo = BacktestRepository(db_session)
    saved_config = await repo.create(config)

    service = BacktestService()
    run = await service.run_backtest(saved_config.id, random_seed=42)

    # Wait for completion
    while run.status == RunStatus.RUNNING:
        await asyncio.sleep(1)
        run = await repo.get_run(run.id)

    # Assertions
    assert run.status == RunStatus.COMPLETED
    assert run.total_return_pct is not None
    assert run.sharpe_ratio is not None
    assert run.total_trades >= 0
    assert run.candles_processed > 0

    # Verify determinism
    run2 = await service.run_backtest(saved_config.id, random_seed=42)
    while run2.status == RunStatus.RUNNING:
        await asyncio.sleep(1)
        run2 = await repo.get_run(run2.id)

    assert run.total_return_pct == run2.total_return_pct  # Deterministic replay
```

---

## Troubleshooting

### Issue: Backtest fails with "Data gaps detected"

**Solution**: Pre-validate data or set `validate_data=False` to skip gaps:
```python
run = await backtest_service.run_backtest(config.id, validate_data=False)
```

### Issue: Synthetic mode results don't correlate with full mode

**Solution**: Adjust synthetic rules to better approximate agent behavior. Check correlation:
```python
from scipy.stats import pearsonr

# Run same config in both modes
run_full = await backtest_service.run_backtest(config_full.id)
run_synthetic = await backtest_service.run_backtest(config_synthetic.id)

correlation, p_value = pearsonr(
    [run_full.total_return_pct],
    [run_synthetic.total_return_pct]
)
print(f"Correlation: {correlation:.2f} (target: > 0.7)")
```

### Issue: RL environment training is unstable

**Solution**: Normalize observations and use reward shaping:
```python
env = BacktestTradingEnv(
    ...,
    normalize_observations=True,  # Scale to [-1, 1]
    reward_type="risk_adjusted",  # Penalize volatility
    max_drawdown_penalty=0.1      # Stop episode if DD > 10%
)
```

---

## Next Steps

1. **Implement Phase 1 (P1 user story)**: Core backtesting functionality
2. **Write unit tests**: Portfolio state, metrics calculator, trade simulator
3. **Integration testing**: Full backtest runs with sample data
4. **Performance profiling**: Ensure 30min target for 6-month backtests
5. **Phase 2 (P2)**: Synthetic mode and batch optimization
6. **Phase 3 (P3)**: Gymnasium environment for RL training

## References

- **Spec**: [spec.md](./spec.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Contracts**: [contracts/backtesting-service.yaml](./contracts/backtesting-service.yaml)
- **Research**: [research.md](./research.md)
