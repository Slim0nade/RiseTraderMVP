"""
Unit tests for RL trading environments.

Tests TradingEnvironment (T104), PositionSizingEnvironment (T105),
StopLossEnvironment (T106), and TakeProfitEnvironment (T107).
"""

import numpy as np
import pytest

from src.ml.rl.environments.trading_env import (
    BUY,
    HOLD,
    SELL,
    TradingEnvironment,
)
from src.ml.rl.environments.position_sizing_env import PositionSizingEnvironment
from src.ml.rl.environments.stop_loss_env import StopLossEnvironment
from src.ml.rl.environments.take_profit_env import TakeProfitEnvironment


# ============================================================================
# Fixtures
# ============================================================================


def _make_price_data(n: int = 200, seed: int = 42):
    """Generate synthetic price data with a gentle uptrend."""
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.0002, 0.01, n)
    prices = 100.0 * np.exp(np.cumsum(returns))
    return prices


def _make_features(n: int = 200, num_features: int = 5, seed: int = 42):
    """Generate random normalised features."""
    rng = np.random.RandomState(seed)
    return rng.randn(n, num_features).astype(np.float32)


@pytest.fixture
def trading_env():
    """Create a TradingEnvironment with synthetic data."""
    n = 200
    prices = _make_price_data(n)
    features = _make_features(n)
    env = TradingEnvironment(
        prices=prices,
        features=features,
        initial_balance=10_000.0,
        transaction_cost=0.001,
        lookback_window=30,
    )
    return env


@pytest.fixture
def position_sizing_env():
    """Create a PositionSizingEnvironment with synthetic data."""
    n = 200
    rng = np.random.RandomState(42)
    prices = _make_price_data(n)
    features = _make_features(n)
    signals = np.where(rng.rand(n) > 0.5, 1.0, -1.0).astype(np.float32)
    conviction = rng.uniform(0.3, 0.9, n).astype(np.float32)
    regimes = rng.choice([0, 1, 2], n).astype(np.int32)
    env = PositionSizingEnvironment(
        prices=prices,
        features=features,
        signals=signals,
        conviction_scores=conviction,
        regime_labels=regimes,
        lookback_window=30,
    )
    return env


@pytest.fixture
def stop_loss_env():
    """Create a StopLossEnvironment with synthetic data."""
    n = 200
    rng = np.random.RandomState(42)
    prices = _make_price_data(n)
    features = _make_features(n)
    highs = prices * (1 + rng.uniform(0.001, 0.02, n))
    lows = prices * (1 - rng.uniform(0.001, 0.02, n))
    atr = np.full(n, 1.5)
    support = rng.uniform(1.0, 5.0, n).astype(np.float32)
    resistance = rng.uniform(1.0, 5.0, n).astype(np.float32)
    directions = np.where(rng.rand(n) > 0.5, 1.0, -1.0).astype(np.float32)
    env = StopLossEnvironment(
        prices_high=highs,
        prices_low=lows,
        prices_close=prices,
        features=features,
        atr_values=atr,
        support_distances=support,
        resistance_distances=resistance,
        trade_directions=directions,
        lookback_window=30,
        trade_horizon=20,
    )
    return env


@pytest.fixture
def take_profit_env():
    """Create a TakeProfitEnvironment with synthetic data."""
    n = 200
    rng = np.random.RandomState(42)
    prices = _make_price_data(n)
    features = _make_features(n)
    highs = prices * (1 + rng.uniform(0.001, 0.02, n))
    lows = prices * (1 - rng.uniform(0.001, 0.02, n))
    atr = np.full(n, 1.5)
    directions = np.where(rng.rand(n) > 0.5, 1.0, -1.0).astype(np.float32)
    q25 = prices * 0.98
    q50 = prices * 1.0
    q75 = prices * 1.02
    env = TakeProfitEnvironment(
        prices_high=highs,
        prices_low=lows,
        prices_close=prices,
        features=features,
        atr_values=atr,
        forecast_q25=q25.astype(np.float32),
        forecast_q50=q50.astype(np.float32),
        forecast_q75=q75.astype(np.float32),
        trade_directions=directions,
        lookback_window=30,
        trade_horizon=40,
    )
    return env


# ============================================================================
# TradingEnvironment Tests
# ============================================================================


