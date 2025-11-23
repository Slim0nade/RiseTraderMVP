"""
Contract tests for MT4 message schemas.

Validates that Pydantic models match the expected JSON schemas for MT4 communication.
"""
import pytest
import json
from decimal import Decimal
from datetime import datetime
import uuid

from pydantic import ValidationError

from src.trading.execution.mt4_models import (
    CreateInstantOrderCommand,
    GetAccountInfoCommand,
    GetOpenPositionsCommand,
    ClosePositionCommand,
    OrderResponse,
    AccountInfoResponse,
    PositionsResponse,
    OrderConfirmedEvent,
    OrderConfirmedData,
    OrderRejectedEvent,
    OrderRejectedData,
    PositionUpdatedEvent,
    PositionUpdatedData,
    PositionClosedEvent,
    PositionClosedData,
    MarketTickEvent,
    MarketTickData,
)


# =============================================================================
# Command Schema Tests
# =============================================================================

def test_create_instant_order_command_schema():
    """Test CreateInstantOrderCommand schema matches contract."""
    # Arrange
    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001,
        stop_loss=Decimal("74.00"),
        take_profit=Decimal("77.00"),
        comment="Test order"
    )

    # Act
    json_data = command.model_dump(mode='json')

    # Assert - Validate schema structure
    assert json_data["command"] == "create_instant_order"
    assert json_data["symbol"] == "CrudeOIL"
    assert json_data["direction"] == "BUY"
    assert json_data["volume"] == 0.1
    assert json_data["magic_number"] == 100001
    assert json_data["stop_loss"] == 74.00
    assert json_data["take_profit"] == 77.00
    assert json_data["comment"] == "Test order"
    assert "correlation_id" in json_data
    assert isinstance(json_data["correlation_id"], str)


def test_create_instant_order_without_sl_tp():
    """Test CreateInstantOrderCommand with optional fields omitted."""
    # Arrange & Act
    command = CreateInstantOrderCommand(
        symbol="EURUSD",
        direction="SELL",
        volume=Decimal("1.0"),
        magic_number=100001
    )

    json_data = command.model_dump(mode='json')

    # Assert
    assert json_data["stop_loss"] is None
    assert json_data["take_profit"] is None
    assert json_data["comment"] is None


def test_create_instant_order_invalid_direction():
    """Test that invalid direction raises validation error."""
    # Act & Assert
    with pytest.raises(ValidationError) as exc_info:
        CreateInstantOrderCommand(
            symbol="CrudeOIL",
            direction="HOLD",  # Invalid
            volume=Decimal("0.1"),
            magic_number=100001
        )

    assert "direction" in str(exc_info.value)


def test_create_instant_order_negative_volume():
    """Test that negative volume raises validation error."""
    # Act & Assert
    with pytest.raises(ValidationError) as exc_info:
        CreateInstantOrderCommand(
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("-0.1"),  # Negative
            magic_number=100001
        )

    assert "volume" in str(exc_info.value).lower()


def test_get_account_info_command_schema():
    """Test GetAccountInfoCommand schema."""
    # Arrange & Act
    command = GetAccountInfoCommand(magic_number=100001)
    json_data = command.model_dump(mode='json')

    # Assert
    assert json_data["command"] == "get_account_info"
    assert json_data["magic_number"] == 100001
    assert "correlation_id" in json_data


def test_get_open_positions_command_schema():
    """Test GetOpenPositionsCommand schema."""
    # Arrange & Act
    command = GetOpenPositionsCommand(magic_number=100001)
    json_data = command.model_dump(mode='json')

    # Assert
    assert json_data["command"] == "get_open_positions"
    assert json_data["magic_number"] == 100001


def test_close_position_command_schema():
    """Test ClosePositionCommand schema."""
    # Arrange & Act
    command = ClosePositionCommand(
        ticket_number=12345,
        magic_number=100001
    )
    json_data = command.model_dump(mode='json')

    # Assert
    assert json_data["command"] == "close_position"
    assert json_data["ticket_number"] == 12345
    assert json_data["magic_number"] == 100001


# =============================================================================
# Response Schema Tests
# =============================================================================

def test_order_response_success_schema():
    """Test OrderResponse success schema."""
    # Arrange
    response_json = {
        "success": True,
        "ticket_number": 12345,
        "execution_price": 75.50,
        "execution_time": "2025-11-22T10:30:00Z",
        "correlation_id": str(uuid.uuid4())
    }

    # Act
    response = OrderResponse(**response_json)

    # Assert
    assert response.success is True
    assert response.ticket_number == 12345
    assert response.execution_price == Decimal("75.50")
    assert isinstance(response.execution_time, datetime)
    assert response.error_code is None
    assert response.error_message is None


