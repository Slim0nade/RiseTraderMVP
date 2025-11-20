"""
Trading simulation model.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class TradingSimulation(Base, TimestampMixin):
    """
    Trading simulation table storing backtest results.

    Contains ~28 records of backtest simulations.
    """

    __tablename__ = "trading_simulation"

    simulation_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # Simulation period
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Capital
    starting_capital: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    ending_capital: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    # Performance metrics
    result: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    return_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Trade statistics
    total_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    win_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Relationships
    optimal_trades: Mapped[list["OptimalTrade"]] = relationship(
        "OptimalTrade",
        back_populates="simulation",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<TradingSimulation(id={self.simulation_id}, "
            f"period={self.start_date.date()} to {self.end_date.date()}, "
            f"return={self.return_percent}%)>"
        )

    @property
    def profit_loss(self) -> Decimal:
        """Calculate profit/loss."""
        return self.ending_capital - self.starting_capital

    @property
    def return_on_investment(self) -> Optional[Decimal]:
        """Calculate ROI percentage."""
        if self.starting_capital == 0:
            return None
        return (self.profit_loss / self.starting_capital) * 100

    @property
    def duration_days(self) -> int:
        """Calculate simulation duration in days."""
        return (self.end_date - self.start_date).days

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "simulation_id": self.simulation_id,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "starting_capital": float(self.starting_capital),
            "ending_capital": float(self.ending_capital),
            "result": float(self.result) if self.result else None,
            "return_percent": float(self.return_percent) if self.return_percent else None,
            "max_drawdown": float(self.max_drawdown) if self.max_drawdown else None,
            "total_trades": self.total_trades,
            "win_rate": float(self.win_rate) if self.win_rate else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
