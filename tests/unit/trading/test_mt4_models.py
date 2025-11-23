"""
Unit tests for MT4 models (Pydantic models for ZMQ messages).

Tests for T047 [US3]: Market tick parsing and validation.
"""
import pytest
from datetime import datetime
from decimal import Decimal
from pydantic import ValidationError

from src.trading.execution.mt4_models import (
    MarketTick,
    MarketTickEvent,
)


class TestMarketTick:
    """Test MarketTick model parsing and validation."""

    def test_market_tick_valid_data(self):
        """Test MarketTick with valid data."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            volume=1000
        )

        assert tick.symbol == "CrudeOIL"
        assert tick.bid == Decimal("75.123")
        assert tick.ask == Decimal("75.145")
        assert tick.timestamp == datetime(2024, 1, 15, 10, 30, 0)
        assert tick.volume == 1000

    def test_market_tick_without_volume(self):
        """Test MarketTick without optional volume field."""
        tick = MarketTick(
            symbol="EURUSD",
            bid=Decimal("1.08500"),
            ask=Decimal("1.08520"),
            timestamp=datetime.utcnow()
        )

        assert tick.symbol == "EURUSD"
        assert tick.volume is None

    def test_market_tick_spread_calculation(self):
        """Test spread calculation from bid/ask."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.100"),
            ask=Decimal("75.120"),
            timestamp=datetime.utcnow()
        )

        spread = tick.ask - tick.bid
        assert spread == Decimal("0.020")

    def test_market_tick_missing_required_field(self):
        """Test MarketTick fails with missing required field."""
        with pytest.raises(ValidationError) as exc_info:
            MarketTick(
                symbol="CrudeOIL",
                bid=Decimal("75.100"),
                # Missing ask
                timestamp=datetime.utcnow()
            )

        assert "ask" in str(exc_info.value)

    def test_market_tick_invalid_symbol_type(self):
        """Test MarketTick fails with invalid symbol type."""
        with pytest.raises(ValidationError):
            MarketTick(
                symbol=12345,  # Should be string
                bid=Decimal("75.100"),
                ask=Decimal("75.120"),
                timestamp=datetime.utcnow()
            )

    def test_market_tick_invalid_price_type(self):
        """Test MarketTick fails with invalid price type."""
        with pytest.raises(ValidationError):
            MarketTick(
                symbol="CrudeOIL",
                bid="not_a_number",  # Invalid
                ask=Decimal("75.120"),
                timestamp=datetime.utcnow()
            )

    def test_market_tick_negative_prices(self):
        """Test MarketTick allows negative prices (for some instruments)."""
        # Some instruments like interest rates can have negative prices
        tick = MarketTick(
            symbol="EURUSD",
            bid=Decimal("-0.005"),
            ask=Decimal("-0.003"),
            timestamp=datetime.utcnow()
        )

        assert tick.bid == Decimal("-0.005")
        assert tick.ask == Decimal("-0.003")

    def test_market_tick_high_precision_prices(self):
        """Test MarketTick handles high precision decimal prices."""
        tick = MarketTick(
            symbol="EURUSD",
            bid=Decimal("1.085001"),
            ask=Decimal("1.085021"),
            timestamp=datetime.utcnow()
        )

        assert tick.bid == Decimal("1.085001")
        assert tick.ask == Decimal("1.085021")

    def test_market_tick_serialization(self):
        """Test MarketTick serialization to dict."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=timestamp,
            volume=1000
        )

        data = tick.model_dump()

        assert data["symbol"] == "CrudeOIL"
        assert data["bid"] == Decimal("75.123")
        assert data["ask"] == Decimal("75.145")
        assert data["timestamp"] == timestamp
        assert data["volume"] == 1000

    def test_market_tick_json_serialization(self):
        """Test MarketTick JSON serialization."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            volume=1000
        )

        json_data = tick.model_dump(mode='json')

        assert json_data["symbol"] == "CrudeOIL"
        assert json_data["bid"] == "75.123"
        assert json_data["ask"] == "75.145"
        assert json_data["volume"] == 1000

    def test_market_tick_from_dict(self):
        """Test MarketTick creation from dictionary."""
        data = {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00",
            "volume": 1000
        }

        tick = MarketTick(**data)

        assert tick.symbol == "CrudeOIL"
        assert tick.bid == Decimal("75.123")
        assert tick.ask == Decimal("75.145")
        assert tick.volume == 1000


class TestMarketTickEvent:
    """Test MarketTickEvent model parsing and validation."""

    def test_market_tick_event_valid_data(self):
        """Test MarketTickEvent with valid data."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            volume=1000
        )

        event = MarketTickEvent(
            event_type="market_tick",
            correlation_id="tick_123",
            data=tick
        )

        assert event.event_type == "market_tick"
        assert event.correlation_id == "tick_123"
        assert event.data.symbol == "CrudeOIL"
        assert event.data.bid == Decimal("75.123")

    def test_market_tick_event_auto_correlation_id(self):
        """Test MarketTickEvent generates correlation_id if not provided."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime.utcnow()
        )

        event = MarketTickEvent(data=tick)

        assert event.event_type == "market_tick"
        assert event.correlation_id is not None
        assert len(event.correlation_id) > 0

    def test_market_tick_event_invalid_event_type(self):
        """Test MarketTickEvent fails with wrong event_type."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime.utcnow()
        )

        with pytest.raises(ValidationError):
            MarketTickEvent(
                event_type="wrong_type",  # Should be "market_tick"
                data=tick
            )

    def test_market_tick_event_missing_data(self):
        """Test MarketTickEvent fails without data field."""
        with pytest.raises(ValidationError) as exc_info:
            MarketTickEvent(event_type="market_tick")

        assert "data" in str(exc_info.value)

    def test_market_tick_event_serialization(self):
        """Test MarketTickEvent full serialization."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=timestamp,
            volume=1000
        )

        event = MarketTickEvent(
            correlation_id="tick_123",
            data=tick
        )

        data = event.model_dump()

        assert data["event_type"] == "market_tick"
        assert data["correlation_id"] == "tick_123"
        assert data["data"]["symbol"] == "CrudeOIL"
        assert data["data"]["bid"] == Decimal("75.123")

    def test_market_tick_event_json_serialization(self):
        """Test MarketTickEvent JSON serialization for ZMQ."""
        tick = MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            volume=1000
        )

        event = MarketTickEvent(
            correlation_id="tick_123",
            data=tick
        )

        json_str = event.model_dump_json()

        assert isinstance(json_str, str)
        assert "market_tick" in json_str
        assert "CrudeOIL" in json_str
        assert "75.123" in json_str

    def test_market_tick_event_from_zmq_message(self):
        """Test parsing MarketTickEvent from simulated ZMQ message."""
        zmq_message = {
            "event_type": "market_tick",
            "correlation_id": "tick_456",
            "data": {
                "symbol": "EURUSD",
                "bid": "1.08500",
                "ask": "1.08520",
                "timestamp": "2024-01-15T10:30:00",
                "volume": 500
            }
        }

        event = MarketTickEvent(**zmq_message)

        assert event.event_type == "market_tick"
        assert event.correlation_id == "tick_456"
        assert event.data.symbol == "EURUSD"
        assert event.data.bid == Decimal("1.08500")
        assert event.data.ask == Decimal("1.08520")
        assert event.data.volume == 500
