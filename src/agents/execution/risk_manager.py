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
import json
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

        # Kelly Criterion trade-stats cache: {symbol: (metrics_dict, cached_at_epoch)}
        self._kelly_stats_cache: Dict[str, tuple] = {}

        # Correlation cache — key: frozenset({sym_a, sym_b}), value: (corr_float, cached_at_epoch)
        self._corr_cache: Dict[frozenset, tuple] = {}

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
        is_valid, rejection_reason, corr_size_multiplier = await self._validate_trade(signal_data)

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

        # Apply correlation-based size reduction on top of regime multiplier.
        # corr_size_multiplier = 0.5 when corr > 0.7 with any existing position.
        if corr_size_multiplier != 1.0:
            existing_mult = signal_data.get("position_size_multiplier", 1.0)
            signal_data = {
                **signal_data,
                "position_size_multiplier": existing_mult * corr_size_multiplier,
            }
            self.logger.warning(
                "position_size_reduced_correlation",
                symbol=symbol,
                corr_multiplier=corr_size_multiplier,
                effective_multiplier=signal_data["position_size_multiplier"],
            )

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

    async def _validate_trade(
        self, signal_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str], float]:
        """
        Perform all risk validation checks

        Returns:
            (is_valid, rejection_reason, size_multiplier)
            size_multiplier = 0.5 when correlation > 0.7, else 1.0
        """
        symbol = signal_data.get("symbol")
        action = signal_data.get("action")

        # 1. Check daily loss limit
        if self.daily_pnl <= -abs(self.max_daily_loss):
            return False, "daily_loss_limit_exceeded", 1.0

        # 2. Check max open positions
        if len(self.open_positions) >= self.max_open_positions:
            return False, "max_open_positions_exceeded", 1.0

        # 3. Check if already have position in this symbol
        existing_position = self._get_position(symbol)
        if existing_position:
            # Don't open opposing position
            if action == "BUY" and existing_position["side"] == "SELL":
                return False, "opposing_position_exists", 1.0
            elif action == "SELL" and existing_position["side"] == "BUY":
                return False, "opposing_position_exists", 1.0

            # Don't add to existing position (for now)
            if action == existing_position["side"]:
                return False, "position_already_exists", 1.0

        # 4. Check correlation with existing positions
        # Returns (block, reduce_50pct): block=True if corr >0.7 AND we choose to block,
        # reduce_50pct=True if corr >0.7 (we reduce size instead of blocking).
        corr_block, corr_reduce = await self._check_correlation(symbol)
        if corr_block:
            return False, "high_correlation_with_existing", 1.0
        size_multiplier = 0.5 if corr_reduce else 1.0

        # 5. Check account balance
        if self.account_balance <= 0:
            return False, "insufficient_balance", 1.0

        # 6. Check signal confidence
        min_confidence = 0.5
        if signal_data.get("confidence", 0) < min_confidence:
            return False, "low_signal_confidence", 1.0

        return True, None, size_multiplier

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
            position_size = await self._kelly_criterion_size(signal_data)

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

    async def _kelly_criterion_size(self, signal_data: Dict[str, Any]) -> float:
        """
        Kelly Criterion position sizing using real historical trade statistics.

        Formula: f* = (p * (b + 1) - 1) / b
        Where:
        - p = actual win rate from trade history (not ML confidence)
        - b = actual avg_win / avg_loss ratio from trade history

        If fewer than 30 historical trades exist for the symbol, returns minimum
        size (0.01 * account_balance) — never falls back to hardcoded assumptions.

        Trade stats are cached per symbol for 1 hour.
        """
        from src.api.dependencies import get_db_context
        from src.database.repositories.trading_history_repository import TradingHistoryRepository

        symbol = signal_data.get("symbol")
        minimum_size = 0.01 * self.account_balance

        # Check 1-hour cache
        now = time.time()
        cached = self._kelly_stats_cache.get(symbol)
        if cached is not None:
            metrics, cached_at = cached
            if now - cached_at < 3600:
                self.logger.debug("kelly_stats_cache_hit", symbol=symbol)
            else:
                cached = None  # Expired

        if cached is None:
            async with get_db_context() as db:
                repo = TradingHistoryRepository(db)
                metrics = await repo.get_performance_metrics(symbol=symbol)
            self._kelly_stats_cache[symbol] = (metrics, now)

        total_trades = metrics.get("total_trades", 0)

        if total_trades < 30:
            self.logger.info(
                "kelly_insufficient_history",
                symbol=symbol,
                total_trades=total_trades,
                required=30,
                fallback="minimum_size",
            )
            return minimum_size

        # win_rate from DB is a percentage (e.g. 55.0 = 55%) — convert to decimal
        win_rate = metrics["win_rate"] / 100.0
        avg_win = metrics.get("average_win", 0.0)
        avg_loss = metrics.get("average_loss", 0.0)

        if avg_loss == 0.0:
            self.logger.info(
                "kelly_zero_avg_loss",
                symbol=symbol,
                fallback="minimum_size",
            )
            return minimum_size

        win_loss_ratio = avg_win / avg_loss

        self.logger.info(
            "kelly_real_stats",
            symbol=symbol,
            total_trades=total_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            win_loss_ratio=win_loss_ratio,
        )

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

    async def _check_correlation(self, symbol: str) -> tuple[bool, bool]:
        """
        Check if opening a position in `symbol` would create high correlation
        with existing open positions.

        Uses rolling 20-day Pearson correlation from D1 candles (same math as
        RiskOverseerAgent._check_correlation). Results are cached per symbol-pair
        for 1 hour.

        Decision:
          - Correlation > 0.7 with any existing position → reduce size 50%
            (corr_reduce=True, block=False)
          - No existing positions or correlation <= 0.7 → allow full size
          - Insufficient D1 data (<21 candles) → allow full size with warning

        Returns:
            (block, reduce_50pct)
            block=True  → reject trade entirely
            reduce_50pct=True → allow trade at 50% position size
        """
        import math
        import numpy as np
        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        if not self.open_positions:
            return False, False

        existing_symbols = list({pos["symbol"] for pos in self.open_positions if pos["symbol"] != symbol})
        if not existing_symbols:
            return False, False

        now = time.time()
        reduce = False

        for existing_sym in existing_symbols:
            pair_key = frozenset({symbol, existing_sym})

            # Check 1-hour cache
            if pair_key in self._corr_cache:
                cached_corr, cached_at = self._corr_cache[pair_key]
                if (now - cached_at) < 3600:
                    self.logger.debug(
                        "correlation_cache_hit",
                        symbol_a=symbol,
                        symbol_b=existing_sym,
                        correlation=cached_corr,
                    )
                    if not math.isnan(cached_corr) and cached_corr > self.max_correlation:
                        reduce = True
                    continue

            # Fetch D1 candles for both symbols
            try:
                async with get_db_context() as db:
                    repo = MarketDataRepository(db)
                    rows_new = await repo.get_latest_ticks(symbol=symbol, timeframe="D1", limit=21)
                    rows_existing = await repo.get_latest_ticks(symbol=existing_sym, timeframe="D1", limit=21)
            except Exception as exc:
                self.logger.warning(
                    "correlation_db_fetch_failed",
                    symbol=symbol,
                    existing_sym=existing_sym,
                    error=str(exc),
                )
                # Allow trade with warning on DB error
                self._corr_cache[pair_key] = (float("nan"), now)
                continue

            if len(rows_new) < 21 or len(rows_existing) < 21:
                self.logger.warning(
                    "correlation_insufficient_d1_data",
                    symbol=symbol,
                    symbol_rows=len(rows_new),
                    existing_sym=existing_sym,
                    existing_rows=len(rows_existing),
                    required=21,
                    action="allow_with_warning",
                )
                self._corr_cache[pair_key] = (float("nan"), now)
                continue

            # rows are newest-first — reverse to oldest-first for chronological returns
            closes_new = [float(r.close) for r in reversed(rows_new)]
            closes_existing = [float(r.close) for r in reversed(rows_existing)]

            returns_new = np.array(
                [np.log(closes_new[i + 1] / closes_new[i]) for i in range(len(closes_new) - 1)]
            )
            returns_existing = np.array(
                [np.log(closes_existing[i + 1] / closes_existing[i]) for i in range(len(closes_existing) - 1)]
            )

            corr = float(np.corrcoef(returns_new, returns_existing)[0, 1])
            self._corr_cache[pair_key] = (corr, now)

            self.logger.info(
                "pre_trade_correlation_computed",
                proposed_symbol=symbol,
                existing_symbol=existing_sym,
                correlation=corr,
                threshold=self.max_correlation,
                reduce_size=corr > self.max_correlation,
            )

            if not math.isnan(corr) and corr > self.max_correlation:
                reduce = True

        # We reduce size (50%) rather than blocking outright — lets correlated
        # trades through but at half size to limit concentrated risk.
        return False, reduce

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
                self.open_positions = json.loads(open_positions) if isinstance(open_positions, str) else []

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
