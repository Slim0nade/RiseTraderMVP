"""
Data Quality Monitor

Background service that detects:
- Gaps in candle data (missing expected periods)
- Stale data (no new candles beyond a threshold)
- Cross-timeframe validation (H1 vs aggregated M1s)

Runs periodically and logs alerts via structlog.

Usage:
    monitor = DataQualityMonitor()
    asyncio.create_task(monitor.run())
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog
from sqlalchemy import and_, cast, func, select, Text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData

logger = structlog.get_logger(__name__)

# Symbols to monitor — same set as candle_aggregator_service
MONITORED_SYMBOLS = [
    "CrudeOIL", "USA500", "BRENT_OIL", "CORN", "WHEAT",
    "GBPJPY", "TSLA", "MSFT", "GASOLINE", "XAUUSD",
]

# Expected candles per day by timeframe (approximate; weekends/holidays may have 0)
EXPECTED_CANDLES_PER_DAY = {
    "M1": 1440,
    "M15": 96,
    "M30": 48,
    "H1": 24,
    "H4": 6,
    "D1": 1,
}

# How old the newest candle can be before it is "stale" (in hours)
STALE_THRESHOLDS_HOURS = {
    "M1": 2,
    "M15": 2,
    "M30": 2,
    "H1": 4,
    "H4": 8,
    "D1": 48,
}


@dataclass
class GapInfo:
    """Description of a data gap."""
    symbol: str
    timeframe: str
    gap_start: datetime
    gap_end: datetime
    missing_periods: int


@dataclass
class StaleInfo:
    """Description of stale data."""
    symbol: str
    timeframe: str
    latest_candle: datetime
    hours_stale: float


@dataclass
class QualityReport:
    """Aggregate quality report for one scan."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    gaps: List[GapInfo] = field(default_factory=list)
    stale: List[StaleInfo] = field(default_factory=list)
    cross_validation_mismatches: int = 0
    symbols_checked: int = 0
    healthy: bool = True

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "gaps": len(self.gaps),
            "stale": len(self.stale),
            "cross_validation_mismatches": self.cross_validation_mismatches,
            "symbols_checked": self.symbols_checked,
            "healthy": self.healthy,
        }


