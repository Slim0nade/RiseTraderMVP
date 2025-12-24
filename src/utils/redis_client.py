"""
Redis client wrapper for MT4 integration.

Provides connection pooling, caching, and pub/sub messaging for portfolio risk state
and MT4 events.
"""
import asyncio
import json
import os
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.client import PubSub
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from src.utils.mt4_helpers import get_mt4_logger

logger = get_mt4_logger("redis_client")


# =============================================================================
# Redis Client Wrapper
# =============================================================================

class MT4RedisClient:
    """
    Async Redis client wrapper for MT4 integration.

    Features:
    - Connection pooling with automatic reconnection
    - Portfolio risk state caching with TTL
    - Pub/sub messaging for MT4 events
    - Structured logging with correlation IDs
    - Health monitoring
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_connections: int = 50,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
    ):
        """
        Initialize Redis client.

        Args:
            redis_url: Redis connection URL (defaults to REDIS_URL env var)
            max_connections: Maximum connections in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Socket connect timeout in seconds
            retry_on_timeout: Whether to retry on timeout
            health_check_interval: Health check interval in seconds
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval

        # Connection pool and client
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[Redis] = None

        # Pub/sub client (separate connection)
        self.pubsub_client: Optional[Redis] = None
        self.pubsub: Optional[PubSub] = None

        # Subscription handlers
        self._handlers: Dict[str, List[Callable]] = {}
        self._subscription_task: Optional[asyncio.Task] = None

        logger.info(
            "redis_client_initialized",
            redis_url=self._sanitize_url(self.redis_url),
            max_connections=max_connections,
        )

    async def connect(self) -> None:
        """Establish Redis connection with connection pool."""
        try:
            # Create connection pool
            self.pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout,
                health_check_interval=self.health_check_interval,
                decode_responses=True,
            )

            # Create main client
            self.client = Redis(connection_pool=self.pool)

            # Test connection
            await self.client.ping()

            logger.info(
                "redis_connected",
                redis_url=self._sanitize_url(self.redis_url),
            )

        except (ConnectionError, TimeoutError) as e:
            logger.error(
                "redis_connection_failed",
                error=str(e),
                redis_url=self._sanitize_url(self.redis_url),
            )
            raise

    async def disconnect(self) -> None:
        """Close Redis connection and cleanup resources."""
        try:
            # Stop pub/sub subscription task
            if self._subscription_task:
                self._subscription_task.cancel()
                try:
                    await self._subscription_task
                except asyncio.CancelledError:
                    pass

            # Close pub/sub connection
            if self.pubsub:
                await self.pubsub.unsubscribe()
                await self.pubsub.close()

            if self.pubsub_client:
                await self.pubsub_client.close()

            # Close main client
            if self.client:
                await self.client.close()

            # Close connection pool
            if self.pool:
                await self.pool.disconnect()

            logger.info("redis_disconnected")

        except Exception as e:
            logger.error("redis_disconnect_error", error=str(e))

    async def health_check(self) -> bool:
        """
        Check Redis connection health.

        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.client:
                return False

            await self.client.ping()
            return True

        except Exception as e:
            logger.warning("redis_health_check_failed", error=str(e))
            return False

    # =========================================================================
    # Portfolio Risk State Caching
    # =========================================================================

    async def cache_portfolio_risk(
        self,
        risk_state: Dict[str, Any],
        ttl_seconds: int = 300,
    ) -> bool:
        """
        Cache portfolio risk state.

        Args:
            risk_state: Portfolio risk state dictionary
            ttl_seconds: Time to live in seconds (default 5 minutes)

        Returns:
            True if cached successfully
        """
        try:
            key = get_portfolio_risk_key()
            value = json.dumps(risk_state)

            await self.client.setex(key, ttl_seconds, value)

            logger.debug(
                "portfolio_risk_cached",
                key=key,
                ttl_seconds=ttl_seconds,
            )

            return True

        except Exception as e:
            logger.error(
                "portfolio_risk_cache_error",
                error=str(e),
            )
            return False

    async def get_portfolio_risk(self) -> Optional[Dict[str, Any]]:
        """
        Get cached portfolio risk state.

        Returns:
            Portfolio risk state dictionary or None if not cached
        """
        try:
            key = get_portfolio_risk_key()
            value = await self.client.get(key)

            if value is None:
                logger.debug("portfolio_risk_cache_miss", key=key)
                return None

            logger.debug("portfolio_risk_cache_hit", key=key)
            return json.loads(value)

        except Exception as e:
            logger.error("portfolio_risk_get_error", error=str(e))
            return None

    async def cache_ea_risk(
        self,
        ea_id: str,
        risk_state: Dict[str, Any],
        ttl_seconds: int = 300,
    ) -> bool:
        """
        Cache EA-specific risk state.

        Args:
            ea_id: EA identifier
            risk_state: EA risk state dictionary
            ttl_seconds: Time to live in seconds

        Returns:
            True if cached successfully
        """
        try:
            key = get_ea_risk_key(ea_id)
            value = json.dumps(risk_state)

            await self.client.setex(key, ttl_seconds, value)

            logger.debug(
                "ea_risk_cached",
                ea_id=ea_id,
                key=key,
                ttl_seconds=ttl_seconds,
            )

            return True

        except Exception as e:
            logger.error("ea_risk_cache_error", ea_id=ea_id, error=str(e))
            return False

    async def get_ea_risk(self, ea_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached EA risk state.

        Args:
            ea_id: EA identifier

        Returns:
            EA risk state dictionary or None if not cached
        """
        try:
            key = get_ea_risk_key(ea_id)
            value = await self.client.get(key)

            if value is None:
                return None

            return json.loads(value)

        except Exception as e:
            logger.error("ea_risk_get_error", ea_id=ea_id, error=str(e))
            return None

    # =========================================================================
    # Generic Caching
    # =========================================================================

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Set a cache value.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl_seconds: Optional TTL in seconds

        Returns:
            True if set successfully
        """
        try:
            serialized = json.dumps(value) if not isinstance(value, str) else value

            if ttl_seconds:
                await self.client.setex(key, ttl_seconds, serialized)
            else:
                await self.client.set(key, serialized)

            return True

        except Exception as e:
            logger.error("redis_set_error", key=key, error=str(e))
            return False

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a cached value.

        Args:
            key: Cache key

        Returns:
            Cached value (JSON deserialized) or None
        """
        try:
            value = await self.client.get(key)

            if value is None:
                return None

            # Try to deserialize as JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        except Exception as e:
            logger.error("redis_get_error", key=key, error=str(e))
            return None

    async def delete(self, key: str) -> bool:
        """
        Delete a cached value.

        Args:
            key: Cache key

        Returns:
            True if deleted successfully
        """
        try:
            await self.client.delete(key)
            return True

        except Exception as e:
            logger.error("redis_delete_error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error("redis_exists_error", key=key, error=str(e))
            return False

    # =========================================================================
    # Pub/Sub Messaging
    # =========================================================================

    async def publish_event(
        self,
        channel: str,
        event: Dict[str, Any],
    ) -> bool:
        """
        Publish an event to a channel.

        Args:
            channel: Channel name
            event: Event data dictionary

        Returns:
            True if published successfully
        """
        try:
            message = json.dumps(event)
            await self.client.publish(channel, message)

            logger.debug(
                "event_published",
                channel=channel,
                event_type=event.get("event_type"),
            )

            return True

        except Exception as e:
            logger.error(
                "event_publish_error",
                channel=channel,
                error=str(e),
            )
            return False

    async def subscribe(
        self,
        channel: str,
        handler: Callable[[Dict[str, Any]], None],
    ) -> bool:
        """
        Subscribe to a channel with a message handler.

        Args:
            channel: Channel name
            handler: Async callback function for messages

        Returns:
            True if subscribed successfully
        """
        try:
            # Initialize pub/sub client if needed
            if self.pubsub_client is None:
                self.pubsub_client = Redis(connection_pool=self.pool)
                self.pubsub = self.pubsub_client.pubsub()

            # Register handler
            if channel not in self._handlers:
                self._handlers[channel] = []
            self._handlers[channel].append(handler)

            # Subscribe to channel
            await self.pubsub.subscribe(channel)

            # Start subscription task if not running
            if self._subscription_task is None or self._subscription_task.done():
                self._subscription_task = asyncio.create_task(self._process_messages())

            logger.info("subscribed_to_channel", channel=channel)

            return True

        except Exception as e:
            logger.error("subscribe_error", channel=channel, error=str(e))
            return False

    async def unsubscribe(self, channel: str) -> bool:
        """
        Unsubscribe from a channel.

        Args:
            channel: Channel name

        Returns:
            True if unsubscribed successfully
        """
        try:
            if self.pubsub:
                await self.pubsub.unsubscribe(channel)

            # Remove handlers
            if channel in self._handlers:
                del self._handlers[channel]

            logger.info("unsubscribed_from_channel", channel=channel)

            return True

        except Exception as e:
            logger.error("unsubscribe_error", channel=channel, error=str(e))
            return False

    async def _process_messages(self) -> None:
        """Process incoming pub/sub messages."""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    data = message["data"]

                    # Parse JSON message
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "invalid_message_format",
                            channel=channel,
                            data=data,
                        )
                        continue

                    # Call registered handlers
                    if channel in self._handlers:
                        for handler in self._handlers[channel]:
                            try:
                                await handler(event)
                            except Exception as e:
                                logger.error(
                                    "message_handler_error",
                                    channel=channel,
                                    handler=handler.__name__,
                                    error=str(e),
                                )

        except asyncio.CancelledError:
            logger.info("message_processing_cancelled")

        except Exception as e:
            logger.error("message_processing_error", error=str(e))

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _sanitize_url(self, url: str) -> str:
        """Sanitize Redis URL for logging (hide password)."""
        if "@" in url:
            # redis://user:password@host:port/db -> redis://user:***@host:port/db
            parts = url.split("@")
            if ":" in parts[0]:
                user_pass = parts[0].split(":")
                return f"{user_pass[0]}:{user_pass[1].split('//')[0]}//***@{parts[1]}"
        return url


