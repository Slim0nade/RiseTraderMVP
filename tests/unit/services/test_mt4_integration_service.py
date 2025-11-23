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
    MarketTick,
    MarketTickEvent,
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


# =============================================================================
# Position Update Event Parsing Tests (T035 - User Story 2)
# =============================================================================

@pytest.mark.asyncio
async def test_handle_position_updated_event_success(mt4_integration_service):
    """Test successful handling of position_updated event."""
    # Arrange
    event_data = {
        "event_type": "position_updated",
        "correlation_id": "test-123",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.50"),
            "current_price": Decimal("75.75"),
            "unrealized_pnl": Decimal("25.00"),
            "stop_loss": None,
            "take_profit": None,
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "last_updated": datetime(2025, 11, 22, 10, 5, 0)
        }
    }

    # Mock repository methods
    mock_position_repo = AsyncMock()
    mock_position_repo.get_by_ticket_number = AsyncMock(return_value=None)
    mock_position_repo.create = AsyncMock()
    mock_position_repo.update = AsyncMock()

    # Act
    await mt4_integration_service.handle_position_updated_event(event_data)

    # Assert - should create new position if not found
    mock_position_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_position_updated_event_update_existing(mt4_integration_service):
    """Test updating existing position with new P&L data."""
    # Arrange
    from src.database.models.mt4_positions import MT4Position

    existing_position = MT4Position(
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.50"),
        current_price=Decimal("75.60"),
        unrealized_pnl=Decimal("10.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 10, 1, 0)
    )

    event_data = {
        "event_type": "position_updated",
        "correlation_id": "test-456",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.50"),
            "current_price": Decimal("75.85"),  # Updated price
            "unrealized_pnl": Decimal("35.00"),  # Updated P&L
            "stop_loss": None,
            "take_profit": None,
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "last_updated": datetime(2025, 11, 22, 10, 10, 0)
        }
    }

    # Mock repository
    mock_position_repo = AsyncMock()
    mock_position_repo.get_by_ticket_number = AsyncMock(return_value=existing_position)
    mock_position_repo.update = AsyncMock()

    # Act
    await mt4_integration_service.handle_position_updated_event(event_data)

    # Assert - should update existing position
    mock_position_repo.update.assert_called_once()
    call_args = mock_position_repo.update.call_args[1]
    assert call_args['current_price'] == Decimal("75.85")
    assert call_args['unrealized_pnl'] == Decimal("35.00")


@pytest.mark.asyncio
async def test_handle_position_closed_event_success(mt4_integration_service):
    """Test successful handling of position_closed event."""
    # Arrange
    from src.database.models.mt4_positions import MT4Position

    existing_position = MT4Position(
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.50"),
        current_price=Decimal("76.00"),
        unrealized_pnl=Decimal("50.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 11, 0, 0)
    )

    event_data = {
        "event_type": "position_closed",
        "correlation_id": "test-789",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.50"),
            "close_price": Decimal("76.00"),
            "realized_pnl": Decimal("50.00"),
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "close_time": datetime(2025, 11, 22, 11, 0, 0),
            "close_reason": "take_profit"
        }
    }

    # Mock repositories
    mock_position_repo = AsyncMock()
    mock_position_repo.get_by_ticket_number = AsyncMock(return_value=existing_position)
    mock_position_repo.delete = AsyncMock()

    mock_order_repo = AsyncMock()
    mock_order_repo.get_by_ticket_number = AsyncMock()
    mock_order_repo.update_status = AsyncMock()

    # Act
    await mt4_integration_service.handle_position_closed_event(event_data)

    # Assert - should delete position and update order
    mock_position_repo.delete.assert_called_once_with(ticket_number=12345)


@pytest.mark.asyncio
async def test_handle_position_event_with_invalid_data(mt4_integration_service):
    """Test handling position event with invalid/missing data."""
    # Arrange
    invalid_event_data = {
        "event_type": "position_updated",
        "correlation_id": "test-invalid",
        "data": {
            "ticket_number": 12345,
            # Missing required fields
        }
    }

    # Act & Assert - should handle gracefully without crashing
    with pytest.raises(Exception):  # ValidationError from Pydantic
        await mt4_integration_service.handle_position_updated_event(invalid_event_data)


@pytest.mark.asyncio
async def test_position_event_publishes_to_redis(mt4_integration_service):
    """Test that position_updated event is published to Redis."""
    # Arrange
    event_data = {
        "event_type": "position_updated",
        "correlation_id": "test-redis",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.50"),
            "current_price": Decimal("75.75"),
            "unrealized_pnl": Decimal("25.00"),
            "stop_loss": None,
            "take_profit": None,
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "last_updated": datetime(2025, 11, 22, 10, 5, 0)
        }
    }

    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.publish_event = AsyncMock()
    mt4_integration_service.redis_client = mock_redis

    # Act
    await mt4_integration_service.handle_position_updated_event(event_data)

    # Assert - should publish to Redis
    mock_redis.publish_event.assert_called_once()
    call_args = mock_redis.publish_event.call_args
    assert call_args[1]['channel'] == 'mt4:events:position_updated'