class DataQualityMonitor:
    """
    Periodic data quality scanner.

    Lifecycle:
        monitor = DataQualityMonitor(interval_seconds=300)
        asyncio.create_task(monitor.run())
    """

    def __init__(
        self,
        interval_seconds: int = 300,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
    ):
        self.interval = interval_seconds
        self.symbols = symbols or MONITORED_SYMBOLS
        self.timeframes = timeframes or ["M1", "H1", "D1"]
        self.running = False
        self._last_report: Optional[QualityReport] = None
        logger.info(
            "data_quality_monitor_initialized",
            symbols=len(self.symbols),
            timeframes=self.timeframes,
            interval=self.interval,
        )

    @property
    def last_report(self) -> Optional[QualityReport]:
        return self._last_report

    async def run(self) -> None:
        """Main loop — runs until cancelled."""
        self.running = True
        logger.info("data_quality_monitor_started")

        while self.running:
            try:
                report = await self.scan()
                self._last_report = report
                if not report.healthy:
                    logger.warning(
                        "data_quality_issues_detected",
                        **report.to_dict(),
                    )
                else:
                    logger.info("data_quality_ok", **report.to_dict())
            except asyncio.CancelledError:
                self.running = False
                break
            except Exception:
                logger.exception("data_quality_scan_error")

            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                self.running = False
                break

        logger.info("data_quality_monitor_stopped")

    def stop(self) -> None:
        self.running = False

    async def scan(self) -> QualityReport:
        """
        Run a full data quality scan across all symbols and timeframes.

        Returns a QualityReport with any detected issues.
        """
        from src.api.dependencies import get_db_context

        report = QualityReport()

        for symbol in self.symbols:
            for tf in self.timeframes:
                try:
                    async with get_db_context() as session:
                        # Check for stale data
                        stale = await self._check_stale(session, symbol, tf)
                        if stale:
                            report.stale.append(stale)

                        # Check for gaps (only for M1 and H1 — D1 gaps are expected on weekends)
                        if tf in ("M1", "H1"):
                            gaps = await self._detect_gaps(session, symbol, tf)
                            report.gaps.extend(gaps)

                    report.symbols_checked += 1
                except Exception:
                    logger.debug("quality_check_failed", symbol=symbol, timeframe=tf)

        # Cross-timeframe validation stub (H1 open should match first M1 open)
        for symbol in self.symbols:
            try:
                async with get_db_context() as session:
                    mismatches = await self._cross_validate(session, symbol)
                    report.cross_validation_mismatches += mismatches
            except Exception:
                pass

        report.healthy = (
            len(report.gaps) == 0
            and len(report.stale) == 0
            and report.cross_validation_mismatches == 0
        )
        return report

    async def _check_stale(
        self, session: AsyncSession, symbol: str, timeframe: str
    ) -> Optional[StaleInfo]:
        """Check if the latest candle is too old."""
        query = select(func.max(MarketData.time)).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
            )
        )
        result = await session.execute(query)
        latest = result.scalar_one_or_none()

        if latest is None:
            return StaleInfo(
                symbol=symbol,
                timeframe=timeframe,
                latest_candle=datetime.min.replace(tzinfo=timezone.utc),
                hours_stale=float("inf"),
            )

        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)

        now = datetime.now(tz=timezone.utc)
        hours_ago = (now - latest).total_seconds() / 3600
        threshold = STALE_THRESHOLDS_HOURS.get(timeframe, 4)

        if hours_ago > threshold:
            return StaleInfo(
                symbol=symbol,
                timeframe=timeframe,
                latest_candle=latest,
                hours_stale=round(hours_ago, 1),
            )
        return None

    async def _detect_gaps(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        lookback_days: int = 7,
    ) -> List[GapInfo]:
        """
        Detect gaps in candle data over the last N days.

        A "gap" is defined as a period where the time difference between
        consecutive candles exceeds 2× the expected interval.
        """
        period_map = {"M1": 1, "M15": 15, "M30": 30, "H1": 60, "H4": 240}
        period_minutes = period_map.get(timeframe, 60)
        max_gap_minutes = period_minutes * 2  # 2× expected = gap

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)

        query = (
            select(MarketData.time)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                    MarketData.time >= cutoff,
                )
            )
            .order_by(MarketData.time)
        )
        result = await session.execute(query)
        times = [row[0] for row in result.all()]

        gaps: List[GapInfo] = []
        for i in range(1, len(times)):
            prev = times[i - 1]
            curr = times[i]
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            if curr.tzinfo is None:
                curr = curr.replace(tzinfo=timezone.utc)

            delta_minutes = (curr - prev).total_seconds() / 60
            if delta_minutes > max_gap_minutes:
                missing = int(delta_minutes / period_minutes) - 1
                gaps.append(
                    GapInfo(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_start=prev,
                        gap_end=curr,
                        missing_periods=missing,
                    )
                )

        return gaps

    async def _cross_validate(
        self, session: AsyncSession, symbol: str, lookback_hours: int = 24
    ) -> int:
        """
        Cross-validate H1 candles against aggregated M1 data.

        Checks that the H1 open matches the first M1 open for the same hour.
        Returns the count of mismatches found.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)

        # Get recent H1 candles
        h1_query = (
            select(MarketData.time, MarketData.open)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == "H1",
                    MarketData.time >= cutoff,
                )
            )
            .order_by(MarketData.time)
            .limit(24)
        )
        h1_result = await session.execute(h1_query)
        h1_candles = h1_result.all()

        mismatches = 0
        for h1_time, h1_open in h1_candles:
            if h1_time.tzinfo is None:
                h1_time = h1_time.replace(tzinfo=timezone.utc)
            hour_end = h1_time + timedelta(hours=1)

            # Get first M1 open in same hour
            m1_query = (
                select(MarketData.open)
                .where(
                    and_(
                        MarketData.symbol == symbol,
                        cast(MarketData.timeframe, Text) == "M1",
                        MarketData.time >= h1_time,
                        MarketData.time < hour_end,
                    )
                )
                .order_by(MarketData.time)
                .limit(1)
            )
            m1_result = await session.execute(m1_query)
            m1_open = m1_result.scalar_one_or_none()

            if m1_open is not None and h1_open is not None:
                if abs(float(h1_open) - float(m1_open)) > 0.01:
                    mismatches += 1
                    logger.debug(
                        "cross_validation_mismatch",
                        symbol=symbol,
                        time=h1_time.isoformat(),
                        h1_open=float(h1_open),
                        m1_open=float(m1_open),
                    )

        return mismatches
