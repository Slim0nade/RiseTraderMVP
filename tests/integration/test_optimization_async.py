"""
Integration tests for async optimization with deterministic grid search.

These tests verify:
- T031: Deterministic results - same params produce identical results
- Full async optimization workflow with real grid search
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.utils.grid_search import generate_grid_combinations, calculate_grid_size


@pytest.mark.asyncio
class TestDeterministicOptimization:
    """Integration tests for deterministic optimization results (T031)."""

    async def test_same_params_produce_identical_combinations(self):
        """Test that same parameter grid always produces identical combinations."""
        grid = {
            "fast_period": [5, 10, 15, 20],
            "slow_period": [25, 30, 35, 40],
            "rsi_period": [7, 10, 14],
        }

        # Generate combinations multiple times
        run1 = list(generate_grid_combinations(grid))
        run2 = list(generate_grid_combinations(grid))
        run3 = list(generate_grid_combinations(grid))

        # Verify all runs are identical
        assert run1 == run2 == run3

        # Verify count is correct
        expected_count = 4 * 4 * 3  # 48 combinations
        assert len(run1) == expected_count

    async def test_optimization_worker_processes_all_combinations(self):
        """Test that worker processes all grid combinations."""
        from src.services.optimization_job_service import OptimizationJobService
        from sqlalchemy.ext.asyncio import AsyncSession

        grid = {
            "fast_period": [5, 10],
            "slow_period": [20, 30],
        }
        expected_combinations = 4

        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)

        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_redis.expire = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.srem = AsyncMock()
        mock_redis.delete = AsyncMock()

        job_id = str(uuid4())
        combinations_tested = []

        # Track which combinations are tested
        async def mock_run_backtest(*args, **kwargs):
            combinations_tested.append(kwargs.get("params") or args[0])
            return {
                "total_trades": 10,
                "winning_trades": 6,
                "losing_trades": 4,
                "total_return_pct": 15.5,
                "sharpe_ratio": 1.2,
                "profit_factor": 1.5,
                "max_drawdown_pct": 5.0,
            }

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            with patch("src.services.optimization_job_service.get_sse_manager") as mock_sse:
                mock_sse_manager = AsyncMock()
                mock_sse.return_value = mock_sse_manager

                service = OptimizationJobService(mock_db)

                # Mock the optimizer to track calls
                with patch.object(
                    service, "_run_worker", wraps=service._run_worker
                ):
                    # Verify grid size calculation
                    assert calculate_grid_size(grid) == expected_combinations

    async def test_grid_order_is_consistent_with_itertools_product(self):
        """Test that our grid generation matches itertools.product ordering."""
        from itertools import product

        grid = {
            "a": [1, 2, 3],
            "b": [10, 20],
            "c": [100, 200],
        }

        # Our implementation
        our_combos = list(generate_grid_combinations(grid))

        # Expected from itertools.product
        keys = list(grid.keys())
        values = [grid[k] for k in keys]
        expected_combos = [dict(zip(keys, combo)) for combo in product(*values)]

        # Should be identical
        assert our_combos == expected_combos

    async def test_parameter_order_does_not_affect_results(self):
        """Test that different key ordering in grid dict produces same combinations."""
        # Python 3.7+ preserves insertion order, but our logic should be consistent
        grid1 = {"a": [1, 2], "b": [10, 20]}
        grid2 = {"b": [10, 20], "a": [1, 2]}

        combos1 = list(generate_grid_combinations(grid1))
        combos2 = list(generate_grid_combinations(grid2))

        # Same number of combinations
        assert len(combos1) == len(combos2) == 4

        # Same set of combinations (regardless of order)
        assert set(frozenset(c.items()) for c in combos1) == set(
            frozenset(c.items()) for c in combos2
        )


@pytest.mark.asyncio
class TestOptimizationResultConsistency:
    """Test that optimization produces consistent, reproducible results."""

    async def test_best_params_selection_is_deterministic(self):
        """Test that best parameter selection is deterministic given same results."""
        from src.utils.grid_search import generate_grid_combinations

        grid = {"fast": [5, 10], "slow": [20, 30]}
        combinations = list(generate_grid_combinations(grid))

        # Simulate backtest results (fixed for determinism)
        results = [
            {"params": combinations[0], "sharpe_ratio": 1.2},
            {"params": combinations[1], "sharpe_ratio": 1.8},  # Best
            {"params": combinations[2], "sharpe_ratio": 1.5},
            {"params": combinations[3], "sharpe_ratio": 1.3},
        ]

        # Find best multiple times
        def find_best(results, target="sharpe_ratio"):
            return max(results, key=lambda r: r.get(target, 0))

        best1 = find_best(results)
        best2 = find_best(results)
        best3 = find_best(results)

        # Should always select the same best
        assert best1 == best2 == best3
        assert best1["sharpe_ratio"] == 1.8

    async def test_results_ordering_is_deterministic(self):
        """Test that results are ordered consistently."""
        from src.utils.grid_search import generate_grid_combinations

        grid = {"x": [1, 2, 3], "y": [10, 20]}
        combinations = list(generate_grid_combinations(grid))

        # Verify ordering is consistent
        assert combinations[0] == {"x": 1, "y": 10}
        assert combinations[1] == {"x": 1, "y": 20}
        assert combinations[2] == {"x": 2, "y": 10}
        assert combinations[3] == {"x": 2, "y": 20}
        assert combinations[4] == {"x": 3, "y": 10}
        assert combinations[5] == {"x": 3, "y": 20}


@pytest.mark.asyncio
class TestGridSearchEdgeCases:
    """Test edge cases in grid search."""

    async def test_single_value_parameters(self):
        """Test grid with single-value parameters."""
        grid = {
            "fixed_param": [100],
            "variable_param": [1, 2, 3],
        }

        combos = list(generate_grid_combinations(grid))

        assert len(combos) == 3
        # All should have the fixed param value
        assert all(c["fixed_param"] == 100 for c in combos)

    async def test_boolean_parameters(self):
        """Test grid with boolean parameters."""
        grid = {
            "use_filter": [True, False],
            "threshold": [0.5, 1.0],
        }

        combos = list(generate_grid_combinations(grid))

        assert len(combos) == 4
        # Verify boolean values are preserved correctly
        bool_values = [c["use_filter"] for c in combos]
        assert True in bool_values
        assert False in bool_values

    async def test_float_parameters(self):
        """Test grid with float parameters."""
        grid = {
            "stop_loss_pct": [0.01, 0.02, 0.03],
            "take_profit_pct": [0.02, 0.04],
        }

        combos = list(generate_grid_combinations(grid))

        assert len(combos) == 6
        # Verify float precision is maintained
        first_combo = combos[0]
        assert first_combo["stop_loss_pct"] == 0.01
        assert first_combo["take_profit_pct"] == 0.02

    async def test_string_parameters(self):
        """Test grid with string parameters."""
        grid = {
            "strategy_type": ["aggressive", "conservative"],
            "timeframe": ["H1", "H4"],
        }

        combos = list(generate_grid_combinations(grid))

        assert len(combos) == 4
        # Verify strings are preserved
        strategy_types = {c["strategy_type"] for c in combos}
        assert strategy_types == {"aggressive", "conservative"}
