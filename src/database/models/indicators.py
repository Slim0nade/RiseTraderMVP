"""
Technical indicators model.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Indicators(Base):
    """
    Technical indicators table storing calculated indicator values.

    Contains ~70K records of indicators like RSI, MACD, ATR, etc.
    Linked to market_data via foreign key.
    """

    __tablename__ = "indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_data_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("market_data.id", ondelete="CASCADE"),
        nullable=True
    )
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)

    # Momentum indicators
    rsi: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Trend indicators
    macd: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    macd_signal: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Volatility indicators
    atr: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Parabolic SAR
    sar: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Bollinger Bands
    bb_upper: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    bb_middle: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    bb_lower: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Moving Averages
    ma_20: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    ma_50: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    ma_200: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Volume indicators
    vwap: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Fibonacci levels
    fib_236: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    fib_382: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    fib_500: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    fib_618: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    fib_786: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    fib_high: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    fib_low: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Timestamp
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=True
    )

    # Relationships
    market_data: Mapped[Optional["MarketData"]] = relationship(
        "MarketData",
        back_populates="indicators",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Indicators(id={self.id}, symbol='{self.symbol}', "
            f"time={self.time}, rsi={self.rsi})>"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "market_data_id": self.market_data_id,
            "time": self.time.isoformat() if self.time else None,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "rsi": float(self.rsi) if self.rsi else None,
            "macd": float(self.macd) if self.macd else None,
            "macd_signal": float(self.macd_signal) if self.macd_signal else None,
            "atr": float(self.atr) if self.atr else None,
            "sar": float(self.sar) if self.sar else None,
            "bb_upper": float(self.bb_upper) if self.bb_upper else None,
            "bb_middle": float(self.bb_middle) if self.bb_middle else None,
            "bb_lower": float(self.bb_lower) if self.bb_lower else None,
            "ma_20": float(self.ma_20) if self.ma_20 else None,
            "ma_50": float(self.ma_50) if self.ma_50 else None,
            "ma_200": float(self.ma_200) if self.ma_200 else None,
            "vwap": float(self.vwap) if self.vwap else None,
            "fib_236": float(self.fib_236) if self.fib_236 else None,
            "fib_382": float(self.fib_382) if self.fib_382 else None,
            "fib_500": float(self.fib_500) if self.fib_500 else None,
            "fib_618": float(self.fib_618) if self.fib_618 else None,
            "fib_786": float(self.fib_786) if self.fib_786 else None,
            "fib_high": float(self.fib_high) if self.fib_high else None,
            "fib_low": float(self.fib_low) if self.fib_low else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
