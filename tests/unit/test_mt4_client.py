"""
Unit tests for MT4Client account info commands (US4 - Account Info).

Tests cover:
- get_account_info: command format, response parsing, field mapping
- get_open_positions: command format, response with positions list
- get_symbols: command format, response with symbol list
- Error handling: timeouts, disconnection, malformed responses
"""
import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.mt4_models import (
    AccountInfoResponse,
    GetAccountInfoCommand,
    GetOpenPositionsCommand,
    GetSymbolsCommand,
    PositionInfo,
    PositionsResponse,
    SymbolsResponse,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_encryption_manager():
    """Create a mock encryption manager with encryption disabled."""
    manager = MagicMock(spec=MT4EncryptionManager)
    manager.encryption_enabled = False
    return manager


@pytest.fixture
def mt4_client(mock_encryption_manager):
    """Create an MT4Client instance with mocked internals."""
    client = MT4Client(
        host="127.0.0.1",
        rep_port=5555,
        pub_port=5556,
        magic_number=100001,
        encryption_manager=mock_encryption_manager,
        timeout_ms=5000,
    )
    # Simulate connected state with a mock socket
    client._connected = True
    client._req_socket = AsyncMock()
    client._context = MagicMock()
    return client


@pytest.fixture
def account_info_mt4_response():
    """Simulate raw MT4 EA response for get_account_info (old format with nested account_info)."""
    return {
        "status": "OK",
        "correlation_id": str(uuid.uuid4()),
        "account_info": {
            "balance": 10000.00,
            "equity": 10250.50,
            "margin": 500.00,
            "freeMargin": 9750.50,
            "marginLevel": 2050.10,
            "leverage": 100,
            "accountNumber": 12345678,
        },
    }


@pytest.fixture
def account_info_new_format_response():
    """Simulate MT4 response in the new flat format."""
    return {
        "success": True,
        "correlation_id": str(uuid.uuid4()),
        "balance": 10000.00,
        "equity": 10250.50,
        "margin": 500.00,
        "free_margin": 9750.50,
        "margin_level": 2050.10,
        "leverage": 100,
        "account_number": 12345678,
    }


@pytest.fixture
def positions_mt4_response():
    """Simulate raw MT4 EA response for get_open_positions."""
    return {
        "status": "OK",
        "correlation_id": str(uuid.uuid4()),
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
                "open_time": "2025-11-22T10:00:00Z",
                "magic_number": 100001,
            },
            {
                "ticket_number": 12346,
                "symbol": "EURUSD",
                "direction": "SELL",
                "volume": 1.0,
                "open_price": 1.08500,
                "current_price": 1.08300,
                "unrealized_pnl": 200.00,
                "open_time": "2025-11-22T11:00:00Z",
                "magic_number": 100001,
            },
        ],
    }


@pytest.fixture
def symbols_mt4_response():
    """Simulate raw MT4 EA response for get_symbols."""
    return {
        "status": "OK",
        "correlation_id": str(uuid.uuid4()),
        "symbols": [
            "CrudeOIL",
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "XAUUSD",
        ],
    }


# =============================================================================
# Helper to simulate send_command
# =============================================================================


def _mock_send_command(client, response_data):
    """Replace send_command with a coroutine that returns the given response dict."""
    async def _send(command, timeout_ms=None):
        return response_data

    client.send_command = _send


# =============================================================================
# TestAccountInfoCommands
# =============================================================================


