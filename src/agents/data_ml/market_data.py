"""
MarketDataAgent - Real-time Market Data Streaming and Validation

Responsibilities:
- Stream tick data from MT4 or database
- Validate data quality (missing values, outliers, timestamps)
- Store validated ticks to database
- Emit new_tick events for downstream agents

Performance Target: <20ms per tick processing
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class MarketDataAgent(BaseAgent):
    """
    Streams and validates market data from MT4/database

    Data Flow:
    1. Fetch ticks from source (MT4 ZMQ or PostgreSQL)
    2. Validate data quality (completeness, range, timestamps)
    3. Store valid ticks to database
    4. Emit 'new_tick' events
    5. Emit 'data_quality_issue' on validation failures
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=4,  # High priority - data source
        )

        # Configuration
        self.symbols = config.get("symbols", ["CrudeOIL"])
        self.timeframes = config.get("timeframes", ["M1", "M5"])
        self.batch_size = config.get("stream_batch_size", 10)
        self.validation_enabled = config.get("validation_enabled", True)
        self.store_to_db = config.get("store_to_db", True)

        # Database
        self.db_url = config.get("database_url", "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader")
        self.engine = None
        self.async_session = None

        # MT4 Connection (placeholder for ZMQ)
        self.mt4_connected = False

        # Validation stats
        self.ticks_received = 0
        self.ticks_validated = 0
        self.ticks_rejected = 0

        # Batch buffer
        self.tick_buffer: List[Dict[str, Any]] = []

        # Streaming control
        self._stream_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize database connection and subscribe to events"""
        try:
            # Setup database connection
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

            self.logger.info(
                "market_data_agent_initialized",
                symbols=self.symbols,
                timeframes=self.timeframes,
                batch_size=self.batch_size,
            )

            # Start streaming task
            self._stream_task = asyncio.create_task(
                self._stream_market_data(),
                name=f"{self.agent_id}_stream"
            )

        except Exception as e:
            self.logger.error("initialization_failed", error=str(e), exc_info=True)
            raise

    async def cleanup(self) -> None:
        """Cleanup resources"""
        try:
            # Stop streaming
            if self._stream_task:
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except asyncio.CancelledError:
                    pass

            # Close database
            if self.engine:
                await self.engine.dispose()

            self.logger.info(
                "market_data_agent_cleanup",
                ticks_received=self.ticks_received,
                ticks_validated=self.ticks_validated,
                ticks_rejected=self.ticks_rejected,
            )

        except Exception as e:
            self.logger.error("cleanup_failed", error=str(e))

    async def process_event(self, event: Event) -> None:
        """
        Process incoming events

        MarketDataAgent is a data source, so it typically doesn't process events.
        However, we could add control events like 'pause_streaming', 'resume_streaming'.
        """
        if event.event_type == "pause_streaming":
            await self._pause_streaming()
        elif event.event_type == "resume_streaming":
            await self._resume_streaming()
        else:
            self.logger.debug("unhandled_event", event_type=event.event_type)

    async def _stream_market_data(self) -> None:
        """
        Main streaming loop

        Simulates reading from MT4 or database and emits ticks.
        In production, this would connect to MT4 ZMQ stream or poll database.
        """
        self.logger.info("market_data_streaming_started")

        while self.running:
            try:
                # For now, simulate fetching from database
                # In production: Replace with MT4 ZMQ or real-time feed
                ticks = await self._fetch_ticks_from_db()

                if not ticks:
                    # No new data, wait before next poll
                    await asyncio.sleep(1.0)
                    continue

                # Process each tick
                for tick in ticks:
                    await self._process_tick(tick)

                # Small delay to prevent tight loop
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("streaming_error", error=str(e), exc_info=True)
                await asyncio.sleep(5.0)  # Back off on error

    async def _fetch_ticks_from_db(self) -> List[Dict[str, Any]]:
        """
        Fetch recent ticks from database

        In production, this would be replaced by MT4 ZMQ stream.
        For now, we query the last N records from market_data table.
        """
        try:
            async with self.async_session() as session:
                # Query recent ticks (simulating real-time)
                # This is a placeholder - in production use MT4 ZMQ
                query = text("""
                    SELECT
                        symbol,
                        timeframe,
                        time,
                        open,
                        high,
                        low,
                        last as close,
                        volume
                    FROM market_data
                    WHERE symbol = ANY(:symbols)
                    ORDER BY time DESC
                    LIMIT :limit
                """)

                # Execute raw SQL for now (add ORM models later)
                result = await session.execute(
                    query,
                    {"symbols": self.symbols, "limit": self.batch_size}
                )

                rows = result.fetchall()

                ticks = []
                for row in rows:
                    ticks.append({
                        "symbol": row[0],
                        "timeframe": row[1],
                        "timestamp": row[2].isoformat() if row[2] else None,
                        "open": float(row[3]),
                        "high": float(row[4]),
                        "low": float(row[5]),
                        "close": float(row[6]),
                        "volume": int(row[7]) if row[7] else 0,
                    })

                return ticks

        except Exception as e:
            self.logger.error("fetch_ticks_failed", error=str(e))
            return []

    async def _process_tick(self, tick: Dict[str, Any]) -> None:
        """
        Process individual tick: validate and emit

        Args:
            tick: Raw tick data
        """
        self.ticks_received += 1

        # Validate tick
        if self.validation_enabled:
            is_valid, reason = self._validate_tick(tick)

            if not is_valid:
                self.ticks_rejected += 1

                # Emit data quality issue
                await self.publish_event(
                    event_type="data_quality_issue",
                    data={
                        "tick": tick,
                        "reason": reason,
                        "timestamp": time.time(),
                    },
                    priority=EventPriority.HIGH,
                )

                self.logger.warning(
                    "tick_validation_failed",
                    symbol=tick.get("symbol"),
                    reason=reason,
                )
                return

        self.ticks_validated += 1

        # Store to database if enabled
        if self.store_to_db:
            await self._store_tick(tick)

        # Emit new_tick event
        await self.publish_event(
            event_type="new_tick",
            data=tick,
            priority=EventPriority.NORMAL,
        )

        # Update shared context with latest tick
        await self.set_context(
            f"last_tick_{tick.get('symbol')}",
            tick,
            ttl=300,  # 5 minutes
        )

    def _validate_tick(self, tick: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate tick data quality

        Checks:
        - Required fields present
        - Price values positive and valid
        - OHLC relationships (high >= open/close, low <= open/close)
        - Timestamp not in future

        Args:
            tick: Tick data to validate

        Returns:
            (is_valid, reason): Tuple of validation result and failure reason
        """
        # Check required fields
        required_fields = ["symbol", "timestamp", "open", "high", "low", "close"]
        for field in required_fields:
            if field not in tick:
                return False, f"missing_field_{field}"

        # Check price values
        try:
            open_price = float(tick["open"])
            high_price = float(tick["high"])
            low_price = float(tick["low"])
            close_price = float(tick["close"])

            # Must be positive
            if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
                return False, "invalid_price_negative"

            # OHLC relationships
            if high_price < max(open_price, close_price):
                return False, "invalid_high_too_low"

            if low_price > min(open_price, close_price):
                return False, "invalid_low_too_high"

            # Check for extreme moves (>10% in one tick)
            price_range = high_price - low_price
            avg_price = (open_price + close_price) / 2
            if price_range / avg_price > 0.10:
                return False, "extreme_price_move"

        except (TypeError, ValueError) as e:
            return False, f"invalid_price_format_{str(e)}"

        # Check timestamp
        try:
            tick_time = tick["timestamp"]
            if isinstance(tick_time, str):
                tick_time = datetime.fromisoformat(tick_time).timestamp()

            current_time = time.time()

            # Not in future
            if tick_time > current_time + 60:  # 1 minute tolerance
                return False, "timestamp_future"

            # Not too old (more than 7 days)
            if current_time - tick_time > 7 * 24 * 3600:
                return False, "timestamp_too_old"

        except Exception as e:
            return False, f"invalid_timestamp_{str(e)}"

        return True, None

    async def _store_tick(self, tick: Dict[str, Any]) -> None:
        """
        Store validated tick to database

        Args:
            tick: Validated tick data
        """
        try:
            # Add to buffer
            self.tick_buffer.append(tick)

            # Batch insert when buffer is full
            if len(self.tick_buffer) >= self.batch_size:
                await self._flush_tick_buffer()

        except Exception as e:
            self.logger.error("store_tick_failed", error=str(e))

    async def _flush_tick_buffer(self) -> None:
        """Flush tick buffer to database (batch insert)"""
        if not self.tick_buffer:
            return

        try:
            async with self.async_session() as session:
                # Bulk insert (placeholder - needs ORM model)
                # For now, just clear buffer
                self.logger.debug(
                    "tick_buffer_flushed",
                    count=len(self.tick_buffer),
                )

                self.tick_buffer.clear()

        except Exception as e:
            self.logger.error("flush_buffer_failed", error=str(e))

    async def _pause_streaming(self) -> None:
        """Pause market data streaming"""
        await self.pause()
        self.logger.info("streaming_paused")

    async def _resume_streaming(self) -> None:
        """Resume market data streaming"""
        await self.resume()
        self.logger.info("streaming_resumed")
