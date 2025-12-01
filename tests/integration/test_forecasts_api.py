"""
Integration tests for forecasts API endpoints.

These tests verify the complete flow from API request through service layer
to database for forecast-related operations.

Coverage:
- GET /api/forecasts/latest - Latest forecasts with filters
- GET /api/forecasts/{symbol} - Symbol-specific forecasts with pagination
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.forecasts import Forecast


@pytest.mark.asyncio
class TestForecastsAPIIntegration:
    """Integration tests for forecasts API endpoints."""

    @pytest.fixture(autouse=True)
    async def setup_forecast_data(self, async_session: AsyncSession):
        """Create test forecast data before each test."""
        now = datetime.now(timezone.utc)

        # Create multiple forecasts for different symbols and horizons
        forecasts = [
            Forecast(
                symbol="CrudeOIL",
                timeframe="H1",
                horizon="1h",
                predicted_price=Decimal("85.42"),
                confidence=Decimal("0.87"),
                model_name="XGBoost_v1",
                created_at=now - timedelta(hours=1),
                forecast_time=now,
            ),
            Forecast(
                symbol="CrudeOIL",
                timeframe="H4",
                horizon="4h",
                predicted_price=Decimal("86.15"),
                confidence=Decimal("0.82"),
                model_name="XGBoost_v1",
                created_at=now - timedelta(hours=1),
                forecast_time=now + timedelta(hours=3),
            ),
            Forecast(
                symbol="CrudeOIL",
                timeframe="D1",
                horizon="24h",
                predicted_price=Decimal("87.50"),
                confidence=Decimal("0.75"),
                model_name="TFT_v1",
                created_at=now - timedelta(hours=1),
                forecast_time=now + timedelta(hours=23),
            ),
            Forecast(
                symbol="GOLD",
                timeframe="H1",
                horizon="1h",
                predicted_price=Decimal("2050.80"),
                confidence=Decimal("0.90"),
                model_name="XGBoost_v1",
                created_at=now - timedelta(hours=1),
                forecast_time=now,
            ),
            Forecast(
                symbol="EUR_USD",
                timeframe="H1",
                horizon="1h",
                predicted_price=Decimal("1.0825"),
                confidence=Decimal("0.85"),
                model_name="LSTM_v1",
                created_at=now - timedelta(hours=2),
                forecast_time=now - timedelta(hours=1),  # Older forecast
            ),
        ]

        async_session.add_all(forecasts)
        await async_session.commit()

        self.forecast_count = len(forecasts)

        yield

        # Cleanup
        for forecast in forecasts:
            await async_session.delete(forecast)
        await async_session.commit()

    async def test_get_latest_forecasts_all(self, async_client: AsyncClient):
        """Test retrieving all latest forecasts without filters."""
        response = await async_client.get("/api/forecasts/latest")

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "total" in data
        assert isinstance(data["data"], list)
        assert data["total"] >= 3  # At least 3 different symbols

        # Verify response structure
        if data["data"]:
            forecast = data["data"][0]
            assert "id" in forecast
            assert "symbol" in forecast
            assert "timeframe" in forecast
            assert "horizon" in forecast
            assert "predicted_price" in forecast
            assert "confidence" in forecast
            assert "model_name" in forecast
            assert "created_at" in forecast
            assert "forecast_time" in forecast

    async def test_get_latest_forecasts_symbol_filter(self, async_client: AsyncClient):
        """Test retrieving latest forecasts filtered by symbol."""
        response = await async_client.get("/api/forecasts/latest?symbol=CrudeOIL")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 1
        # All returned forecasts should be for CrudeOIL
        for forecast in data["data"]:
            assert forecast["symbol"] == "CrudeOIL"

    async def test_get_latest_forecasts_horizon_filter(self, async_client: AsyncClient):
        """Test retrieving latest forecasts filtered by horizon."""
        response = await async_client.get("/api/forecasts/latest?horizon=1h")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 2  # At least CrudeOIL and GOLD
        # All returned forecasts should have 1h horizon
        for forecast in data["data"]:
            assert forecast["horizon"] == "1h"

    async def test_get_latest_forecasts_combined_filters(self, async_client: AsyncClient):
        """Test retrieving latest forecasts with both symbol and horizon filters."""
        response = await async_client.get(
            "/api/forecasts/latest?symbol=CrudeOIL&horizon=4h"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 1
        for forecast in data["data"]:
            assert forecast["symbol"] == "CrudeOIL"
            assert forecast["horizon"] == "4h"

    async def test_get_forecasts_by_symbol(self, async_client: AsyncClient):
        """Test retrieving forecasts for a specific symbol."""
        response = await async_client.get("/api/forecasts/CrudeOIL")

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] >= 3  # CrudeOIL has 3 forecasts

        # All forecasts should be for CrudeOIL
        for forecast in data["data"]:
            assert forecast["symbol"] == "CrudeOIL"

    async def test_get_forecasts_by_symbol_pagination(self, async_client: AsyncClient):
        """Test pagination for symbol forecasts."""
        # Get first page
        response = await async_client.get("/api/forecasts/CrudeOIL?page_size=2")

        assert response.status_code == 200
        data = response.json()

        assert data["page_size"] == 2
        assert len(data["data"]) <= 2

        if data["next_cursor"]:
            # Get next page using cursor
            response2 = await async_client.get(
                f"/api/forecasts/CrudeOIL?cursor={data['next_cursor']}"
            )

            assert response2.status_code == 200
            data2 = response2.json()

            # Second page should have different forecasts
            first_page_ids = {f["id"] for f in data["data"]}
            second_page_ids = {f["id"] for f in data2["data"]}
            assert first_page_ids.isdisjoint(second_page_ids)

    async def test_get_forecasts_nonexistent_symbol(self, async_client: AsyncClient):
        """Test retrieving forecasts for a symbol with no forecasts."""
        response = await async_client.get("/api/forecasts/NONEXISTENT")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert len(data["data"]) == 0

    async def test_forecasts_response_data_types(self, async_client: AsyncClient):
        """Test that forecast response fields have correct data types."""
        response = await async_client.get("/api/forecasts/latest")

        assert response.status_code == 200
        data = response.json()

        if data["data"]:
            forecast = data["data"][0]

            # Numeric fields should be strings (Decimal serialization)
            assert isinstance(forecast["predicted_price"], str)
            assert isinstance(forecast["confidence"], str)

            # Confidence should be between 0 and 1
            confidence = Decimal(forecast["confidence"])
            assert Decimal("0") <= confidence <= Decimal("1")

            # Predicted price should be positive
            predicted_price = Decimal(forecast["predicted_price"])
            assert predicted_price > Decimal("0")

    async def test_forecasts_caching_behavior(self, async_client: AsyncClient):
        """Test that forecasts are properly cached."""
        # First request
        response1 = await async_client.get("/api/forecasts/latest")
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request should return same data (from cache)
        response2 = await async_client.get("/api/forecasts/latest")
        assert response2.status_code == 200
        data2 = response2.json()

        assert data1 == data2

    async def test_forecasts_api_error_handling(self, async_client: AsyncClient):
        """Test error handling for invalid requests."""
        # Invalid page size
        response = await async_client.get("/api/forecasts/CrudeOIL?page_size=-1")
        assert response.status_code == 422  # Validation error

        # Invalid cursor format
        response = await async_client.get("/api/forecasts/CrudeOIL?cursor=invalid")
        assert response.status_code in [400, 422]
