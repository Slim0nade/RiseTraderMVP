"""
Unit tests for MT4IntegrationService.

Tests order submission, confirmation handling, and rejection handling.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
import uuid

from src.services.mt4_integration_service import MT4IntegrationService
from src.database.repositories.mt4_order_repository import MT4OrderRepository
from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
from src.database.models.mt4_orders import MT4Order
from src.database.models.mt4_connection import MT4Connection
from src.utils.redis_client import MT4RedisClient
from src.trading.execution.symbol_loader import SymbolLoader
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_models import (
    OrderResponse,
    OrderConfirmedEvent,
    OrderConfirmedData,
    OrderRejectedEvent,
    OrderRejectedData,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_order_repository():
    """Mock MT4OrderRepository."""
    repo = AsyncMock(spec=MT4OrderRepository)
    repo.create = AsyncMock()
    repo.update_status = AsyncMock()
    repo.get_by_order_id = AsyncMock()
    repo.get_by_ticket_number = AsyncMock()
    return repo


@pytest.fixture
def mock_connection_repository():
    """Mock MT4ConnectionRepository."""
    repo = AsyncMock(spec=MT4ConnectionRepository)

    # Mock connection
    connection = Mock(spec=MT4Connection)
    connection.ea_id = "ea_100001"
    connection.magic_number = 100001
    connection.rep_port = 5555
    connection.pub_port = 5556
    connection.mt4_server_host = "localhost"
    connection.encryption_enabled = True
    connection.status = "ACTIVE"

    repo.get_by_magic_number = AsyncMock(return_value=connection)
    return repo


@pytest.fixture
def mock_redis_client():
    """Mock MT4RedisClient."""
    client = AsyncMock(spec=MT4RedisClient)
    client.publish_event = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_symbol_loader():
    """Mock SymbolLoader."""
    loader = Mock(spec=SymbolLoader)
    loader.is_valid_symbol = Mock(return_value=True)
    loader.validate_volume = Mock()
    loader.validate_direction = Mock()
    return loader


@pytest.fixture
def mock_mt4_client():
    """Mock MT4Client."""
    client = AsyncMock(spec=MT4Client)
    client.create_instant_order = AsyncMock()
    client.connect = AsyncMock()
    client.is_connected = Mock(return_value=True)
    return client


@pytest.fixture
def mock_logger():
    """Mock logger."""
    return Mock()


@pytest.fixture
def mt4_integration_service(
    mock_order_repository,
    mock_redis_client,
    mock_connection_repository,
    mock_symbol_loader,
    mock_logger
):
    """Create MT4IntegrationService instance for testing."""
    service = MT4IntegrationService(
        order_repository=mock_order_repository,
        redis_client=mock_redis_client,
        connection_repository=mock_connection_repository,
        symbol_loader=mock_symbol_loader,
        logger=mock_logger
    )
    return service


# =============================================================================
# Order Submission Tests
# =============================================================================

@pytest.mark.asyncio
async def test_submit_market_order_success(
    mt4_integration_service,
    mock_order_repository,
    mock_mt4_client,
    mock_redis_client
):
    """Test successful market order submission."""
    # Arrange
    mt4_integration_service._clients[100001] = mock_mt4_client

    order_id = str(uuid.uuid4())
    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.UUID(order_id)
    mock_order.order_id = order_id
    mock_order.magic_number = 100001
    mock_order.symbol = "CrudeOIL"
    mock_order.direction = "BUY"
    mock_order.volume = Decimal("0.1")
    mock_order.status = "PENDING"
    mock_order.correlation_id = str(uuid.uuid4())
    mock_order.submitted_at = datetime.utcnow()

    mock_order_repository.create.return_value = mock_order

    order_response = OrderResponse(
        success=True,
        ticket_number=12345,
        execution_price=Decimal("75.50"),
        execution_time=datetime.utcnow(),
        correlation_id=mock_order.correlation_id
    )

    mock_mt4_client.create_instant_order.return_value = order_response

    # Act
    result = await mt4_integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Assert
    assert result == mock_order
    mock_order_repository.create.assert_called_once()
    mock_mt4_client.create_instant_order.assert_called_once()
    mock_redis_client.publish_event.assert_called_once()


@pytest.mark.asyncio
async def test_submit_market_order_with_sl_tp(
    mt4_integration_service,
    mock_order_repository,
    mock_mt4_client
):
    """Test order submission with stop loss and take profit."""
    # Arrange
    mt4_integration_service._clients[100001] = mock_mt4_client

    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.uuid4()
    mock_order.order_id = str(uuid.uuid4())
    mock_order.correlation_id = str(uuid.uuid4())
    mock_order.submitted_at = datetime.utcnow()

    mock_order_repository.create.return_value = mock_order

    order_response = OrderResponse(
        success=True,
        ticket_number=12345,
        execution_price=Decimal("75.50"),
        execution_time=datetime.utcnow(),
        correlation_id=mock_order.correlation_id
    )

    mock_mt4_client.create_instant_order.return_value = order_response

    # Act
    await mt4_integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001,
        stop_loss=Decimal("74.00"),
        take_profit=Decimal("77.00")
    )

    # Assert
    call_args = mock_mt4_client.create_instant_order.call_args
    assert call_args.kwargs["stop_loss"] == Decimal("74.00")
    assert call_args.kwargs["take_profit"] == Decimal("77.00")


@pytest.mark.asyncio
async def test_submit_market_order_invalid_symbol(
    mt4_integration_service,
    mock_symbol_loader
):
    """Test order rejection for invalid symbol."""
    # Arrange
    mock_symbol_loader.is_valid_symbol.return_value = False

    # Act & Assert
    with pytest.raises(ValueError, match="Invalid symbol"):
        await mt4_integration_service.submit_market_order(
            symbol="INVALID",
            direction="BUY",
            volume=Decimal("0.1"),
            magic_number=100001
        )


@pytest.mark.asyncio
async def test_submit_market_order_invalid_volume(
    mt4_integration_service,
    mock_symbol_loader
):
    """Test order rejection for invalid volume."""
    # Arrange
    mock_symbol_loader.validate_volume.side_effect = ValueError("Volume too large")

    # Act & Assert
    with pytest.raises(ValueError, match="Volume too large"):
        await mt4_integration_service.submit_market_order(
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("1000.0"),
            magic_number=100001
        )


@pytest.mark.asyncio
async def test_submit_market_order_connection_not_found(
    mt4_integration_service,
    mock_connection_repository
):
    """Test order rejection when EA connection not found."""
    # Arrange
    mock_connection_repository.get_by_magic_number.return_value = None

    # Act & Assert
    with pytest.raises(ValueError, match="Connection not found"):
        await mt4_integration_service.submit_market_order(
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            magic_number=999999
        )


# =============================================================================
# Order Confirmation Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_handle_order_confirmed_event(
    mt4_integration_service,
    mock_order_repository
):
    """Test handling of order_confirmed event."""
    # Arrange
    order_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.UUID(order_id)
    mock_order.order_id = order_id
    mock_order.magic_number = 100001
    mock_order.symbol = "CrudeOIL"
    mock_order.direction = "BUY"
    mock_order.status = "PENDING"
    mock_order.submitted_at = datetime.utcnow() - timedelta(seconds=1)
    mock_order.calculate_latency_ms = Mock(return_value=1000.0)

    mock_order_repository.get_by_ticket_number.return_value = mock_order

    event_data = {
        "event_type": "order_confirmed",
        "data": {
            "order_id": order_id,
            "magic_number": 100001,
            "ticket_number": 12345,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": 0.1,
            "execution_price": 75.50,
            "execution_time": datetime.utcnow().isoformat()
        },
        "correlation_id": correlation_id
    }

    # Act
    await mt4_integration_service.handle_order_confirmed_event(event_data)

    # Assert
    mock_order_repository.get_by_ticket_number.assert_called_once_with(12345)
    mock_order_repository.update_status.assert_called_once()

    update_call = mock_order_repository.update_status.call_args
    assert update_call.kwargs["status"] == "CONFIRMED"
    assert update_call.kwargs["ticket_number"] == 12345


@pytest.mark.asyncio
async def test_handle_order_confirmed_latency_calculation(
    mt4_integration_service,
    mock_order_repository
):
    """Test latency calculation in order confirmation."""
    # Arrange
    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.uuid4()
    mock_order.order_id = str(uuid.uuid4())
    mock_order.submitted_at = datetime.utcnow() - timedelta(milliseconds=500)
    mock_order.calculate_latency_ms = Mock(return_value=500.0)

    mock_order_repository.get_by_ticket_number.return_value = mock_order

    event_data = {
        "event_type": "order_confirmed",
        "data": {
            "order_id": mock_order.order_id,
            "magic_number": 100001,
            "ticket_number": 12345,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": 0.1,
            "execution_price": 75.50,
            "execution_time": datetime.utcnow().isoformat()
        }
    }

    # Act
    with patch('src.monitoring.mt4_metrics.record_order_confirmed') as mock_metric:
        await mt4_integration_service.handle_order_confirmed_event(event_data)

        # Assert
        mock_order.calculate_latency_ms.assert_called_once()
        mock_metric.assert_called_once()
        call_args = mock_metric.call_args
        # Latency should be in seconds
        assert call_args.kwargs["latency_seconds"] == 0.5


@pytest.mark.asyncio
async def test_handle_order_confirmed_order_not_found(
    mt4_integration_service,
    mock_order_repository,
    mock_logger
):
    """Test handling confirmation for non-existent order."""
    # Arrange
    mock_order_repository.get_by_ticket_number.return_value = None

    event_data = {
        "event_type": "order_confirmed",
        "data": {
            "order_id": str(uuid.uuid4()),
            "magic_number": 100001,
            "ticket_number": 99999,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": 0.1,
            "execution_price": 75.50,
            "execution_time": datetime.utcnow().isoformat()
        }
    }

    # Act
    await mt4_integration_service.handle_order_confirmed_event(event_data)

    # Assert - Should log warning but not raise error
    mock_logger.warning.assert_called()
    mock_order_repository.update_status.assert_not_called()


# =============================================================================
# Order Rejection Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_handle_order_rejected_event(
    mt4_integration_service,
    mock_order_repository,
    mock_redis_client
):
    """Test handling of order_rejected event."""
    # Arrange
    order_id = str(uuid.uuid4())

    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.UUID(order_id)
    mock_order.order_id = order_id
    mock_order.magic_number = 100001
    mock_order.symbol = "CrudeOIL"
    mock_order.status = "PENDING"

    mock_order_repository.get_by_order_id.return_value = mock_order

    event_data = {
        "event_type": "order_rejected",
        "data": {
            "order_id": order_id,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "error_code": 134,
            "error_message": "Not enough margin"
        }
    }

    # Act
    await mt4_integration_service.handle_order_rejected_event(event_data)

    # Assert
    mock_order_repository.update_status.assert_called_once()
    update_call = mock_order_repository.update_status.call_args
    assert update_call.kwargs["status"] == "REJECTED"
    assert update_call.kwargs["error_message"] == "Not enough margin"


@pytest.mark.asyncio
async def test_handle_order_rejected_publishes_event(
    mt4_integration_service,
    mock_order_repository,
    mock_redis_client
):
    """Test that rejection event is published to Redis."""
    # Arrange
    order_id = str(uuid.uuid4())

    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.UUID(order_id)
    mock_order.order_id = order_id

    mock_order_repository.get_by_order_id.return_value = mock_order

    event_data = {
        "event_type": "order_rejected",
        "data": {
            "order_id": order_id,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "error_code": 134,
            "error_message": "Not enough margin"
        }
    }

    # Act
    await mt4_integration_service.handle_order_rejected_event(event_data)

    # Assert
    mock_redis_client.publish_event.assert_called()


@pytest.mark.asyncio
async def test_handle_order_rejected_records_metrics(
    mt4_integration_service,
    mock_order_repository
):
    """Test that rejection metrics are recorded."""
    # Arrange
    order_id = str(uuid.uuid4())

    mock_order = Mock(spec=MT4Order)
    mock_order.id = uuid.UUID(order_id)
    mock_order.order_id = order_id
    mock_order.magic_number = 100001
    mock_order.symbol = "CrudeOIL"

    mock_order_repository.get_by_order_id.return_value = mock_order

    event_data = {
        "event_type": "order_rejected",
        "data": {
            "order_id": order_id,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "error_code": 134,
            "error_message": "Not enough margin"
        }
    }

    # Act
    with patch('src.monitoring.mt4_metrics.record_order_rejected') as mock_metric:
        await mt4_integration_service.handle_order_rejected_event(event_data)

        # Assert
        mock_metric.assert_called_once()
        call_args = mock_metric.call_args
        assert call_args.kwargs["ea_id"] == "ea_100001"
        assert call_args.kwargs["symbol"] == "CrudeOIL"
        assert call_args.kwargs["error_code"] == "134"


# =============================================================================
# Client Management Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_client_creates_new(mt4_integration_service, mock_connection_repository):
    """Test that _get_client creates new client if not cached."""
    # Act
    with patch('src.trading.execution.mt4_client.MT4Client') as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance

        client = await mt4_integration_service._get_client(100001)

        # Assert
        assert client == mock_client_instance
        assert 100001 in mt4_integration_service._clients
        mock_client_instance.connect.assert_called_once()


@pytest.mark.asyncio
async def test_get_client_returns_cached(mt4_integration_service):
    """Test that _get_client returns cached client."""
    # Arrange
    cached_client = AsyncMock(spec=MT4Client)
    mt4_integration_service._clients[100001] = cached_client

    # Act
    client = await mt4_integration_service._get_client(100001)

    # Assert
    assert client == cached_client
    cached_client.connect.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_magic_numbers(mt4_integration_service):
    """Test handling multiple EAs with different magic numbers."""
    # Arrange
    magic_numbers = [100001, 100002, 100003]

    # Act
    with patch('src.trading.execution.mt4_client.MT4Client') as MockClient:
        mock_instances = [AsyncMock() for _ in magic_numbers]
        MockClient.side_effect = mock_instances

        clients = []
        for magic_number in magic_numbers:
            client = await mt4_integration_service._get_client(magic_number)
            clients.append(client)

        # Assert
        assert len(mt4_integration_service._clients) == 3
        assert all(client in mock_instances for client in clients)
