"""
PortfolioAllocation database model for capital allocation across strategy teams.
Supports both static (config-based) and dynamic (Portfolio Allocator Agent) allocation.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class PortfolioAllocation(Base, TimestampMixin):
    """
    PortfolioAllocation model for managing capital distribution.

    Supports two allocation modes:
    1. Static: Fixed allocations from portfolio_allocation.yaml
    2. Dynamic: AI-driven rebalancing by Portfolio Allocator Agent

    Example allocations:
    - 40% to Gold strategy team ($40,000 of $100,000 portfolio)
    - 40% to Crude Oil strategy team ($40,000)
    - 20% Reserve capital ($20,000)

    Includes risk limits and rebalancing triggers per allocation.
    """

    __tablename__ = "portfolio_allocations"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique allocation identifier"
    )

    # Allocation identity
    allocation_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable allocation name (e.g., 'Q1 2025 Gold Allocation')"
    )

    strategy_team_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="FK to strategy_teams table (NULL for reserve capital)"
    )

    symbol: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Trading symbol (e.g., 'Gold', 'CrudeOIL') - NULL for reserve"
    )

    # Allocation amounts
    allocated_capital_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Capital allocated in USD"
    )

    allocated_percentage: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Percentage of total portfolio (0.0-100.0)"
    )

    total_portfolio_capital_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Total portfolio capital at allocation time (for reference)"
    )

    # Risk limits
    max_drawdown_limit: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Maximum allowed drawdown for this allocation (0.0-1.0, e.g., 0.15 = 15%)"
    )

    max_leverage: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=1.0,
        comment="Maximum leverage allowed (1.0 = no leverage)"
    )

    max_correlated_exposure_pct: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Maximum combined exposure to correlated instruments (0.0-100.0)"
    )

    # Rebalancing configuration
    allocation_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="static",
        index=True,
        comment="Allocation mode: static (config-based), dynamic (AI-driven)"
    )

    rebalance_frequency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        comment="Rebalancing frequency: manual, daily, weekly, monthly"
    )

    next_rebalance_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        index=True,
        comment="Next scheduled rebalancing timestamp"
    )

    last_rebalanced_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Last rebalancing timestamp"
    )

    # Rebalancing triggers (for dynamic mode)
    sharpe_threshold: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Increase allocation if Sharpe ratio > threshold"
    )

    drawdown_threshold: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Reduce allocation if drawdown > threshold"
    )

    correlation_threshold: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Reduce allocation if correlation with other positions > threshold"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this allocation is currently active"
    )

    effective_from: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
        comment="Effective start date for this allocation"
    )

    effective_until: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Effective end date (NULL = indefinite)"
    )

    # Performance tracking
    current_capital_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Current capital value (allocated + P&L)"
    )

    realized_pnl_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Realized P&L for this allocation"
    )

    unrealized_pnl_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Unrealized P&L for this allocation"
    )

    current_drawdown_pct: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Current drawdown percentage (0.0-100.0)"
    )

    # Metadata
    created_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
        comment="User or system that created this allocation"
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Allocation notes and rationale"
    )

    def __repr__(self) -> str:
        return (
            f"<PortfolioAllocation(id={self.id}, symbol='{self.symbol}', "
            f"allocated=${self.allocated_capital_usd:,.2f} ({self.allocated_percentage}%), "
            f"mode='{self.allocation_mode}', active={self.is_active})>"
        )