@pytest.mark.asyncio
async def test_position_closed_updates_order_status(mt4_integration_service):
    """Test that position_closed event updates associated order to CLOSED."""
    # Arrange
    from src.database.models.mt4_orders import MT4Order
    from src.database.models.mt4_positions import MT4Position

    existing_order = MT4Order(
        order_id="order-123",
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        order_type="MARKET",
        status="CONFIRMED"
    )

    existing_position = MT4Position(
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.50"),
        current_price=Decimal("76.00"),
        unrealized_pnl=Decimal("50.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 11, 0, 0)
    )

    event_data = {
        "event_type": "position_closed",
        "correlation_id": "test-close-order",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.50"),
            "close_price": Decimal("76.00"),
            "realized_pnl": Decimal("50.00"),
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "close_time": datetime(2025, 11, 22, 11, 0, 0),
            "close_reason": "manual"
        }
    }

    # Mock repositories
    mock_position_repo = AsyncMock()
    mock_position_repo.get_by_ticket_number = AsyncMock(return_value=existing_position)
    mock_position_repo.delete = AsyncMock()

    mock_order_repo = AsyncMock()
    mock_order_repo.get_by_ticket_number = AsyncMock(return_value=existing_order)
    mock_order_repo.update_status = AsyncMock()

    mt4_integration_service.order_repository = mock_order_repo

    # Act
    await mt4_integration_service.handle_position_closed_event(event_data)

    # Assert - order should be updated to CLOSED
    mock_order_repo.update_status.assert_called_once()
    call_args = mock_order_repo.update_status.call_args[1]
    assert call_args['status'] == 'CLOSED'
    assert call_args['realized_pnl'] == Decimal("50.00")


@pytest.mark.asyncio
async def test_position_event_records_metrics(mt4_integration_service):
    """Test that position events record Prometheus metrics."""
    # Arrange
    event_data = {
        "event_type": "position_updated",
        "correlation_id": "test-metrics",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.50"),
            "current_price": Decimal("75.75"),
            "unrealized_pnl": Decimal("25.00"),
            "stop_loss": None,
            "take_profit": None,
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "last_updated": datetime(2025, 11, 22, 10, 5, 0)
        }
    }

    # Mock metrics recording
    with patch('src.services.mt4_integration_service.record_position_update') as mock_record:
        # Act
        await mt4_integration_service.handle_position_updated_event(event_data)

        # Assert - metrics should be recorded
        mock_record.assert_called_once()
        call_args = mock_record.call_args[1]
        assert call_args['symbol'] == 'CrudeOIL'
        assert call_args['unrealized_pnl'] == Decimal("25.00")


# =============================================================================
# Market Tick Event Tests (T048 - User Story 3)
# =============================================================================

@pytest.mark.asyncio
async def test_handle_market_tick_event_publishes_to_redis(mt4_integration_service):
    """Test that market tick event is published to Redis."""
    # Arrange
    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00",
            "volume": 1000
        }
    }

    # Mock position repository (not used for ticks)
    mock_position_repo = AsyncMock()

    # Act
    await mt4_integration_service.handle_market_tick_event(event_data)

    # Assert - event should be published to Redis
    mt4_integration_service.redis_client.publish_event.assert_called_once()
    call_args = mt4_integration_service.redis_client.publish_event.call_args[1]
    assert call_args['channel'] == 'mt4:events:market_tick'
    assert 'event' in call_args


@pytest.mark.asyncio
async def test_handle_market_tick_event_validates_schema(mt4_integration_service):
    """Test that market tick event validates data schema."""
    # Arrange - missing required field
    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            # Missing "ask"
            "timestamp": "2024-01-15T10:30:00"
        }
    }

    # Act & Assert - should raise ValidationError
    with pytest.raises(Exception):  # Pydantic ValidationError
        await mt4_integration_service.handle_market_tick_event(event_data)


@pytest.mark.asyncio
async def test_handle_market_tick_event_records_metrics(mt4_integration_service):
    """Test that market tick event records Prometheus metrics."""
    # Arrange
    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00.500",
            "volume": 1000
        }
    }

    # Mock metrics recording
    with patch('src.services.mt4_integration_service.record_market_tick') as mock_record:
        # Act
        await mt4_integration_service.handle_market_tick_event(event_data)

        # Assert - metrics should be recorded
        mock_record.assert_called_once()
        call_args = mock_record.call_args
        assert call_args[1]['symbol'] == 'CrudeOIL'
        assert 'latency_seconds' in call_args[1]


