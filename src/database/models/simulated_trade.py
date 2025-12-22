"""
SQLAlchemy models for backtest execution tracking.

This module defines models for tracking backtest execution details:
- SimulatedTrade: Individual trade records with P&L
- PortfolioSnapshot: Periodic portfolio state snapshots
- AgentDecisionLog: Audit trail of agent decisions (full pipeline mode)
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from enum import Enum as PyEnum
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship

from src.database.models.base import Base


class TradeAction(str, PyEnum):
    """Trade action type."""
    BUY = "buy"
    SELL = "sell"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class DecisionType(str, PyEnum):
    """Agent decision type."""
    SIGNAL = "signal"
    RISK = "risk"
    EXECUTION = "execution"
    OTHER = "other"


class SimulatedTrade(Base):
    """
    Record of a single trade executed during backtest.

    Attributes:
        id: Unique identifier
        backtest_run_id: Foreign key to BacktestRun
        symbol: Trading symbol
        action: 'buy', 'sell', 'close_long', or 'close_short'
        entry_timestamp: Trade entry time (UTC)
        entry_price: Entry price
        quantity: Trade quantity/lot size
        exit_timestamp: Trade exit time (NULL if still open)
        exit_price: Exit price (NULL if still open)
        gross_pnl: P&L before fees (NULL if open)
        fees_paid: Total fees (slippage + commission)
        net_pnl: P&L after fees (NULL if open)
        holding_duration_seconds: Time between entry and exit
        decision_context: Agent decision rationale (JSON, full mode)
        slippage_applied: Actual slippage on entry
    """
    __tablename__ = "simulated_trades"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    backtest_run_id = Column(PGUUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    action = Column(
        SQLEnum(TradeAction, name="trade_action", create_type=False),
        nullable=False
    )
    entry_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    entry_price = Column(Numeric(18, 8), nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    exit_timestamp = Column(DateTime(timezone=True), nullable=True)
    exit_price = Column(Numeric(18, 8), nullable=True)
    gross_pnl = Column(Numeric(18, 2), nullable=True)
    fees_paid = Column(Numeric(18, 2), nullable=False)
    net_pnl = Column(Numeric(18, 2), nullable=True)
    holding_duration_seconds = Column(Integer, nullable=True)
    decision_context = Column(JSONB, nullable=True)
    slippage_applied = Column(Numeric(18, 8), nullable=False)

    # Relationships
    backtest_run = relationship("BacktestRun", back_populates="trades")

    def __repr__(self) -> str:
        return f"<SimulatedTrade(id={self.id}, symbol={self.symbol}, action={self.action}, pnl={self.net_pnl})>"


class PortfolioSnapshot(Base):
    """
    Periodic snapshot of portfolio state during backtest.

    Attributes:
        id: Unique identifier
        backtest_run_id: Foreign key to BacktestRun
        timestamp: Snapshot time (UTC)
        cash_balance: Available cash
        positions: List of open positions (JSON)
        total_value: Cash + unrealized position value
        unrealized_pnl: Mark-to-market P&L on open positions
        realized_pnl: Cumulative P&L from closed trades
        buying_power: Available capital for new trades
    """
    __tablename__ = "portfolio_snapshots"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    backtest_run_id = Column(PGUUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    cash_balance = Column(Numeric(18, 2), nullable=False)
    positions = Column(JSONB, nullable=False)
    total_value = Column(Numeric(18, 2), nullable=False)
    unrealized_pnl = Column(Numeric(18, 2), nullable=False)
    realized_pnl = Column(Numeric(18, 2), nullable=False)
    buying_power = Column(Numeric(18, 2), nullable=False)

    # Relationships
    backtest_run = relationship("BacktestRun", back_populates="snapshots")

    def __repr__(self) -> str:
        return f"<PortfolioSnapshot(id={self.id}, timestamp={self.timestamp}, value={self.total_value})>"


class AgentDecisionLog(Base):
    """
    Audit trail of agent decisions during full pipeline mode backtest.

    Attributes:
        id: Unique identifier
        backtest_run_id: Foreign key to BacktestRun
        timestamp: Decision timestamp (UTC)
        agent_identifier: Agent name (e.g., "SignalGeneratorAgent")
        decision_type: 'signal', 'risk', 'execution', or 'other'
        input_data: All inputs to agent decision (JSON)
        output_decision: Agent's decision output (JSON)
        execution_outcome: Result ('accepted', 'rejected', 'timeout', etc.)
        processing_time_ms: Time taken for agent to decide
        correlation_id: Links related decisions (same market event)
    """
    __tablename__ = "agent_decision_logs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    backtest_run_id = Column(PGUUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    agent_identifier = Column(String(255), nullable=False, index=True)
    decision_type = Column(String(9), nullable=False)  # Changed from ENUM to match database VARCHAR(9)
    input_data = Column(JSONB, nullable=False)
    output_decision = Column(JSONB, nullable=False)
    execution_outcome = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    correlation_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)

    # Relationships
    backtest_run = relationship("BacktestRun", back_populates="agent_decisions")

    def __repr__(self) -> str:
        return f"<AgentDecisionLog(id={self.id}, agent={self.agent_identifier}, type={self.decision_type})>"
