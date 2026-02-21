#!/usr/bin/env python3
"""
Test Agent-Mode Backtest with Ollama LLM.

This script runs a backtest using the full_pipeline execution mode where
trading decisions are made by an LLM-powered agent via Ollama rather than
rule-based strategies.

Usage:
    python scripts/test_agent_backtest.py
    python scripts/test_agent_backtest.py --days 3  # 3 days
    python scripts/test_agent_backtest.py --model deepseek-r1:14b
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


async def run_agent_backtest(
    start_date: datetime,
    end_date: datetime,
    initial_capital: Decimal = Decimal("10000.00"),
    model: str = "qwen3:14b",
    ollama_url: str = "http://192.168.0.123:11434/v1",
    decision_threshold: float = 0.6,
):
    """Run agent-mode backtest using Ollama LLM."""

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

        # Create backtest configuration for agent mode
        period_str = f"{start_date.date()} to {end_date.date()}"
        config = await service.create_configuration(
            name=f"Agent Mode ({model}) - {period_str}",
            symbol="CrudeOIL",
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            execution_mode="full_pipeline",  # Use agent mode!
            slippage_pct=Decimal("0.001"),  # 0.1% slippage
            commission_pct=Decimal("0.0005"),  # 0.05% commission
            config_params={
                "agent_config": {
                    "model": model,
                    "ollama_base_url": ollama_url,
                    "decision_threshold": decision_threshold,
                }
            }
        )

        print("=" * 70)
        print("AGENT-MODE BACKTEST (OLLAMA LLM)")
        print("=" * 70)
        print(f"Period:           {period_str}")
        print(f"Initial Capital:  ${initial_capital:,.2f}")
        print(f"Symbol:           {config.symbol}")
        print(f"Timeframe:        M5 (5-minute bars)")
        print(f"Execution Mode:   {config.execution_mode}")
        print(f"LLM Model:        {model}")
        print(f"Ollama Server:    {ollama_url}")
        print(f"Decision Threshold: {decision_threshold}")
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
        print("Running agent-mode backtest...")
        print("⚠️  NOTE: This will be MUCH slower than synthetic mode (~5s per decision)")
        print("   Agent makes decisions every 10 candles to balance speed vs accuracy")
        print()

        progress_count = [0]
        def progress_callback(processed, total, message=None):
            progress_count[0] = processed
            if processed % 500 == 0 or processed == total:
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
        print(f"  Candles Processed:   {getattr(run, 'candles_processed', progress_count[0]):,}")
        print(f"  Agent Decisions:     {getattr(run, 'agent_decisions_count', 0):,}")
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
        description="Run Agent-Mode Backtest with Ollama LLM"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to test (default: 1, max: 7 for reasonable speed)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen3:14b",
        choices=["qwen3:14b", "deepseek-r1:14b"],
        help="Ollama model to use (default: qwen3:14b)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="Decision conviction threshold (0.0-1.0, default: 0.6)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000)"
    )

    args = parser.parse_args()

    # Determine date range (recent data for speed)
    end_date = datetime(2024, 2, 1, tzinfo=timezone.utc)  # Start of Feb 2024
    start_date = end_date - timedelta(days=args.days)

    print()
    print(f"Testing {args.days} day(s) with {args.model}")
    print(f"Expected agent decisions: ~{args.days * 288 // 10} (every 10 candles)")
    print(f"Estimated time: ~{args.days * 288 // 10 * 3 // 60} minutes")
    print()

    # Run backtest
    try:
        run = await run_agent_backtest(
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(args.capital)),
            model=args.model,
            decision_threshold=args.threshold,
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
