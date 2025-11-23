"""
MT4 Client for ZMQ communication.

Handles low-level ZMQ socket operations for communicating with MT4 Expert Advisors.
"""
import asyncio
import json
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

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
        self._sub_socket: Optional[zmq.asyncio.Socket] = None
        self._connected = False
        self._listening = False

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
            # Stop listening if active
            self._listening = False

            # Close REQ socket
            if self._req_socket:
                self._req_socket.close()
                self._req_socket = None

            # Close SUB socket
            if self._sub_socket:
                self._sub_socket.close()
                self._sub_socket = None

            # Terminate context
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

    def _adapt_mt4_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adapt MT4 EA response format to our Pydantic model format.

        MT4 EA returns: {"status": "OK", ...}
        We need: {"success": true, "correlation_id": "...", ...}
        """
        # Check if response is already in new format
        if "success" in response_data:
            return response_data

        # Adapt old format to new format
        adapted = {
            "success": response_data.get("status") == "OK",
            "correlation_id": response_data.get("correlation_id", "unknown"),
        }

        # Copy error info if present
        if "message" in response_data and response_data["message"]:
            adapted["error_message"] = response_data["message"]

        # Copy all other fields
        for key, value in response_data.items():
            if key not in ["status", "message"]:
                adapted[key] = value

        return adapted

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

        # Adapt response format
        response_data = self._adapt_mt4_response(response_data)

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

        # Adapt response format
        response_data = self._adapt_mt4_response(response_data)

        # Flatten account_info nested structure if present
        if "account_info" in response_data:
            account_info = response_data.pop("account_info")
            # Map field names: freeMargin -> free_margin, marginLevel -> margin_level
            response_data["balance"] = account_info.get("balance")
            response_data["equity"] = account_info.get("equity")
            response_data["margin"] = account_info.get("margin")
            response_data["free_margin"] = account_info.get("freeMargin")
            response_data["margin_level"] = account_info.get("marginLevel")
            response_data["leverage"] = account_info.get("leverage")
            response_data["account_number"] = account_info.get("accountNumber")

        return AccountInfoResponse(**response_data)

    async def get_open_positions(self) -> PositionsResponse:
        """
        Get all open positions from MT4.

        Returns:
            PositionsResponse with list of positions
        """
        command = GetOpenPositionsCommand(magic_number=self.magic_number)
        response_data = await self.send_command(command)

        # Adapt response format
        response_data = self._adapt_mt4_response(response_data)

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

    async def subscribe_to_events(self, topics: Optional[List[str]] = None) -> None:
        """
        Subscribe to PUB socket for real-time events from MT4.

        Args:
            topics: Optional list of topics to subscribe to.
                   If None or empty, subscribes to all topics.
                   Valid topics: ["position_updated", "position_closed", "market_tick"]

        Raises:
            ConnectionError: If not connected to MT4
        """
        if not self._connected or not self._context:
            raise ConnectionError("Must be connected before subscribing to events")

        try:
            # Create SUB socket if it doesn't exist
            if not self._sub_socket:
                self._sub_socket = self._context.socket(zmq.SUB)

                # Configure encryption if enabled
                if self.encryption_manager.encryption_enabled:
                    self._sub_socket = self.encryption_manager.configure_socket(self._sub_socket)

                # Connect to PUB socket
                pub_endpoint = f"tcp://{self.host}:{self.pub_port}"
                self._sub_socket.connect(pub_endpoint)

                logger.info(
                    "mt4_pub_socket_connected",
                    endpoint=pub_endpoint,
                    magic_number=self.magic_number
                )

            # Subscribe to topics
            if not topics:
                # Subscribe to all topics (empty filter)
                self._sub_socket.subscribe(b"")
                logger.info("mt4_subscribed_all_topics", magic_number=self.magic_number)
            else:
                # Subscribe to specific topics
                for topic in topics:
                    self._sub_socket.subscribe(topic.encode('utf-8'))
                    logger.debug(
                        "mt4_subscribed_topic",
                        topic=topic,
                        magic_number=self.magic_number
                    )

        except Exception as e:
            logger.error(
                "mt4_subscribe_error",
                error=str(e),
                host=self.host,
                pub_port=self.pub_port
            )
            raise ConnectionError(f"Failed to subscribe to MT4 events: {e}")

    async def unsubscribe_from_events(self, topics: Optional[List[str]] = None) -> None:
        """
        Unsubscribe from specific topics or all topics.

        Args:
            topics: Optional list of topics to unsubscribe from.
                   If None, unsubscribes from all topics.
        """
        if not self._sub_socket:
            return

        try:
            if not topics:
                # Unsubscribe from all
                self._sub_socket.unsubscribe(b"")
            else:
                for topic in topics:
                    self._sub_socket.unsubscribe(topic.encode('utf-8'))

            logger.debug("mt4_unsubscribed", topics=topics, magic_number=self.magic_number)

        except Exception as e:
            logger.error("mt4_unsubscribe_error", error=str(e))

    async def receive_event(self, timeout_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Receive a single event from the PUB socket.

        Args:
            timeout_ms: Timeout in milliseconds (default: self.timeout_ms)

        Returns:
            Event data as dictionary, or None if timeout

        Raises:
            ConnectionError: If SUB socket not initialized
        """
        if not self._sub_socket:
            raise ConnectionError("SUB socket not initialized. Call subscribe_to_events() first.")

        timeout = timeout_ms or self.timeout_ms

        try:
            # Poll for events with timeout
            if await self._sub_socket.poll(timeout=timeout) == 0:
                return None  # Timeout - no events available

            # Receive event
            event_json = await self._sub_socket.recv_string()
            event_data = json.loads(event_json)

            logger.debug(
                "mt4_event_received",
                event_type=event_data.get("event_type"),
                magic_number=self.magic_number
            )

            return event_data

        except json.JSONDecodeError as e:
            logger.error(
                "mt4_event_invalid_json",
                error=str(e)
            )
            return None
        except Exception as e:
            logger.error(
                "mt4_event_receive_error",
                error=str(e)
            )
            raise

    async def start_listening(
        self,
        event_handler: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """
        Start continuous event listener loop.

        Args:
            event_handler: Async callback function to handle each event

        Raises:
            ConnectionError: If SUB socket not initialized
            asyncio.CancelledError: When listener is stopped
        """
        if not self._sub_socket:
            raise ConnectionError("SUB socket not initialized. Call subscribe_to_events() first.")

        self._listening = True

        logger.info("mt4_event_listener_started", magic_number=self.magic_number)

        try:
            while self._listening:
                # Receive event with timeout
                event_data = await self.receive_event(timeout_ms=1000)

                if event_data:
                    # Call event handler
                    try:
                        await event_handler(event_data)
                    except Exception as e:
                        logger.error(
                            "mt4_event_handler_error",
                            error=str(e),
                            event_type=event_data.get("event_type")
                        )
                        # Continue listening even if handler fails

        except asyncio.CancelledError:
            logger.info("mt4_event_listener_cancelled", magic_number=self.magic_number)
            raise
        except Exception as e:
            logger.error("mt4_event_listener_error", error=str(e))
            raise
        finally:
            self._listening = False

    def stop_listening(self) -> None:
        """Stop the event listener loop."""
        self._listening = False
        logger.info("mt4_event_listener_stopped", magic_number=self.magic_number)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        return False