@pytest.mark.asyncio
async def test_handle_market_tick_event_calculates_latency(mt4_integration_service):
    """Test that market tick event calculates latency from MT4 timestamp."""
    # Arrange - tick from 1 second ago
    tick_timestamp = datetime.utcnow() - timedelta(seconds=1)
    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "EURUSD",
            "bid": "1.08500",
            "ask": "1.08520",
            "timestamp": tick_timestamp.isoformat(),
            "volume": 500
        }
    }

    # Mock metrics to capture latency
    with patch('src.services.mt4_integration_service.record_market_tick') as mock_record:
        # Act
        await mt4_integration_service.handle_market_tick_event(event_data)

        # Assert - latency should be around 1 second
        call_args = mock_record.call_args[1]
        latency = call_args['latency_seconds']
        assert 0.9 <= latency <= 1.5  # Allow some tolerance


@pytest.mark.asyncio
async def test_handle_market_tick_event_without_volume(mt4_integration_service):
    """Test that market tick event handles optional volume field."""
    # Arrange - no volume
    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "EURUSD",
            "bid": "1.08500",
            "ask": "1.08520",
            "timestamp": "2024-01-15T10:30:00"
            # No volume
        }
    }

    # Act
    await mt4_integration_service.handle_market_tick_event(event_data)

    # Assert - should succeed without error
    mt4_integration_service.redis_client.publish_event.assert_called_once()


@pytest.mark.asyncio
async def test_handle_market_tick_event_logs_reception(mt4_integration_service):
    """Test that market tick event logs reception."""
    # Arrange
    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00",
            "volume": 1000
        }
    }

    # Mock logger
    with patch.object(mt4_integration_service.logger, 'debug') as mock_log:
        # Act
        await mt4_integration_service.handle_market_tick_event(event_data)

        # Assert - should log reception
        mock_log.assert_called()
        log_call = mock_log.call_args
        assert 'market_tick_received' in str(log_call) or 'symbol' in str(log_call)


@pytest.mark.asyncio
async def test_handle_market_tick_event_handles_errors_gracefully(mt4_integration_service):
    """Test that market tick event handler handles errors gracefully."""
    # Arrange - cause Redis to fail
    mt4_integration_service.redis_client.publish_event = AsyncMock(
        side_effect=Exception("Redis connection failed")
    )

    event_data = {
        "event_type": "market_tick",
        "correlation_id": "tick_123",
        "data": {
            "symbol": "CrudeOIL",
            "bid": "75.123",
            "ask": "75.145",
            "timestamp": "2024-01-15T10:30:00",
            "volume": 1000
        }
    }

    # Act - should not raise exception
    await mt4_integration_service.handle_market_tick_event(event_data)

    # Assert - error should be logged
    # (In real implementation, check logger.error was called)


# =============================================================================
# Portfolio Risk Aggregation Tests (T061 - User Story 5)
# =============================================================================

@pytest.mark.asyncio
async def test_calculate_portfolio_risk_single_ea(mt4_integration_service):
    """Test portfolio risk calculation with single EA."""
    # Arrange - mock position repository with positions
    mock_positions = [
        Mock(
            magic_number=100000,
            symbol="CrudeOIL",
            volume=Decimal("0.1"),
            unrealized_pnl=Decimal("50.00"),
            direction="BUY"
        ),
        Mock(
            magic_number=100000,
            symbol="EURUSD",
            volume=Decimal("0.2"),
            unrealized_pnl=Decimal("-25.00"),
            direction="SELL"
        )
    ]

    # Act
    portfolio_risk = await mt4_integration_service.calculate_portfolio_risk(mock_positions)

    # Assert
    assert portfolio_risk["total_positions"] == 2
    assert portfolio_risk["total_unrealized_pnl"] == Decimal("25.00")
    assert portfolio_risk["ea_count"] == 1


@pytest.mark.asyncio
async def test_calculate_portfolio_risk_multiple_eas(mt4_integration_service):
    """Test portfolio risk aggregation across multiple EAs."""
    # Arrange
    mock_positions = [
        Mock(magic_number=100000, unrealized_pnl=Decimal("50.00"), volume=Decimal("0.1")),
        Mock(magic_number=100000, unrealized_pnl=Decimal("30.00"), volume=Decimal("0.1")),
        Mock(magic_number=100001, unrealized_pnl=Decimal("-20.00"), volume=Decimal("0.2")),
        Mock(magic_number=100002, unrealized_pnl=Decimal("100.00"), volume=Decimal("0.3")),
    ]

    # Act
    portfolio_risk = await mt4_integration_service.calculate_portfolio_risk(mock_positions)

    # Assert
    assert portfolio_risk["total_positions"] == 4
    assert portfolio_risk["total_unrealized_pnl"] == Decimal("160.00")
    assert portfolio_risk["ea_count"] == 3


