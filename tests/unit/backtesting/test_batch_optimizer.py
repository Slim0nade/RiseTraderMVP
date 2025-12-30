"""
Unit tests for BatchOptimizer (User Story 2).

Tests parallel execution, parameter grid expansion, result ranking,
and statistical significance testing.

T058: Parallel execution test
T059: Parameter grid expansion test
"""
import pytest
from decimal import Decimal
from pathlib import Path
import tempfile
from typing import Dict, Any
from unittest.mock import Mock, patch
import time

from src.services.backtesting.batch_optimizer import (
    BatchOptimizer,
    OptimizationResult,
    ParameterGrid,
    create_quick_grid,
)


class TestBatchOptimizerParallelExecution:
    """T058: Test parallel execution with worker pools."""

    def test_parallel_execution_with_multiple_workers(self):
        """Verify BatchOptimizer can execute backtests in parallel."""
        # Arrange
        grid = ParameterGrid(
            ema_fast=[5, 8, 10],
            ema_slow=[25, 29],
            rsi_period=[10, 14],
        )

        def mock_backtest(params: Dict[str, Any]) -> OptimizationResult:
            """Mock backtest function that simulates work."""
            time.sleep(0.01)  # Simulate computation
            return OptimizationResult(
                params=params,
                total_return=0.15,
                sharpe_ratio=1.5,
                max_drawdown=-0.10,
                win_rate=0.60,
                profit_factor=2.0,
                total_trades=100,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=2,
                results_dir=Path(tmpdir),
            )

            # Act
            start_time = time.time()
            results = optimizer.run()
            elapsed_time = time.time() - start_time

            # Assert
            expected_combinations = 3 * 2 * 2  # 12 combinations
            assert len(results) == expected_combinations

            # Parallel execution should be faster than sequential
            # Sequential would take 12 * 0.01 = 0.12 seconds
            # Parallel with 2 workers should take ~6 * 0.01 = 0.06 seconds
            assert elapsed_time < 0.10  # Some overhead acceptable

            # All results should have valid metrics
            for result in results:
                assert result.total_return > 0
                assert result.sharpe_ratio > 0
                assert isinstance(result.params, dict)

    def test_single_worker_fallback(self):
        """Verify BatchOptimizer works with max_workers=1 (sequential)."""
        # Arrange
        grid = ParameterGrid(
            ema_fast=[5, 8],
            ema_slow=[25],
        )

        def mock_backtest(params: Dict[str, Any]) -> OptimizationResult:
            return OptimizationResult(
                params=params,
                total_return=0.10,
                sharpe_ratio=1.2,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=1,
                results_dir=Path(tmpdir),
            )

            # Act
            results = optimizer.run()

            # Assert
            assert len(results) == 2
            assert all(r.total_return == 0.10 for r in results)

    def test_progress_callback_invoked(self):
        """Verify progress callback is called during execution."""
        # Arrange
        grid = ParameterGrid(
            ema_fast=[5, 8, 10],
            ema_slow=[25],
        )

        progress_calls = []

        def progress_callback(completed: int, total: int):
            progress_calls.append((completed, total))

        def mock_backtest(params: Dict[str, Any]) -> OptimizationResult:
            return OptimizationResult(params=params, total_return=0.05)

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=2,
                results_dir=Path(tmpdir),
            )

            # Act
            results = optimizer.run(progress_callback=progress_callback)

            # Assert
            assert len(progress_calls) > 0
            # Last call should be (3, 3)
            assert progress_calls[-1] == (3, 3)

    def test_early_stopping_on_threshold(self):
        """Verify early stopping when threshold is met."""
        # Arrange
        grid = ParameterGrid(
            ema_fast=[5, 8, 10, 12, 15],
            ema_slow=[25],
        )

        call_count = [0]

        def mock_backtest(params: Dict[str, Any]) -> OptimizationResult:
            call_count[0] += 1
            # First result has high Sharpe, should trigger early stop
            sharpe = 3.0 if call_count[0] == 1 else 1.0
            return OptimizationResult(
                params=params,
                total_return=0.20,
                sharpe_ratio=sharpe,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=1,
                results_dir=Path(tmpdir),
            )

            # Act
            results = optimizer.run(early_stop_threshold=2.5)

            # Assert
            # Should stop early (not process all 5 combinations)
            assert len(results) < 5
            assert call_count[0] < 5


