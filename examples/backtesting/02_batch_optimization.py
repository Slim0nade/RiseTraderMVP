"""
Example 2: Batch Parameter Optimization

Demonstrates parameter grid search:
1. Define parameter grid
2. Run parallel optimization
3. Analyze top results
4. Compare best vs worst

This example shows how to optimize EMA crossover parameters.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.services.backtesting import (
    BacktestService,
    BatchOptimizer,
    ParameterGrid,
    create_quick_grid,
)


async def backtest_function(params: dict, session: AsyncSession) -> dict:
    """Wrapper function for batch optimizer."""
    config = {
        "symbol": "EURUSD",
        "timeframe": "M5",
        "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2024, 2, 1, tzinfo=timezone.utc),
        "initial_capital": Decimal("10000"),
        "mode": "synthetic",
        "synthetic_strategy": "ma_crossover",
        "strategy_params": params,
    }

    service = BacktestService(session)
    result = await service.run_backtest(config)

    return {
        "params": params,
        "total_return": float(result.total_return or 0),
        "sharpe_ratio": float(result.sharpe_ratio or 0),
        "max_drawdown": float(result.max_drawdown or 0),
        "profit_factor": float(result.profit_factor or 0),
        "total_trades": result.total_trades or 0,
    }


async def main():
    """Run batch optimization example."""

    # Create database connection
    DATABASE_URL = "postgresql+asyncpg://localhost/risetrader"
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Define parameter grid
        print("Creating parameter grid...")
        grid = ParameterGrid(
            ema_fast=[5, 8, 10, 13],        # 4 values
            ema_slow=[20, 25, 29, 34],      # 4 values
            rsi_period=[10, 14, 21],        # 3 values
        )

        total_combinations = 4 * 4 * 3  # = 48 combinations
        print(f"Total combinations: {total_combinations}")

        # Create optimizer
        optimizer = BatchOptimizer(
            parameter_grid=grid,
            backtest_function=lambda params: backtest_function(params, session),
            max_workers=4,  # Run 4 backtests in parallel
        )

        # Run optimization
        print(f"\nRunning optimization with {4} parallel workers...")
        results = optimizer.run(
            early_stop_threshold=2.0,  # Stop if Sharpe > 2.0
        )

        print(f"Completed {len(results)} backtests")

        # Analyze results
        print("\n" + "="*80)
        print("TOP 10 PARAMETER COMBINATIONS")
        print("="*80)

        for i, result in enumerate(results[:10], 1):
            print(f"\n#{i}")
            print(f"  Parameters:")
            print(f"    - EMA Fast:   {result['params']['ema_fast']}")
            print(f"    - EMA Slow:   {result['params']['ema_slow']}")
            print(f"    - RSI Period: {result['params']['rsi_period']}")
            print(f"  Performance:")
            print(f"    - Sharpe:     {result['sharpe_ratio']:.2f}")
            print(f"    - Return:     {result['total_return']:.2%}")
            print(f"    - Drawdown:   {result['max_drawdown']:.2%}")
            print(f"    - Trades:     {result['total_trades']}")

        # Compare best vs worst
        best = results[0]
        worst = results[-1]

        print("\n" + "="*80)
        print("BEST vs WORST COMPARISON")
        print("="*80)
        print(f"\nBEST:")
        print(f"  Params: EMA {best['params']['ema_fast']}/{best['params']['ema_slow']}, RSI {best['params']['rsi_period']}")
        print(f"  Sharpe: {best['sharpe_ratio']:.2f}")
        print(f"  Return: {best['total_return']:.2%}")

        print(f"\nWORST:")
        print(f"  Params: EMA {worst['params']['ema_fast']}/{worst['params']['ema_slow']}, RSI {worst['params']['rsi_period']}")
        print(f"  Sharpe: {worst['sharpe_ratio']:.2f}")
        print(f"  Return: {worst['total_return']:.2%}")

        improvement = ((best['sharpe_ratio'] - worst['sharpe_ratio']) / abs(worst['sharpe_ratio']) * 100
                      if worst['sharpe_ratio'] != 0 else 0)
        print(f"\n💡 Best parameters improved Sharpe by {improvement:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
