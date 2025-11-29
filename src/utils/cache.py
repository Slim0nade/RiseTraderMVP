"""
Cache-aside pattern helpers for Dashboard API.

Provides high-level caching utilities with standardized key patterns,
serialization, and TTL management for market data, account info, and forecasts.
"""
import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional, TypeVar

from src.utils.redis_client import MT4RedisClient

T = TypeVar("T")


# =============================================================================
# Cache Key Patterns (as constants per T024)
# =============================================================================

# Market Data cache keys
CACHE_KEY_PRICE_LATEST = "price:latest:{symbol}"  # Latest price for symbol
CACHE_KEY_CHART = "chart:{symbol}:{timeframe}:{start}:{end}"  # Chart data range
CACHE_KEY_SYMBOLS = "symbols:list"  # List of available symbols

# Trading cache keys
CACHE_KEY_ACCOUNT = "account:info"  # Account balance and equity
CACHE_KEY_POSITIONS = "positions:{symbol}"  # Open positions (optional symbol filter)
CACHE_KEY_POSITIONS_ALL = "positions:all"  # All open positions
CACHE_KEY_TRADE_HISTORY = "trades:history:{symbol}:{start}:{end}"  # Trade history range

# Forecast cache keys
CACHE_KEY_FORECAST_LATEST = "forecast:latest:{symbol}"  # Latest forecast for symbol
CACHE_KEY_FORECAST_ALL = "forecast:all"  # All latest forecasts

# Strategy cache keys
CACHE_KEY_STRATEGY = "strategy:{strategy_id}"  # Strategy details
CACHE_KEY_STRATEGY_PERFORMANCE = "strategy:{strategy_id}:performance"  # Strategy perf metrics


# =============================================================================
# Cache TTL values (seconds)
# =============================================================================

TTL_PRICE_LATEST = 5  # 5 seconds for latest prices (high-frequency updates)
TTL_CHART_DATA = 3600  # 1 hour for historical chart data (less frequent)
TTL_ACCOUNT_INFO = 10  # 10 seconds for account info
TTL_POSITIONS = 5  # 5 seconds for open positions
TTL_FORECAST = 60  # 1 minute for forecasts
TTL_STRATEGY = 300  # 5 minutes for strategy details


# =============================================================================
# Cache Helper Functions (T023)
# =============================================================================

