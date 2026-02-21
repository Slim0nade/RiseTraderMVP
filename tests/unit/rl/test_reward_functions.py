"""
Unit tests for RL reward functions.

Tests reward_functions.py (T108-T111).
"""

import pytest

from src.ml.rl.rewards.reward_functions import (
    position_sizing_reward,
    stop_loss_reward,
    take_profit_reward,
    trade_decision_reward,
)


# ============================================================================
# position_sizing_reward (T108)
# ============================================================================


class TestPositionSizingReward:
    """Tests for the position sizing reward function."""

    def test_positive_sharpe_no_drawdown_no_cost(self):
        """Reward equals sharpe_contrib when drawdown and cost are zero."""
        reward = position_sizing_reward(
            sharpe_contrib=0.5, drawdown_pct=0.0, transaction_cost=0.0
        )
        assert reward == pytest.approx(0.5)

    def test_drawdown_penalty_above_threshold(self):
        """Drawdown above threshold should reduce reward."""
        reward_no_dd = position_sizing_reward(
            sharpe_contrib=0.5, drawdown_pct=0.0, transaction_cost=0.0
        )
        reward_with_dd = position_sizing_reward(
            sharpe_contrib=0.5, drawdown_pct=0.15, transaction_cost=0.0
        )
        assert reward_with_dd < reward_no_dd

    def test_drawdown_below_threshold_no_penalty(self):
        """Drawdown below threshold should not incur a penalty."""
        reward = position_sizing_reward(
            sharpe_contrib=0.5,
            drawdown_pct=0.03,
            transaction_cost=0.0,
            drawdown_threshold=0.05,
        )
        assert reward == pytest.approx(0.5)

    def test_transaction_cost_reduces_reward(self):
        """Transaction cost should reduce reward linearly."""
        reward_no_cost = position_sizing_reward(
            sharpe_contrib=0.5, drawdown_pct=0.0, transaction_cost=0.0
        )
        reward_with_cost = position_sizing_reward(
            sharpe_contrib=0.5, drawdown_pct=0.0, transaction_cost=0.1
        )
        assert reward_with_cost < reward_no_cost
        assert reward_with_cost == pytest.approx(0.5 - 0.1)


# ============================================================================
# stop_loss_reward (T109)
# ============================================================================


class TestStopLossReward:
    """Tests for the stop loss reward function."""

    def test_no_stop_returns_small_positive(self):
        """When stop is not triggered, a small positive reward is returned."""
        reward = stop_loss_reward(
            stopped_out=False,
            capital_protected_pct=0.0,
            unnecessary_stop=False,
        )
        assert reward > 0

    def test_stop_with_capital_protection(self):
        """Capital protection should produce a positive reward."""
        reward = stop_loss_reward(
            stopped_out=True,
            capital_protected_pct=0.8,
            unnecessary_stop=False,
        )
        assert reward > 0

    def test_unnecessary_stop_penalty(self):
        """Unnecessary stop should reduce reward below the protection value."""
        reward_necessary = stop_loss_reward(
            stopped_out=True,
            capital_protected_pct=0.3,
            unnecessary_stop=False,
        )
        reward_unnecessary = stop_loss_reward(
            stopped_out=True,
            capital_protected_pct=0.3,
            unnecessary_stop=True,
        )
        assert reward_unnecessary < reward_necessary


# ============================================================================
# take_profit_reward (T110)
# ============================================================================


class TestTakeProfitReward:
    """Tests for the take profit reward function."""

    def test_full_capture_high_reward(self):
        """Capturing 100% of the move should yield a reward near 1.0."""
        reward = take_profit_reward(
            profit_captured_pct=1.0,
            expected_value=0.5,
            partial_fills=False,
        )
        assert reward > 0.9

    def test_zero_capture_zero_reward(self):
        """Capturing nothing should yield at most a small negative reward."""
        reward = take_profit_reward(
            profit_captured_pct=0.0,
            expected_value=0.5,
            partial_fills=False,
        )
        assert reward <= 0.0 + 1e-6

    def test_partial_fill_penalty(self):
        """Partial fills should be penalised relative to full fills."""
        reward_full = take_profit_reward(
            profit_captured_pct=0.5,
            expected_value=0.5,
            partial_fills=False,
        )
        reward_partial = take_profit_reward(
            profit_captured_pct=0.5,
            expected_value=0.5,
            partial_fills=True,
        )
        assert reward_partial < reward_full

    def test_ev_bonus_when_exceeding_forecast(self):
        """Capturing more than the expected value should yield a bonus."""
        reward_at_ev = take_profit_reward(
            profit_captured_pct=0.5,
            expected_value=0.5,
            partial_fills=False,
        )
        reward_above_ev = take_profit_reward(
            profit_captured_pct=0.8,
            expected_value=0.5,
            partial_fills=False,
        )
        assert reward_above_ev > reward_at_ev


# ============================================================================
# trade_decision_reward (T111)
# ============================================================================


class TestTradeDecisionReward:
    """Tests for the trade decision reward function."""

    def test_positive_pnl_positive_reward(self):
        """Positive PnL should produce a positive reward."""
        reward = trade_decision_reward(
            realized_pnl=0.01, direction_correct=True
        )
        assert reward > 0

    def test_negative_pnl_negative_reward(self):
        """Negative PnL should produce a negative reward."""
        reward = trade_decision_reward(
            realized_pnl=-0.01, direction_correct=False
        )
        assert reward < 0

    def test_direction_bonus_adds_value(self):
        """Correct direction should add to the reward."""
        reward_correct = trade_decision_reward(
            realized_pnl=0.01, direction_correct=True
        )
        reward_wrong = trade_decision_reward(
            realized_pnl=0.01, direction_correct=False
        )
        assert reward_correct > reward_wrong

    def test_zero_pnl_direction_only(self):
        """Zero PnL with correct direction should still be positive."""
        reward = trade_decision_reward(
            realized_pnl=0.0, direction_correct=True
        )
        assert reward > 0
