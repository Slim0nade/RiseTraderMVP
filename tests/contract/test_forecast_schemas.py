"""
Contract tests for forecast API schemas.

These tests verify that API responses conform to expected schemas
for forecast-related endpoints. They validate structure, field types,
and required fields without testing business logic.

Coverage:
- GET /api/forecasts/latest - Latest forecasts across symbols
- GET /api/forecasts/{symbol} - Symbol-specific forecasts
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import ValidationError

from src.api.models.forecasts import (
    ForecastResponse,
    ForecastListResponse,
)


class TestForecastResponseSchema:
    """Contract tests for ForecastResponse model."""

    def test_forecast_response_valid_data(self):
        """Test that valid forecast data passes validation."""
        data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "horizon": "1h",
            "predicted_price": Decimal("85.42"),
            "confidence": Decimal("0.87"),
            "model_name": "XGBoost_v1",
            "created_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "forecast_time": datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        }

        response = ForecastResponse(**data)

        assert response.id == 1
        assert response.symbol == "CrudeOIL"
        assert response.timeframe == "H1"
        assert response.horizon == "1h"
        assert response.predicted_price == Decimal("85.42")
        assert response.confidence == Decimal("0.87")
        assert response.model_name == "XGBoost_v1"
        assert response.created_at == data["created_at"]
        assert response.forecast_time == data["forecast_time"]

    def test_forecast_response_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        data = {
            "id": 1,
            "symbol": "CrudeOIL",
            # Missing required fields
        }

        with pytest.raises(ValidationError) as exc_info:
            ForecastResponse(**data)

        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}

        assert "timeframe" in missing_fields
        assert "horizon" in missing_fields
        assert "predicted_price" in missing_fields

    def test_forecast_response_invalid_types(self):
        """Test that invalid field types raise ValidationError."""
        data = {
            "id": "not_an_int",  # Invalid type
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "horizon": "1h",
            "predicted_price": "not_a_decimal",  # Invalid type
            "confidence": Decimal("0.87"),
            "model_name": "XGBoost_v1",
            "created_at": "not_a_datetime",  # Invalid type
            "forecast_time": datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        }

        with pytest.raises(ValidationError):
            ForecastResponse(**data)

    def test_forecast_response_from_orm(self):
        """Test that from_attributes=True allows ORM model conversion."""
        # Simulate ORM model with attributes
        class MockForecastModel:
            id = 1
            symbol = "CrudeOIL"
            timeframe = "H1"
            horizon = "1h"
            predicted_price = Decimal("85.42")
            confidence = Decimal("0.87")
            model_name = "XGBoost_v1"
            created_at = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
            forecast_time = datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc)

        mock_model = MockForecastModel()
        response = ForecastResponse.model_validate(mock_model)

        assert response.id == 1
        assert response.symbol == "CrudeOIL"
        assert response.predicted_price == Decimal("85.42")


class TestForecastListResponseSchema:
    """Contract tests for ForecastListResponse model."""

    def test_forecast_list_response_valid_data(self):
        """Test that valid forecast list data passes validation."""
        forecast_data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "horizon": "1h",
            "predicted_price": Decimal("85.42"),
            "confidence": Decimal("0.87"),
            "model_name": "XGBoost_v1",
            "created_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "forecast_time": datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        }

        data = {
            "data": [forecast_data],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "next_cursor": None,
        }

        response = ForecastListResponse(**data)

        assert len(response.data) == 1
        assert response.total == 1
        assert response.page == 1
        assert response.page_size == 50
        assert response.next_cursor is None

    def test_forecast_list_response_with_pagination(self):
        """Test forecast list with pagination cursor."""
        data = {
            "data": [],
            "total": 100,
            "page": 1,
            "page_size": 50,
            "next_cursor": "2025-01-15T10:00:00Z",
        }

        response = ForecastListResponse(**data)

        assert response.total == 100
        assert response.next_cursor == "2025-01-15T10:00:00Z"

    def test_forecast_list_response_empty_list(self):
        """Test that empty forecast list is valid."""
        data = {
            "data": [],
            "total": 0,
            "page": 1,
            "page_size": 50,
            "next_cursor": None,
        }

        response = ForecastListResponse(**data)

        assert len(response.data) == 0
        assert response.total == 0
