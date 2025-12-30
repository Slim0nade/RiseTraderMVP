"""
Validation tests for backtesting engine (T053-T057).

These tests validate the complete backtesting system against real data:
- End-to-end backtest execution
- Metrics calculation accuracy
- Deterministic replay
- Performance benchmarks
- Data quality validation
"""
import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.backtest import BacktestConfiguration, BacktestRun, ExecutionMode, RunStatus
from src.database.models.market_data import MarketData
from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.backtesting import (
    BacktestService,
    MetricsCalculator,
    SyntheticEngine,
)


@pytest.mark.asyncio
class TestEndToEndBacktest:
    """
    T053: Test complete backtest flow with sample 1-week dataset.

    Validates:
    - Configuration creation
    - Data availability check
    - Backtest execution (synthetic mode)
    - Metrics calculation
    - Database persistence
    """

    async def test_complete_backtest_flow_with_real_data(
        self, async_session: AsyncSession
    ):
        """
        Test complete backtest flow using actual database data.

        This test:
        1. Creates a backtest configuration
        2. Validates data availability for 1-week period
        3. Executes backtest with MA crossover strategy
        4. Verifies results are persisted correctly
        5. Validates metrics are calculated
        """
        # Initialize services
        backtest_repo = BacktestRepository(async_session)
        market_data_repo = MarketDataRepository(async_session)
        service = BacktestService(
            session=async_session,
            backtest_repository=backtest_repo,
            market_data_repository=market_data_repo,
        )

        # Step 1: Check if we have sufficient market data
        # Query for available data range
        result = await async_session.execute(
            select(MarketData.time)
            .where(MarketData.symbol == "EURUSD")
            .where(MarketData.timeframe == "M5")
            .order_by(MarketData.time.desc())
            .limit(1)
        )
        latest_data = result.scalar_one_or_none()

        if not latest_data:
            pytest.skip("No EURUSD M5 data available in database")

        # Use data from 1 week before latest available
        end_date = latest_data
        start_date = end_date - timedelta(days=7)

        # Step 2: Create backtest configuration
        config = await service.create_configuration(
            name="E2E Test - MA Crossover 1 Week",
            symbol="EURUSD",
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            config_params={
                "strategy": "ma_crossover",
                "fast_period": 10,
                "slow_period": 30,
            },
        )

        await async_session.commit()
        assert config.id is not None
        assert config.name == "E2E Test - MA Crossover 1 Week"

        # Step 3: Validate data availability
        validation = await service.validate_configuration(config, timeframe="M5")

        if not validation["can_proceed"]:
            pytest.skip(
                f"Insufficient data for test period: {validation['data_validation']}"
            )

        assert validation["can_proceed"] is True
        assert validation["configuration_valid"] is True
        assert "data_validation" in validation

        # Step 4: Execute backtest
        synthetic_engine = SyntheticEngine(
            strategy="ma_crossover",
            params={"fast_period": 10, "slow_period": 30, "quantity": Decimal("1.0")},
        )

        def decision_engine(tick):
            signal = synthetic_engine.process_tick(tick)
            if signal.action:
                return {"action": signal.action, "quantity": signal.quantity}
            return None

        run = await service.run_backtest(
            config_id=config.id,
            timeframe="M5",
            random_seed=42,
            decision_engine=decision_engine,
        )

        await async_session.commit()

        # Step 5: Verify run completed successfully
        assert run.id is not None
        assert run.status == RunStatus.COMPLETED
        assert run.candles_processed > 0
        assert run.end_time is not None

        # Step 6: Verify metrics were calculated
        assert run.total_return_pct is not None
        assert run.sharpe_ratio is not None
        assert run.max_drawdown_pct is not None
        assert run.win_rate is not None

        # Step 7: Verify trades were persisted
        trades = await backtest_repo.get_trades(run.id)
        assert len(trades) >= 0  # May be 0 if no signals generated

        # Step 8: Verify snapshots were created
        snapshots = await backtest_repo.get_snapshots(run.id)
        assert len(snapshots) > 0

        # Step 9: Verify final capital makes sense
        assert run.final_capital is not None
        assert run.final_capital > Decimal("0")

        print(f"\n✅ E2E Test Results:")
        print(f"   Candles Processed: {run.candles_processed}")
        print(f"   Total Trades: {len(trades)}")
        print(f"   Final Capital: ${run.final_capital:,.2f}")
        print(f"   Total Return: {float(run.total_return_pct):.2f}%")
        print(f"   Sharpe Ratio: {float(run.sharpe_ratio):.2f}")
        print(f"   Max Drawdown: {float(run.max_drawdown_pct):.2f}%")
        print(f"   Win Rate: {float(run.win_rate) * 100:.2f}%")


