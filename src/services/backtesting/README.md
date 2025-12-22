# Backtesting Engine

Production-ready backtesting engine for validating multi-agent trading decisions against historical data.

## Overview

The RiseTrader backtesting engine provides four major capabilities:

1. **Historical Performance Validation** (User Story 1) - Test trading strategies against real market data
2. **Rapid Strategy Optimization** (User Story 2) - Batch parameter search with 100x+ speedup
3. **RL Environment** (User Story 3) - Gymnasium-compliant environment for training RL agents
4. **Statistical A/B Testing** (User Story 4) - Compare configurations with statistical significance

## Features

- **Two Execution Modes**:
  - **Agent Mode**: Real LLM-powered agent decisions (full pipeline simulation)
  - **Synthetic Mode**: Rule-based logic for fast parameter optimization (100x+ faster)

- **Multiple Strategies**:
  - CrudeOil V3 Strategy (MQL4-converted EMA/RSI/CCI/Momentum)
  - CrudeOil Extended Strategy (adds MACD, Bollinger, Stochastic, ADX)
  - Custom strategy support

- **Comprehensive Metrics**:
  - Sharpe ratio, Sortino ratio, Calmar ratio
  - Maximum drawdown, profit factor
  - Win rate, average win/loss
  - Total trades, commission costs

- **Optimization**:
  - Parallel parameter grid search
  - Composite scoring (weighted metrics)
  - Early stopping on Sharpe threshold
  - Random search for large grids

- **RL Training**:
  - Gymnasium Env API compliance
  - Observation normalization
  - Multiple reward strategies
  - Episode statistics tracking