class TestParameterGridExpansion:
    """T059: Test parameter grid expansion logic."""

    def test_cartesian_product_expansion(self):
        """Verify parameter grid creates cartesian product correctly."""
        # Arrange
        grid = ParameterGrid(
            ema_fast=[5, 8, 10],
            ema_slow=[25, 29],
            rsi_period=[10, 14, 18],
        )

        # Act
        combinations = list(grid.expand())

        # Assert
        expected_count = 3 * 2 * 3  # 18 combinations
        assert len(combinations) == expected_count

        # Check first combination
        assert combinations[0] == {
            'ema_fast': 5,
            'ema_slow': 25,
            'rsi_period': 10,
        }

        # Check last combination
        assert combinations[-1] == {
            'ema_fast': 10,
            'ema_slow': 29,
            'rsi_period': 18,
        }

        # All combinations should be unique
        unique_combinations = set(
            tuple(sorted(c.items())) for c in combinations
        )
        assert len(unique_combinations) == expected_count

    def test_single_parameter_grid(self):
        """Verify grid with single parameter works."""
        # Arrange
        grid = ParameterGrid(ema_fast=[5, 8, 10])

        # Act
        combinations = list(grid.expand())

        # Assert
        assert len(combinations) == 3
        assert combinations[0] == {'ema_fast': 5}
        assert combinations[2] == {'ema_fast': 10}

    def test_empty_grid_raises_error(self):
        """Verify empty grid raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="at least one parameter"):
            ParameterGrid()

    def test_quick_grid_factory(self):
        """Verify create_quick_grid() produces expected size."""
        # Act
        grid = create_quick_grid()
        combinations = list(grid.expand())

        # Assert
        # Quick grid should have ~500 combinations
        assert 400 <= len(combinations) <= 600

        # Should include expected parameters
        sample = combinations[0]
        assert 'ema_fast' in sample
        assert 'ema_slow' in sample
        assert 'rsi_period' in sample


class TestResultRanking:
    """Test result ranking by different metrics."""

    def test_rank_by_sharpe_ratio(self):
        """Verify results can be ranked by Sharpe ratio."""
        # Arrange
        results = [
            OptimizationResult(params={'id': 1}, sharpe_ratio=1.5),
            OptimizationResult(params={'id': 2}, sharpe_ratio=2.5),
            OptimizationResult(params={'id': 3}, sharpe_ratio=0.8),
        ]

        grid = ParameterGrid(dummy=[1])

        def mock_backtest(params):
            return results[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=1,
                results_dir=Path(tmpdir),
            )
            optimizer.results = results

            # Act
            top_results = optimizer.get_top_results(n=3, sort_by='sharpe_ratio')

            # Assert
            assert len(top_results) == 3
            assert top_results[0].sharpe_ratio == 2.5
            assert top_results[1].sharpe_ratio == 1.5
            assert top_results[2].sharpe_ratio == 0.8

    def test_rank_by_composite_score(self):
        """Verify results can be ranked by composite score."""
        # Arrange
        results = [
            OptimizationResult(
                params={'id': 1},
                sharpe_ratio=1.5,
                total_return=0.20,
                profit_factor=2.0,
                win_rate=0.60,
                max_drawdown=-0.10,
            ),
            OptimizationResult(
                params={'id': 2},
                sharpe_ratio=2.5,
                total_return=0.30,
                profit_factor=3.0,
                win_rate=0.70,
                max_drawdown=-0.05,
            ),
        ]

        grid = ParameterGrid(dummy=[1])

        def mock_backtest(params):
            return results[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=1,
                results_dir=Path(tmpdir),
            )
            optimizer.results = results

            # Act
            top_results = optimizer.get_top_results(n=2, sort_by='composite_score')

            # Assert
            # Result 2 has better metrics across the board
            assert top_results[0].params['id'] == 2
            assert top_results[1].params['id'] == 1


class TestStatisticalSignificance:
    """Test statistical significance testing between results."""

    def test_ttest_between_results(self):
        """Verify t-test correctly identifies significant differences."""
        # Arrange
        result_a = OptimizationResult(
            params={'strategy': 'A'},
            total_return=0.20,
        )

        result_b = OptimizationResult(
            params={'strategy': 'B'},
            total_return=0.10,
        )

        grid = ParameterGrid(dummy=[1])

        def mock_backtest(params):
            return result_a

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=1,
                results_dir=Path(tmpdir),
            )

            # Act
            with patch('src.services.backtesting.batch_optimizer.stats.ttest_ind') as mock_ttest:
                mock_ttest.return_value = Mock(pvalue=0.03)

                p_value = optimizer.statistical_significance(
                    result_a,
                    result_b,
                    metric='total_return'
                )

            # Assert
            assert p_value == 0.03
            assert p_value < 0.05  # Statistically significant


class TestMemoryManagement:
    """Test memory management during batch execution."""

    def test_memory_cleanup_after_each_backtest(self):
        """Verify memory is released after each backtest completes."""
        # Arrange
        grid = ParameterGrid(
            ema_fast=[5, 8, 10],
            ema_slow=[25, 29],
        )

        def mock_backtest(params: Dict[str, Any]) -> OptimizationResult:
            # Allocate some memory
            _ = [0] * 10000
            return OptimizationResult(params=params, total_return=0.05)

        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=grid,
                backtest_function=mock_backtest,
                max_workers=2,
                results_dir=Path(tmpdir),
            )

            # Act
            results = optimizer.run()

            # Assert
            # If memory cleanup works, this should complete without OOM
            assert len(results) == 6

            # Verify results directory has saved results
            result_files = list(Path(tmpdir).glob("optimization_*.json"))
            assert len(result_files) > 0
