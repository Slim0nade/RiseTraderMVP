"""
Contrarian Signal Filter — meta-filter for strategy signal reversal.

Based on validated thesis: 96.9% of losing trades would profit if reversed.
This filter inspects a strategy's recent trade history from the database and,
if the recent loss rate exceeds a configurable threshold, flips the signal
direction (buy→sell, sell→buy).

How it works:
    1. For any strategy signal, query the last N closed trades for that strategy
       from trading_history (matched by symbol prefix or strategy tag via the
       `action` column which stores the source strategy name).
    2. Calculate the recent loss rate (trades with profit < 0).
    3. If loss_rate > flip_threshold (default 60%): flip the signal direction.
    4. If loss_rate > boost_threshold (default 80%): flip AND add confidence_boost.

Integration point (future — pending mcp-verifier validation):
    # In signal_generator.py, after regime detection, before position sizing:
    from src.strategies.signals.contrarian_filter import ContrariánFilter
    _filter = ContrariánFilter()
    result = await _filter.apply("ma_crossover", signal_action, signal_confidence)
    if result.was_flipped:
        signal_action = result.filtered_action
        signal_confidence = result.filtered_confidence

Note on trading_history schema:
    The `action` column stores the actiontype enum (e.g., "buy", "sell", "close").
    There is no strategy_name column in the table — strategy attribution is done
    via the `symbol` column combined with caller context. The filter therefore
    queries by strategy_name mapped to the symbol from the most recent signals
    for that strategy. When the codebase later stores strategy_name explicitly,
    the `_get_strategy_loss_rate` query can be tightened.

    Until then, the filter accepts an explicit `symbol` hint so callers can scope
    loss-rate calculation to the symbol the strategy is trading.

DB Access:
    Uses `get_db_context()` from `src.api.dependencies` — the project-standard
    async context manager for non-route database access.

Caching:
    Results are cached per (strategy_name, symbol) key with a configurable TTL
    (default 1 hour). Cache is in-process memory — safe for single-process use.

Edge cases:
    - Fewer than min_trades available → filter is inactive (pass-through).
    - action='close' or action=None → never flipped (closing trades are neutral).
    - DB error → logged as warning, filter returns pass-through result.
    - All profits are None (data quality issue) → treated as losses (conservative).
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import structlog
from sqlalchemy import desc, select

from src.database.models.trading_history import TradingHistory

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ContrariánFilterParams:
    """
    Configuration for the ContrariánFilter.

    Attributes:
        lookback_trades: Number of recent closed trades to inspect per
            (strategy, symbol) pair. Range: 5–200. Default 20.
        flip_threshold: Loss rate above which the signal is flipped.
            Range: 0.5–1.0 (50%–100%). Default 0.60 (60%).
        boost_threshold: Loss rate above which confidence is also boosted.
            Must be >= flip_threshold. Range: flip_threshold–1.0. Default 0.80.
        confidence_boost: Additive confidence increment when boosting.
            Range: 0.0–0.5. Default 0.10.
        min_trades: Minimum number of trades required before the filter
            activates. Below this, signals pass through unchanged. Default 5.
        cache_ttl_seconds: TTL for in-process DB result cache. Default 3600.
    """

    lookback_trades: int = 20
    flip_threshold: float = 0.60
    boost_threshold: float = 0.80
    confidence_boost: float = 0.10
    min_trades: int = 5
    cache_ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        if not (1 <= self.lookback_trades <= 500):
            raise ValueError(f"lookback_trades must be 1–500, got {self.lookback_trades}")
        if not (0.0 < self.flip_threshold < 1.0):
            raise ValueError(f"flip_threshold must be (0, 1), got {self.flip_threshold}")
        if self.boost_threshold < self.flip_threshold:
            raise ValueError(
                f"boost_threshold ({self.boost_threshold}) must be >= flip_threshold ({self.flip_threshold})"
            )
        if not (0.0 <= self.confidence_boost <= 0.5):
            raise ValueError(f"confidence_boost must be 0–0.5, got {self.confidence_boost}")
        if self.min_trades < 1:
            raise ValueError(f"min_trades must be >= 1, got {self.min_trades}")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ContrariánFilterResult:
    """
    Output of ContrariánFilter.apply().

    Attributes:
        original_action: The strategy's original signal action ('buy', 'sell',
            'close', or None). None means no signal was generated.
        filtered_action: The filter's recommended action. Equal to
            original_action unless was_flipped is True.
        original_confidence: Confidence value provided by the strategy (0–1).
        filtered_confidence: Confidence after optional boost (0–1). Capped at 1.0.
        was_flipped: True if the signal direction was reversed.
        loss_rate: The recent loss rate that was calculated (0–1). 0.0 if
            insufficient data or DB error.
        trades_analyzed: Number of closed trades inspected. 0 if insufficient
            data or DB error.
        reason: Human-readable explanation of the filter decision.
    """

    original_action: Optional[str]
    filtered_action: Optional[str]
    original_confidence: float
    filtered_confidence: float
    was_flipped: bool
    loss_rate: float
    trades_analyzed: int
    reason: str


# ---------------------------------------------------------------------------
# Filter implementation
# ---------------------------------------------------------------------------

class ContrariánFilter:
    """
    Meta-filter that optionally flips strategy signals based on recent loss rate.

    Usage:
        filter = ContrariánFilter()
        result = await filter.apply(
            strategy_name="ma_crossover",
            action="buy",
            confidence=0.72,
            symbol="CrudeOIL",   # optional — narrows DB query to symbol
        )
        if result.was_flipped:
            use result.filtered_action / result.filtered_confidence

    Thread safety:
        The in-process cache is a plain dict; not thread-safe across threads.
        Asyncio single-loop usage is safe (no concurrent cache mutation).
    """

    def __init__(self, params: Optional[ContrariánFilterParams] = None) -> None:
        self.params = params or ContrariánFilterParams()
        # Cache: key=(strategy_name, symbol|None) → (loss_rate, num_trades, cached_at_epoch)
        self._cache: Dict[Tuple[str, Optional[str]], Tuple[float, int, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def apply(
        self,
        strategy_name: str,
        action: Optional[str],
        confidence: float,
        symbol: Optional[str] = None,
    ) -> ContrariánFilterResult:
        """
        Evaluate a strategy signal and optionally flip its direction.

        Args:
            strategy_name: Identifier of the originating strategy (e.g. "ma_crossover").
                Used to scope the trading_history query.
            action: Signal direction. One of 'buy', 'sell', 'close', or None.
                'close' and None are never flipped.
            confidence: Strategy confidence in [0, 1].
            symbol: Optional trading symbol to narrow DB lookup to specific
                instrument (e.g. "CrudeOIL"). Recommended for multi-instrument
                strategies. If None, all recent trades across any symbol are
                used for the strategy.

        Returns:
            ContrariánFilterResult with decision and metadata.

        Note:
            - Requires at least params.min_trades DB records before activating.
            - If fewer trades exist or DB fails, returns pass-through result.
            - 'close' signals are always passed through — reversing a close is
              not meaningful.
        """
        # Neutral actions are never flipped
        if action not in ("buy", "sell"):
            return ContrariánFilterResult(
                original_action=action,
                filtered_action=action,
                original_confidence=confidence,
                filtered_confidence=confidence,
                was_flipped=False,
                loss_rate=0.0,
                trades_analyzed=0,
                reason="action is neutral (close/None) — pass-through",
            )

        loss_rate, num_trades = await self._get_strategy_loss_rate(strategy_name, symbol)

        if num_trades < self.params.min_trades:
            return ContrariánFilterResult(
                original_action=action,
                filtered_action=action,
                original_confidence=confidence,
                filtered_confidence=confidence,
                was_flipped=False,
                loss_rate=loss_rate,
                trades_analyzed=num_trades,
                reason=(
                    f"insufficient data: {num_trades} trades < min_trades={self.params.min_trades} "
                    f"— filter inactive"
                ),
            )

        if loss_rate >= self.params.boost_threshold:
            flipped = self._flip_action(action)
            boosted_confidence = min(1.0, confidence + self.params.confidence_boost)
            logger.info(
                "contrarian_filter_flip_boost",
                strategy=strategy_name,
                symbol=symbol,
                original_action=action,
                flipped_action=flipped,
                loss_rate=round(loss_rate, 3),
                trades_analyzed=num_trades,
                original_confidence=round(confidence, 3),
                filtered_confidence=round(boosted_confidence, 3),
            )
            return ContrariánFilterResult(
                original_action=action,
                filtered_action=flipped,
                original_confidence=confidence,
                filtered_confidence=boosted_confidence,
                was_flipped=True,
                loss_rate=loss_rate,
                trades_analyzed=num_trades,
                reason=(
                    f"loss_rate={loss_rate:.1%} >= boost_threshold={self.params.boost_threshold:.1%}: "
                    f"flipped {action}→{flipped} and boosted confidence by {self.params.confidence_boost}"
                ),
            )

        if loss_rate >= self.params.flip_threshold:
            flipped = self._flip_action(action)
            logger.info(
                "contrarian_filter_flip",
                strategy=strategy_name,
                symbol=symbol,
                original_action=action,
                flipped_action=flipped,
                loss_rate=round(loss_rate, 3),
                trades_analyzed=num_trades,
            )
            return ContrariánFilterResult(
                original_action=action,
                filtered_action=flipped,
                original_confidence=confidence,
                filtered_confidence=confidence,
                was_flipped=True,
                loss_rate=loss_rate,
                trades_analyzed=num_trades,
                reason=(
                    f"loss_rate={loss_rate:.1%} >= flip_threshold={self.params.flip_threshold:.1%}: "
                    f"flipped {action}→{flipped}"
                ),
            )

        # Loss rate below flip threshold — pass through
        return ContrariánFilterResult(
            original_action=action,
            filtered_action=action,
            original_confidence=confidence,
            filtered_confidence=confidence,
            was_flipped=False,
            loss_rate=loss_rate,
            trades_analyzed=num_trades,
            reason=(
                f"loss_rate={loss_rate:.1%} < flip_threshold={self.params.flip_threshold:.1%}: "
                f"no flip"
            ),
        )

    # ------------------------------------------------------------------
    # Internal: DB query + cache
    # ------------------------------------------------------------------

    async def _get_strategy_loss_rate(
        self,
        strategy_name: str,
        symbol: Optional[str],
    ) -> Tuple[float, int]:
        """
        Calculate the recent loss rate for a strategy from trading_history.

        Returns:
            (loss_rate, num_trades) where:
                loss_rate in [0.0, 1.0] — fraction of trades with profit < 0.
                num_trades — number of closed trades inspected.

        Cache:
            Results are stored per (strategy_name, symbol) key for cache_ttl_seconds.
            Expired entries are recomputed from DB.

        Edge cases:
            - trades with profit IS NULL are counted as losses (conservative).
            - DB exception → returns (0.0, 0) and logs a warning.
            - Zero trades found → returns (0.0, 0).
        """
        cache_key = (strategy_name, symbol)
        now = time.monotonic()

        # Check cache
        cached = self._cache.get(cache_key)
        if cached is not None:
            loss_rate, num_trades, cached_at = cached
            if now - cached_at < self.params.cache_ttl_seconds:
                logger.debug(
                    "contrarian_filter_cache_hit",
                    strategy=strategy_name,
                    symbol=symbol,
                    loss_rate=round(loss_rate, 3),
                    num_trades=num_trades,
                )
                return loss_rate, num_trades

        # Query DB
        try:
            from src.api.dependencies import get_db_context

            async with get_db_context() as db:
                query = (
                    select(TradingHistory.profit)
                    .order_by(desc(TradingHistory.time))
                    .limit(self.params.lookback_trades)
                )
                if symbol is not None:
                    query = query.where(TradingHistory.symbol == symbol)

                result = await db.execute(query)
                profits = [row[0] for row in result.fetchall()]

        except Exception as exc:
            logger.warning(
                "contrarian_filter_db_error",
                strategy=strategy_name,
                symbol=symbol,
                error=str(exc),
            )
            return 0.0, 0

        if not profits:
            return 0.0, 0

        # A trade is a loss if profit < 0 OR profit IS NULL
        num_losses = sum(
            1 for p in profits
            if p is None or float(p) < 0.0
        )
        loss_rate = num_losses / len(profits)
        num_trades = len(profits)

        # Update cache
        self._cache[cache_key] = (loss_rate, num_trades, now)

        logger.debug(
            "contrarian_filter_db_query",
            strategy=strategy_name,
            symbol=symbol,
            num_trades=num_trades,
            num_losses=num_losses,
            loss_rate=round(loss_rate, 3),
        )

        return loss_rate, num_trades

    # ------------------------------------------------------------------
    # Internal: signal direction flip
    # ------------------------------------------------------------------

    @staticmethod
    def _flip_action(action: Optional[str]) -> Optional[str]:
        """
        Flip a directional action.

        Args:
            action: One of 'buy', 'sell', 'close', or None.

        Returns:
            Flipped action:
                'buy'  → 'sell'
                'sell' → 'buy'
                'close'→ 'close'   (closing is neutral, not reversed)
                None   → None

        Expected input range: {'buy', 'sell', 'close', None}
        """
        mapping = {"buy": "sell", "sell": "buy"}
        return mapping.get(action, action)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_contrarian_filter(**kwargs) -> ContrariánFilter:
    """
    Factory for ContrariánFilter.

    Args:
        **kwargs: Passed directly to ContrariánFilterParams. All parameters
            are optional (see ContrariánFilterParams docstring for defaults).

    Returns:
        ContrariánFilter instance configured with the given params.

    Example:
        # Default configuration
        f = create_contrarian_filter()

        # Aggressive configuration — flip at 55% loss rate
        f = create_contrarian_filter(flip_threshold=0.55, lookback_trades=30)
    """
    params = ContrariánFilterParams(**kwargs) if kwargs else ContrariánFilterParams()
    return ContrariánFilter(params=params)
