"""
CrossAssetMonitor - Monitors rolling correlations between asset pairs.

Detects correlation regime changes that may signal informed flow
(e.g., crude oil decoupling from equity index).

Inputs accepted by calculate_correlation():
    prices1, prices2: close-price series (oldest first), length >= window.

Outputs:
    CorrelationAlert with correlation in [-1.0, 1.0] and threshold_exceeded
    flag set when abs(correlation) >= correlation_threshold (default 0.7).
    Returns None when fewer than `window` prices are supplied for either series.

Edge cases:
    - Fewer than `window` prices → return None (not NaN, not 0.0).
    - All-identical prices in one series → log returns are 0.0; corrcoef
      returns NaN; the method returns None to avoid propagating bad data.
    - window < 2 → log-return diff produces an empty array; returns None.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from .schemas import CorrelationAlert

logger = structlog.get_logger(__name__)

# Default pairs to monitor.
# Note: DXY is not available on Fortrade — use DOLLAR_INDX instead.
# VIX is not available on Fortrade — omitted.
DEFAULT_PAIRS: List[Tuple[str, str]] = [
    ("CrudeOIL", "XAUUSD"),    # gold as risk proxy
    ("CrudeOIL", "USA500"),    # equity correlation
    ("CrudeOIL", "BRENT_OIL"), # spread monitoring
]


class CrossAssetMonitor:
    """
    Monitors rolling correlations between asset pairs.

    Alerts when abs(correlation) >= correlation_threshold or when the
    correlation breaks meaningfully from historical norms.

    Args:
        pairs: List of (symbol1, symbol2) tuples to monitor.
            Defaults to DEFAULT_PAIRS.
        correlation_threshold: Absolute correlation value that triggers an
            alert.  Range [0.0, 1.0], default 0.7.
        window: Number of H1 candles used for the rolling look-back.
            Must be >= 2 to compute at least one log-return.  Default 20.
    """

    def __init__(
        self,
        pairs: Optional[List[Tuple[str, str]]] = None,
        correlation_threshold: float = 0.7,
        window: int = 20,
    ) -> None:
        self.pairs = pairs or DEFAULT_PAIRS
        self.correlation_threshold = correlation_threshold
        self.window = window

    # ------------------------------------------------------------------
    # Pure math helpers (no I/O; fully testable without a DB)
    # ------------------------------------------------------------------

    def calculate_correlation(
        self,
        prices1: List[float],
        prices2: List[float],
    ) -> Optional[float]:
        """
        Calculate Pearson correlation of log returns between two price series.

        Args:
            prices1: Close prices for symbol 1, oldest first.
                Must contain at least `window` values.
            prices2: Close prices for symbol 2, oldest first.
                Must contain at least `window` values.

        Returns:
            Pearson correlation in [-1.0, 1.0], or None when:
            - Either series has fewer than `window` values.
            - After taking log-returns the result is fewer than 2 points.
            - The correlation is NaN (e.g. zero-variance series).

        Edge cases:
            - Constant price series → log-returns all zero → corrcoef NaN
              → method returns None.
            - window == 1 → diff produces empty array → returns None.
        """
        min_len = min(len(prices1), len(prices2))
        if min_len < self.window:
            return None

        # Slice the most-recent `window` prices (oldest first).
        p1 = np.array(prices1[-self.window :], dtype=float)
        p2 = np.array(prices2[-self.window :], dtype=float)

        # Log returns require at least two prices to produce one return.
        r1 = np.diff(np.log(p1))
        r2 = np.diff(np.log(p2))

        if len(r1) < 2:
            return None

        corr_matrix = np.corrcoef(r1, r2)
        corr = float(corr_matrix[0, 1])

        if np.isnan(corr):
            return None

        return corr

    def check_pair(
        self,
        symbol1: str,
        symbol2: str,
        prices1: List[float],
        prices2: List[float],
    ) -> Optional[CorrelationAlert]:
        """
        Compute correlation for a single pair and return a CorrelationAlert.

        Args:
            symbol1: Primary symbol name (e.g. 'CrudeOIL').
            symbol2: Secondary symbol name (e.g. 'XAUUSD').
            prices1: Close prices for symbol1, oldest first.
            prices2: Close prices for symbol2, oldest first.

        Returns:
            CorrelationAlert — always returned when there is enough data,
            regardless of whether the threshold was exceeded.  Callers can
            filter on alert.threshold_exceeded.
            Returns None when insufficient data.
        """
        corr = self.calculate_correlation(prices1, prices2)
        if corr is None:
            return None

        threshold_exceeded = abs(corr) >= self.correlation_threshold

        alert = CorrelationAlert(
            symbol1=symbol1,
            symbol2=symbol2,
            correlation=round(corr, 4),
            window_minutes=self.window,
            timestamp=datetime.now(timezone.utc),
            threshold_exceeded=threshold_exceeded,
        )

        if threshold_exceeded:
            logger.info(
                "cross_asset_correlation_alert",
                symbol1=symbol1,
                symbol2=symbol2,
                correlation=round(corr, 4),
                threshold=self.correlation_threshold,
            )

        return alert

    # ------------------------------------------------------------------
    # Async DB-backed methods
    # ------------------------------------------------------------------

    async def calculate_rolling_correlation(
        self,
        symbol1: str,
        symbol2: str,
        window: int = 20,
    ) -> Optional[CorrelationAlert]:
        """
        Fetch candle data from the DB and return a CorrelationAlert.

        Fetches the most recent `window + 5` H1 candles for each symbol
        (extra buffer in case of gaps) and delegates to check_pair().

        Args:
            symbol1: First symbol (e.g. 'CrudeOIL').
            symbol2: Second symbol (e.g. 'XAUUSD').
            window: Look-back window in candles.  Overrides self.window
                for this single call.

        Returns:
            CorrelationAlert or None if insufficient DB data for either symbol.
        """
        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        effective_window = window
        fetch_limit = effective_window + 5

        try:
            async with get_db_context() as db:
                repo = MarketDataRepository(db)
                # get_latest_ticks returns rows newest-first; reverse to get
                # oldest-first for the correlation math.
                rows1 = await repo.get_latest_ticks(
                    symbol=symbol1, timeframe="H1", limit=fetch_limit
                )
                rows2 = await repo.get_latest_ticks(
                    symbol=symbol2, timeframe="H1", limit=fetch_limit
                )
        except Exception as exc:
            logger.warning(
                "cross_asset_db_fetch_failed",
                symbol1=symbol1,
                symbol2=symbol2,
                error=str(exc),
            )
            return None

        if not rows1 or not rows2:
            return None

        prices1 = [float(r.close) for r in reversed(rows1)]
        prices2 = [float(r.close) for r in reversed(rows2)]

        # Temporarily swap window so check_pair uses the caller-supplied value.
        orig_window = self.window
        self.window = effective_window
        try:
            alert = self.check_pair(symbol1, symbol2, prices1, prices2)
        finally:
            self.window = orig_window

        return alert

    async def check_all_pairs(self) -> List[CorrelationAlert]:
        """
        Fetch data for all configured pairs and check correlations.

        Returns:
            List of CorrelationAlert instances for pairs that had
            enough data.  Includes both threshold-exceeded and
            non-exceeded alerts so callers can track all correlations.
        """
        from src.api.dependencies import get_db_context
        from src.database.repositories.market_data_repository import MarketDataRepository

        fetch_limit = self.window + 5
        alerts: List[CorrelationAlert] = []

        async with get_db_context() as db:
            repo = MarketDataRepository(db)

            for sym1, sym2 in self.pairs:
                try:
                    rows1 = await repo.get_latest_ticks(
                        symbol=sym1, timeframe="H1", limit=fetch_limit
                    )
                    rows2 = await repo.get_latest_ticks(
                        symbol=sym2, timeframe="H1", limit=fetch_limit
                    )

                    if not rows1 or not rows2:
                        continue

                    prices1 = [float(r.close) for r in reversed(rows1)]
                    prices2 = [float(r.close) for r in reversed(rows2)]

                    alert = self.check_pair(sym1, sym2, prices1, prices2)
                    if alert:
                        alerts.append(alert)

                except Exception as exc:
                    logger.warning(
                        "cross_asset_check_failed",
                        sym1=sym1,
                        sym2=sym2,
                        error=str(exc),
                    )

        return alerts

    # ------------------------------------------------------------------
    # Correlation summary helper
    # ------------------------------------------------------------------

    def summarise_alerts(
        self, alerts: List[CorrelationAlert]
    ) -> Dict[str, float]:
        """
        Return a flat dict mapping 'SYM1/SYM2' → correlation value.

        Useful for logging and MCP tool responses.

        Args:
            alerts: List of CorrelationAlert returned by check_all_pairs().

        Returns:
            Dict with pair keys and rounded correlation values.
        """
        return {
            f"{a.symbol1}/{a.symbol2}": a.correlation
            for a in alerts
        }
