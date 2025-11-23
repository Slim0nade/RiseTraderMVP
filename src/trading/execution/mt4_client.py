"""
MT4 Client for ZMQ communication.

Handles low-level ZMQ socket operations for communicating with MT4 Expert Advisors.
"""
import asyncio
import json
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

import zmq
import zmq.asyncio

from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.mt4_models import (
    MT4Command,
    CreateInstantOrderCommand,
    GetAccountInfoCommand,
    GetOpenPositionsCommand,
    GetSymbolsCommand,
    ClosePositionCommand,
    OrderResponse,
    AccountInfoResponse,
    PositionsResponse,
    SymbolsResponse,
)
from src.utils.mt4_helpers import get_mt4_logger, PerformanceTimer
from src.monitoring.mt4_metrics import record_zmq_command, record_zmq_error

logger = get_mt4_logger("mt4_client")


class MT4Client:
    """
    Low-level ZMQ client for MT4 communication.

    Manages a single REQ/REP socket connection to an MT4 EA.
    Supports encrypted communication via CurveZMQ.
    """

    def __init__(
        self,
        host: str,
        rep_port: int,
        pub_port: int,
        magic_number: int,
        encryption_manager: MT4EncryptionManager,
        timeout_ms: int = 5000
    ):
        """
        Initialize MT4 client for a specific EA.

        Args:
            host: MT4 server host (IP or hostname)
            rep_port: REP socket port for commands
            pub_port: PUB socket port for streaming (not used yet)
            magic_number: MT4 magic number for this EA
            encryption_manager: CurveZMQ encryption manager
            timeout_ms: Command timeout in milliseconds
        """
        self.host = host
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.magic_number = magic_number
        self.encryption_manager = encryption_manager
        self.timeout_ms = timeout_ms

        # ZMQ context and sockets
        self._context: Optional[zmq.asyncio.Context] = None
        self._req_socket: Optional[zmq.asyncio.Socket] = None
        self._connected = False

        logger.info(
            "mt4_client_initialized",
            host=host,
            rep_port=rep_port,
            magic_number=magic_number,
            encryption_enabled=encryption_manager.encryption_enabled
        )

    async def connect(self) -> None:
        """Establish ZMQ connection to MT4 EA."""
        if self._connected:
            logger.warning("mt4_client_already_connected", magic_number=self.magic_number)
            return

        try:
            # Create ZMQ context
            self._context = zmq.asyncio.Context()

            # Create REQ socket for commands
            self._req_socket = self._context.socket(zmq.REQ)

            # Configure encryption if enabled
            if self.encryption_manager.encryption_enabled:
                self._req_socket = self.encryption_manager.configure_socket(self._req_socket)
                logger.info("mt4_client_encryption_enabled", magic_number=self.magic_number)

            # Connect to MT4 EA
            endpoint = f"tcp://{self.host}:{self.rep_port}"
            self._req_socket.connect(endpoint)

            self._connected = True

            logger.info(
                "mt4_client_connected",
                endpoint=endpoint,
                magic_number=self.magic_number
            )

        except Exception as e:
            logger.error(
                "mt4_connection_failed",
                error=str(e),
                host=self.host,
                rep_port=self.rep_port
            )
            raise ConnectionError(f"Failed to connect to MT4: {e}")

    async def disconnect(self) -> None:
        """Close ZMQ connection."""
        if not self._connected:
            return

        try:
            if self._req_socket:
                self._req_socket.close()
                self._req_socket = None

            if self._context:
                self._context.term()
                self._context = None

            self._connected = False

            logger.info("mt4_client_disconnected", magic_number=self.magic_number)

        except Exception as e:
            logger.error("mt4_disconnect_error", error=str(e))

    def is_connected(self) -> bool:
        """Check if client is connected to MT4."""
        return self._connected

    async def send_command(
        self,
        command: MT4Command,
        timeout_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send command to MT4 and await response.

        Args:
            command: MT4 command instance (Pydantic model)
            timeout_ms: Optional timeout override

        Returns:
            Response dictionary from MT4

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
            zmq.ZMQError: If ZMQ communication fails
        """
        if not self._connected or not self._req_socket:
            raise ConnectionError("Not connected to MT4")

        timeout = timeout_ms or self.timeout_ms
        command_type = command.command

        try:
            # Serialize command
            command_json = json.dumps(command.model_dump(mode='json'))

            # Send command
            await self._req_socket.send_string(command_json)

            logger.debug(
                "mt4_command_sent",
                command=command_type,
                correlation_id=command.correlation_id,
                magic_number=self.magic_number
            )

            # Poll for response with timeout
            if await self._req_socket.poll(timeout=timeout) == 0:
                logger.error(
                    "mt4_command_timeout",
                    command=command_type,
                    timeout_ms=timeout
                )
                record_zmq_error(command_type=command_type, error_type="timeout")
                raise TimeoutError(f"MT4 command timeout after {timeout}ms")

            # Receive response
            response_json = await self._req_socket.recv_string()
            response = json.loads(response_json)

            logger.debug(
                "mt4_response_received",
                command=command_type,
                correlation_id=command.correlation_id,
                success=response.get("success", False)
            )

            return response

        except zmq.ZMQError as e:
            logger.error(
                "mt4_zmq_error",
                error=str(e),
                command=command_type
            )
            record_zmq_error(command_type=command_type, error_type="zmq_error")
            raise ConnectionError(f"ZMQ error: {e}")

        except json.JSONDecodeError as e:
            logger.error(
                "mt4_invalid_json_response",
                error=str(e),
                command=command_type
            )
            record_zmq_error(command_type=command_type, error_type="json_error")
            raise

        except Exception as e:
            logger.error(
                "mt4_command_error",
                error=str(e),
                command=command_type
            )
            record_zmq_error(command_type=command_type, error_type="unknown")
            raise

    async def create_instant_order(
        self,
        symbol: str,
        direction: Literal["BUY", "SELL"],
        volume: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        comment: Optional[str] = None
    ) -> OrderResponse:
        """
        Submit instant market order to MT4.

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL")
            direction: Order direction (BUY or SELL)
            volume: Order volume in lots
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            comment: Optional order comment

        Returns:
            OrderResponse with execution details

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        # Create command
        command = CreateInstantOrderCommand(
            symbol=symbol,
            direction=direction,
            volume=volume,
            magic_number=self.magic_number,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment
        )

        # Send command with performance timing
        async with PerformanceTimer(
            logger=logger,
            operation="create_instant_order",
            correlation_id=command.correlation_id,
            symbol=symbol,
            direction=direction
        ):
            response_data = await self.send_command(command)

            # Record metrics
            duration_ms = 0  # Will be calculated by PerformanceTimer
            record_zmq_command(
                command_type="create_instant_order",
                duration_seconds=duration_ms / 1000
            )

        # Parse response
        order_response = OrderResponse(**response_data)

        logger.info(
            "instant_order_submitted",
            correlation_id=command.correlation_id,
            symbol=symbol,
            direction=direction,
            volume=float(volume),
            success=order_response.success,
            ticket_number=order_response.ticket_number if order_response.success else None
        )

        return order_response

    async def get_symbols(self) -> List[str]:
        """
        Fetch available trading symbols from MT4.

        Returns:
            List of symbol names

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        # Create command
        command = GetSymbolsCommand(magic_number=self.magic_number)

        # Send command
        response_data = await self.send_command(command)

        # Parse response
        if not response_data.get("success", False):
            logger.error(
                "get_symbols_failed",
                error=response_data.get("error_message", "Unknown error")
            )
            return []

        symbols = response_data.get("symbols", [])

        logger.info(
            "symbols_retrieved",
            count=len(symbols),
            symbols=symbols[:10]  # Log first 10 for debugging
        )

        return symbols

    async def get_account_info(self) -> AccountInfoResponse:
        """
        Get MT4 account information.

        Returns:
            AccountInfoResponse with balance, equity, margin, etc.
        """
        command = GetAccountInfoCommand(magic_number=self.magic_number)
        response_data = await self.send_command(command)
        return AccountInfoResponse(**response_data)

    async def get_open_positions(self) -> PositionsResponse:
        """
        Get all open positions from MT4.

        Returns:
            PositionsResponse with list of positions
        """
        command = GetOpenPositionsCommand(magic_number=self.magic_number)
        response_data = await self.send_command(command)
        return PositionsResponse(**response_data)

    async def close_position(
        self,
        ticket_number: int
    ) -> Dict[str, Any]:
        """
        Close an open position by ticket number.

        Args:
            ticket_number: MT4 ticket number to close

        Returns:
            Response dictionary from MT4
        """
        command = ClosePositionCommand(
            ticket_number=ticket_number,
            magic_number=self.magic_number
        )

        response_data = await self.send_command(command)

        logger.info(
            "position_close_requested",
            ticket_number=ticket_number,
            success=response_data.get("success", False)
        )

        return response_data

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        return False
