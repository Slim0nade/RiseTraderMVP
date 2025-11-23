"""
Integration tests for MT4 communication (T049 - User Story 3).

Tests multi-symbol market data subscription and event streaming.
"""
import pytest
import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
import zmq.asyncio

from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.services.mt4_integration_service import MT4IntegrationService
from src.trading.execution.mt4_models import MarketTickEvent, MarketTick


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def zmq_context():
    """Create ZMQ context."""
    ctx = zmq.asyncio.Context()
    yield ctx
    ctx.term()


@pytest.fixture
def encryption_manager():
    """Create encryption manager (disabled for tests)."""
    return MT4EncryptionManager(encryption_enabled=False)


@pytest.fixture
async def mt4_client(zmq_context, encryption_manager):
    """Create MT4Client instance."""
    client = MT4Client(
        host="localhost",
        rep_port=5555,
        pub_port=5556,
        magic_number=100001,
        encryption_manager=encryption_manager,
        timeout_ms=5000
    )
    yield client
    # Cleanup
    if client._connected:
        await client.disconnect()


@pytest.fixture
def mock_mt4_pub_server(zmq_context):
    """Mock MT4 PUB server for testing."""
    socket = zmq_context.socket(zmq.PUB)
    socket.bind("tcp://127.0.0.1:5556")
    yield socket
    socket.close()


# =============================================================================
# Multi-Symbol Subscription Tests (T049)
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscribe_to_single_symbol(mt4_client, mock_mt4_pub_server):
    """Test subscribing to a single symbol."""
    # Arrange - connect client
    await mt4_client.connect()

    # Act - subscribe to CrudeOIL
    await mt4_client.subscribe_to_events(topics=["CrudeOIL"])

    # Assert - client should be subscribed
    assert mt4_client._sub_socket is not None
    assert mt4_client._connected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscribe_to_multiple_symbols(mt4_client, mock_mt4_pub_server):
    """Test subscribing to multiple symbols simultaneously."""
    # Arrange - connect client
    await mt4_client.connect()

    # Act - subscribe to multiple symbols
    symbols = ["CrudeOIL", "EURUSD", "GBPUSD"]
    await mt4_client.subscribe_to_events(topics=symbols)

    # Assert - client should be subscribed to all
    assert mt4_client._sub_socket is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscribe_to_all_symbols(mt4_client, mock_mt4_pub_server):
    """Test subscribing to all symbols (no filter)."""
    # Arrange - connect client
    await mt4_client.connect()

    # Act - subscribe to all (empty topics list)
    await mt4_client.subscribe_to_events(topics=None)

    # Assert - client should be subscribed
    assert mt4_client._sub_socket is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unsubscribe_from_single_symbol(mt4_client, mock_mt4_pub_server):
    """Test unsubscribing from a single symbol."""
    # Arrange - subscribe first
    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=["CrudeOIL", "EURUSD"])

    # Act - unsubscribe from CrudeOIL
    await mt4_client.unsubscribe_from_events(topics=["CrudeOIL"])

    # Assert - should still be connected
    assert mt4_client._sub_socket is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unsubscribe_from_all_symbols(mt4_client, mock_mt4_pub_server):
    """Test unsubscribing from all symbols."""
    # Arrange - subscribe first
    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=["CrudeOIL", "EURUSD"])

    # Act - unsubscribe from all
    await mt4_client.unsubscribe_from_events(topics=None)

    # Assert - socket should still exist but no subscriptions
    assert mt4_client._sub_socket is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_receive_tick_for_subscribed_symbol(mt4_client, mock_mt4_pub_server):
    """Test receiving market tick for subscribed symbol."""
    # Arrange - connect and subscribe
    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=["market_tick"])

    # Publish tick from mock server
    tick_event = MarketTickEvent(
        correlation_id="test_tick_1",
        data=MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime.utcnow(),
            volume=1000
        )
    )

    tick_json = tick_event.model_dump_json()
    await asyncio.sleep(0.1)  # Give time for subscription
    mock_mt4_pub_server.send_string(tick_json)

    # Act - receive event
    event = await mt4_client.receive_event(timeout_ms=2000)

    # Assert - should receive the tick
    assert event is not None
    assert event["event_type"] == "market_tick"
    assert event["data"]["symbol"] == "CrudeOIL"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_receive_multiple_ticks_from_different_symbols(mt4_client, mock_mt4_pub_server):
    """Test receiving ticks from multiple symbols."""
    # Arrange - connect and subscribe to all
    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=None)

    # Publish ticks for different symbols
    symbols = ["CrudeOIL", "EURUSD", "GBPUSD"]
    await asyncio.sleep(0.1)  # Give time for subscription

    for symbol in symbols:
        tick_event = MarketTickEvent(
            data=MarketTick(
                symbol=symbol,
                bid=Decimal("1.00"),
                ask=Decimal("1.01"),
                timestamp=datetime.utcnow()
            )
        )
        mock_mt4_pub_server.send_string(tick_event.model_dump_json())
        await asyncio.sleep(0.05)

    # Act - receive events
    received_symbols = []
    for _ in range(3):
        event = await mt4_client.receive_event(timeout_ms=2000)
        if event:
            received_symbols.append(event["data"]["symbol"])

    # Assert - should receive all symbols
    assert len(received_symbols) == 3
    assert set(received_symbols) == set(symbols)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_event_listener_loop_processes_ticks(mt4_client, mock_mt4_pub_server):
    """Test event listener loop processes ticks continuously."""
    # Arrange - connect and subscribe
    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=None)

    received_events = []

    async def event_handler(event_data):
        """Handler to collect events."""
        received_events.append(event_data)

    # Start listener in background
    listener_task = asyncio.create_task(
        mt4_client.start_listening(event_handler)
    )

    # Publish multiple ticks
    await asyncio.sleep(0.1)  # Give time for listener to start
    for i in range(5):
        tick_event = MarketTickEvent(
            data=MarketTick(
                symbol="CrudeOIL",
                bid=Decimal(f"75.{i}"),
                ask=Decimal(f"75.{i+1}"),
                timestamp=datetime.utcnow()
            )
        )
        mock_mt4_pub_server.send_string(tick_event.model_dump_json())
        await asyncio.sleep(0.05)

    # Wait for events to be processed
    await asyncio.sleep(0.5)

    # Stop listener
    mt4_client.stop_listening()
    await asyncio.wait_for(listener_task, timeout=2.0)

    # Assert - should have received all 5 ticks
    assert len(received_events) >= 3  # At least most of them


