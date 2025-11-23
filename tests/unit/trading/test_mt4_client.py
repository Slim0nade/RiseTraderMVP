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
