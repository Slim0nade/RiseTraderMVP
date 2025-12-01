"""
Integration tests for Market Data API endpoints.

Tests the full flow from API request through service/repository to database.
Following TDD - these tests should FAIL initially, then PASS after implementation.
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.api.main import app
from src.database.models.base import Base
from src.database.models.market_data import MarketData


# Test database URL (use different database for tests)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/risetrader_test"


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def sample_market_data(db_session: AsyncSession):
    """Create sample market data for testing."""
    # Create 100 market data records for CrudeOIL M5
    base_time = datetime(2024, 11, 26, 10, 0, 0)
    records = []

    for i in range(100):
        record = MarketData(
            time=base_time + timedelta(minutes=5 * i),
            symbol="CrudeOIL",
            import_symbol="CL",
            timeframe="M5",
            source="MT4",
            open=Decimal("72.00") + Decimal(str(i * 0.01)),
            high=Decimal("72.10") + Decimal(str(i * 0.01)),
            low=Decimal("71.90") + Decimal(str(i * 0.01)),
            last=Decimal("72.05") + Decimal(str(i * 0.01)),
            change=Decimal("0.05"),
            change_percent=Decimal("0.07"),
            volume=1000 + i * 10,
        )
        records.append(record)

    db_session.add_all(records)
    await db_session.commit()

    return records


# =============================================================================
# T037: Integration test for market data retrieval with pagination
# =============================================================================

@pytest.mark.asyncio
class TestMarketDataRetrieval:
    """Test market data retrieval API endpoint."""

    async def test_get_market_data_latest(self, client: AsyncClient, sample_market_data):
        """Test GET /api/market-data/{symbol} returns latest data."""
        response = await client.get(
            "/api/market-data/CrudeOIL",
            params={"timeframe": "M5", "limit": 50},
        )

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert len(data["data"]) <= 50
        assert data["symbol"] == "CrudeOIL"
        assert data["total"] >= 50

    async def test_get_market_data_with_cursor_pagination(
        self, client: AsyncClient, sample_market_data
    ):
        """Test keyset pagination with cursor parameter."""
        # First page
        response1 = await client.get(
            "/api/market-data/CrudeOIL",
            params={"timeframe": "M5", "limit": 20},
        )

        assert response1.status_code == 200
        data1 = response1.json()

        # Should have next_cursor if more data available
        if data1["total"] > 20:
            assert data1.get("next_cursor") is not None

            # Second page using cursor
            response2 = await client.get(
                "/api/market-data/CrudeOIL",
                params={
                    "timeframe": "M5",
                    "limit": 20,
                    "cursor": data1["next_cursor"],
                },
            )

            assert response2.status_code == 200
            data2 = response2.json()

            # Data from second page should be different from first page
            first_page_ids = {item["id"] for item in data1["data"]}
            second_page_ids = {item["id"] for item in data2["data"]}
            assert first_page_ids.isdisjoint(second_page_ids)

    async def test_get_market_data_invalid_symbol(self, client: AsyncClient):
        """Test 404 response for non-existent symbol."""
        response = await client.get(
            "/api/market-data/INVALID_SYMBOL",
            params={"timeframe": "M5"},
        )

        assert response.status_code == 404
        error = response.json()
        assert "error" in error
        assert "detail" in error


# =============================================================================
# T038: Integration test for market data time range queries
# =============================================================================

@pytest.mark.asyncio
class TestMarketDataTimeRange:
    """Test market data time range query endpoint."""

    async def test_get_market_data_by_time_range(
        self, client: AsyncClient, sample_market_data
    ):
        """Test GET /api/market-data/{symbol}/range with time filters."""
        start_time = datetime(2024, 11, 26, 10, 0, 0).isoformat()
        end_time = datetime(2024, 11, 26, 12, 0, 0).isoformat()

        response = await client.get(
            "/api/market-data/CrudeOIL/range",
            params={
                "start_time": start_time,
                "end_time": end_time,
                "timeframe": "M5",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert data["symbol"] == "CrudeOIL"
        assert data["start_time"] == start_time
        assert data["end_time"] == end_time

        # All returned data should be within time range
        for item in data["data"]:
            item_time = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            assert (
                datetime.fromisoformat(start_time)
                <= item_time
                <= datetime.fromisoformat(end_time)
            )

    async def test_get_market_data_range_with_pagination(
        self, client: AsyncClient, sample_market_data
    ):
        """Test time range query with cursor pagination."""
        start_time = datetime(2024, 11, 26, 10, 0, 0).isoformat()
        end_time = datetime(2024, 11, 26, 20, 0, 0).isoformat()

        response = await client.get(
            "/api/market-data/CrudeOIL/range",
            params={
                "start_time": start_time,
                "end_time": end_time,
                "timeframe": "M5",
                "limit": 30,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 30

    async def test_get_market_data_range_invalid_timeframe(
        self, client: AsyncClient
    ):
        """Test 400 response for invalid timeframe."""
        response = await client.get(
            "/api/market-data/CrudeOIL/range",
            params={
                "start_time": datetime(2024, 11, 26, 10, 0, 0).isoformat(),
                "end_time": datetime(2024, 11, 26, 12, 0, 0).isoformat(),
                "timeframe": "INVALID",
            },
        )

        assert response.status_code == 400
        error = response.json()
        assert "error" in error
        assert "timeframe" in error["detail"].lower()


# =============================================================================
# T039: Integration test for symbols listing with metadata
# =============================================================================

@pytest.mark.asyncio
class TestSymbolsListing:
    """Test symbols listing endpoint."""

    async def test_get_available_symbols(
        self, client: AsyncClient, sample_market_data
    ):
        """Test GET /api/market-data/symbols returns all symbols."""
        response = await client.get("/api/market-data/symbols")

        assert response.status_code == 200
        data = response.json()

        assert "symbols" in data
        assert "total" in data
        assert data["total"] > 0

        # Should include CrudeOIL from sample data
        symbols = [s["symbol"] for s in data["symbols"]]
        assert "CrudeOIL" in symbols

    async def test_symbols_include_metadata(
        self, client: AsyncClient, sample_market_data
    ):
        """Test that symbols response includes metadata."""
        response = await client.get("/api/market-data/symbols")

        assert response.status_code == 200
        data = response.json()

        for symbol_info in data["symbols"]:
            assert "symbol" in symbol_info
            assert "data_points_count" in symbol_info
            # Optional fields may be present
            assert symbol_info["data_points_count"] >= 0

    async def test_symbols_with_timeframe_filter(
        self, client: AsyncClient, sample_market_data
    ):
        """Test symbols filtering by timeframe."""
        response = await client.get(
            "/api/market-data/symbols",
            params={"timeframe": "M5"},
        )

        assert response.status_code == 200
        data = response.json()

        # All symbols should have M5 data
        assert len(data["symbols"]) > 0


# =============================================================================
# T040: Integration test for SSE market data streaming
# (Note: SSE testing is complex, this is a placeholder for the structure)
# =============================================================================

@pytest.mark.asyncio
class TestMarketDataStreaming:
    """Test SSE streaming endpoint for real-time market data."""

    @pytest.mark.skip(reason="SSE streaming requires Redis pub/sub setup")
    async def test_stream_market_data_connection(self, client: AsyncClient):
        """Test SSE stream connection establishment."""
        # Note: This test requires Redis pub/sub to be running
        # and MT4 service publishing events
        response = await client.get(
            "/api/stream/market-data",
            params={"symbols": "CrudeOIL"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

    @pytest.mark.skip(reason="SSE streaming requires Redis pub/sub setup")
    async def test_stream_receives_updates(self, client: AsyncClient):
        """Test that SSE stream receives market data updates."""
        # This would require:
        # 1. Connect to SSE stream
        # 2. Publish test event to Redis channel
        # 3. Verify event received via SSE
        pass

    @pytest.mark.skip(reason="SSE streaming requires Redis pub/sub setup")
    async def test_stream_handles_multiple_symbols(self, client: AsyncClient):
        """Test streaming multiple symbols simultaneously."""
        pass


# =============================================================================
# Performance and Edge Case Tests
# =============================================================================

@pytest.mark.asyncio
class TestMarketDataPerformance:
    """Test market data API performance requirements."""

    async def test_large_dataset_performance(
        self, client: AsyncClient, sample_market_data
    ):
        """Test that retrieving 500 candlesticks completes within 2 seconds."""
        import time

        start = time.time()

        response = await client.get(
            "/api/market-data/CrudeOIL",
            params={"timeframe": "M5", "limit": 500},
        )

        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 2.0  # Must complete in under 2 seconds (spec requirement)

    async def test_concurrent_requests(
        self, client: AsyncClient, sample_market_data
    ):
        """Test handling multiple concurrent requests."""
        import asyncio

        # Send 10 concurrent requests
        tasks = [
            client.get("/api/market-data/CrudeOIL", params={"timeframe": "M5"})
            for _ in range(10)
        ]

        responses = await asyncio.gather(*tasks)

        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)