async def get_cached(
    redis_client: MT4RedisClient,
    key: str,
    deserialize: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Get cached value with cache-aside pattern.

    Args:
        redis_client: Redis client instance
        key: Cache key
        deserialize: Whether to deserialize JSON (default True)

    Returns:
        Cached data dict or None if not found or expired

    Example:
        data = await get_cached(redis, CACHE_KEY_ACCOUNT)
        if data is None:
            # Cache miss - fetch from database
            data = await fetch_from_db()
            await set_cached(redis, CACHE_KEY_ACCOUNT, data, TTL_ACCOUNT_INFO)
    """
    try:
        cached_value = await redis_client.get(key)
        if cached_value is None:
            return None

        if not deserialize:
            return cached_value

        # Deserialize with metadata extraction
        data = json.loads(cached_value) if isinstance(cached_value, str) else cached_value

        # Extract actual data from envelope if present
        if isinstance(data, dict) and "_metadata" in data:
            return data.get("data")

        return data

    except (json.JSONDecodeError, Exception) as e:
        # Log error but don't fail the request - treat as cache miss
        # TODO: Add structured logging here
        return None


async def set_cached(
    redis_client: MT4RedisClient,
    key: str,
    value: Any,
    ttl: int,
    serialize: bool = True,
    include_metadata: bool = True,
) -> bool:
    """
    Set cached value with TTL and optional metadata.

    Args:
        redis_client: Redis client instance
        key: Cache key
        value: Value to cache
        ttl: Time-to-live in seconds
        serialize: Whether to serialize to JSON (default True)
        include_metadata: Whether to add cache metadata (cached_at, source, version)

    Returns:
        True if cached successfully, False otherwise

    Example:
        success = await set_cached(
            redis,
            CACHE_KEY_PRICE_LATEST.format(symbol="CrudeOIL"),
            price_data,
            TTL_PRICE_LATEST
        )
    """
    try:
        # Wrap value with metadata if requested
        if include_metadata and serialize:
            envelope = {
                "data": value,
                "_metadata": {
                    "cached_at": datetime.utcnow().isoformat(),
                    "source": "dashboard-api",
                    "version": "1.0",
                    "ttl": ttl,
                }
            }
            cache_value = json.dumps(envelope)
        elif serialize:
            cache_value = json.dumps(value)
        else:
            cache_value = value

        # Set with TTL
        await redis_client.set(key, cache_value, ex=ttl)
        return True

    except Exception as e:
        # Log error but don't fail the request
        # TODO: Add structured logging here
        return False


async def invalidate_cache(
    redis_client: MT4RedisClient,
    key: str,
) -> bool:
    """
    Invalidate (delete) cached value.

    Args:
        redis_client: Redis client instance
        key: Cache key to invalidate

    Returns:
        True if key was deleted, False if key didn't exist or error

    Example:
        # Invalidate price cache after new tick arrives
        await invalidate_cache(redis, CACHE_KEY_PRICE_LATEST.format(symbol="CrudeOIL"))
    """
    try:
        return await redis_client.delete(key)
    except Exception as e:
        # TODO: Add structured logging here
        return False


async def invalidate_pattern(
    redis_client: MT4RedisClient,
    pattern: str,
) -> int:
    """
    Invalidate all keys matching pattern.

    Args:
        redis_client: Redis client instance
        pattern: Key pattern (e.g., "chart:CrudeOIL:*")

    Returns:
        Number of keys deleted

    Example:
        # Invalidate all chart caches for CrudeOIL
        count = await invalidate_pattern(redis, "chart:CrudeOIL:*")
    """
    try:
        # Use Redis SCAN to find keys matching pattern
        cursor = 0
        deleted_count = 0

        while True:
            cursor, keys = await redis_client.client.scan(cursor, match=pattern, count=100)
            if keys:
                deleted = await redis_client.client.delete(*keys)
                deleted_count += deleted

            if cursor == 0:
                break

        return deleted_count

    except Exception as e:
        # TODO: Add structured logging here
        return 0


async def cached_fetch(
    redis_client: MT4RedisClient,
    key: str,
    fetch_func: Callable,
    ttl: int,
) -> Optional[Any]:
    """
    Cache-aside pattern: Get from cache, or fetch and cache if miss.

    Args:
        redis_client: Redis client instance
        key: Cache key
        fetch_func: Async function to call on cache miss
        ttl: Time-to-live for cached value

    Returns:
        Data from cache or fetch_func

    Example:
        data = await cached_fetch(
            redis,
            CACHE_KEY_ACCOUNT,
            lambda: db.get_account_info(),
            TTL_ACCOUNT_INFO
        )
    """
    # Try cache first
    cached = await get_cached(redis_client, key)
    if cached is not None:
        return cached

    # Cache miss - fetch from source
    data = await fetch_func()

    # Cache the result
    if data is not None:
        await set_cached(redis_client, key, data, ttl)

    return data


# =============================================================================
# Event-Driven Cache Invalidation Helpers
# =============================================================================

async def invalidate_market_data_cache(
    redis_client: MT4RedisClient,
    symbol: str,
    timeframe: Optional[str] = None,
) -> int:
    """
    Invalidate market data caches for a symbol after new tick.

    Args:
        redis_client: Redis client instance
        symbol: Trading symbol
        timeframe: Optional timeframe filter

    Returns:
        Number of cache keys invalidated
    """
    count = 0

    # Invalidate latest price
    await invalidate_cache(redis_client, CACHE_KEY_PRICE_LATEST.format(symbol=symbol))
    count += 1

    # Invalidate chart data for this symbol
    if timeframe:
        pattern = f"chart:{symbol}:{timeframe}:*"
    else:
        pattern = f"chart:{symbol}:*"

    count += await invalidate_pattern(redis_client, pattern)

    return count


async def invalidate_trading_cache(
    redis_client: MT4RedisClient,
    symbol: Optional[str] = None,
) -> int:
    """
    Invalidate trading caches after position/account changes.

    Args:
        redis_client: Redis client instance
        symbol: Optional symbol filter

    Returns:
        Number of cache keys invalidated
    """
    count = 0

    # Always invalidate account info
    await invalidate_cache(redis_client, CACHE_KEY_ACCOUNT)
    count += 1

    # Invalidate position caches
    if symbol:
        await invalidate_cache(redis_client, CACHE_KEY_POSITIONS.format(symbol=symbol))
        count += 1
    else:
        # Invalidate all positions
        count += await invalidate_pattern(redis_client, "positions:*")

    return count
