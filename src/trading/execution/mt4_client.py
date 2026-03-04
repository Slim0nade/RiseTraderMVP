"""
MT4 Client for ZMQ communication.

Handles low-level ZMQ socket operations for communicating with MT4 Expert Advisors.
Includes circuit breaker for resilience and exponential backoff for reconnection.
"""
import asyncio
import json
import random
from datetime import datetime, timedelta
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
    GetTradeHistoryCommand,
    GetSymbolsCommand,
    GetSymbolInfoCommand,
    GetAllSymbolsInfoCommand,
    ClosePositionCommand,
    OrderResponse,
)
from src.trading.execution.mt4_request_logger import MT4RequestLogger
from src.utils.mt4_helpers import get_mt4_logger, PerformanceTimer
from src.monitoring.mt4_metrics import record_zmq_command, record_zmq_error

logger = get_mt4_logger("mt4_client")


# =============================================================================
# Circuit Breaker Implementation (T091)
# =============================================================================

class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker for MT4 connection resilience (T091).

    Implements three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 30,
        success_threshold: int = 2
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting reset (OPEN -> HALF_OPEN)
            success_threshold: Successes needed in HALF_OPEN to close circuit
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold

        self.state: Literal["CLOSED", "OPEN", "HALF_OPEN"] = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None

        logger.info(
            "circuit_breaker_initialized",
            failure_threshold=failure_threshold,
            timeout=timeout
        )

    def can_proceed(self) -> bool:
        """Check if request can proceed."""
        if self.state == "CLOSED":
            return True

        if self.state == "HALF_OPEN":
            return True

        if self.state == "OPEN":
            if self.should_attempt_reset():
                self.attempt_reset()
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record successful request."""
        if self.state == "CLOSED":
            self.failure_count = 0

        elif self.state == "HALF_OPEN":
            self.success_count += 1

            if self.success_count >= self.success_threshold:
                self._close_circuit()
                logger.info("circuit_breaker_closed_after_recovery")

    def record_failure(self) -> None:
        """Record failed request."""
        self.last_failure_time = datetime.utcnow()

        if self.state == "CLOSED":
            self.failure_count += 1

            if self.failure_count >= self.failure_threshold:
                self._open_circuit()
                logger.warning(
                    "circuit_breaker_opened",
                    failure_count=self.failure_count
                )

        elif self.state == "HALF_OPEN":
            self._open_circuit()
            logger.warning("circuit_breaker_reopened_after_failed_test")

    def should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.state != "OPEN":
            return False

        if self.last_failure_time is None:
            return True

        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout

    def attempt_reset(self) -> None:
        """Transition from OPEN to HALF_OPEN."""
        if self.state == "OPEN":
            self.state = "HALF_OPEN"
            self.success_count = 0
            logger.info("circuit_breaker_half_open_testing_recovery")

    def _open_circuit(self) -> None:
        """Open the circuit."""
        self.state = "OPEN"
        self.last_failure_time = datetime.utcnow()

    def _close_circuit(self) -> None:
        """Close the circuit."""
        self.state = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    def get_state_info(self) -> dict:
        """Get circuit breaker state information."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None
        }


# =============================================================================
# Exponential Backoff (T092)
# =============================================================================

