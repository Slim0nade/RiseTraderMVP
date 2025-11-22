"""
MT4 Position model for tracking open positions.

Tracks open positions with real-time P&L updates from MT4.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Index, Integer,
    Numeric, String
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin


class MT4Position(Base, TimestampMixin):
    """
    Open position tracking.

    Represents currently open positions in MT4 with P&L tracking.
    Updated in real-time via position_updated events from MT4.
    """

    __tablename__ = "mt4_positions"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # Order Reference (optional - position might be manually opened in MT4)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('mt4_orders.id', ondelete='SET NULL'),
        nullable=True,
        comment="References mt4_orders.id (NULL for manual positions)"
    )

    # MT4 References
    ticket_number: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="MT4 position ticket"
    )

    magic_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="Magic number identifying EA"
    )

    # Position Details
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Trading symbol"
    )

    direction: Mapped[str] = mapped_column(
        Enum('BUY', 'SELL', name='position_direction'),
        nullable=False,
        comment="Position direction"
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Position size in lots"
    )

    # Pricing
    open_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 5),
        nullable=False,
        comment="Position open price"
    )

    current_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 5),
        nullable=False,
        comment="Current market price (updated real-time)"
    )

    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Current unrealized P&L"
    )

    # Risk Management
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 5),
        nullable=True,
        comment="Stop loss level"
    )

    take_profit: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 5),
        nullable=True,
        comment="Take profit level"
    )

    # Timestamps
    open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When position was opened"
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last price update time"
    )

    # Relationships
    order = relationship(
        "MT4Order",
        back_populates="position",
        foreign_keys=[order_id]
    )

    # Indexes
    __table_args__ = (
        Index('idx_mt4_position_ticket', 'ticket_number'),
        Index('idx_mt4_position_magic', 'magic_number'),
        Index('idx_mt4_position_symbol', 'symbol'),
    )

    @validates('volume')
    def validate_volume(self, key, value):
        """Validate position volume is positive."""
        if value <= 0:
            raise ValueError(f"Position volume must be positive, got {value}")
        return value

    @validates('direction')
    def validate_direction(self, key, value):
        """Validate position direction."""
        if value not in ['BUY', 'SELL']:
            raise ValueError(f"Direction must be BUY or SELL, got {value}")
        return value

    def calculate_pnl(self, contract_size: Decimal = Decimal('1000')) -> Decimal:
        """
        Calculate P&L based on current price.

        Args:
            contract_size: Contract size for the symbol (default 1000 for CrudeOIL)

        Returns:
            Calculated P&L
        """
        price_diff = self.current_price - self.open_price

        if self.direction == 'SELL':
            price_diff = -price_diff

        return price_diff * self.volume * contract_size

    def is_profitable(self) -> bool:
        """Check if position is currently profitable."""
        return self.unrealized_pnl > 0

    def get_duration_seconds(self) -> float:
        """Get position duration in seconds."""
        return (datetime.utcnow() - self.open_time).total_seconds()

    def is_at_stop_loss(self, tolerance: Decimal = Decimal('0.0001')) -> bool:
        """
        Check if current price is at stop loss level.

        Args:
            tolerance: Price tolerance for matching

        Returns:
            True if at stop loss, False otherwise
        """
        if self.stop_loss is None:
            return False

        return abs(self.current_price - self.stop_loss) <= tolerance

    def is_at_take_profit(self, tolerance: Decimal = Decimal('0.0001')) -> bool:
        """
        Check if current price is at take profit level.

        Args:
            tolerance: Price tolerance for matching

        Returns:
            True if at take profit, False otherwise
        """
        if self.take_profit is None:
            return False

        return abs(self.current_price - self.take_profit) <= tolerance

    def __repr__(self) -> str:
        return (
            f"<MT4Position(ticket={self.ticket_number}, "
            f"symbol='{self.symbol}', "
            f"direction='{self.direction}', "
            f"volume={self.volume}, "
            f"pnl={self.unrealized_pnl})>"
        )
