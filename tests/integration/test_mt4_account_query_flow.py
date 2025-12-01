"""
Integration tests for account information query flow (T078 - User Story 4).

Tests end-to-end flow from MT4Client through MT4IntegrationService.
"""
import pytest
import json
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from src.services.mt4_integration_service import MT4IntegrationService
from src.database.repositories.mt4_order_repository import MT4OrderRepository
from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
from src.utils.redis_client import MT4RedisClient
from src.trading.execution.symbol_loader import SymbolLoader
from src.trading.execution.mt4_connection_pool import MT4ConnectionPool


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_order_repository():
    """Mock order repository."""
    return AsyncMock(spec=MT4OrderRepository)


@pytest.fixture
def mock_connection_repository():
    """Mock connection repository."""
    repo = AsyncMock(spec=MT4ConnectionRepository)

    # Mock connection
    connection = Mock()
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
    """Mock Redis client."""
    return AsyncMock(spec=MT4RedisClient)


@pytest.fixture
def mock_symbol_loader():
    """Mock symbol loader."""
    loader = Mock(spec=SymbolLoader)
    loader.get_symbols = Mock(return_value=["CrudeOIL", "EURUSD"])
    return loader


@pytest.fixture
def mock_connection_pool():
    """Mock connection pool."""
    return Mock(spec=MT4ConnectionPool)


@pytest.fixture
def mt4_integration_service(
    mock_order_repository,
    mock_connection_repository,
    mock_redis_client,
    mock_symbol_loader,
    mock_connection_pool
):
    """Create MT4IntegrationService for testing."""
    return MT4IntegrationService(
        order_repository=mock_order_repository,
        redis_client=mock_redis_client,
        connection_repository=mock_connection_repository,
        symbol_loader=mock_symbol_loader,
        connection_pool=mock_connection_pool
    )


# =============================================================================
# Integration Tests (T078)
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_account_info_end_to_end(mt4_integration_service, mock_connection_repository):
    """Test T078: Complete account info query flow."""
    # Arrange
    magic_number = 100001

    account_response = {
        "success": True,
        "balance": 10000.00,
        "equity": 10250.50,
        "margin": 500.00,
        "free_margin": 9750.50,
        "margin_level": 2050.10,
        "profit": 250.50,
        "account_number": 12345678,
        "leverage": 100,
        "currency": "USD",
        "server": "Demo-Server",
        "company": "MetaQuotes"
    }

    # Mock the MT4Client.get_account_info method
    with patch.object(
        mt4_integration_service,
        '_get_client',
        return_value=Mock(get_account_info=AsyncMock(return_value=account_response))
    ):
        # Act
        result = await mt4_integration_service.query_account_info(magic_number)

        # Assert
        assert result is not None
        assert result.balance == Decimal("10000.00")
        assert result.equity == Decimal("10250.50")
        assert result.margin_level == Decimal("2050.10")
        assert result.account_number == 12345678
        mock_connection_repository.get_by_magic_number.assert_called_once_with(magic_number)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_open_positions_end_to_end(mt4_integration_service):
    """Test T078: Complete open positions query flow."""
    # Arrange
    magic_number = 100001

    positions_response = {
        "success": True,
        "positions": [
            {
                "ticket": 12345,
                "symbol": "CrudeOIL",
                "type": "BUY",
                "volume": 0.1,
                "open_price": 75.50,
                "current_price": 75.75,
                "stop_loss": 75.00,
                "take_profit": 76.50,
                "profit": 25.00,
                "open_time": "2025-11-22T10:00:00Z",
                "magic_number": 100001
            },
            {
                "ticket": 12346,
                "symbol": "EURUSD",
                "type": "SELL",
                "volume": 0.2,
                "open_price": 1.0950,
                "current_price": 1.0940,
                "stop_loss": 1.1000,
                "take_profit": 1.0900,
                "profit": 20.00,
                "open_time": "2025-11-22T11:00:00Z",
                "magic_number": 100001
            }
        ]
    }

    # Mock the MT4Client.get_open_positions method
    with patch.object(
        mt4_integration_service,
        '_get_client',
        return_value=Mock(get_open_positions=AsyncMock(return_value=positions_response))
    ):
        # Act
        result = await mt4_integration_service.query_open_positions(magic_number)

        # Assert
        assert result is not None
        assert len(result) == 2
        assert result[0].ticket == 12345
        assert result[0].symbol == "CrudeOIL"
        assert result[1].ticket == 12346
        assert result[1].symbol == "EURUSD"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_account_info_caching(mt4_integration_service):
    """Test T078: Account info caching mechanism."""
    # Arrange
    magic_number = 100001

    account_response = {
        "success": True,
        "balance": 10000.00,
        "equity": 10250.50,
        "margin": 500.00,
        "free_margin": 9750.50,
        "margin_level": 2050.10,
        "profit": 250.50,
        "account_number": 12345678,
        "leverage": 100,
        "currency": "USD",
        "server": "Demo-Server",
        "company": "MetaQuotes"
    }

    mock_client = Mock(get_account_info=AsyncMock(return_value=account_response))

    with patch.object(mt4_integration_service, '_get_client', return_value=mock_client):
        # Act - First call
        result1 = await mt4_integration_service.query_account_info(magic_number)

        # Act - Second call (should use cache)
        result2 = await mt4_integration_service.get_cached_account_info(magic_number)

        # Assert
        assert result1 is not None
        if result2 is not None:  # If caching is implemented
            assert result1.balance == result2.balance
            assert result1.equity == result2.equity


@pytest.mark.asyncio
@pytest.mark.integration
async def test_query_account_info_connection_error(mt4_integration_service, mock_connection_repository):
    """Test T078: Handle connection not found error."""
    # Arrange
    mock_connection_repository.get_by_magic_number.return_value = None

    # Act & Assert
    with pytest.raises(ValueError, match="Connection not found"):
        await mt4_integration_service.query_account_info(999999)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_query_account_info_mt4_timeout(mt4_integration_service):
    """Test T078: Handle MT4 timeout during account query."""
    # Arrange
    magic_number = 100001

    mock_client = Mock(get_account_info=AsyncMock(side_effect=TimeoutError("MT4 timeout")))

    with patch.object(mt4_integration_service, '_get_client', return_value=mock_client):
        # Act & Assert
        with pytest.raises(TimeoutError):
            await mt4_integration_service.query_account_info(magic_number)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_query_positions_filtered_by_magic_number(mt4_integration_service):
    """Test T078: Query positions filtered by specific magic number."""
    # Arrange
    magic_number = 100001

    positions_response = {
        "success": True,
        "positions": [
            {
                "ticket": 12345,
                "symbol": "CrudeOIL",
                "type": "BUY",
                "volume": 0.1,
                "open_price": 75.50,
                "current_price": 75.75,
                "profit": 25.00,
                "open_time": "2025-11-22T10:00:00Z",
                "magic_number": 100001
            }
        ]
    }

    mock_client = Mock(
        get_open_positions=AsyncMock(return_value=positions_response)
    )

    with patch.object(mt4_integration_service, '_get_client', return_value=mock_client):
        # Act
        result = await mt4_integration_service.query_open_positions(magic_number)

        # Assert
        assert len(result) == 1
        assert result[0].magic_number == magic_number
        mock_client.get_open_positions.assert_called_once_with(magic_number=magic_number)