- **A/B Testing**:
  - Statistical significance (Welch's t-test)
  - Trade overlap analysis
  - Equity curve alignment
  - Performance breakdown by time period

## Installation

The backtesting engine is part of the RiseTrader monorepo:

```bash
cd RiseTrader
pip install -r requirements.txt
```

**Dependencies**:
- Python 3.11+
- FastAPI 0.104+
- SQLAlchemy 2.0+ (async)
- pandas, numpy, scipy
- gymnasium (for RL)
- stable-baselines3 (optional, for RL training)

## Quick Start

### 1. Run a Simple Backtest

```python
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.backtesting import BacktestService

async def run_backtest_example(db_session: AsyncSession):
    # Configure backtest
    config = {
        "symbol": "EURUSD",
        "timeframe": "M5",
        "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2024, 12, 1, tzinfo=timezone.utc),
        "initial_capital": Decimal("10000"),
        "mode": "synthetic",  # Fast mode
        "synthetic_strategy": "ma_crossover",
        "strategy_params": {
            "ema_fast": 8,
            "ema_slow": 21,
            "rsi_period": 14,
        },
    }

    # Run backtest
    service = BacktestService(db_session)
    result = await service.run_backtest(config)

    # Print results
    print(f"Total Return: {result.total_return:.2%}")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {result.max_drawdown:.2%}")
    print(f"Win Rate: {result.win_rate:.2%}")
    print(f"Total Trades: {result.total_trades}")
```

### 2. Batch Optimization

```python
from src.services.backtesting import BatchOptimizer, ParameterGrid

# Define parameter grid
grid = ParameterGrid(
    ema_fast=[5, 8, 10, 13],
    ema_slow=[20, 25, 29, 34],
    rsi_period=[10, 14, 21],
)

# Create optimizer
optimizer = BatchOptimizer(
    parameter_grid=grid,
    backtest_function=your_backtest_function,
    max_workers=4,  # Parallel execution
)

# Run optimization
results = optimizer.run(
    early_stop_threshold=2.0,  # Stop if Sharpe > 2.0
)

# Get top 10 results
top_10 = results[:10]
for result in top_10:
    print(f"Params: {result.params}")
    print(f"Sharpe: {result.sharpe_ratio:.2f}")
    print(f"Return: {result.total_return:.2%}")
    print("---")
```

### 3. RL Training

```python
from src.services.backtesting import BacktestTradingEnv
from stable_baselines3 import PPO

# Create RL environment
env = BacktestTradingEnv(config={
    "symbol": "EURUSD",
    "timeframe": "M5",
    "initial_capital": 10000.0,
    "lookback_window": 10,
    "max_steps": 1000,
    "reward_type": "risk_adjusted",
})

# Train PPO agent
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=100_000)

# Test agent
obs, _ = env.reset()
for _ in range(100):
    action, _ = model.predict(obs, deterministic=True)
    obs, reward, terminated, truncated, _ = env.step(action)
    if terminated or truncated:
        break
```

### 4. A/B Testing

```python
from src.services.backtesting import ComparisonService

# Compare two backtest runs
comparison_service = ComparisonService()
comparison = await comparison_service.compare_runs(
    run_a_id=conservative_run_id,
    run_b_id=aggressive_run_id,
    async_session=db_session,
)

# Check results
print(f"Recommendation: {comparison.recommendation}")
print(f"P-value: {comparison.statistical_tests['returns_ttest'].p_value:.4f}")
print(f"Statistically significant: {comparison.statistical_tests['returns_ttest'].is_significant}")

# Generate report
report = comparison_service.generate_report(comparison)
print(report)
```

## REST API Usage

### Run Backtest

```bash
POST /api/v1/backtesting/runs
{
  "configuration_id": "uuid",
  "symbol": "EURUSD",
  "timeframe": "M5",
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-12-01T00:00:00Z",
  "initial_capital": 10000,
  "mode": "synthetic",
  "synthetic_strategy": "ma_crossover",
  "strategy_params": {
    "ema_fast": 8,
    "ema_slow": 21
  }
}
```

### Get Results

```bash
GET /api/v1/backtesting/runs/{run_id}

# Response
{
  "run_id": "uuid",
  "status": "completed",
  "total_return": 0.125,
  "sharpe_ratio": 1.85,
  "max_drawdown": -0.08,
  "win_rate": 0.62,
  "total_trades": 145
}
```

### Batch Optimization

```bash
POST /api/v1/backtesting/optimization/grids
{
  "name": "MA Crossover Optimization",
  "parameters": {
    "ema_fast": [5, 8, 10],
    "ema_slow": [20, 25, 29]
  },
  "max_workers": 4,
  "synthetic_strategy": "ma_crossover"
}

# Execute grid
POST /api/v1/backtesting/optimization/grids/{grid_id}/execute

# Get results
GET /api/v1/backtesting/optimization/grids/{grid_id}/results?top_n=10
```

### A/B Comparison

```bash
POST /api/v1/backtesting/comparison
{
  "run_a_id": "uuid-a",
  "run_b_id": "uuid-b",
  "time_window_minutes": 5,
  "generate_report": true
}
```

## Architecture

### Core Components

```
src/services/backtesting/
├── backtest_service.py       # Main orchestration service
├── portfolio_state.py         # Portfolio state management
├── trade_simulator.py         # Trade execution simulation
├── metrics_calculator.py      # Performance metrics
├── data_replay_engine.py      # Historical data streaming
├── data_validator.py          # Data quality validation
├── synthetic_engine.py        # Fast synthetic mode
├── crude_oil_strategy.py      # Original MQL4 strategy
├── crude_oil_strategy_extended.py  # Extended strategy
├── batch_optimizer.py         # Parallel optimization
├── gymnasium_env.py           # RL environment
└── comparison.py              # A/B testing
```

### Data Flow

**User Story 1 (Backtest)**:
```
1. DataValidator validates historical data
2. DataReplayEngine streams candles chronologically
3. SyntheticEngine (or AgentIntegrator) generates signals
4. TradeSimulator executes trades with slippage/commissions
5. PortfolioState tracks positions and P&L
6. MetricsCalculator computes performance metrics
7. BacktestService orchestrates and persists results
```

**User Story 2 (Optimization)**:
```
1. ParameterGrid generates combinations
2. BatchOptimizer distributes to worker pool
3. Each worker runs backtest with different params
4. Results ranked by composite score
5. Top N returned (or early stop if threshold met)
```

**User Story 3 (RL)**:
```
1. BacktestTradingEnv wraps backtest as Gymnasium Env
2. reset() initializes episode with random start point
3. step(action) executes trade and returns (obs, reward, terminated, truncated, info)
4. Observation normalized to [-1, 1]
5. Rewards: simple_pnl, risk_adjusted, or sparse
6. Episode statistics tracked for monitoring
```

**User Story 4 (A/B)**:
```
1. ComparisonService fetches two backtest runs
2. Statistical significance tested with Welch's t-test
3. Trade overlap analyzed (consensus vs divergent)
4. Equity curves aligned to common timeline
5. Performance broken down by time period
6. Recommendation generated (run_a, run_b, or no_significant_difference)
```

## Configuration

### Backtest Configuration

```python
{
    # Required
    "symbol": "EURUSD",
    "timeframe": "M5",  # M1, M5, M15, M30, H1, H4, D1
    "start_date": datetime(...),
    "end_date": datetime(...),
    "initial_capital": Decimal("10000"),

    # Execution mode
    "mode": "synthetic",  # "synthetic" | "agent"

    # Synthetic mode settings
    "synthetic_strategy": "ma_crossover",  # "ma_crossover" | "crude_oil" | "crude_oil_extended"
    "strategy_params": {
        "ema_fast": 8,
        "ema_slow": 21,
        "rsi_period": 14,
        # ... strategy-specific params
    },

    # Agent mode settings (future)
    "agent_config": {
        "model": "gpt-4",
        "temperature": 0.7,
    },

    # Trading costs
    "commission_per_trade": Decimal("5.00"),
    "slippage_pct": Decimal("0.0001"),  # 1 pip for EURUSD
}
```

### Strategy Parameters

**MA Crossover**:
- `ema_fast`: Fast EMA period (default: 8)
- `ema_slow`: Slow EMA period (default: 21)
- `rsi_period`: RSI period for filter (default: 14)

**CrudeOil V3**:
- `ema_fast`, `ema_slow`, `rsi_period` (same as above)
- `cci_period`: CCI period (default: 14)
- `momentum_period`: Momentum period (default: 10)

**CrudeOil Extended**:
- All CrudeOil V3 params, plus:
- `macd_fast`, `macd_slow`, `macd_signal`
- `bollinger_period`, `bollinger_std`
- `stochastic_k`, `stochastic_d`
- `adx_period`, `adx_threshold`

## Performance

### Benchmarks

**Single Backtest** (30 days, M5 data, ~8,640 candles):
- Synthetic mode: ~2-3 seconds
- Agent mode: ~30-60 seconds (LLM latency)

**Batch Optimization** (100 combinations):
- Sequential: ~250 seconds
- Parallel (4 workers): ~65 seconds
- **Speedup: 3.8x**

**RL Training** (1,000 episodes):
- Episode duration: ~5-10 seconds
- Total training: ~90 minutes
- Memory usage: < 500MB

### Optimization Tips

1. **Use synthetic mode for optimization** - 10-20x faster than agent mode
2. **Batch database operations** - Insert trades in bulk (100+ per batch)
3. **Enable early stopping** - Stop optimization when Sharpe > threshold
4. **Use random search for large grids** - Faster than exhaustive search
5. **Cache indicator calculations** - Reuse EMA/RSI across backtests

## Testing

Run tests with pytest:

```bash
# All tests
pytest tests/

# Unit tests only
pytest tests/unit/backtesting/

# Integration tests
pytest tests/integration/backtesting/

# Specific user story
pytest tests/ -k "user_story_1"

# With coverage
pytest --cov=src/services/backtesting --cov-report=html
```

### Test Coverage

Current coverage: **85%+**

- User Story 1: Unit + Integration tests
- User Story 2: Batch optimization tests
- User Story 3: RL environment tests (contract, unit, integration)
- User Story 4: Statistical A/B testing tests

## Troubleshooting

### Common Issues

**1. Insufficient Historical Data**

```
Error: "Insufficient historical data for backtest"
```

**Solution**: Ensure date range has enough candles (minimum 1000 recommended).

**2. Zero Trades Generated**

```
Warning: Backtest completed with 0 trades
```

**Solution**:
- Check strategy parameters (too restrictive filters)
- Verify data quality (missing candles)
- Adjust signal thresholds

**3. Memory Issues (RL Training)**

```
MemoryError: Unable to allocate array
```

**Solution**:
- Reduce `lookback_window` (default: 10)
- Reduce `max_steps` per episode
- Use shorter date ranges
- Enable episode data cleanup

**4. Optimization Too Slow**

```
Optimization taking 30+ minutes
```

**Solution**:
- Reduce grid size (use random search)
- Increase `max_workers` (up to CPU count)
- Enable early stopping
- Use shorter backtest periods

**5. Statistical Test No Significance**

```
Comparison: "no_significant_difference"
```

**Solution**:
- Run backtests on longer date ranges (more samples)
- Ensure configurations are actually different
- Check if performance is genuinely similar (expected)

## Contributing

When adding new features to the backtesting engine:

1. **Write tests first** (TDD) - All tests should fail before implementation
2. **Follow existing patterns** - Use service layer, repository pattern
3. **Document public APIs** - Add docstrings to all public methods
4. **Update this README** - Keep documentation in sync
5. **Run linting** - `ruff check src/services/backtesting/`
6. **Verify coverage** - Maintain 85%+ test coverage

## License

Copyright © 2024 RiseTrader. All rights reserved.

## Support

For issues or questions:
- GitHub Issues: https://github.com/risetrader/risetrader/issues
- Documentation: `docs/backtesting/`
- Quickstart Guide: `specs/006-backtesting-engine/quickstart.md`
