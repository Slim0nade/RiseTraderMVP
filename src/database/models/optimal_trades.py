"""
Optimal trades model.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Interval, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class OptimalTrade(Base, TimestampMixin):
    """
    Optimal trades table storing backtest trade results.

    Contains ~8,171 records of simulated trades.
    """

    __tablename__ = "optimal_trades"

    trade_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trading_simulation.simulation_id", ondelete="CASCADE"),
        nullable=True
    )

    # Trade timing
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Trade details
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    trade_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., 'LONG', 'SHORT'
    position_type: Mapped[str] = mapped_column(String, nullable=False)

    # Market data references
    entry_market_data_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exit_market_data_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Prices
    entry_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    exit_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    # Trade metrics
    trade_duration: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    return_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    return_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    simulation: Mapped[Optional["TradingSimulation"]] = relationship(
        "TradingSimulation",
        back_populates="optimal_trades",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<OptimalTrade(id={self.trade_id}, symbol='{self.symbol}', "
            f"type='{self.trade_type}', entry={self.entry_price}, "
            f"exit={self.exit_price}, return={self.return_percent}%)>"
        )

    @property
    def is_profitable(self) -> bool:
        """Check if trade was profitable."""
        if self.return_amount is None:
            return False
        return self.return_amount > 0

    @property
    def duration_hours(self) -> Optional[float]:
        """Get trade duration in hours."""
        if self.trade_duration is None:
            return None
        return self.trade_duration.total_seconds() / 3600

    @property
    def price_change_percent(self) -> Decimal:
        """Calculate price change percentage."""
        if self.entry_price == 0:
            return Decimal(0)
        return ((self.exit_price - self.entry_price) / self.entry_price) * 100

    def calculate_returns(self, volume: Optional[Decimal] = None) -> None:
        """
        Calculate return amount and percentage.

        Args:
            volume: Trading volume (defaults to 1 if not provided)
        """
        vol = volume or self.volume or Decimal(1)

        # Calculate price difference
        price_diff = self.exit_price - self.entry_price

        # Adjust for trade type (short positions profit from price drops)
        if self.trade_type.upper() == "SHORT":
            price_diff = -price_diff

        # Calculate returns
        self.return_amount = price_diff * vol
        if self.entry_price != 0:
            self.return_percent = (price_diff / self.entry_price) * 100

        # Calculate duration
        self.trade_duration = self.exit_time - self.entry_time

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "trade_id": self.trade_id,
            "simulation_id": self.simulation_id,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "symbol": self.symbol,
            "trade_type": self.trade_type,
            "position_type": self.position_type,
            "entry_market_data_id": self.entry_market_data_id,
            "exit_market_data_id": self.exit_market_data_id,
            "entry_price": float(self.entry_price),
            "exit_price": float(self.exit_price),
            "trade_duration": str(self.trade_duration) if self.trade_duration else None,
            "return_amount": (
                float(self.return_amount) if self.return_amount else None
            ),
            "return_percent": (
                float(self.return_percent) if self.return_percent else None
            ),
            "volume": self.volume,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