# =============================================================================
# Cache Key Helpers
# =============================================================================

def get_portfolio_risk_key() -> str:
    """Get Redis key for portfolio risk state."""
    return "mt4:portfolio_risk"


def get_ea_risk_key(ea_id: str) -> str:
    """
    Get Redis key for EA risk state.

    Args:
        ea_id: EA identifier

    Returns:
        Redis key
    """
    return f"mt4:ea_risk:{ea_id}"


def get_connection_health_key(ea_id: str) -> str:
    """
    Get Redis key for EA connection health.

    Args:
        ea_id: EA identifier

    Returns:
        Redis key
    """
    return f"mt4:connection_health:{ea_id}"


def get_circuit_breaker_key(ea_id: str) -> str:
    """
    Get Redis key for circuit breaker state.

    Args:
        ea_id: EA identifier

    Returns:
        Redis key
    """
    return f"mt4:circuit_breaker:{ea_id}"


def get_order_cache_key(order_id: str) -> str:
    """
    Get Redis key for order cache.

    Args:
        order_id: Order identifier

    Returns:
        Redis key
    """
    return f"mt4:order:{order_id}"


def get_position_cache_key(ticket_number: int) -> str:
    """
    Get Redis key for position cache.

    Args:
        ticket_number: MT4 ticket number

    Returns:
        Redis key
    """
    return f"mt4:position:{ticket_number}"


