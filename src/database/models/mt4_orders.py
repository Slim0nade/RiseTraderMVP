"""
MT4 Order model for tracking order lifecycle.

Tracks orders from submission to execution/rejection with full audit trail.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Index, Integer,
    Numeric, String, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin


class MT4Order(Base, TimestampMixin):
    """
    Order lifecycle tracking.

    Tracks orders from submission through confirmation to execution or rejection.
    Supports market orders, limit orders, and stop orders.
    """

    __tablename__ = "mt4_orders"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # External Reference
    order_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        comment="External UUID for API/agent reference"
    )

    # Connection Reference
    magic_number: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('mt4_connections.magic_number', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="References mt4_connections.magic_number"
    )

    # MT4 Reference
    ticket_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        unique=True,
        nullable=True,
        index=True,
        comment="MT4 ticket number (NULL until confirmed)"
    )

    # Order Details
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol (e.g., 'CrudeOIL')"
    )

    direction: Mapped[str] = mapped_column(
        Enum('BUY', 'SELL', name='order_direction'),
        nullable=False,
        comment="Order direction"
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Order volume in lots"
    )

    order_type: Mapped[str] = mapped_column(
        Enum(
            'MARKET', 'LIMIT', 'STOP',
            'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP',
            name='order_type'
        ),
        nullable=False,
        comment="Order type"
    )

    # Prices
    limit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 5),
        nullable=True,
        comment="Limit price for pending orders"
    )

    stop_loss: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 5),
        nullable=True,
        comment="Stop loss price"
    )

    take_profit: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 5),
        nullable=True,
        comment="Take profit price"
    )

    execution_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 5),
        nullable=True,
        comment="Actual execution price"
    )

    # Risk Management
    required_margin: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Estimated margin requirement"
    )

    # Status Tracking
    status: Mapped[str] = mapped_column(
        Enum(
            'PENDING', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED',
            name='order_status'
        ),
        nullable=False,
        index=True,
        comment="Order status"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if rejected"
    )

    # Timestamps
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="When order was submitted to MT4"
    )

    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When MT4 confirmed receipt"
    )

    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When order was filled"
    )

    # Tracing
    correlation_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="UUID for tracing across services"
    )

    # Relationships
    connection = relationship(
        "MT4Connection",
        back_populates="orders",
        foreign_keys=[magic_number]
    )

    position = relationship(
        "MT4Position",
        uselist=False,
        back_populates="order",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index('idx_mt4_order_magic', 'magic_number'),
        Index('idx_mt4_order_ticket', 'ticket_number'),
        Index('idx_mt4_order_status', 'status'),
        Index('idx_mt4_order_correlation', 'correlation_id'),
        Index('idx_mt4_order_submitted', 'submitted_at'),
    )

    @validates('volume')
    def validate_volume(self, key, value):
        """Validate order volume is positive."""
        if value <= 0:
            raise ValueError(f"Order volume must be positive, got {value}")
        return value

    @validates('direction')
    def validate_direction(self, key, value):
        """Validate order direction."""
        if value not in ['BUY', 'SELL']:
            raise ValueError(f"Direction must be BUY or SELL, got {value}")
        return value

    @validates('status')
    def validate_status(self, key, value):
        """Validate order status."""
        valid_statuses = ['PENDING', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED']
        if value not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}, got {value}")
        return value

    def is_active(self) -> bool:
        """Check if order is in an active state."""
        return self.status in ['PENDING', 'CONFIRMED']

    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in ['EXECUTED', 'REJECTED', 'CANCELLED']

    def calculate_latency_ms(self) -> Optional[float]:
        """
        Calculate order confirmation latency in milliseconds.

        Returns:
            Latency in ms if confirmed, None otherwise
        """
        if self.confirmed_at is None:
            return None

        delta = self.confirmed_at - self.submitted_at
        return delta.total_seconds() * 1000

    def __repr__(self) -> str:
        return (
            f"<MT4Order(order_id='{self.order_id}', "
            f"ticket={self.ticket_number}, "
            f"symbol='{self.symbol}', "
            f"direction='{self.direction}', "
            f"volume={self.volume}, "
            f"status='{self.status}')>"
        )
