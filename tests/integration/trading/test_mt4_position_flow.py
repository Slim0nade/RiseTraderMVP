"""
Integration tests for MT4 position lifecycle flow.

Tests the complete flow:
1. Position opened (from order execution)
2. Position updates with P&L changes
3. Position closed with final P&L

Tests database integration, event publishing, and end-to-end flow.
"""
import asyncio
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from src.services.mt4_integration_service import MT4IntegrationService
from src.database.models.mt4_orders import MT4Order
from src.database.models.mt4_positions import MT4Position
from src.trading.execution.mt4_models import (
    PositionUpdatedEvent,
    PositionUpdatedData,
    PositionClosedEvent,
    PositionClosedData,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_order_repository():
    """Mock order repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.get_by_ticket_number = AsyncMock()
    repo.update_status = AsyncMock()
    return repo


@pytest.fixture
def mock_position_repository():
    """Mock position repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.get_by_ticket_number = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    return repo


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = AsyncMock()
    client.publish_event = AsyncMock()
    return client


@pytest.fixture
def mock_connection_repository():
    """Mock connection repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_symbol_loader():
    """Mock symbol loader."""
    loader = Mock()
    loader.is_valid_symbol = Mock(return_value=True)
    loader.validate_volume = Mock()
    loader.validate_direction = Mock()
    loader.get_symbols = Mock(return_value=[])
    return loader


@pytest.fixture
def mt4_integration_service(
    mock_order_repository,
    mock_redis_client,
    mock_connection_repository,
    mock_symbol_loader
):
    """Create MT4IntegrationService with mocked dependencies."""
    return MT4IntegrationService(
        order_repository=mock_order_repository,
        redis_client=mock_redis_client,
        connection_repository=mock_connection_repository,
        symbol_loader=mock_symbol_loader
    )


# =============================================================================
# Position Lifecycle Integration Tests (T037 - User Story 2)
# =============================================================================

@pytest.mark.asyncio
async def test_complete_position_lifecycle(
    mt4_integration_service,
    mock_order_repository,
    mock_position_repository,
    mock_redis_client
):
    """Test complete position lifecycle: open → update → close."""

    # STEP 1: Order is submitted and confirmed (from User Story 1)
    # This creates a position in MT4
    order = MT4Order(
        order_id="order-123",
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        order_type="MARKET",
        status="CONFIRMED",
        execution_price=Decimal("75.00")
    )

    # STEP 2: Position opened - first update from MT4
    position_opened_event = {
        "event_type": "position_updated",
        "correlation_id": "corr-001",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.00"),
            "current_price": Decimal("75.00"),  # Just opened
            "unrealized_pnl": Decimal("0.00"),
            "stop_loss": Decimal("74.00"),
            "take_profit": Decimal("77.00"),
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "last_updated": datetime(2025, 11, 22, 10, 0, 0)
        }
    }

    # Mock: Position doesn't exist yet, will be created
    mock_position_repository.get_by_ticket_number.return_value = None
    mock_position_repository.create.return_value = MT4Position(
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.00"),
        current_price=Decimal("75.00"),
        unrealized_pnl=Decimal("0.00"),
        stop_loss=Decimal("74.00"),
        take_profit=Decimal("77.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 10, 0, 0)
    )

    # Inject repository
    mt4_integration_service.position_repository = mock_position_repository

    # Act: Handle position opened event
    await mt4_integration_service.handle_position_updated_event(position_opened_event)

    # Assert: Position created in database
    mock_position_repository.create.assert_called_once()

    # Assert: Event published to Redis
    mock_redis_client.publish_event.assert_called()

    # STEP 3: Position updated with profit (price moved up)
    existing_position = MT4Position(
        ticket_number=12345,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.00"),
        current_price=Decimal("75.00"),
        unrealized_pnl=Decimal("0.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 10, 0, 0)
    )

    position_update_event = {
        "event_type": "position_updated",
        "correlation_id": "corr-002",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.00"),
            "current_price": Decimal("75.50"),  # Price moved up
            "unrealized_pnl": Decimal("50.00"),  # +$50
            "stop_loss": Decimal("74.00"),
            "take_profit": Decimal("77.00"),
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "last_updated": datetime(2025, 11, 22, 10, 5, 0)
        }
    }

    # Mock: Position exists now
    mock_position_repository.get_by_ticket_number.return_value = existing_position

    # Act: Handle position update
    await mt4_integration_service.handle_position_updated_event(position_update_event)

    # Assert: Position updated in database
    mock_position_repository.update.assert_called_once()
    call_args = mock_position_repository.update.call_args[1]
    assert call_args['current_price'] == Decimal("75.50")
    assert call_args['unrealized_pnl'] == Decimal("50.00")

    # STEP 4: Position closed at take profit
    position_closed_event = {
        "event_type": "position_closed",
        "correlation_id": "corr-003",
        "data": {
            "ticket_number": 12345,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.00"),
            "close_price": Decimal("77.00"),  # Hit take profit
            "realized_pnl": Decimal("200.00"),  # Final P&L
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "close_time": datetime(2025, 11, 22, 11, 0, 0),
            "close_reason": "take_profit"
        }
    }

    # Mock: Get the order for status update
    mock_order_repository.get_by_ticket_number.return_value = order

    # Act: Handle position closure
    await mt4_integration_service.handle_position_closed_event(position_closed_event)

    # Assert: Position deleted from database
    mock_position_repository.delete.assert_called_once_with(ticket_number=12345)

    # Assert: Order updated to CLOSED with realized P&L
    mock_order_repository.update_status.assert_called()
    order_call_args = mock_order_repository.update_status.call_args[1]
    assert order_call_args['status'] == 'CLOSED'
    assert order_call_args['realized_pnl'] == Decimal("200.00")

    # Assert: Position closed event published to Redis
    assert mock_redis_client.publish_event.call_count >= 2  # At least update + close


@pytest.mark.asyncio
async def test_position_closure_at_stop_loss(
    mt4_integration_service,
    mock_order_repository,
    mock_position_repository,
    mock_redis_client
):
    """Test position closed at stop loss (losing trade)."""

    # Arrange: Position exists and hits stop loss
    existing_position = MT4Position(
        ticket_number=12346,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.00"),
        current_price=Decimal("74.00"),  # At stop loss
        unrealized_pnl=Decimal("-100.00"),
        stop_loss=Decimal("74.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 10, 30, 0)
    )

    order = MT4Order(
        order_id="order-456",
        ticket_number=12346,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        order_type="MARKET",
        status="CONFIRMED"
    )

    position_closed_event = {
        "event_type": "position_closed",
        "correlation_id": "corr-sl-001",
        "data": {
            "ticket_number": 12346,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.00"),
            "close_price": Decimal("74.00"),  # Closed at stop loss
            "realized_pnl": Decimal("-100.00"),  # Loss
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "close_time": datetime(2025, 11, 22, 10, 30, 0),
            "close_reason": "stop_loss"
        }
    }

    # Mock repositories
    mock_position_repository.get_by_ticket_number.return_value = existing_position
    mock_order_repository.get_by_ticket_number.return_value = order
    mt4_integration_service.position_repository = mock_position_repository

    # Act
    await mt4_integration_service.handle_position_closed_event(position_closed_event)

    # Assert: Position deleted
    mock_position_repository.delete.assert_called_once_with(ticket_number=12346)

    # Assert: Order updated with loss
    mock_order_repository.update_status.assert_called()
    call_args = mock_order_repository.update_status.call_args[1]
    assert call_args['status'] == 'CLOSED'
    assert call_args['realized_pnl'] == Decimal("-100.00")


@pytest.mark.asyncio
async def test_manual_position_closure(
    mt4_integration_service,
    mock_order_repository,
    mock_position_repository,
    mock_redis_client
):
    """Test position closed manually by trader."""

    # Arrange
    existing_position = MT4Position(
        ticket_number=12347,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="SELL",
        volume=Decimal("0.2"),
        open_price=Decimal("76.00"),
        current_price=Decimal("75.50"),
        unrealized_pnl=Decimal("100.00"),  # Profit on short
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 10, 45, 0)
    )

    order = MT4Order(
        order_id="order-789",
        ticket_number=12347,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="SELL",
        volume=Decimal("0.2"),
        order_type="MARKET",
        status="CONFIRMED"
    )

    position_closed_event = {
        "event_type": "position_closed",
        "correlation_id": "corr-manual-001",
        "data": {
            "ticket_number": 12347,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "SELL",
            "volume": Decimal("0.2"),
            "open_price": Decimal("76.00"),
            "close_price": Decimal("75.50"),  # Manual close
            "realized_pnl": Decimal("100.00"),
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "close_time": datetime(2025, 11, 22, 10, 45, 0),
            "close_reason": "manual"
        }
    }

    # Mock repositories
    mock_position_repository.get_by_ticket_number.return_value = existing_position
    mock_order_repository.get_by_ticket_number.return_value = order
    mt4_integration_service.position_repository = mock_position_repository

    # Act
    await mt4_integration_service.handle_position_closed_event(position_closed_event)

    # Assert
    mock_position_repository.delete.assert_called_once()
    mock_order_repository.update_status.assert_called()


@pytest.mark.asyncio
async def test_multiple_positions_concurrent_updates(
    mt4_integration_service,
    mock_position_repository,
    mock_redis_client
):
    """Test handling multiple position updates concurrently."""

    # Arrange: Three positions with concurrent updates
    positions = [
        MT4Position(
            ticket_number=i,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY" if i % 2 == 0 else "SELL",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.00"),
            unrealized_pnl=Decimal("0.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )
        for i in [12345, 12346, 12347]
    ]

    # Mock: Return different position based on ticket_number
    def get_position(ticket_number):
        for pos in positions:
            if pos.ticket_number == ticket_number:
                return pos
        return None

    mock_position_repository.get_by_ticket_number.side_effect = get_position
    mt4_integration_service.position_repository = mock_position_repository

    # Create update events for all positions
    update_events = [
        {
            "event_type": "position_updated",
            "correlation_id": f"corr-{i}",
            "data": {
                "ticket_number": ticket,
                "magic_number": 100001,
                "symbol": "CrudeOIL",
                "direction": "BUY" if ticket % 2 == 0 else "SELL",
                "volume": Decimal("0.1"),
                "open_price": Decimal("75.00"),
                "current_price": Decimal("75.50"),
                "unrealized_pnl": Decimal("50.00"),
                "stop_loss": None,
                "take_profit": None,
                "open_time": datetime.now(),
                "last_updated": datetime.now()
            }
        }
        for i, ticket in enumerate([12345, 12346, 12347])
    ]

    # Act: Process all updates concurrently
    tasks = [
        mt4_integration_service.handle_position_updated_event(event)
        for event in update_events
    ]
    await asyncio.gather(*tasks)

    # Assert: All positions updated
    assert mock_position_repository.update.call_count == 3


@pytest.mark.asyncio
async def test_position_closure_without_order(
    mt4_integration_service,
    mock_order_repository,
    mock_position_repository,
    mock_redis_client
):
    """Test position closure when no order exists (manual MT4 position)."""

    # Arrange: Position opened manually in MT4 (no order record)
    existing_position = MT4Position(
        ticket_number=99999,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.00"),
        current_price=Decimal("76.00"),
        unrealized_pnl=Decimal("100.00"),
        open_time=datetime(2025, 11, 22, 10, 0, 0),
        last_updated=datetime(2025, 11, 22, 11, 0, 0)
    )

    position_closed_event = {
        "event_type": "position_closed",
        "correlation_id": "corr-manual-pos",
        "data": {
            "ticket_number": 99999,
            "magic_number": 100001,
            "symbol": "CrudeOIL",
            "direction": "BUY",
            "volume": Decimal("0.1"),
            "open_price": Decimal("75.00"),
            "close_price": Decimal("76.00"),
            "realized_pnl": Decimal("100.00"),
            "open_time": datetime(2025, 11, 22, 10, 0, 0),
            "close_time": datetime(2025, 11, 22, 11, 0, 0),
            "close_reason": "manual"
        }
    }

    # Mock: Position exists but no order
    mock_position_repository.get_by_ticket_number.return_value = existing_position
    mock_order_repository.get_by_ticket_number.return_value = None  # No order
    mt4_integration_service.position_repository = mock_position_repository

    # Act
    await mt4_integration_service.handle_position_closed_event(position_closed_event)

    # Assert: Position still deleted
    mock_position_repository.delete.assert_called_once_with(ticket_number=99999)

    # Assert: No order update attempted (order doesn't exist)
    mock_order_repository.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_position_event_metrics_recorded(
    mt4_integration_service,
    mock_position_repository,
    mock_redis_client
):
    """Test that position events record Prometheus metrics throughout lifecycle."""

    # Arrange
    position = MT4Position(
        ticket_number=12348,
        magic_number=100001,
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        open_price=Decimal("75.00"),
        current_price=Decimal("75.00"),
        unrealized_pnl=Decimal("0.00"),
        open_time=datetime.now(),
        last_updated=datetime.now()
    )

    mock_position_repository.get_by_ticket_number.return_value = position
    mt4_integration_service.position_repository = mock_position_repository

    # Mock metrics recording
    with patch('src.services.mt4_integration_service.record_position_update') as mock_update_metric, \
         patch('src.services.mt4_integration_service.record_position_closure') as mock_closure_metric:

        # Act: Position update
        update_event = {
            "event_type": "position_updated",
            "correlation_id": "corr-metrics",
            "data": {
                "ticket_number": 12348,
                "magic_number": 100001,
                "symbol": "CrudeOIL",
                "direction": "BUY",
                "volume": Decimal("0.1"),
                "open_price": Decimal("75.00"),
                "current_price": Decimal("75.50"),
                "unrealized_pnl": Decimal("50.00"),
                "stop_loss": None,
                "take_profit": None,
                "open_time": datetime.now(),
                "last_updated": datetime.now()
            }
        }

        await mt4_integration_service.handle_position_updated_event(update_event)

        # Assert: Update metric recorded
        mock_update_metric.assert_called_once()

        # Act: Position closure
        closure_event = {
            "event_type": "position_closed",
            "correlation_id": "corr-metrics-close",
            "data": {
                "ticket_number": 12348,
                "magic_number": 100001,
                "symbol": "CrudeOIL",
                "direction": "BUY",
                "volume": Decimal("0.1"),
                "open_price": Decimal("75.00"),
                "close_price": Decimal("75.50"),
                "realized_pnl": Decimal("50.00"),
                "open_time": datetime.now(),
                "close_time": datetime.now(),
                "close_reason": "manual"
            }
        }

        await mt4_integration_service.handle_position_closed_event(closure_event)

        # Assert: Closure metric recorded
        mock_closure_metric.assert_called_once()
