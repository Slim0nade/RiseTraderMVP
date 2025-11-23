"""
MT4 Integration Service.

High-level service for MT4 integration, orchestrating order submission,
event handling, and database persistence.
"""
import asyncio
from decimal import Decimal
from datetime import datetime
from typing import Dict, Literal, Optional
import uuid

from src.database.repositories.mt4_order_repository import MT4OrderRepository
from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
from src.database.models.mt4_orders import MT4Order
from src.utils.redis_client import (
    MT4RedisClient,
    CHANNEL_ORDER_CONFIRMED,
    CHANNEL_ORDER_REJECTED,
)
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.symbol_loader import SymbolLoader
from src.trading.execution.mt4_models import (
    OrderResponse,
    OrderConfirmedEvent,
    OrderConfirmedData,
    OrderRejectedEvent,
    OrderRejectedData,
)
from src.utils.mt4_helpers import (
    get_mt4_logger,
    generate_correlation_id,
    log_order_submitted,
    log_order_confirmed,
    log_order_rejected,
)
from src.monitoring.mt4_metrics import (
    record_order_submitted,
    record_order_confirmed,
    record_order_rejected,
)


logger = get_mt4_logger("mt4_integration_service")


class MT4IntegrationService:
    """
    High-level service for MT4 integration.

    Orchestrates order submission, event handling, and database persistence.
    Manages multiple MT4Client instances (one per EA/magic_number).
    """

    def __init__(
        self,
        order_repository: MT4OrderRepository,
        redis_client: MT4RedisClient,
        connection_repository: MT4ConnectionRepository,
        symbol_loader: SymbolLoader,
        logger_instance=None
    ):
        """
        Initialize MT4 integration service.

        Args:
            order_repository: Repository for order persistence
            redis_client: Redis client for pub/sub
            connection_repository: Repository for EA connection info
            symbol_loader: Symbol validation loader
            logger_instance: Optional logger override
        """
        self.order_repository = order_repository
        self.redis_client = redis_client
        self.connection_repository = connection_repository
        self.symbol_loader = symbol_loader
        self.logger = logger_instance or logger

        # Cache of MT4Client instances by magic_number
        self._clients: Dict[int, MT4Client] = {}

        # Lock for client creation
        self._client_lock = asyncio.Lock()

        self.logger.info("mt4_integration_service_initialized")

    async def submit_market_order(
        self,
        symbol: str,
        direction: Literal["BUY", "SELL"],
        volume: Decimal,
        magic_number: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        comment: Optional[str] = None
    ) -> MT4Order:
        """
        Submit market order to MT4.

        Flow:
        1. Validate symbol and volume
        2. Get EA connection details
        3. Get/create MT4Client
        4. Create order record (status=PENDING)
        5. Submit order to MT4
        6. Update order status based on response
        7. Publish event to Redis

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL")
            direction: Order direction (BUY or SELL)
            volume: Order volume in lots
            magic_number: MT4 magic number for this EA
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            comment: Optional order comment

        Returns:
            Persisted MT4Order instance

        Raises:
            ValueError: If validation fails or connection not found
            ConnectionError: If MT4 communication fails
        """
        # Generate correlation ID for tracking
        correlation_id = generate_correlation_id()

        self.logger.info(
            "submit_market_order_started",
            correlation_id=correlation_id,
            symbol=symbol,
            direction=direction,
            volume=float(volume),
            magic_number=magic_number
        )

        # Validate symbol
        if not self.symbol_loader.is_valid_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        # Validate direction
        self.symbol_loader.validate_direction(direction)

        # Validate volume
        self.symbol_loader.validate_volume(volume)

        # Get EA connection
        connection = await self.connection_repository.get_by_magic_number(magic_number)
        if not connection:
            raise ValueError(f"Connection not found for magic_number: {magic_number}")

        if connection.status != "ACTIVE":
            raise ValueError(f"Connection not active: {connection.status}")

        # Get or create MT4Client
        client = await self._get_client(magic_number)

        # Create order record (PENDING)
        order_id = str(uuid.uuid4())
        order = await self.order_repository.create(
            order_id=order_id,
            magic_number=magic_number,
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type="MARKET",
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="PENDING",
            submitted_at=datetime.utcnow(),
            correlation_id=correlation_id
        )

        self.logger.info(
            "order_record_created",
            correlation_id=correlation_id,
            order_id=order_id,
            status="PENDING"
        )

        # Submit order to MT4
        try:
            response = await client.create_instant_order(
                symbol=symbol,
                direction=direction,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=comment
            )

            # Log submission
            log_order_submitted(
                logger=self.logger,
                correlation_id=correlation_id,
                ea_id=connection.ea_id,
                order_id=order_id,
                symbol=symbol,
                direction=direction,
                volume=float(volume)
            )

            # Record metrics
            record_order_submitted(
                ea_id=connection.ea_id,
                symbol=symbol,
                direction=direction,
                order_type="MARKET"
            )

            # Handle response
            if response.success:
                # Update order status to CONFIRMED
                order = await self.order_repository.update_status(
                    order_id=order_id,
                    status="CONFIRMED",
                    ticket_number=response.ticket_number,
                    execution_price=response.execution_price,
                    confirmed_at=response.execution_time or datetime.utcnow()
                )

                # Calculate latency
                latency_ms = order.calculate_latency_ms() if order.confirmed_at else 0

                # Log confirmation
                log_order_confirmed(
                    logger=self.logger,
                    correlation_id=correlation_id,
                    ea_id=connection.ea_id,
                    order_id=order_id,
                    ticket_number=response.ticket_number,
                    latency_ms=latency_ms
                )

                # Record metrics
                record_order_confirmed(
                    ea_id=connection.ea_id,
                    symbol=symbol,
                    direction=direction,
                    latency_seconds=latency_ms / 1000 if latency_ms else 0
                )

                # Publish confirmed event
                await self._publish_order_confirmed_event(order, response, connection.ea_id)

            else:
                # Order rejected
                error_code = response.error_code or 0
                error_message = response.error_message or "Order rejected by MT4"

                # Update order status to REJECTED
                order = await self.order_repository.update_status(
                    order_id=order_id,
                    status="REJECTED",
                    error_message=error_message
                )

                # Log rejection
                log_order_rejected(
                    logger=self.logger,
                    correlation_id=correlation_id,
                    ea_id=connection.ea_id,
                    order_id=order_id,
                    error_code=error_code,
                    error_message=error_message
                )

                # Record metrics
                record_order_rejected(
                    ea_id=connection.ea_id,
                    symbol=symbol,
                    error_code=str(error_code)
                )

                # Publish rejected event
                await self._publish_order_rejected_event(order, error_code, error_message, connection.ea_id)

            return order

        except Exception as e:
            # Update order status to REJECTED with error
            error_message = f"Exception during order submission: {str(e)}"
            order = await self.order_repository.update_status(
                order_id=order_id,
                status="REJECTED",
                error_message=error_message
            )

            self.logger.error(
                "order_submission_error",
                correlation_id=correlation_id,
                order_id=order_id,
                error=str(e)
            )

            raise

    async def handle_order_confirmed_event(self, event_data: dict) -> None:
        """
        Handle order_confirmed event from MT4 EA.

        This is called when the EA publishes a confirmation via PUB socket.
        Updates database order status to CONFIRMED.

        Args:
            event_data: Event data dictionary
        """
        try:
            event = OrderConfirmedEvent(**event_data)

            # Find order by ticket_number
            order = await self.order_repository.get_by_ticket_number(
                event.data.ticket_number
            )

            if not order:
                self.logger.warning(
                    "order_not_found_for_confirmation",
                    ticket_number=event.data.ticket_number
                )
                return

            # Update to CONFIRMED if still PENDING
            if order.status == "PENDING":
                await self.order_repository.update_status(
                    order_id=order.order_id,
                    status="CONFIRMED",
                    ticket_number=event.data.ticket_number,
                    execution_price=event.data.execution_price,
                    confirmed_at=event.data.execution_time
                )

                # Calculate latency
                latency_ms = order.calculate_latency_ms() if order.confirmed_at else 0

                # Record metrics
                record_order_confirmed(
                    ea_id=f"ea_{order.magic_number}",
                    symbol=order.symbol,
                    direction=order.direction,
                    latency_seconds=latency_ms / 1000 if latency_ms else 0
                )

                self.logger.info(
                    "order_confirmed_via_event",
                    order_id=order.order_id,
                    ticket_number=event.data.ticket_number,
                    latency_ms=latency_ms
                )

        except Exception as e:
            self.logger.error(
                "handle_order_confirmed_error",
                error=str(e),
                event_data=event_data
            )

    async def handle_order_rejected_event(self, event_data: dict) -> None:
        """
        Handle order_rejected event from MT4 EA.

        Updates database order status to REJECTED and publishes to Redis.

        Args:
            event_data: Event data dictionary
        """
        try:
            event = OrderRejectedEvent(**event_data)

            # Find order by order_id
            order = await self.order_repository.get_by_order_id(
                event.data.order_id
            )

            if not order:
                self.logger.warning(
                    "order_not_found_for_rejection",
                    order_id=event.data.order_id
                )
                return

            # Update to REJECTED
            await self.order_repository.update_status(
                order_id=order.order_id,
                status="REJECTED",
                error_message=event.data.error_message
            )

            # Record metrics
            record_order_rejected(
                ea_id=f"ea_{order.magic_number}",
                symbol=order.symbol,
                error_code=str(event.data.error_code)
            )

            # Publish rejection event to Redis
            await self.redis_client.publish_event(
                channel=CHANNEL_ORDER_REJECTED,
                event=event.model_dump(mode='json')
            )

            self.logger.warning(
                "order_rejected_via_event",
                order_id=order.order_id,
                error_code=event.data.error_code,
                error_message=event.data.error_message
            )

        except Exception as e:
            self.logger.error(
                "handle_order_rejected_error",
                error=str(e),
                event_data=event_data
            )

    async def _get_client(self, magic_number: int) -> MT4Client:
        """
        Get or create MT4Client for the given magic_number.

        Args:
            magic_number: MT4 magic number

        Returns:
            MT4Client instance

        Raises:
            ValueError: If connection not found
        """
        # Check cache
        if magic_number in self._clients:
            return self._clients[magic_number]

        # Create new client (thread-safe)
        async with self._client_lock:
            # Double-check after acquiring lock
            if magic_number in self._clients:
                return self._clients[magic_number]

            # Get connection details
            connection = await self.connection_repository.get_by_magic_number(magic_number)
            if not connection:
                raise ValueError(f"Connection not found for magic_number: {magic_number}")

            # Create encryption manager
            encryption_manager = MT4EncryptionManager(
                encryption_enabled=connection.encryption_enabled
            )

            # Create MT4Client
            client = MT4Client(
                host=connection.mt4_server_host,
                rep_port=connection.rep_port,
                pub_port=connection.pub_port,
                magic_number=magic_number,
                encryption_manager=encryption_manager
            )

            # Connect
            await client.connect()

            # Refresh symbols if loader is empty
            if len(self.symbol_loader.get_symbols()) == 0:
                await self.symbol_loader.refresh_symbols(client)

            # Cache client
            self._clients[magic_number] = client

            self.logger.info(
                "mt4_client_created_and_cached",
                magic_number=magic_number,
                host=connection.mt4_server_host,
                rep_port=connection.rep_port
            )

            return client

    async def _publish_order_confirmed_event(
        self,
        order: MT4Order,
        response: OrderResponse,
        ea_id: str
    ) -> None:
        """
        Publish order_confirmed event to Redis.

        Args:
            order: MT4Order instance
            response: OrderResponse from MT4
            ea_id: EA identifier
        """
        event = OrderConfirmedEvent(
            correlation_id=order.correlation_id,
            data=OrderConfirmedData(
                order_id=order.order_id,
                magic_number=order.magic_number,
                ticket_number=response.ticket_number,
                symbol=order.symbol,
                direction=order.direction,
                volume=order.volume,
                execution_price=response.execution_price,
                execution_time=response.execution_time or datetime.utcnow()
            )
        )

        await self.redis_client.publish_event(
            channel=CHANNEL_ORDER_CONFIRMED,
            event=event.model_dump(mode='json')
        )

        self.logger.debug(
            "order_confirmed_event_published",
            correlation_id=order.correlation_id,
            channel=CHANNEL_ORDER_CONFIRMED
        )

    async def _publish_order_rejected_event(
        self,
        order: MT4Order,
        error_code: int,
        error_message: str,
        ea_id: str
    ) -> None:
        """
        Publish order_rejected event to Redis.

        Args:
            order: MT4Order instance
            error_code: MT4 error code
            error_message: Error message
            ea_id: EA identifier
        """
        event = OrderRejectedEvent(
            correlation_id=order.correlation_id,
            data=OrderRejectedData(
                order_id=order.order_id,
                magic_number=order.magic_number,
                symbol=order.symbol,
                error_code=error_code,
                error_message=error_message
            )
        )

        await self.redis_client.publish_event(
            channel=CHANNEL_ORDER_REJECTED,
            event=event.model_dump(mode='json')
        )

        self.logger.debug(
            "order_rejected_event_published",
            correlation_id=order.correlation_id,
            channel=CHANNEL_ORDER_REJECTED
        )

    async def cleanup(self) -> None:
        """Cleanup resources - disconnect all clients."""
        self.logger.info("cleaning_up_mt4_clients", count=len(self._clients))

        for magic_number, client in self._clients.items():
            try:
                await client.disconnect()
                self.logger.info("client_disconnected", magic_number=magic_number)
            except Exception as e:
                self.logger.error(
                    "client_disconnect_error",
                    magic_number=magic_number,
                    error=str(e)
                )

        self._clients.clear()
