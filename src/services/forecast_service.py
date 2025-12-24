"""
Forecast service for ML prediction operations.

Handles business logic for forecast retrieval with Redis caching.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import desc, select
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
        """Initialize forecast service."""
        self.repository = ForecastsRepository(session)
        self.redis = redis
        self.cache_ttl = 3600  # 1 hour

    async def get_latest_forecasts(
        self,
        symbol: Optional[str] = None,
        horizon: Optional[str] = None
    ) -> List[Forecast]:
        """Get latest forecasts with optional filters."""
        # Generate cache key
        cache_key = self._generate_cache_key("forecasts:latest", symbol=symbol, horizon=horizon)

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("forecast_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    return self._deserialize_forecasts(data.get("forecasts", []))
            except Exception as e:
                logger.warning("forecast_cache_error", error=str(e), cache_key=cache_key)

        # Cache miss - fetch from database
        logger.info("forecast_cache_miss", cache_key=cache_key, symbol=symbol, horizon=horizon)

        query = select(Forecast).order_by(desc(Forecast.created_at))

        if symbol:
            query = query.where(Forecast.symbol == symbol)
        if horizon:
            query = query.where(Forecast.forecast_horizon == horizon)

        query = query.limit(100)

        result = await self.repository.session.execute(query)
        forecasts = list(result.scalars().all())

        # Cache the results
        if self.redis and forecasts:
            try:
                cache_data = {
                    "forecasts": self._serialize_forecasts(forecasts),
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(cache_key, json.dumps(cache_data), ex=self.cache_ttl)
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
        """Get forecasts for a specific symbol with keyset pagination."""
        cache_key = self._generate_cache_key(f"forecasts:symbol:{symbol}", cursor=cursor, limit=limit)

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("forecast_symbol_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    return (self._deserialize_forecasts(data.get("forecasts", [])), data.get("next_cursor"))
            except Exception as e:
                logger.warning("forecast_cache_error", error=str(e))

        # Build query with keyset pagination
        query = (
            select(Forecast)
            .where(Forecast.symbol == symbol)
            .order_by(desc(Forecast.created_at))
            .limit(limit + 1)
        )

        if cursor:
            try:
                cursor_time = datetime.fromisoformat(cursor.replace('Z', '+00:00'))
                query = query.where(Forecast.created_at < cursor_time)
            except (ValueError, AttributeError):
                logger.warning("invalid_cursor", cursor=cursor)

        result = await self.repository.session.execute(query)
        all_forecasts = list(result.scalars().all())

        has_more = len(all_forecasts) > limit
        forecasts = all_forecasts[:limit]
        next_cursor = forecasts[-1].created_at.isoformat() if has_more and forecasts else None

        # Cache results
        if self.redis and forecasts:
            try:
                cache_data = {
                    "forecasts": self._serialize_forecasts(forecasts),
                    "next_cursor": next_cursor,
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(cache_key, json.dumps(cache_data), ex=self.cache_ttl)
            except Exception as e:
                logger.warning("forecast_cache_write_error", error=str(e))

        return forecasts, next_cursor

    async def invalidate_forecast_cache(self, symbol: Optional[str] = None):
        """Invalidate forecast cache."""
        if not self.redis:
            return
        try:
            pattern = f"forecasts:*{symbol}*" if symbol else "forecasts:*"
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
                "forecast_horizon": f.forecast_horizon,
                "model_type": f.model_type,
                "model_version": f.model_version,
                "predicted_value": float(f.predicted_value) if f.predicted_value else None,
                "lower_bound": float(f.lower_bound) if f.lower_bound else None,
                "upper_bound": float(f.upper_bound) if f.upper_bound else None,
                "confidence_score": float(f.confidence_score) if f.confidence_score else None,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in forecasts
        ]

    def _deserialize_forecasts(self, data: List[dict]) -> List:
        """Deserialize forecasts from cache."""
        return [
            type('Forecast', (), {
                'id': f['id'],
                'symbol': f['symbol'],
                'forecast_horizon': f.get('forecast_horizon'),
                'model_type': f.get('model_type'),
                'model_version': f.get('model_version'),
                'predicted_value': f.get('predicted_value'),
                'lower_bound': f.get('lower_bound'),
                'upper_bound': f.get('upper_bound'),
                'confidence_score': f.get('confidence_score'),
                'created_at': datetime.fromisoformat(f['created_at']) if f.get('created_at') else None,
            })()
            for f in data
        ]
