"""
PriceVelocityDetector - Detects abnormal price velocity.

Primary signal for informed flow detection since MT4 tick volume != exchange volume.
Uses price change rate (not volume) as the main indicator.

Design notes:
- MT4 reports synthetic tick volume (number of broker quotes), not exchange lot volume.
  Therefore volume-based anomaly detection is unreliable on MT4 symbols.
- Price velocity (|return_1m| in %) is exchange-independent and captures the same
  informed-flow signature: abnormally large directional moves before a catalyst.
- Z-score is computed against the 60-minute rolling window of absolute 1-minute
  returns, giving a time-of-day-local baseline rather than a fixed threshold.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import structlog

from .schemas import InformedFlowAlert

logger = structlog.get_logger(__name__)


class PriceVelocityDetector:
    """Detects abnormal price velocity by comparing the most recent 1-minute
    absolute price return against a 60-minute rolling baseline.

    An alert fires when BOTH conditions hold:
        1. |price_change_1m| >= velocity_threshold_pct  (default 0.5 %)
        2. z_score >= z_score_threshold                 (default 2.0 σ)

    Confidence is computed via a logistic function of the z-score so that
    it is bounded in (0, 1) without hard caps:
        confidence = 1 / (1 + exp(-(z_score - 2.0)))
    This yields approximately 0.50 at z=2.0, 0.73 at z=3.0, and 0.88 at z=4.0.

    Args:
        velocity_threshold_pct: Minimum absolute 1-minute percentage move
            required to consider a velocity alert.  Range: (0, ∞), typical 0.5.
        z_score_threshold: Minimum z-score against the rolling baseline.
            Range: (0, ∞), typical 2.0 (2 standard deviations).
        baseline_window: Number of historical 1-minute returns to use when
            computing the rolling baseline mean and std.  Must be >= 2.
            Typical: 60 (one hour of M1 candles).
    """

    def __init__(
        self,
        velocity_threshold_pct: float = 0.5,
        z_score_threshold: float = 2.0,
        baseline_window: int = 60,
    ) -> None:
        if baseline_window < 2:
            raise ValueError("baseline_window must be >= 2")
        if velocity_threshold_pct <= 0:
            raise ValueError("velocity_threshold_pct must be > 0")
        if z_score_threshold <= 0:
            raise ValueError("z_score_threshold must be > 0")

        self.velocity_threshold_pct = velocity_threshold_pct
        self.z_score_threshold = z_score_threshold
        self.baseline_window = baseline_window

        # Per-symbol deque of historical absolute 1-minute returns (%).
        # Not currently used by detect() (which is stateless over a price list)
        # but available for callers that want to push incremental bars.
        self._history: Dict[str, deque] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        symbol: str,
        prices: List[Dict],
    ) -> Optional[InformedFlowAlert]:
        """Analyse a list of 1-minute candles for a velocity anomaly.

        Args:
            symbol: MT4 symbol string (e.g. 'CrudeOIL', 'GBPJPY').
            prices: Oldest-first list of dicts, each with at least a 'close'
                key holding the bar close price (float-compatible).  The list
                must contain at least baseline_window + 1 entries so that:
                  - baseline_window absolute returns are available as the
                    rolling baseline (the second-to-last bar back to the oldest),
                  - the last bar provides the current return to test.

        Returns:
            InformedFlowAlert if both thresholds are exceeded, else None.

        Edge cases:
            - Fewer than baseline_window + 1 prices → returns None (not enough
              history; callers should accumulate candles before calling).
            - baseline_std == 0 (all baseline returns identical) → returns None
              (z-score undefined; flat markets should not generate alerts).
            - Returns exactly at threshold boundaries are NOT alerts
              (strict greater-than comparison for both conditions).
        """
        if len(prices) < self.baseline_window + 1:
            return None

        closes = np.array([float(p["close"]) for p in prices], dtype=np.float64)

        # 1-minute percentage returns (signed): r_i = (c_i - c_{i-1}) / c_{i-1} * 100
        # Length: len(closes) - 1
        returns = np.diff(closes) / closes[:-1] * 100.0

        if len(returns) < self.baseline_window:
            return None

        latest_return = returns[-1]
        latest_abs_return = abs(latest_return)

        # Baseline: the baseline_window absolute returns immediately before the
        # current bar.  Slice indices relative to returns array:
        #   baseline = |returns[-(baseline_window + 1) : -1]|
        # This excludes the current return from the baseline to avoid
        # look-ahead bias.
        baseline_slice = np.abs(returns[-(self.baseline_window + 1):-1])
        baseline_mean = float(np.mean(baseline_slice))
        baseline_std = float(np.std(baseline_slice))

        if baseline_std == 0.0:
            return None

        z_score = (latest_abs_return - baseline_mean) / baseline_std

        # Both conditions must exceed their thresholds (strict inequality).
        if latest_abs_return <= self.velocity_threshold_pct:
            return None
        if z_score <= self.z_score_threshold:
            return None

        direction = "up" if latest_return > 0 else "down"

        # Logistic confidence: centred at z=2.0, asymptotes to 0/1.
        confidence = float(1.0 / (1.0 + np.exp(-(z_score - 2.0))))

        alert = InformedFlowAlert(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            alert_type="price_velocity",
            confidence=confidence,
            price_change_pct=float(latest_return),
            z_score=float(z_score),
            direction=direction,
            details={
                "baseline_mean_pct": round(baseline_mean, 4),
                "baseline_std_pct": round(baseline_std, 4),
                "threshold_pct": self.velocity_threshold_pct,
                "z_threshold": self.z_score_threshold,
                "latest_price": float(closes[-1]),
                "previous_price": float(closes[-2]),
            },
        )

        logger.info(
            "price_velocity_detected",
            symbol=symbol,
            change_pct=round(float(latest_return), 4),
            z_score=round(float(z_score), 2),
            confidence=round(confidence, 3),
            direction=direction,
        )

        return alert

    async def detect_from_db(
        self,
        symbol: str,
        timeframe: str = "M1",
        limit: int = 120,
    ) -> Optional[InformedFlowAlert]:
        """Fetch candles from the database and run velocity detection.

        Fetches `limit` candles (newest-first from DB), reverses them to
        oldest-first, then calls detect().

        Args:
            symbol: MT4 symbol string.
            timeframe: Candle timeframe string accepted by
                MarketDataRepository.get_latest_ticks() (e.g. 'M1', 'H1').
                DB timeframe ENUMs use uppercase ('M1', not 'm1').
            limit: Number of candles to fetch.  Should be at least
                baseline_window + 2 to leave a safety margin.

        Returns:
            InformedFlowAlert if anomaly detected, else None.

        Note:
            Uses lazy imports of get_db_context and MarketDataRepository to
            avoid circular imports at module load time.  The `last` field on
            MarketData rows is used as the close price.
        """
        # Lazy imports to avoid circular dependency at module load time.
        from src.api.dependencies import get_db_context  # noqa: PLC0415
        from src.database.repositories.market_data_repository import (  # noqa: PLC0415
            MarketDataRepository,
        )

        async with get_db_context() as db:
            repo = MarketDataRepository(db)
            rows = await repo.get_latest_ticks(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )

        if not rows:
            return None

        # DB returns newest-first; detect() expects oldest-first.
        rows = list(reversed(rows))
        prices = [{"close": float(row.last)} for row in rows]

        return self.detect(symbol, prices)