class TestTradingEnvironment:
    """Tests for TradingEnvironment (T104)."""

    def test_reset_returns_observation_and_info(self, trading_env):
        """Reset must return (observation, info) tuple."""
        result = trading_env.reset()
        assert isinstance(result, tuple)
        assert len(result) == 2
        obs, info = result
        assert isinstance(obs, np.ndarray)
        assert isinstance(info, dict)

    def test_observation_shape(self, trading_env):
        """Observation shape must match observation_space."""
        obs, _ = trading_env.reset()
        assert obs.shape == trading_env.observation_space.shape

    def test_observation_dtype(self, trading_env):
        """Observation must be float32 for neural network compatibility."""
        obs, _ = trading_env.reset()
        assert obs.dtype == np.float32

    def test_step_returns_five_elements(self, trading_env):
        """Step must return (obs, reward, terminated, truncated, info)."""
        trading_env.reset()
        result = trading_env.step(HOLD)
        assert len(result) == 5
        obs, reward, terminated, truncated, info = result
        assert isinstance(obs, np.ndarray)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)

    def test_step_hold_no_trade(self, trading_env):
        """HOLD action should not change position or trade count."""
        trading_env.reset()
        _, _, _, _, info = trading_env.step(HOLD)
        assert info["position"] == 0.0
        assert info["trade_count"] == 0

    def test_step_buy_opens_long(self, trading_env):
        """BUY action should open a long position."""
        trading_env.reset()
        _, _, _, _, info = trading_env.step(BUY)
        assert info["position"] > 0
        assert info["trade_count"] == 1

    def test_step_sell_opens_short(self, trading_env):
        """SELL action should open a short position."""
        trading_env.reset()
        _, _, _, _, info = trading_env.step(SELL)
        assert info["position"] < 0
        assert info["trade_count"] == 1

    def test_episode_terminates(self, trading_env):
        """Episode must eventually terminate when stepping through all data."""
        trading_env.reset()
        done = False
        steps = 0
        max_steps = len(trading_env.prices) + 10

        while not done and steps < max_steps:
            _, _, terminated, truncated, _ = trading_env.step(HOLD)
            done = terminated or truncated
            steps += 1

        assert done, "Episode did not terminate within expected steps"

    def test_invalid_action_raises(self, trading_env):
        """Passing an invalid action should raise an AssertionError."""
        trading_env.reset()
        with pytest.raises(AssertionError):
            trading_env.step(99)

    def test_info_contains_required_keys(self, trading_env):
        """Info dict must contain position, balance, drawdown, trade_count, price."""
        trading_env.reset()
        _, _, _, _, info = trading_env.step(HOLD)
        for key in ["position", "balance", "drawdown", "trade_count", "price"]:
            assert key in info, f"Missing key '{key}' in info dict"

    def test_balance_changes_after_trade(self, trading_env):
        """Balance should change after entering and exiting a trade."""
        trading_env.reset()
        _, _, _, _, info_before = trading_env.step(HOLD)
        balance_before = info_before["balance"]

        # Enter long
        trading_env.step(BUY)
        # Step forward several bars
        for _ in range(5):
            trading_env.step(HOLD)
        # Exit
        _, _, _, _, info_after = trading_env.step(SELL)

        # Balance should have changed (very unlikely to be exactly equal)
        assert info_after["balance"] != balance_before


# ============================================================================
# PositionSizingEnvironment Tests
# ============================================================================


class TestPositionSizingEnvironment:
    """Tests for PositionSizingEnvironment (T105)."""

    def test_reset_returns_correct_shape(self, position_sizing_env):
        obs, info = position_sizing_env.reset()
        assert obs.shape == position_sizing_env.observation_space.shape

    def test_action_space_is_box(self, position_sizing_env):
        from gymnasium.spaces import Box
        assert isinstance(position_sizing_env.action_space, Box)

    def test_step_with_zero_allocation(self, position_sizing_env):
        position_sizing_env.reset()
        action = np.array([0.0], dtype=np.float32)
        obs, reward, terminated, truncated, info = position_sizing_env.step(action)
        assert obs.shape == position_sizing_env.observation_space.shape

    def test_step_with_full_allocation(self, position_sizing_env):
        position_sizing_env.reset()
        action = np.array([1.0], dtype=np.float32)
        obs, reward, terminated, truncated, info = position_sizing_env.step(action)
        assert isinstance(reward, float)

    def test_episode_terminates(self, position_sizing_env):
        position_sizing_env.reset()
        done = False
        steps = 0
        while not done and steps < 500:
            action = np.array([0.5], dtype=np.float32)
            _, _, terminated, truncated, _ = position_sizing_env.step(action)
            done = terminated or truncated
            steps += 1
        assert done


# ============================================================================
# StopLossEnvironment Tests
# ============================================================================


class TestStopLossEnvironment:
    """Tests for StopLossEnvironment (T106)."""

    def test_reset_returns_correct_shape(self, stop_loss_env):
        obs, info = stop_loss_env.reset()
        assert obs.shape == stop_loss_env.observation_space.shape

    def test_action_space_bounds(self, stop_loss_env):
        assert float(stop_loss_env.action_space.low[0]) == pytest.approx(0.5)
        assert float(stop_loss_env.action_space.high[0]) == pytest.approx(5.0)

    def test_step_with_tight_stop(self, stop_loss_env):
        stop_loss_env.reset()
        action = np.array([0.5], dtype=np.float32)
        obs, reward, terminated, truncated, info = stop_loss_env.step(action)
        assert isinstance(reward, float)
        assert "trade_count" in info

    def test_step_with_wide_stop(self, stop_loss_env):
        stop_loss_env.reset()
        action = np.array([5.0], dtype=np.float32)
        obs, reward, terminated, truncated, info = stop_loss_env.step(action)
        assert obs.shape == stop_loss_env.observation_space.shape


# ============================================================================
# TakeProfitEnvironment Tests
# ============================================================================


class TestTakeProfitEnvironment:
    """Tests for TakeProfitEnvironment (T107)."""

    def test_reset_returns_correct_shape(self, take_profit_env):
        obs, info = take_profit_env.reset()
        assert obs.shape == take_profit_env.observation_space.shape

    def test_action_space_bounds(self, take_profit_env):
        assert float(take_profit_env.action_space.low[0]) == pytest.approx(1.0)
        assert float(take_profit_env.action_space.high[0]) == pytest.approx(10.0)

    def test_step_with_low_rr(self, take_profit_env):
        take_profit_env.reset()
        action = np.array([1.0], dtype=np.float32)
        obs, reward, terminated, truncated, info = take_profit_env.step(action)
        assert isinstance(reward, float)

    def test_step_with_high_rr(self, take_profit_env):
        take_profit_env.reset()
        action = np.array([10.0], dtype=np.float32)
        obs, reward, terminated, truncated, info = take_profit_env.step(action)
        assert "tp_hits" in info

    def test_episode_terminates(self, take_profit_env):
        take_profit_env.reset()
        done = False
        steps = 0
        while not done and steps < 500:
            action = np.array([2.0], dtype=np.float32)
            _, _, terminated, truncated, _ = take_profit_env.step(action)
            done = terminated or truncated
            steps += 1
        assert done
