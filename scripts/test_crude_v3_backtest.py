#!/usr/bin/env python3
"""
Test CrudeOil Strategy V3 (Extended) backtest.

This script runs a backtest using the CrudeOilStrategyExtended with historical data.
Tests the full indicator suite including EMA, RSI, CCI, MACD, Bollinger Bands, etc.

Usage:
    python scripts/test_crude_v3_backtest.py
    python scripts/test_crude_v3_backtest.py --period 3  # 3 months
    python scripts/test_crude_v3_backtest.py --year 2024
"""
import asyncio
import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.backtesting import BacktestService
from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.market_data_repository import MarketDataRepository


async def run_backtest(
    start_date: datetime,
    end_date: datetime,
    initial_capital: Decimal = Decimal("10000.00"),
    strategy_params: dict = None
):
    """Run CrudeOil V3 backtest for specified period."""

    # Database connection
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres@localhost:5433/risetrader"
    )

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Initialize repositories and service
        backtest_repo = BacktestRepository(session)
        market_repo = MarketDataRepository(session)
        service = BacktestService(session, backtest_repo, market_repo)

        # Default strategy parameters (from MQL4 original + extended)
        if strategy_params is None:
            strategy_params = {
                # Original indicators
                "ema_fast": 8,
                "ema_slow": 29,
                "rsi_period": 10,
                "rsi_overbought": 68,
                "rsi_oversold": 32,
                "cci_period": 20,
                "cci_overbought": 100,
                "cci_oversold": -80,
                "use_cci_filter": True,

                # Risk management
                "atr_period": 10,
                "atr_multiplier": 2.0,
                "take_profit_multiplier": 2.5,
                "quantity": 1.0,

                # Extended filters (optional, set to False to disable)
                "use_macd_filter": False,
                "use_bollinger_filter": False,
                "use_stochastic_filter": False,
                "use_adx_filter": False,
                "use_volume_filter": False,
            }

        # Create backtest configuration
        period_str = f"{start_date.date()} to {end_date.date()}"
        config = await service.create_configuration(
            name=f"CrudeOil V3 Extended - {period_str}",
            symbol="CrudeOIL",
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            execution_mode="synthetic_fast",
            slippage_pct=Decimal("0.001"),  # 0.1% slippage
            commission_pct=Decimal("0.0005"),  # 0.05% commission
            config_params={
                "strategy": "crude_oil_v3",
                "strategy_params": strategy_params
            }
        )

        print("=" * 70)
        print("CRUDEOIL STRATEGY V3 (EXTENDED) BACKTEST")
        print("=" * 70)
        print(f"Period:           {period_str}")
        print(f"Initial Capital:  ${initial_capital:,.2f}")
        print(f"Symbol:           {config.symbol}")
        print(f"Timeframe:        M5 (5-minute bars)")
        print(f"Execution Mode:   {config.execution_mode}")
        print()

        # Validate data availability
        print("Validating data availability...")
        validation = await service.validate_configuration(config, timeframe="M5")

        if not validation["can_proceed"]:
            print(f"\n❌ Validation failed: {validation['message']}")
            print(f"   Available data: {validation.get('available_data_info', 'N/A')}")
            return None

        print(f"✅ Data validated")
        print(f"   Available candles: {validation.get('available_candles', 0):,}")
        print(f"   Data range: {validation.get('data_start', 'N/A')} to {validation.get('data_end', 'N/A')}")
        print()

        # Run backtest
        print("Running backtest...")
        print("(This may take 10-30 seconds depending on data volume)")
        print()

        progress_count = [0]
        def progress_callback(processed, total, message=None):
            progress_count[0] = processed
            if processed % 1000 == 0 or processed == total:
                pct = (processed / total * 100) if total > 0 else 0
                print(f"  Progress: {processed:,}/{total:,} candles ({pct:.1f}%)")

        # Execute backtest
        run = await service.run_backtest(
            config_id=config.id,
            timeframe="M5",
            progress_callback=progress_callback
        )

        # Print results
        print()
        print("=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)
        print()

        print("Performance Metrics:")
        print(f"  Total Return:        {getattr(run, 'total_return_pct', 0):>8.2f}%")
        print(f"  Sharpe Ratio:        {getattr(run, 'sharpe_ratio', 0):>8.2f}")
        print(f"  Sortino Ratio:       {getattr(run, 'sortino_ratio', 0):>8.2f}")
        print(f"  Calmar Ratio:        {getattr(run, 'calmar_ratio', 0):>8.2f}")
        print()

        print("Risk Metrics:")
        print(f"  Max Drawdown:        {getattr(run, 'max_drawdown_pct', 0):>8.2f}%")
        print(f"  Max Drawdown Duration: {(run.metrics or {}).get('max_drawdown_duration_days', 0):>6.0f} days")
        print(f"  Volatility (ann.):   {(run.metrics or {}).get('annual_volatility', 0):>8.2f}%")
        print()

        print("Trading Metrics:")
        print(f"  Total Trades:        {getattr(run, 'total_trades', 0):>8}")
        print(f"  Win Rate:            {getattr(run, 'win_rate', 0):>8.2f}%")
        print(f"  Profit Factor:       {getattr(run, 'profit_factor', 0):>8.2f}")
        print(f"  Average Win:         ${(run.metrics or {}).get('avg_win', 0):>7.2f}")
        print(f"  Average Loss:        ${(run.metrics or {}).get('avg_loss', 0):>7.2f}")
        print(f"  Largest Win:         ${(run.metrics or {}).get('largest_win', 0):>7.2f}")
        print(f"  Largest Loss:        ${(run.metrics or {}).get('largest_loss', 0):>7.2f}")
        print()

        print("Execution Details:")
        print(f"  Duration:            {run.end_time - run.start_time}")
        print(f"  Status:              {run.status}")
        print(f"  Candles Processed:   {progress_count[0]:,}")
        if hasattr(run, 'final_capital') and run.final_capital:
            print(f"  Final Capital:       ${float(run.final_capital):,.2f}")
        print()

        print("=" * 70)

        # Performance summary
        print()
        sharpe = getattr(run, 'sharpe_ratio', 0)
        if sharpe > 2.0:
            print("🎉 Excellent performance! Sharpe > 2.0")
        elif sharpe > 1.0:
            print("✅ Good performance! Sharpe > 1.0")
        elif sharpe > 0:
            print("⚠️  Marginal performance. Sharpe > 0 but needs optimization")
        else:
            print("❌ Poor performance. Sharpe < 0")

        print()
        print(f"Backtest Run ID: {run.id}")
        print(f"Configuration ID: {config.id}")
        print()

        return run


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run CrudeOil Strategy V3 backtest"
    )
    parser.add_argument(
        "--period",
        type=int,
        default=1,
        help="Number of months to test (default: 1)"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="Year to test (default: 2024)"
    )
    parser.add_argument(
        "--month",
        type=int,
        help="Specific month to test (1-12)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000)"
    )

    args = parser.parse_args()

    # Determine date range
    if args.month:
        # Specific month
        start_date = datetime(args.year, args.month, 1, tzinfo=timezone.utc)
        # Last day of month
        if args.month == 12:
            end_date = datetime(args.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(args.year, args.month + 1, 1, tzinfo=timezone.utc)
    else:
        # First N months of year
        start_date = datetime(args.year, 1, 1, tzinfo=timezone.utc)
        if args.period >= 12:
            end_date = datetime(args.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(args.year, args.period + 1, 1, tzinfo=timezone.utc)

    # Run backtest
    try:
        run = await run_backtest(
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(args.capital))
        )

        if run:
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
