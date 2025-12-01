"""
Unit tests for ForecastService.

These tests verify the caching logic and business rules for forecast operations
without requiring database connections.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.services.forecast_service import ForecastService
from src.database.models.forecasts import Forecast


@pytest.mark.asyncio
class TestForecastServiceCaching:
    """Unit tests for ForecastService caching behavior."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock ForecastRepository."""
        repository = Mock()
        repository.get_latest_forecasts = AsyncMock()
        repository.get_forecasts_by_symbol = AsyncMock()
        return repository

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.set = AsyncMock()
        redis_client.delete = AsyncMock()
        return redis_client

    @pytest.fixture
    def service(self, mock_repository, mock_redis):
        """Create ForecastService with mocked dependencies."""
        return ForecastService(repository=mock_repository, redis=mock_redis)

    async def test_get_latest_forecasts_cache_miss(
        self, service, mock_repository, mock_redis
    ):
        """Test that cache miss fetches from database and stores in cache."""
        now = datetime.now(timezone.utc)
        mock_forecasts = [
            Forecast(
                id=1,
                symbol="CrudeOIL",
                timeframe="H1",
                horizon="1h",
                predicted_price=Decimal("85.42"),
                confidence=Decimal("0.87"),
                model_name="XGBoost_v1",
                created_at=now,
                forecast_time=now + timedelta(hours=1),
            )
        ]

        # Mock cache miss
        mock_redis.get.return_value = None

        # Mock repository response
        mock_repository.get_latest_forecasts.return_value = mock_forecasts

        # Call service method
        result = await service.get_latest_forecasts(symbol=None, horizon=None)

        # Verify repository was called
        mock_repository.get_latest_forecasts.assert_called_once()

        # Verify cache was written
        mock_redis.set.assert_called_once()
        cache_key = mock_redis.set.call_args[0][0]
        assert "forecasts:latest" in cache_key

        # Verify TTL is 1 hour (3600 seconds)
        assert mock_redis.set.call_args[1]["ex"] == 3600

        assert len(result) == 1
        assert result[0].symbol == "CrudeOIL"

    async def test_get_latest_forecasts_cache_hit(self, service, mock_repository, mock_redis):
        """Test that cache hit returns cached data without database query."""
        now = datetime.now(timezone.utc)

        # Mock cached data
        cached_data = {
            "forecasts": [
                {
                    "id": 1,
                    "symbol": "CrudeOIL",
                    "timeframe": "H1",
                    "horizon": "1h",
                    "predicted_price": "85.42",
                    "confidence": "0.87",
                    "model_name": "XGBoost_v1",
                    "created_at": now.isoformat(),
                    "forecast_time": (now + timedelta(hours=1)).isoformat(),
                }
            ],
            "cached_at": now.isoformat(),
        }

        import json
        mock_redis.get.return_value = json.dumps(cached_data)

        # Call service method
        result = await service.get_latest_forecasts(symbol=None, horizon=None)

        # Verify repository was NOT called (cache hit)
        mock_repository.get_latest_forecasts.assert_not_called()

        # Verify result from cache
        assert len(result) == 1

    async def test_get_latest_forecasts_with_filters_generates_unique_cache_key(
        self, service, mock_redis, mock_repository
    ):
        """Test that different filters generate unique cache keys."""
        mock_repository.get_latest_forecasts.return_value = []

        # Call with different filters
        await service.get_latest_forecasts(symbol="CrudeOIL", horizon=None)
        cache_key_1 = mock_redis.set.call_args[0][0]

        await service.get_latest_forecasts(symbol="GOLD", horizon=None)
        cache_key_2 = mock_redis.set.call_args[0][0]

        await service.get_latest_forecasts(symbol="CrudeOIL", horizon="1h")
        cache_key_3 = mock_redis.set.call_args[0][0]

        # All cache keys should be different
        assert cache_key_1 != cache_key_2
        assert cache_key_1 != cache_key_3
        assert cache_key_2 != cache_key_3

    async def test_get_forecasts_by_symbol_cache_miss(
        self, service, mock_repository, mock_redis
    ):
        """Test symbol-specific forecast retrieval with cache miss."""
        now = datetime.now(timezone.utc)
        mock_forecasts = [
            Forecast(
                id=1,
                symbol="CrudeOIL",
                timeframe="H1",
                horizon="1h",
                predicted_price=Decimal("85.42"),
                confidence=Decimal("0.87"),
                model_name="XGBoost_v1",
                created_at=now,
                forecast_time=now + timedelta(hours=1),
            )
        ]

        # Mock cache miss
        mock_redis.get.return_value = None

        # Mock repository response
        mock_repository.get_forecasts_by_symbol.return_value = (
            mock_forecasts,
            None,  # next_cursor
        )

        # Call service method
        result, next_cursor = await service.get_forecasts_by_symbol(
            symbol="CrudeOIL", cursor=None
        )

        # Verify repository was called
        mock_repository.get_forecasts_by_symbol.assert_called_once_with(
            symbol="CrudeOIL", cursor=None, limit=50
        )

        # Verify cache was written
        mock_redis.set.assert_called_once()

        assert len(result) == 1
        assert next_cursor is None

    async def test_cache_invalidation_on_forecast_generation(
        self, service, mock_redis
    ):
        """Test that cache is invalidated when new forecasts are generated."""
        # Simulate forecast generation event
        await service.invalidate_forecast_cache(symbol="CrudeOIL")

        # Verify cache deletion was called with pattern
        mock_redis.delete.assert_called()
        # Pattern should include the symbol
        call_args = str(mock_redis.delete.call_args)
        assert "CrudeOIL" in call_args or "forecasts:" in call_args


@pytest.mark.asyncio
class TestForecastServiceBusinessLogic:
    """Unit tests for ForecastService business logic."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock ForecastRepository."""
        repository = Mock()
        repository.get_latest_forecasts = AsyncMock()
        repository.get_forecasts_by_symbol = AsyncMock()
        return repository

    @pytest.fixture
    def service(self, mock_repository):
        """Create ForecastService with mocked repository (no Redis for logic tests)."""
        # Create a mock Redis that always misses cache
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        return ForecastService(repository=mock_repository, redis=mock_redis)

    async def test_get_latest_forecasts_passes_filters_to_repository(
        self, service, mock_repository
    ):
        """Test that service passes filters correctly to repository."""
        mock_repository.get_latest_forecasts.return_value = []

        await service.get_latest_forecasts(symbol="CrudeOIL", horizon="1h")

        # Verify repository was called with correct filters
        mock_repository.get_latest_forecasts.assert_called_once_with(
            symbol_filter="CrudeOIL", horizon_filter="1h"
        )

    async def test_get_forecasts_by_symbol_pagination(
        self, service, mock_repository
    ):
        """Test pagination logic for symbol forecasts."""
        mock_repository.get_forecasts_by_symbol.return_value = ([], "next_cursor_value")

        result, next_cursor = await service.get_forecasts_by_symbol(
            symbol="CrudeOIL", cursor="current_cursor", limit=25
        )

        # Verify repository was called with cursor and limit
        mock_repository.get_forecasts_by_symbol.assert_called_once_with(
            symbol="CrudeOIL", cursor="current_cursor", limit=25
        )

        assert next_cursor == "next_cursor_value"

    async def test_get_latest_forecasts_empty_result(
        self, service, mock_repository
    ):
        """Test handling of empty forecast results."""
        mock_repository.get_latest_forecasts.return_value = []

        result = await service.get_latest_forecasts(symbol="NONEXISTENT", horizon=None)

        assert result == []
        assert isinstance(result, list)