def test_order_response_failure_schema():
    """Test OrderResponse failure schema."""
    # Arrange
    response_json = {
        "success": False,
        "error_code": 134,
        "error_message": "Not enough margin",
        "correlation_id": str(uuid.uuid4())
    }

    # Act
    response = OrderResponse(**response_json)

    # Assert
    assert response.success is False
    assert response.error_code == 134
    assert response.error_message == "Not enough margin"
    assert response.ticket_number is None
    assert response.execution_price is None


def test_account_info_response_schema():
    """Test AccountInfoResponse schema."""
    # Arrange
    response_json = {
        "success": True,
        "balance": 10000.00,
        "equity": 10250.50,
        "margin": 500.00,
        "free_margin": 9750.50,
        "margin_level": 2050.10,
        "account_number": "12345678",
        "leverage": 100
    }

    # Act
    response = AccountInfoResponse(**response_json)

    # Assert
    assert response.success is True
    assert response.balance == Decimal("10000.00")
    assert response.equity == Decimal("10250.50")
    assert response.margin == Decimal("500.00")
    assert response.free_margin == Decimal("9750.50")
    assert response.margin_level == Decimal("2050.10")
    assert response.account_number == "12345678"
    assert response.leverage == 100


def test_positions_response_schema():
    """Test PositionsResponse schema."""
    # Arrange
    response_json = {
        "success": True,
        "positions": [
            {
                "ticket_number": 12345,
                "symbol": "CrudeOIL",
                "direction": "BUY",
                "volume": 0.1,
                "open_price": 75.00,
                "current_price": 75.50,
                "unrealized_pnl": 50.00,
                "stop_loss": 74.00,
                "take_profit": 77.00,
                "open_time": "2025-11-22T10:00:00Z"
            }
        ],
        "count": 1
    }

    # Act
    response = PositionsResponse(**response_json)

    # Assert
    assert response.success is True
    assert len(response.positions) == 1
    assert response.count == 1

    position = response.positions[0]
    assert position.ticket_number == 12345
    assert position.symbol == "CrudeOIL"
    assert position.direction == "BUY"
    assert position.volume == Decimal("0.1")
    assert position.unrealized_pnl == Decimal("50.00")


# =============================================================================
# Event Schema Tests
# =============================================================================

