"""
Integration tests for end-to-end MT4 order flow.

Tests complete flow from order submission through confirmation using Mock MT4 EA.
"""
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
import uuid

from src.services.mt4_integration_service import MT4IntegrationService
from src.database.repositories.mt4_order_repository import MT4OrderRepository
from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
from src.database.models.mt4_orders import MT4Order
from src.database.models.mt4_connection import MT4Connection
from src.utils.redis_client import MT4RedisClient
from src.trading.execution.symbol_loader import SymbolLoader
from src.utils.mt4_helpers import get_mt4_logger


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def mock_mt4_ea():
    """Start Mock MT4 EA for testing."""
    from tests.integration.mock_mt4_ea import MockMT4EA

    ea = MockMT4EA(
        rep_port=15555,  # Use different ports for testing
        pub_port=15556,
        magic_number=100001
    )

    # Start EA in background
    ea_task = asyncio.create_task(ea.run())

    # Give EA time to start
    await asyncio.sleep(0.5)

    yield ea

    # Cleanup
    ea.stop()
    ea_task.cancel()
    try:
        await ea_task
    except asyncio.CancelledError:
        pass


@pytest.fixture
async def test_database_session(test_db_session):
    """Database session for testing."""
    return test_db_session


@pytest.fixture
async def order_repository(test_database_session):
    """Create MT4OrderRepository with test database."""
    return MT4OrderRepository(session=test_database_session)


@pytest.fixture
async def connection_repository(test_database_session):
    """Create MT4ConnectionRepository with test database."""
    return MT4ConnectionRepository(session=test_database_session)


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    # Use test Redis instance or mock
    client = MT4RedisClient(redis_url="redis://localhost:6379/15")  # Test DB
    await client.connect()

    yield client

    await client.disconnect()


@pytest.fixture
async def symbol_loader(mock_mt4_ea):
    """Create SymbolLoader and refresh symbols."""
    from src.trading.execution.mt4_client import MT4Client
    from src.trading.execution.mt4_encryption import MT4EncryptionManager

    loader = SymbolLoader()

    # Create temporary client to fetch symbols
    encryption_mgr = MT4EncryptionManager(encryption_enabled=False)
    client = MT4Client(
        host="localhost",
        rep_port=15555,
        pub_port=15556,
        magic_number=100001,
        encryption_manager=encryption_mgr
    )

    await client.connect()
    await loader.refresh_symbols(client)
    await client.disconnect()

    return loader


@pytest.fixture
async def test_connection(connection_repository):
    """Create test MT4 connection in database."""
    connection = MT4Connection(
        id=uuid.uuid4(),
        ea_id="test_ea_100001",
        magic_number=100001,
        rep_port=15555,
        pub_port=15556,
        symbol="CrudeOIL",
        status="ACTIVE",
        mt4_server_host="localhost",
        encryption_enabled=False,
        last_heartbeat=datetime.utcnow()
    )

    await connection_repository.create(connection)
    return connection


@pytest.fixture
async def integration_service(
    order_repository,
    connection_repository,
    redis_client,
    symbol_loader,
    test_connection
):
    """Create MT4IntegrationService for testing."""
    logger = get_mt4_logger("test")

    service = MT4IntegrationService(
        order_repository=order_repository,
        redis_client=redis_client,
        connection_repository=connection_repository,
        symbol_loader=symbol_loader,
        logger=logger
    )

    yield service

    # Cleanup - disconnect all clients
    for client in service._clients.values():
        await client.disconnect()


