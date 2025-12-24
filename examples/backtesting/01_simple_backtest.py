"""
Example 1: Simple Backtest

Demonstrates basic backtesting workflow:
1. Connect to database
2. Configure backtest
3. Run backtest
4. Print results

This is the most basic example - runs a single backtest with MA crossover strategy.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.services.backtesting import BacktestService


async def main():
    """Run a simple backtest example."""

    # Create database connection
    DATABASE_URL = "postgresql+asyncpg://localhost/risetrader"
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Configure backtest
        config = {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "end_date": datetime(2024, 1, 31, tzinfo=timezone.utc),  # 1 month
            "initial_capital": Decimal("10000"),
            "mode": "synthetic",  # Fast mode
            "synthetic_strategy": "ma_crossover",
            "strategy_params": {
                "ema_fast": 8,
                "ema_slow": 21,
                "rsi_period": 14,
            },
            "commission_per_trade": Decimal("5.00"),
            "slippage_pct": Decimal("0.0001"),  # 1 pip
        }

        # Create service and run backtest
        service = BacktestService(session)
        print("Running backtest...")
        result = await service.run_backtest(config)

        # Print results
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        print(f"Symbol:          {config['symbol']}")
        print(f"Period:          {config['start_date'].date()} to {config['end_date'].date()}")
        print(f"Initial Capital: ${config['initial_capital']:,.2f}")
        print("-"*60)
        print(f"Total Return:    {result.total_return:.2%}")
        print(f"Sharpe Ratio:    {result.sharpe_ratio:.2f}")
        print(f"Sortino Ratio:   {result.sortino_ratio:.2f}")
        print(f"Max Drawdown:    {result.max_drawdown:.2%}")
        print(f"Profit Factor:   {result.profit_factor:.2f}")
        print(f"Win Rate:        {result.win_rate:.2%}")
        print("-"*60)
        print(f"Total Trades:    {result.total_trades}")
        print(f"Winning Trades:  {result.winning_trades}")
        print(f"Losing Trades:   {result.losing_trades}")
        print(f"Avg Win:         ${result.avg_win:.2f}")
        print(f"Avg Loss:        ${result.avg_loss:.2f}")
        print("="*60)

        # Verdict
        if result.sharpe_ratio > 1.5:
            print("✅ EXCELLENT - Sharpe > 1.5")
        elif result.sharpe_ratio > 1.0:
            print("✅ GOOD - Sharpe > 1.0")
        elif result.sharpe_ratio > 0.5:
            print("⚠️  MEDIOCRE - Sharpe > 0.5")
        else:
            print("❌ POOR - Sharpe < 0.5")


if __name__ == "__main__":
    asyncio.run(main())