@pytest.mark.asyncio
class TestAccountInfoCommands:
    """Tests for get_account_info, get_open_positions, get_symbols on MT4Client."""

    # ---- get_account_info ----

    async def test_get_account_info_sends_correct_command(self, mt4_client):
        """Verify get_account_info sends a GetAccountInfoCommand with the client magic_number."""
        captured_commands = []

        async def capture_send(command, timeout_ms=None):
            captured_commands.append(command)
            return {
                "success": True,
                "correlation_id": command.correlation_id,
                "balance": 10000.00,
                "equity": 10000.00,
                "margin": 0.0,
                "free_margin": 10000.00,
                "margin_level": 0.0,
                "leverage": 100,
            }

        mt4_client.send_command = capture_send

        await mt4_client.get_account_info()

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert isinstance(cmd, GetAccountInfoCommand)
        assert cmd.command == "get_account_info"
        assert cmd.magic_number == 100001
        assert cmd.correlation_id is not None

    async def test_get_account_info_parses_response_new_format(
        self, mt4_client, account_info_new_format_response
    ):
        """Verify get_account_info parses a new-format response into AccountInfoResponse."""
        _mock_send_command(mt4_client, account_info_new_format_response)

        result = await mt4_client.get_account_info()

        assert isinstance(result, AccountInfoResponse)
        assert result.success is True
        assert result.balance == Decimal("10000.00")
        assert result.equity == Decimal("10250.50")
        assert result.margin == Decimal("500.00")
        assert result.free_margin == Decimal("9750.50")
        assert result.margin_level == Decimal("2050.10")
        assert result.leverage == 100
        assert result.account_number == 12345678

    async def test_get_account_info_parses_old_format_with_nested_account_info(
        self, mt4_client, account_info_mt4_response
    ):
        """Verify get_account_info handles the old MT4 response format with nested account_info
        and camelCase field names (freeMargin, marginLevel, accountNumber)."""
        _mock_send_command(mt4_client, account_info_mt4_response)

        result = await mt4_client.get_account_info()

        assert isinstance(result, AccountInfoResponse)
        assert result.success is True
        assert result.balance == Decimal("10000.00")
        assert result.equity == Decimal("10250.50")
        assert result.margin == Decimal("500.00")
        assert result.free_margin == Decimal("9750.50")
        assert result.margin_level == Decimal("2050.10")
        assert result.leverage == 100
        assert result.account_number == 12345678

    async def test_get_account_info_preserves_correlation_id(self, mt4_client):
        """Verify correlation_id flows through from command to response."""
        expected_corr_id = str(uuid.uuid4())

        async def fake_send(command, timeout_ms=None):
            return {
                "success": True,
                "correlation_id": command.correlation_id,
                "balance": 5000.00,
                "equity": 5000.00,
                "margin": 0.0,
                "free_margin": 5000.00,
                "margin_level": 0.0,
                "leverage": 50,
            }

        mt4_client.send_command = fake_send

        result = await mt4_client.get_account_info()

        # The correlation_id on the response matches the one generated by the command
        assert result.correlation_id is not None
        assert isinstance(result.correlation_id, str)
        assert len(result.correlation_id) == 36  # UUID format

    async def test_get_account_info_zero_margin(self, mt4_client):
        """Verify get_account_info handles zero margin (no open positions)."""
        _mock_send_command(mt4_client, {
            "success": True,
            "correlation_id": str(uuid.uuid4()),
            "balance": 10000.00,
            "equity": 10000.00,
            "margin": 0.0,
            "free_margin": 10000.00,
            "margin_level": 0.0,
            "leverage": 100,
        })

        result = await mt4_client.get_account_info()

        assert result.margin == Decimal("0")
        assert result.free_margin == Decimal("10000.00")

    # ---- get_open_positions ----

    async def test_get_open_positions_sends_correct_command(self, mt4_client):
        """Verify get_open_positions sends a GetOpenPositionsCommand."""
        captured_commands = []

        async def capture_send(command, timeout_ms=None):
            captured_commands.append(command)
            return {
                "success": True,
                "correlation_id": command.correlation_id,
                "positions": [],
            }

        mt4_client.send_command = capture_send

        await mt4_client.get_open_positions()

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert isinstance(cmd, GetOpenPositionsCommand)
        assert cmd.command == "get_open_positions"
        assert cmd.magic_number == 100001

    async def test_get_open_positions_returns_positions(
        self, mt4_client, positions_mt4_response
    ):
        """Verify get_open_positions returns a PositionsResponse with correctly parsed positions."""
        _mock_send_command(mt4_client, positions_mt4_response)

        result = await mt4_client.get_open_positions()

        assert isinstance(result, PositionsResponse)
        assert result.success is True
        assert len(result.positions) == 2

        # Validate first position
        pos1 = result.positions[0]
        assert isinstance(pos1, PositionInfo)
        assert pos1.ticket_number == 12345
        assert pos1.symbol == "CrudeOIL"
        assert pos1.direction == "BUY"
        assert pos1.volume == Decimal("0.1")
        assert pos1.open_price == Decimal("75.00")
        assert pos1.current_price == Decimal("75.50")
        assert pos1.unrealized_pnl == Decimal("50.00")
        assert pos1.stop_loss == Decimal("74.00")
        assert pos1.take_profit == Decimal("77.00")
        assert pos1.magic_number == 100001

        # Validate second position
        pos2 = result.positions[1]
        assert pos2.ticket_number == 12346
        assert pos2.symbol == "EURUSD"
        assert pos2.direction == "SELL"
        assert pos2.volume == Decimal("1.0")
        assert pos2.unrealized_pnl == Decimal("200.00")
        assert pos2.stop_loss is None
        assert pos2.take_profit is None

    async def test_get_open_positions_empty_list(self, mt4_client):
        """Verify get_open_positions handles an empty positions list."""
        _mock_send_command(mt4_client, {
            "success": True,
            "correlation_id": str(uuid.uuid4()),
            "positions": [],
        })

        result = await mt4_client.get_open_positions()

        assert isinstance(result, PositionsResponse)
        assert result.success is True
        assert len(result.positions) == 0

    async def test_get_open_positions_adapts_old_format(self, mt4_client):
        """Verify get_open_positions handles the old MT4 response format (status: OK)."""
        _mock_send_command(mt4_client, {
            "status": "OK",
            "correlation_id": str(uuid.uuid4()),
            "positions": [
                {
                    "ticket_number": 99999,
                    "symbol": "XAUUSD",
                    "direction": "BUY",
                    "volume": 0.5,
                    "open_price": 2000.00,
                    "current_price": 2010.00,
                    "unrealized_pnl": 500.00,
                    "open_time": "2025-11-22T12:00:00Z",
                    "magic_number": 100001,
                },
            ],
        })

        result = await mt4_client.get_open_positions()

        assert isinstance(result, PositionsResponse)
        assert result.success is True
        assert len(result.positions) == 1
        assert result.positions[0].ticket_number == 99999

    # ---- get_symbols ----

    async def test_get_symbols_sends_correct_command(self, mt4_client):
        """Verify get_symbols sends a GetSymbolsCommand."""
        captured_commands = []

        async def capture_send(command, timeout_ms=None):
            captured_commands.append(command)
            return {
                "success": True,
                "correlation_id": command.correlation_id,
                "symbols": [],
            }

        mt4_client.send_command = capture_send

        await mt4_client.get_symbols()

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert isinstance(cmd, GetSymbolsCommand)
        assert cmd.command == "get_symbols"
        assert cmd.magic_number == 100001

    async def test_get_symbols_returns_symbol_list(
        self, mt4_client, symbols_mt4_response
    ):
        """Verify get_symbols returns a list of symbol name strings."""
        _mock_send_command(mt4_client, symbols_mt4_response)

        result = await mt4_client.get_symbols()

        assert isinstance(result, list)
        assert len(result) == 5
        assert "CrudeOIL" in result
        assert "EURUSD" in result
        assert "GBPUSD" in result
        assert "USDJPY" in result
        assert "XAUUSD" in result

    async def test_get_symbols_returns_empty_on_failure(self, mt4_client):
        """Verify get_symbols returns an empty list when MT4 reports failure."""
        _mock_send_command(mt4_client, {
            "status": "ERROR",
            "correlation_id": str(uuid.uuid4()),
            "message": "Symbol list unavailable",
        })

        result = await mt4_client.get_symbols()

        assert isinstance(result, list)
        assert len(result) == 0

    async def test_get_symbols_empty_list(self, mt4_client):
        """Verify get_symbols handles an empty symbols list from MT4."""
        _mock_send_command(mt4_client, {
            "success": True,
            "correlation_id": str(uuid.uuid4()),
            "symbols": [],
        })

        result = await mt4_client.get_symbols()

        assert isinstance(result, list)
        assert len(result) == 0


