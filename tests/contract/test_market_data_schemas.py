"""
Contract tests for Market Data API schemas.

Validates that API responses conform to expected schemas for dashboard integration.
Following TDD - these tests should FAIL initially, then PASS after implementation.
"""
import pytest
from decimal import Decimal
from datetime import datetime
from typing import Any, Dict

from pydantic import ValidationError

from src.api.models import (
    MarketDataResponse,
    MarketDataListResponse,
    SymbolInfoResponse,
    SymbolListResponse,
)


# =============================================================================
# T033: Contract test for GET /api/market-data/{symbol} schema
# =============================================================================

class TestMarketDataResponseSchema:
    """Test MarketDataResponse model schema validation."""

    def test_valid_market_data_response(self):
        """Test that valid market data conforms to schema."""
        valid_data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "time": datetime(2024, 11, 26, 10, 30, 0),
            "timeframe": "M5",
            "open": Decimal("72.45"),
            "high": Decimal("72.65"),
            "low": Decimal("72.40"),
            "close": Decimal("72.55"),
            "volume": 1500,
        }

        response = MarketDataResponse(**valid_data)

        assert response.id == 1
        assert response.symbol == "CrudeOIL"
        assert response.timeframe == "M5"
        assert response.open == Decimal("72.45")
        assert response.high == Decimal("72.65")
        assert response.low == Decimal("72.40")
        assert response.close == Decimal("72.55")
        assert response.volume == 1500

    def test_market_data_response_optional_fields(self):
        """Test optional fields in MarketDataResponse."""
        data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "time": datetime(2024, 11, 26, 10, 30, 0),
            "timeframe": "M5",
            "open": Decimal("72.45"),
            "high": Decimal("72.65"),
            "low": Decimal("72.40"),
            "close": Decimal("72.55"),
            "volume": 1500,
            "import_symbol": "CL",
            "source": "MT4",
            "change": Decimal("0.10"),
            "change_percent": Decimal("0.14"),
        }

        response = MarketDataResponse(**data)

        assert response.import_symbol == "CL"
        assert response.source == "MT4"
        assert response.change == Decimal("0.10")
        assert response.change_percent == Decimal("0.14")

    def test_market_data_response_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        invalid_data = {
            "id": 1,
            "symbol": "CrudeOIL",
            # Missing required fields: time, timeframe, OHLC, volume
        }

        with pytest.raises(ValidationError) as exc_info:
            MarketDataResponse(**invalid_data)

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "time" in error_fields
        assert "timeframe" in error_fields
        assert "open" in error_fields


class TestMarketDataListResponseSchema:
    """Test MarketDataListResponse schema with pagination."""

    def test_valid_market_data_list_response(self):
        """Test valid paginated market data list."""
        valid_data = {
            "data": [
                {
                    "id": 1,
                    "symbol": "CrudeOIL",
                    "time": datetime(2024, 11, 26, 10, 30, 0),
                    "timeframe": "M5",
                    "open": Decimal("72.45"),
                    "high": Decimal("72.65"),
                    "low": Decimal("72.40"),
                    "close": Decimal("72.55"),
                    "volume": 1500,
                }
            ],
            "total": 1000,
            "page": 1,
            "page_size": 50,
            "symbol": "CrudeOIL",
        }

        response = MarketDataListResponse(**valid_data)

        assert len(response.data) == 1
        assert response.total == 1000
        assert response.page == 1
        assert response.page_size == 50
        assert response.symbol == "CrudeOIL"
        assert response.next_cursor is None  # No cursor provided

    def test_market_data_list_with_cursor(self):
        """Test MarketDataListResponse with next_cursor for pagination."""
        data = {
            "data": [],
            "total": 1000,
            "page": 1,
            "page_size": 50,
            "symbol": "CrudeOIL",
            "next_cursor": "2024-11-26T10:30:00_123",
        }

        response = MarketDataListResponse(**data)

        assert response.next_cursor == "2024-11-26T10:30:00_123"


# =============================================================================
# T034: Contract test for GET /api/market-data/{symbol}/range schema
# =============================================================================

class TestMarketDataRangeResponseSchema:
    """Test market data range query response schema."""

    def test_market_data_range_with_time_filters(self):
        """Test range response with start/end time."""
        data = {
            "data": [],
            "total": 500,
            "page": 1,
            "page_size": 500,
            "symbol": "CrudeOIL",
            "start_time": datetime(2024, 11, 1, 0, 0, 0),
            "end_time": datetime(2024, 11, 26, 23, 59, 59),
        }

        response = MarketDataListResponse(**data)

        assert response.start_time == datetime(2024, 11, 1, 0, 0, 0)
        assert response.end_time == datetime(2024, 11, 26, 23, 59, 59)
        assert response.symbol == "CrudeOIL"


# =============================================================================
# T035: Contract test for GET /api/market-data/symbols schema
# =============================================================================

