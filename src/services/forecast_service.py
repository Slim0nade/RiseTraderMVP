"""
Forecast service for ML prediction operations.

Handles business logic for forecast retrieval with Redis caching.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from decimal import Decimal

from sqlalchemy import desc, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.database.models.forecasts import Forecast
from src.database.repositories.forecasts_repository import ForecastsRepository
import structlog

logger = structlog.get_logger(__name__)


class ForecastService:
    """
    Service for forecast operations with caching.

    Implements cache-aside pattern with Redis for forecast data.
    Cache TTL: 1 hour (3600 seconds) for forecast data.
    """

    def __init__(self, session: AsyncSession, redis: Optional[Redis] = None):
        """
        Initialize forecast service.

        Args:
            session: Database session
            redis: Optional Redis client for caching
        """
        self.repository = ForecastsRepository(session)
        self.redis = redis
        self.cache_ttl = 3600  # 1 hour

    async def get_latest_forecasts(
        self,
        symbol: Optional[str] = None,
        horizon: Optional[str] = None
    ) -> List[Forecast]:
        """
        Get latest forecasts with optional filters.

        Checks cache first, falls back to database if cache miss.

        Args:
            symbol: Optional symbol filter
            horizon: Optional horizon filter (1h, 4h, 24h, etc.)

        Returns:
            List of Forecast instances
        """
        # Generate cache key
        cache_key = self._generate_cache_key("forecasts:latest", symbol=symbol, horizon=horizon)

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("forecast_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    # Convert back to Forecast objects
                    return self._deserialize_forecasts(data.get("forecasts", []))
            except Exception as e:
                logger.warning("forecast_cache_error", error=str(e), cache_key=cache_key)

        # Cache miss - fetch from database
        logger.info("forecast_cache_miss", cache_key=cache_key, symbol=symbol, horizon=horizon)

        query = select(Forecast).order_by(desc(Forecast.created_at))

        if symbol:
            query = query.where(Forecast.symbol == symbol)
        if horizon:
            query = query.where(Forecast.horizon == horizon)

        # Get latest forecast per symbol/horizon combination
        query = query.limit(100)  # Reasonable limit

        result = await self.repository.session.execute(query)
        forecasts = list(result.scalars().all())

        # Cache the results
        if self.redis and forecasts:
            try:
                cache_data = {
                    "forecasts": self._serialize_forecasts(forecasts),
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=self.cache_ttl
                )
                logger.info("forecast_cached", cache_key=cache_key, count=len(forecasts))
            except Exception as e:
                logger.warning("forecast_cache_write_error", error=str(e))

        return forecasts

    async def get_forecasts_by_symbol(
        self,
        symbol: str,
        cursor: Optional[str] = None,
        limit: int = 50
    ) -> Tuple[List[Forecast], Optional[str]]:
        """
        Get forecasts for a specific symbol with keyset pagination.

        Args:
            symbol: Trading symbol
            cursor: Pagination cursor (ISO timestamp)
            limit: Number of forecasts to return

        Returns:
            Tuple of (forecasts list, next_cursor)
        """
        # Generate cache key
        cache_key = self._generate_cache_key(
            f"forecasts:symbol:{symbol}",
            cursor=cursor,
            limit=limit
        )

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("forecast_symbol_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    return (
                        self._deserialize_forecasts(data.get("forecasts", [])),
                        data.get("next_cursor")
                    )
            except Exception as e:
                logger.warning("forecast_cache_error", error=str(e))

        # Build query with keyset pagination
        query = (
            select(Forecast)
            .where(Forecast.symbol == symbol)
            .order_by(desc(Forecast.created_at))
            .limit(limit + 1)  # Fetch one extra to determine if there's a next page
        )

        if cursor:
            # Parse cursor as timestamp
            try:
                cursor_time = datetime.fromisoformat(cursor.replace('Z', '+00:00'))
                query = query.where(Forecast.created_at < cursor_time)
            except (ValueError, AttributeError):
                logger.warning("invalid_cursor", cursor=cursor)

        result = await self.repository.session.execute(query)
        all_forecasts = list(result.scalars().all())

        # Determine next cursor
        has_more = len(all_forecasts) > limit
        forecasts = all_forecasts[:limit]
        next_cursor = None

        if has_more and forecasts:
            next_cursor = forecasts[-1].created_at.isoformat()

        # Cache results
        if self.redis and forecasts:
            try:
                cache_data = {
                    "forecasts": self._serialize_forecasts(forecasts),
                    "next_cursor": next_cursor,
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=self.cache_ttl
                )
            except Exception as e:
                logger.warning("forecast_cache_write_error", error=str(e))

        return forecasts, next_cursor

    async def invalidate_forecast_cache(self, symbol: Optional[str] = None):
        """
        Invalidate forecast cache.

        Args:
            symbol: Optional symbol to invalidate specific cache entries
        """
        if not self.redis:
            return

        try:
            if symbol:
                # Invalidate symbol-specific caches
                pattern = f"forecasts:*{symbol}*"
            else:
                # Invalidate all forecast caches
                pattern = "forecasts:*"

            # Note: In production, use SCAN instead of KEYS for large datasets
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.info("forecast_cache_invalidated", pattern=pattern, count=len(keys))
        except Exception as e:
            logger.error("forecast_cache_invalidation_error", error=str(e))

    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate cache key from prefix and parameters."""
        parts = [prefix]
        for key, value in sorted(kwargs.items()):
            if value is not None:
                parts.append(f"{key}:{value}")
        return ":".join(parts)

    def _serialize_forecasts(self, forecasts: List[Forecast]) -> List[dict]:
        """Serialize forecasts for caching."""
        return [
            {
                "id": f.id,
                "symbol": f.symbol,
                "timeframe": f.timeframe,
                "horizon": f.horizon,
                "predicted_price": str(f.predicted_price),
                "confidence": str(f.confidence),
                "model_name": f.model_name,
                "created_at": f.created_at.isoformat(),
                "forecast_time": f.forecast_time.isoformat(),
            }
            for f in forecasts
        ]

    def _deserialize_forecasts(self, data: List[dict]) -> List[Forecast]:
        """Deserialize forecasts from cache (for cache hit scenario)."""
        # Note: This returns dict-like objects, not full ORM instances
        # For cache hits, we return simple objects that can be serialized by Pydantic
        return [
            type('Forecast', (), {
                'id': f['id'],
                'symbol': f['symbol'],
                'timeframe': f['timeframe'],
                'horizon': f['horizon'],
                'predicted_price': Decimal(f['predicted_price']),
                'confidence': Decimal(f['confidence']),
                'model_name': f['model_name'],
                'created_at': datetime.fromisoformat(f['created_at']),
                'forecast_time': datetime.fromisoformat(f['forecast_time']),
            })()
            for f in data
        ]
