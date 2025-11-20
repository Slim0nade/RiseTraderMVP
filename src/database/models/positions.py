"""
Open positions model.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class OpenPosition(Base, TimestampMixin):
    """
    Open positions table storing currently active trading positions.

    Contains ~1,130 records of open positions.
    """

    __tablename__ = "open_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # Order number
    type: Mapped[str] = mapped_column(Text, nullable=False)  # BUY or SELL (positiontype enum)
    size: Mapped[Decimal] = mapped_column(Numeric, nullable=False)  # Position size
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)  # Entry price

    # Risk management
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    take_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # P&L tracking
    commission: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    last_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Metadata
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_strategy: Mapped[str] = mapped_column(String, nullable=False)

    # Simulation flag
    simulation: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<OpenPosition(id={self.id}, number='{self.number}', "
            f"symbol='{self.symbol}', type='{self.type}', size={self.size}, "
            f"price={self.price})>"
        )

    @property
    def current_pnl(self) -> Optional[Decimal]:
        """Get current profit/loss."""
        return self.last_profit

    @property
    def is_long(self) -> bool:
        """Check if position is long (BUY)."""
        return self.type.upper() == "BUY"

    @property
    def is_short(self) -> bool:
        """Check if position is short (SELL)."""
        return self.type.upper() == "SELL"

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "number": self.number,
            "type": self.type,
            "size": float(self.size),
            "symbol": self.symbol,
            "price": float(self.price),
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "take_profit": float(self.take_profit) if self.take_profit else None,
            "commission": float(self.commission),
            "last_profit": float(self.last_profit) if self.last_profit else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "last_strategy": self.last_strategy,
            "simulation": self.simulation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
