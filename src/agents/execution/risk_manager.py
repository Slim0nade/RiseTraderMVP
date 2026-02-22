"""
RiskManagerAgent - Pre-Trade Risk Validation and Position Sizing

Responsibilities:
- Validate trading signals against risk limits
- Calculate position size using Kelly Criterion
- Check: max position size, daily loss, open positions, correlation
- Emit trade_validated or trade_rejected events

Performance Target: <30ms risk validation
"""

import asyncio
import time
from typing import Dict, Any, Optional, List

import structlog
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class RiskManagerAgent(BaseAgent):
    """
    Validates trades and calculates position sizing

    Risk Checks:
    1. Position size limits
    2. Daily loss limits
    3. Maximum open positions
    4. Position correlation
    5. Account balance checks

    Position Sizing Methods:
    - Kelly Criterion: Optimal bet size based on win rate
    - Fixed: Fixed percentage of capital
    - Volatility-adjusted: Size based on volatility
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=2,  # High priority - critical risk control
        )

        # Risk limits
        self.max_position_size = config.get("max_position_size", 10.0)
        self.max_daily_loss = config.get("max_daily_loss", 1000.0)
        self.max_open_positions = config.get("max_open_positions", 5)
        self.max_correlation = config.get("max_correlation", 0.7)

        # Position sizing
        self.sizing_method = config.get("position_sizing_method", "kelly")
        self.risk_per_trade = config.get("risk_per_trade", 0.02)  # 2%

        # Database
        self.db_url = config.get("database_url", "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader")
        self.engine = None
        self.async_session = None

        # Current state
        self.open_positions: List[Dict[str, Any]] = []
        self.daily_pnl = 0.0
        self.account_balance = 10000.0  # Starting balance

        # Stats
        self.trades_validated = 0
        self.trades_rejected = 0
        self.rejection_reasons: Dict[str, int] = {}

    async def initialize(self) -> None:
        """Initialize database and subscribe to events"""
        self.subscribe_to_event("signal_generated")
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

            # Load current positions and daily P&L
            await self._load_current_state()

            self.logger.info(
                "risk_manager_initialized",
                max_position_size=self.max_position_size,
                max_daily_loss=self.max_daily_loss,
                max_open_positions=self.max_open_positions,
                sizing_method=self.sizing_method,
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
                "risk_manager_cleanup",
                trades_validated=self.trades_validated,
                trades_rejected=self.trades_rejected,
                rejection_reasons=self.rejection_reasons,
            )

        except Exception as e:
            self.logger.error("cleanup_failed", error=str(e))

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "signal_generated":
                await self._on_signal_generated(event.data)

            elif event.event_type == "trade_executed":
                await self._on_trade_executed(event.data)

            elif event.event_type == "position_updated":
                await self._on_position_updated(event.data)

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_signal_generated(self, signal_data: Dict[str, Any]) -> None:
        """
        Validate trading signal

        Performs all risk checks and calculates position size
        """
        start_time = time.time()

        symbol = signal_data.get("symbol")
        action = signal_data.get("action")
        confidence = signal_data.get("confidence", 0.0)

        self.logger.debug(
            "validating_signal",
            symbol=symbol,
            action=action,
            confidence=confidence,
        )

        # Run risk checks
        is_valid, rejection_reason = await self._validate_trade(signal_data)

        if not is_valid:
            self.trades_rejected += 1

            # Track rejection reason
            if rejection_reason not in self.rejection_reasons:
                self.rejection_reasons[rejection_reason] = 0
            self.rejection_reasons[rejection_reason] += 1

            # Emit rejection
            await self.publish_event(
                event_type="trade_rejected",
                data={
                    "signal": signal_data,
                    "reason": rejection_reason,
                    "timestamp": time.time(),
                },
                priority=EventPriority.HIGH,
            )

            self.logger.warning(
                "trade_rejected",
                symbol=symbol,
                reason=rejection_reason,
            )
            return

        # Calculate position size
        position_size = await self._calculate_position_size(signal_data)

        self.trades_validated += 1

        # Emit validated trade
        validated_trade = {
            **signal_data,
            "position_size": position_size,
            "validated_at": time.time(),
            "account_balance": self.account_balance,
            "open_positions_count": len(self.open_positions),
        }

        await self.publish_event(
            event_type="trade_validated",
            data=validated_trade,
            priority=EventPriority.HIGH,
        )

        # Store in context
        await self.set_context(
            f"validated_trade_{symbol}",
            validated_trade,
            ttl=300,
        )

        processing_time = time.time() - start_time

        self.logger.info(
            "trade_validated",
            symbol=symbol,
            action=action,
            position_size=position_size,
            processing_time=processing_time,
        )

    async def _validate_trade(self, signal_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Perform all risk validation checks

        Returns:
            (is_valid, rejection_reason)
        """
        symbol = signal_data.get("symbol")
        action = signal_data.get("action")

        # 1. Check daily loss limit
        if self.daily_pnl <= -abs(self.max_daily_loss):
            return False, "daily_loss_limit_exceeded"

        # 2. Check max open positions
        if len(self.open_positions) >= self.max_open_positions:
            return False, "max_open_positions_exceeded"

        # 3. Check if already have position in this symbol
        existing_position = self._get_position(symbol)
        if existing_position:
            # Don't open opposing position
            if action == "BUY" and existing_position["side"] == "SELL":
                return False, "opposing_position_exists"
            elif action == "SELL" and existing_position["side"] == "BUY":
                return False, "opposing_position_exists"

            # Don't add to existing position (for now)
            if action == existing_position["side"]:
                return False, "position_already_exists"

        # 4. Check correlation with existing positions
        if not await self._check_correlation(symbol):
            return False, "high_correlation_with_existing"

        # 5. Check account balance
        if self.account_balance <= 0:
            return False, "insufficient_balance"

        # 6. Check signal confidence
        min_confidence = 0.5
        if signal_data.get("confidence", 0) < min_confidence:
            return False, "low_signal_confidence"

        return True, None

    async def _calculate_position_size(self, signal_data: Dict[str, Any]) -> float:
        """
        Calculate optimal position size

        Methods:
        - kelly: Kelly Criterion
        - fixed: Fixed percentage
        - volatility: Volatility-adjusted

        All methods are subject to a hard 2% account risk cap enforced here.
        """
        confidence = signal_data.get("confidence", 0.5)

        if self.sizing_method == "kelly":
            position_size = self._kelly_criterion_size(confidence)

        elif self.sizing_method == "fixed":
            position_size = self._fixed_size()

        elif self.sizing_method == "volatility":
            position_size = await self._volatility_adjusted_size(signal_data)

        else:
            # Default to fixed
            position_size = self._fixed_size()

        # Apply regime-based position size multiplier (e.g., 0.5x for low_volatility)
        size_multiplier = signal_data.get("position_size_multiplier", 1.0)
        if size_multiplier != 1.0:
            self.logger.info(
                "position_size_regime_scaled",
                original=position_size,
                multiplier=size_multiplier,
                scaled=position_size * size_multiplier,
            )
            position_size = position_size * size_multiplier

        # Hard 2% cap — final enforcement regardless of sizing method
        max_risk = self.account_balance * self.risk_per_trade
        if position_size > max_risk:
            self.logger.warning(
                "position_size_capped",
                original=position_size,
                capped=max_risk,
                method=self.sizing_method,
            )
            position_size = max_risk

        assert position_size <= max_risk, (
            f"Position size {position_size} exceeds 2% risk cap {max_risk}"
        )

        return position_size

    def _kelly_criterion_size(self, confidence: float) -> float:
        """
        Kelly Criterion position sizing

        Formula: f* = (p * (b + 1) - 1) / b
        Where:
        - p = probability of win (confidence)
        - b = win/loss ratio (assume 1.5)
        """
        win_rate = confidence
        win_loss_ratio = 1.5  # Assume 1.5:1 risk-reward

        # Kelly fraction
        kelly_fraction = (win_rate * (win_loss_ratio + 1) - 1) / win_loss_ratio

        # Use fractional Kelly (25% Kelly) for safety
        fractional_kelly = kelly_fraction * 0.25

        # Convert to position size (as percentage of balance).
        # Hard cap at risk_per_trade (2%) — never exceed 2% account risk.
        position_size = max(0.01, min(fractional_kelly, self.risk_per_trade))

        # Multiply by balance
        dollar_size = position_size * self.account_balance

        # Apply max position size limit
        return min(dollar_size, self.max_position_size)

    def _fixed_size(self) -> float:
        """Fixed percentage position sizing"""
        return min(
            self.risk_per_trade * self.account_balance,
            self.max_position_size,
        )

    async def _volatility_adjusted_size(self, signal_data: Dict[str, Any]) -> float:
        """
        Volatility-adjusted position sizing

        Larger positions in low volatility, smaller in high volatility
        """
        # Get recent volatility from shared context
        symbol = signal_data.get("symbol")
        volatility = await self.get_shared_context(
            "regime_detection",
            f"volatility_{symbol}",
            default=0.02,  # 2% default
        )

        try:
            volatility = float(volatility)
        except (TypeError, ValueError):
            volatility = 0.02

        # Target volatility (2%)
        target_vol = 0.02

        # Adjust size inversely to volatility
        vol_adjustment = target_vol / max(volatility, 0.001)

        # Base size
        base_size = self.risk_per_trade * self.account_balance

        # Adjusted size
        adjusted_size = base_size * vol_adjustment

        # Hard cap at 2% account risk regardless of volatility adjustment
        max_risk_amount = self.risk_per_trade * self.account_balance
        adjusted_size = min(adjusted_size, max_risk_amount)

        # Apply limits
        return max(0.01, min(adjusted_size, self.max_position_size))

    async def _check_correlation(self, symbol: str) -> bool:
        """
        Check if symbol is highly correlated with existing positions

        Returns:
            True if correlation is acceptable, False if too high
        """
        if not self.open_positions:
            return True

        # For now, simple check: don't allow multiple positions in same symbol
        # In production, calculate actual correlation coefficients
        for position in self.open_positions:
            if position["symbol"] == symbol:
                return False

        return True

    def _get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get existing position for symbol"""
        for position in self.open_positions:
            if position["symbol"] == symbol:
                return position
        return None

    async def _on_trade_executed(self, trade_data: Dict[str, Any]) -> None:
        """Update state when trade is executed"""
        symbol = trade_data.get("symbol")
        action = trade_data.get("action")
        size = trade_data.get("position_size", 0.0)
        price = trade_data.get("fill_price", 0.0)

        # Add to open positions
        position = {
            "symbol": symbol,
            "side": action,
            "size": size,
            "entry_price": price,
            "opened_at": time.time(),
        }

        self.open_positions.append(position)

        # Update context
        await self.set_context("open_positions", self.open_positions)

        self.logger.info(
            "position_opened",
            symbol=symbol,
            action=action,
            size=size,
            price=price,
            total_positions=len(self.open_positions),
        )

    async def _on_position_updated(self, position_data: Dict[str, Any]) -> None:
        """Update position state (close, modify, etc.)"""
        symbol = position_data.get("symbol")
        status = position_data.get("status")

        if status == "CLOSED":
            # Remove from open positions
            self.open_positions = [
                p for p in self.open_positions if p["symbol"] != symbol
            ]

            # Update daily P&L
            pnl = position_data.get("pnl", 0.0)
            self.daily_pnl += pnl
            self.account_balance += pnl

            await self.set_context("daily_pnl", self.daily_pnl)
            await self.set_context("account_balance", self.account_balance)

            self.logger.info(
                "position_closed",
                symbol=symbol,
                pnl=pnl,
                daily_pnl=self.daily_pnl,
                balance=self.account_balance,
            )

    async def _load_current_state(self) -> None:
        """Load current positions and P&L from database"""
        try:
            # Load from context first (faster)
            open_positions = await self.get_context("open_positions")
            if open_positions:
                self.open_positions = eval(open_positions) if isinstance(open_positions, str) else []

            daily_pnl = await self.get_context("daily_pnl")
            if daily_pnl:
                self.daily_pnl = float(daily_pnl)

            balance = await self.get_context("account_balance")
            if balance:
                self.account_balance = float(balance)

            self.logger.info(
                "state_loaded",
                open_positions=len(self.open_positions),
                daily_pnl=self.daily_pnl,
                balance=self.account_balance,
            )

        except Exception as e:
            self.logger.error("load_state_failed", error=str(e))
