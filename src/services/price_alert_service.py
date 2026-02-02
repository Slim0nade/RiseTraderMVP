"""
Price Alert Service (T052-T057)

Monitors configured price levels for open positions and emits SSE alerts
when prices breach configured thresholds.

Supports:
- Liquidity sweep detection (stop hunting avoidance)
- Breakeven price alerts
- Key support/resistance levels
- Custom price alerts
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.optimization import AlertDirection, AlertType, PriceAlert
from src.database.repositories.optimization_repository import OptimizationRepository
from src.utils.sse_events import get_sse_manager

logger = structlog.get_logger(__name__)

# Alert check interval in seconds
MONITOR_INTERVAL = 5.0

# Singleton instance
_price_alert_service: Optional["PriceAlertService"] = None


class PriceAlertService:
    """
    Service for managing and monitoring price alerts.

    Provides:
    - Alert CRUD operations
    - Real-time price monitoring
    - SSE event emission on alert triggers
    - Automatic cleanup on position close
    """

    def __init__(self, db: AsyncSession, price_fetcher=None):
        """
        Initialize the price alert service.

        Args:
            db: Async database session
            price_fetcher: Callable to get current prices (symbol -> price)
        """
        self.db = db
        self.repo = OptimizationRepository(db)
        self._price_fetcher = price_fetcher
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # In-memory cache for faster alert checking
        self._active_alerts: Dict[int, List[PriceAlert]] = {}  # ticket -> alerts
        self._last_cache_update: Optional[datetime] = None

    async def start(self) -> None:
        """Start the price monitoring loop."""
        if self._running:
            logger.warning("price_alert_service_already_running")
            return

        self._running = True
        await self._refresh_cache()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("price_alert_service_started", interval=MONITOR_INTERVAL)

    async def stop(self) -> None:
        """Stop the price monitoring loop."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("price_alert_service_stopped")

    async def set_price_alert(
        self,
        ticket: int,
        alert_type: str,
        price_level: float,
        direction: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PriceAlert:
        """
        Set a new price alert for a position (T053).

        Args:
            ticket: MT4 position ticket number
            alert_type: Type of alert (liquidity_sweep, breakeven, key_level, custom)
            price_level: Price level to monitor
            direction: Trigger direction (above, below)
            metadata: Additional alert data

        Returns:
            Created PriceAlert instance
        """
        alert = await self.repo.create_alert(
            ticket=ticket,
            alert_type=alert_type,
            price_level=price_level,
            direction=direction,
            metadata=metadata,
        )
        await self.db.commit()

        # Update cache
        if ticket not in self._active_alerts:
            self._active_alerts[ticket] = []
        self._active_alerts[ticket].append(alert)

        logger.info(
            "price_alert_created",
            alert_id=str(alert.id),
            ticket=ticket,
            type=alert_type,
            level=price_level,
            direction=direction,
        )

        return alert

    async def set_multiple_alerts(
        self,
        ticket: int,
        alerts: List[Dict[str, Any]],
    ) -> List[PriceAlert]:
        """
        Set multiple alerts for a position in batch.

        Args:
            ticket: MT4 position ticket
            alerts: List of alert configs with keys: alert_type, price_level, direction, metadata

        Returns:
            List of created alerts
        """
        created = []
        for config in alerts:
            alert = await self.repo.create_alert(
                ticket=ticket,
                alert_type=config["alert_type"],
                price_level=config["price_level"],
                direction=config["direction"],
                metadata=config.get("metadata"),
            )
            created.append(alert)

        await self.db.commit()

        # Update cache
        if ticket not in self._active_alerts:
            self._active_alerts[ticket] = []
        self._active_alerts[ticket].extend(created)

        logger.info("price_alerts_batch_created", ticket=ticket, count=len(created))

        return created

    async def get_alerts_for_ticket(self, ticket: int) -> List[PriceAlert]:
        """
        Get all active alerts for a position (T054).

        Args:
            ticket: MT4 position ticket

        Returns:
            List of active PriceAlert instances
        """
        return await self.repo.get_active_alerts(ticket=ticket)

    async def get_all_active_alerts(self) -> List[PriceAlert]:
        """Get all active (untriggered) alerts."""
        return await self.repo.get_active_alerts()

    async def get_alert_by_id(self, alert_id: UUID) -> Optional[PriceAlert]:
        """Get a specific alert by ID."""
        query = select(PriceAlert).where(PriceAlert.id == alert_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def delete_alert(self, alert_id: UUID) -> bool:
        """Delete a specific alert."""
        alert = await self.get_alert_by_id(alert_id)
        if not alert:
            return False

        # Remove from cache
        if alert.ticket in self._active_alerts:
            self._active_alerts[alert.ticket] = [
                a for a in self._active_alerts[alert.ticket] if a.id != alert_id
            ]

        await self.db.delete(alert)
        await self.db.commit()

        logger.info("price_alert_deleted", alert_id=str(alert_id))
        return True

    async def clear_alerts_for_ticket(self, ticket: int) -> int:
        """
        Clear all alerts for a position (T055).

        Called when position is closed.

        Args:
            ticket: MT4 position ticket

        Returns:
            Number of alerts deleted
        """
        deleted = await self.repo.delete_alerts_for_ticket(ticket)
        await self.db.commit()

        # Remove from cache
        if ticket in self._active_alerts:
            del self._active_alerts[ticket]

        logger.info("price_alerts_cleared", ticket=ticket, deleted=deleted)

        return deleted

    async def check_level_breach(
        self,
        alert: PriceAlert,
        current_price: float,
    ) -> bool:
        """
        Check if price has breached the alert level (T050).

        Args:
            alert: The price alert to check
            current_price: Current market price

        Returns:
            True if price breached the level in configured direction
        """
        level = float(alert.price_level)

        if alert.direction == AlertDirection.ABOVE.value:
            return current_price >= level
        elif alert.direction == AlertDirection.BELOW.value:
            return current_price <= level

        return False

    async def trigger_alert(
        self,
        alert: PriceAlert,
        current_price: float,
    ) -> None:
        """
        Trigger an alert and emit SSE event (T057).

        Args:
            alert: The triggered alert
            current_price: Current price that triggered the alert
        """
        # Mark as triggered in DB
        await self.repo.trigger_alert(alert.id)
        await self.db.commit()

        # Remove from cache
        if alert.ticket in self._active_alerts:
            self._active_alerts[alert.ticket] = [
                a for a in self._active_alerts[alert.ticket] if a.id != alert.id
            ]

        # Emit SSE event
        sse_manager = await get_sse_manager()
        await sse_manager.emit_price_alert(
            ticket=alert.ticket,
            alert_type=alert.alert_type,
            price_level=float(alert.price_level),
            current_price=current_price,
            direction=alert.direction,
        )

        logger.info(
            "price_alert_triggered",
            alert_id=str(alert.id),
            ticket=alert.ticket,
            type=alert.alert_type,
            level=float(alert.price_level),
            current_price=current_price,
        )

    async def _refresh_cache(self) -> None:
        """Refresh the in-memory alert cache from database."""
        alerts = await self.repo.get_active_alerts()

        self._active_alerts = {}
        for alert in alerts:
            if alert.ticket not in self._active_alerts:
                self._active_alerts[alert.ticket] = []
            self._active_alerts[alert.ticket].append(alert)

        self._last_cache_update = datetime.now(timezone.utc)

        logger.debug(
            "price_alert_cache_refreshed",
            total_alerts=len(alerts),
            unique_tickets=len(self._active_alerts),
        )

    async def _monitor_loop(self) -> None:
        """
        Main monitoring loop (T056).

        Polls every 5 seconds, checks price levels, triggers alerts.
        """
        logger.info("price_alert_monitor_loop_started")

        while self._running:
            try:
                await self._check_all_alerts()
            except Exception as e:
                logger.error("price_alert_monitor_error", error=str(e), exc_info=True)

            await asyncio.sleep(MONITOR_INTERVAL)

    async def _check_all_alerts(self) -> None:
        """Check all active alerts against current prices."""
        if not self._price_fetcher:
            return

        # Get unique symbols from open positions
        # For now, we fetch price per ticket (could optimize to fetch per symbol)
        for ticket, alerts in list(self._active_alerts.items()):
            if not alerts:
                continue

            try:
                # Get current price for this position's symbol
                current_price = await self._price_fetcher(ticket)

                if current_price is None:
                    continue

                # Check each alert
                for alert in list(alerts):
                    if await self.check_level_breach(alert, current_price):
                        await self.trigger_alert(alert, current_price)

            except Exception as e:
                logger.warning(
                    "price_alert_check_failed",
                    ticket=ticket,
                    error=str(e),
                )

    # =========================================================================
    # Autonomous Monitoring (T067-T069)
    # =========================================================================

    async def detect_fast_move(
        self,
        ticket: int,
        entry_price: float,
        current_price: float,
        atr: float,
        time_window_minutes: int = 5,
        atr_multiplier: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Detect rapid price movement exceeding ATR threshold (T067).

        A "fast move" is detected when price changes by more than the
        specified ATR multiplier within the time window.

        Args:
            ticket: Position ticket number
            entry_price: Position entry price or window start price
            current_price: Current market price
            atr: Average True Range value
            time_window_minutes: Time window for move detection
            atr_multiplier: Threshold as multiple of ATR (default 2.0)

        Returns:
            Detection result with move details
        """
        move_size = abs(current_price - entry_price)
        direction = "up" if current_price > entry_price else "down"

        # Calculate threshold
        threshold = atr * atr_multiplier

        # Handle edge case of zero ATR
        if atr <= 0:
            atr_multiple = float("inf") if move_size > 0 else 0
            detected = move_size > 0
        else:
            atr_multiple = move_size / atr
            detected = move_size >= threshold

        result = {
            "detected": detected,
            "ticket": ticket,
            "entry_price": entry_price,
            "current_price": current_price,
            "move_size": move_size,
            "direction": direction,
            "atr": atr,
            "atr_multiplier": atr_multiplier,
            "atr_multiple": atr_multiple,
            "threshold": threshold,
            "time_window_minutes": time_window_minutes,
        }

        if detected:
            # Add suggestion (T069: no auto-execution)
            result["suggestion"] = (
                f"Fast move detected: {direction} {move_size:.4f} "
                f"({atr_multiple:.1f}x ATR) in {time_window_minutes} min. "
                f"Consider adjusting stop loss or taking partial profits."
            )
            logger.info(
                "fast_move_detected",
                ticket=ticket,
                direction=direction,
                move_size=move_size,
                atr_multiple=atr_multiple,
            )

        return result

    async def detect_liquidity_sweep(
        self,
        ticket: int,
        support_level: float,
        resistance_level: float,
        recent_low: float,
        recent_high: float,
        current_price: float,
        direction: str,
        min_penetration: float = 0.05,
    ) -> Dict[str, Any]:
        """
        Detect liquidity sweep (stop hunting) patterns (T068).

        A liquidity sweep occurs when price briefly penetrates a key level
        to trigger stops, then quickly reverses back into the range.

        Args:
            ticket: Position ticket number
            support_level: Key support level
            resistance_level: Key resistance level
            recent_low: Recent low price
            recent_high: Recent high price
            current_price: Current market price
            direction: Trade direction ("long" or "short")
            min_penetration: Minimum penetration depth to consider

        Returns:
            Detection result with sweep details
        """
        result = {
            "detected": False,
            "ticket": ticket,
            "support_level": support_level,
            "resistance_level": resistance_level,
            "recent_low": recent_low,
            "recent_high": recent_high,
            "current_price": current_price,
            "direction": direction,
        }

        # Check for support sweep (price went below support then recovered)
        if recent_low < support_level:
            penetration_depth = support_level - recent_low
            if penetration_depth >= min_penetration:
                # Check if price recovered back above support
                if current_price > support_level:
                    result["detected"] = True
                    result["sweep_type"] = "support_sweep"
                    result["sweep_level"] = support_level
                    result["penetration_depth"] = penetration_depth
                    result["suggestion"] = (
                        f"Liquidity sweep below support at {support_level:.4f}. "
                        f"Penetrated {penetration_depth:.4f} then recovered. "
                        f"Stops may have been hit - consider re-entry opportunity."
                    )
                    logger.info(
                        "liquidity_sweep_detected",
                        ticket=ticket,
                        sweep_type="support_sweep",
                        level=support_level,
                        penetration=penetration_depth,
                    )

        # Check for resistance sweep (price went above resistance then fell)
        elif recent_high > resistance_level:
            penetration_depth = recent_high - resistance_level
            if penetration_depth >= min_penetration:
                # Check if price fell back below resistance
                if current_price < resistance_level:
                    result["detected"] = True
                    result["sweep_type"] = "resistance_sweep"
                    result["sweep_level"] = resistance_level
                    result["penetration_depth"] = penetration_depth
                    result["suggestion"] = (
                        f"Liquidity sweep above resistance at {resistance_level:.4f}. "
                        f"Penetrated {penetration_depth:.4f} then fell back. "
                        f"Short stops may have been hit - consider re-entry opportunity."
                    )
                    logger.info(
                        "liquidity_sweep_detected",
                        ticket=ticket,
                        sweep_type="resistance_sweep",
                        level=resistance_level,
                        penetration=penetration_depth,
                    )

        return result

    async def _emit_fast_move_alert(
        self,
        ticket: int,
        result: Dict[str, Any],
    ) -> None:
        """
        Emit SSE event for fast move detection.

        Args:
            ticket: Position ticket number
            result: Detection result from detect_fast_move()
        """
        sse_manager = await get_sse_manager()
        await sse_manager.emit(
            "fast_move",
            {
                "ticket": ticket,
                "direction": result["direction"],
                "move_size": result["move_size"],
                "atr_multiple": result["atr_multiple"],
                "current_price": result["current_price"],
                "suggestion": result.get("suggestion"),
            },
        )

    async def _emit_liquidity_sweep_alert(
        self,
        ticket: int,
        result: Dict[str, Any],
    ) -> None:
        """
        Emit SSE event for liquidity sweep detection.

        Args:
            ticket: Position ticket number
            result: Detection result from detect_liquidity_sweep()
        """
        sse_manager = await get_sse_manager()
        await sse_manager.emit(
            "liquidity_sweep",
            {
                "ticket": ticket,
                "sweep_type": result["sweep_type"],
                "sweep_level": result["sweep_level"],
                "penetration_depth": result["penetration_depth"],
                "current_price": result["current_price"],
                "suggestion": result.get("suggestion"),
            },
        )

    def set_price_fetcher(self, fetcher) -> None:
        """
        Set the price fetcher callback.

        Args:
            fetcher: Async callable that takes ticket -> returns current price
        """
        self._price_fetcher = fetcher

    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running

    @property
    def active_alert_count(self) -> int:
        """Get total active alerts."""
        return sum(len(alerts) for alerts in self._active_alerts.values())


async def get_price_alert_service(db: AsyncSession) -> PriceAlertService:
    """
    Get or create the price alert service singleton.

    Args:
        db: Database session

    Returns:
        PriceAlertService instance
    """
    global _price_alert_service

    if _price_alert_service is None:
        _price_alert_service = PriceAlertService(db)

    return _price_alert_service


async def shutdown_price_alert_service() -> None:
    """Shutdown the price alert service."""
    global _price_alert_service

    if _price_alert_service:
        await _price_alert_service.stop()
        _price_alert_service = None
