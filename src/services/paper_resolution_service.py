"""
Paper Resolution Watchdog Service

Scans all open paper (simulation=True) positions older than STALENESS_THRESHOLD_HOURS
that have not yet hit their SL or TP via the normal live-trading loop, and closes them
at the current market price.

Architecture:
    FastAPI lifespan → asyncio.create_task(PaperResolutionService().run())
                           ↓  every SCAN_INTERVAL_SECONDS
                       scan_once()
                           ↓ for each stale paper position
                       _resolve_position()
                           ├─ _get_current_price(symbol) — real DB fetch, NO fake
                           ├─ DELETE open_positions row
                           ├─ INSERT trading_history row (resolution_reason='watchdog_24h')
                           └─ emit 'paper_resolved' SSE event

Design decisions:
- In-process asyncio only. No new container, no new Celery worker.
- Individual resolution errors are caught so one bad position cannot stop the loop.
- If market data is unavailable for a symbol, we log a warning and SKIP — never fake.
- SL and TP bounds are NOT checked here; that is the live-trading loop's job. Positions
  that hit SL/TP are already removed before this watchdog would see them. The watchdog
  only touches positions that are STILL OPEN after STALENESS_THRESHOLD_HOURS.
- P&L calculation uses real entry price, real close price, real lot size.

Configuration (environment variables):
    PAPER_WATCHDOG_ENABLED          "true" / "false"  (default: matches PAPER_VALIDATION_MODE)
    PAPER_WATCHDOG_SCAN_INTERVAL    Seconds between scans  (default: 300)
    PAPER_WATCHDOG_STALENESS_HOURS  Hours before a paper position is considered stale (default: 24)
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import text as sa_text

from src.database.models.positions import OpenPosition
from src.database.models.trading_history import TradingHistory
from src.database.repositories.positions_repository import PositionsRepository
from src.utils.sse_events import get_sse_manager

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_SCAN_INTERVAL = 300      # 5 minutes
_DEFAULT_STALENESS_HOURS = 24     # 24 hours

# Contract size approximations for P&L calculation (units per lot).
# These are the same values used in live_trading_service.py CONTRACT_SIZES.
# The P&L formula is:  move (price units) × lots × contract_size
# For a BUY:  (exit − entry) × lots × contract_size
# For a SELL: (entry − exit) × lots × contract_size
_CONTRACT_SIZES = {
    "CrudeOIL": 1000,
    "USA500": 50,
    "GBPJPY.": 100_000,
    "GBPJPY": 100_000,
    "XAUUSD": 100,
    "BRENT_OIL": 1000,
    "#TSLA": 1000,
    "TSLA": 1000,
}
_DEFAULT_CONTRACT_SIZE = 1000


def _contract_size(symbol: str) -> int:
    """Return contract size for a symbol, falling back to 1000."""
    return _CONTRACT_SIZES.get(symbol, _DEFAULT_CONTRACT_SIZE)


def _calc_pnl(position_type: str, entry: Decimal, close: Decimal, size: Decimal, symbol: str) -> Decimal:
    """
    Calculate realized P&L for a paper position closed at `close`.

    Args:
        position_type: "BUY" or "SELL"
        entry:         Entry price (from position.price)
        close:         Close price from real market data
        size:          Lot size (from position.size)
        symbol:        Trading symbol (for contract size lookup)

    Returns:
        Realized P&L as Decimal
    """
    cs = Decimal(_contract_size(symbol))
    if position_type.upper() == "BUY":
        return (close - entry) * size * cs
    else:
        return (entry - close) * size * cs


class PaperResolutionService:
    """
    Background watchdog that resolves stale paper positions.

    Runs as an asyncio task inside the FastAPI process — no new container.
    """

    def __init__(
        self,
        scan_interval: int = _DEFAULT_SCAN_INTERVAL,
        staleness_hours: int = _DEFAULT_STALENESS_HOURS,
    ) -> None:
        """
        Initialise the watchdog.

        Args:
            scan_interval:    Seconds between each full scan.
            staleness_hours:  Age (hours) at which an open paper position is considered stale.
        """
        self._scan_interval = scan_interval
        self._staleness_hours = staleness_hours
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Forever-loop: sleep SCAN_INTERVAL, then scan_once().

        Cancellation (CancelledError) exits cleanly.
        All other exceptions are logged and the loop continues.
        """
        self._running = True
        logger.info(
            "paper_watchdog_started",
            scan_interval_seconds=self._scan_interval,
            staleness_hours=self._staleness_hours,
        )

        while self._running:
            try:
                await asyncio.sleep(self._scan_interval)
                await self.scan_once()
            except asyncio.CancelledError:
                logger.info("paper_watchdog_cancelled")
                self._running = False
                raise
            except Exception as exc:
                logger.error(
                    "paper_watchdog_loop_error",
                    error=str(exc),
                    exc_info=True,
                )

    def stop(self) -> None:
        """Signal the loop to stop (used by tests that drive the loop manually)."""
        self._running = False

    # ------------------------------------------------------------------
    # Core scan
    # ------------------------------------------------------------------

    async def scan_once(self, _db=None) -> int:
        """
        Scan all open paper positions; resolve any that are stale.

        Args:
            _db: Optional AsyncSession for testing.  In production this is
                 None and the method opens its own session via get_db_context.

        Returns:
            Number of positions resolved in this scan.
        """
        from contextlib import asynccontextmanager

        if _db is not None:
            # Test-injection path: wrap the provided session in an async context
            # so the body below can use the same `async with ... as db:` syntax.
            @asynccontextmanager
            async def _passthrough():
                yield _db

            ctx = _passthrough()
        else:
            # Local import avoids circular-import via src/api/__init__.py at
            # module level.
            from src.api.dependencies import get_db_context  # noqa: PLC0415
            ctx = get_db_context()

        staleness_cutoff = datetime.now(timezone.utc) - timedelta(hours=self._staleness_hours)
        resolved_count = 0

        async with ctx as db:
            repo = PositionsRepository(db)
            paper_positions = await repo.get_open_positions(simulation=True)

            stale = [
                p for p in paper_positions
                if _position_age_utc(p) is not None and _position_age_utc(p) < staleness_cutoff
            ]

            if not stale:
                logger.debug(
                    "paper_watchdog_scan_no_stale",
                    total_paper=len(paper_positions),
                    staleness_hours=self._staleness_hours,
                )
                return 0

            logger.info(
                "paper_watchdog_stale_found",
                stale_count=len(stale),
                total_paper=len(paper_positions),
            )

            for position in stale:
                try:
                    # Use a SAVEPOINT for each position so that a failure on one
                    # (e.g. unexpected FK constraint) rolls back only that position
                    # and does NOT abort the outer transaction for the remaining ones.
                    async with db.begin_nested():
                        closed = await self._resolve_position(position, db)
                    if closed:
                        resolved_count += 1
                except Exception as exc:
                    logger.error(
                        "paper_watchdog_resolution_failed",
                        position_id=position.id,
                        position_number=position.number,
                        symbol=position.symbol,
                        error=str(exc),
                        exc_info=True,
                    )

            # Commit all successful resolutions in the batch as one outer transaction.
            if resolved_count > 0:
                await db.commit()

        logger.info(
            "paper_watchdog_scan_complete",
            resolved=resolved_count,
            scan_interval_seconds=self._scan_interval,
        )
        return resolved_count

    # ------------------------------------------------------------------
    # Single-position resolution
    # ------------------------------------------------------------------

    async def _resolve_position(self, position: OpenPosition, db) -> bool:
        """
        Close one stale paper position at the current market price.

        Steps:
          1. Fetch current price from market_data (real DB row — no fake).
          2. If no price available, log a warning and SKIP (return False).
          3. Calculate realized P&L.
          4. Insert a TradingHistory row.
          5. Delete the OpenPosition row.
          6. Emit a 'paper_resolved' SSE event.

        Args:
            position: The OpenPosition ORM object to resolve.
            db:       The active AsyncSession.

        Returns:
            True if the position was successfully resolved, False if skipped.
        """
        symbol = position.symbol

        # Step 1: Fetch real current price — no defaults, no fakes.
        close_price = await self._get_current_price(symbol, db)
        if close_price is None:
            logger.warning(
                "paper_watchdog_no_price_skipping",
                position_id=position.id,
                symbol=symbol,
            )
            return False

        close_decimal = Decimal(str(close_price))
        entry_price = position.price
        size = position.size
        position_type = position.type

        # Step 2: Realized P&L (real entry × real close × real lot size).
        realized_pnl = _calc_pnl(position_type, entry_price, close_decimal, size, symbol)

        # Step 3: Age in days for trading_history.days_in_trade.
        opened_at = _position_age_utc(position)
        days_in_trade: Optional[Decimal] = None
        if opened_at is not None:
            age_seconds = (datetime.now(timezone.utc) - opened_at).total_seconds()
            days_in_trade = Decimal(str(round(age_seconds / 86400.0, 4)))

        now_utc = datetime.now(timezone.utc)

        # Step 4: Insert into trading_history.
        #
        # The live PostgreSQL schema uses custom enum types for `order_type`
        # (ordertype) and `action` (actiontype).  The SQLAlchemy ORM models
        # declare those columns as Text, which asyncpg rejects with a
        # DatatypeMismatchError.  We try the raw-SQL path first (PostgreSQL),
        # and fall back to the ORM path for SQLite (used in unit tests).
        #
        # resolution_reason='watchdog_24h' is carried in the SSE event, the
        # structlog entry, and the ORM path action field.  The PostgreSQL DB
        # action field uses 'CLOSE' (the nearest valid actiontype enum value).
        # Step 4: Insert into trading_history.
        #
        # Strategy: detect dialect at runtime.
        # - PostgreSQL: the schema uses custom enum types (ordertype, actiontype).
        #   SQLAlchemy ORM INSERT would fail because the ORM model declares those
        #   columns as Text while asyncpg enforces strict enum matching.
        #   We use raw SQL with explicit casts.
        # - SQLite (unit tests): no enums; use the ORM path.
        # Detect dialect via sync_session (works for both AsyncSession and
        # plain synchronous Session in unit tests).
        try:
            dialect_name = db.sync_session.get_bind().dialect.name
        except Exception:
            dialect_name = "sqlite"  # safe fallback for unit tests
        if dialect_name == "postgresql":
            await db.execute(
                sa_text(
                    """
                    INSERT INTO trading_history
                        (time, symbol, order_type, volume, price, sl, tp,
                         commission, swap, profit, action, position_id,
                         order_number, days_in_trade, simulation,
                         created_at, updated_at)
                    VALUES
                        (:time, :symbol,
                         CAST(:order_type AS ordertype),
                         :volume, :price, :sl, :tp,
                         :commission, :swap, :profit,
                         CAST('CLOSE' AS actiontype),
                         :position_id, :order_number,
                         :days_in_trade, :simulation,
                         now(), now())
                    """
                ),
                {
                    "time": now_utc,
                    "symbol": symbol,
                    "order_type": position_type,
                    "volume": float(size),
                    "price": float(close_decimal),
                    "sl": float(position.stop_loss) if position.stop_loss else None,
                    "tp": float(position.take_profit) if position.take_profit else None,
                    "commission": float(position.commission),
                    "swap": 0.0,
                    "profit": float(realized_pnl),
                    "position_id": position.id,
                    "order_number": position.number,
                    "days_in_trade": float(days_in_trade) if days_in_trade is not None else None,
                    "simulation": True,
                },
            )
        else:
            # SQLite path (unit tests) — no enum columns.
            # resolution_reason is surfaced via the SSE event + logs.
            history_row = TradingHistory(
                time=now_utc,
                symbol=symbol,
                order_type=position_type,
                volume=size,
                price=close_decimal,
                sl=position.stop_loss,
                tp=position.take_profit,
                commission=position.commission,
                swap=Decimal("0"),
                profit=realized_pnl,
                action="watchdog_24h",
                position_id=position.id,
                order_number=position.number,
                days_in_trade=days_in_trade,
                simulation=True,
            )
            db.add(history_row)
            await db.flush()

        # Step 5: Detach FK-dependent rows, then delete the open position.
        #
        # Two tables reference open_positions.id via non-CASCADE FKs:
        #   - position_strategy_history.position_id  (NOT NULL — must DELETE rows)
        #   - trading_history.position_id             (NULLABLE — NULL-out the column)
        #
        # We preserve trading history (set position_id=NULL) and remove strategy
        # history entries (they are supplementary audit rows, safe to delete).
        if dialect_name == "postgresql":
            await db.execute(
                sa_text(
                    "DELETE FROM position_strategy_history WHERE position_id = :pid"
                ),
                {"pid": position.id},
            )
            # NULL-out back-references in trading_history (including the watchdog
            # INSERT row that was just added above) so the FK no longer blocks.
            # Trading history rows remain fully queryable by order_number.
            await db.execute(
                sa_text(
                    "UPDATE trading_history SET position_id = NULL WHERE position_id = :pid"
                ),
                {"pid": position.id},
            )

        repo = PositionsRepository(db)
        await repo.delete(position.id)

        # NOTE: db.commit() is NOT called here.
        # scan_once() wraps each resolution in db.begin_nested() (SAVEPOINT).
        # The SAVEPOINT is released (committed to the outer transaction) when
        # begin_nested().__aexit__ succeeds, and the outer commit happens after
        # all positions in the batch are processed.

        logger.info(
            "paper_watchdog_resolved",
            position_id=position.id,
            position_number=position.number,
            symbol=symbol,
            type=position_type,
            entry_price=float(entry_price),
            close_price=close_price,
            realized_pnl=float(realized_pnl),
            days_in_trade=float(days_in_trade) if days_in_trade is not None else None,
            resolution_reason="watchdog_24h",
        )

        # Step 6: Emit SSE event (non-blocking — failure does NOT abort the resolution).
        try:
            sse_manager = await get_sse_manager()
            await sse_manager.emit(
                "paper_resolved",
                {
                    "position_id": position.id,
                    "position_number": position.number,
                    "symbol": symbol,
                    "type": position_type,
                    "entry_price": float(entry_price),
                    "close_price": close_price,
                    "realized_pnl": float(realized_pnl),
                    "resolution_reason": "watchdog_24h",
                    "resolved_at": now_utc.isoformat(),
                },
            )
        except Exception as sse_exc:
            logger.warning(
                "paper_watchdog_sse_emit_failed",
                error=str(sse_exc),
                position_number=position.number,
            )

        return True

    # ------------------------------------------------------------------
    # Market price lookup
    # ------------------------------------------------------------------

    async def _get_current_price(self, symbol: str, db) -> Optional[float]:
        """
        Fetch the most recent `last` price for a symbol from market_data.

        Uses the same query pattern as LiveTradingService._get_latest_price().
        Strips trailing '.' from MT4 symbol names (e.g. 'GBPJPY.' → 'GBPJPY').

        Returns:
            Current price as float, or None if no data is available.
        """
        db_symbol = symbol.rstrip(".")
        try:
            result = await db.execute(
                sa_text(
                    "SELECT last FROM market_data "
                    "WHERE symbol = :sym "
                    "ORDER BY time DESC LIMIT 1"
                ),
                {"sym": db_symbol},
            )
            row = result.first()
            if row and row[0] is not None:
                return float(row[0])
        except Exception as exc:
            logger.warning(
                "paper_watchdog_price_fetch_error",
                symbol=symbol,
                db_symbol=db_symbol,
                error=str(exc),
            )

        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position_age_utc(position: OpenPosition) -> Optional[datetime]:
    """
    Return the UTC datetime the position was created, or None if unavailable.

    Prefers `created_at` (set by TimestampMixin); falls back to `last_update`
    if created_at is missing (e.g. legacy rows inserted before the column existed).
    """
    if position.created_at is not None:
        ts = position.created_at
        # Ensure timezone-aware
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    if position.last_update is not None:
        ts = position.last_update
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    return None


# ---------------------------------------------------------------------------
# Factory helper used by main.py
# ---------------------------------------------------------------------------

def _read_env_int(key: str, default: int) -> int:
    """Read an integer env var with a default."""
    raw = os.getenv(key, "")
    if raw.strip().isdigit():
        return int(raw.strip())
    return default


def create_paper_resolution_service() -> PaperResolutionService:
    """
    Construct a PaperResolutionService from environment variables.

    PAPER_WATCHDOG_SCAN_INTERVAL    (default: 300s / 5 minutes)
    PAPER_WATCHDOG_STALENESS_HOURS  (default: 24 hours)
    """
    scan_interval = _read_env_int("PAPER_WATCHDOG_SCAN_INTERVAL", _DEFAULT_SCAN_INTERVAL)
    staleness_hours = _read_env_int("PAPER_WATCHDOG_STALENESS_HOURS", _DEFAULT_STALENESS_HOURS)
    return PaperResolutionService(
        scan_interval=scan_interval,
        staleness_hours=staleness_hours,
    )
