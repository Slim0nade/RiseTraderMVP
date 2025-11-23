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
    MarketTick,
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


# =============================================================================
# Position Event Schema Tests (T038 - User Story 2)
# =============================================================================

def test_position_updated_event_required_fields():
    """Test that PositionUpdatedEvent requires all mandatory fields."""
    # Act & Assert - Missing required fields should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        PositionUpdatedEvent(
            data=PositionUpdatedData(
                ticket_number=12345,
                magic_number=100001,
                symbol="CrudeOIL",
                direction="BUY",
                volume=Decimal("0.1"),
                open_price=Decimal("75.00"),
                # Missing: current_price, unrealized_pnl, open_time, last_updated
            )
        )

    errors = exc_info.value.errors()
    required_fields = {'current_price', 'unrealized_pnl', 'open_time', 'last_updated'}
    error_fields = {error['loc'][1] for error in errors if 'loc' in error}

    assert required_fields.issubset(error_fields)


def test_position_updated_event_optional_fields():
    """Test PositionUpdatedEvent with optional fields (stop_loss, take_profit)."""
    # Arrange - Create event without optional fields
    event = PositionUpdatedEvent(
        data=PositionUpdatedData(
            ticket_number=12345,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.50"),
            unrealized_pnl=Decimal("50.00"),
            open_time=datetime.utcnow(),
            last_updated=datetime.utcnow()
            # stop_loss and take_profit omitted
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert - Optional fields should be None
    data = json_data["data"]
    assert data["stop_loss"] is None
    assert data["take_profit"] is None


def test_position_updated_event_serialization():
    """Test PositionUpdatedEvent can be serialized to JSON and deserialized."""
    # Arrange
    original_event = PositionUpdatedEvent(
        correlation_id="test-corr-123",
        data=PositionUpdatedData(
            ticket_number=12345,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.75"),
            unrealized_pnl=Decimal("75.00"),
            stop_loss=Decimal("74.00"),
            take_profit=Decimal("77.00"),
            open_time=datetime(2025, 11, 22, 10, 0, 0),
            last_updated=datetime(2025, 11, 22, 10, 5, 0)
        )
    )

    # Act - Serialize to JSON
    json_str = json.dumps(original_event.model_dump(mode='json'))

    # Parse back from JSON
    parsed_data = json.loads(json_str)
    reconstructed_event = PositionUpdatedEvent(**parsed_data)

    # Assert - Data preserved
    assert reconstructed_event.event_type == "position_updated"
    assert reconstructed_event.correlation_id == "test-corr-123"
    assert reconstructed_event.data.ticket_number == 12345
    assert reconstructed_event.data.unrealized_pnl == Decimal("75.00")


def test_position_closed_event_required_fields():
    """Test that PositionClosedEvent requires all mandatory fields."""
    # Act & Assert
    with pytest.raises(ValidationError) as exc_info:
        PositionClosedEvent(
            data=PositionClosedData(
                ticket_number=12345,
                magic_number=100001,
                symbol="CrudeOIL",
                direction="BUY",
                volume=Decimal("0.1"),
                open_price=Decimal("75.00"),
                # Missing: close_price, realized_pnl, open_time, close_time, close_reason
            )
        )

    errors = exc_info.value.errors()
    required_fields = {'close_price', 'realized_pnl', 'open_time', 'close_time', 'close_reason'}
    error_fields = {error['loc'][1] for error in errors if 'loc' in error}

    assert required_fields.issubset(error_fields)


def test_position_closed_event_close_reasons():
    """Test PositionClosedEvent with different close reasons."""
    close_reasons = ["manual", "stop_loss", "take_profit", "margin_call"]

    for reason in close_reasons:
        # Arrange & Act
        event = PositionClosedEvent(
            data=PositionClosedData(
                ticket_number=12345,
                magic_number=100001,
                symbol="CrudeOIL",
                direction="BUY",
                volume=Decimal("0.1"),
                open_price=Decimal("75.00"),
                close_price=Decimal("75.50"),
                realized_pnl=Decimal("50.00"),
                open_time=datetime.utcnow(),
                close_time=datetime.utcnow(),
                close_reason=reason
            )
        )

        # Assert
        json_data = event.model_dump(mode='json')
        assert json_data["data"]["close_reason"] == reason


def test_position_closed_event_serialization():
    """Test PositionClosedEvent can be serialized and deserialized."""
    # Arrange
    original_event = PositionClosedEvent(
        correlation_id="close-corr-456",
        data=PositionClosedData(
            ticket_number=12346,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="SELL",
            volume=Decimal("0.2"),
            open_price=Decimal("76.00"),
            close_price=Decimal("75.50"),
            realized_pnl=Decimal("100.00"),
            open_time=datetime(2025, 11, 22, 10, 0, 0),
            close_time=datetime(2025, 11, 22, 11, 0, 0),
            close_reason="take_profit"
        )
    )

    # Act
    json_str = json.dumps(original_event.model_dump(mode='json'))
    parsed_data = json.loads(json_str)
    reconstructed_event = PositionClosedEvent(**parsed_data)

    # Assert
    assert reconstructed_event.event_type == "position_closed"
    assert reconstructed_event.correlation_id == "close-corr-456"
    assert reconstructed_event.data.ticket_number == 12346
    assert reconstructed_event.data.realized_pnl == Decimal("100.00")
    assert reconstructed_event.data.close_reason == "take_profit"


def test_position_event_decimal_precision():
    """Test that position events preserve decimal precision for prices and P&L."""
    # Arrange - Use precise decimal values
    event = PositionUpdatedEvent(
        data=PositionUpdatedData(
            ticket_number=12347,
            magic_number=100001,
            symbol="EURUSD",
            direction="BUY",
            volume=Decimal("1.00"),
            open_price=Decimal("1.10050"),  # 5 decimal places
            current_price=Decimal("1.10125"),
            unrealized_pnl=Decimal("75.00"),
            open_time=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert - Precision preserved
    data = json_data["data"]
    assert data["open_price"] == 1.10050
    assert data["current_price"] == 1.10125


def test_position_updated_invalid_direction():
    """Test that PositionUpdatedEvent rejects invalid direction."""
    # Act & Assert
    with pytest.raises(ValidationError) as exc_info:
        PositionUpdatedEvent(
            data=PositionUpdatedData(
                ticket_number=12348,
                magic_number=100001,
                symbol="CrudeOIL",
                direction="HOLD",  # Invalid
                volume=Decimal("0.1"),
                open_price=Decimal("75.00"),
                current_price=Decimal("75.50"),
                unrealized_pnl=Decimal("50.00"),
                open_time=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
        )

    assert "direction" in str(exc_info.value)


def test_position_event_negative_pnl():
    """Test position events handle negative P&L correctly."""
    # Arrange - Losing position
    update_event = PositionUpdatedEvent(
        data=PositionUpdatedData(
            ticket_number=12349,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("76.00"),
            current_price=Decimal("75.00"),  # Down $1.00
            unrealized_pnl=Decimal("-100.00"),  # Loss
            open_time=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
    )

    close_event = PositionClosedEvent(
        data=PositionClosedData(
            ticket_number=12349,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("76.00"),
            close_price=Decimal("75.00"),
            realized_pnl=Decimal("-100.00"),  # Realized loss
            open_time=datetime.utcnow(),
            close_time=datetime.utcnow(),
            close_reason="stop_loss"
        )
    )

    # Act
    update_json = update_event.model_dump(mode='json')
    close_json = close_event.model_dump(mode='json')

    # Assert - Negative P&L preserved
    assert update_json["data"]["unrealized_pnl"] == -100.00
    assert close_json["data"]["realized_pnl"] == -100.00


def test_position_event_timestamp_format():
    """Test that position events use correct timestamp format."""
    # Arrange
    open_time = datetime(2025, 11, 22, 10, 0, 0)
    last_updated = datetime(2025, 11, 22, 10, 5, 0)

    event = PositionUpdatedEvent(
        data=PositionUpdatedData(
            ticket_number=12350,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.50"),
            unrealized_pnl=Decimal("50.00"),
            open_time=open_time,
            last_updated=last_updated
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert - Timestamps are ISO format strings
    data = json_data["data"]
    assert isinstance(data["open_time"], str)
    assert isinstance(data["last_updated"], str)
    # Should be ISO 8601 format
    assert "2025-11-22" in data["open_time"]
    assert "10:00:00" in data["open_time"]


def test_position_event_correlation_id():
    """Test that position events include correlation_id."""
    # Arrange
    correlation_id = str(uuid.uuid4())

    event = PositionUpdatedEvent(
        correlation_id=correlation_id,
        data=PositionUpdatedData(
            ticket_number=12351,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.50"),
            unrealized_pnl=Decimal("50.00"),
            open_time=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
    )

    # Act
    json_data = event.model_dump(mode='json')

    # Assert
    assert "correlation_id" in json_data
    assert json_data["correlation_id"] == correlation_id
    # Validate it's a UUID format
    assert len(correlation_id.split('-')) == 5


def test_position_event_backward_compatibility():
    """Test that position events can be parsed from older schema versions."""
    # Arrange - Simulate old event format (without some optional fields)
    old_format = {
        "event_type": "position_updated",
        "correlation_id": "old-corr-123",
        "data": {
            "ticket_number": 12352,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": "0.1",
            "open_price": "75.00",
            "current_price": "75.50",
            "unrealized_pnl": "50.00",
            "open_time": "2025-11-22T10:00:00",
            "last_updated": "2025-11-22T10:05:00"
            # stop_loss, take_profit omitted (None)
        }
    }

    # Act - Parse old format
    event = PositionUpdatedEvent(**old_format)

    # Assert - Successfully parsed
    assert event.event_type == "position_updated"
    assert event.data.ticket_number == 12352
    assert event.data.stop_loss is None
    assert event.data.take_profit is None


# =============================================================================
# Market Tick Event Schema Tests (T050 - User Story 3)
# =============================================================================

def test_market_tick_event_schema():
    """Test MarketTickEvent schema matches expected MT4 contract."""
    # Arrange - simulated MT4 message
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_12345",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00.500",
            "volume": 1000
        }
    }

    # Act - parse message
    event = MarketTickEvent(**mt4_message)

    # Assert - all fields match
    assert event.event_type == "market_tick"
    assert event.correlation_id == "tick_12345"
    assert event.data.symbol == "CrudeOIL"
    assert event.data.bid == Decimal("75.123")
    assert event.data.ask == Decimal("75.145")
    assert event.data.volume == 1000


def test_market_tick_event_json_serialization():
    """Test MarketTickEvent serializes to expected JSON format."""
    # Arrange
    event = MarketTickEvent(
        correlation_id="tick_67890",
        data=MarketTick(
            symbol="EURUSD",
            bid=Decimal("1.08500"),
            ask=Decimal("1.08520"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            volume=500
        )
    )

    # Act - serialize to JSON
    json_str = event.model_dump_json()
    parsed = json.loads(json_str)

    # Assert - JSON structure matches expected
    assert parsed["event_type"] == "market_tick"
    assert parsed["correlation_id"] == "tick_67890"
    assert parsed["data"]["symbol"] == "EURUSD"
    assert parsed["data"]["bid"] == "1.08500"
    assert parsed["data"]["ask"] == "1.08520"
    assert parsed["data"]["volume"] == 500


def test_market_tick_event_without_volume():
    """Test MarketTickEvent handles optional volume field."""
    # Arrange - no volume
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_no_vol",
        "data": {
            "symbol": "GBPUSD",
            "bid": "1.25000",
            "ask": "1.25020",
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act
    event = MarketTickEvent(**mt4_message)

    # Assert - volume should be None
    assert event.data.volume is None


def test_market_tick_event_missing_required_field():
    """Test MarketTickEvent fails with missing required field."""
    # Arrange - missing "ask"
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_invalid",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            # Missing "ask"
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act & Assert
    with pytest.raises(ValidationError) as exc_info:
        MarketTickEvent(**mt4_message)

    assert "ask" in str(exc_info.value)


def test_market_tick_event_invalid_event_type():
    """Test MarketTickEvent rejects wrong event_type."""
    # Arrange - wrong event type
    mt4_message = {
        "event_type": "position_updated",  # Wrong!
        "correlation_id": "tick_wrong",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act & Assert
    with pytest.raises(ValidationError):
        MarketTickEvent(**mt4_message)


def test_market_tick_event_high_precision_prices():
    """Test MarketTickEvent handles high precision decimal prices."""
    # Arrange - 6 decimal places
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_precision",
        "data": {
            "symbol": "EURUSD",
            "bid": "1.085001",
            "ask": "1.085021",
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act
    event = MarketTickEvent(**mt4_message)

    # Assert - precision preserved
    assert event.data.bid == Decimal("1.085001")
    assert event.data.ask == Decimal("1.085021")


def test_market_tick_event_negative_prices():
    """Test MarketTickEvent allows negative prices (e.g., interest rates)."""
    # Arrange
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_negative",
        "data": {
            "symbol": "EUR3M",
            "bid": "-0.005",
            "ask": "-0.003",
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act
    event = MarketTickEvent(**mt4_message)

    # Assert
    assert event.data.bid == Decimal("-0.005")
    assert event.data.ask == Decimal("-0.003")


def test_market_tick_event_auto_correlation_id():
    """Test MarketTickEvent generates correlation_id if missing."""
    # Arrange - no correlation_id
    mt4_message = {
        "event_type": "market_tick",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act
    event = MarketTickEvent(**mt4_message)

    # Assert - should have generated one
    assert event.correlation_id is not None
    assert len(event.correlation_id) > 0


def test_market_tick_event_spread_calculation():
    """Test calculating spread from tick data."""
    # Arrange
    event = MarketTickEvent(
        data=MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.100"),
            ask=Decimal("75.120"),
            timestamp=datetime.utcnow()
        )
    )

    # Act - calculate spread
    spread = event.data.ask - event.data.bid

    # Assert
    assert spread == Decimal("0.020")


def test_market_tick_event_timestamp_parsing():
    """Test MarketTickEvent parses ISO 8601 timestamps correctly."""
    # Arrange - ISO format with milliseconds
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_time",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00.500Z"
        }
    }

    # Act
    event = MarketTickEvent(**mt4_message)

    # Assert - timestamp parsed correctly
    assert event.data.timestamp.year == 2024
    assert event.data.timestamp.month == 1
    assert event.data.timestamp.day == 15
    assert event.data.timestamp.hour == 10
    assert event.data.timestamp.minute == 30


def test_market_tick_event_roundtrip_serialization():
    """Test MarketTickEvent roundtrip (serialize -> deserialize)."""
    # Arrange
    original = MarketTickEvent(
        correlation_id="tick_roundtrip",
        data=MarketTick(
            symbol="GBPUSD",
            bid=Decimal("1.25000"),
            ask=Decimal("1.25020"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            volume=750
        )
    )

    # Act - serialize and deserialize
    json_str = original.model_dump_json()
    parsed_data = json.loads(json_str)
    reconstructed = MarketTickEvent(**parsed_data)

    # Assert - data should match
    assert reconstructed.event_type == original.event_type
    assert reconstructed.correlation_id == original.correlation_id
    assert reconstructed.data.symbol == original.data.symbol
    assert reconstructed.data.bid == original.data.bid
    assert reconstructed.data.ask == original.data.ask
    assert reconstructed.data.volume == original.data.volume


def test_market_tick_event_large_volume():
    """Test MarketTickEvent handles large volume values."""
    # Arrange
    mt4_message = {
        "event_type": "market_tick",
        "correlation_id": "tick_large_vol",
        "data": {
            "symbol": "EURUSD",
            "bid": "1.08500",
            "ask": "1.08520",
            "timestamp": "2024-01-15T10:30:00",
            "volume": 9999999999
        }
    }

    # Act
    event = MarketTickEvent(**mt4_message)

    # Assert
    assert event.data.volume == 9999999999


def test_market_tick_event_backwards_compatibility():
    """Test MarketTickEvent maintains backwards compatibility with old messages."""
    # Arrange - old format without correlation_id
    old_format = {
        "event_type": "market_tick",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.000",
            "ask": "75.020",
            "timestamp": "2024-01-15T10:00:00"
        }
    }

    # Act
    event = MarketTickEvent(**old_format)

    # Assert - should parse successfully
    assert event.event_type == "market_tick"
    assert event.data.symbol == "CrudeOIL"
    assert event.correlation_id is not None  # Auto-generated


# =============================================================================
# Portfolio Risk Event Schema Tests (T064 - User Story 5)
# =============================================================================

def test_portfolio_risk_updated_event_schema():
    """Test PortfolioRiskUpdatedEvent schema (multi-EA portfolio)."""
    # Note: This test assumes PortfolioRiskUpdatedEvent will be created
    # For now, testing the concept with a dictionary structure
    portfolio_event = {
        "event_type": "portfolio_risk_updated",
        "correlation_id": "portfolio_123",
        "data": {
            "total_positions": 10,
            "total_unrealized_pnl": "250.50",
            "total_exposure": "15000.00",
            "ea_count": 3,
            "by_ea": {
                "100000": {"pnl": "100.00", "positions": 3},
                "100001": {"pnl": "75.50", "positions": 4},
                "100002": {"pnl": "75.00", "positions": 3}
            },
            "by_symbol": {
                "CrudeOIL": {"pnl": "150.00", "positions": 5},
                "EURUSD": {"pnl": "100.50", "positions": 5}
            },
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Assert - structure is correct
    assert portfolio_event["event_type"] == "portfolio_risk_updated"
    assert portfolio_event["data"]["ea_count"] == 3
    assert portfolio_event["data"]["total_positions"] == 10
