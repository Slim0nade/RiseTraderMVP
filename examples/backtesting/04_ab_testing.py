"""
Example 4: A/B Testing Configurations

Demonstrates statistical comparison of two configurations:
1. Run backtest A (Conservative)
2. Run backtest B (Aggressive)
3. Compare with statistical significance
4. Make data-driven decision

This example shows how to choose between two trading strategies.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.services.backtesting import BacktestService, ComparisonService


async def main():
    """Run A/B testing example."""

    # Create database connection
    DATABASE_URL = "postgresql+asyncpg://localhost/risetrader"
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Configuration A: Conservative (1% position size, slow MA)
        print("Running backtest A (Conservative)...")
        config_a = {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "end_date": datetime(2024, 3, 1, tzinfo=timezone.utc),  # 2 months
            "initial_capital": Decimal("10000"),
            "mode": "synthetic",
            "synthetic_strategy": "ma_crossover",
            "strategy_params": {
                "ema_fast": 10,  # Slower signals
                "ema_slow": 25,
                "rsi_period": 14,
                "position_size": 0.01,  # Conservative: 1% risk
            },
        }

        service = BacktestService(session)
        result_a = await service.run_backtest(config_a)

        print(f"  Return: {result_a.total_return:.2%}")
        print(f"  Sharpe: {result_a.sharpe_ratio:.2f}")
        print(f"  Trades: {result_a.total_trades}")

        # Configuration B: Aggressive (5% position size, fast MA)
        print("\nRunning backtest B (Aggressive)...")
        config_b = {
            **config_a,
            "strategy_params": {
                "ema_fast": 5,   # Faster signals
                "ema_slow": 13,
                "rsi_period": 7,
                "position_size": 0.05,  # Aggressive: 5% risk
            },
        }

        result_b = await service.run_backtest(config_b)

        print(f"  Return: {result_b.total_return:.2%}")
        print(f"  Sharpe: {result_b.sharpe_ratio:.2f}")
        print(f"  Trades: {result_b.total_trades}")

        # Statistical comparison
        print("\n" + "="*80)
        print("STATISTICAL A/B COMPARISON")
        print("="*80)

        comparison_service = ComparisonService()
        comparison = await comparison_service.compare_runs(
            run_a_id=result_a.run_id,
            run_b_id=result_b.run_id,
            async_session=session,
            time_window_minutes=5,
        )

        # Print side-by-side metrics
        print("\nSide-by-Side Metrics:")
        print(f"{'Metric':<20} {'Conservative':<15} {'Aggressive':<15} {'Difference':<15}")
        print("-"*65)

        metrics_a = comparison.metrics_comparison["run_a"]
        metrics_b = comparison.metrics_comparison["run_b"]

        print(f"{'Total Return':<20} {metrics_a['total_return']:>13.2%} {metrics_b['total_return']:>13.2%}  {metrics_a['total_return'] - metrics_b['total_return']:>13.2%}")
        print(f"{'Sharpe Ratio':<20} {metrics_a['sharpe_ratio']:>13.2f} {metrics_b['sharpe_ratio']:>13.2f}  {metrics_a['sharpe_ratio'] - metrics_b['sharpe_ratio']:>13.2f}")
        print(f"{'Max Drawdown':<20} {metrics_a['max_drawdown']:>13.2%} {metrics_b['max_drawdown']:>13.2%}  {metrics_a['max_drawdown'] - metrics_b['max_drawdown']:>13.2%}")
        print(f"{'Win Rate':<20} {metrics_a['win_rate']:>13.2%} {metrics_b['win_rate']:>13.2%}  {metrics_a['win_rate'] - metrics_b['win_rate']:>13.2%}")
        print(f"{'Total Trades':<20} {metrics_a['total_trades']:>13} {metrics_b['total_trades']:>13}  {metrics_a['total_trades'] - metrics_b['total_trades']:>13}")

        # Statistical significance
        ttest = comparison.statistical_tests["returns_ttest"]

        print("\n" + "-"*80)
        print("Statistical Significance (Welch's t-test):")
        print(f"  T-statistic:      {ttest.t_statistic:.3f}")
        print(f"  P-value:          {ttest.p_value:.4f}")
        print(f"  Significant:      {ttest.is_significant} (p < 0.05)")
        print(f"  Mean Difference:  {ttest.mean_difference:.4f}")
        print(f"  95% CI:           ({ttest.confidence_interval[0]:.4f}, {ttest.confidence_interval[1]:.4f})")

        # Trade overlap
        overlap = comparison.trade_overlap

        print("\n" + "-"*80)
        print("Trade Overlap Analysis:")
        print(f"  Consensus Trades:  {overlap.consensus_trades} (both configurations took same trades)")
        print(f"  Divergent A:       {overlap.divergent_trades_a} (only Conservative took these)")
        print(f"  Divergent B:       {overlap.divergent_trades_b} (only Aggressive took these)")
        print(f"  Overlap Rate:      {overlap.overlap_rate:.2%}")

        # Recommendation
        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80)

        if comparison.recommendation == "run_a":
            print("✅ Choose CONSERVATIVE configuration")
            print("   Statistically superior performance")
        elif comparison.recommendation == "run_b":
            print("✅ Choose AGGRESSIVE configuration")
            print("   Statistically superior performance")
        else:
            print("⚠️  NO SIGNIFICANT DIFFERENCE")
            print("   Choose based on:")
            print("   - Risk tolerance (Conservative = lower risk)")
            print("   - Trade frequency preferences")
            print("   - Other non-statistical factors")

        if ttest.is_significant:
            print(f"\n📊 Statistical confidence: {(1 - ttest.p_value) * 100:.1f}%")
        else:
            print(f"\n📊 Not statistically significant (p = {ttest.p_value:.4f})")
            print("   Consider running longer backtests for more data")


if __name__ == "__main__":
    asyncio.run(main())