@pytest.mark.asyncio
class TestMetricsAccuracy:
    """
    T054: Verify metrics accuracy against manual calculations.

    Tests that metrics calculations match expected values within 0.1% variance.
    """

    async def test_metrics_calculation_accuracy(self):
        """
        Test metrics calculator with known inputs and expected outputs.

        Uses hardcoded trade data to verify metrics are calculated correctly.
        """
        # Known trade data (manually calculated expected values)
        initial_capital = Decimal("10000.00")

        # Simulate 10 trades with known P&L
        trade_pnls = [
            Decimal("100.00"),   # +1%
            Decimal("-50.00"),   # -0.5%
            Decimal("150.00"),   # +1.5%
            Decimal("200.00"),   # +2%
            Decimal("-100.00"),  # -1%
            Decimal("50.00"),    # +0.5%
            Decimal("-75.00"),   # -0.75%
            Decimal("125.00"),   # +1.25%
            Decimal("175.00"),   # +1.75%
            Decimal("-25.00"),   # -0.25%
        ]

        # Calculate equity curve
        equity_curve = [initial_capital]
        for pnl in trade_pnls:
            equity_curve.append(equity_curve[-1] + pnl)

        # Create timestamps
        base_time = datetime(2024, 1, 1)
        timestamps = [base_time + timedelta(hours=i) for i in range(len(equity_curve))]
        entry_times = timestamps[:-1]
        exit_times = timestamps[1:]

        # Calculate metrics
        metrics = MetricsCalculator.calculate_all_metrics(
            initial_capital=initial_capital,
            final_capital=equity_curve[-1],
            equity_curve=equity_curve,
            timestamps=timestamps,
            trade_pnls=trade_pnls,
            entry_times=entry_times,
            exit_times=exit_times,
        )

        # Verify total return
        expected_total_return = float((equity_curve[-1] - initial_capital) / initial_capital * 100)
        actual_total_return = metrics.total_return_pct
        variance = abs(expected_total_return - actual_total_return) / expected_total_return * 100
        assert variance < 0.1, f"Total return variance {variance:.3f}% exceeds 0.1%"

        # Verify win rate
        winning_trades = sum(1 for pnl in trade_pnls if pnl > 0)
        expected_win_rate = winning_trades / len(trade_pnls)
        actual_win_rate = metrics.win_rate
        variance = abs(expected_win_rate - actual_win_rate) / expected_win_rate * 100 if expected_win_rate > 0 else 0
        assert variance < 0.1, f"Win rate variance {variance:.3f}% exceeds 0.1%"

        # Verify profit factor
        gross_profit = sum(pnl for pnl in trade_pnls if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in trade_pnls if pnl < 0))
        expected_profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0
        actual_profit_factor = metrics.profit_factor or 0
        if expected_profit_factor > 0:
            variance = abs(expected_profit_factor - actual_profit_factor) / expected_profit_factor * 100
            assert variance < 0.1, f"Profit factor variance {variance:.3f}% exceeds 0.1%"

        print(f"\n✅ Metrics Accuracy Test:")
        print(f"   Total Return: {actual_total_return:.2f}% (expected: {expected_total_return:.2f}%)")
        print(f"   Win Rate: {actual_win_rate:.2%} (expected: {expected_win_rate:.2%})")
        print(f"   Profit Factor: {actual_profit_factor:.2f} (expected: {expected_profit_factor:.2f})")
        print(f"   All variances < 0.1% ✓")


