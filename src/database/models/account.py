"""
Account info model.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AccountInfo(Base, TimestampMixin):
    """
    Account info table storing trading account state.

    Contains snapshots of account balance, equity, and margin.
    """

    __tablename__ = "account_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Account metrics
    balance: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    margin: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    free_margin: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    margin_level: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    __table_args__ = (Index("ix_account_info_time", "time"),)

    def __repr__(self) -> str:
        return (
            f"<AccountInfo(id={self.id}, time={self.time}, "
            f"balance={self.balance}, equity={self.equity}, "
            f"margin_level={self.margin_level}%)>"
        )

    @property
    def unrealized_pnl(self) -> Decimal:
        """Calculate unrealized P&L (equity - balance)."""
        return self.equity - self.balance

    @property
    def used_margin_percent(self) -> Optional[Decimal]:
        """Calculate used margin as percentage of equity."""
        if self.equity == 0:
            return None
        return (self.margin / self.equity) * 100

    @property
    def is_margin_call_risk(self) -> bool:
        """Check if account is at risk of margin call (below 100%)."""
        return self.margin_level < 100

    @property
    def is_critical_margin(self) -> bool:
        """Check if margin level is critically low (below 50%)."""
        return self.margin_level < 50

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "time": self.time.isoformat() if self.time else None,
            "balance": float(self.balance),
            "equity": float(self.equity),
            "margin": float(self.margin),
            "free_margin": float(self.free_margin),
            "margin_level": float(self.margin_level),
            "unrealized_pnl": float(self.unrealized_pnl),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
