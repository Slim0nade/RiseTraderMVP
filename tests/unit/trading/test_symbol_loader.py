"""
Unit tests for SymbolLoader.

Tests dynamic symbol loading from MT4 and validation logic.
"""
import pytest
from unittest.mock import AsyncMock, Mock
from decimal import Decimal

from src.trading.execution.symbol_loader import SymbolLoader
from src.trading.execution.mt4_client import MT4Client


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_mt4_client():
    """Mock MT4Client for testing."""
    client = AsyncMock(spec=MT4Client)
    client.get_symbols = AsyncMock(return_value=["CrudeOIL", "EURUSD", "GBPUSD", "GOLD"])
    return client


@pytest.fixture
def symbol_loader():
    """Create SymbolLoader instance."""
    return SymbolLoader()


# =============================================================================
# Symbol Loading Tests
# =============================================================================

@pytest.mark.asyncio
async def test_refresh_symbols_success(symbol_loader, mock_mt4_client):
    """Test successful symbol refresh from MT4."""
    # Act
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Assert
    symbols = symbol_loader.get_symbols()
    assert len(symbols) == 4
    assert "CrudeOIL" in symbols
    assert "EURUSD" in symbols
    assert "GBPUSD" in symbols
    assert "GOLD" in symbols
    mock_mt4_client.get_symbols.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_symbols_empty_list(symbol_loader, mock_mt4_client):
    """Test handling of empty symbol list from MT4."""
    # Arrange
    mock_mt4_client.get_symbols.return_value = []

    # Act
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Assert
    symbols = symbol_loader.get_symbols()
    assert len(symbols) == 0


@pytest.mark.asyncio
async def test_refresh_symbols_updates_cache(symbol_loader, mock_mt4_client):
    """Test that refresh updates the cached symbol list."""
    # Arrange
    await symbol_loader.refresh_symbols(mock_mt4_client)
    assert len(symbol_loader.get_symbols()) == 4

    # Update mock to return different symbols
    mock_mt4_client.get_symbols.return_value = ["BTCUSD", "ETHUSD"]

    # Act
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Assert
    symbols = symbol_loader.get_symbols()
    assert len(symbols) == 2
    assert "BTCUSD" in symbols
    assert "ETHUSD" in symbols
    assert "CrudeOIL" not in symbols


# =============================================================================
# Symbol Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_is_valid_symbol_true(symbol_loader, mock_mt4_client):
    """Test validation returns True for valid symbol."""
    # Arrange
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Act & Assert
    assert symbol_loader.is_valid_symbol("CrudeOIL") is True
    assert symbol_loader.is_valid_symbol("EURUSD") is True
    assert symbol_loader.is_valid_symbol("GOLD") is True


@pytest.mark.asyncio
async def test_is_valid_symbol_false(symbol_loader, mock_mt4_client):
    """Test validation returns False for invalid symbol."""
    # Arrange
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Act & Assert
    assert symbol_loader.is_valid_symbol("INVALID") is False
    assert symbol_loader.is_valid_symbol("BTCUSD") is False
    assert symbol_loader.is_valid_symbol("") is False


@pytest.mark.asyncio
async def test_is_valid_symbol_case_sensitive(symbol_loader, mock_mt4_client):
    """Test symbol validation is case-sensitive."""
    # Arrange
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Act & Assert
    assert symbol_loader.is_valid_symbol("CrudeOIL") is True
    assert symbol_loader.is_valid_symbol("crudeoil") is False
    assert symbol_loader.is_valid_symbol("CRUDEOIL") is False


def test_is_valid_symbol_before_refresh(symbol_loader):
    """Test validation before symbols are loaded returns False."""
    # Act & Assert
    assert symbol_loader.is_valid_symbol("CrudeOIL") is False
    assert symbol_loader.is_valid_symbol("EURUSD") is False


# =============================================================================
# Volume Validation Tests
# =============================================================================

def test_validate_volume_positive(symbol_loader):
    """Test volume must be positive."""
    # Valid volumes
    symbol_loader.validate_volume(Decimal("0.01"))
    symbol_loader.validate_volume(Decimal("0.1"))
    symbol_loader.validate_volume(Decimal("1.0"))
    symbol_loader.validate_volume(Decimal("10.0"))

    # Invalid volumes
    with pytest.raises(ValueError, match="Volume must be positive"):
        symbol_loader.validate_volume(Decimal("0.0"))

    with pytest.raises(ValueError, match="Volume must be positive"):
        symbol_loader.validate_volume(Decimal("-1.0"))

    with pytest.raises(ValueError, match="Volume must be positive"):
        symbol_loader.validate_volume(Decimal("-0.1"))