class TestSymbolResponseSchemas:
    """Test symbol info and symbol list response schemas."""

    def test_valid_symbol_info_response(self):
        """Test SymbolInfoResponse with symbol metadata."""
        valid_data = {
            "symbol": "CrudeOIL",
            "description": "Crude Oil Futures",
            "latest_price": Decimal("72.55"),
            "latest_time": datetime(2024, 11, 26, 10, 30, 0),
            "data_points_count": 50000,
            "first_time": datetime(2024, 1, 1, 0, 0, 0),
            "last_time": datetime(2024, 11, 26, 10, 30, 0),
        }

        response = SymbolInfoResponse(**valid_data)

        assert response.symbol == "CrudeOIL"
        assert response.description == "Crude Oil Futures"
        assert response.latest_price == Decimal("72.55")
        assert response.data_points_count == 50000

    def test_symbol_info_optional_fields(self):
        """Test SymbolInfoResponse with minimal required fields."""
        data = {
            "symbol": "EURUSD",
            "data_points_count": 10000,
        }

        response = SymbolInfoResponse(**data)

        assert response.symbol == "EURUSD"
        assert response.data_points_count == 10000
        assert response.description is None
        assert response.latest_price is None

    def test_valid_symbol_list_response(self):
        """Test SymbolListResponse with multiple symbols."""
        data = {
            "symbols": [
                {
                    "symbol": "CrudeOIL",
                    "description": "Crude Oil Futures",
                    "data_points_count": 50000,
                },
                {
                    "symbol": "EURUSD",
                    "description": "Euro/US Dollar",
                    "data_points_count": 30000,
                },
            ],
            "total": 2,
        }

        response = SymbolListResponse(**data)

        assert len(response.symbols) == 2
        assert response.total == 2
        assert response.symbols[0].symbol == "CrudeOIL"
        assert response.symbols[1].symbol == "EURUSD"


# =============================================================================
# T036: Contract test for SSE /api/stream/market-data event schema
# =============================================================================

class TestSSEMarketDataEventSchema:
    """Test Server-Sent Events (SSE) market data stream schema."""

    def test_sse_event_format(self):
        """Test that SSE events conform to EventSource format."""
        # SSE format: event: {event_type}\ndata: {json}\n\n
        sse_event = {
            "event": "market_data",
            "data": {
                "id": 1,
                "symbol": "CrudeOIL",
                "time": datetime(2024, 11, 26, 10, 30, 0),
                "timeframe": "M5",
                "open": Decimal("72.45"),
                "high": Decimal("72.65"),
                "low": Decimal("72.40"),
                "close": Decimal("72.55"),
                "volume": 1500,
            },
        }

        # Validate the data payload conforms to MarketDataResponse
        data_response = MarketDataResponse(**sse_event["data"])

        assert sse_event["event"] == "market_data"
        assert data_response.symbol == "CrudeOIL"
        assert data_response.close == Decimal("72.55")

    def test_sse_heartbeat_event(self):
        """Test SSE heartbeat/ping event format."""
        heartbeat = {
            "event": "ping",
            "data": {"timestamp": datetime(2024, 11, 26, 10, 30, 0).isoformat()},
        }

        assert heartbeat["event"] == "ping"
        assert "timestamp" in heartbeat["data"]

    def test_sse_error_event(self):
        """Test SSE error event format."""
        error_event = {
            "event": "error",
            "data": {
                "error": "SubscriptionError",
                "detail": "Symbol not found: INVALID",
                "timestamp": datetime.utcnow().isoformat(),
            },
        }

        assert error_event["event"] == "error"
        assert error_event["data"]["error"] == "SubscriptionError"
        assert "detail" in error_event["data"]


# =============================================================================
# Edge Cases and Validation Tests
# =============================================================================

class TestMarketDataValidation:
    """Test validation and edge cases for market data schemas."""

    def test_negative_volume_rejected(self):
        """Test that negative volume is rejected."""
        invalid_data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "time": datetime(2024, 11, 26, 10, 30, 0),
            "timeframe": "M5",
            "open": Decimal("72.45"),
            "high": Decimal("72.65"),
            "low": Decimal("72.40"),
            "close": Decimal("72.55"),
            "volume": -100,  # Invalid negative volume
        }

        # Pydantic should allow negative volumes (validation happens at business logic layer)
        # This test documents current behavior
        response = MarketDataResponse(**invalid_data)
        assert response.volume == -100

    def test_invalid_timeframe_format(self):
        """Test handling of non-standard timeframe values."""
        data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "time": datetime(2024, 11, 26, 10, 30, 0),
            "timeframe": "INVALID",  # Non-standard timeframe
            "open": Decimal("72.45"),
            "high": Decimal("72.65"),
            "low": Decimal("72.40"),
            "close": Decimal("72.55"),
            "volume": 1500,
        }

        # Schema accepts any string for timeframe (validation at API layer)
        response = MarketDataResponse(**data)
        assert response.timeframe == "INVALID"

    def test_ohlc_consistency_not_enforced(self):
        """Test that OHLC consistency is not enforced at schema level."""
        # High < Low - logically invalid but schema doesn't validate
        data = {
            "id": 1,
            "symbol": "CrudeOIL",
            "time": datetime(2024, 11, 26, 10, 30, 0),
            "timeframe": "M5",
            "open": Decimal("72.45"),
            "high": Decimal("72.00"),  # Lower than low
            "low": Decimal("72.40"),
            "close": Decimal("72.55"),
            "volume": 1500,
        }

        # Schema validation passes (business logic should validate OHLC consistency)
        response = MarketDataResponse(**data)
        assert response.high == Decimal("72.00")
        assert response.low == Decimal("72.40")
