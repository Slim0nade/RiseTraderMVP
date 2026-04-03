"""
TickClusteringDetector - Detects abnormal tick count bursts.

MT4 tick volume = number of price changes per bar, NOT exchange volume.
Tick bursts correlated with price direction indicate unusual activity.

Normal tick range: 1-50 ticks/minute for CrudeOIL.
Anomaly threshold: 150+ ticks/minute (>3x baseline).

Typical usage:

    detector = TickClusteringDetector()
    result = detector.analyze(prices)  # prices is oldest-first list of M1 candle dicts
    if result.is_anomaly:
        # tick_z_score, price_direction, confidence are populated

DB-backed usage:

    result = await detector.analyze_from_db("CrudeOIL", timeframe="M1", limit=120)
"""

from typing import Dict, List

import numpy as np
import structlog

from .schemas import ClusterAnalysis

logger = structlog.get_logger(__name__)


class TickClusteringDetector:
    """
    Identifies tick count bursts (>3x baseline) and correlates with price
    direction for informed-flow confirmation.

    Parameters:
        burst_multiplier: Ratio of current ticks to baseline mean required to
            declare an anomaly. Default 3.0 (i.e. 3x the rolling average).
            Range: > 1.0.
        baseline_window: Number of 1-minute bars used to compute the rolling
            baseline (mean and std). Default 60 bars (one hour of history).
            Range: >= 2.
        min_absolute_ticks: Hard floor — the latest bar must exceed this count
            before any anomaly is declared, regardless of the z-score or
            burst_multiplier test. Default 150, matching the CrudeOIL anomaly
            threshold documented in the module docstring. Range: >= 1.

    Edge cases:
        - Fewer than baseline_window + 1 bars: returns is_anomaly=False,
          all numeric fields zero, confidence 0.0.
        - baseline_std == 0 (all baseline bars have identical tick count):
          z_score is set to 0.0 when latest_ticks == baseline_mean, or 10.0
          when latest_ticks > baseline_mean. This avoids divide-by-zero while
          still flagging a genuine jump.
        - latest_ticks == 0 (no price changes in bar, common during illiquid
          sessions): evaluated normally; will not satisfy min_absolute_ticks,
          so is_anomaly will be False.
    """

    def __init__(
        self,
        burst_multiplier: float = 3.0,
        baseline_window: int = 60,
        min_absolute_ticks: int = 150,
    ):
        if burst_multiplier <= 1.0:
            raise ValueError(f"burst_multiplier must be > 1.0, got {burst_multiplier}")
        if baseline_window < 2:
            raise ValueError(f"baseline_window must be >= 2, got {baseline_window}")
        if min_absolute_ticks < 1:
            raise ValueError(f"min_absolute_ticks must be >= 1, got {min_absolute_ticks}")

        self.burst_multiplier = burst_multiplier
        self.baseline_window = baseline_window
        self.min_absolute_ticks = min_absolute_ticks

    def analyze(self, prices: List[Dict]) -> ClusterAnalysis:
        """
        Analyze tick clustering from a sequence of 1-minute candle dicts.

        Args:
            prices: Oldest-first list of dicts, each with:
                - 'volume' (float | int): MT4 tick count for that bar.
                  Missing or None is treated as 0.
                - 'close' (float | str): Close price of the bar.
                Minimum required length: baseline_window + 1.

        Returns:
            ClusterAnalysis dataclass.
            - is_anomaly (bool): True when BOTH the burst_multiplier AND
              min_absolute_ticks conditions are satisfied.
            - tick_z_score (float): Z-score of the latest bar's tick count
              relative to the rolling baseline. Rounded to 2 decimal places.
            - price_direction (str): 'up', 'down', or 'flat' based on
              close[-1] vs close[-2].
            - confidence (float): 0.0 when not an anomaly. When anomaly,
              derived from z_score (capped at 1.0, scaled so z=5 → 1.0),
              then multiplied by 1.3 if price_direction is not 'flat'
              (i.e. confirming directional tick burst). Rounded to 3 dp.
            - tick_count (int): Raw tick count of the latest bar.
            - baseline_mean (float): Rolling mean over baseline_window bars
              (excluding the latest). Rounded to 1 dp.
            - baseline_std (float): Rolling std dev over baseline_window bars
              (excluding the latest). Rounded to 1 dp.

        Edge cases:
            - len(prices) < baseline_window + 1: all-zero / False result.
            - Single-bar price sequence: price_direction is 'flat'.
        """
        if len(prices) < self.baseline_window + 1:
            return ClusterAnalysis(
                is_anomaly=False,
                tick_z_score=0.0,
                price_direction="flat",
                confidence=0.0,
                tick_count=0,
                baseline_mean=0.0,
                baseline_std=0.0,
            )

        volumes = np.array([float(p.get("volume") or 0) for p in prices])
        closes = np.array([float(p["close"]) for p in prices])

        latest_ticks = int(volumes[-1])

        # Baseline: the baseline_window bars immediately before the latest bar.
        baseline = volumes[-self.baseline_window - 1 : -1]
        baseline_mean = float(np.mean(baseline))
        baseline_std = float(np.std(baseline))

        # Z-score with divide-by-zero guard.
        if baseline_std > 0:
            z_score = (latest_ticks - baseline_mean) / baseline_std
        else:
            # Flat baseline — any jump gets a sentinel high z-score.
            z_score = 0.0 if latest_ticks <= baseline_mean else 10.0

        # Anomaly requires BOTH the relative burst AND the absolute floor.
        is_burst = latest_ticks >= baseline_mean * self.burst_multiplier
        is_above_min = latest_ticks >= self.min_absolute_ticks
        is_anomaly = is_burst and is_above_min

        # Price direction over the most recent completed bar.
        if len(closes) >= 2:
            price_change = closes[-1] - closes[-2]
            if price_change > 0:
                price_direction = "up"
            elif price_change < 0:
                price_direction = "down"
            else:
                price_direction = "flat"
        else:
            price_direction = "flat"

        # Confidence: non-zero only when an anomaly is declared.
        confidence = 0.0
        if is_anomaly:
            # Scale: z=5 → 1.0; capped at 1.0 above that.
            confidence = min(1.0, z_score / 5.0)
            # Directional confirmation boosts confidence.
            if price_direction != "flat":
                confidence = min(1.0, confidence * 1.3)

        result = ClusterAnalysis(
            is_anomaly=is_anomaly,
            tick_z_score=round(z_score, 2),
            price_direction=price_direction,
            confidence=round(confidence, 3),
            tick_count=latest_ticks,
            baseline_mean=round(baseline_mean, 1),
            baseline_std=round(baseline_std, 1),
        )

        if is_anomaly:
            logger.info(
                "tick_cluster_detected",
                tick_count=latest_ticks,
                baseline_mean=round(baseline_mean, 1),
                z_score=round(z_score, 2),
                price_direction=price_direction,
                confidence=round(confidence, 3),
            )

        return result

    async def analyze_from_db(
        self,
        symbol: str,
        timeframe: str = "M1",
        limit: int = 120,
    ) -> ClusterAnalysis:
        """
        Fetch candles from the database and run tick clustering analysis.

        Retrieves the most recent `limit` bars for `symbol` / `timeframe`,
        reverses them to oldest-first order, then delegates to `analyze()`.

        Args:
            symbol: MT4 symbol string (e.g. 'CrudeOIL').
            timeframe: Bar timeframe string. Must match an existing ENUM value
                in the database (e.g. 'M1', 'H1', 'D1'). Default 'M1'.
            limit: Maximum number of bars to fetch. Should be at least
                baseline_window + 2 to produce a valid result.
                Default 120 (two hours of M1 bars).

        Returns:
            ClusterAnalysis. Returns an all-zero / False result when no rows
            are found in the database.

        Edge cases:
            - If the database returns fewer bars than baseline_window + 1,
              `analyze()` returns is_anomaly=False with zero numeric fields.
            - Rows with NULL volume are treated as 0.0 tick count.
        """
        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        async with get_db_context() as db:
            repo = MarketDataRepository(db)
            rows = await repo.get_latest_ticks(symbol=symbol, timeframe=timeframe, limit=limit)

        if not rows:
            return ClusterAnalysis(
                is_anomaly=False,
                tick_z_score=0.0,
                price_direction="flat",
                confidence=0.0,
                tick_count=0,
                baseline_mean=0.0,
                baseline_std=0.0,
            )

        # DB returns newest-first; reverse to oldest-first for analyze().
        rows = list(reversed(rows))
        prices = [
            {
                "close": float(row.last),
                "volume": float(row.volume) if row.volume is not None else 0.0,
            }
            for row in rows
        ]

        return self.analyze(prices)