# =============================================================================
# Channel Names
# =============================================================================

# MT4 event channels
CHANNEL_ORDER_CONFIRMED = "mt4:events:order_confirmed"
CHANNEL_ORDER_REJECTED = "mt4:events:order_rejected"
CHANNEL_POSITION_UPDATED = "mt4:events:position_updated"
CHANNEL_POSITION_CLOSED = "mt4:events:position_closed"
CHANNEL_MARKET_TICK = "mt4:events:market_tick"
CHANNEL_CONNECTION_STATUS = "mt4:events:connection_status"
CHANNEL_PORTFOLIO_RISK = "mt4:events:portfolio_risk"
CHANNEL_CIRCUIT_BREAKER = "mt4:events:circuit_breaker"


# =============================================================================
# Convenience Functions
# =============================================================================

async def create_redis_client() -> MT4RedisClient:
    """
    Create and connect Redis client.

    Returns:
        Connected MT4RedisClient instance
    """
    client = MT4RedisClient()
    await client.connect()
    return client


# Global Redis client singleton
_redis_client: Optional[Redis] = None
_redis_client_lock = asyncio.Lock()


async def get_redis_client() -> Optional[Redis]:
    """
    Get or create a shared Redis client for pub/sub operations.
    
    Returns a simple redis.asyncio.Redis client (not MT4RedisClient)
    for use by the backtest progress service.
    
    Returns:
        Redis client instance, or None if connection fails
    """
    global _redis_client
    
    async with _redis_client_lock:
        if _redis_client is not None:
            # Check if still connected
            try:
                await _redis_client.ping()
                return _redis_client
            except Exception:
                _redis_client = None
        
        # Create new connection
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_client = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            await _redis_client.ping()
            logger.info("redis_client_connected", url=redis_url.split("@")[-1])
            return _redis_client
        except Exception as e:
            logger.warning("redis_client_connection_failed", error=str(e))
            return None


async def close_redis_client() -> None:
    """Close the shared Redis client."""
    global _redis_client
    
    async with _redis_client_lock:
        if _redis_client:
            await _redis_client.close()
            _redis_client = None
            logger.info("redis_client_closed")
