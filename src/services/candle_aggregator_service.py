"""
Candle Aggregator Service

Aggregates M1 candles into H1 and M30 candles in real-time for all tracked symbols.

The MT4 EA pushes M1 candles. Many strategies (value_area, crack_spread,
seasonal_ma, etc.) require H1 data. ML training also needs M30 data.
Historical data has both M1 and H1 from imports, but live data only has M1.
This service bridges that gap.

Architecture:
    MT4 EA → M1 candle → mt4_sync_service → PostgreSQL (M1)
                                                  ↓
                              candle_aggregator_service (runs every 60s)
                                                  ↓
                                        PostgreSQL (H1 + M30 aggregated)

Design decisions:
- Periodic aggregation (NOT event-driven): runs every 60 seconds.
  Simpler and more reliable than Redis pub/sub.
- Only aggregates COMPLETED periods. Never writes the current (open) period.
- Idempotent: safe to re-run because upsert handles conflicts.
- Resilient: DB errors are logged and retried on next cycle.
- State in memory: tracks last aggregated period per symbol per timeframe
  so we only process new, unaggregated periods on each cycle.
- Multi-timeframe: aggregates both M30 and H1 from M1 data.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional

import structlog
from sqlalchemy import and_, cast, desc, func, select, Text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData

logger = structlog.get_logger(__name__)

# All symbols that receive live M1 data from MT4 and need H1 aggregation.
# Add symbols here when new instruments are brought live.
TRACKED_SYMBOLS = [
    "CrudeOIL",
    "USA500",
    "BRENT_OIL",
    "CORN",
    "WHEAT",
    "GBPJPY",
    "TSLA",
    "MSFT",
    "GASOLINE",
    "XAUUSD",
]

# How often (seconds) the aggregation loop runs.
# 60s is sufficient: the current period cannot be aggregated anyway, so
# running more frequently would be wasted work.
AGGREGATION_INTERVAL_SECONDS = 60

# Timeframes to aggregate from M1 data: (timeframe_name, period_minutes)
# M15 = 15-minute, M30 = 30-minute, H1 = 60-minute, H4 = 240-minute, D1 = 1440-minute
AGGREGATION_TIMEFRAMES = [
    ("M15", 15),
    ("M30", 30),
    ("H1", 60),
    ("H4", 240),
    ("D1", 1440),
]


class CandleAggregatorService:
    """
    Background service that aggregates completed M1 periods into H1 and M30 candles.

    Lifecycle:
        aggregator = CandleAggregatorService()
        asyncio.create_task(aggregator.run())  # fires and forgets

    State:
        _last_aggregated: Dict[str, Dict[str, datetime]]
            Maps timeframe → symbol → UTC floor-of-period of the most recently
            written candle. Initialised from the DB on first run so restarts are safe.

    Input / output ranges:
        Reads:  market_data WHERE timeframe='M1' AND symbol=? AND time in [start, end)
        Writes: market_data WHERE timeframe IN ('H1','M30') AND source='MT4'
        open    = first M1 open (lowest time)
        high    = MAX(M1 highs)
        low     = MIN(M1 lows)
        last    = last M1 close (highest time)  — DB uses 'last' not 'close'
        volume  = SUM(M1 volumes)
        change  = last - open
        change_percent = ((last - open) / open) * 100

    Edge cases:
        - Zero M1 candles for a period → skip, do not write an empty candle.
        - Fewer than expected M1 candles (market closed, data gap) → still write
          whatever partial data arrived so strategies have a candle.
        - DB unavailable → log error, sleep, retry on next cycle.
        - Symbol has no M1 data at all → skip silently.
    """

    def __init__(self, interval_seconds: int = AGGREGATION_INTERVAL_SECONDS):
        """
        Initialise the service.

        Args:
            interval_seconds: Seconds between aggregation passes.
                              Default 60.  Decrease in tests for faster cycling.
        """
        self.interval_seconds = interval_seconds
        self.running = False

        # Per-timeframe, per-symbol: UTC datetime of the most recently written candle.
        # E.g.  {"H1": {"CrudeOIL": datetime(2024, 3, 5, 14, 0, tzinfo=UTC)}}
        self._last_aggregated: Dict[str, Dict[str, Optional[datetime]]] = {
            tf_name: {s: None for s in TRACKED_SYMBOLS}
            for tf_name, _ in AGGREGATION_TIMEFRAMES
        }

        # Keep backward-compatible property for code that references H1 state
        self._last_aggregated_hour = self._last_aggregated.get("H1", {})

        logger.info(
            "candle_aggregator_service_initialized",
            symbols=TRACKED_SYMBOLS,
            timeframes=[tf for tf, _ in AGGREGATION_TIMEFRAMES],
            interval_seconds=interval_seconds,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Main loop — runs indefinitely until cancelled.

        On each tick:
          1. Initialise state from DB if this is the first cycle.
          2. Determine the last COMPLETED hour (current hour minus one).
          3. For each symbol, aggregate any un-aggregated completed hours.
          4. Sleep for interval_seconds.

        Exceptions inside a cycle are caught and logged; the loop continues.
        CancelledError propagates normally so asyncio.Task.cancel() works.
        """
        self.running = True
        first_cycle = True

        logger.info("candle_aggregator_service_started")

        while self.running:
            try:
                cycle_start = datetime.now(tz=timezone.utc)

                if first_cycle:
                    await self._init_state_from_db()
                    first_cycle = False

                await self._run_aggregation_cycle()

                cycle_duration = (
                    datetime.now(tz=timezone.utc) - cycle_start
                ).total_seconds()
                logger.debug(
                    "candle_aggregator_cycle_complete",
                    duration_seconds=round(cycle_duration, 2),
                )

            except asyncio.CancelledError:
                logger.info("candle_aggregator_service_cancelled")
                self.running = False
                break

            except Exception as exc:
                logger.error(
                    "candle_aggregator_cycle_error",
                    error=str(exc),
                    exc_info=True,
                )
                # Brief back-off before the next attempt so we don't spam
                # the logs if the DB is completely down.
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(self.interval_seconds)

        logger.info("candle_aggregator_service_stopped")

    def stop(self) -> None:
        """Signal the run loop to exit on the next iteration."""
        self.running = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _init_state_from_db(self) -> None:
        """
        Initialise _last_aggregated from the database.

        For each tracked symbol and each aggregation timeframe, query the latest
        candle with source='MT4' (i.e. previously aggregated by this service,
        not imported historical data which uses other sources like BARCHART/DUKASCOPY).

        This ensures restarts are idempotent — we will not re-aggregate periods
        that are already in the DB.
        """
        from src.api.dependencies import get_db_context

        logger.info("candle_aggregator_initializing_state_from_db")

        for tf_name, tf_minutes in AGGREGATION_TIMEFRAMES:
            for symbol in TRACKED_SYMBOLS:
                try:
                    async with get_db_context() as session:
                        latest = await self._get_latest_aggregated_candle(
                            session, symbol, tf_name
                        )
                        if latest is not None:
                            # Floor to the period boundary
                            candle_time = self._floor_to_period(
                                latest.time, tf_minutes
                            )
                            self._last_aggregated[tf_name][symbol] = candle_time
                            logger.debug(
                                "candle_aggregator_state_loaded",
                                symbol=symbol,
                                timeframe=tf_name,
                                last_time=candle_time.isoformat(),
                            )
                        else:
                            logger.debug(
                                "candle_aggregator_no_existing_data",
                                symbol=symbol,
                                timeframe=tf_name,
                            )
                except Exception as exc:
                    logger.warning(
                        "candle_aggregator_state_init_failed",
                        symbol=symbol,
                        timeframe=tf_name,
                        error=str(exc),
                    )

    async def _run_aggregation_cycle(self) -> None:
        """
        Process all tracked symbols for all aggregation timeframes.

        For each timeframe and symbol, determine which completed periods
        have not yet been aggregated and write a candle for each of them.

        We never write the current (open) period because it is not yet complete.
        """
        from src.api.dependencies import get_db_context

        now_utc = datetime.now(tz=timezone.utc)

        for tf_name, tf_minutes in AGGREGATION_TIMEFRAMES:
            # Determine the most recent completed period
            last_completed = self._floor_to_period(now_utc, tf_minutes) - timedelta(minutes=tf_minutes)

            for symbol in TRACKED_SYMBOLS:
                try:
                    async with get_db_context() as session:
                        await self._aggregate_symbol(
                            session, symbol, tf_name, tf_minutes, last_completed
                        )
                except Exception as exc:
                    logger.error(
                        "candle_aggregator_symbol_failed",
                        symbol=symbol,
                        timeframe=tf_name,
                        error=str(exc),
                        exc_info=True,
                    )

    async def _aggregate_symbol(
        self,
        session: AsyncSession,
        symbol: str,
        tf_name: str,
        tf_minutes: int,
        last_completed: datetime,
    ) -> None:
        """
        Aggregate all un-processed completed periods for a single symbol/timeframe.

        Args:
            session: Active async DB session.
            symbol: Trading symbol (e.g. "CrudeOIL").
            tf_name: Target timeframe name (e.g. "H1", "M30").
            tf_minutes: Period length in minutes (e.g. 60, 30).
            last_completed: The floor-of-period of the most recently
                completed period in UTC.

        The loop walks forward one period at a time so that if the service was
        offline for several periods, all missed ones are back-filled in order.
        """
        last_written = self._last_aggregated.get(tf_name, {}).get(symbol)
        period_delta = timedelta(minutes=tf_minutes)

        if last_written is None:
            # No state yet — start from the M1 data's oldest available period
            earliest_m1 = await self._get_earliest_m1_period(
                session, symbol, tf_minutes
            )
            if earliest_m1 is None:
                return
            candidate = earliest_m1
        else:
            candidate = last_written + period_delta

        while candidate <= last_completed:
            period_start = candidate
            period_end = candidate + period_delta

            await self._aggregate_single_period(
                session, symbol, tf_name, period_start, period_end
            )
            candidate += period_delta

    async def _aggregate_single_period(
        self,
        session: AsyncSession,
        symbol: str,
        tf_name: str,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        """
        Aggregate M1 candles within [period_start, period_end) into a single candle.

        Args:
            session: Active async DB session.
            symbol: Trading symbol.
            tf_name: Target timeframe (e.g. "H1", "M30").
            period_start: Inclusive start of the period (UTC).
            period_end: Exclusive end of the period.

        Writes:
            One row into market_data with timeframe=tf_name, source='MT4'.

        If zero M1 candles exist in the window, nothing is written and no
        error is raised (the period is considered a market-closed period).

        After a successful write the in-memory state is updated.
        """
        # --- Step 1: Fetch aggregate stats in a single DB round-trip --------
        agg_query = select(
            func.min(MarketData.time).label("first_time"),
            func.max(MarketData.time).label("last_time"),
            func.max(MarketData.high).label("high"),
            func.min(MarketData.low).label("low"),
            func.sum(MarketData.volume).label("total_volume"),
            func.count(MarketData.id).label("candle_count"),
        ).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == "M1",
                MarketData.time >= period_start,
                MarketData.time < period_end,
            )
        )

        agg_result = await session.execute(agg_query)
        agg_row = agg_result.one()

        candle_count = agg_row.candle_count or 0
        if candle_count == 0:
            # No M1 data — market closed or data gap. Update state so we
            # don't re-attempt this period on every subsequent cycle.
            self._last_aggregated[tf_name][symbol] = period_start
            return

        # --- Step 2: Fetch the OPEN price (first M1's open) -----------------
        first_m1_query = (
            select(MarketData.open)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == "M1",
                    MarketData.time >= period_start,
                    MarketData.time < period_end,
                )
            )
            .order_by(MarketData.time)
            .limit(1)
        )
        first_m1_result = await session.execute(first_m1_query)
        open_price = first_m1_result.scalar_one()

        # --- Step 3: Fetch the CLOSE price (last M1's last/close) -----------
        last_m1_query = (
            select(MarketData.last)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == "M1",
                    MarketData.time >= period_start,
                    MarketData.time < period_end,
                )
            )
            .order_by(desc(MarketData.time))
            .limit(1)
        )
        last_m1_result = await session.execute(last_m1_query)
        close_price = last_m1_result.scalar_one()

        # --- Step 4: Calculate derived fields --------------------------------
        high_price = agg_row.high
        low_price = agg_row.low
        total_volume = int(agg_row.total_volume or 0)

        open_dec = Decimal(str(open_price))
        close_dec = Decimal(str(close_price))

        change = close_dec - open_dec
        change_pct = (
            (change / open_dec * Decimal("100"))
            if open_dec != Decimal("0")
            else Decimal("0")
        )

        # --- Step 5: Upsert candle -------------------------------------------
        # Uses PostgreSQL ON CONFLICT to make re-runs safe.
        stmt = pg_insert(MarketData).values(
            time=period_start,
            symbol=symbol,
            import_symbol=symbol,
            timeframe=tf_name,
            source="MT4",
            open=open_dec,
            high=Decimal(str(high_price)),
            low=Decimal(str(low_price)),
            last=close_dec,
            change=change,
            change_percent=change_pct,
            volume=total_volume,
        )

        stmt = stmt.on_conflict_do_update(
            constraint="unique_time_source_timeframe_symbol",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "last": stmt.excluded.last,
                "change": stmt.excluded.change,
                "change_percent": stmt.excluded.change_percent,
                "volume": stmt.excluded.volume,
            },
        )

        await session.execute(stmt)
        await session.commit()

        # --- Step 6: Update in-memory state ----------------------------------
        self._last_aggregated[tf_name][symbol] = period_start

        logger.info(
            "candle_aggregator_candle_written",
            symbol=symbol,
            timeframe=tf_name,
            period=period_start.isoformat(),
            m1_candle_count=candle_count,
            open=float(open_dec),
            high=float(high_price),
            low=float(low_price),
            close=float(close_dec),
            volume=total_volume,
        )

    # ------------------------------------------------------------------
    # DB helper queries
    # ------------------------------------------------------------------

    @staticmethod
    def _floor_to_period(dt: datetime, period_minutes: int) -> datetime:
        """
        Floor a datetime to the start of its period.

        E.g. for period_minutes=30: 14:47 → 14:30, 14:15 → 14:00
             for period_minutes=60: 14:47 → 14:00
             for period_minutes=240 (H4): 14:47 → 12:00
             for period_minutes=1440 (D1): any time → 00:00 same day
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if period_minutes >= 1440:
            # Daily: floor to midnight UTC
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)

        if period_minutes > 60:
            # Multi-hour (H4 = 240 min): floor by total minutes since midnight
            total_minutes = dt.hour * 60 + dt.minute
            floored = (total_minutes // period_minutes) * period_minutes
            return dt.replace(
                hour=floored // 60,
                minute=floored % 60,
                second=0,
                microsecond=0,
            )

        # Sub-hourly or hourly
        minute_floor = (dt.minute // period_minutes) * period_minutes
        return dt.replace(minute=minute_floor, second=0, microsecond=0)

    async def _get_latest_aggregated_candle(
        self, session: AsyncSession, symbol: str, tf_name: str
    ) -> Optional[MarketData]:
        """
        Return the most recent MT4-aggregated candle for a symbol/timeframe.

        Only considers candles with source='MT4' to avoid treating imported
        historical data as previously aggregated.
        """
        query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == tf_name,
                    cast(MarketData.source, Text) == "MT4",
                )
            )
            .order_by(desc(MarketData.time))
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def _get_earliest_m1_period(
        self, session: AsyncSession, symbol: str, period_minutes: int
    ) -> Optional[datetime]:
        """
        Return the UTC floor-of-period of the earliest M1 candle for a symbol.

        Used to determine where to start back-filling when no prior state
        exists (e.g. first run ever for this symbol/timeframe).
        """
        query = select(func.min(MarketData.time)).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == "M1",
            )
        )
        result = await session.execute(query)
        earliest = result.scalar_one_or_none()

        if earliest is None:
            return None

        return self._floor_to_period(earliest, period_minutes)

    # Backward compatibility alias
    async def _get_latest_h1_candle(
        self, session: AsyncSession, symbol: str
    ) -> Optional[MarketData]:
        """Backward-compatible alias for _get_latest_aggregated_candle with H1."""
        return await self._get_latest_aggregated_candle(session, symbol, "H1")

    async def _get_earliest_m1_hour(
        self, session: AsyncSession, symbol: str
    ) -> Optional[datetime]:
        """Backward-compatible alias for _get_earliest_m1_period with 60 minutes."""
        return await self._get_earliest_m1_period(session, symbol, 60)
