"""
RiskOverseerAgent - System-Wide Risk Monitoring

Responsibilities:
- Portfolio-level risk checks (VaR, exposure, correlation)
- Monitor for emergency stop conditions
- Emit emergency_stop and risk_alert events
- Coordinate system shutdown if necessary

Performance Target: <200ms risk calculation
"""

import asyncio
import time
from typing import Dict, Any, List, Optional

import numpy as np
import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class RiskOverseerAgent(BaseAgent):
    """
    Monitors system-wide risk and enforces emergency stops

    Risk Checks:
    1. Position Concentration - Max exposure per symbol
    2. Correlation - Portfolio diversification
    3. VaR (Value at Risk) - Maximum expected loss
    4. Total Exposure - Sum of all position sizes

    Emergency Stop Conditions:
    - Daily loss exceeds limit
    - Drawdown exceeds limit
    - Open positions exceed limit
    - VaR exceeds limit
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=8,  # Supervisory layer
        )

        # Configuration
        self.checks = config.get("checks", [
            "position_concentration",
            "correlation",
            "var",
            "exposure",
        ])
        self.check_frequency = config.get("check_frequency", 10)  # seconds
        self.auto_hedge = config.get("auto_hedge", False)

        # Emergency stop conditions
        self.emergency_conditions = config.get("emergency_stop_conditions", {})
        self.max_daily_loss = self.emergency_conditions.get("max_daily_loss", -1000.0)
        self.max_drawdown = self.emergency_conditions.get("max_drawdown", -0.15)  # 15%
        self.max_open_positions = self.emergency_conditions.get("max_open_positions", 10)

        # Portfolio state
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.daily_pnl = 0.0
        self.current_balance = 10000.0
        self.peak_balance = 10000.0

        # Risk metrics
        self.portfolio_var = 0.0
        self.portfolio_exposure = 0.0
        self.max_concentration = 0.0

        # Emergency state
        self.emergency_stop_active = False
        self.stop_reason: Optional[str] = None

        # Last check timestamp
        self.last_check = 0.0

        # Stats
        self.risk_alerts = 0
        self.emergency_stops = 0

    async def initialize(self) -> None:
        """Subscribe to events and start monitoring"""
        self.subscribe_to_event("trade_executed")
        self.subscribe_to_event("position_updated")
        self.subscribe_to_event("performance_alert")

        self.logger.info(
            "risk_overseer_initialized",
            checks=self.checks,
            max_daily_loss=self.max_daily_loss,
            max_drawdown=self.max_drawdown,
            max_positions=self.max_open_positions,
        )

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self.logger.info(
            "risk_overseer_cleanup",
            risk_alerts=self.risk_alerts,
            emergency_stops=self.emergency_stops,
            stop_active=self.emergency_stop_active,
        )

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "trade_executed":
                await self._on_trade_executed(event.data)

            elif event.event_type == "position_updated":
                await self._on_position_updated(event.data)

            elif event.event_type == "performance_alert":
                await self._on_performance_alert(event.data)

            # Periodic risk checks
            current_time = time.time()
            if current_time - self.last_check >= self.check_frequency:
                await self._perform_risk_checks()
                self.last_check = current_time

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_trade_executed(self, trade_data: Dict[str, Any]) -> None:
        """Track new position"""
        symbol = trade_data.get("symbol")
        action = trade_data.get("action")
        size = trade_data.get("position_size", 0.0)
        price = trade_data.get("fill_price", 0.0)

        self.open_positions[symbol] = {
            "symbol": symbol,
            "side": action,
            "size": size,
            "entry_price": price,
            "current_price": price,
            "unrealized_pnl": 0.0,
        }

        self.logger.debug(
            "position_tracked",
            symbol=symbol,
            size=size,
            total_positions=len(self.open_positions),
        )

    async def _on_position_updated(self, position_data: Dict[str, Any]) -> None:
        """Update position state"""
        symbol = position_data.get("symbol")
        status = position_data.get("status")

        if status == "CLOSED":
            # Remove from tracking
            pnl = position_data.get("pnl", 0.0)
            self.daily_pnl += pnl
            self.current_balance += pnl

            if symbol in self.open_positions:
                del self.open_positions[symbol]

            # Update peak
            if self.current_balance > self.peak_balance:
                self.peak_balance = self.current_balance

        elif status == "UPDATED":
            # Update unrealized P&L
            if symbol in self.open_positions:
                self.open_positions[symbol]["unrealized_pnl"] = position_data.get("unrealized_pnl", 0.0)
                self.open_positions[symbol]["current_price"] = position_data.get("current_price", 0.0)

    async def _on_performance_alert(self, alert_data: Dict[str, Any]) -> None:
        """
        Handle performance alert from PerformanceMonitorAgent

        May trigger emergency stop
        """
        alert_type = alert_data.get("type")
        severity = alert_data.get("severity")

        self.logger.warning(
            "performance_alert_received",
            alert_type=alert_type,
            severity=severity,
        )

        # Check if emergency stop needed
        if severity == "critical":
            await self._evaluate_emergency_stop(f"performance_alert_{alert_type}")

    async def _perform_risk_checks(self) -> None:
        """
        Perform all risk checks

        Checks portfolio-level risk and emits alerts if needed
        """
        start_time = time.time()

        risk_metrics = {}
        alerts = []

        # 1. Position Concentration
        if "position_concentration" in self.checks:
            concentration = self._check_position_concentration()
            risk_metrics["max_concentration"] = concentration

            if concentration > 0.3:  # More than 30% in single position
                alerts.append({
                    "type": "high_concentration",
                    "metric": "position_concentration",
                    "value": concentration,
                    "threshold": 0.3,
                    "severity": "medium",
                })

        # 2. Correlation
        if "correlation" in self.checks:
            correlation = self._check_correlation()
            risk_metrics["avg_correlation"] = correlation

            if correlation > 0.7:  # High correlation
                alerts.append({
                    "type": "high_correlation",
                    "metric": "correlation",
                    "value": correlation,
                    "threshold": 0.7,
                    "severity": "low",
                })

        # 3. VaR (Value at Risk)
        if "var" in self.checks:
            var = self._calculate_var()
            risk_metrics["var_95"] = var

            if var < -0.05 * self.current_balance:  # VaR > 5% of capital
                alerts.append({
                    "type": "high_var",
                    "metric": "var",
                    "value": var,
                    "threshold": -0.05 * self.current_balance,
                    "severity": "high",
                })

        # 4. Exposure
        if "exposure" in self.checks:
            exposure = self._calculate_exposure()
            risk_metrics["total_exposure"] = exposure

            if exposure > self.current_balance:  # Leverage > 1x
                alerts.append({
                    "type": "high_exposure",
                    "metric": "exposure",
                    "value": exposure,
                    "threshold": self.current_balance,
                    "severity": "medium",
                })

        # Store metrics in context
        await self.set_context("risk_metrics", str(risk_metrics), ttl=60)

        # Emit alerts
        for alert in alerts:
            self.risk_alerts += 1

            await self.publish_event(
                event_type="risk_alert",
                data={
                    **alert,
                    "risk_metrics": risk_metrics,
                    "timestamp": time.time(),
                },
                priority=EventPriority.HIGH,
            )

            self.logger.warning(
                "risk_alert",
                alert_type=alert["type"],
                value=alert["value"],
                threshold=alert["threshold"],
            )

        # Check emergency stop conditions
        await self._evaluate_emergency_stop("periodic_check")

        check_time = time.time() - start_time

        if check_time > 0.2:  # Warn if >200ms
            self.logger.warning(
                "risk_check_slow",
                check_time=check_time,
            )

    def _check_position_concentration(self) -> float:
        """
        Check position concentration

        Returns:
            Maximum position size as fraction of portfolio
        """
        if not self.open_positions or self.current_balance == 0:
            return 0.0

        max_position_value = max(
            abs(pos["size"]) for pos in self.open_positions.values()
        )

        concentration = max_position_value / self.current_balance

        return float(concentration)

    def _check_correlation(self) -> float:
        """
        Check average correlation between positions

        For simplicity, returns 0 (uncorrelated) if diverse symbols,
        1 (fully correlated) if same symbols

        In production, calculate actual correlation matrix
        """
        if len(self.open_positions) <= 1:
            return 0.0

        # Simplified: Check if all same symbol
        symbols = set(pos["symbol"] for pos in self.open_positions.values())

        if len(symbols) == 1:
            return 1.0  # All same symbol = fully correlated

        # Diverse symbols - assume low correlation
        return 0.2

    def _calculate_var(self, confidence: float = 0.95) -> float:
        """
        Calculate Value at Risk (VaR)

        VaR = Expected maximum loss at confidence level

        Args:
            confidence: Confidence level (0.95 = 95%)

        Returns:
            VaR (negative value)
        """
        if not self.open_positions:
            return 0.0

        # Simplified VaR calculation
        # In production: Use historical simulation or parametric VaR

        # Sum unrealized P&L
        total_unrealized = sum(
            pos.get("unrealized_pnl", 0.0) for pos in self.open_positions.values()
        )

        # Estimate portfolio volatility (assume 2% daily)
        portfolio_volatility = 0.02 * self.current_balance

        # VaR at confidence level (z-score for 95% = 1.645)
        z_score = 1.645 if confidence == 0.95 else 2.33

        var = -z_score * portfolio_volatility + total_unrealized

        return float(var)

    def _calculate_exposure(self) -> float:
        """
        Calculate total portfolio exposure

        Exposure = Sum of absolute position sizes

        Returns:
            Total exposure
        """
        if not self.open_positions:
            return 0.0

        total_exposure = sum(
            abs(pos["size"]) for pos in self.open_positions.values()
        )

        return float(total_exposure)

    async def _evaluate_emergency_stop(self, trigger: str) -> None:
        """
        Evaluate if emergency stop is needed

        Args:
            trigger: What triggered the evaluation
        """
        if self.emergency_stop_active:
            return  # Already stopped

        stop_conditions = []

        # 1. Daily loss limit
        if self.daily_pnl <= self.max_daily_loss:
            stop_conditions.append(f"daily_loss_{self.daily_pnl}")

        # 2. Drawdown limit
        if self.peak_balance > 0:
            drawdown = (self.current_balance - self.peak_balance) / self.peak_balance
            if drawdown <= self.max_drawdown:
                stop_conditions.append(f"drawdown_{drawdown:.2%}")

        # 3. Open positions limit
        if len(self.open_positions) >= self.max_open_positions:
            stop_conditions.append(f"max_positions_{len(self.open_positions)}")

        # Trigger emergency stop if any condition met
        if stop_conditions:
            await self._trigger_emergency_stop(stop_conditions, trigger)

    async def _trigger_emergency_stop(self, conditions: List[str], trigger: str) -> None:
        """
        Trigger emergency stop

        Emits emergency_stop event to halt all trading

        Args:
            conditions: List of conditions that triggered stop
            trigger: What evaluation triggered the stop
        """
        self.emergency_stop_active = True
        self.stop_reason = f"{trigger}:{','.join(conditions)}"
        self.emergency_stops += 1

        # Emit emergency stop event
        await self.publish_event(
            event_type="emergency_stop",
            data={
                "trigger": trigger,
                "conditions": conditions,
                "daily_pnl": self.daily_pnl,
                "current_balance": self.current_balance,
                "open_positions": len(self.open_positions),
                "timestamp": time.time(),
            },
            priority=EventPriority.CRITICAL,
        )

        # Store in context
        await self.set_context("emergency_stop_active", "true", ttl=3600)
        await self.set_context("stop_reason", self.stop_reason, ttl=3600)

        # Pause all agents (send pause command)
        await self.publish_event(
            event_type="pause_all_agents",
            data={"reason": self.stop_reason},
            priority=EventPriority.CRITICAL,
        )

        self.logger.critical(
            "emergency_stop_triggered",
            trigger=trigger,
            conditions=conditions,
            daily_pnl=self.daily_pnl,
            balance=self.current_balance,
            positions=len(self.open_positions),
        )

        # Optionally close all positions
        if self.auto_hedge:
            await self._close_all_positions()

    async def _close_all_positions(self) -> None:
        """
        Emergency close all positions

        Emits close_position events for all open positions
        """
        for symbol, position in self.open_positions.items():
            await self.publish_event(
                event_type="close_position",
                data={
                    "symbol": symbol,
                    "reason": "emergency_stop",
                    "size": position["size"],
                },
                priority=EventPriority.CRITICAL,
            )

            self.logger.warning(
                "emergency_position_close",
                symbol=symbol,
                size=position["size"],
            )
