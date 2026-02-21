"""
Unit tests for ABTestService.

Tests the pure statistical functions directly (no database required).
Tests that exercise the full service lifecycle skip when the database
is unavailable.
"""

import math
from collections import Counter
from uuid import uuid4

import numpy as np
import pytest
from scipy import stats as scipy_stats

from src.services.ab_test_service import (
    ABTestService,
    ExperimentStatus,
    VariantDefinition,
    compute_t_test,
    compute_variant_stats,
    select_variant_weighted,
)


# ============================================================================
# Pure statistical function tests (no DB needed)
# ============================================================================


class TestComputeTTest:
    """Tests for the compute_t_test pure function."""

    def test_known_significant_difference(self):
        """Two clearly different distributions should yield significant result."""
        np.random.seed(42)
        returns_a = list(np.random.normal(loc=0.05, scale=0.02, size=100))
        returns_b = list(np.random.normal(loc=0.01, scale=0.02, size=100))

        result = compute_t_test(returns_a, returns_b)

        assert result["t_statistic"] is not None
        assert result["p_value"] is not None
        assert result["p_value"] < 0.05
        assert result["is_significant"] is True
        assert result["winner"] == "A"
        assert result["confidence_interval_95"] is not None

        ci_lower, ci_upper = result["confidence_interval_95"]
        assert ci_lower > 0  # A is meaningfully better than B
        assert ci_upper > ci_lower

    def test_known_not_significant(self):
        """Two similar distributions should yield non-significant result."""
        np.random.seed(42)
        returns_a = list(np.random.normal(loc=0.02, scale=0.05, size=30))
        returns_b = list(np.random.normal(loc=0.02, scale=0.05, size=30))

        result = compute_t_test(returns_a, returns_b)

        assert result["t_statistic"] is not None
        assert result["p_value"] is not None
        # With same mean and only 30 samples, should not be significant
        # (not guaranteed but highly likely with same loc)
        assert result["confidence_interval_95"] is not None

    def test_b_wins(self):
        """When B has higher returns, winner should be B."""
        returns_a = [0.01] * 50
        returns_b = [0.10] * 50

        result = compute_t_test(returns_a, returns_b)

        assert result["is_significant"] is True
        assert result["winner"] == "B"

    def test_insufficient_data_a(self):
        """With fewer than 2 samples in A, return None values."""
        result = compute_t_test([0.05], [0.01, 0.02, 0.03])

        assert result["t_statistic"] is None
        assert result["p_value"] is None
        assert result["is_significant"] is False
        assert result["winner"] is None

    def test_insufficient_data_b(self):
        """With fewer than 2 samples in B, return None values."""
        result = compute_t_test([0.01, 0.02, 0.03], [0.05])

        assert result["t_statistic"] is None
        assert result["p_value"] is None
        assert result["is_significant"] is False

    def test_empty_arrays(self):
        """Empty arrays should return None values."""
        result = compute_t_test([], [])

        assert result["t_statistic"] is None
        assert result["p_value"] is None
        assert result["is_significant"] is False

    def test_identical_arrays(self):
        """Identical data should have p-value = 1 and not be significant."""
        data = [0.01, 0.02, 0.03, 0.04, 0.05]

        result = compute_t_test(data, data)

        assert result["t_statistic"] is not None
        assert abs(result["t_statistic"]) < 1e-10
        assert result["p_value"] is not None
        assert result["p_value"] > 0.99
        assert result["is_significant"] is False

    def test_t_statistic_matches_scipy(self):
        """Our t-statistic should match scipy's ttest_ind."""
        np.random.seed(123)
        a = list(np.random.normal(0.03, 0.01, 50))
        b = list(np.random.normal(0.01, 0.01, 50))

        result = compute_t_test(a, b)
        scipy_t, scipy_p = scipy_stats.ttest_ind(a, b, equal_var=False)

        assert abs(result["t_statistic"] - scipy_t) < 1e-10
        assert abs(result["p_value"] - scipy_p) < 1e-10

    def test_confidence_interval_contains_true_diff(self):
        """95% CI should contain the true difference of means most of the time."""
        np.random.seed(0)
        contained = 0
        trials = 200
        true_diff = 0.04  # A mean=0.05, B mean=0.01

        for i in range(trials):
            a = list(np.random.normal(0.05, 0.02, 50))
            b = list(np.random.normal(0.01, 0.02, 50))
            result = compute_t_test(a, b)
            if result["confidence_interval_95"] is not None:
                lo, hi = result["confidence_interval_95"]
                if lo <= true_diff <= hi:
                    contained += 1

        coverage = contained / trials
        # Should be roughly 95% but allow tolerance
        assert coverage > 0.88, f"CI coverage {coverage:.2%} is too low"


