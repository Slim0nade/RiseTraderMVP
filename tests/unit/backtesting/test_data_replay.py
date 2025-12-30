"""
Unit tests for DataReplayEngine.

Tests historical data streaming, chronological ordering, and data validation.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.database.models.market_data import MarketData
from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.backtesting.data_replay_engine import (
    DataReplayEngine,
    MarketTick
)


class TestMarketTick:
    """Test MarketTick dataclass."""

    def test_from_market_data(self):
        """Test creation from MarketData model."""
        md = MarketData(
            id=1,
            symbol="EURUSD",
            time=datetime(2024, 1, 1, 10, 0),
            source="MT4",
            timeframe="M5",
            open=Decimal("1.1000"),
            high=Decimal("1.1050"),
            low=Decimal("1.0950"),
            last=Decimal("1.1025"),
            volume=Decimal("1000")
        )

        tick = MarketTick.from_market_data(md)

        assert tick.symbol == "EURUSD"
        assert tick.timestamp == datetime(2024, 1, 1, 10, 0)
        assert tick.open == Decimal("1.1000")
        assert tick.high == Decimal("1.1050")
        assert tick.low == Decimal("1.0950")
        assert tick.close == Decimal("1.1025")
        assert tick.volume == 1000


class TestDataReplayEngine:
    """Test DataReplayEngine class."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock MarketDataRepository."""
        repository = AsyncMock(spec=MarketDataRepository)
        return repository

    @pytest.fixture
    def engine(self, mock_repository):
        """Create DataReplayEngine with mock repository."""
        return DataReplayEngine(
            repository=mock_repository,
            chunk_size=100
        )

    @pytest.mark.asyncio
    async def test_initialization(self, mock_repository):
        """Test engine initializes with correct parameters."""
        engine = DataReplayEngine(
            repository=mock_repository,
            chunk_size=500
        )

        assert engine.repository == mock_repository
        assert engine.chunk_size == 500

    @pytest.mark.asyncio
    async def test_replay_chronological_ordering(self, engine, mock_repository):
        """Test that candles are yielded in chronological order."""
        # Create mock candles
        candles = [
            MarketData(
                id=i,
                symbol="EURUSD",
                time=datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i*5),
                source="MT4",
                timeframe="M5",
                open=Decimal("1.1000"),
                high=Decimal("1.1050"),
                low=Decimal("1.0950"),
                last=Decimal("1.1025"),
                volume=Decimal("100")
            )
            for i in range(10)
        ]

        # Mock the streaming method to yield chunks
        async def mock_stream(*args, **kwargs):
            yield candles[:5]
            yield candles[5:]

        mock_repository.get_historical_candles_streamed = mock_stream

        # Collect all ticks
        ticks = []
        async for tick in engine.replay_historical_data(
            symbol="EURUSD",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2)
        ):
            ticks.append(tick)

        # Verify chronological order
        assert len(ticks) == 10
        for i in range(len(ticks) - 1):
            assert ticks[i].timestamp <= ticks[i+1].timestamp

    @pytest.mark.asyncio
    async def test_get_total_candles(self, engine, mock_repository):
        """Test retrieving total candle count."""
        mock_repository.count_candles_in_range.return_value = 5000

        total = await engine.get_total_candles(
            symbol="EURUSD",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31)
        )

        assert total == 5000
        mock_repository.count_candles_in_range.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_data_availability_sufficient(self, engine, mock_repository):
        """Test validation passes with sufficient data."""
        mock_repository.validate_data_continuity.return_value = {
            "total_candles": 1000,
            "has_gaps": False,
            "first_candle_time": datetime(2024, 1, 1),
            "last_candle_time": datetime(2024, 12, 31)
        }

        validation = await engine.validate_data_availability(
            symbol="EURUSD",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31)
        )

        assert validation["can_proceed"] is True
        assert "Ready for backtest" in validation["recommendation"]

    @pytest.mark.asyncio
    async def test_validate_data_availability_insufficient(self, engine, mock_repository):
        """Test validation fails with insufficient data."""
        mock_repository.validate_data_continuity.return_value = {
            "total_candles": 50,  # Less than 100 minimum
            "has_gaps": False,
            "first_candle_time": datetime(2024, 1, 1),
            "last_candle_time": datetime(2024, 1, 2)
        }

        validation = await engine.validate_data_availability(
            symbol="EURUSD",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2)
        )

        assert validation["can_proceed"] is False
        assert "Consider longer date range" in validation["recommendation"]

    @pytest.mark.asyncio
    async def test_validate_data_availability_no_data(self, engine, mock_repository):
        """Test validation fails with no data."""
        mock_repository.validate_data_continuity.return_value = {
            "total_candles": 0,
            "has_gaps": True,
            "first_candle_time": None,
            "last_candle_time": None,
            "error": "No data found in range"
        }

        validation = await engine.validate_data_availability(
            symbol="EURUSD",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2)
        )

        assert validation["can_proceed"] is False
        assert "Cannot run backtest" in validation["recommendation"]

    @pytest.mark.asyncio
    async def test_get_price_at_timestamp(self, engine, mock_repository):
        """Test retrieving price at specific timestamp."""
        candle = MarketData(
            id=1,
            symbol="EURUSD",
            time=datetime(2024, 1, 1, 10, 0),
            source="MT4",
            timeframe="M5",
            open=Decimal("1.1000"),
            high=Decimal("1.1050"),
            low=Decimal("1.0950"),
            last=Decimal("1.1025"),
            volume=Decimal("100")
        )

        mock_repository.get_by_timeframe_range.return_value = [candle]

        tick = await engine.get_price_at_timestamp(
            symbol="EURUSD",
            timeframe="M5",
            timestamp=datetime(2024, 1, 1, 10, 0)
        )

        assert tick is not None
        assert tick.close == Decimal("1.1025")

    @pytest.mark.asyncio
    async def test_replay_with_progress(self, engine, mock_repository):
        """Test replay with progress tracking."""
        candles = [
            MarketData(
                id=i,
                symbol="EURUSD",
                time=datetime(2024, 1, 1) + timedelta(minutes=i*5),
                source="MT4",
                timeframe="M5",
                open=Decimal("1.1000"),
                high=Decimal("1.1050"),
                low=Decimal("1.0950"),
                last=Decimal("1.1025"),
                volume=Decimal("100")
            )
            for i in range(5)
        ]

        async def mock_stream(*args, **kwargs):
            yield candles

        mock_repository.get_historical_candles_streamed = mock_stream
        mock_repository.count_candles_in_range.return_value = 5

        progress_updates = []

        def progress_callback(processed, total):
            progress_updates.append((processed, total))

        ticks_with_progress = []
        async for tick, processed, total in engine.replay_with_progress(
            symbol="EURUSD",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            progress_callback=progress_callback
        ):
            ticks_with_progress.append((tick, processed, total))

        # Verify all ticks received
        assert len(ticks_with_progress) == 5

        # Verify progress tracking
        for tick, processed, total in ticks_with_progress:
            assert total == 5
            assert 1 <= processed <= 5