def test_validate_volume_too_small(symbol_loader):
    """Test volume validation for too-small values."""
    # Arrange - Very small volume
    very_small = Decimal("0.0001")

    # Act & Assert
    with pytest.raises(ValueError, match="Volume too small"):
        symbol_loader.validate_volume(very_small)


def test_validate_volume_too_large(symbol_loader):
    """Test volume validation for too-large values."""
    # Arrange - Very large volume
    very_large = Decimal("1000.0")

    # Act & Assert
    with pytest.raises(ValueError, match="Volume too large"):
        symbol_loader.validate_volume(very_large)


def test_validate_volume_within_limits(symbol_loader):
    """Test volume validation for acceptable range."""
    # Valid volumes within typical range (0.01 - 100.0)
    symbol_loader.validate_volume(Decimal("0.01"))
    symbol_loader.validate_volume(Decimal("0.1"))
    symbol_loader.validate_volume(Decimal("1.0"))
    symbol_loader.validate_volume(Decimal("5.0"))
    symbol_loader.validate_volume(Decimal("10.0"))
    symbol_loader.validate_volume(Decimal("50.0"))
    symbol_loader.validate_volume(Decimal("100.0"))


# =============================================================================
# Direction Validation Tests
# =============================================================================

def test_validate_direction_valid(symbol_loader):
    """Test direction validation for valid values."""
    # Valid directions
    symbol_loader.validate_direction("BUY")
    symbol_loader.validate_direction("SELL")


def test_validate_direction_invalid(symbol_loader):
    """Test direction validation for invalid values."""
    # Invalid directions
    with pytest.raises(ValueError, match="Direction must be BUY or SELL"):
        symbol_loader.validate_direction("HOLD")

    with pytest.raises(ValueError, match="Direction must be BUY or SELL"):
        symbol_loader.validate_direction("buy")

    with pytest.raises(ValueError, match="Direction must be BUY or SELL"):
        symbol_loader.validate_direction("")

    with pytest.raises(ValueError, match="Direction must be BUY or SELL"):
        symbol_loader.validate_direction("LONG")


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_refresh(symbol_loader, mock_mt4_client):
    """Test concurrent symbol refresh calls."""
    # Act - Multiple concurrent refreshes
    import asyncio
    await asyncio.gather(
        symbol_loader.refresh_symbols(mock_mt4_client),
        symbol_loader.refresh_symbols(mock_mt4_client),
        symbol_loader.refresh_symbols(mock_mt4_client)
    )

    # Assert - Should have final state
    symbols = symbol_loader.get_symbols()
    assert len(symbols) == 4


@pytest.mark.asyncio
async def test_refresh_symbols_with_duplicates(symbol_loader, mock_mt4_client):
    """Test handling of duplicate symbols in MT4 response."""
    # Arrange
    mock_mt4_client.get_symbols.return_value = [
        "CrudeOIL", "EURUSD", "CrudeOIL", "GOLD", "EURUSD"
    ]

    # Act
    await symbol_loader.refresh_symbols(mock_mt4_client)

    # Assert - Duplicates should be handled
    symbols = symbol_loader.get_symbols()
    assert symbols.count("CrudeOIL") <= 1
    assert symbols.count("EURUSD") <= 1


@pytest.mark.asyncio
async def test_refresh_symbols_connection_error(symbol_loader, mock_mt4_client):
    """Test handling of connection error during refresh."""
    # Arrange
    mock_mt4_client.get_symbols.side_effect = ConnectionError("Connection lost")

    # Act & Assert
    with pytest.raises(ConnectionError):
        await symbol_loader.refresh_symbols(mock_mt4_client)


def test_get_symbols_returns_copy(symbol_loader, mock_mt4_client):
    """Test that get_symbols returns a copy, not the internal list."""
    # Arrange
    import asyncio
    asyncio.run(symbol_loader.refresh_symbols(mock_mt4_client))

    # Act
    symbols1 = symbol_loader.get_symbols()
    symbols2 = symbol_loader.get_symbols()

    # Modify one list
    symbols1.append("NEWSY MBOL")

    # Assert - Other list should be unaffected
    assert "NEWSYMBOL" not in symbols2
    assert "NEWSYMBOL" not in symbol_loader.get_symbols()
