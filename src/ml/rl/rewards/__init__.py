"""
Reward functions for RL trading agents.

Functions:
    position_sizing_reward: Sharpe contribution minus drawdown and costs
    stop_loss_reward: Capital protection balanced against unnecessary stops
    take_profit_reward: Expected value capture maximization
    trade_decision_reward: PnL scaled by directional accuracy
"""

from .reward_functions import (
    position_sizing_reward,
    stop_loss_reward,
    take_profit_reward,
    trade_decision_reward,
)

__all__ = [
    "position_sizing_reward",
    "stop_loss_reward",
    "take_profit_reward",
    "trade_decision_reward",
]