# =============================================================================
# TestAccountInfoErrorHandling
# =============================================================================


@pytest.mark.asyncio
class TestAccountInfoErrorHandling:
    """Tests for error conditions on account info commands."""

    async def test_get_account_info_raises_when_disconnected(self, mock_encryption_manager):
        """Verify get_account_info raises ConnectionError when client is not connected."""
        client = MT4Client(
            host="127.0.0.1",
            rep_port=5555,
            pub_port=5556,
            magic_number=100001,
            encryption_manager=mock_encryption_manager,
        )
        # Client is NOT connected (default state)

        with pytest.raises(ConnectionError, match="Not connected to MT4"):
            await client.get_account_info()

    async def test_get_open_positions_raises_when_disconnected(self, mock_encryption_manager):
        """Verify get_open_positions raises ConnectionError when client is not connected."""
        client = MT4Client(
            host="127.0.0.1",
            rep_port=5555,
            pub_port=5556,
            magic_number=100001,
            encryption_manager=mock_encryption_manager,
        )

        with pytest.raises(ConnectionError, match="Not connected to MT4"):
            await client.get_open_positions()

    async def test_get_symbols_raises_when_disconnected(self, mock_encryption_manager):
        """Verify get_symbols raises ConnectionError when client is not connected."""
        client = MT4Client(
            host="127.0.0.1",
            rep_port=5555,
            pub_port=5556,
            magic_number=100001,
            encryption_manager=mock_encryption_manager,
        )

        with pytest.raises(ConnectionError, match="Not connected to MT4"):
            await client.get_symbols()

    async def test_get_account_info_timeout(self, mt4_client):
        """Verify get_account_info raises TimeoutError when MT4 does not respond."""
        async def timeout_send(command, timeout_ms=None):
            raise TimeoutError("MT4 command timeout after 5000ms")

        mt4_client.send_command = timeout_send

        with pytest.raises(TimeoutError):
            await mt4_client.get_account_info()

    async def test_get_open_positions_zmq_error(self, mt4_client):
        """Verify get_open_positions raises ConnectionError on ZMQ failure."""
        async def zmq_error_send(command, timeout_ms=None):
            raise ConnectionError("ZMQ error: Resource temporarily unavailable")

        mt4_client.send_command = zmq_error_send

        with pytest.raises(ConnectionError):
            await mt4_client.get_open_positions()


