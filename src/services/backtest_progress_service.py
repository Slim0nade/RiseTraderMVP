"""
Backtest Progress Streaming Service

Provides real-time progress updates for long-running backtests via:
1. Redis Pub/Sub - Backend publishes progress
2. SSE (Server-Sent Events) - Clients receive updates

Architecture:
    BacktestService → Redis Channel → SSE Endpoint → Client
    
Usage:
    # Backend (in backtest_service.py):
    await progress_publisher.publish_progress(run_id, candles_processed, total_candles)
    
    # Client (SSE):
    GET /api/backtesting/runs/{run_id}/stream
    
    # MCP (polling with progress):
    GET /api/backtesting/runs/{run_id}/status  # Enhanced with progress_pct
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from uuid import UUID

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class BacktestProgressPublisher:
    """
    Publishes backtest progress updates to Redis.
    
    Used by BacktestService to broadcast progress during execution.
    """
    
    CHANNEL_PREFIX = "backtest:progress:"
    
    def __init__(self, redis: Redis):
        self.redis = redis
        
    def _channel_name(self, run_id: UUID) -> str:
        return f"{self.CHANNEL_PREFIX}{run_id}"
    
    async def publish_progress(
        self,
        run_id: UUID,
        candles_processed: int,
        total_candles: int,
        status: str = "running",
        trades_count: int = 0,
        current_capital: Optional[float] = None,
        error_message: Optional[str] = None,
    ):
        """
        Publish progress update to Redis channel.
        
        Args:
            run_id: Backtest run UUID
            candles_processed: Number of candles processed so far
            total_candles: Total candles to process
            status: Current status (running, completed, failed)
            trades_count: Number of trades executed
            current_capital: Current portfolio value
            error_message: Error message if failed
        """
        progress_pct = (candles_processed / total_candles * 100) if total_candles > 0 else 0
        
        message = {
            "type": "progress",
            "run_id": str(run_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "candles_processed": candles_processed,
            "total_candles": total_candles,
            "progress_pct": round(progress_pct, 2),
            "trades_count": trades_count,
            "current_capital": current_capital,
            "error_message": error_message,
        }
        
        channel = self._channel_name(run_id)
        
        try:
            await self.redis.publish(channel, json.dumps(message))
            logger.debug(
                "progress_published",
                run_id=str(run_id),
                progress_pct=progress_pct,
                candles_processed=candles_processed,
            )
        except Exception as e:
            logger.warning(
                "progress_publish_failed",
                run_id=str(run_id),
                error=str(e),
            )
    
    async def publish_complete(
        self,
        run_id: UUID,
        total_candles: int,
        trades_count: int,
        final_capital: float,
        metrics: Optional[dict] = None,
    ):
        """Publish completion event."""
        message = {
            "type": "complete",
            "run_id": str(run_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "candles_processed": total_candles,
            "total_candles": total_candles,
            "progress_pct": 100.0,
            "trades_count": trades_count,
            "final_capital": final_capital,
            "metrics": metrics,
        }
        
        channel = self._channel_name(run_id)
        await self.redis.publish(channel, json.dumps(message))
        
        logger.info(
            "backtest_complete_published",
            run_id=str(run_id),
            trades_count=trades_count,
            final_capital=final_capital,
        )
    
    async def publish_error(self, run_id: UUID, error_message: str):
        """Publish error event."""
        message = {
            "type": "error",
            "run_id": str(run_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error_message": error_message,
        }
        
        channel = self._channel_name(run_id)
        await self.redis.publish(channel, json.dumps(message))
        
        logger.error(
            "backtest_error_published",
            run_id=str(run_id),
            error=error_message,
        )


class BacktestProgressSubscriber:
    """
    Subscribes to backtest progress updates from Redis.
    
    Used by SSE endpoint to stream updates to clients.
    """
    
    CHANNEL_PREFIX = "backtest:progress:"
    
    def __init__(self, redis: Redis):
        self.redis = redis
        self.pubsub = None
        
    def _channel_name(self, run_id: UUID) -> str:
        return f"{self.CHANNEL_PREFIX}{run_id}"
    
    async def subscribe(self, run_id: UUID) -> AsyncGenerator[dict, None]:
        """
        Subscribe to progress updates for a backtest run.
        
        Yields progress events until completion or error.
        
        Args:
            run_id: Backtest run UUID
            
        Yields:
            Progress update dictionaries
        """
        channel = self._channel_name(run_id)
        self.pubsub = self.redis.pubsub()
        
        try:
            await self.pubsub.subscribe(channel)
            logger.info("subscribed_to_progress", run_id=str(run_id), channel=channel)
            
            while True:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=30.0,  # 30 second timeout for heartbeat
                )
                
                if message is None:
                    # Timeout - send heartbeat
                    yield {
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    continue
                
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield data
                    
                    # Stop if completed or failed
                    if data.get("type") in ("complete", "error"):
                        logger.info(
                            "progress_stream_ended",
                            run_id=str(run_id),
                            final_type=data.get("type"),
                        )
                        break
                        
        except asyncio.CancelledError:
            logger.info("progress_subscription_cancelled", run_id=str(run_id))
            raise
        except Exception as e:
            logger.error(
                "progress_subscription_error",
                run_id=str(run_id),
                error=str(e),
            )
            yield {
                "type": "error",
                "error_message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            if self.pubsub:
                await self.pubsub.unsubscribe(channel)
                await self.pubsub.close()


def format_sse_event(event_type: str, data: dict) -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
