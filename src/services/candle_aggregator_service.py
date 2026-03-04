"""
Candle Aggregator Service

Aggregates M1 candles into H1 candles in real-time for all tracked symbols.

The MT4 EA pushes M1 candles. Many strategies (value_area, crack_spread,
seasonal_ma, etc.) require H1 data. Historical data has both M1 and H1 from
imports, but live data only has M1. This service bridges that gap.

Architecture:
    MT4 EA → M1 candle → mt4_sync_service → PostgreSQL (M1)
                                                  ↓
                              candle_aggregator_service (runs every 60s)
                                                  ↓
                                        PostgreSQL (H1 aggregated)

Design decisions:
- Periodic aggregation (NOT event-driven): runs every 60 seconds.
  Simpler and more reliable than Redis pub/sub.
- Only aggregates COMPLETED hours. Never writes the current (open) hour.
- Idempotent: safe to re-run because upsert handles conflicts.
- Resilient: DB errors are logged and retried on next cycle.
- State in memory: tracks last aggregated hour per symbol so we only
  process new, unaggregated hours on each cycle.
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
# 60s is sufficient: the current hour cannot be aggregated anyway, so
# running more frequently would be wasted work.
AGGREGATION_INTERVAL_SECONDS = 60


class CandleAggregatorService:
    """
    Background service that aggregates completed M1 hours into H1 candles.

    Lifecycle:
        aggregator = CandleAggregatorService()
        asyncio.create_task(aggregator.run())  # fires and forgets

    State:
        _last_aggregated_hour: Dict[str, datetime]
            Maps symbol → UTC floor-of-hour of the most recently written H1
            candle.  Initialised from the DB on first run so restarts are safe.

    Input / output ranges:
        Reads:  market_data WHERE timeframe='M1' AND symbol=? AND time in [h_start, h_end)
        Writes: market_data WHERE timeframe='H1' AND source='MT4'
        open    = first M1 open (lowest time)
        high    = MAX(M1 highs)
        low     = MIN(M1 lows)
        last    = last M1 close (highest time)  — DB uses 'last' not 'close'
        volume  = SUM(M1 volumes)
        change  = last - open
        change_percent = ((last - open) / open) * 100

    Edge cases:
        - Zero M1 candles for an hour → skip, do not write an empty H1 candle.
        - Fewer than 60 M1 candles (market closed, data gap) → still write
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

        # Per-symbol: UTC datetime of the most recently written H1 candle time.
        # E.g.  {"CrudeOIL": datetime(2024, 3, 5, 14, 0, tzinfo=UTC)}
        # means the 14:00-14:59 hour has been written; next candidate is 15:00.
        self._last_aggregated_hour: Dict[str, Optional[datetime]] = {
            s: None for s in TRACKED_SYMBOLS
        }

        logger.info(
            "candle_aggregator_service_initialized",
            symbols=TRACKED_SYMBOLS,
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
        Initialise _last_aggregated_hour from the database.

        For each tracked symbol, query the latest H1 candle with source='MT4'
        (i.e. previously aggregated by this service, not imported historical
        data which uses other sources like BARCHART/DUKASCOPY).

        This ensures restarts are idempotent — we will not re-aggregate hours
        that are already in the DB.

        Note: Historical H1 candles imported via CSV/BARCHART are ignored here
        because they use a different source enum value.  We only track the
        hours we have written ourselves.
        """
        from src.api.dependencies import get_db_context

        logger.info("candle_aggregator_initializing_state_from_db")

        for symbol in TRACKED_SYMBOLS:
            try:
                async with get_db_context() as session:
                    latest_h1 = await self._get_latest_h1_candle(
                        session, symbol
                    )
                    if latest_h1 is not None:
                        # Floor to the hour (should already be, but be safe)
                        h1_time = latest_h1.time.replace(
                            minute=0, second=0, microsecond=0
                        )
                        if h1_time.tzinfo is None:
                            h1_time = h1_time.replace(tzinfo=timezone.utc)
                        self._last_aggregated_hour[symbol] = h1_time
                        logger.debug(
                            "candle_aggregator_state_loaded",
                            symbol=symbol,
                            last_h1=h1_time.isoformat(),
                        )
                    else:
                        logger.debug(
                            "candle_aggregator_no_existing_h1",
                            symbol=symbol,
                        )
            except Exception as exc:
                logger.warning(
                    "candle_aggregator_state_init_failed",
                    symbol=symbol,
                    error=str(exc),
                )

    async def _run_aggregation_cycle(self) -> None:
        """
        Process all tracked symbols for the current aggregation cycle.

        For each symbol, determine which completed hours have not yet been
        aggregated and write an H1 candle for each of them.

        The "last completed hour" is the UTC floor-of-hour for (now - 1 hour).
        We never write the current (open) hour because it is not yet complete.
        """
        from src.api.dependencies import get_db_context

        # Determine the most recent completed hour (UTC).
        # current time: e.g. 15:47 → last completed hour = 14:00
        now_utc = datetime.now(tz=timezone.utc)
        last_completed_hour = now_utc.replace(
            minute=0, second=0, microsecond=0
        ) - timedelta(hours=1)

        for symbol in TRACKED_SYMBOLS:
            try:
                async with get_db_context() as session:
                    await self._aggregate_symbol(
                        session, symbol, last_completed_hour
                    )
            except Exception as exc:
                logger.error(
                    "candle_aggregator_symbol_failed",
                    symbol=symbol,
                    error=str(exc),
                    exc_info=True,
                )

    async def _aggregate_symbol(
        self,
        session: AsyncSession,
        symbol: str,
        last_completed_hour: datetime,
    ) -> None:
        """
        Aggregate all un-processed completed hours for a single symbol.

        Args:
            session: Active async DB session.
            symbol: Trading symbol (e.g. "CrudeOIL").
            last_completed_hour: The floor-of-hour of the most recently
                completed hour in UTC.  We process all hours from the first
                un-processed hour up to and including this one.

        The loop walks forward one hour at a time so that if the service was
        offline for several hours, all missed hours are back-filled in order.
        """
        last_written = self._last_aggregated_hour.get(symbol)

        if last_written is None:
            # No state yet — start from the M1 data's oldest available hour
            # so we don't blindly try to back-fill the entire history.
            earliest_m1_hour = await self._get_earliest_m1_hour(
                session, symbol
            )
            if earliest_m1_hour is None:
                # No M1 data for this symbol at all; nothing to do.
                return
            candidate = earliest_m1_hour
        else:
            # Start from the hour AFTER the last one we already wrote.
            candidate = last_written + timedelta(hours=1)

        # Walk through each un-aggregated completed hour in order.
        while candidate <= last_completed_hour:
            hour_start = candidate  # inclusive
            hour_end = candidate + timedelta(hours=1)  # exclusive

            await self._aggregate_single_hour(
                session, symbol, hour_start, hour_end
            )
            candidate += timedelta(hours=1)

    async def _aggregate_single_hour(
        self,
        session: AsyncSession,
        symbol: str,
        hour_start: datetime,
        hour_end: datetime,
    ) -> None:
        """
        Aggregate M1 candles within [hour_start, hour_end) into a single H1.

        Args:
            session: Active async DB session.
            symbol: Trading symbol.
            hour_start: Inclusive start of the hour (UTC, minute=0, second=0).
            hour_end: Exclusive end of the hour (= hour_start + 1h).

        Writes:
            One row into market_data with timeframe='H1', source='MT4'.
            The 'time' of the H1 candle is hour_start (the open timestamp,
            following MT4 / MetaTrader convention).

        If zero M1 candles exist in the window, nothing is written and no
        error is raised (the hour is considered a market-closed period).

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
                MarketData.time >= hour_start,
                MarketData.time < hour_end,
            )
        )

        agg_result = await session.execute(agg_query)
        agg_row = agg_result.one()

        candle_count = agg_row.candle_count or 0
        if candle_count == 0:
            # No M1 data in this hour — market closed or data gap.
            # Do not insert an empty H1 candle; update state so we
            # don't re-attempt this hour on every subsequent cycle.
            self._last_aggregated_hour[symbol] = hour_start
            return

        # --- Step 2: Fetch the OPEN price (first M1's open) -----------------
        first_m1_query = (
            select(MarketData.open)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == "M1",
                    MarketData.time >= hour_start,
                    MarketData.time < hour_end,
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
                    MarketData.time >= hour_start,
                    MarketData.time < hour_end,
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

        # --- Step 5: Upsert H1 candle ----------------------------------------
        # Uses PostgreSQL ON CONFLICT to make re-runs safe.
        # The unique constraint is (time, source, timeframe, symbol).
        stmt = pg_insert(MarketData).values(
            time=hour_start,
            symbol=symbol,
            import_symbol=symbol,
            timeframe="H1",
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
        self._last_aggregated_hour[symbol] = hour_start

        logger.info(
            "candle_aggregator_h1_written",
            symbol=symbol,
            hour=hour_start.isoformat(),
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

    async def _get_latest_h1_candle(
        self, session: AsyncSession, symbol: str
    ) -> Optional[MarketData]:
        """
        Return the most recent MT4-aggregated H1 candle for a symbol, or None.

        Only considers candles with source='MT4' to avoid treating imported
        historical data (BARCHART, DUKASCOPY, etc.) as previously aggregated.

        Args:
            session: Active async DB session.
            symbol: Trading symbol.

        Returns:
            Latest MarketData row (timeframe='H1', source='MT4'), or None if
            no such row exists.
        """
        query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == "H1",
                    cast(MarketData.source, Text) == "MT4",
                )
            )
            .order_by(desc(MarketData.time))
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def _get_earliest_m1_hour(
        self, session: AsyncSession, symbol: str
    ) -> Optional[datetime]:
        """
        Return the UTC floor-of-hour of the earliest M1 candle for a symbol.

        Used to determine where to start back-filling when no prior H1 state
        exists (e.g. first run ever for this symbol).

        Args:
            session: Active async DB session.
            symbol: Trading symbol.

        Returns:
            UTC datetime floored to the hour of the earliest M1 candle,
            or None if no M1 data exists for the symbol.
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

        # Ensure timezone-aware
        if earliest.tzinfo is None:
            earliest = earliest.replace(tzinfo=timezone.utc)

        # Floor to the hour
        return earliest.replace(minute=0, second=0, microsecond=0)
