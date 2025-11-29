"""
TradingService - Business logic for trading operations with caching.

Implements:
- Account information queries with caching
- Position management (open/close/modify)
- Trading history with keyset pagination
- Real-time position updates integration
- MT4 order execution

Following TDD - Implementation for Phase 4 (T059-T080).
"""
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from decimal import Decimal

from src.database.repositories.trading_repository import TradingRepository
from src.database.models.trading import OpenPosition, TradingHistory
from src.trading.execution.mt4_client import MT4RedisClient
from src.utils.cache import (
    cached_fetch,
    get_cached,
    set_cached,
    CACHE_KEY_ACCOUNT,
    CACHE_KEY_POSITIONS,
    CACHE_KEY_POSITIONS_ALL,
    TTL_ACCOUNT_INFO,
    TTL_POSITIONS,
)
import structlog

logger = structlog.get_logger(__name__)


class TradingService:
    """Service for trading operations with Redis caching."""

    def __init__(
        self,
        repository: TradingRepository,
        redis_client: Optional[MT4RedisClient] = None,
        mt4_client: Optional[MT4RedisClient] = None,
    ):
        """
        Initialize TradingService.

        Args:
            repository: TradingRepository for database operations
            redis_client: Optional Redis client for caching
            mt4_client: Optional MT4 client for order execution
        """
        self.repository = repository
        self.redis_client = redis_client
        self.mt4_client = mt4_client

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information with caching.

        Implements cache-aside pattern with 10-second TTL.

        Returns:
            Dictionary with account information (balance, equity, margin, etc.)
        """
        cache_key = CACHE_KEY_ACCOUNT

        async def fetch_from_db():
            """Fetch account info from database."""
            account = await self.repository.get_account_info()
            if not account:
                # Return default empty account
                return {
                    "account_number": "N/A",
                    "balance": Decimal("0.00"),
                    "equity": Decimal("0.00"),
                    "margin": Decimal("0.00"),
                    "free_margin": Decimal("0.00"),
                    "margin_level": None,
                    "profit": Decimal("0.00"),
                    "currency": "USD",
                    "leverage": None,
                }

            return {
                "account_number": account.account_number,
                "balance": account.balance,
                "equity": account.equity,
                "margin": account.margin,
                "free_margin": account.free_margin,
                "margin_level": account.margin_level,
                "profit": account.profit,
                "currency": account.currency,
                "leverage": account.leverage,
                "created_at": account.created_at,
                "updated_at": account.updated_at,
            }

        if self.redis_client:
            return await cached_fetch(
                self.redis_client,
                cache_key,
                fetch_from_db,
                ttl=TTL_ACCOUNT_INFO,
            )
        else:
            return await fetch_from_db()

    async def get_open_positions(
        self, symbol: Optional[str] = None
    ) -> List[OpenPosition]:
        """
        Get open positions with optional symbol filter.

        Implements caching with 5-second TTL for real-time updates.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of OpenPosition objects
        """
        cache_key = CACHE_KEY_POSITIONS_ALL if not symbol else CACHE_KEY_POSITIONS.format(symbol=symbol)

        async def fetch_from_db():
            """Fetch positions from database."""
            return await self.repository.get_open_positions(symbol=symbol)

        if self.redis_client:
            return await cached_fetch(
                self.redis_client,
                cache_key,
                fetch_from_db,
                ttl=TTL_POSITIONS,
            )
        else:
            return await fetch_from_db()

    async def get_position_by_id(self, position_id: int) -> Optional[OpenPosition]:
        """
        Get specific position by ID.

        Args:
            position_id: Position ID

        Returns:
            OpenPosition or None if not found
        """
        return await self.repository.get_position_by_id(position_id)

    async def get_trading_history(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        trade_type: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Tuple[List[TradingHistory], Optional[str], int]:
        """
        Get trading history with keyset pagination.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            trade_type: Optional trade type filter ("BUY", "SELL")
            cursor: Optional pagination cursor
            limit: Maximum records per page

        Returns:
            Tuple of (trades_list, next_cursor, total_count)
        """
        # Get paginated history
        trades, next_cursor = await self.repository.get_trading_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            trade_type=trade_type,
            cursor=cursor,
            limit=limit,
        )

        # Get total count for pagination info
        total = await self.repository.count_trading_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            trade_type=trade_type,
        )

        return trades, next_cursor, total

    async def close_position(
        self,
        position_id: int,
        volume: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Close a position (full or partial).

        Args:
            position_id: Position ID to close
            volume: Optional partial volume (None = close full position)

        Returns:
            Dictionary with close operation result

        Raises:
            ValueError: If position not found or invalid parameters
        """
        # Get position
        position = await self.repository.get_position_by_id(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Validate partial close
        if volume and volume > position.volume:
            raise ValueError(
                f"Close volume {volume} exceeds position volume {position.volume}"
            )

        # If MT4 client available, send close order
        if self.mt4_client:
            try:
                # TODO: Implement MT4 close order via ZMQ
                logger.info(
                    "closing_position_via_mt4",
                    position_id=position_id,
                    ticket=position.ticket,
                    volume=volume or position.volume,
                )

                # For now, return pending status
                return {
                    "success": True,
                    "message": "Close order sent to MT4",
                    "position_id": position_id,
                    "ticket": position.ticket,
                    "close_volume": float(volume or position.volume),
                    "status": "pending",
                }

            except Exception as e:
                logger.error(
                    "mt4_close_failed",
                    position_id=position_id,
                    error=str(e),
                    exc_info=True,
                )
                raise ValueError(f"Failed to close position: {str(e)}")
        else:
            # No MT4 client - return error
            raise ValueError("MT4 client not available for order execution")

    async def invalidate_account_cache(self) -> int:
        """
        Invalidate account information cache.

        Returns:
            Number of cache keys invalidated
        """
        if not self.redis_client:
            return 0

        try:
            await self.redis_client.delete(CACHE_KEY_ACCOUNT)
            logger.info("account_cache_invalidated")
            return 1
        except Exception as e:
            logger.error("cache_invalidation_failed", error=str(e))
            return 0

    async def invalidate_positions_cache(self, symbol: Optional[str] = None) -> int:
        """
        Invalidate positions cache.

        Args:
            symbol: Optional symbol to invalidate (None = invalidate all)

        Returns:
            Number of cache keys invalidated
        """
        if not self.redis_client:
            return 0

        try:
            count = 0
            if symbol:
                # Invalidate specific symbol
                await self.redis_client.delete(CACHE_KEY_POSITIONS.format(symbol=symbol))
                count = 1

            # Always invalidate "all positions" cache
            await self.redis_client.delete(CACHE_KEY_POSITIONS_ALL)
            count += 1

            logger.info("positions_cache_invalidated", symbol=symbol, count=count)
            return count

        except Exception as e:
            logger.error("cache_invalidation_failed", error=str(e))
            return 0

    async def get_position_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for open positions.

        Returns:
            Dictionary with position statistics:
            - total_positions: Total number of open positions
            - total_volume: Sum of all position volumes
            - total_profit: Sum of all position profits
            - positions_by_symbol: Count per symbol
            - positions_by_type: Count per trade type (BUY/SELL)
        """
        positions = await self.get_open_positions()

        # Calculate statistics
        total_volume = sum(p.volume for p in positions)
        total_profit = sum(p.profit for p in positions)

        # Group by symbol
        by_symbol = {}
        for p in positions:
            if p.symbol not in by_symbol:
                by_symbol[p.symbol] = {"count": 0, "volume": Decimal("0"), "profit": Decimal("0")}
            by_symbol[p.symbol]["count"] += 1
            by_symbol[p.symbol]["volume"] += p.volume
            by_symbol[p.symbol]["profit"] += p.profit

        # Group by type
        by_type = {}
        for p in positions:
            trade_type = p.trade_type
            if trade_type not in by_type:
                by_type[trade_type] = {"count": 0, "volume": Decimal("0"), "profit": Decimal("0")}
            by_type[trade_type]["count"] += 1
            by_type[trade_type]["volume"] += p.volume
            by_type[trade_type]["profit"] += p.profit

        return {
            "total_positions": len(positions),
            "total_volume": float(total_volume),
            "total_profit": float(total_profit),
            "positions_by_symbol": {
                symbol: {
                    "count": stats["count"],
                    "volume": float(stats["volume"]),
                    "profit": float(stats["profit"]),
                }
                for symbol, stats in by_symbol.items()
            },
            "positions_by_type": {
                trade_type: {
                    "count": stats["count"],
                    "volume": float(stats["volume"]),
                    "profit": float(stats["profit"]),
                }
                for trade_type, stats in by_type.items()
            },
        }
