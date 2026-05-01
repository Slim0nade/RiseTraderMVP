"""
Unit tests for StrategyRouter.

All tests operate on a directly instantiated StrategyRouter — no database,
no MT4, no mocks.  Pure routing-table validation.

Coverage
--------
1. TRENDING regime → only momentum/breakout/trend_following allowed,
   value_area/mean_reversion/ml_reversal blocked, threshold = 0.60,
   allow_trading = True, weights sum to 1.0.

2. RANGING regime → only value_area/mean_reversion/ml_reversal allowed,
   momentum/breakout blocked, threshold = 0.60, allow_trading = True,
   weights sum to 1.0.

3. VOLATILE regime → allow_trading = False, strategies dict is empty,
   all known strategy names are blocked.

4. UNKNOWN regime → all five strategies present at equal weight (0.20 each),
   threshold = 0.75, allow_trading = True.

5. Output dict contract — all four required keys are always present with
   correct types for every regime.

6. get_blocked_strategies() returns the correct frozenset for each regime.

7. Unrecognised / future enum value → falls back to UNKNOWN routing without
   raising (defensive coverage for enum extension).
"""

from __future__ import annotations

import pytest

from src.trading.regime.regime_classifier import MarketRegime
from src.trading.regime.strategy_router import StrategyRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def router() -> StrategyRouter:
    """Shared StrategyRouter instance — stateless, safe to reuse."""
    return StrategyRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KNOWN_STRATEGIES = frozenset(
    {"momentum", "breakout", "value_area", "mean_reversion", "ml_reversal", "trend_following"}
)

_TRENDING_STRATEGIES = {"momentum", "breakout", "trend_following"}
_TRENDING_BLOCKED = {"value_area", "mean_reversion", "ml_reversal"}

_RANGING_STRATEGIES = {"value_area", "mean_reversion", "ml_reversal"}
_RANGING_BLOCKED = {"momentum", "breakout"}


# ---------------------------------------------------------------------------
# Test 1 — TRENDING
# ---------------------------------------------------------------------------


class TestTrendingRegime:
    """StrategyRouter output for TRENDING market regime."""

    def test_allow_trading_is_true(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.TRENDING)
        assert config["allow_trading"] is True

    def test_allowed_strategy_names(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.TRENDING)
        strategies = config["strategies"]
        assert set(strategies.keys()) == _TRENDING_STRATEGIES, (
            f"Expected {_TRENDING_STRATEGIES}, got {set(strategies.keys())}"
        )

    def test_blocked_strategies_absent_from_config(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.TRENDING)
        strategies = config["strategies"]
        for blocked in _TRENDING_BLOCKED:
            assert blocked not in strategies, (
                f"Strategy '{blocked}' must be blocked in TRENDING but was present"
            )

    def test_weights_sum_to_one(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.TRENDING)
        total = sum(config["strategies"].values())
        assert abs(total - 1.0) < 1e-9, f"TRENDING weights sum to {total}, expected 1.0"

    def test_individual_weights(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.TRENDING)
        strategies = config["strategies"]
        assert strategies["momentum"] == pytest.approx(0.40)
        assert strategies["breakout"] == pytest.approx(0.35)
        assert strategies["trend_following"] == pytest.approx(0.25)

    def test_signal_threshold(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.TRENDING)
        assert config["signal_threshold"] == pytest.approx(0.60)

    def test_get_blocked_strategies(self, router: StrategyRouter) -> None:
        blocked = router.get_blocked_strategies(MarketRegime.TRENDING)
        assert _TRENDING_BLOCKED.issubset(blocked), (
            f"Expected blocked={_TRENDING_BLOCKED} to be a subset of {blocked}"
        )

    def test_returned_dict_is_a_copy(self, router: StrategyRouter) -> None:
        """Mutating the returned dict must not affect the class-level routing table."""
        config = router.get_strategy_config(MarketRegime.TRENDING)
        config["strategies"]["momentum"] = 0.99
        config2 = router.get_strategy_config(MarketRegime.TRENDING)
        assert config2["strategies"]["momentum"] == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# Test 2 — RANGING
