"""
Unit tests for MarketDataRepository keyset pagination.

Tests cursor generation and pagination logic in isolation.
Following TDD - these tests should FAIL initially, then PASS after implementation.
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.database.models.base import Base
from src.database.models.market_data import MarketData
from src.database.repositories.market_data_repository import MarketDataRepository


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/risetrader_test"


@pytest.fixture(scope="module")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

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
        await session.close()


@pytest.fixture
async def repository(db_session: AsyncSession) -> MarketDataRepository:
    """Create MarketDataRepository instance."""
    return MarketDataRepository(db_session)


@pytest.fixture
async def sample_data(db_session: AsyncSession):
    """Create sample market data for pagination testing."""
    base_time = datetime(2024, 11, 26, 10, 0, 0)
    records = []

    # Create 150 records to test pagination
    for i in range(150):
        record = MarketData(
            time=base_time + timedelta(minutes=5 * i),
            symbol="CrudeOIL",
            import_symbol="CL",
            timeframe="M5",
            source="MT4",
            open=Decimal("72.00"),
            high=Decimal("72.10"),
            low=Decimal("71.90"),
            last=Decimal("72.05"),
            change=Decimal("0.05"),
            change_percent=Decimal("0.07"),
            volume=1000,
        )
        records.append(record)

    db_session.add_all(records)
    await db_session.commit()

    return records


# =============================================================================
# T042: Unit test for keyset pagination cursor generation
# =============================================================================

@pytest.mark.asyncio
class TestKeysetPaginationCursor:
    """Test cursor generation for keyset pagination."""

    async def test_cursor_format(self, repository: MarketDataRepository, sample_data):
        """Test that cursor format is 'timestamp_id'."""
        # Get first page
        data, next_cursor = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=datetime(2024, 11, 26, 10, 0, 0),
            end=datetime(2024, 11, 27, 0, 0, 0),
            limit=50,
        )

        if next_cursor:
            # Cursor should have format: "timestamp_id"
            parts = next_cursor.split("_")
            assert len(parts) == 2

            # First part should be valid ISO timestamp
            timestamp_str = parts[0]
            datetime.fromisoformat(timestamp_str)  # Should not raise

            # Second part should be integer ID
            record_id = int(parts[1])  # Should not raise
            assert record_id > 0

    async def test_cursor_stable_ordering(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that cursor provides stable, consistent ordering."""
        # Get first page
        page1, cursor1 = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=datetime(2024, 11, 26, 10, 0, 0),
            end=datetime(2024, 11, 27, 0, 0, 0),
            limit=30,
        )

        # Get second page using cursor
        page2, cursor2 = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=datetime(2024, 11, 26, 10, 0, 0),
            end=datetime(2024, 11, 27, 0, 0, 0),
            cursor=cursor1,
            limit=30,
        )

        # No overlap between pages
        page1_ids = {record.id for record in page1}
        page2_ids = {record.id for record in page2}
        assert page1_ids.isdisjoint(page2_ids)

        # Pages should be sequential (no gaps)
        page1_times = [record.time for record in page1]
        page2_times = [record.time for record in page2]

        # Page 1 should have later times than page 2 (DESC order)
        if page1 and page2:
            assert max(page2_times) < min(page1_times)

    async def test_cursor_none_when_no_more_pages(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that cursor is None when no more data available."""
        # Request more than available records
        data, next_cursor = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=datetime(2024, 11, 26, 10, 0, 0),
            end=datetime(2024, 11, 27, 0, 0, 0),
            limit=200,  # More than 150 sample records
        )

        # Should return all data with no next cursor
        assert next_cursor is None
        assert len(data) <= 150

    async def test_pagination_consistency(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that paginating through all data retrieves all records exactly once."""
        all_records = []
        cursor = None
        page_size = 25

        # Paginate through all data
        for _ in range(10):  # Max 10 pages to avoid infinite loop
            page, cursor = await repository.get_by_time_range(
                symbol="CrudeOIL",
                timeframe="M5",
                start=datetime(2024, 11, 26, 10, 0, 0),
                end=datetime(2024, 11, 27, 0, 0, 0),
                cursor=cursor,
                limit=page_size,
            )

            all_records.extend(page)

            if cursor is None:
                break

        # Should retrieve all 150 records exactly once
        assert len(all_records) == 150

        # All IDs should be unique (no duplicates)
        ids = [record.id for record in all_records]
        assert len(ids) == len(set(ids))

    async def test_invalid_cursor_handling(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that invalid cursors are gracefully handled."""
        # Invalid cursor should be ignored and start from beginning
        invalid_cursors = [
            "invalid",
            "not_a_timestamp_123",
            "2024-11-26T10:00:00",  # Missing ID
            "2024-11-26T10:00:00_invalid",  # Invalid ID
            "_123",  # Missing timestamp
        ]

        for invalid_cursor in invalid_cursors:
            # Should not raise exception, should start from beginning
            data, next_cursor = await repository.get_by_time_range(
                symbol="CrudeOIL",
                timeframe="M5",
                start=datetime(2024, 11, 26, 10, 0, 0),
                end=datetime(2024, 11, 27, 0, 0, 0),
                cursor=invalid_cursor,
                limit=10,
            )

            # Should return data (starting from beginning due to invalid cursor)
            assert len(data) > 0


@pytest.mark.asyncio
class TestGetLatestBySymbol:
    """Test get_latest_by_symbol method."""

    async def test_get_latest_returns_most_recent(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that get_latest_by_symbol returns most recent data."""
        latest = await repository.get_latest_by_symbol(
            symbol="CrudeOIL",
            timeframe="M5",
            limit=10,
        )

        assert len(latest) == 10

        # Should be ordered chronologically (oldest first after reversal)
        times = [record.time for record in latest]
        assert times == sorted(times)

        # Most recent should be last
        most_recent = latest[-1]
        assert most_recent.time == max(record.time for record in sample_data)

    async def test_get_latest_respects_limit(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that limit parameter is respected."""
        for limit in [5, 10, 50, 100]:
            latest = await repository.get_latest_by_symbol(
                symbol="CrudeOIL",
                timeframe="M5",
                limit=limit,
            )

            assert len(latest) <= limit

    async def test_get_latest_empty_result(self, repository: MarketDataRepository):
        """Test behavior when no data exists for symbol/timeframe."""
        latest = await repository.get_latest_by_symbol(
            symbol="NONEXISTENT",
            timeframe="M5",
            limit=10,
        )

        assert latest == []


@pytest.mark.asyncio
class TestGetByTimeRange:
    """Test get_by_time_range method."""

    async def test_time_range_filtering(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test that time range filters are applied correctly."""
        start = datetime(2024, 11, 26, 12, 0, 0)  # After first records
        end = datetime(2024, 11, 26, 14, 0, 0)

        data, _ = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=start,
            end=end,
            limit=100,
        )

        # All returned data should be within range
        for record in data:
            assert start <= record.time <= end

    async def test_time_range_pagination(
        self, repository: MarketDataRepository, sample_data
    ):
        """Test pagination within time range."""
        start = datetime(2024, 11, 26, 10, 0, 0)
        end = datetime(2024, 11, 27, 0, 0, 0)

        page1, cursor = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=start,
            end=end,
            limit=20,
        )

        assert len(page1) == 20
        assert cursor is not None

        # Get next page
        page2, _ = await repository.get_by_time_range(
            symbol="CrudeOIL",
            timeframe="M5",
            start=start,
            end=end,
            cursor=cursor,
            limit=20,
        )

        assert len(page2) > 0

        # No overlap
        page1_ids = {r.id for r in page1}
        page2_ids = {r.id for r in page2}
        assert page1_ids.isdisjoint(page2_ids)