@pytest.mark.asyncio
async def test_calculate_portfolio_risk_by_symbol(mt4_integration_service):
    """Test portfolio risk breakdown by symbol."""
    # Arrange
    mock_positions = [
        Mock(symbol="CrudeOIL", unrealized_pnl=Decimal("50.00"), volume=Decimal("0.1")),
        Mock(symbol="CrudeOIL", unrealized_pnl=Decimal("30.00"), volume=Decimal("0.1")),
        Mock(symbol="EURUSD", unrealized_pnl=Decimal("-20.00"), volume=Decimal("0.2")),
    ]

    # Act
    portfolio_risk = await mt4_integration_service.calculate_portfolio_risk(mock_positions)

    # Assert
    assert "by_symbol" in portfolio_risk
    assert portfolio_risk["by_symbol"]["CrudeOIL"]["pnl"] == Decimal("80.00")
    assert portfolio_risk["by_symbol"]["EURUSD"]["pnl"] == Decimal("-20.00")


@pytest.mark.asyncio
async def test_calculate_portfolio_risk_empty_positions(mt4_integration_service):
    """Test portfolio risk with no positions."""
    # Act
    portfolio_risk = await mt4_integration_service.calculate_portfolio_risk([])

    # Assert
    assert portfolio_risk["total_positions"] == 0
    assert portfolio_risk["total_unrealized_pnl"] == Decimal("0.00")
    assert portfolio_risk["ea_count"] == 0


# =============================================================================
# Risk Limit Enforcement Tests (T062 - User Story 5)
# =============================================================================

@pytest.mark.asyncio
async def test_check_risk_limits_within_limits(mt4_integration_service):
    """Test risk check passes when within limits."""
    # Arrange
    portfolio_risk = {
        "total_unrealized_pnl": Decimal("100.00"),
        "total_exposure": Decimal("5000.00"),
        "total_positions": 5
    }

    # Act
    can_trade = await mt4_integration_service.check_risk_limits(
        portfolio_risk=portfolio_risk,
        max_loss=Decimal("1000.00"),
        max_exposure=Decimal("10000.00"),
        max_positions=10
    )

    # Assert
    assert can_trade is True


@pytest.mark.asyncio
async def test_check_risk_limits_exceeds_max_loss(mt4_integration_service):
    """Test risk check fails when exceeding max loss."""
    # Arrange
    portfolio_risk = {
        "total_unrealized_pnl": Decimal("-1500.00"),
        "total_exposure": Decimal("5000.00"),
        "total_positions": 5
    }

    # Act
    can_trade = await mt4_integration_service.check_risk_limits(
        portfolio_risk=portfolio_risk,
        max_loss=Decimal("1000.00"),
        max_exposure=Decimal("10000.00"),
        max_positions=10
    )

    # Assert
    assert can_trade is False


@pytest.mark.asyncio
async def test_check_risk_limits_exceeds_max_exposure(mt4_integration_service):
    """Test risk check fails when exceeding max exposure."""
    # Arrange
    portfolio_risk = {
        "total_unrealized_pnl": Decimal("100.00"),
        "total_exposure": Decimal("15000.00"),
        "total_positions": 5
    }

    # Act
    can_trade = await mt4_integration_service.check_risk_limits(
        portfolio_risk=portfolio_risk,
        max_loss=Decimal("1000.00"),
        max_exposure=Decimal("10000.00"),
        max_positions=10
    )

    # Assert
    assert can_trade is False


@pytest.mark.asyncio
async def test_check_risk_limits_exceeds_max_positions(mt4_integration_service):
    """Test risk check fails when exceeding max positions."""
    # Arrange
    portfolio_risk = {
        "total_unrealized_pnl": Decimal("100.00"),
        "total_exposure": Decimal("5000.00"),
        "total_positions": 15
    }

    # Act
    can_trade = await mt4_integration_service.check_risk_limits(
        portfolio_risk=portfolio_risk,
        max_loss=Decimal("1000.00"),
        max_exposure=Decimal("10000.00"),
        max_positions=10
    )

    # Assert
    assert can_trade is False


@pytest.mark.asyncio
async def test_check_risk_limits_at_threshold(mt4_integration_service):
    """Test risk check at exact threshold (should pass)."""
    # Arrange
    portfolio_risk = {
        "total_unrealized_pnl": Decimal("-1000.00"),
        "total_exposure": Decimal("10000.00"),
        "total_positions": 10
    }

    # Act
    can_trade = await mt4_integration_service.check_risk_limits(
        portfolio_risk=portfolio_risk,
        max_loss=Decimal("1000.00"),
        max_exposure=Decimal("10000.00"),
        max_positions=10
    )

    # Assert
    assert can_trade is True
