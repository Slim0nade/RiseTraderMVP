"""
DecisionLog database model for agent decision tracking.
Uses TimescaleDB hypertable for time-series optimization with 90-day retention.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DecisionLog(Base):
    """
    DecisionLog model for tracking all agent decisions in chronological order.

    This table is converted to a TimescaleDB hypertable partitioned by decided_at
    for efficient time-series queries and automatic 90-day retention policy.

    Stores the complete decision-making context including:
    - Input data (market state, analyst reports)
    - Agent reasoning (LLM chain-of-thought)
    - Output decision (position size, stop loss, etc.)
    - Execution outcome
    """

    __tablename__ = "decision_log"

    # Primary key (UUID for global uniqueness)
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique decision identifier"
    )

    # Timestamp (MUST be part of primary key for TimescaleDB hypertable)
    decided_at: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
        comment="Decision timestamp (hypertable partition key)"
    )

    # Agent identity
    agent_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="FK to agents table"
    )

    agent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Agent type (denormalized for query performance)"
    )

    strategy_team_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="FK to strategy_teams table (NULL for global agents)"
    )

    # Market context
    symbol: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Trading symbol (e.g., 'Gold', 'CrudeOIL')"
    )

    timeframe: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Chart timeframe (e.g., 'H1', 'D1')"
    )

    # Decision input data (JSON)
    input_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Input data provided to agent (market state, analyst reports, etc.)"
    )

    # Agent reasoning
    reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Agent's chain-of-thought reasoning (LLM output)"
    )

    # Decision output
    decision_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Decision type: trade_intent, position_size, stop_loss, take_profit, etc."
    )

    decision_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Decision output (position size, stop price, confidence score, etc.)"
    )

    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Agent confidence score (0.0-1.0) if applicable"
    )

    # Execution outcome
    was_executed: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether decision led to actual trade execution"
    )

    execution_result: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Execution outcome (order ID, fill price, etc.) if executed"
    )

    # Performance tracking (for RL reward calculation)
    pnl_impact: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="P&L impact of this decision (USD) if measurable"
    )

    sharpe_impact: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Impact on portfolio Sharpe ratio if measurable"
    )

    # Metadata
    decision_latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Time taken for agent to make decision (milliseconds)"
    )

    model_version: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="RL model version if RL-enabled agent (e.g., 'v3.2-20250115')"
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_decision_log_agent_time", "agent_id", "decided_at"),
        Index("ix_decision_log_symbol_time", "symbol", "decided_at"),
        Index("ix_decision_log_team_time", "strategy_team_id", "decided_at"),
        Index("ix_decision_log_type_time", "decision_type", "decided_at"),
        {
            "comment": (
                "Agent decision log - TimescaleDB hypertable with 90-day retention. "
                "Partitioned by decided_at for time-series performance."
            )
        }
    )

    def __repr__(self) -> str:
        return (
            f"<DecisionLog(id={self.id}, agent_type='{self.agent_type}', "
            f"decision_type='{self.decision_type}', decided_at={self.decided_at})>"
        )
