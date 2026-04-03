"""
Market data model - OHLCV time-series data.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class MarketData(Base, TimestampMixin):
    """
    Market data table storing OHLCV tick data.

    Contains 13.5M+ records with multiple timeframes and symbols.
    Optimized with indexes for time-series queries.
    """

    __tablename__ = "market_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    import_symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(ENUM('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'MN1', name='timeframe', create_type=False), nullable=False)
    source: Mapped[str] = mapped_column(ENUM('BARCHART', 'MT4', 'BC', 'CSV', 'DUKASCOPY', 'HISTDATA', 'TWELVEDATA', name='datasource', create_type=False), nullable=False)

    # OHLCV data
    open: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    last: Mapped[Decimal] = mapped_column(Numeric, nullable=False)  # Close price

    # Change metrics
    change: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    change_percent: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    # Volume
    volume: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    indicators: Mapped[list["Indicators"]] = relationship(
        "Indicators",
        back_populates="market_data",
        lazy="noload"  # Don't auto-load indicators (performance)
    )

    __table_args__ = (
        UniqueConstraint(
            "time", "source", "timeframe", "symbol",
            name="unique_time_source_timeframe_symbol"
        ),
        Index("ix_market_data_time", "time"),
        Index("ix_market_data_symbol", "symbol"),
        Index("ix_market_data_timeframe", "timeframe"),
        Index("ix_market_data_source", "source"),
        Index("ix_market_data_import_symbol", "import_symbol"),
        # Composite index for common queries
        Index("ix_market_data_symbol_timeframe_time", "symbol", "timeframe", "time"),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketData(id={self.id}, symbol='{self.symbol}', "
            f"timeframe='{self.timeframe}', time={self.time}, last={self.last})>"
        )

    @property
    def close(self) -> Decimal:
        """Alias for 'last' field to match common naming convention."""
        return self.last

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "time": self.time.isoformat() if self.time else None,
            "symbol": self.symbol,
            "import_symbol": self.import_symbol,
            "timeframe": self.timeframe,
            "source": self.source,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.last),
            "change": float(self.change),
            "change_percent": float(self.change_percent),
            "volume": self.volume,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
