"""Forecast Cache - Redis integration with 5-minute TTL."""

import json
from typing import Optional
from redis import Redis


class ForecastCache:
    """Redis cache for forecasts with configurable TTL."""
    
    def __init__(self, redis_client: Redis, ttl_seconds: int = 300):
        self.redis = redis_client
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[dict]:
        """Get cached forecast."""
        data = self.redis.get(key)
        return json.loads(data) if data else None
    
    def set(self, key: str, value: dict):
        """Cache forecast with TTL."""
        self.redis.setex(key, self.ttl, json.dumps(value))
    
    def make_key(self, symbol: str, horizon: str, model_version: str) -> str:
        """Generate cache key."""
        return f"forecast:{symbol}:{horizon}:{model_version}"