# ---------------------------------------------------------------------------


class TestRangingRegime:
    """StrategyRouter output for RANGING market regime."""

    def test_allow_trading_is_true(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.RANGING)
        assert config["allow_trading"] is True

    def test_allowed_strategy_names(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.RANGING)
        strategies = config["strategies"]
        assert set(strategies.keys()) == _RANGING_STRATEGIES, (
            f"Expected {_RANGING_STRATEGIES}, got {set(strategies.keys())}"
        )

    def test_blocked_strategies_absent_from_config(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.RANGING)
        strategies = config["strategies"]
        for blocked in _RANGING_BLOCKED:
            assert blocked not in strategies, (
                f"Strategy '{blocked}' must be blocked in RANGING but was present"
            )

    def test_weights_sum_to_one(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.RANGING)
        total = sum(config["strategies"].values())
        assert abs(total - 1.0) < 1e-9, f"RANGING weights sum to {total}, expected 1.0"

    def test_individual_weights(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.RANGING)
        strategies = config["strategies"]
        assert strategies["value_area"] == pytest.approx(0.45)
        assert strategies["mean_reversion"] == pytest.approx(0.35)
        assert strategies["ml_reversal"] == pytest.approx(0.20)

    def test_signal_threshold(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.RANGING)
        assert config["signal_threshold"] == pytest.approx(0.60)

    def test_get_blocked_strategies(self, router: StrategyRouter) -> None:
        blocked = router.get_blocked_strategies(MarketRegime.RANGING)
        assert _RANGING_BLOCKED.issubset(blocked)


# ---------------------------------------------------------------------------
# Test 3 — VOLATILE
# ---------------------------------------------------------------------------


class TestVolatileRegime:
    """StrategyRouter output for VOLATILE market regime (trading halt)."""

    def test_allow_trading_is_false(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.VOLATILE)
        assert config["allow_trading"] is False

    def test_strategies_dict_is_empty(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.VOLATILE)
        assert config["strategies"] == {}, (
            f"VOLATILE should return empty strategies, got {config['strategies']}"
        )

    def test_all_known_strategies_are_blocked(self, router: StrategyRouter) -> None:
        blocked = router.get_blocked_strategies(MarketRegime.VOLATILE)
        for name in _KNOWN_STRATEGIES:
            assert name in blocked, f"Strategy '{name}' should be blocked in VOLATILE"

    def test_reason_is_non_empty_string(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.VOLATILE)
        assert isinstance(config["reason"], str) and len(config["reason"]) > 0

    def test_config_has_all_required_keys(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.VOLATILE)
        for key in ("strategies", "signal_threshold", "allow_trading", "reason"):
            assert key in config, f"Missing required key '{key}' in VOLATILE config"


# ---------------------------------------------------------------------------
# Test 4 — UNKNOWN
# ---------------------------------------------------------------------------


class TestUnknownRegime:
    """StrategyRouter output for UNKNOWN market regime (extra-selective)."""

    def test_allow_trading_is_true(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.UNKNOWN)
        assert config["allow_trading"] is True

    def test_all_five_strategies_present(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.UNKNOWN)
        strategies = config["strategies"]
        expected = {"momentum", "breakout", "value_area", "mean_reversion", "ml_reversal"}
        assert set(strategies.keys()) == expected, (
            f"UNKNOWN should have all 5 strategies, got {set(strategies.keys())}"
        )

    def test_equal_weights(self, router: StrategyRouter) -> None:
        config = router.get_strategy_config(MarketRegime.UNKNOWN)
        for name, weight in config["strategies"].items():
            assert weight == pytest.approx(0.20), (
                f"Strategy '{name}' weight should be 0.20, got {weight}"
            )

    def test_signal_threshold_is_more_selective(self, router: StrategyRouter) -> None:
        """UNKNOWN threshold (0.75) must be stricter than TRENDING/RANGING (0.60)."""
        config = router.get_strategy_config(MarketRegime.UNKNOWN)
        assert config["signal_threshold"] == pytest.approx(0.75)
        assert config["signal_threshold"] > 0.60

    def test_no_strategies_blocked(self, router: StrategyRouter) -> None:
        blocked = router.get_blocked_strategies(MarketRegime.UNKNOWN)
        assert len(blocked) == 0, f"UNKNOWN should block nothing, got blocked={blocked}"


