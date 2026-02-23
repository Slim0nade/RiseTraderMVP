"""
Shared MarketTick dataclass — imported by strategies and backtesting engine.

Kept in a standalone module to avoid circular imports between
  src.strategies.* → src.services.backtesting.data_replay_engine
  src.services.backtesting.__init__ → synthetic_engine → src.strategies.*
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class MarketTick:
    """
    Simplified market data tick for backtesting.

    Attributes:
        symbol: Trading symbol
        timestamp: Tick timestamp
        open: Open price
        high: High price
        low: Low price
        close: Close price
        volume: Volume
    """

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @classmethod
    def from_market_data(cls, md) -> "MarketTick":
        """
        Create MarketTick from MarketData model.

        Args:
            md: MarketData instance

        Returns:
            MarketTick instance
        """
        return cls(
            symbol=md.symbol,
            timestamp=md.time,
            open=md.open,
            high=md.high,
            low=md.low,
            close=md.last,
            volume=int(md.volume or 0),
        )