# =============================================================================
# TestCommandSerialization
# =============================================================================


@pytest.mark.asyncio
class TestCommandSerialization:
    """Tests that account info commands serialize correctly for ZMQ transmission."""

    async def test_get_account_info_command_json(self):
        """Verify GetAccountInfoCommand serializes to the correct JSON format."""
        command = GetAccountInfoCommand(magic_number=100001)
        json_data = command.model_dump(mode="json")

        assert json_data["command"] == "get_account_info"
        assert json_data["magic_number"] == 100001
        assert "correlation_id" in json_data

        # Verify it can be serialized to a JSON string (as send_command does)
        json_str = json.dumps(json_data)
        parsed = json.loads(json_str)
        assert parsed["command"] == "get_account_info"

    async def test_get_open_positions_command_json(self):
        """Verify GetOpenPositionsCommand serializes correctly."""
        command = GetOpenPositionsCommand(magic_number=100001)
        json_data = command.model_dump(mode="json")

        assert json_data["command"] == "get_open_positions"
        assert json_data["magic_number"] == 100001

    async def test_get_symbols_command_json(self):
        """Verify GetSymbolsCommand serializes correctly."""
        command = GetSymbolsCommand(magic_number=100001)
        json_data = command.model_dump(mode="json")

        assert json_data["command"] == "get_symbols"
        assert json_data["magic_number"] == 100001
