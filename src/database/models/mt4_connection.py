"""
MT4 Connection model for Expert Advisor registry.

Tracks EA connections, encryption keys, and connection health.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin


class MT4Connection(Base, TimestampMixin):
    """
    Expert Advisor (EA) connection registry.

    Tracks MT4 EA connections with encryption configuration and health monitoring.
    Each EA has a unique magic number and port allocation for command/stream sockets.
    """

    __tablename__ = "mt4_connections"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # EA Identification
    ea_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Human-readable EA identifier (e.g., 'crude_oil_ea_1')"
    )

    magic_number: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="MT4 magic number for order attribution (100000-999999)"
    )

    # Connection Configuration
    rep_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="ZMQ REP socket port for commands"
    )

    pub_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="ZMQ PUB socket port for streaming"
    )

    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Primary trading symbol for this EA"
    )

    status: Mapped[str] = mapped_column(
        Enum('ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING', name='connection_status'),
        nullable=False,
        index=True,
        comment="Connection status"
    )

    mt4_server_host: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default='75.154.254.174',
        comment="MT4 server IP/hostname"
    )

    # Encryption Configuration
    encryption_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether CurveZMQ encryption is enabled"
    )

    client_public_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Z85-encoded client public key"
    )

    server_public_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Z85-encoded server public key"
    )

    # Health Monitoring
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful ping/pong timestamp"
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Consecutive error count for health monitoring"
    )

    # Relationships
    orders = relationship(
        "MT4Order",
        back_populates="connection",
        foreign_keys="[MT4Order.magic_number]",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index('idx_mt4_connection_magic', 'magic_number'),
        Index('idx_mt4_connection_status', 'status'),
        Index('idx_mt4_connection_ea_id', 'ea_id'),
    )

    @validates('magic_number')
    def validate_magic_number(self, key, value):
        """Validate magic number is in valid range."""
        if not (100000 <= value <= 999999):
            raise ValueError(
                f"Magic number must be between 100000 and 999999, got {value}"
            )
        return value

    @validates('rep_port', 'pub_port')
    def validate_ports(self, key, value):
        """Validate port numbers are in valid range."""
        if not (5000 <= value <= 65535):
            raise ValueError(
                f"{key} must be between 5000 and 65535, got {value}"
            )
        return value

    @validates('status')
    def validate_status(self, key, value):
        """Validate connection status."""
        valid_statuses = ['ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING']
        if value not in valid_statuses:
            raise ValueError(
                f"Status must be one of {valid_statuses}, got {value}"
            )
        return value

    def is_healthy(self, heartbeat_timeout_seconds: int = 90) -> bool:
        """
        Check if connection is healthy based on heartbeat.

        Args:
            heartbeat_timeout_seconds: Maximum seconds since last heartbeat

        Returns:
            True if connection is healthy, False otherwise
        """
        if self.status != 'ACTIVE':
            return False

        if self.last_heartbeat is None:
            return False

        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return elapsed < heartbeat_timeout_seconds

    def __repr__(self) -> str:
        return (
            f"<MT4Connection(ea_id='{self.ea_id}', "
            f"magic={self.magic_number}, status='{self.status}')>"
        )
