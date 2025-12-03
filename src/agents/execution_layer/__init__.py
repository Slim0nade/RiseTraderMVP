"""
Execution Layer Agents.

Provides specialized agents for trade execution and position management:
- Trade execution via MT4/ZMQ bridge
- Position monitoring and adjustment
- Trailing stops and profit scaling
- Regime change detection and invalidation handling
"""

from src.agents.execution_layer.trade_executor import (
    TradeExecutorAgent,
    ExecutionResult,
    ExecutionStatus,
    OrderType,
    OrderSide,
    create_trade_executor,
)
from src.agents.execution_layer.position_monitor import (
    PositionMonitorAgent,
    PositionAdjustment,
    PositionAction,
    PositionAdjustmentReason,
    create_position_monitor,
)

__all__ = [
    # Trade Execution
    "TradeExecutorAgent",
    "ExecutionResult",
    "ExecutionStatus",
    "OrderType",
    "OrderSide",
    "create_trade_executor",
    # Position Monitoring
    "PositionMonitorAgent",
    "PositionAdjustment",
    "PositionAction",
    "PositionAdjustmentReason",
    "create_position_monitor",
]
