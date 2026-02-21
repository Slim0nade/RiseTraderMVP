"""
PerformanceMonitorAgent - Real-time Performance Tracking

Responsibilities:
- Track P&L in real-time
- Calculate performance metrics (Sharpe, drawdown, win rate)
- Emit performance_alert on threshold breaches
- Emit performance_report periodically

Performance Target: <100ms metrics calculation
"""

import asyncio
import time
from collections import deque
from typing import Dict, Any, List, Optional

import numpy as np
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class PerformanceMonitorAgent(BaseAgent):
    """
    Monitors trading performance in real-time

    Metrics Tracked:
    1. P&L (realized and unrealized)
    2. Sharpe Ratio
    3. Maximum Drawdown
    4. Win Rate
    5. Profit Factor
    6. Average Trade Duration
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
        self.tracked_metrics = config.get("metrics", [
            "pnl",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
        ])
        self.update_frequency = config.get("update_frequency", 5)  # seconds
        self.report_frequency = config.get("report_frequency", 3600)  # 1 hour

        # Alert thresholds
        self.alert_thresholds = config.get("alert_thresholds", {})
        self.daily_loss_threshold = self.alert_thresholds.get("daily_loss", -500.0)
        self.drawdown_threshold = self.alert_thresholds.get("drawdown", -0.10)  # 10%

        # Database
        self.db_url = config.get("database_url", "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader")
        self.engine = None
        self.async_session = None

        # Performance state
        self.starting_balance = 10000.0
        self.current_balance = 10000.0
        self.peak_balance = 10000.0
        self.daily_pnl = 0.0

        # Trade history
        self.closed_trades: List[Dict[str, Any]] = []
        self.open_positions: Dict[str, Dict[str, Any]] = {}

        # Returns history for Sharpe
        self.returns_history = deque(maxlen=1000)

        # Update tracking
        self.last_update = 0.0
        self.last_report = 0.0

        # Stats
        self.alerts_sent = 0
        self.reports_sent = 0

    async def initialize(self) -> None:
        """Initialize database and subscribe to events"""
        self.subscribe_to_event("trade_executed")
        self.subscribe_to_event("position_updated")

        # Setup database
        try:
            self.engine = create_async_engine(
                self.db_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
            )
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Load historical performance
            await self._load_performance_state()

            self.logger.info(
                "performance_monitor_initialized",
                metrics=self.tracked_metrics,
                starting_balance=self.starting_balance,
                current_balance=self.current_balance,
            )

        except Exception as e:
            self.logger.error("initialization_failed", error=str(e), exc_info=True)
            raise

    async def cleanup(self) -> None:
        """Cleanup resources"""
        try:
            if self.engine:
                await self.engine.dispose()

            self.logger.info(
                "performance_monitor_cleanup",
                alerts_sent=self.alerts_sent,
                reports_sent=self.reports_sent,
                final_balance=self.current_balance,
                total_pnl=self.current_balance - self.starting_balance,
            )

        except Exception as e:
            self.logger.error("cleanup_failed", error=str(e))

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "trade_executed":
                await self._on_trade_executed(event.data)

            elif event.event_type == "position_updated":
                await self._on_position_updated(event.data)

            # Check if time to update metrics
            current_time = time.time()

            if current_time - self.last_update >= self.update_frequency:
                await self._update_metrics()
                self.last_update = current_time

            # Check if time to send report
            if current_time - self.last_report >= self.report_frequency:
                await self._send_performance_report()
                self.last_report = current_time

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_trade_executed(self, trade_data: Dict[str, Any]) -> None:
        """Track new trade execution"""
        symbol = trade_data.get("symbol")
        action = trade_data.get("action")
        size = trade_data.get("position_size", 0.0)
        price = trade_data.get("fill_price", 0.0)

        # Add to open positions
        self.open_positions[symbol] = {
            "symbol": symbol,
            "side": action,
            "size": size,
            "entry_price": price,
            "entry_time": time.time(),
            "unrealized_pnl": 0.0,
        }

        self.logger.debug(
            "trade_tracked",
            symbol=symbol,
            action=action,
            size=size,
            price=price,
        )

    async def _on_position_updated(self, position_data: Dict[str, Any]) -> None:
        """Update position (close, modify, etc.)"""
        symbol = position_data.get("symbol")
        status = position_data.get("status")

        if status == "CLOSED":
            # Calculate realized P&L
            pnl = position_data.get("pnl", 0.0)
            exit_price = position_data.get("exit_price", 0.0)

            # Get position details
            position = self.open_positions.pop(symbol, {})
            entry_price = position.get("entry_price", 0.0)
            entry_time = position.get("entry_time", time.time())
            duration = time.time() - entry_time

            # Record closed trade
            trade_record = {
                "symbol": symbol,
                "side": position.get("side"),
                "size": position.get("size"),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "duration": duration,
                "closed_at": time.time(),
            }

            self.closed_trades.append(trade_record)

            # Update balances
            self.current_balance += pnl
            self.daily_pnl += pnl

            # Update peak
            if self.current_balance > self.peak_balance:
                self.peak_balance = self.current_balance

            # Calculate return
            if self.starting_balance > 0:
                trade_return = pnl / self.starting_balance
                self.returns_history.append(trade_return)

            # Store in context
            await self.set_context("current_balance", self.current_balance)
            await self.set_context("daily_pnl", self.daily_pnl)

            self.logger.info(
                "position_closed_tracked",
                symbol=symbol,
                pnl=pnl,
                duration=duration,
                current_balance=self.current_balance,
            )

        elif status == "UPDATED":
            # Update unrealized P&L
            if symbol in self.open_positions:
                unrealized_pnl = position_data.get("unrealized_pnl", 0.0)
                self.open_positions[symbol]["unrealized_pnl"] = unrealized_pnl

    async def _update_metrics(self) -> None:
        """Calculate and update performance metrics"""
        metrics = {}

        # 1. P&L
        metrics["realized_pnl"] = self.daily_pnl
        metrics["unrealized_pnl"] = sum(
            pos.get("unrealized_pnl", 0.0) for pos in self.open_positions.values()
        )
        metrics["total_pnl"] = metrics["realized_pnl"] + metrics["unrealized_pnl"]

        # 2. Sharpe Ratio
        metrics["sharpe_ratio"] = self._calculate_sharpe_ratio()

        # 3. Maximum Drawdown
        metrics["max_drawdown"] = self._calculate_max_drawdown()

        # 4. Win Rate
        metrics["win_rate"] = self._calculate_win_rate()

        # 5. Profit Factor
        metrics["profit_factor"] = self._calculate_profit_factor()

        # 6. Trade count
        metrics["total_trades"] = len(self.closed_trades)
        metrics["open_positions"] = len(self.open_positions)

        # 7. Current balance
        metrics["current_balance"] = self.current_balance
        metrics["peak_balance"] = self.peak_balance

        # Store in context
        await self.set_context("performance_metrics", str(metrics), ttl=3600)

        # Check for alerts
        await self._check_alert_thresholds(metrics)

    def _calculate_sharpe_ratio(self) -> float:
        """
        Calculate Sharpe Ratio

        Sharpe = (Mean Return - Risk-Free Rate) / Std(Returns)

        Returns:
            Annualized Sharpe Ratio
        """
        if len(self.returns_history) < 10:
            return 0.0

        returns = np.array(self.returns_history)

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Risk-free rate (assume 0 for simplicity)
        risk_free_rate = 0.0

        sharpe = (mean_return - risk_free_rate) / std_return

        # Annualize (assuming daily returns)
        annualized_sharpe = sharpe * np.sqrt(252)

        return float(annualized_sharpe)

    def _calculate_max_drawdown(self) -> float:
        """
        Calculate Maximum Drawdown

        Max DD = (Trough - Peak) / Peak

        Returns:
            Maximum drawdown as percentage (negative value)
        """
        if self.peak_balance == 0:
            return 0.0

        drawdown = (self.current_balance - self.peak_balance) / self.peak_balance

        return float(drawdown)

    def _calculate_win_rate(self) -> float:
        """
        Calculate Win Rate

        Win Rate = Winning Trades / Total Trades

        Returns:
            Win rate (0-1)
        """
        if not self.closed_trades:
            return 0.0

        winning_trades = sum(1 for trade in self.closed_trades if trade.get("pnl", 0) > 0)
        total_trades = len(self.closed_trades)

        win_rate = winning_trades / total_trades

        return float(win_rate)

    def _calculate_profit_factor(self) -> float:
        """
        Calculate Profit Factor

        Profit Factor = Gross Profit / Gross Loss

        Returns:
            Profit factor (>1 is profitable)
        """
        if not self.closed_trades:
            return 1.0

        gross_profit = sum(
            trade.get("pnl", 0) for trade in self.closed_trades if trade.get("pnl", 0) > 0
        )

        gross_loss = abs(sum(
            trade.get("pnl", 0) for trade in self.closed_trades if trade.get("pnl", 0) < 0
        ))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 1.0

        profit_factor = gross_profit / gross_loss

        return float(profit_factor)

    async def _check_alert_thresholds(self, metrics: Dict[str, float]) -> None:
        """
        Check if any metrics breach alert thresholds

        Args:
            metrics: Current performance metrics
        """
        alerts = []

        # Check daily loss
        if metrics["realized_pnl"] <= self.daily_loss_threshold:
            alerts.append({
                "type": "daily_loss_exceeded",
                "metric": "daily_pnl",
                "value": metrics["realized_pnl"],
                "threshold": self.daily_loss_threshold,
                "severity": "high",
            })

        # Check drawdown
        if metrics["max_drawdown"] <= self.drawdown_threshold:
            alerts.append({
                "type": "drawdown_exceeded",
                "metric": "max_drawdown",
                "value": metrics["max_drawdown"],
                "threshold": self.drawdown_threshold,
                "severity": "critical",
            })

        # Emit alerts
        for alert in alerts:
            self.alerts_sent += 1

            await self.publish_event(
                event_type="performance_alert",
                data={
                    **alert,
                    "metrics": metrics,
                    "timestamp": time.time(),
                },
                priority=EventPriority.CRITICAL,
            )

            self.logger.warning(
                "performance_alert",
                alert_type=alert["type"],
                value=alert["value"],
                threshold=alert["threshold"],
            )

    async def _send_performance_report(self) -> None:
        """Send periodic performance report"""
        self.reports_sent += 1

        # Calculate all metrics
        metrics = {
            "realized_pnl": self.daily_pnl,
            "unrealized_pnl": sum(
                pos.get("unrealized_pnl", 0.0) for pos in self.open_positions.values()
            ),
            "current_balance": self.current_balance,
            "peak_balance": self.peak_balance,
            "sharpe_ratio": self._calculate_sharpe_ratio(),
            "max_drawdown": self._calculate_max_drawdown(),
            "win_rate": self._calculate_win_rate(),
            "profit_factor": self._calculate_profit_factor(),
            "total_trades": len(self.closed_trades),
            "open_positions": len(self.open_positions),
        }

        # Add trade statistics
        if self.closed_trades:
            pnls = [trade.get("pnl", 0) for trade in self.closed_trades]
            durations = [trade.get("duration", 0) for trade in self.closed_trades]

            metrics["avg_pnl"] = float(np.mean(pnls))
            metrics["avg_duration"] = float(np.mean(durations))
            metrics["best_trade"] = float(np.max(pnls))
            metrics["worst_trade"] = float(np.min(pnls))

        # Emit report
        await self.publish_event(
            event_type="performance_report",
            data={
                "metrics": metrics,
                "report_period": self.report_frequency,
                "timestamp": time.time(),
            },
            priority=EventPriority.LOW,
        )

        self.logger.info(
            "performance_report_sent",
            pnl=metrics["realized_pnl"],
            balance=metrics["current_balance"],
            sharpe=metrics["sharpe_ratio"],
            win_rate=metrics["win_rate"],
        )

    async def _load_performance_state(self) -> None:
        """Load historical performance from database/context"""
        try:
            # Load from context
            balance = await self.get_context("current_balance")
            if balance:
                self.current_balance = float(balance)
                self.peak_balance = self.current_balance

            daily_pnl = await self.get_context("daily_pnl")
            if daily_pnl:
                self.daily_pnl = float(daily_pnl)

            self.logger.info(
                "performance_state_loaded",
                balance=self.current_balance,
                daily_pnl=self.daily_pnl,
            )

        except Exception as e:
            self.logger.error("load_state_failed", error=str(e))
