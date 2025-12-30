"""
Backtest Event Streaming for Live Visualization.

Provides WebSocket event streaming for real-time backtest progress visualization.
Events include candle processing, agent decisions, trades, and performance metrics.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class BacktestEventType(str, Enum):
    """Types of events emitted during backtest execution."""

    BACKTEST_STARTED = "backtest_started"
    PROGRESS_UPDATE = "progress_update"
    CANDLE_PROCESSED = "candle_processed"
    AGENT_DECISION = "agent_decision"
    TRADE_EXECUTED = "trade_executed"
    POSITION_UPDATED = "position_updated"
    EQUITY_UPDATED = "equity_updated"
    BACKTEST_COMPLETED = "backtest_completed"
    BACKTEST_ERROR = "backtest_error"


@dataclass
class BacktestEvent:
    """Base event structure for backtest updates."""

    event_type: BacktestEventType
    run_id: UUID
    timestamp: datetime
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type.value,
            "run_id": str(self.run_id),
            "timestamp": self.timestamp.isoformat(),
            "data": self._serialize_data(self.data),
        }

    @staticmethod
    def _serialize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively serialize Decimal and UUID values for JSON."""
        serialized = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                serialized[key] = float(value)
            elif isinstance(value, UUID):
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, dict):
                serialized[key] = BacktestEvent._serialize_data(value)
            elif isinstance(value, list):
                serialized[key] = [
                    BacktestEvent._serialize_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                serialized[key] = value
        return serialized


class BacktestEventBroadcaster:
    """
    Manages WebSocket connections and broadcasts backtest events.

    Maintains list of active WebSocket connections per backtest run
    and broadcasts events to all connected clients.
    """

    def __init__(self):
        """Initialize event broadcaster."""
        # Dict of run_id -> list of WebSocket connections
        self._connections: Dict[UUID, List[Any]] = {}
        logger.info("backtest_event_broadcaster_initialized")

    def register_connection(self, run_id: UUID, websocket: Any) -> None:
        """
        Register a new WebSocket connection for a backtest run.

        Args:
            run_id: Backtest run UUID
            websocket: WebSocket connection
        """
        if run_id not in self._connections:
            self._connections[run_id] = []

        self._connections[run_id].append(websocket)
        logger.info(
            "websocket_connection_registered",
            run_id=str(run_id),
            total_connections=len(self._connections[run_id]),
        )

    def unregister_connection(self, run_id: UUID, websocket: Any) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            run_id: Backtest run UUID
            websocket: WebSocket connection to remove
        """
        if run_id in self._connections:
            try:
                self._connections[run_id].remove(websocket)
                logger.info(
                    "websocket_connection_unregistered",
                    run_id=str(run_id),
                    remaining_connections=len(self._connections[run_id]),
                )

                # Clean up empty connection lists
                if not self._connections[run_id]:
                    del self._connections[run_id]

            except ValueError:
                logger.warning(
                    "websocket_connection_not_found",
                    run_id=str(run_id),
                )

    async def broadcast(self, event: BacktestEvent) -> None:
        """
        Broadcast event to all connected clients for this run.

        Args:
            event: Event to broadcast
        """
        if event.run_id not in self._connections:
            # No active connections for this run
            return

        event_dict = event.to_dict()
        connections = self._connections[event.run_id].copy()

        # Remove dead connections
        dead_connections = []

        for websocket in connections:
            try:
                await websocket.send_json(event_dict)
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    run_id=str(event.run_id),
                    event_type=event.event_type.value,
                    error=str(e),
                )
                dead_connections.append(websocket)

        # Clean up dead connections
        for websocket in dead_connections:
            self.unregister_connection(event.run_id, websocket)

    def get_connection_count(self, run_id: UUID) -> int:
        """
        Get number of active connections for a backtest run.

        Args:
            run_id: Backtest run UUID

        Returns:
            Number of active WebSocket connections
        """
        return len(self._connections.get(run_id, []))


# Global broadcaster instance
_broadcaster: Optional[BacktestEventBroadcaster] = None


def get_event_broadcaster() -> BacktestEventBroadcaster:
    """Get or create the global event broadcaster instance."""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = BacktestEventBroadcaster()
    return _broadcaster