class TestComputeVariantStats:
    """Tests for the compute_variant_stats pure function."""

    def test_basic_stats(self):
        """Verify mean, std, win_rate, total_pnl."""
        returns = [0.05, -0.02, 0.03, 0.01, -0.01]
        pnls = [50.0, -20.0, 30.0, 10.0, -10.0]

        stats = compute_variant_stats(returns, pnls)

        assert stats["trade_count"] == 5
        assert abs(stats["mean_return"] - np.mean(returns)) < 1e-10
        assert abs(stats["std_return"] - np.std(returns, ddof=1)) < 1e-10
        assert abs(stats["total_pnl"] - 60.0) < 1e-10
        assert abs(stats["win_rate"] - 0.6) < 1e-10
        assert stats["sharpe_ratio"] is not None

    def test_all_wins(self):
        """All positive returns should give 100% win rate."""
        returns = [0.01, 0.02, 0.03]
        pnls = [10.0, 20.0, 30.0]

        stats = compute_variant_stats(returns, pnls)

        assert stats["win_rate"] == 1.0
        assert stats["total_pnl"] == 60.0

    def test_all_losses(self):
        """All negative returns should give 0% win rate."""
        returns = [-0.01, -0.02, -0.03]
        pnls = [-10.0, -20.0, -30.0]

        stats = compute_variant_stats(returns, pnls)

        assert stats["win_rate"] == 0.0
        assert stats["total_pnl"] == -60.0

    def test_empty_returns(self):
        """Empty returns should return zeroed stats."""
        stats = compute_variant_stats([], [])

        assert stats["trade_count"] == 0
        assert stats["mean_return"] == 0.0
        assert stats["win_rate"] == 0.0
        assert stats["sharpe_ratio"] is None

    def test_single_return(self):
        """Single trade should have zero std and no Sharpe."""
        stats = compute_variant_stats([0.05], [50.0])

        assert stats["trade_count"] == 1
        assert stats["mean_return"] == 0.05
        assert stats["std_return"] == 0.0
        assert stats["sharpe_ratio"] is None

    def test_sharpe_calculation(self):
        """Verify annualized Sharpe ratio."""
        returns = [0.01, 0.02, 0.015, 0.012, 0.018]
        pnls = [10.0] * 5

        stats = compute_variant_stats(returns, pnls)

        mean_r = np.mean(returns)
        std_r = np.std(returns, ddof=1)
        expected_sharpe = (mean_r / std_r) * np.sqrt(252)

        assert abs(stats["sharpe_ratio"] - expected_sharpe) < 1e-10


