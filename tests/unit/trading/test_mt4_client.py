"""
Unit tests for MT4Client.

Tests ZMQ command sending, timeout handling, and encryption configuration.
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

import zmq

from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.mt4_models import (
    CreateInstantOrderCommand,
    OrderResponse,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_zmq_context():
    """Mock ZMQ context."""
    with patch('zmq.asyncio.Context') as mock_context:
        yield mock_context


@pytest.fixture
def mock_zmq_socket():
    """Mock ZMQ socket."""
    socket = AsyncMock()
    socket.poll = AsyncMock(return_value=zmq.POLLIN)
    socket.send_string = AsyncMock()
    socket.recv_string = AsyncMock()
    socket.close = AsyncMock()
    socket.setsockopt = Mock()
    return socket


@pytest.fixture
def mock_encryption_manager():
    """Mock encryption manager."""
    manager = Mock(spec=MT4EncryptionManager)
    manager.encryption_enabled = True
    manager.configure_socket = Mock(side_effect=lambda s: s)
    return manager


@pytest.fixture
def mt4_client(mock_encryption_manager):
    """Create MT4Client instance for testing."""
    client = MT4Client(
        host="localhost",
        rep_port=5555,
        pub_port=5556,
        magic_number=100001,
        encryption_manager=mock_encryption_manager,
        timeout_ms=5000
    )
    return client


# =============================================================================
# Connection Tests
# =============================================================================

@pytest.mark.asyncio
async def test_connect_success(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test successful connection to MT4."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    # Act
    await mt4_client.connect()

    # Assert
    assert mt4_client.is_connected() is True
    mock_zmq_socket.connect.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test disconnection from MT4."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    # Act
    await mt4_client.disconnect()

    # Assert
    assert mt4_client.is_connected() is False
    mock_zmq_socket.close.assert_called_once()


# =============================================================================
# send_command() Tests
# =============================================================================

@pytest.mark.asyncio
async def test_send_command_success(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test successful command sending and response."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    response_data = {
        "success": True,
        "ticket_number": 12345,
        "execution_price": 75.50,
        "execution_time": "2025-11-22T10:30:00Z",
        "correlation_id": command.correlation_id
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    response = await mt4_client.send_command(command)

    # Assert
    assert isinstance(response, dict)
    assert response["success"] is True
    assert response["ticket_number"] == 12345
    mock_zmq_socket.send_string.assert_called_once()
    mock_zmq_socket.recv_string.assert_called_once()


@pytest.mark.asyncio
async def test_send_command_timeout(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test command timeout handling."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    # Simulate timeout (poll returns 0)
    mock_zmq_socket.poll = AsyncMock(return_value=0)

    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Act & Assert
    with pytest.raises(TimeoutError, match="MT4 command timeout"):
        await mt4_client.send_command(command, timeout_ms=1000)


@pytest.mark.asyncio
async def test_send_command_connection_error(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test connection error handling."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    # Simulate connection error
    mock_zmq_socket.send_string.side_effect = zmq.ZMQError("Connection refused")

    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Act & Assert
    with pytest.raises(ConnectionError):
        await mt4_client.send_command(command)


@pytest.mark.asyncio
async def test_send_command_without_connection(mt4_client):
    """Test sending command without connection raises error."""
    # Arrange
    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Act & Assert
    with pytest.raises(ConnectionError, match="Not connected"):
        await mt4_client.send_command(command)


@pytest.mark.asyncio
async def test_send_command_correlation_id_preserved(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test correlation ID is preserved through request/response."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    original_correlation_id = command.correlation_id

    response_data = {
        "success": True,
        "ticket_number": 12345,
        "correlation_id": original_correlation_id
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    response = await mt4_client.send_command(command)

    # Assert
    assert response["correlation_id"] == original_correlation_id


# =============================================================================
# create_instant_order() Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_instant_order_success(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test successful instant order creation."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    response_data = {
        "success": True,
        "ticket_number": 12345,
        "execution_price": 75.50,
        "execution_time": "2025-11-22T10:30:00Z",
        "correlation_id": "test-uuid"
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    response = await mt4_client.create_instant_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1")
    )

    # Assert
    assert isinstance(response, OrderResponse)
    assert response.success is True
    assert response.ticket_number == 12345
    assert response.execution_price == Decimal("75.50")


@pytest.mark.asyncio
async def test_create_instant_order_with_sl_tp(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test order creation with stop loss and take profit."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    response_data = {
        "success": True,
        "ticket_number": 12345,
        "execution_price": 75.50,
        "execution_time": "2025-11-22T10:30:00Z",
        "correlation_id": "test-uuid"
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    response = await mt4_client.create_instant_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        stop_loss=Decimal("74.00"),
        take_profit=Decimal("77.00")
    )

    # Assert
    assert response.success is True
    # Verify SL/TP were sent in command
    sent_data = json.loads(mock_zmq_socket.send_string.call_args[0][0])
    assert sent_data["stop_loss"] == 74.00
    assert sent_data["take_profit"] == 77.00


@pytest.mark.asyncio
async def test_create_instant_order_rejection(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test order rejection from MT4."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    response_data = {
        "success": False,
        "error_code": 134,
        "error_message": "Not enough margin",
        "correlation_id": "test-uuid"
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    response = await mt4_client.create_instant_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("10.0")  # Large volume
    )

    # Assert
    assert response.success is False
    assert response.error_code == 134
    assert "margin" in response.error_message.lower()


# =============================================================================
# get_symbols() Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_symbols_success(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test fetching available symbols from MT4."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    response_data = {
        "success": True,
        "symbols": ["CrudeOIL", "EURUSD", "GBPUSD", "GOLD", "BTCUSD"],
        "count": 5
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    symbols = await mt4_client.get_symbols()

    # Assert
    assert isinstance(symbols, list)
    assert len(symbols) == 5
    assert "CrudeOIL" in symbols
    assert "EURUSD" in symbols


@pytest.mark.asyncio
async def test_get_symbols_empty_response(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test handling of empty symbol list."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    response_data = {
        "success": True,
        "symbols": [],
        "count": 0
    }

    mock_zmq_socket.recv_string.return_value = json.dumps(response_data)

    # Act
    symbols = await mt4_client.get_symbols()

    # Assert
    assert isinstance(symbols, list)
    assert len(symbols) == 0


# =============================================================================
# Encryption Tests
# =============================================================================

@pytest.mark.asyncio
async def test_encryption_enabled(mock_zmq_context, mock_zmq_socket):
    """Test that encryption is configured when enabled."""
    # Arrange
    encryption_manager = Mock(spec=MT4EncryptionManager)
    encryption_manager.encryption_enabled = True
    encryption_manager.configure_socket = Mock(side_effect=lambda s: s)

    client = MT4Client(
        host="localhost",
        rep_port=5555,
        pub_port=5556,
        magic_number=100001,
        encryption_manager=encryption_manager,
        timeout_ms=5000
    )

    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    # Act
    await client.connect()

    # Assert
    encryption_manager.configure_socket.assert_called_once_with(mock_zmq_socket)


@pytest.mark.asyncio
async def test_encryption_disabled(mock_zmq_context, mock_zmq_socket):
    """Test that encryption is not configured when disabled."""
    # Arrange
    encryption_manager = Mock(spec=MT4EncryptionManager)
    encryption_manager.encryption_enabled = False
    encryption_manager.configure_socket = Mock(side_effect=lambda s: s)

    client = MT4Client(
        host="localhost",
        rep_port=5555,
        pub_port=5556,
        magic_number=100001,
        encryption_manager=encryption_manager,
        timeout_ms=5000
    )

    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    # Act
    await client.connect()

    # Assert
    # configure_socket should still be called, but manager handles the no-op
    encryption_manager.configure_socket.assert_called_once()


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_malformed_json_response(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test handling of malformed JSON response."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    mock_zmq_socket.recv_string.return_value = "INVALID JSON"

    command = CreateInstantOrderCommand(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Act & Assert
    with pytest.raises(json.JSONDecodeError):
        await mt4_client.send_command(command)


@pytest.mark.asyncio
async def test_reconnection_after_disconnect(mt4_client, mock_zmq_context, mock_zmq_socket):
    """Test reconnection after disconnect."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.return_value = mock_zmq_socket
    mock_zmq_context.return_value = mock_context_instance

    # Act
    await mt4_client.connect()
    assert mt4_client.is_connected() is True

    await mt4_client.disconnect()
    assert mt4_client.is_connected() is False

    await mt4_client.connect()
    assert mt4_client.is_connected() is True


