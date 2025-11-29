"""
Database models for trading strategies.

This module defines the SQLAlchemy ORM models for strategy management:
- Strategy: Trading strategy configuration and allocation
- StrategyAllocation: Historical capital allocation records
- StrategyPerformance: Performance metrics by period
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Numeric,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from src.database.config import Base


class StrategyStatus(str, enum.Enum):
    """Strategy status enumeration."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class PerformancePeriod(str, enum.Enum):
    """Performance period enumeration."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ALL_TIME = "all_time"


class Strategy(Base):
    """
    Trading strategy model.

    Stores configuration and current state for each trading strategy including
    allocated capital, parameters, and status.
    """
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus, name="strategy_status", create_type=False),
        nullable=False,
        default=StrategyStatus.ACTIVE,
        server_default="ACTIVE",
        index=True
    )
    allocated_capital: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00"
    )
    parameters: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        onupdate=datetime.utcnow
    )

    # Relationships
    allocations: Mapped[List["StrategyAllocation"]] = relationship(
        "StrategyAllocation",
        back_populates="strategy",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    performance_records: Mapped[List["StrategyPerformance"]] = relationship(
        "StrategyPerformance",
        back_populates="strategy",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Strategy(id={self.id}, name='{self.name}', status='{self.status}', capital={self.allocated_capital})>"


class StrategyAllocation(Base):
    """
    Strategy allocation history model.

    Tracks changes in capital allocation to strategies over time for
    performance analysis and auditing.
    """
    __tablename__ = "strategy_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    allocated_capital: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False
    )
    allocated_percentage: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False
    )
    allocation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()"
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(
        "Strategy",
        back_populates="allocations"
    )

    def __repr__(self) -> str:
        return f"<StrategyAllocation(id={self.id}, strategy_id={self.strategy_id}, capital={self.allocated_capital}, date={self.allocation_date})>"

    __table_args__ = (
        Index(
            "ix_strategy_allocations_strategy_id_date",
            "strategy_id",
            "allocation_date",
            postgresql_ops={"allocation_date": "DESC"}
        ),
    )


class StrategyPerformance(Base):
    """
    Strategy performance metrics model.

    Stores calculated performance metrics for strategies by time period
    (daily, weekly, monthly, all-time) for analysis and reporting.
    """
    __tablename__ = "strategy_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    period: Mapped[PerformancePeriod] = mapped_column(
        Enum(PerformancePeriod, name="performance_period", create_type=False),
        nullable=False,
        index=True
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Trade statistics
    total_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    winning_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    losing_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )

    # Performance metrics
    win_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00"
    )
    total_profit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00"
    )
    total_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00"
    )
    net_profit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00"
    )
    sharpe_ratio: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=8, scale=4),
        nullable=True
    )
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=8, scale=4),
        nullable=True
    )
    average_win: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=True
    )
    average_loss: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        onupdate=datetime.utcnow
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(
        "Strategy",
        back_populates="performance_records"
    )

    def __repr__(self) -> str:
        return f"<StrategyPerformance(id={self.id}, strategy_id={self.strategy_id}, period='{self.period}', net_profit={self.net_profit})>"

    __table_args__ = (
        Index(
            "ix_strategy_performance_strategy_id_period",
            "strategy_id",
            "period"
        ),
        UniqueConstraint(
            "strategy_id",
            "period",
            "period_start",
            "period_end",
            name="uq_strategy_performance_strategy_period_dates"
        ),
    )
