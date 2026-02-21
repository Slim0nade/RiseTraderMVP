"""
Reward functions for RL trading environments.

Tasks T108-T111: Phase 7, User Story 5.

Each function computes a scalar reward for a specific RL task:
    - position_sizing_reward (T108): Sharpe contribution - drawdown - costs
    - stop_loss_reward (T109): Capital protection vs unnecessary stop penalty
    - take_profit_reward (T110): Expected value capture maximisation
    - trade_decision_reward (T111): PnL weighted by directional accuracy
"""

import numpy as np


def position_sizing_reward(
    sharpe_contrib: float,
    drawdown_pct: float,
    transaction_cost: float,
    drawdown_threshold: float = 0.05,
    drawdown_penalty_coef: float = 2.0,
    cost_penalty_coef: float = 1.0,
) -> float:
    """
    Reward for position sizing decisions.

    Encourages risk-adjusted returns (positive Sharpe contribution)
    while penalising excessive drawdown and transaction costs.

    Args:
        sharpe_contrib: Marginal Sharpe ratio contribution of this trade.
                        Positive means the trade improved portfolio Sharpe.
        drawdown_pct: Current drawdown as a fraction (0 to 1).
        transaction_cost: Absolute or proportional cost of the trade.
        drawdown_threshold: Drawdown level below which no penalty applies.
        drawdown_penalty_coef: Multiplier for drawdown above threshold.
        cost_penalty_coef: Multiplier for transaction cost penalty.

    Returns:
        Scalar reward.
    """
    reward = float(sharpe_contrib)

    # Penalise drawdown only when it exceeds the threshold
    excess_drawdown = max(0.0, float(drawdown_pct) - drawdown_threshold)
    reward -= drawdown_penalty_coef * excess_drawdown

    # Penalise transaction costs
    reward -= cost_penalty_coef * float(transaction_cost)

    return reward


def stop_loss_reward(
    stopped_out: bool,
    capital_protected_pct: float,
    unnecessary_stop: bool,
    protection_bonus: float = 1.0,
    unnecessary_penalty: float = 0.5,
    no_stop_reward: float = 0.1,
) -> float:
    """
    Reward for stop-loss placement decisions.

    Rewards the agent for protecting capital when the trade moves against
    it, but penalises unnecessary stop-outs that cause whipsaw losses.

    Args:
        stopped_out: Whether the stop was triggered.
        capital_protected_pct: Fraction of capital saved by the stop
                               (relevant only when stopped_out and loss).
        unnecessary_stop: Whether the trade reversed back in favour
                          after the stop was hit.
        protection_bonus: Bonus multiplier for capital protection.
        unnecessary_penalty: Penalty for triggering an unnecessary stop.
        no_stop_reward: Small reward for trades that did not trigger the stop.

    Returns:
        Scalar reward.
    """
    if not stopped_out:
        # Trade completed without hitting the stop
        return float(no_stop_reward)

    reward = protection_bonus * float(capital_protected_pct)

    if unnecessary_stop:
        reward -= float(unnecessary_penalty)

    return reward


def take_profit_reward(
    profit_captured_pct: float,
    expected_value: float,
    partial_fills: bool,
    ev_bonus_coef: float = 0.5,
    partial_penalty: float = 0.1,
) -> float:
    """
    Reward for take-profit placement decisions.

    Maximises the fraction of available profit captured and rewards
    the agent for placing take-profit levels that align with the
    expected value from forecasting models.

    Args:
        profit_captured_pct: Fraction of maximum favourable excursion
                             captured by the exit (0 to 1).
        expected_value: Forecasted expected move as a fraction of price.
        partial_fills: True if the trade exited before hitting TP or SL
                       (time-based exit).
        ev_bonus_coef: Bonus coefficient when capture exceeds expected value.
        partial_penalty: Penalty for partial fills (did not reach TP/SL).

    Returns:
        Scalar reward.
    """
    reward = float(profit_captured_pct)

    # Bonus when the agent captures more than the forecasted EV
    if profit_captured_pct > expected_value and expected_value > 0:
        reward += ev_bonus_coef * (profit_captured_pct - expected_value)

    # Mild penalty for trades that timed out
    if partial_fills:
        reward -= float(partial_penalty)

    return reward


def trade_decision_reward(
    realized_pnl: float,
    direction_correct: bool,
    direction_bonus: float = 0.2,
    pnl_scale: float = 100.0,
) -> float:
    """
    Reward for trade entry/exit decisions (HOLD/BUY/SELL).

    Combines realised PnL with a bonus for correct directional prediction.
    The PnL is scaled so that typical trade returns produce rewards in
    a reasonable range for policy gradient methods.

    Args:
        realized_pnl: PnL of the step as a fraction of capital.
        direction_correct: Whether the agent's position matched the
                           subsequent price move direction.
        direction_bonus: Additional reward for correct direction.
        pnl_scale: Scaling factor applied to the raw PnL.

    Returns:
        Scalar reward.
    """
    reward = float(realized_pnl) * pnl_scale

    if direction_correct:
        reward += float(direction_bonus)

    return reward
