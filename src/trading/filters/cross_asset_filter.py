"""
CrossAssetFilter — Confirms or rejects signals using related instrument price action.

Before placing a trade, checks whether correlated assets agree with the proposed
direction.  Two categories of related assets apply different rules:

  "confirm" assets:
    These must agree directionally.  If a BUY is proposed on CrudeOIL but BRENT_OIL
    is falling, the signal is rejected (score < -0.3 threshold).

  "context" assets:
    USA500 / equity indices provide macroeconomic color.  A crude sell confirmed
    by falling equities (demand destruction narrative) earns a mild positive bump.
    Context assets alone cannot reject a trade.

Score range: -1.0 (strong reject) to +1.0 (strong confirm).
Trade passes if final score > -0.3.

Asset groups:
    CrudeOIL:  confirm=[BRENT_OIL], context=[USA500]
    BRENT_OIL: confirm=[CrudeOIL],  context=[USA500]
    USA500:    confirm=[],           context=[CrudeOIL, BRENT_OIL]
    GBPJPY:    confirm=[],           context=[USA500]

Symbols not in the asset groups pass unchecked (score=0.0, reason="no_group").

DB access: lazy-imports get_db_context + MarketDataRepository (same pattern as
live_trading_service.py) to avoid circular imports at module load time.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REJECT_THRESHOLD = -0.3

# Scores awarded per individual asset check
_CONFIRM_AGREE_SCORE = 0.5   # confirm asset moving with us
_CONFIRM_DISAGREE_SCORE = -0.7  # confirm asset moving against us (strong reject)

# Context (USA500 / equity) score contributions
_CONTEXT_BOTH_DOWN_SCORE = 0.3   # oil sell + equity sell → demand destruction
_CONTEXT_OIL_UP_EQ_DOWN_SCORE = 0.2  # oil buy + equity down → supply shock
_CONTEXT_BOTH_UP_SCORE = 0.1    # risk-on, mild confirm for oil buy
_CONTEXT_OIL_DOWN_EQ_UP_SCORE = -0.2  # oil sell + equity up → deflationary

# Directional thresholds for classifying a move as meaningful
_DIRECTION_UP_THRESHOLD = 0.1
_DIRECTION_DOWN_THRESHOLD = -0.1

# How many H1 bars to look back
_DEFAULT_LOOKBACK = 10

# Rate-of-change normalisation cap (±5% move maps to ±1.0)
_ROC_CAP = 0.05


# ---------------------------------------------------------------------------
# CrossAssetFilter
# ---------------------------------------------------------------------------


class CrossAssetFilter:
    """
    Checks whether related instruments confirm or contradict a proposed signal.

    Score > 0:   confirming — proceed.
    Score < -0.3: rejecting — discard the signal.
    Score 0..-0.3: neutral — proceed with caution (not blocked).

    Symbols not listed in _asset_groups return (0.0, "no_group") — no filtering.
    """

    _asset_groups: Dict[str, Dict[str, List[str]]] = {
        "CrudeOIL": {"confirm": ["BRENT_OIL"], "context": ["USA500"]},
        "BRENT_OIL": {"confirm": ["CrudeOIL"], "context": ["USA500"]},
        "USA500": {"confirm": [], "context": ["CrudeOIL", "BRENT_OIL"]},
        "GBPJPY": {"confirm": [], "context": ["USA500"]},
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_confirmation(
        self,
        symbol: str,
        action: str,
        lookback_bars: int = _DEFAULT_LOOKBACK,
    ) -> Tuple[float, str]:
        """
        Fetch the latest H1 closes for all related assets and compute a
        confirmation score.

        Args:
            symbol:        Instrument being traded (e.g. "CrudeOIL").
            action:        Proposed direction — "BUY" or "SELL".
            lookback_bars: Number of H1 bars used for rate-of-change calculation.

        Returns:
            (confirmation_score, reason_string)

            confirmation_score: float in [-1.0, +1.0].
            reason_string:      human-readable log annotation.

            Trade passes if confirmation_score > -0.3.
        """
        group = self._asset_groups.get(symbol)
        if group is None:
            return 0.0, "no_group"

        action_upper = action.upper()
        confirm_syms: List[str] = group.get("confirm", [])
        context_syms: List[str] = group.get("context", [])

        all_related = list(set(confirm_syms + context_syms))
        if not all_related:
            return 0.0, "no_related_assets"

        # Fetch closes for all related symbols in parallel.
        closes_map: Dict[str, Optional[List[float]]] = {}
        fetch_tasks = {
            rel_sym: self._fetch_closes(rel_sym, lookback_bars + 5)
            for rel_sym in all_related
        }
        results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)
        for rel_sym, result in zip(fetch_tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(
                    "cross_asset_fetch_failed",
                    symbol=rel_sym,
                    error=str(result),
                )
                closes_map[rel_sym] = None
            else:
                closes_map[rel_sym] = result

        # Score each asset contribution.
        component_scores: List[float] = []
        reason_parts: List[str] = []

        for confirm_sym in confirm_syms:
            closes = closes_map.get(confirm_sym)
            if not closes:
                reason_parts.append(f"{confirm_sym}:no_data")
                continue
            direction = self._short_term_direction(closes, lookback_bars)
            score, part = self._score_confirm(confirm_sym, action_upper, direction)
            component_scores.append(score)
            reason_parts.append(part)

        for context_sym in context_syms:
            closes = closes_map.get(context_sym)
            if not closes:
                reason_parts.append(f"{context_sym}:no_data")
                continue
            direction = self._short_term_direction(closes, lookback_bars)
            score, part = self._score_context(context_sym, symbol, action_upper, direction)
            component_scores.append(score)
            reason_parts.append(part)

        if not component_scores:
            return 0.0, "all_data_unavailable"

        final_score = float(sum(component_scores) / len(component_scores))
        reason = "|".join(reason_parts) if reason_parts else "no_checks"
        return final_score, reason

    # ------------------------------------------------------------------
    # Direction calculation
    # ------------------------------------------------------------------

    def _short_term_direction(self, closes: List[float], bars: int = _DEFAULT_LOOKBACK) -> float:
        """
        Rate-of-change directional signal for the last `bars` prices.

        Uses the last N closes to compute percentage change from first to last,
        then normalises to [-1, +1] by capping at ±5%.

        Args:
            closes: Close prices, oldest first.  Must have at least `bars` entries.
            bars:   Look-back window.  If len(closes) < bars, uses all available.

        Returns:
            float in [-1.0, +1.0].  Positive = rising, negative = falling.
            Returns 0.0 if fewer than 2 prices are available.
        """
        if len(closes) < 2:
            return 0.0
        window = closes[-bars:] if len(closes) >= bars else closes
        if len(window) < 2:
            return 0.0
        roc = (window[-1] - window[0]) / window[0]
        return max(-1.0, min(1.0, roc / _ROC_CAP))

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _score_confirm(
        self,
        confirm_sym: str,
        action: str,
        direction: float,
    ) -> Tuple[float, str]:
        """
        Score a "confirm" asset's contribution.

        BUY signal:
            confirm rising  (direction >  0.1) → +0.5 (agreement)
            confirm falling (direction < -0.1) → -0.7 (contradiction, reject)
            flat                               →  0.0 (neutral)

        SELL signal: signs are flipped.
        """
        if action == "BUY":
            if direction > _DIRECTION_UP_THRESHOLD:
                return _CONFIRM_AGREE_SCORE, f"{confirm_sym}:confirm_rising(BUY)"
            if direction < _DIRECTION_DOWN_THRESHOLD:
                return _CONFIRM_DISAGREE_SCORE, f"{confirm_sym}:confirm_falling_vs_BUY"
        elif action == "SELL":
            if direction < _DIRECTION_DOWN_THRESHOLD:
                return _CONFIRM_AGREE_SCORE, f"{confirm_sym}:confirm_falling(SELL)"
            if direction > _DIRECTION_UP_THRESHOLD:
                return _CONFIRM_DISAGREE_SCORE, f"{confirm_sym}:confirm_rising_vs_SELL"

        return 0.0, f"{confirm_sym}:neutral"

    def _score_context(
        self,
        context_sym: str,
        traded_sym: str,
        action: str,
        direction: float,
    ) -> Tuple[float, str]:
        """
        Score a "context" asset's contribution.

        Context logic is oil-centric (CrudeOIL / BRENT_OIL vs USA500):

        BUY oil + equity up   → risk-on, mild confirm (+0.1)
        BUY oil + equity down → supply shock narrative  (+0.2)
        SELL oil + equity down → demand destruction      (+0.3)
        SELL oil + equity up   → deflationary risk       (-0.2)

        For non-oil instruments, context direction confirms if it moves with
        the action direction (+0.1) or contradicts mildly (-0.1).
        """
        traded_is_oil = traded_sym in ("CrudeOIL", "BRENT_OIL")
        context_rising = direction > _DIRECTION_UP_THRESHOLD
        context_falling = direction < _DIRECTION_DOWN_THRESHOLD

        if traded_is_oil and context_sym == "USA500":
            if action == "BUY":
                if context_rising:
                    return _CONTEXT_BOTH_UP_SCORE, f"{context_sym}:risk_on_oil_buy"
                if context_falling:
                    return _CONTEXT_OIL_UP_EQ_DOWN_SCORE, f"{context_sym}:supply_shock"
            elif action == "SELL":
                if context_falling:
                    return _CONTEXT_BOTH_DOWN_SCORE, f"{context_sym}:demand_destruction"
                if context_rising:
                    return _CONTEXT_OIL_DOWN_EQ_UP_SCORE, f"{context_sym}:deflationary"
            return 0.0, f"{context_sym}:neutral"

        # Generic context: mild agreement or mild disagreement
        if action == "BUY" and context_rising:
            return 0.1, f"{context_sym}:ctx_agree_buy"
        if action == "SELL" and context_falling:
            return 0.1, f"{context_sym}:ctx_agree_sell"
        if action == "BUY" and context_falling:
            return -0.1, f"{context_sym}:ctx_contra_buy"
        if action == "SELL" and context_rising:
            return -0.1, f"{context_sym}:ctx_contra_sell"
        return 0.0, f"{context_sym}:neutral"

    # ------------------------------------------------------------------
    # DB fetch helper
    # ------------------------------------------------------------------

    async def _fetch_closes(self, symbol: str, limit: int) -> List[float]:
        """
        Fetch the latest `limit` H1 close prices for `symbol` from the DB.

        Returns closes in chronological order (oldest first).
        Raises if the DB call fails — callers catch and treat as no_data.
        """
        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        async with get_db_context() as db:
            repo = MarketDataRepository(db)
            # get_latest_ticks returns newest-first; reverse for oldest-first order
            rows = await repo.get_latest_ticks(symbol=symbol, timeframe="H1", limit=limit)

        rows = list(reversed(rows))
        return [float(row.last) for row in rows]
