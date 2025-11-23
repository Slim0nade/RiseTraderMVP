"""
Symbol Loader for dynamic symbol validation.

Fetches available symbols from MT4 and validates order parameters.
"""
import asyncio
from decimal import Decimal
from typing import List, Literal, Optional

from src.utils.mt4_helpers import get_mt4_logger

logger = get_mt4_logger("symbol_loader")


class SymbolLoader:
    """
    Dynamic symbol loader and validator.

    Fetches available symbols from MT4 and caches them for validation.
    Validates order parameters (volume, direction) independently of symbols.
    """

    def __init__(self):
        """Initialize symbol loader with empty cache."""
        self._symbols: List[str] = []
        self._lock = asyncio.Lock()

        logger.info("symbol_loader_initialized")

    async def refresh_symbols(self, mt4_client) -> None:
        """
        Refresh available symbols from MT4.

        Args:
            mt4_client: MT4Client instance to fetch symbols from

        Raises:
            ConnectionError: If unable to fetch symbols
        """
        async with self._lock:
            try:
                symbols = await mt4_client.get_symbols()

                # Remove duplicates and sort
                unique_symbols = list(set(symbols))
                unique_symbols.sort()

                self._symbols = unique_symbols

                logger.info(
                    "symbols_refreshed",
                    count=len(self._symbols),
                    symbols=self._symbols[:20]  # Log first 20
                )

            except Exception as e:
                logger.error(
                    "symbol_refresh_failed",
                    error=str(e)
                )
                raise

    def get_symbols(self) -> List[str]:
        """
        Get cached symbol list.

        Returns:
            Copy of cached symbol list
        """
        return self._symbols.copy()

    def is_valid_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is in cached list.

        Args:
            symbol: Symbol name to validate

        Returns:
            True if symbol is valid (cached)
        """
        return symbol in self._symbols

    def validate_volume(self, volume: Decimal) -> None:
        """
        Validate order volume.

        Args:
            volume: Order volume in lots

        Raises:
            ValueError: If volume is invalid
        """
        # Volume must be positive
        if volume <= 0:
            raise ValueError("Volume must be positive")

        # Volume too small (< 0.001)
        if volume < Decimal("0.001"):
            raise ValueError("Volume too small (minimum 0.001 lots)")

        # Volume too large (> 100.0)
        if volume > Decimal("100.0"):
            raise ValueError("Volume too large (maximum 100.0 lots)")

        logger.debug("volume_validated", volume=float(volume))

    def validate_direction(self, direction: str) -> None:
        """
        Validate order direction.

        Args:
            direction: Order direction (BUY or SELL)

        Raises:
            ValueError: If direction is invalid
        """
        if direction not in ["BUY", "SELL"]:
            raise ValueError("Direction must be BUY or SELL")

        logger.debug("direction_validated", direction=direction)

    def validate_order(
        self,
        symbol: str,
        direction: str,
        volume: Decimal
    ) -> None:
        """
        Validate all order parameters.

        Args:
            symbol: Trading symbol
            direction: Order direction (BUY or SELL)
            volume: Order volume in lots

        Raises:
            ValueError: If any parameter is invalid
        """
        # Validate symbol
        if not self.is_valid_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        # Validate direction
        self.validate_direction(direction)

        # Validate volume
        self.validate_volume(volume)

        logger.debug(
            "order_validated",
            symbol=symbol,
            direction=direction,
            volume=float(volume)
        )