# =============================================================================
# End-to-End Order Flow Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_order_full_flow(
    integration_service,
    order_repository,
    redis_client,
    mock_mt4_ea
):
    """Test complete order submission and confirmation flow."""
    # Act - Submit market order
    order = await integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Assert - Order created in database
    assert order is not None
    assert order.order_id is not None
    assert order.magic_number == 100001
    assert order.symbol == "CrudeOIL"
    assert order.direction == "BUY"
    assert order.volume == Decimal("0.1")
    assert order.status in ["PENDING", "CONFIRMED"]

    # Wait for confirmation event
    await asyncio.sleep(0.5)

    # Verify order was confirmed
    confirmed_order = await order_repository.get_by_order_id(order.order_id)
    assert confirmed_order is not None
    assert confirmed_order.ticket_number is not None
    assert confirmed_order.status == "CONFIRMED"
    assert confirmed_order.execution_price is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_order_with_sl_tp(
    integration_service,
    order_repository,
    mock_mt4_ea
):
    """Test order submission with stop loss and take profit."""
    # Act
    order = await integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001,
        stop_loss=Decimal("74.00"),
        take_profit=Decimal("77.00")
    )

    # Assert
    assert order.stop_loss == Decimal("74.00")
    assert order.take_profit == Decimal("77.00")

    # Wait for confirmation
    await asyncio.sleep(0.5)

    # Verify in mock EA
    confirmed_order = await order_repository.get_by_order_id(order.order_id)
    assert confirmed_order.status == "CONFIRMED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_multiple_orders(
    integration_service,
    order_repository,
    mock_mt4_ea
):
    """Test submitting multiple orders in sequence."""
    # Act - Submit 3 orders
    orders = []
    for i in range(3):
        order = await integration_service.submit_market_order(
            symbol="CrudeOIL",
            direction="BUY" if i % 2 == 0 else "SELL",
            volume=Decimal("0.1"),
            magic_number=100001
        )
        orders.append(order)

    # Assert - All orders created
    assert len(orders) == 3
    assert all(order.status in ["PENDING", "CONFIRMED"] for order in orders)

    # Wait for confirmations
    await asyncio.sleep(1.0)

    # Verify all confirmed
    for order in orders:
        confirmed = await order_repository.get_by_order_id(order.order_id)
        assert confirmed.status == "CONFIRMED"
        assert confirmed.ticket_number is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_order_different_symbols(
    integration_service,
    order_repository,
    mock_mt4_ea
):
    """Test submitting orders for different symbols."""
    # Act
    symbols = ["CrudeOIL", "EURUSD", "GOLD"]
    orders = []

    for symbol in symbols:
        order = await integration_service.submit_market_order(
            symbol=symbol,
            direction="BUY",
            volume=Decimal("0.1"),
            magic_number=100001
        )
        orders.append(order)

    # Assert
    assert len(orders) == 3
    assert [o.symbol for o in orders] == symbols

    # Wait for confirmations
    await asyncio.sleep(1.0)

    # Verify all confirmed
    for order in orders:
        confirmed = await order_repository.get_by_order_id(order.order_id)
        assert confirmed.status == "CONFIRMED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_rejection_flow(
    integration_service,
    order_repository,
    redis_client,
    mock_mt4_ea
):
    """Test order rejection handling."""
    # Configure mock EA to reject next order
    mock_mt4_ea.should_reject_next = True
    mock_mt4_ea.rejection_error_code = 134
    mock_mt4_ea.rejection_error_message = "Not enough margin"

    # Act
    order = await integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("100.0"),  # Large volume to trigger rejection
        magic_number=100001
    )

    # Wait for rejection event
    await asyncio.sleep(0.5)

    # Assert - Order rejected
    rejected_order = await order_repository.get_by_order_id(order.order_id)
    assert rejected_order.status == "REJECTED"
    assert rejected_order.error_message == "Not enough margin"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_latency_measurement(
    integration_service,
    order_repository,
    mock_mt4_ea
):
    """Test that order latency is measured and recorded."""
    # Act
    order = await integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Wait for confirmation
    await asyncio.sleep(0.5)

    # Assert
    confirmed_order = await order_repository.get_by_order_id(order.order_id)
    assert confirmed_order.status == "CONFIRMED"
    assert confirmed_order.confirmed_at is not None

    # Calculate latency
    latency_ms = confirmed_order.calculate_latency_ms()
    assert latency_ms is not None
    assert latency_ms > 0
    assert latency_ms < 5000  # Should be less than 5 seconds


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_event_published(
    integration_service,
    redis_client,
    mock_mt4_ea
):
    """Test that order events are published to Redis."""
    # Setup Redis subscriber
    events_received = []

    async def event_handler(event):
        events_received.append(event)

    await redis_client.subscribe(
        channel="mt4:events:order_confirmed",
        handler=event_handler
    )

    # Act
    order = await integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    # Wait for event
    await asyncio.sleep(1.0)

    # Assert
    assert len(events_received) > 0
    event = events_received[0]
    assert event["event_type"] == "order_confirmed"
    assert event["data"]["order_id"] == order.order_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_symbol_rejection(
    integration_service,
    symbol_loader
):
    """Test that invalid symbols are rejected before sending to MT4."""
    # Act & Assert
    with pytest.raises(ValueError, match="Invalid symbol"):
        await integration_service.submit_market_order(
            symbol="INVALIDSYMBOL",
            direction="BUY",
            volume=Decimal("0.1"),
            magic_number=100001
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connection_not_found(integration_service):
    """Test error when EA connection not found."""
    # Act & Assert
    with pytest.raises(ValueError, match="Connection not found"):
        await integration_service.submit_market_order(
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            magic_number=999999  # Non-existent
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_orders(
    integration_service,
    order_repository,
    mock_mt4_ea
):
    """Test submitting multiple orders concurrently."""
    # Act - Submit 5 orders concurrently
    tasks = [
        integration_service.submit_market_order(
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            magic_number=100001
        )
        for _ in range(5)
    ]

    orders = await asyncio.gather(*tasks)

    # Assert
    assert len(orders) == 5
    assert all(order.status in ["PENDING", "CONFIRMED"] for order in orders)

    # Wait for confirmations
    await asyncio.sleep(1.5)

    # Verify all confirmed
    for order in orders:
        confirmed = await order_repository.get_by_order_id(order.order_id)
        assert confirmed.status == "CONFIRMED"


# =============================================================================
# Performance Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_order_submission_performance(
    integration_service,
    mock_mt4_ea
):
    """Test order submission meets performance target (<500ms)."""
    # Act
    start_time = datetime.utcnow()

    order = await integration_service.submit_market_order(
        symbol="CrudeOIL",
        direction="BUY",
        volume=Decimal("0.1"),
        magic_number=100001
    )

    end_time = datetime.utcnow()

    # Assert - Submission should be fast
    submission_time_ms = (end_time - start_time).total_seconds() * 1000
    assert submission_time_ms < 500  # Target: <500ms

    # Wait for confirmation
    await asyncio.sleep(0.5)

    # Total latency (submission + confirmation)
    confirmed_order = await order_repository.get_by_order_id(order.order_id)
    total_latency = confirmed_order.calculate_latency_ms()

    # Should meet target
    assert total_latency < 5000  # Conservative target for integration test
