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
    CHANNEL_POSITION_UPDATED,
    CHANNEL_POSITION_CLOSED,
    CHANNEL_MARKET_TICK,
)

# Portfolio risk event channel
CHANNEL_PORTFOLIO_RISK_UPDATED = "portfolio_risk_updated"
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.symbol_loader import SymbolLoader
from src.trading.execution.mt4_connection_pool import MT4ConnectionPool
from src.trading.execution.mt4_models import (
    OrderResponse,
    OrderConfirmedEvent,
    OrderConfirmedData,
    OrderRejectedEvent,
    OrderRejectedData,
    PositionUpdatedEvent,
    PositionUpdatedData,
    PositionClosedEvent,
    PositionClosedData,
    MarketTickEvent,
    MarketTick,
    PortfolioRiskState,
    PortfolioRiskUpdatedEvent,
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
    update_position_pnl,
    record_position_closed,
    record_market_tick,
    update_portfolio_metrics,
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
        connection_pool: Optional[MT4ConnectionPool] = None,
        logger_instance=None
    ):
        """
        Initialize MT4 integration service.

        Args:
            order_repository: Repository for order persistence
            redis_client: Redis client for pub/sub
            connection_repository: Repository for EA connection info
            symbol_loader: Symbol validation loader
            connection_pool: Optional connection pool for multi-EA management
            logger_instance: Optional logger override
        """
        self.order_repository = order_repository
        self.redis_client = redis_client
        self.connection_repository = connection_repository
        self.symbol_loader = symbol_loader
        self.connection_pool = connection_pool or MT4ConnectionPool()
        self.logger = logger_instance or logger

        # Cache of MT4Client instances by magic_number
        self._clients: Dict[int, MT4Client] = {}

        # Lock for client creation
        self._client_lock = asyncio.Lock()

        # Connection health tracking (last tick timestamp by magic_number)
        self._last_tick_timestamp: Dict[int, datetime] = {}

        # Portfolio risk cache (T071)
        self._portfolio_risk_cache: Optional[PortfolioRiskState] = None
        self._portfolio_cache_lock = asyncio.Lock()

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

    async def handle_position_updated_event(
        self,
        event_data: dict,
        position_repository=None
    ) -> None:
        """
        Handle position_updated event from MT4 EA.

        Updates position P&L and current price in the database.
        Publishes event to Redis for monitoring and agent consumption.

        Args:
            event_data: Event data dictionary
            position_repository: Optional MT4PositionRepository instance

        Raises:
            ValueError: If position_repository is not provided
        """
        if position_repository is None:
            self.logger.error(
                "position_repository_not_provided",
                event_type="position_updated"
            )
            raise ValueError("position_repository is required for position update handling")

        try:
            # Parse event
            event = PositionUpdatedEvent(**event_data)

            self.logger.debug(
                "position_updated_event_received",
                ticket_number=event.data.ticket_number,
                symbol=event.data.symbol,
                unrealized_pnl=float(event.data.unrealized_pnl),
                current_price=float(event.data.current_price)
            )

            # Upsert position in database
            position = await position_repository.upsert_position(
                ticket_number=event.data.ticket_number,
                magic_number=event.data.magic_number,
                symbol=event.data.symbol,
                direction=event.data.direction,
                volume=event.data.volume,
                open_price=event.data.open_price,
                current_price=event.data.current_price,
                unrealized_pnl=event.data.unrealized_pnl,
                stop_loss=event.data.stop_loss,
                take_profit=event.data.take_profit,
                open_time=event.data.open_time,
                last_updated=event.data.last_updated
            )

            # Publish to Redis for monitoring
            await self.redis_client.publish_event(
                channel=CHANNEL_POSITION_UPDATED,
                event=event.model_dump(mode='json')
            )

            # Update metrics
            ea_id = f"ea_{event.data.magic_number}"
            update_position_pnl(
                ea_id=ea_id,
                ticket_number=event.data.ticket_number,
                symbol=event.data.symbol,
                pnl=float(event.data.unrealized_pnl)
            )

            self.logger.info(
                "position_updated_handled",
                ticket_number=event.data.ticket_number,
                position_id=str(position.id),
                unrealized_pnl=float(event.data.unrealized_pnl)
            )

        except Exception as e:
            self.logger.error(
                "handle_position_updated_error",
                error=str(e),
                event_data=event_data
            )

    async def handle_position_closed_event(
        self,
        event_data: dict,
        position_repository=None
    ) -> None:
        """
        Handle position_closed event from MT4 EA.

        Removes position from open positions table, updates related order status,
        and publishes event to Redis.

        Args:
            event_data: Event data dictionary
            position_repository: Optional MT4PositionRepository instance

        Raises:
            ValueError: If position_repository is not provided
        """
        if position_repository is None:
            self.logger.error(
                "position_repository_not_provided",
                event_type="position_closed"
            )
            raise ValueError("position_repository is required for position close handling")

        try:
            # Parse event
            event = PositionClosedEvent(**event_data)

            self.logger.debug(
                "position_closed_event_received",
                ticket_number=event.data.ticket_number,
                symbol=event.data.symbol,
                realized_pnl=float(event.data.realized_pnl),
                close_reason=event.data.close_reason
            )

            # Get position from database
            position = await position_repository.get_by_ticket_number(
                event.data.ticket_number
            )

            if not position:
                self.logger.warning(
                    "position_not_found_for_closure",
                    ticket_number=event.data.ticket_number
                )
                # Still publish event even if position not found
                await self.redis_client.publish_event(
                    channel=CHANNEL_POSITION_CLOSED,
                    event=event.model_dump(mode='json')
                )
                return

            # Update related order status to CLOSED (if exists)
            if position.order_id:
                order = await self.order_repository.get_by_id(position.order_id)
                if order and order.status == "CONFIRMED":
                    await self.order_repository.update_status(
                        order_id=str(position.order_id),
                        status="CLOSED",
                        realized_pnl=event.data.realized_pnl
                    )

            # Delete position from open positions
            await position_repository.delete_position(event.data.ticket_number)

            # Publish to Redis
            await self.redis_client.publish_event(
                channel=CHANNEL_POSITION_CLOSED,
                event=event.model_dump(mode='json')
            )

            # Record metrics
            ea_id = f"ea_{event.data.magic_number}"
            holding_time_seconds = (
                event.data.close_time - event.data.open_time
            ).total_seconds()
            record_position_closed(
                ea_id=ea_id,
                symbol=event.data.symbol,
                close_reason=event.data.close_reason,
                holding_time_seconds=holding_time_seconds
            )

            self.logger.info(
                "position_closed_handled",
                ticket_number=event.data.ticket_number,
                realized_pnl=float(event.data.realized_pnl),
                close_reason=event.data.close_reason
            )

        except Exception as e:
            self.logger.error(
                "handle_position_closed_error",
                error=str(e),
                event_data=event_data
            )

    async def subscribe_to_market_data(
        self,
        magic_number: int,
        symbols: Optional[list[str]] = None
    ) -> None:
        """
        Subscribe to market data for specific symbols or all symbols.

        Args:
            magic_number: MT4 magic number (EA identifier)
            symbols: List of symbols to subscribe to (None = all symbols)

        Raises:
            ValueError: If connection not found
            ConnectionError: If MT4 communication fails
        """
        # Get client
        client = await self._get_client(magic_number)

        # Subscribe to market_tick events (with optional symbol filter)
        topics = ["market_tick"] if not symbols else [f"market_tick_{s}" for s in symbols]
        await client.subscribe_to_events(topics=topics)

        self.logger.info(
            "subscribed_to_market_data",
            magic_number=magic_number,
            symbols=symbols or "ALL",
            topic_count=len(topics)
        )

    async def unsubscribe_from_market_data(
        self,
        magic_number: int,
        symbols: Optional[list[str]] = None
    ) -> None:
        """
        Unsubscribe from market data for specific symbols or all symbols.

        Args:
            magic_number: MT4 magic number
            symbols: List of symbols to unsubscribe from (None = all)

        Raises:
            ValueError: If connection not found
        """
        # Check if client exists
        if magic_number not in self._clients:
            self.logger.warning(
                "unsubscribe_client_not_found",
                magic_number=magic_number
            )
            return

        client = self._clients[magic_number]

        # Unsubscribe from topics
        topics = None if not symbols else [f"market_tick_{s}" for s in symbols]
        await client.unsubscribe_from_events(topics=topics)

        self.logger.info(
            "unsubscribed_from_market_data",
            magic_number=magic_number,
            symbols=symbols or "ALL"
        )

    async def handle_market_tick_event(self, event_data: dict) -> None:
        """
        Handle market_tick event from MT4 EA.

        Processes real-time market ticks, publishes to Redis for signal generation,
        and records metrics for latency tracking.

        Args:
            event_data: Event data dictionary

        Raises:
            ValidationError: If event data doesn't match schema
        """
        try:
            # Parse event
            event = MarketTickEvent(**event_data)

            self.logger.debug(
                "market_tick_received",
                symbol=event.data.symbol,
                bid=float(event.data.bid),
                ask=float(event.data.ask),
                timestamp=event.data.timestamp.isoformat()
            )

            # Calculate latency (time from MT4 tick to now)
            reception_time = datetime.utcnow()
            latency_seconds = (reception_time - event.data.timestamp).total_seconds()

            # Update connection health timestamp (extract magic_number if available)
            # Note: MT4 EA should include magic_number in tick events for proper tracking
            if hasattr(event, 'magic_number'):
                self._last_tick_timestamp[event.magic_number] = reception_time

            # Publish to Redis for signal generators and monitoring
            await self.redis_client.publish_event(
                channel=CHANNEL_MARKET_TICK,
                event=event.model_dump(mode='json')
            )

            # Record metrics
            record_market_tick(
                symbol=event.data.symbol,
                latency_seconds=latency_seconds
            )

            self.logger.debug(
                "market_tick_processed",
                symbol=event.data.symbol,
                latency_ms=latency_seconds * 1000,
                correlation_id=event.correlation_id
            )

        except Exception as e:
            self.logger.error(
                "handle_market_tick_error",
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

    async def register_ea(
        self,
        ea_id: str,
        symbol: str,
        host: str = "localhost",
        **kwargs
    ) -> Dict[str, any]:
        """
        Register a new Expert Advisor in the connection pool (T067).

        Allocates magic number and port pair, registers in pool and database.

        Args:
            ea_id: Unique EA identifier
            symbol: Trading symbol for this EA
            host: MT4 server host (default: localhost)
            **kwargs: Additional EA metadata (e.g., strategy_name, max_positions)

        Returns:
            Dictionary with registration details:
            - ea_id: EA identifier
            - magic_number: Allocated magic number
            - rep_port: REP socket port
            - pub_port: PUB socket port
            - host: MT4 server host
            - symbol: Trading symbol

        Raises:
            ValueError: If EA already registered
            RuntimeError: If resource allocation fails
        """
        self.logger.info(
            "registering_ea",
            ea_id=ea_id,
            symbol=symbol,
            host=host
        )

        try:
            # Allocate magic number
            magic_number = self.connection_pool.allocate_magic_number()

            # Allocate port pair
            rep_port, pub_port = self.connection_pool.allocate_ports()

            # Register in connection pool
            self.connection_pool.register_ea(
                ea_id=ea_id,
                magic_number=magic_number,
                rep_port=rep_port,
                pub_port=pub_port,
                host=host,
                symbol=symbol,
                **kwargs
            )

            # Persist to database
            await self.connection_repository.create(
                ea_id=ea_id,
                magic_number=magic_number,
                rep_port=rep_port,
                pub_port=pub_port,
                mt4_server_host=host,
                status="ACTIVE",
                encryption_enabled=True
            )

            self.logger.info(
                "ea_registered",
                ea_id=ea_id,
                magic_number=magic_number,
                rep_port=rep_port,
                pub_port=pub_port
            )

            return {
                "ea_id": ea_id,
                "magic_number": magic_number,
                "rep_port": rep_port,
                "pub_port": pub_port,
                "host": host,
                "symbol": symbol
            }

        except Exception as e:
            self.logger.error(
                "ea_registration_failed",
                ea_id=ea_id,
                error=str(e)
            )
            raise

    async def unregister_ea(self, ea_id: str) -> None:
        """
        Unregister EA and release resources (T067).

        Args:
            ea_id: EA identifier to unregister
        """
        self.logger.info("unregistering_ea", ea_id=ea_id)

        try:
            # Get EA info before unregistration
            ea_info = self.connection_pool.get_ea_info(ea_id)
            if not ea_info:
                self.logger.warning("ea_not_found_for_unregistration", ea_id=ea_id)
                return

            magic_number = ea_info["magic_number"]

            # Disconnect client if exists
            if magic_number in self._clients:
                client = self._clients[magic_number]
                await client.disconnect()
                del self._clients[magic_number]

            # Unregister from pool (releases resources)
            self.connection_pool.unregister_ea(ea_id)

            # Update database status
            await self.connection_repository.update_status(
                magic_number=magic_number,
                status="INACTIVE"
            )

            self.logger.info("ea_unregistered", ea_id=ea_id, magic_number=magic_number)

        except Exception as e:
            self.logger.error(
                "ea_unregistration_failed",
                ea_id=ea_id,
                error=str(e)
            )
            raise

    async def calculate_portfolio_risk(
        self,
        position_repository
    ) -> PortfolioRiskState:
        """
        Calculate portfolio-level risk aggregation across all EAs (T070).

        Aggregates positions from all registered EAs and calculates:
        - Total unrealized P&L
        - Exposure by symbol
        - Exposure by EA
        - Position count

        Args:
            position_repository: MT4PositionRepository instance

        Returns:
            PortfolioRiskState with aggregated risk metrics

        Raises:
            ValueError: If position_repository is not provided
        """
        if position_repository is None:
            raise ValueError("position_repository is required for portfolio risk calculation")

        self.logger.debug("calculating_portfolio_risk")

        try:
            # Get all open positions from database
            all_positions = await position_repository.get_all_open_positions()

            # Initialize aggregations
            total_unrealized_pnl = Decimal("0")
            total_positions = 0
            exposure_by_symbol: Dict[str, Decimal] = {}
            exposure_by_ea: Dict[str, Decimal] = {}

            # Aggregate across all positions
            for position in all_positions:
                # Total P&L
                total_unrealized_pnl += position.unrealized_pnl or Decimal("0")
                total_positions += 1

                # Symbol exposure (notional value = volume * current_price)
                symbol = position.symbol
                notional = (position.volume or Decimal("0")) * (position.current_price or Decimal("0"))
                if symbol not in exposure_by_symbol:
                    exposure_by_symbol[symbol] = Decimal("0")
                exposure_by_symbol[symbol] += notional

                # EA exposure (by magic number)
                ea_id = str(position.magic_number)
                if ea_id not in exposure_by_ea:
                    exposure_by_ea[ea_id] = Decimal("0")
                exposure_by_ea[ea_id] += notional

            # Create portfolio risk state
            # Note: For now, we use simplified equity/margin calculations
            # In production, these would come from MT4 account info
            total_equity = Decimal("10000.00")  # Placeholder - should come from account info
            total_margin_used = sum(exposure_by_ea.values()) * Decimal("0.01")  # 1% margin estimate
            margin_level = (total_equity / total_margin_used * 100) if total_margin_used > 0 else Decimal("999.99")

            portfolio_risk = PortfolioRiskState(
                total_equity=total_equity,
                total_margin_used=total_margin_used,
                margin_level=margin_level,
                total_open_positions=total_positions,
                exposure_by_symbol=exposure_by_symbol,
                exposure_by_ea=exposure_by_ea,
                last_updated=datetime.utcnow()
            )

            self.logger.info(
                "portfolio_risk_calculated",
                total_positions=total_positions,
                total_unrealized_pnl=float(total_unrealized_pnl),
                margin_level=float(margin_level)
            )

            return portfolio_risk

        except Exception as e:
            self.logger.error(
                "portfolio_risk_calculation_error",
                error=str(e)
            )
            raise

    async def get_cached_portfolio_risk(
        self,
        cache_ttl_seconds: int = 5
    ) -> Optional[PortfolioRiskState]:
        """
        Get cached portfolio risk state (T071).

        Returns cached portfolio risk if available and not expired.

        Args:
            cache_ttl_seconds: Cache TTL in seconds (default: 5s)

        Returns:
            Cached PortfolioRiskState or None if expired/not available
        """
        async with self._portfolio_cache_lock:
            if self._portfolio_risk_cache is None:
                return None

            # Check if cache is still valid
            age_seconds = (datetime.utcnow() - self._portfolio_risk_cache.last_updated).total_seconds()
            if age_seconds > cache_ttl_seconds:
                self.logger.debug("portfolio_cache_expired", age_seconds=age_seconds)
                return None

            self.logger.debug("portfolio_cache_hit", age_seconds=age_seconds)
            return self._portfolio_risk_cache

    async def update_portfolio_risk_cache(
        self,
        position_repository,
        publish_event: bool = True
    ) -> PortfolioRiskState:
        """
        Update portfolio risk cache and optionally publish event (T071 + T073 + T074).

        Calculates fresh portfolio risk, updates cache, publishes to Redis,
        and updates Prometheus metrics.

        Args:
            position_repository: MT4PositionRepository instance
            publish_event: Whether to publish portfolio_risk_updated event

        Returns:
            Updated PortfolioRiskState
        """
        self.logger.debug("updating_portfolio_risk_cache")

        try:
            # Calculate fresh portfolio risk
            risk_state = await self.calculate_portfolio_risk(position_repository)

            # Update cache
            async with self._portfolio_cache_lock:
                self._portfolio_risk_cache = risk_state

            # Update Prometheus metrics (T074)
            update_portfolio_metrics(
                total_equity=float(risk_state.total_equity),
                total_margin_used=float(risk_state.total_margin_used),
                margin_level=float(risk_state.margin_level),
                exposure_by_symbol=risk_state.exposure_by_symbol,
                exposure_by_ea=risk_state.exposure_by_ea
            )

            # Publish event if requested
            if publish_event:
                await self._publish_portfolio_risk_event(risk_state)

            self.logger.info(
                "portfolio_risk_cache_updated",
                total_positions=risk_state.total_open_positions,
                margin_level=float(risk_state.margin_level)
            )

            return risk_state

        except Exception as e:
            self.logger.error(
                "portfolio_risk_cache_update_error",
                error=str(e)
            )
            raise

    async def validate_portfolio_risk_limits(
        self,
        position_repository,
        max_total_loss: Decimal = Decimal("1000.00"),
        max_positions: int = 20,
        min_margin_level: Decimal = Decimal("120.00")
    ) -> Dict[str, any]:
        """
        Validate portfolio-level risk limits (T072).

        Checks:
        - Total unrealized loss doesn't exceed max_total_loss
        - Total open positions doesn't exceed max_positions
        - Margin level stays above min_margin_level

        Args:
            position_repository: MT4PositionRepository instance
            max_total_loss: Maximum allowed portfolio loss
            max_positions: Maximum number of open positions
            min_margin_level: Minimum margin level percentage

        Returns:
            Dictionary with validation results:
            - valid: bool - Overall validation result
            - violations: List of violation messages
            - risk_state: PortfolioRiskState - Current risk state

        """
        self.logger.debug("validating_portfolio_risk_limits")

        try:
            # Calculate current portfolio risk
            risk_state = await self.calculate_portfolio_risk(position_repository)

            violations = []

            # Check total positions
            if risk_state.total_open_positions > max_positions:
                violations.append(
                    f"Total positions ({risk_state.total_open_positions}) exceeds limit ({max_positions})"
                )

            # Check margin level
            if risk_state.margin_level < min_margin_level:
                violations.append(
                    f"Margin level ({risk_state.margin_level}%) below minimum ({min_margin_level}%)"
                )

            # Check if margin is critical
            if risk_state.is_margin_critical:
                violations.append(
                    f"Margin level is critical: {risk_state.margin_level}%"
                )

            is_valid = len(violations) == 0

            self.logger.info(
                "portfolio_risk_validation_complete",
                valid=is_valid,
                violations_count=len(violations)
            )

            return {
                "valid": is_valid,
                "violations": violations,
                "risk_state": risk_state
            }

        except Exception as e:
            self.logger.error(
                "portfolio_risk_validation_error",
                error=str(e)
            )
            raise

    async def _publish_portfolio_risk_event(
        self,
        risk_state: PortfolioRiskState
    ) -> None:
        """
        Publish portfolio_risk_updated event to Redis (T073).

        Args:
            risk_state: PortfolioRiskState to publish
        """
        try:
            event = PortfolioRiskUpdatedEvent(
                correlation_id=generate_correlation_id(),
                data=risk_state
            )

            await self.redis_client.publish_event(
                channel=CHANNEL_PORTFOLIO_RISK_UPDATED,
                event=event.model_dump(mode='json')
            )

            self.logger.debug(
                "portfolio_risk_event_published",
                channel=CHANNEL_PORTFOLIO_RISK_UPDATED,
                total_positions=risk_state.total_open_positions
            )

        except Exception as e:
            self.logger.error(
                "portfolio_risk_event_publish_error",
                error=str(e)
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

    def check_connection_health(
        self,
        magic_number: int,
        max_stale_seconds: int = 60
    ) -> Dict[str, any]:
        """
        Check connection health based on last tick timestamp.

        Args:
            magic_number: MT4 magic number to check
            max_stale_seconds: Maximum seconds since last tick before considered stale

        Returns:
            Dictionary with health status:
            - is_healthy: bool
            - last_tick: datetime or None
            - seconds_since_tick: float or None
            - status: str ("healthy", "stale", "unknown")
        """
        if magic_number not in self._last_tick_timestamp:
            return {
                "is_healthy": False,
                "last_tick": None,
                "seconds_since_tick": None,
                "status": "unknown",
                "message": "No ticks received yet"
            }

        last_tick = self._last_tick_timestamp[magic_number]
        now = datetime.utcnow()
        seconds_since_tick = (now - last_tick).total_seconds()

        is_healthy = seconds_since_tick <= max_stale_seconds

        return {
            "is_healthy": is_healthy,
            "last_tick": last_tick,
            "seconds_since_tick": seconds_since_tick,
            "status": "healthy" if is_healthy else "stale",
            "message": f"Last tick {seconds_since_tick:.1f}s ago"
        }
