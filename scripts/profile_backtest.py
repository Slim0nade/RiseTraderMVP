"""
Profiling script for backtesting performance analysis.

T118: Profile backtest execution and optimize hot paths

Usage:
    python scripts/profile_backtest.py

Outputs:
    - CPU profiling data (cProfile)
    - Memory profiling data (memory_profiler)
    - Hot path identification
    - Optimization recommendations
"""
import asyncio
import cProfile
import pstats
import io
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.services.backtesting import BacktestService


async def run_profiled_backtest():
    """Run a backtest with profiling enabled."""

    # Database connection
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/risetrader")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Configure a medium-sized backtest for profiling
        config = {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "end_date": datetime(2024, 2, 1, tzinfo=timezone.utc),  # 1 month
            "initial_capital": Decimal("10000"),
            "mode": "synthetic",
            "synthetic_strategy": "ma_crossover",
            "strategy_params": {
                "ema_fast": 8,
                "ema_slow": 21,
                "rsi_period": 14,
            },
        }

        print("="*80)
        print("BACKTESTING PERFORMANCE PROFILER")
        print("="*80)
        print(f"Symbol: {config['symbol']}")
        print(f"Period: {config['start_date'].date()} to {config['end_date'].date()}")
        print(f"Timeframe: {config['timeframe']}")
        print("\nStarting profiled backtest...")

        # Create profiler
        profiler = cProfile.Profile()

        # Run backtest with profiling
        profiler.enable()
        service = BacktestService(session)
        result = await service.run_backtest(config)
        profiler.disable()

        print(f"\n✅ Backtest complete")
        print(f"   Total Return: {result.total_return:.2%}")
        print(f"   Total Trades: {result.total_trades}")

        # Analyze profiling results
        print("\n" + "="*80)
        print("PROFILING RESULTS")
        print("="*80)

        # Create stats object
        stats_stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stats_stream)

        # Sort by cumulative time
        print("\n📊 TOP 20 FUNCTIONS BY CUMULATIVE TIME:")
        print("-"*80)
        stats.sort_stats('cumulative')
        stats.print_stats(20)

        # Sort by total time
        print("\n⏱️  TOP 20 FUNCTIONS BY TOTAL TIME:")
        print("-"*80)
        stats.sort_stats('tottime')
        stats.print_stats(20)

        # Sort by calls
        print("\n🔁 TOP 20 FUNCTIONS BY CALL COUNT:")
        print("-"*80)
        stats.sort_stats('ncalls')
        stats.print_stats(20)

        # Print full stats to file
        with open("backtest_profile.txt", "w") as f:
            stats = pstats.Stats(profiler, stream=f)
            stats.sort_stats('cumulative')
            stats.print_stats()

        print("\n" + "="*80)
        print("OPTIMIZATION RECOMMENDATIONS")
        print("="*80)
        print("""
Based on profiling results, consider:

1. **Hot Paths Identified**:
   - Look for functions with high 'tottime' or 'cumtime'
   - Functions called many times (high 'ncalls')

2. **Common Bottlenecks**:
   - Database queries (await statements)
   - Indicator calculations (EMA, RSI, etc.)
   - Metrics computation (Sharpe, drawdown)
   - NumPy array operations

3. **Optimization Strategies**:
   - Enable Numba JIT: `USE_OPTIMIZED_METRICS=1` (T119)
   - Batch database inserts (T120)
   - Cache indicator calculations (T121)
   - Use vectorized NumPy operations
   - Consider async batching for DB operations

4. **Quick Wins**:
   - If metrics_calculator methods are hot → Enable Numba (pip install numba)
   - If database queries are slow → Add indexes or batch operations
   - If indicator calculations are slow → Cache results

Full profiling data saved to: backtest_profile.txt
        """)


async def compare_optimizations():
    """
    Compare performance with different optimization levels.

    Runs same backtest with:
    1. No optimizations
    2. With Numba JIT (if available)
    3. With caching (if implemented)
    """
    import time

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/risetrader")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    config = {
        "symbol": "EURUSD",
        "timeframe": "M5",
        "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2024, 1, 15, tzinfo=timezone.utc),  # 2 weeks for speed
        "initial_capital": Decimal("10000"),
        "mode": "synthetic",
        "synthetic_strategy": "ma_crossover",
        "strategy_params": {
            "ema_fast": 8,
            "ema_slow": 21,
            "rsi_period": 14,
        },
    }

    print("\n" + "="*80)
    print("OPTIMIZATION COMPARISON")
    print("="*80)

    async with async_session_maker() as session:
        # Baseline (no optimizations)
        print("\n1️⃣  Running baseline (no optimizations)...")
        os.environ["USE_OPTIMIZED_METRICS"] = "0"
        start = time.perf_counter()
        service = BacktestService(session)
        result_baseline = await service.run_backtest(config)
        baseline_time = time.perf_counter() - start
        print(f"   Time: {baseline_time:.3f} seconds")
        print(f"   Return: {result_baseline.total_return:.2%}")

    # With Numba (if available)
    async with async_session_maker() as session:
        print("\n2️⃣  Running with Numba JIT...")
        os.environ["USE_OPTIMIZED_METRICS"] = "1"
        start = time.perf_counter()
        service = BacktestService(session)
        result_optimized = await service.run_backtest(config)
        optimized_time = time.perf_counter() - start
        print(f"   Time: {optimized_time:.3f} seconds")
        print(f"   Return: {result_optimized.total_return:.2%}")

        # Calculate speedup
        speedup = (baseline_time / optimized_time) if optimized_time > 0 else 1.0
        print(f"\n   🚀 Speedup: {speedup:.2f}x")

        if speedup > 1.1:
            print(f"   ✅ Optimization effective ({(speedup - 1) * 100:.1f}% faster)")
        else:
            print(f"   ⚠️  Marginal improvement (install numba: pip install numba)")


if __name__ == "__main__":
    print("Starting performance profiling...")
    print("(This may take 30-60 seconds)\n")

    # Run profiled backtest
    asyncio.run(run_profiled_backtest())

    # Compare optimizations
    print("\n" + "="*80)
    asyncio.run(compare_optimizations())

    print("\n" + "="*80)
    print("✅ Profiling complete!")
    print("="*80)
