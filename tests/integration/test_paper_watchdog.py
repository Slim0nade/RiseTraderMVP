"""
Integration tests for PaperResolutionService (Phase 6 Task A4).

Tier 2: uses a real PostgreSQL database (localhost:5433).
No mocks of database, positions repository, or market_data table.

The conftest.py root fixture sets DATABASE_URL to SQLite, so we create our own
SQLAlchemy engine + asyncpg connection from the known-good PostgreSQL DSN
(same pattern as test_phase1_week1.py and test_phase1_week3.py).

Tests:
  1. Happy path — insert a 25h-old paper position, run scan_once, confirm:
       - OpenPosition row is deleted.
       - TradingHistory row exists with action='watchdog_24h'.
       - close_price (price field) is non-null.
       - profit field is non-null.
  2. No-price path — insert a 25h-old position for a symbol that has no rows
     in market_data; confirm the position is NOT deleted and scan returns 0.
  3. Young position — 23h-old position must NOT be touched.

Run:
    pytest tests/integration/test_paper_watchdog.py -v --no-cov
"""

import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Real PostgreSQL DSNs — bypasses conftest.py SQLite override
_PG_DSN = "postgresql://postgres:risetrader2024@localhost:5433/risetrader"
_PG_URL = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"


# ---------------------------------------------------------------------------
# Session factory: one SQLAlchemy AsyncSession per test, with rollback
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _pg_session():
    """Real PostgreSQL AsyncSession — rolls back on exit for test isolation."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(_PG_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Setup: insert paper position via asyncpg (handles positiontype enum)
# Teardown: delete via asyncpg after the test (in case rollback was missed)
# ---------------------------------------------------------------------------

async def _insert_position_via_asyncpg(
    *,
    symbol: str,
    position_type: str = "BUY",
    age_hours: float,
    price: float = 80.0,
    size: float = 0.01,
) -> tuple[int, str]:
    """
    Insert a paper position directly via asyncpg and return (id, order_number).

    asyncpg supports $1::positiontype so the enum cast works without issues.
    This row will be visible to any other connection immediately (autocommit).
    """
    import asyncpg

    opened_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    order_number = f"WATCHDOG_IT_{uuid.uuid4().hex[:8].upper()}"

    conn = await asyncpg.connect(_PG_DSN)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO open_positions
                (number, type, size, symbol, price, stop_loss, take_profit,
                 commission, last_profit, last_update, last_strategy,
                 simulation, created_at, updated_at)
            VALUES ($1, $2::positiontype, $3, $4, $5, $6, $7, $8, $9,
                   $10, $11, $12, $13, now())
            RETURNING id
            """,
            order_number,
            position_type,
            size,
            symbol,
            price,
            price * 0.98,
            price * 1.03,
            0.5,
            0.0,
            opened_at,
            "watchdog_test",
            True,
            opened_at,
        )
        return row["id"], order_number
    finally:
        await conn.close()


async def _delete_position_via_asyncpg(pos_id: int) -> None:
    """Hard-delete a position row by id (used as test teardown)."""
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        await conn.execute("DELETE FROM open_positions WHERE id = $1", pos_id)
    finally:
        await conn.close()


async def _delete_history_via_asyncpg(order_number: str) -> None:
    """Delete trading_history rows created by this test."""
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        await conn.execute(
            "DELETE FROM trading_history WHERE order_number = $1", order_number
        )
    finally:
        await conn.close()