def test_order_confirmed_event_schema():
    """Test OrderConfirmedEvent schema."""
    # Arrange
    correlation_id = str(uuid.uuid4())

    event = OrderConfirmedEvent(
        correlation_id=correlation_id,
        data=OrderConfirmedData(
            order_id=str(uuid.uuid4()),
            magic_number=100001,
            ticket_number=12345,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            execution_price=Decimal("75.50"),
            execution_time=datetime.utcnow()
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert json_data["event_type"] == "order_confirmed"
    assert json_data["version"] == "1.0.0"
    assert json_data["source"] == "mt4_integration_service"
    assert json_data["correlation_id"] == correlation_id
    assert "timestamp" in json_data

    data = json_data["data"]
    assert data["magic_number"] == 100001
    assert data["ticket_number"] == 12345
    assert data["symbol"] == "CrudeOIL"
    assert data["direction"] == "BUY"
    assert data["volume"] == 0.1
    assert data["execution_price"] == 75.50


def test_order_rejected_event_schema():
    """Test OrderRejectedEvent schema."""
    # Arrange
    event = OrderRejectedEvent(
        data=OrderRejectedData(
            order_id=str(uuid.uuid4()),
            magic_number=100001,
            symbol="CrudeOIL",
            error_code=134,
            error_message="Not enough margin"
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert json_data["event_type"] == "order_rejected"
    assert json_data["version"] == "1.0.0"

    data = json_data["data"]
    assert data["error_code"] == 134
    assert data["error_message"] == "Not enough margin"
    assert data["magic_number"] == 100001


def test_position_updated_event_schema():
    """Test PositionUpdatedEvent schema."""
    # Arrange
    event = PositionUpdatedEvent(
        data=PositionUpdatedData(
            magic_number=100001,
            ticket_number=12345,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.50"),
            unrealized_pnl=Decimal("50.00"),
            stop_loss=Decimal("74.00"),
            take_profit=Decimal("77.00")
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert json_data["event_type"] == "position_updated"

    data = json_data["data"]
    assert data["ticket_number"] == 12345
    assert data["current_price"] == 75.50
    assert data["unrealized_pnl"] == 50.00


def test_position_closed_event_schema():
    """Test PositionClosedEvent schema."""
    # Arrange
    event = PositionClosedEvent(
        data=PositionClosedData(
            magic_number=100001,
            ticket_number=12345,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            close_price=Decimal("75.50"),
            realized_pnl=Decimal("50.00"),
            open_time=datetime.utcnow() - timedelta(hours=1),
            close_time=datetime.utcnow(),
            close_reason="TAKE_PROFIT"
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert json_data["event_type"] == "position_closed"

    data = json_data["data"]
    assert data["ticket_number"] == 12345
    assert data["close_price"] == 75.50
    assert data["realized_pnl"] == 50.00
    assert data["close_reason"] == "TAKE_PROFIT"


def test_market_tick_event_schema():
    """Test MarketTickEvent schema."""
    # Arrange
    event = MarketTickEvent(
        data=MarketTickData(
            symbol="CrudeOIL",
            bid=Decimal("75.45"),
            ask=Decimal("75.55"),
            last=Decimal("75.50"),
            volume=1000,
            time=datetime.utcnow()
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert json_data["event_type"] == "market_tick"

    data = json_data["data"]
    assert data["symbol"] == "CrudeOIL"
    assert data["bid"] == 75.45
    assert data["ask"] == 75.55
    assert data["last"] == 75.50


# =============================================================================
# Correlation ID Preservation Tests
# =============================================================================

def test_correlation_id_preserved_in_command():
    """Test that correlation ID is preserved through command."""
    # Arrange
    custom_correlation_id = str(uuid.uuid4())

    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001,
        correlation_id=custom_correlation_id
    )

    # Act
    json_data = command.model_dump(mode='json')

    # Assert
    assert json_data["correlation_id"] == custom_correlation_id


def test_correlation_id_auto_generated():
    """Test that correlation ID is auto-generated if not provided."""
    # Arrange & Act
    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Assert
    assert command.correlation_id is not None
    assert len(command.correlation_id) == 36  # UUID format


def test_correlation_id_in_event():
    """Test that correlation ID is included in events."""
    # Arrange
    correlation_id = str(uuid.uuid4())

    event = OrderConfirmedEvent(
        correlation_id=correlation_id,
        data=OrderConfirmedData(
            order_id=str(uuid.uuid4()),
            magic_number=100001,
            ticket_number=12345,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            execution_price=Decimal("75.50"),
            execution_time=datetime.utcnow()
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert json_data["correlation_id"] == correlation_id


# =============================================================================
# JSON Serialization Tests
# =============================================================================

def test_command_json_serialization():
    """Test that commands can be serialized to JSON string."""
    # Arrange
    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Act
    json_str = json.dumps(command.model_dump(mode='json'))
    deserialized = json.loads(json_str)

    # Assert
    assert deserialized["command"] == "create_instant_order"
    assert deserialized["symbol"] == "CrudeOIL"


def test_event_json_serialization():
    """Test that events can be serialized to JSON string."""
    # Arrange
    event = OrderConfirmedEvent(
        data=OrderConfirmedData(
            order_id=str(uuid.uuid4()),
            magic_number=100001,
            ticket_number=12345,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            execution_price=Decimal("75.50"),
            execution_time=datetime.utcnow()
        )
    )

    # Act
    json_str = json.dumps(event.model_dump(mode='json'))
    deserialized = json.loads(json_str)

    # Assert
    assert deserialized["event_type"] == "order_confirmed"
    assert deserialized["data"]["ticket_number"] == 12345


# =============================================================================
# Backwards Compatibility Tests
# =============================================================================

def test_schema_version_included():
    """Test that all events include version field."""
    # Arrange
    events = [
        OrderConfirmedEvent(
            data=OrderConfirmedData(
                order_id=str(uuid.uuid4()),
                magic_number=100001,
                ticket_number=12345,
                symbol="CrudeOIL",
                direction="BUY",
                volume=Decimal("0.1"),
                execution_price=Decimal("75.50"),
                execution_time=datetime.utcnow()
            )
        ),
        OrderRejectedEvent(
            data=OrderRejectedData(
                order_id=str(uuid.uuid4()),
                magic_number=100001,
                symbol="CrudeOIL",
                error_code=134,
                error_message="Error"
            )
        ),
    ]

    # Act & Assert
    for event in events:
        json_data = event.model_dump(mode='json')
        assert "version" in json_data
        assert json_data["version"] == "1.0.0"


def test_source_field_included():
    """Test that all events include source field."""
    # Arrange
    event = OrderConfirmedEvent(
        data=OrderConfirmedData(
            order_id=str(uuid.uuid4()),
            magic_number=100001,
            ticket_number=12345,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            execution_price=Decimal("75.50"),
            execution_time=datetime.utcnow()
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert "source" in json_data
    assert json_data["source"] == "mt4_integration_service"
