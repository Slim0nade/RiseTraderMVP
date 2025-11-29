"""
MarketDataService - Business logic for market data retrieval with caching.

Implements:
- Cache-aside pattern for market data queries
- Redis caching with differentiated TTL strategy
- Symbol metadata aggregation
- Integration with MarketDataRepository

Following TDD - Implementation to make tests pass (T045-T048).
"""
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from decimal import Decimal

from src.database.repositories.market_data_repository import MarketDataRepository
from src.database.models.market_data import MarketData
from src.trading.execution.mt4_client import MT4RedisClient
from src.utils.cache import (
    cached_fetch,
    get_cached,
    set_cached,
    CACHE_KEY_PRICE_LATEST,
    CACHE_KEY_CHART,
    CACHE_KEY_SYMBOLS,
    TTL_PRICE_LATEST,
    TTL_CHART_DATA,
)


class MarketDataService:
    """Service for market data operations with Redis caching."""

    def __init__(
        self,
        repository: MarketDataRepository,
        redis_client: Optional[MT4RedisClient] = None,
    ):
        """
        Initialize MarketDataService.

        Args:
            repository: MarketDataRepository for database operations
            redis_client: Optional Redis client for caching (if None, caching disabled)
        """
        self.repository = repository
        self.redis_client = redis_client

    async def get_market_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[MarketData], Optional[str], int]:
        """
        Get latest market data for symbol with caching.

        Implements cache-aside pattern:
        1. Check cache for latest data
        2. On miss, fetch from database
        3. Cache the result with TTL_PRICE_LATEST (5 seconds)

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL")
            timeframe: Timeframe (e.g., "M5", "H1")
            limit: Maximum number of records to return
            cursor: Optional cursor for keyset pagination

        Returns:
            Tuple of (data_list, next_cursor, total_count)
        """
        # If using cursor pagination, skip cache and go direct to DB
        if cursor:
            data, next_cursor = await self.repository.get_latest_by_symbol(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                cursor=cursor,
            )
            total = await self.repository.count_by_symbol(symbol, timeframe)
            return data, next_cursor, total

        # Try cache first for non-paginated request
        cache_key = CACHE_KEY_PRICE_LATEST.format(symbol=symbol)

        async def fetch_from_db():
            """Fetch data from database."""
            data, next_cursor = await self.repository.get_latest_by_symbol(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
            total = await self.repository.count_by_symbol(symbol, timeframe)
            return {"data": data, "next_cursor": next_cursor, "total": total}

        if self.redis_client:
            result = await cached_fetch(
                self.redis_client,
                cache_key,
                fetch_from_db,
                ttl=TTL_PRICE_LATEST,
            )
        else:
            # No caching, fetch directly
            result = await fetch_from_db()

        return result["data"], result["next_cursor"], result["total"]

    async def get_market_data_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        cursor: Optional[str] = None,
        limit: int = 500,
    ) -> Tuple[List[MarketData], Optional[str], int]:
        """
        Get market data for time range with caching.

        Historical data is cached longer (TTL_CHART_DATA = 1 hour) since it's immutable.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start: Start time for range query
            end: End time for range query
            cursor: Optional cursor for pagination
            limit: Maximum records per page

        Returns:
            Tuple of (data_list, next_cursor, total_count)
        """
        # Build cache key including time range
        cache_key = CACHE_KEY_CHART.format(
            symbol=symbol,
            timeframe=timeframe,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        async def fetch_from_db():
            """Fetch range data from database."""
            data, next_cursor = await self.repository.get_by_time_range(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                cursor=cursor,
                limit=limit,
            )
            total = await self.repository.count_by_time_range(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            return {"data": data, "next_cursor": next_cursor, "total": total}

        if self.redis_client and not cursor:
            # Cache only first page (non-cursor requests)
            result = await cached_fetch(
                self.redis_client,
                cache_key,
                fetch_from_db,
                ttl=TTL_CHART_DATA,
            )
        else:
            # No caching for paginated requests
            result = await fetch_from_db()

        return result["data"], result["next_cursor"], result["total"]

    async def get_symbols(
        self, timeframe: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get list of available symbols with metadata.

        Aggregates metadata for each symbol:
        - Total data points count
        - First/last timestamp
        - Latest price (if available)

        Args:
            timeframe: Optional timeframe filter

        Returns:
            List of symbol info dictionaries
        """
        cache_key = CACHE_KEY_SYMBOLS
        if timeframe:
            cache_key = f"{CACHE_KEY_SYMBOLS}:{timeframe}"

        async def fetch_from_db():
            """Fetch symbols with metadata from database."""
            symbols_data = await self.repository.get_symbols_with_metadata(
                timeframe=timeframe
            )

            # Convert to dict format for API response
            symbols_list = []
            for symbol_info in symbols_data:
                symbol_dict = {
                    "symbol": symbol_info.symbol,
                    "data_points_count": symbol_info.data_points_count or 0,
                }

                # Add optional fields if available
                if hasattr(symbol_info, "latest_price") and symbol_info.latest_price:
                    symbol_dict["latest_price"] = symbol_info.latest_price
                if hasattr(symbol_info, "latest_time") and symbol_info.latest_time:
                    symbol_dict["latest_time"] = symbol_info.latest_time
                if hasattr(symbol_info, "first_time") and symbol_info.first_time:
                    symbol_dict["first_time"] = symbol_info.first_time
                if hasattr(symbol_info, "last_time") and symbol_info.last_time:
                    symbol_dict["last_time"] = symbol_info.last_time
                if hasattr(symbol_info, "description") and symbol_info.description:
                    symbol_dict["description"] = symbol_info.description

                symbols_list.append(symbol_dict)

            return symbols_list

        if self.redis_client:
            return await cached_fetch(
                self.redis_client,
                cache_key,
                fetch_from_db,
                ttl=TTL_CHART_DATA,  # 1 hour TTL for symbols list
            )
        else:
            return await fetch_from_db()

    async def invalidate_cache(self, symbol: str, timeframe: str) -> int:
        """
        Invalidate cached data for symbol/timeframe.

        Called when new market data arrives to ensure cache consistency.

        Args:
            symbol: Symbol to invalidate
            timeframe: Timeframe to invalidate

        Returns:
            Number of cache keys invalidated
        """
        if not self.redis_client:
            return 0

        from src.utils.cache import invalidate_market_data_cache

        return await invalidate_market_data_cache(
            self.redis_client, symbol, timeframe
        )
