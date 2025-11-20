"""
ExecutionAgent - Trade Execution via MT4

Responsibilities:
- Execute validated trades on MT4 via ZMQ
- Retry logic with exponential backoff
- Slippage tolerance validation
- Emit trade_executed or trade_failed events

Performance Target: <500ms execution time
"""

import asyncio
import time
import json
from typing import Dict, Any, Optional

import structlog
import zmq
import zmq.asyncio

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class ExecutionAgent(BaseAgent):
    """
    Executes trades on MT4 via ZMQ

    Execution Flow:
    1. Receive trade_validated event
    2. Connect to MT4 via ZMQ
    3. Send order command
    4. Verify execution
    5. Validate slippage
    6. Emit trade_executed or trade_failed
    7. Retry on failure (max 3 attempts)
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=3,  # High priority - execution layer
        )

        # MT4 Configuration
        self.mt4_host = config.get("mt4_host", "75.154.254.186")
        self.mt4_command_port = config.get("mt4_command_port", 5555)
        self.mt4_stream_port = config.get("mt4_stream_port", 5556)
        self.use_encryption = config.get("use_encryption", False)

        # Execution parameters
        self.max_retry = config.get("max_retry", 3)
        self.retry_delay = config.get("retry_delay", 1.0)
        self.timeout = config.get("timeout", 5.0)
        self.slippage_tolerance = config.get("slippage_tolerance", 0.0002)  # 2 pips

        # ZMQ
        self.zmq_context: Optional[zmq.asyncio.Context] = None
        self.zmq_socket: Optional[zmq.asyncio.Socket] = None
        self.mt4_connected = False

        # Stats
        self.trades_executed = 0
        self.trades_failed = 0
        self.total_slippage = 0.0
        self.retry_count = 0

    async def initialize(self) -> None:
        """Initialize ZMQ connection and subscribe to events"""
        self.subscribe_to_event("trade_validated")

        # Initialize ZMQ
        try:
            await self._connect_mt4()

            self.logger.info(
                "execution_agent_initialized",
                mt4_host=self.mt4_host,
                command_port=self.mt4_command_port,
                max_retry=self.max_retry,
            )

        except Exception as e:
            self.logger.error("initialization_failed", error=str(e), exc_info=True)
            # Don't raise - allow agent to start and retry connection

    async def cleanup(self) -> None:
        """Cleanup ZMQ resources"""
        try:
            await self._disconnect_mt4()

            self.logger.info(
                "execution_agent_cleanup",
                trades_executed=self.trades_executed,
                trades_failed=self.trades_failed,
                avg_slippage=self.total_slippage / max(self.trades_executed, 1),
                retry_count=self.retry_count,
            )

        except Exception as e:
            self.logger.error("cleanup_failed", error=str(e))

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "trade_validated":
                await self._on_trade_validated(event.data)

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_trade_validated(self, trade_data: Dict[str, Any]) -> None:
        """
        Execute validated trade

        Implements retry logic with exponential backoff
        """
        start_time = time.time()

        symbol = trade_data.get("symbol")
        action = trade_data.get("action")
        size = trade_data.get("position_size")

        self.logger.info(
            "executing_trade",
            symbol=symbol,
            action=action,
            size=size,
        )

        # Retry loop
        for attempt in range(1, self.max_retry + 1):
            try:
                # Execute trade
                result = await self._execute_trade(trade_data)

                if result["success"]:
                    # Validate slippage
                    slippage = self._calculate_slippage(
                        trade_data.get("current_price"),
                        result["fill_price"],
                    )

                    if abs(slippage) > self.slippage_tolerance:
                        self.logger.warning(
                            "high_slippage",
                            symbol=symbol,
                            expected=trade_data.get("current_price"),
                            filled=result["fill_price"],
                            slippage=slippage,
                        )

                    self.trades_executed += 1
                    self.total_slippage += abs(slippage)

                    # Emit success
                    execution_data = {
                        **trade_data,
                        "order_id": result.get("order_id"),
                        "fill_price": result.get("fill_price"),
                        "fill_time": result.get("fill_time", time.time()),
                        "slippage": slippage,
                        "attempts": attempt,
                        "execution_time": time.time() - start_time,
                    }

                    await self.publish_event(
                        event_type="trade_executed",
                        data=execution_data,
                        priority=EventPriority.HIGH,
                    )

                    # Store in context
                    await self.set_context(
                        f"executed_trade_{symbol}",
                        execution_data,
                        ttl=3600,
                    )

                    self.logger.info(
                        "trade_executed",
                        symbol=symbol,
                        order_id=result.get("order_id"),
                        fill_price=result.get("fill_price"),
                        slippage=slippage,
                        attempts=attempt,
                        execution_time=time.time() - start_time,
                    )

                    return

                else:
                    # Execution failed
                    error = result.get("error", "unknown_error")

                    if attempt < self.max_retry:
                        # Retry
                        self.retry_count += 1
                        delay = self.retry_delay * (2 ** (attempt - 1))  # Exponential backoff

                        self.logger.warning(
                            "execution_failed_retrying",
                            symbol=symbol,
                            attempt=attempt,
                            max_retry=self.max_retry,
                            error=error,
                            retry_delay=delay,
                        )

                        await asyncio.sleep(delay)
                        continue

                    else:
                        # Max retries reached
                        raise Exception(f"Max retries reached: {error}")

            except Exception as e:
                if attempt < self.max_retry:
                    # Retry on exception
                    self.retry_count += 1
                    delay = self.retry_delay * (2 ** (attempt - 1))

                    self.logger.warning(
                        "execution_exception_retrying",
                        symbol=symbol,
                        attempt=attempt,
                        error=str(e),
                        retry_delay=delay,
                    )

                    await asyncio.sleep(delay)
                    continue

                else:
                    # Max retries reached
                    self.trades_failed += 1

                    # Emit failure
                    await self.publish_event(
                        event_type="trade_failed",
                        data={
                            **trade_data,
                            "error": str(e),
                            "attempts": attempt,
                            "execution_time": time.time() - start_time,
                        },
                        priority=EventPriority.CRITICAL,
                    )

                    self.logger.error(
                        "trade_execution_failed",
                        symbol=symbol,
                        attempts=attempt,
                        error=str(e),
                    )

                    return

    async def _execute_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send trade order to MT4 via ZMQ

        Args:
            trade_data: Trade information

        Returns:
            Execution result with order_id, fill_price, etc.
        """
        if not self.mt4_connected:
            # Try to reconnect
            await self._connect_mt4()

        if not self.mt4_connected:
            return {
                "success": False,
                "error": "MT4 not connected",
            }

        # Build order command
        order_command = {
            "action": "OPEN_TRADE",
            "symbol": trade_data.get("symbol"),
            "type": "BUY" if trade_data.get("action") == "BUY" else "SELL",
            "volume": trade_data.get("position_size", 0.1),
            "price": trade_data.get("current_price"),
            "slippage": int(self.slippage_tolerance * 10000),  # Convert to points
            "stop_loss": trade_data.get("stop_loss", 0),
            "take_profit": trade_data.get("take_profit", 0),
            "comment": f"RiseTrader_{self.agent_id}",
            "magic_number": 12345,
        }

        try:
            # Send to MT4
            await self.zmq_socket.send_json(order_command)

            # Wait for response with timeout
            if await self.zmq_socket.poll(timeout=int(self.timeout * 1000)):
                response = await self.zmq_socket.recv_json()

                return {
                    "success": response.get("success", False),
                    "order_id": response.get("order_id"),
                    "fill_price": response.get("price"),
                    "fill_time": response.get("timestamp"),
                    "error": response.get("error"),
                }

            else:
                # Timeout
                return {
                    "success": False,
                    "error": "MT4 response timeout",
                }

        except zmq.error.ZMQError as e:
            self.logger.error("zmq_error", error=str(e))
            self.mt4_connected = False
            return {
                "success": False,
                "error": f"ZMQ error: {str(e)}",
            }

        except Exception as e:
            self.logger.error("execution_error", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def _connect_mt4(self) -> None:
        """Establish ZMQ connection to MT4"""
        try:
            self.zmq_context = zmq.asyncio.Context()
            self.zmq_socket = self.zmq_context.socket(zmq.REQ)

            # Set socket options
            self.zmq_socket.setsockopt(zmq.LINGER, 0)
            self.zmq_socket.setsockopt(zmq.RCVTIMEO, int(self.timeout * 1000))
            self.zmq_socket.setsockopt(zmq.SNDTIMEO, int(self.timeout * 1000))

            # TODO: Add CurveZMQ encryption if use_encryption=True
            # self.zmq_socket.curve_secretkey = ...
            # self.zmq_socket.curve_publickey = ...
            # self.zmq_socket.curve_serverkey = ...

            # Connect
            endpoint = f"tcp://{self.mt4_host}:{self.mt4_command_port}"
            self.zmq_socket.connect(endpoint)

            self.mt4_connected = True

            self.logger.info(
                "mt4_connected",
                endpoint=endpoint,
                encryption=self.use_encryption,
            )

        except Exception as e:
            self.logger.error("mt4_connection_failed", error=str(e))
            self.mt4_connected = False
            raise

    async def _disconnect_mt4(self) -> None:
        """Close ZMQ connection"""
        if self.zmq_socket:
            self.zmq_socket.close()

        if self.zmq_context:
            self.zmq_context.term()

        self.mt4_connected = False
        self.logger.info("mt4_disconnected")

    def _calculate_slippage(self, expected_price: Optional[float], fill_price: Optional[float]) -> float:
        """
        Calculate slippage as percentage

        Args:
            expected_price: Expected execution price
            fill_price: Actual fill price

        Returns:
            Slippage as decimal (e.g., 0.0001 = 1 pip = 0.01%)
        """
        if not expected_price or not fill_price:
            return 0.0

        try:
            expected = float(expected_price)
            filled = float(fill_price)

            slippage = (filled - expected) / expected

            return slippage

        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