# =============================================================================
# PUB Socket Subscription Tests (T034 - User Story 2)
# =============================================================================

@pytest.fixture
def mock_pub_socket():
    """Mock PUB socket for subscription tests."""
    socket = AsyncMock()
    socket.poll = AsyncMock(return_value=zmq.POLLIN)
    socket.recv_string = AsyncMock()
    socket.close = AsyncMock()
    socket.setsockopt = Mock()
    socket.subscribe = Mock()
    return socket


@pytest.mark.asyncio
async def test_subscribe_to_pub_socket_success(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test successful subscription to PUB socket."""
    # Arrange
    mock_context_instance = Mock()
    # REQ socket for commands
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    # Act
    await mt4_client.subscribe_to_events()

    # Assert
    mock_pub_socket.connect.assert_called_once_with(f"tcp://{mt4_client.host}:{mt4_client.pub_port}")
    # Verify subscription to all topics (empty filter subscribes to all)
    mock_pub_socket.subscribe.assert_called_once_with(b"")


@pytest.mark.asyncio
async def test_subscribe_with_specific_topics(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test subscription to specific event topics."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()

    # Act
    await mt4_client.subscribe_to_events(topics=["position_updated", "position_closed"])

    # Assert
    assert mock_pub_socket.subscribe.call_count == 2
    mock_pub_socket.subscribe.assert_any_call(b"position_updated")
    mock_pub_socket.subscribe.assert_any_call(b"position_closed")


@pytest.mark.asyncio
async def test_receive_position_updated_event(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test receiving position_updated event from PUB socket."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    # Mock position_updated event
    event_json = json.dumps({
        "event_type": "position_updated",
        "correlation_id": "test-123",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": "0.1",
            "open_price": "75.50",
            "current_price": "75.75",
            "unrealized_pnl": "25.00",
            "stop_loss": None,
            "take_profit": None,
            "open_time": "2025-11-22T10:00:00Z",
            "last_updated": "2025-11-22T10:05:00Z"
        }
    })
    mock_pub_socket.recv_string.return_value = event_json
    mock_pub_socket.poll.return_value = zmq.POLLIN

    await mt4_client.connect()
    await mt4_client.subscribe_to_events()

    # Act
    event_data = await mt4_client.receive_event()

    # Assert
    assert event_data is not None
    assert event_data["event_type"] == "position_updated"
    assert event_data["data"]["ticket_number"] == 12345
    assert event_data["data"]["symbol"] == "CrudeOIL"
    assert event_data["data"]["unrealized_pnl"] == "25.00"


@pytest.mark.asyncio
async def test_receive_position_closed_event(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test receiving position_closed event from PUB socket."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    # Mock position_closed event
    event_json = json.dumps({
        "event_type": "position_closed",
        "correlation_id": "test-456",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": "0.1",
            "open_price": "75.50",
            "close_price": "76.00",
            "realized_pnl": "50.00",
            "open_time": "2025-11-22T10:00:00Z",
            "close_time": "2025-11-22T11:00:00Z",
            "close_reason": "take_profit"
        }
    })
    mock_pub_socket.recv_string.return_value = event_json
    mock_pub_socket.poll.return_value = zmq.POLLIN

    await mt4_client.connect()
    await mt4_client.subscribe_to_events()

    # Act
    event_data = await mt4_client.receive_event()

    # Assert
    assert event_data is not None
    assert event_data["event_type"] == "position_closed"
    assert event_data["data"]["ticket_number"] == 12345
    assert event_data["data"]["realized_pnl"] == "50.00"
    assert event_data["data"]["close_reason"] == "take_profit"


@pytest.mark.asyncio
async def test_event_listener_loop(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test event listener loop that continuously receives events."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    # Mock multiple events
    events = [
        json.dumps({"event_type": "position_updated", "data": {"ticket_number": 123}}),
        json.dumps({"event_type": "position_updated", "data": {"ticket_number": 456}}),
        json.dumps({"event_type": "position_closed", "data": {"ticket_number": 123}}),
    ]
    mock_pub_socket.recv_string.side_effect = events
    mock_pub_socket.poll.return_value = zmq.POLLIN

    await mt4_client.connect()
    await mt4_client.subscribe_to_events()

    # Act - receive multiple events
    received_events = []
    for _ in range(3):
        event_data = await mt4_client.receive_event()
        received_events.append(event_data)

    # Assert
    assert len(received_events) == 3
    assert received_events[0]["event_type"] == "position_updated"
    assert received_events[1]["event_type"] == "position_updated"
    assert received_events[2]["event_type"] == "position_closed"


@pytest.mark.asyncio
async def test_event_receive_timeout(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test event receive with timeout (no events available)."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    # Mock no events available (timeout)
    mock_pub_socket.poll.return_value = 0

    await mt4_client.connect()
    await mt4_client.subscribe_to_events()

    # Act
    event_data = await mt4_client.receive_event(timeout_ms=1000)

    # Assert
    assert event_data is None  # No event received within timeout


@pytest.mark.asyncio
async def test_start_listening_with_callback(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test start_listening() method with event callback."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    # Mock events
    event1 = json.dumps({"event_type": "position_updated", "data": {"ticket_number": 123}})
    event2 = json.dumps({"event_type": "position_closed", "data": {"ticket_number": 123}})

    mock_pub_socket.recv_string.side_effect = [event1, event2, asyncio.CancelledError()]
    mock_pub_socket.poll.return_value = zmq.POLLIN

    await mt4_client.connect()
    await mt4_client.subscribe_to_events()

    # Mock event handler callback
    received_events = []

    async def event_handler(event_data):
        received_events.append(event_data)
        if len(received_events) >= 2:
            raise asyncio.CancelledError()  # Stop after 2 events

    # Act
    try:
        await mt4_client.start_listening(event_handler)
    except asyncio.CancelledError:
        pass  # Expected

    # Assert
    assert len(received_events) == 2
    assert received_events[0]["event_type"] == "position_updated"
    assert received_events[1]["event_type"] == "position_closed"


@pytest.mark.asyncio
async def test_unsubscribe_from_pub_socket(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test unsubscribing from PUB socket."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=["position_updated"])

    # Act
    await mt4_client.unsubscribe_from_events(topics=["position_updated"])

    # Assert
    mock_pub_socket.unsubscribe.assert_called_once_with(b"position_updated")


@pytest.mark.asyncio
async def test_pub_socket_disconnect(mt4_client, mock_zmq_context, mock_zmq_socket, mock_pub_socket):
    """Test PUB socket is closed on disconnect."""
    # Arrange
    mock_context_instance = Mock()
    mock_context_instance.socket.side_effect = [mock_zmq_socket, mock_pub_socket]
    mock_zmq_context.return_value = mock_context_instance

    await mt4_client.connect()
    await mt4_client.subscribe_to_events()

    # Act
    await mt4_client.disconnect()

    # Assert
    mock_pub_socket.close.assert_called_once()
    assert mt4_client.is_connected() is False