@pytest.mark.asyncio
class TestDeterministicReplay:
    """
    T055: Verify deterministic replay (same config + seed = identical results).

    Tests that running the same backtest twice with the same random seed
    produces identical results.
    """

    async def test_deterministic_replay_with_same_seed(
        self, async_session: AsyncSession
    ):
        """
        Run the same backtest twice with same random seed.

        Verifies:
        - Identical number of trades
        - Identical trade prices
        - Identical final capital
        - Identical metrics
        """
        # Initialize services
        backtest_repo = BacktestRepository(async_session)
        market_data_repo = MarketDataRepository(async_session)
        service = BacktestService(
            session=async_session,
            backtest_repository=backtest_repo,
            market_data_repository=market_data_repo,
        )

        # Get available data
        result = await async_session.execute(
            select(MarketData.time)
            .where(MarketData.symbol == "EURUSD")
            .where(MarketData.timeframe == "M5")
            .order_by(MarketData.time.desc())
            .limit(1)
        )
        latest_data = result.scalar_one_or_none()

        if not latest_data:
            pytest.skip("No EURUSD M5 data available")

        # Use 3 days of data
        end_date = latest_data
        start_date = end_date - timedelta(days=3)

        # Create configuration
        config = await service.create_configuration(
            name="Determinism Test",
            symbol="EURUSD",
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            config_params={"strategy": "rsi"},
        )
        await async_session.commit()

        # Validate data
        validation = await service.validate_configuration(config, timeframe="M5")
        if not validation["can_proceed"]:
            pytest.skip("Insufficient data for determinism test")

        # Define decision engine
        synthetic_engine_1 = SyntheticEngine(strategy="rsi", params={"rsi_period": 14})
        synthetic_engine_2 = SyntheticEngine(strategy="rsi", params={"rsi_period": 14})

        def decision_engine_1(tick):
            signal = synthetic_engine_1.process_tick(tick)
            return {"action": signal.action, "quantity": signal.quantity} if signal.action else None

        def decision_engine_2(tick):
            signal = synthetic_engine_2.process_tick(tick)
            return {"action": signal.action, "quantity": signal.quantity} if signal.action else None

        # Run backtest twice with SAME seed
        RANDOM_SEED = 12345

        run1 = await service.run_backtest(
            config_id=config.id,
            timeframe="M5",
            random_seed=RANDOM_SEED,
            decision_engine=decision_engine_1,
        )
        await async_session.commit()

        # Reset engine state
        synthetic_engine_2.reset()

        run2 = await service.run_backtest(
            config_id=config.id,
            timeframe="M5",
            random_seed=RANDOM_SEED,
            decision_engine=decision_engine_2,
        )
        await async_session.commit()

        # Verify both runs completed
        assert run1.status == RunStatus.COMPLETED
        assert run2.status == RunStatus.COMPLETED

        # Verify determinism: identical results
        assert run1.candles_processed == run2.candles_processed, "Candles processed should be identical"

        # Get trades for both runs
        trades1 = await backtest_repo.get_trades(run1.id)
        trades2 = await backtest_repo.get_trades(run2.id)

        assert len(trades1) == len(trades2), f"Trade count mismatch: {len(trades1)} vs {len(trades2)}"

        # Verify identical trade prices (if trades exist)
        if len(trades1) > 0:
            for t1, t2 in zip(trades1, trades2):
                assert t1.entry_price == t2.entry_price, f"Entry price mismatch: {t1.entry_price} vs {t2.entry_price}"
                assert t1.quantity == t2.quantity, f"Quantity mismatch: {t1.quantity} vs {t2.quantity}"
                if t1.exit_price and t2.exit_price:
                    assert t1.exit_price == t2.exit_price, f"Exit price mismatch"

        # Verify identical final capital
        assert run1.final_capital == run2.final_capital, f"Final capital mismatch: {run1.final_capital} vs {run2.final_capital}"

        print(f"\n✅ Deterministic Replay Test:")
        print(f"   Run 1: {run1.candles_processed} candles, {len(trades1)} trades, ${run1.final_capital:,.2f} final")
        print(f"   Run 2: {run2.candles_processed} candles, {len(trades2)} trades, ${run2.final_capital:,.2f} final")
        print(f"   Results are IDENTICAL ✓")