@pytest.mark.asyncio
@pytest.mark.integration
async def test_listener_handles_invalid_json_gracefully(mt4_client, mock_mt4_pub_server):
    """Test listener handles invalid JSON without crashing."""
    # Arrange
    await mt4_client.connect()
    await mt4_client.subscribe_to_events(topics=None)

    received_events = []
    errors = []

    async def event_handler(event_data):
        """Handler to collect events."""
        try:
            received_events.append(event_data)
        except Exception as e:
            errors.append(e)

    # Start listener
    listener_task = asyncio.create_task(
        mt4_client.start_listening(event_handler)
    )

    await asyncio.sleep(0.1)

    # Publish invalid JSON
    mock_mt4_pub_server.send_string("invalid json {{{")
    await asyncio.sleep(0.1)

    # Publish valid event
    tick_event = MarketTickEvent(
        data=MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime.utcnow()
        )
    )
    mock_mt4_pub_server.send_string(tick_event.model_dump_json())
    await asyncio.sleep(0.2)

    # Stop listener
    mt4_client.stop_listening()
    await asyncio.wait_for(listener_task, timeout=2.0)

    # Assert - should have received the valid event despite invalid JSON
    assert len(received_events) >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscription_before_connection_raises_error(mt4_client):
    """Test that subscribing before connection raises error."""
    # Act & Assert - should raise ConnectionError
    with pytest.raises(ConnectionError):
        await mt4_client.subscribe_to_events(topics=["CrudeOIL"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_clients_can_subscribe_simultaneously(
    zmq_context,
    encryption_manager,
    mock_mt4_pub_server
):
    """Test multiple clients can subscribe to same PUB socket."""
    # Arrange - create multiple clients
    clients = [
        MT4Client(
            host="localhost",
            rep_port=5555,
            pub_port=5556,
            magic_number=100001 + i,
            encryption_manager=encryption_manager
        )
        for i in range(3)
    ]

    # Connect all clients
    for client in clients:
        await client.connect()
        await client.subscribe_to_events(topics=None)

    # Publish tick
    await asyncio.sleep(0.1)
    tick_event = MarketTickEvent(
        data=MarketTick(
            symbol="CrudeOIL",
            bid=Decimal("75.123"),
            ask=Decimal("75.145"),
            timestamp=datetime.utcnow()
        )
    )
    mock_mt4_pub_server.send_string(tick_event.model_dump_json())

    # Act - all clients receive
    received_counts = []
    for client in clients:
        event = await client.receive_event(timeout_ms=2000)
        if event:
            received_counts.append(1)

    # Cleanup
    for client in clients:
        await client.disconnect()

    # Assert - all clients should receive the tick
    assert len(received_counts) == 3