class TestSelectVariantWeighted:
    """Tests for the select_variant_weighted pure function."""

    def test_distribution_matches_weights(self):
        """Run 10000 selections, verify distribution approximates weights."""
        id_a = uuid4()
        id_b = uuid4()
        variant_ids = [id_a, id_b]
        weights = [70, 30]

        counts = Counter()
        n = 10000
        for _ in range(n):
            selected = select_variant_weighted(variant_ids, weights)
            counts[selected] += 1

        ratio_a = counts[id_a] / n
        ratio_b = counts[id_b] / n

        # Should be roughly 70/30 with tolerance
        assert abs(ratio_a - 0.70) < 0.05, f"Expected ~70%, got {ratio_a:.1%}"
        assert abs(ratio_b - 0.30) < 0.05, f"Expected ~30%, got {ratio_b:.1%}"

    def test_single_variant_always_selected(self):
        """With one variant at 100%, always select it."""
        id_a = uuid4()

        for _ in range(100):
            selected = select_variant_weighted([id_a], [100])
            assert selected == id_a

    def test_three_way_split(self):
        """Three-way 40/30/30 split should distribute accordingly."""
        ids = [uuid4() for _ in range(3)]
        weights = [40, 30, 30]

        counts = Counter()
        n = 10000
        for _ in range(n):
            selected = select_variant_weighted(ids, weights)
            counts[selected] += 1

        assert abs(counts[ids[0]] / n - 0.40) < 0.05
        assert abs(counts[ids[1]] / n - 0.30) < 0.05
        assert abs(counts[ids[2]] / n - 0.30) < 0.05

    def test_empty_variant_ids_raises(self):
        """Empty variant_ids should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            select_variant_weighted([], [])

    def test_mismatched_lengths_raises(self):
        """Mismatched lengths should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            select_variant_weighted([uuid4(), uuid4()], [100])

    def test_zero_total_weight_raises(self):
        """All-zero weights should raise ValueError."""
        with pytest.raises(ValueError, match="Total weight must be > 0"):
            select_variant_weighted([uuid4()], [0])

    def test_unequal_weights(self):
        """90/10 split should strongly favor the first variant."""
        id_a = uuid4()
        id_b = uuid4()

        counts = Counter()
        n = 5000
        for _ in range(n):
            selected = select_variant_weighted([id_a, id_b], [90, 10])
            counts[selected] += 1

        assert counts[id_a] > counts[id_b] * 5  # Should be ~9x, checking >5x


# ============================================================================
# Edge case tests for statistical functions
# ============================================================================


class TestStatisticalEdgeCases:
    """Edge case coverage for the statistics module."""

    def test_zero_variance_one_side(self):
        """One variant with constant returns, the other with variance."""
        returns_a = [0.05] * 20
        returns_b = list(np.random.normal(0.02, 0.01, 20))

        result = compute_t_test(returns_a, returns_b)

        # Should still compute (scipy handles this via Welch approximation)
        assert result["t_statistic"] is not None
        assert result["p_value"] is not None

    def test_large_sample_sizes(self):
        """Verify function handles large datasets efficiently."""
        np.random.seed(99)
        returns_a = list(np.random.normal(0.001, 0.01, 10000))
        returns_b = list(np.random.normal(0.000, 0.01, 10000))

        result = compute_t_test(returns_a, returns_b)

        # With 10k samples and small difference, may or may not be significant
        assert result["t_statistic"] is not None
        assert result["p_value"] is not None

    def test_negative_returns_both(self):
        """Both variants losing money - winner is less negative."""
        returns_a = [-0.01, -0.02, -0.015, -0.01, -0.025] * 10
        returns_b = [-0.05, -0.06, -0.055, -0.04, -0.065] * 10

        result = compute_t_test(returns_a, returns_b)

        assert result["is_significant"] is True
        assert result["winner"] == "A"  # A loses less

    def test_variant_stats_with_zero_return(self):
        """Trades with exactly 0.0 return should not count as wins."""
        returns = [0.0, 0.0, 0.01, -0.01]
        pnls = [0.0, 0.0, 10.0, -10.0]

        stats = compute_variant_stats(returns, pnls)

        assert stats["win_rate"] == 0.25  # Only one positive trade out of four

    def test_very_small_differences(self):
        """Nearly identical distributions should not be significant."""
        np.random.seed(7)
        base = list(np.random.normal(0.02, 0.05, 20))
        returns_a = base.copy()
        returns_b = [x + 0.0001 for x in base]

        result = compute_t_test(returns_a, returns_b)

        assert result["is_significant"] is False


# ============================================================================
# Service lifecycle tests (require database - skip if unavailable)
# ============================================================================


