"""
StrategyTeam database model for multi-agent strategy team management.
Each team contains 11 specialized agents working on a single symbol.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class StrategyTeam(Base, TimestampMixin):
    """
    StrategyTeam model representing a cohesive team of 11 agents.

    Each strategy team operates on a single trading symbol (e.g., Gold, CrudeOIL)
    with 11 specialized agents across 4 layers:
    - Analysis Layer: Technical Analyst, Fundamental Analyst, Sentiment Analyst
    - Debate Layer: Devil's Advocate
    - Decision Layer: Position Sizing, Stop Loss, Take Profit, Entry Timing
    - Execution Layer: Trade Executor, Order Monitor
    - (Portfolio Allocator and Performance Tracker are global, not per-team)

    The 12th agent (Portfolio Allocator) is global and manages capital across teams.

    Example teams:
    - "team-gold-001": 11 agents trading Gold
    - "team-crude-001": 11 agents trading Crude Oil
    """

    __tablename__ = "strategy_teams"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique strategy team identifier"
    )

    # Team identity
    team_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique team name (e.g., 'team-gold-001', 'team-crude-001')"
    )

    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable display name (e.g., 'Gold Strategy Team v1')"
    )

    # Trading symbol
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Trading symbol (e.g., 'Gold', 'CrudeOIL', 'EURUSD')"
    )

    asset_class: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Asset class (e.g., 'commodity', 'forex', 'crypto')"
    )

    # Strategy configuration
    strategy_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="multi_agent_autonomous",
        comment="Strategy type: multi_agent_autonomous, hybrid, backtested"
    )

    trading_sessions: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Active trading sessions (e.g., {'london': true, 'new_york': true})"
    )

    allowed_timeframes: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=["H1", "H4", "D1"],
        comment="Timeframes this team can analyze (e.g., ['H1', 'H4', 'D1'])"
    )

    # Risk parameters (team-level defaults)
    max_position_size_lots: Mapped[float] = mapped_column(
        nullable=False,
        default=1.0,
        comment="Maximum position size in lots"
    )

    max_daily_trades: Mapped[int] = mapped_column(
        nullable=False,
        default=5,
        comment="Maximum trades per day for this team"
    )

    max_open_positions: Mapped[int] = mapped_column(
        nullable=False,
        default=3,
        comment="Maximum concurrent open positions"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether team is actively trading"
    )

    is_paper_trading: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether team is in paper trading mode (not live)"
    )

    activated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp when team was activated"
    )

    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp when team was deactivated"
    )

    # Agent composition (metadata)
    agent_count: Mapped[int] = mapped_column(
        nullable=False,
        default=11,
        comment="Number of agents in this team (should be 11)"
    )

    agent_composition: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment=(
            "Agent composition metadata "
            "(e.g., {'technical_analyst': 'agent-uuid-1', 'position_sizing': 'agent-uuid-2', ...})"
        )
    )

    # Team performance metadata (updated by Performance Tracker agent)
    total_trades: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Total trades executed by this team"
    )

    win_rate: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Win rate (0.0-1.0)"
    )

    current_sharpe_ratio: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Current Sharpe ratio"
    )

    current_drawdown_pct: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Current drawdown percentage"
    )

    # Metadata
    created_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
        comment="User or system that created this team"
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Team notes and configuration details"
    )

    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Custom tags (e.g., {'region': 'asia', 'version': 'v2.0'})"
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyTeam(id={self.id}, name='{self.team_name}', symbol='{self.symbol}', "
            f"agents={self.agent_count}, active={self.is_active}, paper={self.is_paper_trading})>"
        )