def calculate_backoff_time(
    attempt: int,
    base: float = 1.0,
    max_backoff: float = 300.0,
    jitter: bool = False
) -> float:
    """
    Calculate exponential backoff time (T092).

    Formula: min(base * 2^attempt, max_backoff)
    With optional jitter: backoff * random(0.5, 1.5)

    Args:
        attempt: Reconnection attempt number (0-based)
        base: Base time in seconds (default 1 second)
        max_backoff: Maximum backoff time in seconds (default 5 minutes)
        jitter: Whether to add random jitter

    Returns:
        Backoff time in seconds
    """
    backoff = base * (2 ** attempt)
    backoff = min(backoff, max_backoff)

    if jitter:
        jitter_factor = 0.5 + random.random()
        backoff = backoff * jitter_factor

    return backoff


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
        timeout_ms: int = 5000,
        enable_circuit_breaker: bool = False  # DISABLED by default for development
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
            enable_circuit_breaker: Enable circuit breaker (default: False for development)
        """
        self.host = host
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.magic_number = magic_number
        self.encryption_manager = encryption_manager
        self.timeout_ms = timeout_ms
        self.enable_circuit_breaker = enable_circuit_breaker

        # ZMQ context and sockets
        self._context: Optional[zmq.asyncio.Context] = None
        self._req_socket: Optional[zmq.asyncio.Socket] = None
        self._sub_socket: Optional[zmq.asyncio.Socket] = None
        self._connected = False
        self._listening = False

        # Circuit breaker for resilience (T091) - only if enabled
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=30,
            success_threshold=2
        ) if enable_circuit_breaker else None

        # Reconnection state (T092, T094)
        self.reconnect_attempt = 0
        self._auto_reconnect_task: Optional[asyncio.Task] = None
        self._should_reconnect = True

        # Pending messages for graceful shutdown (T095)
        self._pending_messages: List[Dict] = []

        logger.info(
            "mt4_client_initialized",
            host=host,
            rep_port=rep_port,
            magic_number=magic_number,
            encryption_enabled=encryption_manager.encryption_enabled
        )

    async def connect(self) -> None:
        """Establish ZMQ connection to MT4 EA (with connection event logging - T110)."""
        if self._connected:
            logger.warning("mt4_client_already_connected", magic_number=self.magic_number)
            return

        try:
            # Create ZMQ context
            self._context = zmq.asyncio.Context()

            # Create REQ socket for commands
            self._req_socket = self._context.socket(zmq.REQ)

            # Configure encryption if enabled
            encrypted = self.encryption_manager.encryption_enabled
            if encrypted:
                self._req_socket = self.encryption_manager.configure_socket(self._req_socket)
                logger.info("mt4_client_encryption_enabled", magic_number=self.magic_number)

            # Connect to MT4 EA
            endpoint = f"tcp://{self.host}:{self.rep_port}"
            self._req_socket.connect(endpoint)

            self._connected = True

            # Log connection event (T110)
            MT4RequestLogger.log_connection_event(
                event_type="CONNECT",
                magic_number=self.magic_number,
                host=self.host,
                port=self.rep_port,
                encrypted=encrypted,
                details={"endpoint": endpoint}
            )

        except Exception as e:
            logger.error(
                "mt4_connection_failed",
                error=str(e),
                host=self.host,
                rep_port=self.rep_port
            )
            raise ConnectionError(f"Failed to connect to MT4: {e}")

    async def _reset_req_socket(self) -> None:
        """Reset the REQ socket to recover from an invalid state (e.g., EFSM error).
        
        ZMQ REQ sockets can get stuck in an invalid state if a send/receive cycle
        is interrupted. This method closes and recreates the socket to recover.
        """
        try:
            logger.warning("mt4_socket_reset", magic_number=self.magic_number)
            
            # Close old socket if it exists
            if self._req_socket:
                self._req_socket.close(linger=0)  # Don't wait for pending messages
                self._req_socket = None
            
            # Create new socket
            if self._context:
                self._req_socket = self._context.socket(zmq.REQ)
                
                # Configure encryption if enabled
                if self.encryption_manager.encryption_enabled:
                    self._req_socket = self.encryption_manager.configure_socket(self._req_socket)
                
                # Reconnect
                endpoint = f"tcp://{self.host}:{self.rep_port}"
                self._req_socket.connect(endpoint)
                
                logger.info("mt4_socket_reset_complete", magic_number=self.magic_number)
            else:
                # Context is gone, need full reconnect
                self._connected = False
                raise ConnectionError("ZMQ context not available, need full reconnect")
                
        except Exception as e:
            logger.error("mt4_socket_reset_failed", error=str(e))
            self._connected = False
            raise ConnectionError(f"Socket reset failed: {e}")

    async def disconnect(self) -> None:
        """Close ZMQ connection (with disconnect event logging - T110)."""
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

            # Log disconnection event (T110)
            MT4RequestLogger.log_connection_event(
                event_type="DISCONNECT",
                magic_number=self.magic_number,
                host=self.host,
                port=self.rep_port,
                encrypted=self.encryption_manager.encryption_enabled
            )

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
        Send command to MT4 and await response (with circuit breaker - T091 & logging - T110).

        Args:
            command: MT4 command instance (Pydantic model)
            timeout_ms: Optional timeout override

        Returns:
            Response dictionary from MT4

        Raises:
            ConnectionError: If not connected
            CircuitOpenError: If circuit breaker is open
            TimeoutError: If command times out
            zmq.ZMQError: If ZMQ communication fails
        """
        command_type = command.command
        correlation_id = command.correlation_id
        request_data = command.model_dump(mode='json')
        # Convert Decimal-serialized strings back to numbers for MT4
        for key in ('stop_loss', 'take_profit'):
            if key in request_data and isinstance(request_data[key], str):
                request_data[key] = float(request_data[key])

        # Check circuit breaker first (T091 - fail fast if open) - only if enabled
        if self.circuit_breaker and not self.circuit_breaker.can_proceed():
            # Log blocked request (T110)
            MT4RequestLogger.log_circuit_breaker_blocked(
                command_type=command_type,
                correlation_id=correlation_id,
                magic_number=self.magic_number,
                circuit_state=self.circuit_breaker.state,
                failure_count=self.circuit_breaker.failure_count
            )
            raise CircuitOpenError(
                f"Circuit breaker is {self.circuit_breaker.state}, "
                f"cannot send command to MT4"
            )

        if not self._connected or not self._req_socket:
            raise ConnectionError("Not connected to MT4")

        timeout = timeout_ms or self.timeout_ms

        try:
            # Serialize command
            command_json = json.dumps(request_data)

            # Log request with timestamp (T110)
            request_time = MT4RequestLogger.log_request(
                command_type=command_type,
                correlation_id=correlation_id,
                magic_number=self.magic_number,
                request_data=request_data,
                encrypted=self.encryption_manager is not None
            )

            # Send command
            await self._req_socket.send_string(command_json)

            # Poll for response with timeout
            if await self._req_socket.poll(timeout=timeout) == 0:
                # Log timeout (T110)
                MT4RequestLogger.log_timeout(
                    command_type=command_type,
                    correlation_id=correlation_id,
                    magic_number=self.magic_number,
                    request_time=request_time,
                    timeout_ms=timeout
                )
                record_zmq_error(command_type=command_type, error_type="timeout")

                # Record failure in circuit breaker (T091) - only if enabled
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure()

                raise TimeoutError(f"MT4 command timeout after {timeout}ms")

            # Receive response
            response_json = await self._req_socket.recv_string()
            response = json.loads(response_json)

            # Determine success (handle both old and new response formats - T110)
            # Old format: {"status": "OK", ...}
            # New format: {"success": true, ...}
            is_success = response.get("success", False) or response.get("status") == "OK"

            # Log response (T110)
            MT4RequestLogger.log_response(
                command_type=command_type,
                correlation_id=correlation_id,
                magic_number=self.magic_number,
                response_data=response,
                request_time=request_time,
                success=is_success,
                error_code=response.get("error_code"),
                error_message=response.get("error_message") or response.get("message")
            )

            # Record success in circuit breaker (T091) - only if enabled
            if self.circuit_breaker:
                self.circuit_breaker.record_success()

            # Reset reconnect attempt counter on success (T092)
            self.reconnect_attempt = 0

            return response

        except zmq.ZMQError as e:
            # Log ZMQ error (T110)
            MT4RequestLogger.log_zmq_error(
                command_type=command_type,
                correlation_id=correlation_id,
                magic_number=self.magic_number,
                request_time=request_time,
                error_type="zmq_error",
                error_details=str(e)
            )
            record_zmq_error(command_type=command_type, error_type="zmq_error")

            # Record failure in circuit breaker (T091) - only if enabled
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()

            # Check for EFSM (finite state machine) error - socket is in bad state
            # This happens when send/receive cycle is interrupted
            error_str = str(e).lower()
            if "state" in error_str or "efsm" in error_str or "operation cannot be accomplished" in error_str:
                logger.warning(
                    "mt4_socket_state_error",
                    command_type=command_type,
                    error=str(e),
                    recovery="attempting socket reset"
                )
                # Attempt socket recovery for next call
                try:
                    await self._reset_req_socket()
                except Exception as reset_error:
                    logger.error("mt4_socket_reset_failed_in_send", error=str(reset_error))

            raise ConnectionError(f"ZMQ error: {e}")

        except json.JSONDecodeError as e:
            # Log JSON decode error (T110)
            MT4RequestLogger.log_zmq_error(
                command_type=command_type,
                correlation_id=correlation_id,
                magic_number=self.magic_number,
                request_time=request_time,
                error_type="json_decode_error",
                error_details=str(e)
            )
            record_zmq_error(command_type=command_type, error_type="json_error")

            # Record failure in circuit breaker (T091) - only if enabled
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()

            raise

        except Exception as e:
            # Log unknown error (T110)
            MT4RequestLogger.log_zmq_error(
                command_type=command_type,
                correlation_id=correlation_id,
                magic_number=self.magic_number,
                request_time=request_time,
                error_type="unknown_error",
                error_details=str(e)
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
            order_type=direction,  # Use direction parameter for order_type field
            volume=volume,
            magic_number=self.magic_number,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment
        )

        # Send command with performance timing
        with PerformanceTimer(
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

        # Parse response (adapt old EA format to new format)
        adapted_response = self._adapt_mt4_response(response_data)
        order_response = OrderResponse(**adapted_response)

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
        message = response_data.get("message", "")
        if message:
            if adapted["success"]:
                # For success messages, check if ticket number is embedded
                # Format: "Order created with ticket 24427082"
                import re
                ticket_match = re.search(r"ticket (\d+)", message)
                if ticket_match:
                    adapted["ticket_number"] = int(ticket_match.group(1))
                # Keep success message as error_message for now (will be used in logs)
                adapted["error_message"] = message
            else:
                # For errors, copy as error_message
                adapted["error_message"] = message

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

    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed symbol specifications from MT4.

        Returns leverage, margin %, swap rates, trading hours, contract size, etc.

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL", "EURUSD")

        Returns:
            Dictionary with symbol specifications:
            - symbol: str
            - bid: float
            - ask: float
            - spread: float (in points)
            - contract_size: float
            - leverage: float (calculated)
            - margin_pct: float (margin percentage)
            - swap_long: float (swap points for long positions)
            - swap_short: float (swap points for short positions)
            - min_lot: float
            - max_lot: float
            - lot_step: float
            - digits: int (price decimal places)
            - trade_allowed: bool
            - point: float
            - tick_size: float
            - tick_value: float

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MT4")

        command = GetSymbolInfoCommand(
            symbol=symbol,
            magic_number=self.magic_number
        )

        response_data = await self.send_command(command)

        # Adapt response format
        response_data = self._adapt_mt4_response(response_data)

        if not response_data.get("success", False):
            logger.error(
                "get_symbol_info_failed",
                symbol=symbol,
                error=response_data.get("error_message", "Unknown error")
            )
            return response_data

        logger.info(
            "symbol_info_retrieved",
            symbol=symbol,
            leverage=response_data.get("leverage"),
            margin_pct=response_data.get("margin_pct")
        )

        return response_data

    async def get_all_symbols_info(self) -> Dict[str, Any]:
        """
        Get detailed specifications for all available symbols from MT4.

        Returns specifications for all tradeable symbols including:
        - Leverage/margin requirements
        - Swap rates
        - Contract sizes
        - Trading hours
        - Spread information

        Useful for:
        - Portfolio diversification analysis (Dalio's Holy Grail)
        - Finding high-leverage opportunities
        - Understanding margin requirements

        Returns:
            Dictionary with:
            - success: bool
            - symbols: List of symbol info dictionaries
            - total: int (number of symbols)

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MT4")

        command = GetAllSymbolsInfoCommand(magic_number=self.magic_number)

        response_data = await self.send_command(command)

        # Adapt response format
        response_data = self._adapt_mt4_response(response_data)

        if not response_data.get("success", False):
            logger.error(
                "get_all_symbols_info_failed",
                error=response_data.get("error_message", "Unknown error")
            )
            return response_data

        symbols_count = len(response_data.get("symbols", []))

        logger.info(
            "all_symbols_info_retrieved",
            count=symbols_count
        )

        return response_data

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get MT4 account information (T080 - User Story 4).

        Returns:
            Dictionary with account info:
            - success: bool
            - balance: float
            - equity: float
            - margin: float
            - free_margin: float
            - margin_level: float
            - profit: float
            - account_number: int
            - leverage: int
            - currency: str
            - server: str
            - company: str

        Raises:
            ConnectionError: If not connected to MT4
            TimeoutError: If MT4 doesn't respond
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MT4")

        command = GetAccountInfoCommand()
        response_data = await self.send_command(command)

        logger.info(
            "account_info_received",
            balance=response_data.get("balance"),
            equity=response_data.get("equity")
        )

        return response_data

    async def get_open_positions(self, magic_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Get open positions from MT4 (T081 - User Story 4).

        Args:
            magic_number: Optional magic number to filter positions

        Returns:
            Dictionary with:
            - success: bool
            - positions: List of position dictionaries

        Raises:
            ConnectionError: If not connected to MT4
            TimeoutError: If MT4 doesn't respond
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MT4")

        command = GetOpenPositionsCommand(magic_number=magic_number)
        response_data = await self.send_command(command)

        logger.info(
            "positions_received",
            count=len(response_data.get("positions", []))
        )

        return response_data

    async def get_trade_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        ticket: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get trade history from MT4 for closed positions.

        Args:
            start_time: Start time filter (None = all history)
            end_time: End time filter (None = now)
            ticket: Specific ticket to fetch (None = all)

        Returns:
            Dictionary with:
            - status: str ("OK" or "ERROR")
            - trades: List of trade dictionaries with close data

        Raises:
            ConnectionError: If not connected to MT4
            TimeoutError: If MT4 doesn't respond
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MT4")

        command = GetTradeHistoryCommand(
            start_time=int(start_time.timestamp()) if start_time else None,
            end_time=int(end_time.timestamp()) if end_time else None,
            ticket=ticket
        )
        response_data = await self.send_command(command)

        logger.info(
            "trade_history_received",
            count=len(response_data.get("trades", []))
        )

        return response_data

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
            ticket=ticket_number,  # EA expects "ticket" field
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

    # =========================================================================
    # Reconnection Logic (T092, T094)
    # =========================================================================

    def _get_reconnect_backoff(self) -> float:
        """Get backoff time for current reconnection attempt (T092)."""
        return calculate_backoff_time(
            attempt=self.reconnect_attempt,
            base=1.0,
            max_backoff=300.0,
            jitter=True
        )

    async def _wait_with_backoff(self, backoff_seconds: float) -> None:
        """Wait for backoff period (T092)."""
        await asyncio.sleep(backoff_seconds)

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to MT4 (T094 with reconnection event logging - T110).

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            logger.info(
                "mt4_reconnection_attempt",
                magic_number=self.magic_number,
                attempt=self.reconnect_attempt
            )

            # Disconnect first
            await self.disconnect()

            # Wait with exponential backoff
            backoff = self._get_reconnect_backoff()
            logger.info(
                "mt4_reconnection_backoff",
                backoff_seconds=backoff,
                attempt=self.reconnect_attempt
            )
            await self._wait_with_backoff(backoff)

            # Attempt connection
            await self.connect()

            # Log successful reconnection event (T110)
            MT4RequestLogger.log_connection_event(
                event_type="RECONNECT",
                magic_number=self.magic_number,
                host=self.host,
                port=self.rep_port,
                encrypted=self.encryption_manager.encryption_enabled,
                details={
                    "reconnect_attempt": self.reconnect_attempt,
                    "backoff_seconds": backoff,
                    "status": "success"
                }
            )

            # Reset reconnection counter on success
            self.reconnect_attempt = 0
            return True

        except Exception as e:
            logger.error(
                "mt4_reconnection_failed",
                error=str(e),
                magic_number=self.magic_number,
                attempt=self.reconnect_attempt
            )
            self.reconnect_attempt += 1
            return False

    async def start_auto_reconnect(self) -> None:
        """
        Start automatic reconnection loop (T094).

        Monitors connection and automatically reconnects on failure.
        """
        if self._auto_reconnect_task and not self._auto_reconnect_task.done():
            logger.warning("auto_reconnect_already_running", magic_number=self.magic_number)
            return

        self._should_reconnect = True
        self._auto_reconnect_task = asyncio.create_task(self._auto_reconnect_loop())

        logger.info("auto_reconnect_started", magic_number=self.magic_number)

    async def stop_auto_reconnect(self) -> None:
        """Stop automatic reconnection loop (T094)."""
        self._should_reconnect = False

        if self._auto_reconnect_task:
            self._auto_reconnect_task.cancel()
            try:
                await self._auto_reconnect_task
            except asyncio.CancelledError:
                pass

        logger.info("auto_reconnect_stopped", magic_number=self.magic_number)

    async def _auto_reconnect_loop(self) -> None:
        """Background task for automatic reconnection (T094)."""
        while self._should_reconnect:
            try:
                # Check if connected
                if not self.is_connected() or self.circuit_breaker.state == "OPEN":
                    logger.info(
                        "auto_reconnect_triggered",
                        connected=self.is_connected(),
                        circuit_state=self.circuit_breaker.state
                    )

                    # Attempt reconnection
                    success = await self.reconnect()

                    if success:
                        # Publish connection status event (T093)
                        await self._publish_connection_status("ACTIVE")
                    else:
                        await self._publish_connection_status("RECONNECTING")

                # Check every 10 seconds
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("auto_reconnect_loop_error", error=str(e))
                await asyncio.sleep(5)

    # =========================================================================
    # Connection Status Events (T093)
    # =========================================================================

    async def _publish_connection_status(self, status: str) -> None:
        """
        Publish connection status changed event (T093).

        Args:
            status: Connection status (ACTIVE, INACTIVE, ERROR, RECONNECTING)
        """
        try:
            event = {
                "event_type": "connection_status_changed",
                "ea_id": f"ea_{self.magic_number}",
                "magic_number": self.magic_number,
                "status": status,
                "circuit_state": self.circuit_breaker.state,
                "timestamp": datetime.utcnow().isoformat()
            }

            logger.info(
                "connection_status_changed",
                magic_number=self.magic_number,
                status=status,
                circuit_state=self.circuit_breaker.state
            )

            # This would normally publish to Redis
            # For now, just log it
            # await self.redis_client.publish("connection_status_changed", event)

        except Exception as e:
            logger.error("publish_connection_status_error", error=str(e))

    # =========================================================================
    # Pending Orders (T096)
    # =========================================================================

    async def create_pending_order(
        self,
        symbol: str,
        order_type: Literal["BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT"],
        volume: Decimal,
        price: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        comment: Optional[str] = None,
        expiration: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a pending order in MT4.

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL")
            order_type: Order type (BUY_STOP, SELL_STOP, BUY_LIMIT, SELL_LIMIT)
            volume: Order volume in lots
            price: Entry price for the pending order
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            comment: Optional order comment
            expiration: Optional expiration datetime (ISO format)

        Returns:
            Response dict with success status and ticket number

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        from src.trading.execution.mt4_models import CreatePendingOrderCommand

        command = CreatePendingOrderCommand(
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            price=price,
            magic_number=self.magic_number,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
            expiration=expiration
        )

        with PerformanceTimer(
            logger=logger,
            operation="create_pending_order",
            correlation_id=command.correlation_id,
            symbol=symbol,
            order_type=order_type
        ):
            response_data = await self.send_command(command)

        # Adapt response format
        adapted_response = self._adapt_mt4_response(response_data)

        logger.info(
            "pending_order_submitted",
            correlation_id=command.correlation_id,
            symbol=symbol,
            order_type=order_type,
            volume=float(volume),
            price=float(price),
            success=adapted_response.get("success", False),
            ticket_number=adapted_response.get("ticket_number")
        )

        return adapted_response

    async def get_pending_orders(
        self,
        magic_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get all pending orders from MT4.

        Args:
            magic_number: Optional magic number to filter orders

        Returns:
            Response dict with list of pending orders

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        from src.trading.execution.mt4_models import GetPendingOrdersCommand

        command = GetPendingOrdersCommand(magic_number=magic_number)
        response_data = await self.send_command(command)

        logger.info(
            "pending_orders_retrieved",
            count=len(response_data.get("orders", []))
        )

        return response_data

    async def delete_pending_order(
        self,
        ticket: int
    ) -> Dict[str, Any]:
        """
        Delete/cancel a pending order in MT4.

        Args:
            ticket: Order ticket number to cancel

        Returns:
            Response dict with success status

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        from src.trading.execution.mt4_models import DeletePendingOrderCommand

        command = DeletePendingOrderCommand(
            ticket=ticket,
            magic_number=self.magic_number
        )

        response_data = await self.send_command(command)

        logger.info(
            "pending_order_deleted",
            ticket=ticket,
            success=response_data.get("success", False) or response_data.get("status") == "OK"
        )

        return response_data

    # =========================================================================
    # Position Modification (Institutional Stop-Hunting Avoidance)
    # =========================================================================

    async def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Modify stop loss and/or take profit of an open position.

        Used for:
        - Adjusting stops to non-obvious "weird" levels (anti-stop-hunting)
        - Implementing trailing stops
        - Moving stops to breakeven

        Args:
            ticket: Position ticket number to modify
            stop_loss: New stop loss price (None to keep existing)
            take_profit: New take profit price (None to keep existing)

        Returns:
            Response dict with success status and new SL/TP values

        Raises:
            ConnectionError: If not connected
            TimeoutError: If command times out
        """
        from src.trading.execution.mt4_models import ModifyPositionCommand

        command = ModifyPositionCommand(
            ticket=ticket,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        with PerformanceTimer(
            logger=logger,
            operation="modify_position",
            correlation_id=command.correlation_id,
            ticket=ticket
        ):
            response_data = await self.send_command(command)

        # Adapt response format
        adapted_response = self._adapt_mt4_response(response_data)

        logger.info(
            "position_modified",
            correlation_id=command.correlation_id,
            ticket=ticket,
            stop_loss=float(stop_loss) if stop_loss else None,
            take_profit=float(take_profit) if take_profit else None,
            success=adapted_response.get("success", False)
        )

        return adapted_response

    # =========================================================================
    # Graceful Shutdown (T095)
    # =========================================================================

    async def flush_pending_messages(self) -> None:
        """
        Flush pending messages before shutdown (T095).

        Ensures no messages are lost during graceful shutdown.
        """
        if not self._pending_messages:
            logger.info("no_pending_messages_to_flush", magic_number=self.magic_number)
            return

        logger.info(
            "flushing_pending_messages",
            count=len(self._pending_messages),
            magic_number=self.magic_number
        )

        for message in self._pending_messages[:]:
            try:
                # Attempt to send pending message
                await self.send_command(message)
                self._pending_messages.remove(message)
            except Exception as e:
                logger.error(
                    "failed_to_flush_message",
                    error=str(e),
                    message=message
                )
                # Keep message in queue for retry

        logger.info(
            "pending_messages_flushed",
            remaining=len(self._pending_messages),
            magic_number=self.magic_number
        )

    async def graceful_shutdown(self) -> None:
        """
        Gracefully shutdown client (T095).

        Stops auto-reconnect, flushes pending messages, and disconnects.
        """
        logger.info("graceful_shutdown_started", magic_number=self.magic_number)

        try:
            # Stop auto-reconnect
            await self.stop_auto_reconnect()

            # Stop listening
            self.stop_listening()

            # Flush pending messages
            await self.flush_pending_messages()

            # Disconnect
            await self.disconnect()

            logger.info("graceful_shutdown_complete", magic_number=self.magic_number)

        except Exception as e:
            logger.error("graceful_shutdown_error", error=str(e))

    # =========================================================================
    # Context Manager (existing)
    # =========================================================================

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with graceful shutdown (T095)."""
        await self.graceful_shutdown()
        return False