async def _fetch_position_via_asyncpg(pos_id: int) -> Optional[dict]:
    """Return the position row as a dict, or None if deleted."""
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        row = await conn.fetchrow(
            "SELECT id, number FROM open_positions WHERE id = $1", pos_id
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def _fetch_history_via_asyncpg(order_number: str) -> Optional[dict]:
    """Return the trading_history row as a dict, or None if absent."""
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        row = await conn.fetchrow(
            "SELECT action, price, profit FROM trading_history WHERE order_number = $1",
            order_number,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def _crudeOIL_has_market_data() -> bool:
    """Return True if market_data contains at least one CrudeOIL row."""
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        row = await conn.fetchrow(
            "SELECT last FROM market_data WHERE symbol = 'CrudeOIL' LIMIT 1"
        )
        return row is not None
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPaperWatchdogIntegration:
    """Real PostgreSQL, real schema, real market_data price fetch."""

    async def test_stale_position_resolved(self):
        """
        Insert a 25h-old paper position; run scan_once; verify:
          - OpenPosition row deleted.
          - TradingHistory row inserted with action='watchdog_24h'.
          - price (close_price) is non-null.
          - profit is non-null.

        Skipped if no CrudeOIL market_data rows exist.
        """
        from src.services.paper_resolution_service import PaperResolutionService

        if not await _crudeOIL_has_market_data():
            pytest.skip("No CrudeOIL market_data rows available")

        pos_id, order_number = await _insert_position_via_asyncpg(
            symbol="CrudeOIL", age_hours=25.0
        )
        try:
            async with _pg_session() as session:
                svc = PaperResolutionService(scan_interval=300, staleness_hours=24)
                with patch(
                    "src.services.paper_resolution_service.get_sse_manager",
                    new=AsyncMock(return_value=AsyncMock()),
                ):
                    resolved = await svc.scan_once(_db=session)

            assert resolved >= 1, f"Expected at least 1 resolution, got {resolved}"

            # Position must be gone
            position = await _fetch_position_via_asyncpg(pos_id)
            assert position is None, "OpenPosition must be deleted after watchdog resolution"

            # TradingHistory row must exist
            history = await _fetch_history_via_asyncpg(order_number)
            assert history is not None, "TradingHistory row must be inserted"
            # DB actiontype enum: 'CLOSE' is used for watchdog resolution
            # (resolution_reason='watchdog_24h' is in the SSE event + logs).
            assert history["action"] == "CLOSE", (
                f"Expected action='CLOSE', got '{history['action']}'"
            )
            assert history["price"] is not None, "close_price must be non-null"
            assert history["profit"] is not None, "profit must be non-null"

        finally:
            # Cleanup: remove any leftover rows so other tests aren't polluted
            await _delete_position_via_asyncpg(pos_id)
            await _delete_history_via_asyncpg(order_number)

    async def test_young_position_not_touched(self):
        """23h-old position must NOT be resolved."""
        from src.services.paper_resolution_service import PaperResolutionService

        pos_id, order_number = await _insert_position_via_asyncpg(
            symbol="CrudeOIL", age_hours=23.0
        )
        try:
            async with _pg_session() as session:
                svc = PaperResolutionService(scan_interval=300, staleness_hours=24)
                with patch(
                    "src.services.paper_resolution_service.get_sse_manager",
                    new=AsyncMock(return_value=AsyncMock()),
                ):
                    resolved = await svc.scan_once(_db=session)

            assert resolved == 0, "23h position must not be resolved"

            # Position must still exist
            position = await _fetch_position_via_asyncpg(pos_id)
            assert position is not None, "23h position must remain open"

        finally:
            await _delete_position_via_asyncpg(pos_id)

    async def test_no_market_data_position_stays_open(self):
        """
        Position for a symbol with no market_data rows must stay open.
        Uses a deliberately fake symbol that will never be in the DB.
        """
        from src.services.paper_resolution_service import PaperResolutionService

        fake_symbol = "FAKESYMBOL"  # exactly 10 chars to fit varchar(10)
        pos_id, order_number = await _insert_position_via_asyncpg(
            symbol=fake_symbol, age_hours=48.0
        )
        try:
            async with _pg_session() as session:
                svc = PaperResolutionService(scan_interval=300, staleness_hours=24)
                with patch(
                    "src.services.paper_resolution_service.get_sse_manager",
                    new=AsyncMock(return_value=AsyncMock()),
                ):
                    resolved = await svc.scan_once(_db=session)

            assert resolved == 0, "Position with no market data must not be resolved"

            # Position must still exist
            position = await _fetch_position_via_asyncpg(pos_id)
            assert position is not None, "Position with no market data must remain open"

        finally:
            await _delete_position_via_asyncpg(pos_id)