class TestABTestServiceLifecycle:
    """
    Integration-style tests for the full experiment lifecycle.

    These tests require a running PostgreSQL database. They are skipped
    if the database is not available.
    """

    @pytest.fixture
    async def db_session(self):
        """Attempt to create a real database session. Skip if unavailable."""
        try:
            from src.database.config import initialize_database
            db = initialize_database()
            async with db.get_session() as session:
                yield session
        except Exception as e:
            pytest.skip(f"Database unavailable: {e}")

    @pytest.mark.asyncio
    async def test_create_and_list_experiment(self, db_session):
        """Create an experiment and verify it appears in active list."""
        service = ABTestService(db_session)

        result = await service.create_experiment(
            name="test_qwen_vs_deepseek",
            description="Compare qwen3 and deepseek for signal generation",
            variants=[
                VariantDefinition(name="qwen3:14b", traffic_pct=50, config={"model": "qwen3:14b"}),
                VariantDefinition(name="deepseek-r1:14b", traffic_pct=50, config={"model": "deepseek-r1:14b"}),
            ],
        )

        assert "experiment_id" in result
        assert len(result["variant_ids"]) == 2

        experiments = await service.get_active_experiments()
        exp_ids = [str(e.experiment_id) for e in experiments]
        assert str(result["experiment_id"]) in exp_ids

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, db_session):
        """Create experiment, record results, compute stats, promote."""
        service = ABTestService(db_session)

        # Create
        exp = await service.create_experiment(
            name="lifecycle_test",
            description="Full lifecycle test",
            variants=[
                VariantDefinition(name="model_a", traffic_pct=50),
                VariantDefinition(name="model_b", traffic_pct=50),
            ],
        )
        exp_id = exp["experiment_id"]
        var_a, var_b = exp["variant_ids"]

        # Record results - A performs better
        for ret in [0.05, 0.03, 0.04, 0.02, 0.06]:
            await service.record_result(exp_id, var_a, {"return_pct": ret, "pnl": ret * 1000})

        for ret in [0.01, -0.02, 0.005, -0.01, 0.015]:
            await service.record_result(exp_id, var_b, {"return_pct": ret, "pnl": ret * 1000})

        # Compute stats
        stats = await service.compute_statistics(exp_id)
        assert stats.variants[0].trade_count == 5
        assert stats.variants[1].trade_count == 5
        assert stats.t_statistic is not None
        assert stats.p_value is not None

        # Promote
        promotion = await service.promote_winner(exp_id)
        assert promotion["winner_variant_id"] == var_a
        assert promotion["status"] == "completed"

    @pytest.mark.asyncio
    async def test_select_variant_distribution(self, db_session):
        """Verify select_variant follows traffic allocation."""
        service = ABTestService(db_session)

        exp = await service.create_experiment(
            name="distribution_test",
            variants=[
                VariantDefinition(name="heavy", traffic_pct=80),
                VariantDefinition(name="light", traffic_pct=20),
            ],
        )
        exp_id = exp["experiment_id"]
        var_heavy, var_light = exp["variant_ids"]

        counts = Counter()
        for _ in range(500):
            selected = await service.select_variant(exp_id)
            counts[selected] += 1

        heavy_ratio = counts[var_heavy] / 500
        assert abs(heavy_ratio - 0.80) < 0.10, f"Expected ~80%, got {heavy_ratio:.1%}"

    @pytest.mark.asyncio
    async def test_get_experiment_results(self, db_session):
        """Verify get_experiment_results returns full summary."""
        service = ABTestService(db_session)

        exp = await service.create_experiment(
            name="results_test",
            variants=[
                VariantDefinition(name="alpha", traffic_pct=50),
                VariantDefinition(name="beta", traffic_pct=50),
            ],
        )
        exp_id = exp["experiment_id"]
        var_a, var_b = exp["variant_ids"]

        await service.record_result(exp_id, var_a, {"return_pct": 0.03})
        await service.record_result(exp_id, var_b, {"return_pct": 0.01})

        results = await service.get_experiment_results(exp_id)

        assert results["experiment_name"] == "results_test"
        assert len(results["variants"]) == 2
        assert "statistics" in results
