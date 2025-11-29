"""
Strategy service for trading strategy operations.

Handles business logic for strategy management, allocations, and performance tracking with Redis caching.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.database.models.strategy import (
    Strategy,
    StrategyAllocation,
    StrategyPerformance,
    StrategyStatus,
    PerformancePeriod,
)
from src.database.repositories.strategy_repository import StrategyRepository
import structlog

logger = structlog.get_logger(__name__)


class StrategyService:
    """
    Service for strategy operations with caching.

    Implements cache-aside pattern with Redis for strategy data.
    Cache TTL: 1 hour (3600 seconds) for allocation data.
    """

    def __init__(self, session: AsyncSession, redis: Optional[Redis] = None):
        """
        Initialize strategy service.

        Args:
            session: Database session
            redis: Optional Redis client for caching
        """
        self.repository = StrategyRepository(session)
        self.redis = redis
        self.cache_ttl = 3600  # 1 hour

    async def get_all_strategies(self) -> List[Strategy]:
        """
        Get all strategies with caching.

        Returns:
            List of Strategy instances
        """
        cache_key = "strategies:all"

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("strategy_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    return self._deserialize_strategies(data.get("strategies", []))
            except Exception as e:
                logger.warning("strategy_cache_error", error=str(e))

        # Cache miss - fetch from database
        logger.info("strategy_cache_miss", cache_key=cache_key)
        strategies = await self.repository.get_all_strategies()

        # Cache results
        if self.redis and strategies:
            try:
                cache_data = {
                    "strategies": self._serialize_strategies(strategies),
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=self.cache_ttl
                )
                logger.info("strategy_cached", cache_key=cache_key, count=len(strategies))
            except Exception as e:
                logger.warning("strategy_cache_write_error", error=str(e))

        return strategies

    async def get_strategy_allocations(
        self,
        strategy_id: int
    ) -> List[StrategyAllocation]:
        """
        Get allocation history for a strategy with caching.

        Args:
            strategy_id: Strategy ID

        Returns:
            List of StrategyAllocation instances ordered by date DESC
        """
        cache_key = f"strategy:allocations:{strategy_id}"

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("allocation_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    return self._deserialize_allocations(data.get("allocations", []))
            except Exception as e:
                logger.warning("allocation_cache_error", error=str(e))

        # Cache miss - fetch from database
        logger.info("allocation_cache_miss", cache_key=cache_key, strategy_id=strategy_id)
        allocations = await self.repository.get_strategy_allocations(strategy_id)

        # Cache results
        if self.redis and allocations:
            try:
                cache_data = {
                    "allocations": self._serialize_allocations(allocations),
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=self.cache_ttl
                )
                logger.info("allocation_cached", cache_key=cache_key, count=len(allocations))
            except Exception as e:
                logger.warning("allocation_cache_write_error", error=str(e))

        return allocations

    async def get_strategy_performance(
        self,
        strategy_id: int,
        period: str = "monthly"
    ) -> Optional[StrategyPerformance]:
        """
        Get performance metrics for a strategy with caching.

        Args:
            strategy_id: Strategy ID
            period: Performance period (daily, weekly, monthly, all_time)

        Returns:
            StrategyPerformance instance or None
        """
        cache_key = f"strategy:performance:{strategy_id}:{period}"

        # Try cache first
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    logger.info("performance_cache_hit", cache_key=cache_key)
                    data = json.loads(cached_data)
                    perf_data = data.get("performance")
                    if perf_data:
                        return self._deserialize_performance(perf_data)
            except Exception as e:
                logger.warning("performance_cache_error", error=str(e))

        # Cache miss - fetch from database
        logger.info("performance_cache_miss", cache_key=cache_key, strategy_id=strategy_id, period=period)
        performance = await self.repository.get_strategy_performance(strategy_id, period)

        # Cache results
        if self.redis and performance:
            try:
                cache_data = {
                    "performance": self._serialize_performance(performance),
                    "cached_at": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=self.cache_ttl
                )
                logger.info("performance_cached", cache_key=cache_key)
            except Exception as e:
                logger.warning("performance_cache_write_error", error=str(e))

        return performance

    async def invalidate_strategy_cache(self, strategy_id: Optional[int] = None):
        """
        Invalidate strategy cache.

        Args:
            strategy_id: Optional strategy ID to invalidate specific cache entries
        """
        if not self.redis:
            return

        try:
            if strategy_id:
                # Invalidate strategy-specific caches
                patterns = [
                    f"strategy:allocations:{strategy_id}",
                    f"strategy:performance:{strategy_id}:*"
                ]
                for pattern in patterns:
                    keys = await self.redis.keys(pattern)
                    if keys:
                        await self.redis.delete(*keys)
            else:
                # Invalidate all strategy caches
                pattern = "strategies:*"
                keys = await self.redis.keys(pattern)
                if keys:
                    await self.redis.delete(*keys)

            logger.info("strategy_cache_invalidated", strategy_id=strategy_id)
        except Exception as e:
            logger.error("strategy_cache_invalidation_error", error=str(e))

    def _serialize_strategies(self, strategies: List[Strategy]) -> List[dict]:
        """Serialize strategies for caching."""
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "status": s.status.value if isinstance(s.status, StrategyStatus) else s.status,
                "allocated_capital": str(s.allocated_capital),
                "parameters": s.parameters,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in strategies
        ]

    def _deserialize_strategies(self, data: List[dict]) -> List[Strategy]:
        """Deserialize strategies from cache."""
        return [
            type('Strategy', (), {
                'id': s['id'],
                'name': s['name'],
                'description': s['description'],
                'status': s['status'],
                'allocated_capital': Decimal(s['allocated_capital']),
                'parameters': s['parameters'],
                'created_at': datetime.fromisoformat(s['created_at']),
                'updated_at': datetime.fromisoformat(s['updated_at']),
            })()
            for s in data
        ]

    def _serialize_allocations(self, allocations: List[StrategyAllocation]) -> List[dict]:
        """Serialize allocations for caching."""
        return [
            {
                "id": a.id,
                "strategy_id": a.strategy_id,
                "allocated_capital": str(a.allocated_capital),
                "allocated_percentage": str(a.allocated_percentage),
                "allocation_date": a.allocation_date.isoformat(),
                "notes": a.notes,
            }
            for a in allocations
        ]

    def _deserialize_allocations(self, data: List[dict]) -> List[StrategyAllocation]:
        """Deserialize allocations from cache."""
        return [
            type('StrategyAllocation', (), {
                'id': a['id'],
                'strategy_id': a['strategy_id'],
                'allocated_capital': Decimal(a['allocated_capital']),
                'allocated_percentage': Decimal(a['allocated_percentage']),
                'allocation_date': datetime.fromisoformat(a['allocation_date']),
                'notes': a['notes'],
            })()
            for a in data
        ]

    def _serialize_performance(self, performance: StrategyPerformance) -> dict:
        """Serialize performance for caching."""
        return {
            "id": performance.id,
            "strategy_id": performance.strategy_id,
            "period": performance.period.value if isinstance(performance.period, PerformancePeriod) else performance.period,
            "period_start": performance.period_start.isoformat(),
            "period_end": performance.period_end.isoformat(),
            "total_trades": performance.total_trades,
            "winning_trades": performance.winning_trades,
            "losing_trades": performance.losing_trades,
            "win_rate": str(performance.win_rate),
            "total_profit": str(performance.total_profit),
            "total_loss": str(performance.total_loss),
            "net_profit": str(performance.net_profit),
            "sharpe_ratio": str(performance.sharpe_ratio) if performance.sharpe_ratio else None,
            "max_drawdown": str(performance.max_drawdown) if performance.max_drawdown else None,
            "average_win": str(performance.average_win) if performance.average_win else None,
            "average_loss": str(performance.average_loss) if performance.average_loss else None,
        }

    def _deserialize_performance(self, data: dict) -> StrategyPerformance:
        """Deserialize performance from cache."""
        return type('StrategyPerformance', (), {
            'id': data['id'],
            'strategy_id': data['strategy_id'],
            'period': data['period'],
            'period_start': datetime.fromisoformat(data['period_start']),
            'period_end': datetime.fromisoformat(data['period_end']),
            'total_trades': data['total_trades'],
            'winning_trades': data['winning_trades'],
            'losing_trades': data['losing_trades'],
            'win_rate': Decimal(data['win_rate']),
            'total_profit': Decimal(data['total_profit']),
            'total_loss': Decimal(data['total_loss']),
            'net_profit': Decimal(data['net_profit']),
            'sharpe_ratio': Decimal(data['sharpe_ratio']) if data['sharpe_ratio'] else None,
            'max_drawdown': Decimal(data['max_drawdown']) if data['max_drawdown'] else None,
            'average_win': Decimal(data['average_win']) if data['average_win'] else None,
            'average_loss': Decimal(data['average_loss']) if data['average_loss'] else None,
        })()