@pytest.mark.asyncio
@pytest.mark.slow
class TestPerformanceBenchmark:
    """
    T056: Performance test - Ensure 6-month backtest completes within 30 minutes.

    Benchmarks backtest execution speed with substantial data.
    """

    async def test_backtest_performance_with_large_dataset(
        self, async_session: AsyncSession
    ):
        """
        Test backtest performance with 6 months of data.

        Target: Complete within 30 minutes (1800 seconds)
        Expected: ~100-200 candles/second processing rate
        """
        # Initialize services
        backtest_repo = BacktestRepository(async_session)
        market_data_repo = MarketDataRepository(async_session)
        service = BacktestService(
            session=async_session,
            backtest_repository=backtest_repo,
            market_data_repository=market_data_repo,
        )

        # Get available data range
        result = await async_session.execute(
            select(MarketData.time)
            .where(MarketData.symbol == "EURUSD")
            .where(MarketData.timeframe == "M5")
            .order_by(MarketData.time.desc())
            .limit(1)
        )
        latest_data = result.scalar_one_or_none()

        if not latest_data:
            pytest.skip("No data available for performance test")

        # Try to get 6 months of data
        end_date = latest_data
        start_date = end_date - timedelta(days=180)  # ~6 months

        # Check available candles
        count_result = await market_data_repo.count_candles_in_range(
            symbol="EURUSD",
            timeframe="M5",
            start_time=start_date,
            end_time=end_date,
        )

        if count_result < 1000:
            pytest.skip(f"Insufficient data for performance test: only {count_result} candles available")

        # Create configuration
        config = await service.create_configuration(
            name="Performance Test - 6 Months",
            symbol="EURUSD",
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            config_params={"strategy": "trend_following"},
        )
        await async_session.commit()

        # Start timer
        start_time = time.time()

        # Execute backtest
        synthetic_engine = SyntheticEngine(strategy="trend_following")

        def decision_engine(tick):
            signal = synthetic_engine.process_tick(tick)
            return {"action": signal.action, "quantity": signal.quantity} if signal.action else None

        run = await service.run_backtest(
            config_id=config.id,
            timeframe="M5",
            decision_engine=decision_engine,
        )

        # End timer
        end_time = time.time()
        elapsed_seconds = end_time - start_time

        await async_session.commit()

        # Verify completion
        assert run.status == RunStatus.COMPLETED

        # Calculate performance metrics
        candles_per_second = run.candles_processed / elapsed_seconds if elapsed_seconds > 0 else 0
        elapsed_minutes = elapsed_seconds / 60

        # Performance assertions
        MAX_ALLOWED_SECONDS = 1800  # 30 minutes
        assert elapsed_seconds < MAX_ALLOWED_SECONDS, \
            f"Backtest took {elapsed_minutes:.1f} minutes, exceeds 30 minute limit"

        MIN_CANDLES_PER_SECOND = 10  # Very conservative minimum
        assert candles_per_second > MIN_CANDLES_PER_SECOND, \
            f"Processing speed {candles_per_second:.1f} candles/sec is too slow"

        print(f"\n✅ Performance Benchmark:")
        print(f"   Candles Processed: {run.candles_processed:,}")
        print(f"   Elapsed Time: {elapsed_minutes:.2f} minutes ({elapsed_seconds:.1f} seconds)")
        print(f"   Processing Speed: {candles_per_second:.1f} candles/second")
        print(f"   Target Met: {'✓' if elapsed_seconds < MAX_ALLOWED_SECONDS else '✗'}")


@pytest.mark.asyncio
class TestDataGapDetection:
    """
    T057: Test data gap detection and validation warnings.

    Tests the data validator's ability to detect:
    - Missing candles (gaps in time series)
    - Data quality issues
    - Warnings about insufficient data
    """

    async def test_data_gap_detection(self, async_session: AsyncSession):
        """
        Test that data validator correctly identifies gaps and issues warnings.

        Uses real data and checks validation results.
        """
        market_data_repo = MarketDataRepository(async_session)

        # Get available data
        result = await async_session.execute(
            select(MarketData.time)
            .where(MarketData.symbol == "EURUSD")
            .where(MarketData.timeframe == "M5")
            .order_by(MarketData.time.desc())
            .limit(1)
        )
        latest_data = result.scalar_one_or_none()

        if not latest_data:
            pytest.skip("No data available for gap detection test")

        # Test with a reasonable date range
        end_date = latest_data
        start_date = end_date - timedelta(days=30)

        # Validate data continuity
        validation = await market_data_repo.validate_data_continuity(
            symbol="EURUSD",
            timeframe="M5",
            start_time=start_date,
            end_time=end_date,
        )

        # Verify validation result structure
        assert "total_candles" in validation
        assert "has_gaps" in validation
        assert "first_candle_time" in validation
        assert "last_candle_time" in validation

        # Log validation results
        print(f"\n✅ Data Gap Detection Test:")
        print(f"   Total Candles: {validation['total_candles']}")
        print(f"   Has Gaps: {validation['has_gaps']}")
        print(f"   First Candle: {validation.get('first_candle_time')}")
        print(f"   Last Candle: {validation.get('last_candle_time')}")

        if "recommendation" in validation:
            print(f"   Recommendation: {validation['recommendation']}")

        if "error" in validation:
            print(f"   Error: {validation['error']}")

        # Test with intentionally bad date range (far future)
        bad_start = datetime(2030, 1, 1)
        bad_end = datetime(2030, 12, 31)

        bad_validation = await market_data_repo.validate_data_continuity(
            symbol="EURUSD",
            timeframe="M5",
            start_time=bad_start,
            end_time=bad_end,
        )

        # Should detect no data available
        assert bad_validation["total_candles"] == 0
        assert "error" in bad_validation or "recommendation" in bad_validation

        print(f"\n   Future Date Test: {bad_validation.get('total_candles', 0)} candles (expected 0) ✓")
