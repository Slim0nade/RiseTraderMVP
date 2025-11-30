"""
RedisSubscriberService - Redis pub/sub client for real-time market data streaming.

Implements T052-T053 from 002-fastapi-dashboard-api specification.
Subscribes to Redis channels and streams events via Server-Sent Events (SSE).
"""
import asyncio
import json
import structlog
from typing import AsyncGenerator, List, Optional, Set
from datetime import datetime

from src.utils.redis_client import MT4RedisClient

logger = structlog.get_logger(__name__)


class RedisSubscriberService:
    """
    Service for subscribing to Redis pub/sub channels and streaming events.

    Used for real-time market data streaming via SSE.
    """

    def __init__(self, redis_client: MT4RedisClient):
        """
        Initialize RedisSubscriberService.

        Args:
            redis_client: Redis client for pub/sub operations
        """
        self.redis_client = redis_client
        self.pubsub = None
        self._subscribed_channels: Set[str] = set()

    async def subscribe(self, channels: List[str]) -> None:
        """
        Subscribe to Redis pub/sub channels.

        Args:
            channels: List of channel names to subscribe to
        """
        if not self.pubsub:
            self.pubsub = self.redis_client.client.pubsub()

        for channel in channels:
            if channel not in self._subscribed_channels:
                await self.pubsub.subscribe(channel)
                self._subscribed_channels.add(channel)
                logger.info("subscribed_to_channel", channel=channel)

    async def unsubscribe(self, channels: Optional[List[str]] = None) -> None:
        """
        Unsubscribe from Redis pub/sub channels.

        Args:
            channels: List of channel names to unsubscribe from (None = all)
        """
        if not self.pubsub:
            return

        if channels is None:
            # Unsubscribe from all
            await self.pubsub.unsubscribe(*self._subscribed_channels)
            self._subscribed_channels.clear()
            logger.info("unsubscribed_from_all_channels")
        else:
            for channel in channels:
                if channel in self._subscribed_channels:
                    await self.pubsub.unsubscribe(channel)
                    self._subscribed_channels.remove(channel)
                    logger.info("unsubscribed_from_channel", channel=channel)

    async def listen(
        self, heartbeat_interval: int = 30
    ) -> AsyncGenerator[dict, None]:
        """
        Listen for messages from subscribed channels.

        Yields messages as they arrive, with periodic heartbeat events.

        Args:
            heartbeat_interval: Seconds between heartbeat events

        Yields:
            Dictionary with message data or heartbeat event
        """
        if not self.pubsub:
            logger.error("listen_called_without_subscription")
            return

        last_heartbeat = asyncio.get_event_loop().time()

        try:
            while True:
                try:
                    # Get message with timeout to allow heartbeat checks
                    message = await asyncio.wait_for(
                        self.pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0,
                    )

                    current_time = asyncio.get_event_loop().time()

                    if message and message["type"] == "message":
                        # Parse message data
                        try:
                            data = json.loads(message["data"])
                            yield {
                                "type": "data",
                                "channel": message["channel"].decode("utf-8"),
                                "data": data,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                            last_heartbeat = current_time

                        except json.JSONDecodeError as e:
                            logger.error(
                                "failed_to_parse_message",
                                channel=message["channel"],
                                error=str(e),
                            )
                            yield {
                                "type": "error",
                                "error": "ParseError",
                                "detail": f"Failed to parse message: {str(e)}",
                                "timestamp": datetime.utcnow().isoformat(),
                            }

                    # Send heartbeat if interval exceeded
                    elif current_time - last_heartbeat >= heartbeat_interval:
                        yield {
                            "type": "heartbeat",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        last_heartbeat = current_time

                except asyncio.TimeoutError:
                    # No message received, check heartbeat
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield {
                            "type": "heartbeat",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        last_heartbeat = current_time

                except Exception as e:
                    logger.error("listen_error", error=str(e), exc_info=True)
                    yield {
                        "type": "error",
                        "error": "StreamError",
                        "detail": str(e),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    break

        finally:
            # Cleanup on exit
            await self.unsubscribe()
            if self.pubsub:
                await self.pubsub.close()
                self.pubsub = None
            logger.info("listen_stopped")

    @staticmethod
    def get_market_data_channel(symbol: str, timeframe: Optional[str] = None) -> str:
        """
        Get Redis channel name for market data updates.

        Args:
            symbol: Trading symbol
            timeframe: Optional timeframe filter

        Returns:
            Channel name string
        """
        if timeframe:
            return f"market_data:{symbol}:{timeframe}"
        return f"market_data:{symbol}"

    @staticmethod
    def format_sse_event(event_type: str, data: dict) -> str:
        """
        Format data as Server-Sent Event (SSE) string.

        Args:
            event_type: Event type (e.g., "market_data", "heartbeat", "error")
            data: Event data dictionary

        Returns:
            SSE-formatted string
        """
        event_str = f"event: {event_type}\n"
        event_str += f"data: {json.dumps(data)}\n\n"
        return event_str