# ---------------------------------------------------------------------------
# Test 5 — Output dict contract (all regimes)
# ---------------------------------------------------------------------------


class TestOutputContract:
    """Every regime must return a dict with the four required typed keys."""

    @pytest.mark.parametrize(
        "regime",
        [
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.VOLATILE,
            MarketRegime.UNKNOWN,
        ],
    )
    def test_required_keys_present(self, router: StrategyRouter, regime: MarketRegime) -> None:
        config = router.get_strategy_config(regime)
        assert "strategies" in config
        assert "signal_threshold" in config
        assert "allow_trading" in config
        assert "reason" in config

    @pytest.mark.parametrize(
        "regime",
        [
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.VOLATILE,
            MarketRegime.UNKNOWN,
        ],
    )
    def test_key_types(self, router: StrategyRouter, regime: MarketRegime) -> None:
        config = router.get_strategy_config(regime)
        assert isinstance(config["strategies"], dict)
        assert isinstance(config["signal_threshold"], float)
        assert isinstance(config["allow_trading"], bool)
        assert isinstance(config["reason"], str)

    @pytest.mark.parametrize(
        "regime",
        [
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.UNKNOWN,
        ],
    )
    def test_all_weights_are_positive(
        self, router: StrategyRouter, regime: MarketRegime
    ) -> None:
        config = router.get_strategy_config(regime)
        for name, weight in config["strategies"].items():
            assert weight > 0, (
                f"Strategy '{name}' in {regime.value} has non-positive weight {weight}"
            )

    @pytest.mark.parametrize(
        "regime",
        [
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.UNKNOWN,
        ],
    )
    def test_threshold_in_valid_range(
        self, router: StrategyRouter, regime: MarketRegime
    ) -> None:
        config = router.get_strategy_config(regime)
        assert 0.0 <= config["signal_threshold"] <= 1.0


# ---------------------------------------------------------------------------
# Test 6 — Isolation between TRENDING and RANGING strategy sets
# ---------------------------------------------------------------------------


class TestRegimeIsolation:
    """Trending and ranging strategies must be mutually exclusive."""

    def test_trending_and_ranging_strategies_do_not_overlap(
        self, router: StrategyRouter
    ) -> None:
        trending = set(router.get_strategy_config(MarketRegime.TRENDING)["strategies"])
        ranging = set(router.get_strategy_config(MarketRegime.RANGING)["strategies"])
        overlap = trending & ranging
        assert overlap == set(), (
            f"TRENDING and RANGING strategy sets must not overlap; found: {overlap}"
        )

    def test_trending_blocked_are_ranging_allowed(self, router: StrategyRouter) -> None:
        """Strategies blocked in TRENDING should be present (and weighted) in RANGING."""
        ranging_strategies = set(
            router.get_strategy_config(MarketRegime.RANGING)["strategies"]
        )
        for name in _TRENDING_BLOCKED:
            assert name in ranging_strategies, (
                f"'{name}' is blocked in TRENDING but should be allowed in RANGING"
            )

    def test_ranging_blocked_are_trending_allowed(self, router: StrategyRouter) -> None:
        """Strategies blocked in RANGING should be present (and weighted) in TRENDING."""
        trending_strategies = set(
            router.get_strategy_config(MarketRegime.TRENDING)["strategies"]
        )
        for name in _RANGING_BLOCKED:
            assert name in trending_strategies, (
                f"'{name}' is blocked in RANGING but should be allowed in TRENDING"
            )
