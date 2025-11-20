"""
Trading history model.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class TradingHistory(Base, TimestampMixin):
    """
    Trading history table storing completed trades.

    Contains full trade history with P&L tracking.
    """

    __tablename__ = "trading_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    order_type: Mapped[str] = mapped_column(Text, nullable=False)  # ordertype enum
    volume: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    # Risk parameters
    sl: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)  # Stop loss
    tp: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)  # Take profit

    # Costs and P&L
    commission: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    swap: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    profit: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Trade metadata
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # actiontype enum
    position_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    days_in_trade: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Simulation flag
    simulation: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)

    __table_args__ = (
        Index("ix_trading_history_time", "time"),
        Index("ix_trading_history_symbol", "symbol"),
        Index("ix_trading_history_symbol_time", "symbol", "time"),
    )

    def __repr__(self) -> str:
        return (
            f"<TradingHistory(id={self.id}, symbol='{self.symbol}', "
            f"order_type='{self.order_type}', time={self.time}, "
            f"profit={self.profit})>"
        )

    @property
    def net_profit(self) -> Optional[Decimal]:
        """Calculate net profit after commission and swap."""
        if self.profit is None:
            return None
        commission = self.commission or Decimal(0)
        swap = self.swap or Decimal(0)
        return self.profit - commission - swap

    @property
    def is_profitable(self) -> Optional[bool]:
        """Check if trade was profitable."""
        if self.profit is None:
            return None
        return self.profit > 0

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "time": self.time.isoformat() if self.time else None,
            "symbol": self.symbol,
            "order_type": self.order_type,
            "volume": float(self.volume),
            "price": float(self.price),
            "sl": float(self.sl) if self.sl else None,
            "tp": float(self.tp) if self.tp else None,
            "commission": float(self.commission) if self.commission else None,
            "swap": float(self.swap) if self.swap else None,
            "profit": float(self.profit) if self.profit else None,
            "action": self.action,
            "position_id": self.position_id,
            "order_number": self.order_number,
            "days_in_trade": float(self.days_in_trade) if self.days_in_trade else None,
            "simulation": self.simulation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
