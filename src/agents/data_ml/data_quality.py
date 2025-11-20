"""
DataQualityAgent - Data Pipeline Health Monitoring

Responsibilities:
- Monitor data quality issues from MarketDataAgent
- Track data pipeline health metrics
- Emit data_pipeline_alert on critical issues
- Maintain data quality dashboard metrics

Performance Target: <50ms issue processing
"""

import asyncio
import time
from collections import deque
from typing import Dict, Any, Optional

import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class DataQualityAgent(BaseAgent):
    """
    Monitors data pipeline health and quality

    Tracked Metrics:
    1. Data validation success rate
    2. Missing data gaps
    3. Latency (time from tick to processing)
    4. Data source uptime
    5. Anomaly detection

    Alerts:
    - High rejection rate
    - Extended data gaps
    - High latency
    - Data source failure
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=7,  # Supervisory layer
        )

        # Configuration
        self.alert_thresholds = {
            "rejection_rate": 0.1,  # 10%
            "data_gap_seconds": 60,  # 1 minute
            "latency_ms": 1000,  # 1 second
        }

        # Metrics tracking
        self.ticks_received = 0
        self.ticks_validated = 0
        self.ticks_rejected = 0
        self.rejection_reasons: Dict[str, int] = {}

        # Latency tracking
        self.latency_history = deque(maxlen=100)

        # Last tick timestamp per symbol
        self.last_tick_time: Dict[str, float] = {}

        # Alerts sent
        self.alerts_sent = 0

    async def initialize(self) -> None:
        """Subscribe to data quality events"""
        self.subscribe_to_event("new_tick")
        self.subscribe_to_event("data_quality_issue")

        self.logger.info(
            "data_quality_agent_initialized",
            thresholds=self.alert_thresholds,
        )

    async def cleanup(self) -> None:
        """Cleanup resources"""
        rejection_rate = self.ticks_rejected / max(self.ticks_received, 1)

        self.logger.info(
            "data_quality_agent_cleanup",
            ticks_received=self.ticks_received,
            ticks_validated=self.ticks_validated,
            ticks_rejected=self.ticks_rejected,
            rejection_rate=rejection_rate,
            alerts_sent=self.alerts_sent,
        )

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "new_tick":
                await self._on_new_tick(event.data)

            elif event.event_type == "data_quality_issue":
                await self._on_quality_issue(event.data)

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_new_tick(self, tick_data: Dict[str, Any]) -> None:
        """
        Track validated tick

        Updates metrics and checks for data gaps
        """
        self.ticks_received += 1
        self.ticks_validated += 1

        symbol = tick_data.get("symbol")
        tick_timestamp = tick_data.get("timestamp", time.time())

        # Calculate latency
        if isinstance(tick_timestamp, (int, float)):
            latency = time.time() - tick_timestamp
            self.latency_history.append(latency)

            # Check latency threshold
            if latency > self.alert_thresholds["latency_ms"] / 1000:
                await self._send_alert(
                    "high_latency",
                    {
                        "symbol": symbol,
                        "latency_seconds": latency,
                        "threshold": self.alert_thresholds["latency_ms"] / 1000,
                    },
                )

        # Check for data gaps
        if symbol in self.last_tick_time:
            gap = time.time() - self.last_tick_time[symbol]

            if gap > self.alert_thresholds["data_gap_seconds"]:
                await self._send_alert(
                    "data_gap",
                    {
                        "symbol": symbol,
                        "gap_seconds": gap,
                        "threshold": self.alert_thresholds["data_gap_seconds"],
                    },
                )

        self.last_tick_time[symbol] = time.time()

    async def _on_quality_issue(self, issue_data: Dict[str, Any]) -> None:
        """
        Handle data quality issue

        Tracks rejection reasons and rates
        """
        self.ticks_received += 1
        self.ticks_rejected += 1

        reason = issue_data.get("reason", "unknown")

        # Track rejection reasons
        if reason not in self.rejection_reasons:
            self.rejection_reasons[reason] = 0
        self.rejection_reasons[reason] += 1

        # Calculate rejection rate
        rejection_rate = self.ticks_rejected / self.ticks_received

        # Check if rejection rate too high
        if rejection_rate > self.alert_thresholds["rejection_rate"]:
            await self._send_alert(
                "high_rejection_rate",
                {
                    "rejection_rate": rejection_rate,
                    "threshold": self.alert_thresholds["rejection_rate"],
                    "total_rejected": self.ticks_rejected,
                    "total_received": self.ticks_received,
                    "top_reasons": dict(
                        sorted(
                            self.rejection_reasons.items(),
                            key=lambda x: x[1],
                            reverse=True,
                        )[:5]
                    ),
                },
            )

        self.logger.warning(
            "data_quality_issue",
            reason=reason,
            rejection_rate=rejection_rate,
        )

    async def _send_alert(self, alert_type: str, data: Dict[str, Any]) -> None:
        """
        Send data pipeline alert

        Args:
            alert_type: Type of alert
            data: Alert data
        """
        self.alerts_sent += 1

        await self.publish_event(
            event_type="data_pipeline_alert",
            data={
                "alert_type": alert_type,
                **data,
                "timestamp": time.time(),
            },
            priority=EventPriority.HIGH,
        )

        self.logger.warning(
            "data_pipeline_alert",
            alert_type=alert_type,
            **data,
        )
