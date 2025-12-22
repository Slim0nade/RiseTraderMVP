"""
Decision Layer Agents.

Provides specialized agents for intelligent decision-making:
- Position sizing (dynamic, Kelly-based, adaptive)
- Stop-loss placement (structure-aware, volatility-adaptive)
- Take-profit targeting (probabilistic, expected-value optimized)

These agents implement the core intelligence of the trading system,
replacing fixed rules with dynamic, data-driven decision-making.
"""

from src.agents.decision.position_sizing_agent import (
    PositionSizingAgent,
    PositionSizeDecision,
    create_position_sizing_agent,
)
from src.agents.decision.stop_loss_agent import (
    StopLossAgent,
    StopLossDecision,
    # StopPlacementStrategy,  # TODO: Class not yet implemented
    create_stop_loss_agent,
)
from src.agents.decision.take_profit_agent import (
    TakeProfitAgent,
    TakeProfitDecision,
    PartialTarget,
    create_take_profit_agent,
)

__all__ = [
    # Position Sizing
    "PositionSizingAgent",
    "PositionSizeDecision",
    "create_position_sizing_agent",
    # Stop-Loss
    "StopLossAgent",
    "StopLossDecision",
    # "StopPlacementStrategy",  # TODO: Class not yet implemented
    "create_stop_loss_agent",
    # Take-Profit
    "TakeProfitAgent",
    "TakeProfitDecision",
    "PartialTarget",
    "create_take_profit_agent",
]
