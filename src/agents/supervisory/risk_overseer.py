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
import math
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

        # Correlation cache — key: frozenset of symbols, value: (corr_value, computed_at)
        self._corr_cache: Dict[frozenset, float] = {}
        self._corr_cache_time: Dict[frozenset, float] = {}

        # VaR realized-vol cache — key: frozenset of symbols, value: (realized_vol, computed_at)
        self._var_vol_cache: Dict[frozenset, tuple] = {}

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
            correlation = await self._check_correlation()
            risk_metrics["avg_correlation"] = correlation

            if math.isnan(correlation):
                self.logger.warning(
                    "correlation_nan_insufficient_data",
                    symbols=[pos["symbol"] for pos in self.open_positions.values()],
                    message="Correlation check skipped — fewer than 21 D1 candles for at least one symbol",
                )

            if correlation > 0.85:  # Critical correlation — near-identical instruments
                alerts.append({
                    "type": "high_correlation",
                    "metric": "correlation",
                    "value": correlation,
                    "threshold": 0.85,
                    "severity": "critical",
                })
            elif correlation > 0.7:  # Warning correlation — significant overlap
                alerts.append({
                    "type": "high_correlation",
                    "metric": "correlation",
                    "value": correlation,
                    "threshold": 0.7,
                    "severity": "warning",
                })

        # 3. VaR (Value at Risk)
        if "var" in self.checks:
            var = await self._calculate_var()
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

    async def _check_correlation(self) -> float:
        """
        Check average pairwise Pearson correlation between open position symbols.

        Uses rolling 20-day log returns from D1 candles fetched from the database.
        Returns NaN if any symbol has fewer than 21 D1 candles (20 returns).
        Results are cached for 1 hour per symbol-set.

        Returns:
            Average pairwise Pearson correlation, or NaN if insufficient data.
        """
        if len(self.open_positions) <= 1:
            return 0.0

        symbols = list(set(pos["symbol"] for pos in self.open_positions.values()))

        if len(symbols) == 1:
            return 1.0

        cache_key = frozenset(symbols)
        now = time.time()
        if cache_key in self._corr_cache and (now - self._corr_cache_time[cache_key]) < 3600:
            cached = self._corr_cache[cache_key]
            self.logger.debug("correlation_cache_hit", symbols=symbols, correlation=cached)
            return cached

        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        returns_by_symbol: Dict[str, np.ndarray] = {}
        async with get_db_context() as db:
            repo = MarketDataRepository(db)
            for sym in symbols:
                rows = await repo.get_latest_ticks(symbol=sym, timeframe="D1", limit=21)
                if len(rows) < 21:
                    self.logger.warning(
                        "correlation_insufficient_data",
                        symbol=sym,
                        rows_available=len(rows),
                        rows_required=21,
                    )
                    return float("nan")
                # rows are newest-first — reverse to oldest-first for chronological returns
                closes = [float(r.close) for r in reversed(rows)]
                log_returns = np.array(
                    [np.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]
                )
                returns_by_symbol[sym] = log_returns

        correlations = []
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                r1 = returns_by_symbol[symbols[i]]
                r2 = returns_by_symbol[symbols[j]]
                corr = float(np.corrcoef(r1, r2)[0, 1])
                correlations.append(corr)
                self.logger.debug(
                    "pairwise_correlation",
                    symbol_a=symbols[i],
                    symbol_b=symbols[j],
                    correlation=corr,
                )

        if not correlations:
            return 0.0

        avg_corr = float(np.mean(correlations))

        self._corr_cache[cache_key] = avg_corr
        self._corr_cache_time[cache_key] = now

        self.logger.info(
            "correlation_computed",
            symbols=symbols,
            avg_correlation=avg_corr,
            pairs=len(correlations),
        )

        return avg_corr

    async def _calculate_var(self, confidence: float = 0.95) -> float:
        """
        Calculate Value at Risk (VaR) using realized rolling volatility from real D1 candles.

        For each open-position symbol, fetches 21 D1 candles and computes 20 log returns.
        If multiple positions are open, the portfolio vol is the position-value-weighted
        average of per-symbol realized volatilities.

        Conservative fallback: any symbol with < 21 D1 candles uses 5% daily vol (not 2%).
        Results are cached per symbol-set for 1 hour.

        Args:
            confidence: Confidence level (0.95 = 95%, 0.99 = 99%)

        Returns:
            VaR (negative value).
        """
        if not self.open_positions:
            return 0.0

        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        CONSERVATIVE_VOL = 0.05  # 5% daily — used when insufficient history

        symbols = list(set(pos["symbol"] for pos in self.open_positions.values()))
        cache_key = frozenset(symbols)
        now = time.time()

        cached = self._var_vol_cache.get(cache_key)
        if cached is not None:
            realized_vol, cached_at = cached
            if now - cached_at < 3600:
                self.logger.debug("var_vol_cache_hit", symbols=symbols, realized_vol=realized_vol)
                # Compute VaR from cached vol
                portfolio_value = self.current_balance
                z_score = 1.645 if confidence == 0.95 else 2.33
                holding_period = 1  # 1-day VaR
                var = -z_score * realized_vol * math.sqrt(holding_period) * portfolio_value
                return float(var)

        vol_by_symbol: Dict[str, float] = {}
        async with get_db_context() as db:
            repo = MarketDataRepository(db)
            for sym in symbols:
                rows = await repo.get_latest_ticks(symbol=sym, timeframe="D1", limit=21)
                if len(rows) < 21:
                    self.logger.warning(
                        "var_insufficient_candles",
                        symbol=sym,
                        rows_available=len(rows),
                        rows_required=21,
                        fallback_vol=CONSERVATIVE_VOL,
                    )
                    vol_by_symbol[sym] = CONSERVATIVE_VOL
                else:
                    # rows newest-first — reverse to oldest-first
                    closes = [float(r.close) for r in reversed(rows)]
                    log_returns = np.array(
                        [np.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]
                    )
                    realized_std = float(np.std(log_returns, ddof=1))
                    vol_by_symbol[sym] = realized_std
                    self.logger.debug(
                        "var_realized_vol",
                        symbol=sym,
                        realized_std=realized_std,
                        n_returns=len(log_returns),
                    )

        # Portfolio vol: weight by position size as fraction of total absolute exposure
        total_exposure = sum(abs(pos["size"]) for pos in self.open_positions.values())
        if total_exposure == 0.0:
            realized_vol = CONSERVATIVE_VOL
        else:
            weighted_vol = 0.0
            for pos in self.open_positions.values():
                sym = pos["symbol"]
                weight = abs(pos["size"]) / total_exposure
                weighted_vol += weight * vol_by_symbol.get(sym, CONSERVATIVE_VOL)
            realized_vol = weighted_vol

        self._var_vol_cache[cache_key] = (realized_vol, now)

        self.logger.info(
            "var_computed",
            symbols=symbols,
            realized_vol=realized_vol,
            old_assumed_vol=0.02,
            improvement_factor=round(realized_vol / 0.02, 2) if realized_vol else None,
        )

        portfolio_value = self.current_balance
        z_score = 1.645 if confidence == 0.95 else 2.33
        holding_period = 1  # 1-day VaR
        var = -z_score * realized_vol * math.sqrt(holding_period) * portfolio_value

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
