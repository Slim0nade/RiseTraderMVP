"""
MT4 Real-Time Sync Service

Background service that continuously syncs MT4 account and position data
to the database for dashboard display.

Runs on a configurable interval (default: 60 seconds).
"""
import asyncio
from datetime import datetime
from typing import List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config.network_config import get_network_manager
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.mt4_models import (
    GetAccountInfoCommand,
    GetOpenPositionsCommand,
)
from src.database.models.account import AccountInfo
from src.database.models.positions import OpenPosition
from src.database.models.market_data import MarketData
from src.database.repositories.market_data_repository import MarketDataRepository

logger = structlog.get_logger(__name__)


class MT4SyncService:
    """
    Background service for real-time MT4 data synchronization.

    Continuously queries MT4 for:
    - Account information (balance, equity, margin, profit)
    - Open positions (tickets, symbols, P&L)

    Updates database every `sync_interval_seconds`.
    """

    def __init__(
        self,
        sync_interval_seconds: int = 60,
        enable_position_sync: bool = True,
        enable_account_sync: bool = True,
        enable_market_data_stream: bool = True,
    ):
        """
        Initialize MT4 sync service.

        Args:
            sync_interval_seconds: Seconds between sync cycles
            enable_position_sync: Enable position synchronization
            enable_account_sync: Enable account info synchronization
            enable_market_data_stream: Enable real-time market data streaming
        """
        self.sync_interval = sync_interval_seconds
        self.enable_position_sync = enable_position_sync
        self.enable_account_sync = enable_account_sync
        self.enable_market_data_stream = enable_market_data_stream

        self.mt4_client: Optional[MT4Client] = None
        self.engine = None
        self.async_session = None
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None
        self._stream_task: Optional[asyncio.Task] = None

        logger.info(
            "mt4_sync_service_initialized",
            interval=sync_interval_seconds,
            positions_enabled=enable_position_sync,
            account_enabled=enable_account_sync,
            market_data_stream_enabled=enable_market_data_stream,
        )

    async def start(self):
        """Start the sync service."""
        if self.running:
            logger.warning("mt4_sync_service_already_running")
            return

        logger.info("mt4_sync_service_starting")

        # Import settings here to avoid circular import
        from src.api.config import settings

        # Create database engine
        self.engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

        # Create session factory
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create MT4 client with proper configuration
        network_manager = get_network_manager()
        mt4_config = network_manager.get_mt4_config()

        # Create encryption manager (disabled for now - will be enabled later)
        encryption_manager = MT4EncryptionManager(encryption_enabled=False)

        self.mt4_client = MT4Client(
            host=mt4_config.host,
            rep_port=mt4_config.command_port,
            pub_port=mt4_config.stream_port,
            magic_number=0,  # Default magic number
            encryption_manager=encryption_manager,
            timeout_ms=10000,  # 10 second timeout
        )

        try:
            # Initialize MT4 connection
            await self.mt4_client.connect()
            logger.info("mt4_client_connected_for_sync", host=mt4_config.host)

            # Start background sync loop
            self.running = True
            self._sync_task = asyncio.create_task(self._sync_loop())

            # Start market data stream listener
            if self.enable_market_data_stream:
                self._stream_task = asyncio.create_task(self._stream_loop())
                logger.info("mt4_market_data_stream_started")

            logger.info("mt4_sync_service_started")

        except Exception as e:
            logger.error("mt4_sync_service_start_failed", error=str(e), exc_info=True)
            await self.stop()
            raise

    async def stop(self):
        """Stop the sync service."""
        if not self.running:
            return

        logger.info("mt4_sync_service_stopping")
        self.running = False

        # Cancel sync task
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        # Cancel stream task
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

        # Cleanup MT4 client
        if self.mt4_client:
            await self.mt4_client.disconnect()

        # Cleanup database
        if self.engine:
            await self.engine.dispose()

        logger.info("mt4_sync_service_stopped")

    async def _sync_loop(self):
        """Main sync loop - runs continuously."""
        logger.info("mt4_sync_loop_started", interval=self.sync_interval)

        while self.running:
            try:
                sync_start = datetime.utcnow()

                # Perform sync cycle
                async with self.async_session() as session:
                    account_synced = False
                    positions_synced = False

                    # Sync account info
                    if self.enable_account_sync:
                        account_synced = await self._sync_account(session)

                    # Sync positions
                    if self.enable_position_sync:
                        positions_synced = await self._sync_positions(session)

                sync_duration = (datetime.utcnow() - sync_start).total_seconds()

                logger.info(
                    "mt4_sync_cycle_completed",
                    duration_seconds=round(sync_duration, 2),
                    account_synced=account_synced,
                    positions_synced=positions_synced,
                )

                # Wait for next cycle
                await asyncio.sleep(self.sync_interval)

            except asyncio.CancelledError:
                logger.info("mt4_sync_loop_cancelled")
                break

            except Exception as e:
                logger.error(
                    "mt4_sync_cycle_failed",
                    error=str(e),
                    exc_info=True,
                )
                # Brief pause before retry
                await asyncio.sleep(5)

    async def _sync_account(self, session: AsyncSession) -> bool:
        """Sync account information from MT4."""
        try:
            # Query MT4
            command = GetAccountInfoCommand()
            response = await self.mt4_client.send_command(command)

            # Handle both response formats:
            # New format: {"success": true, "data": {...}}
            # Old format: {"status": "OK", "account_info": {...}}
            is_success = response.get("success", False) or response.get("status") == "OK"

            if not response or not is_success:
                logger.warning("mt4_account_query_failed", response=response)
                return False

            # Extract data from either format
            data = response.get("data", {}) or response.get("account_info", {})

            # Create record (AccountInfo model only has time, balance, equity, margin, free_margin, margin_level)
            # Handle both snake_case and camelCase field names from MT4
            from datetime import datetime
            account = AccountInfo(
                time=datetime.utcnow(),
                balance=data.get("balance", 0.0),
                equity=data.get("equity", 0.0),
                margin=data.get("margin", 0.0),
                free_margin=data.get("free_margin") or data.get("freeMargin", 0.0),
                margin_level=data.get("margin_level") or data.get("marginLevel", 0.0),
            )

            session.add(account)
            await session.commit()

            logger.debug(
                "account_synced",
                balance=float(account.balance),
                equity=float(account.equity),
                margin_level=float(account.margin_level),
            )

            return True

        except Exception as e:
            logger.error("sync_account_failed", error=str(e))
            await session.rollback()
            return False

    async def _sync_positions(self, session: AsyncSession) -> bool:
        """
        Sync open positions from MT4.

        Clean architecture:
        1. Fetch current positions from MT4
        2. Compare with database to find disappeared positions
        3. Archive disappeared positions to trading_history (with close data)
        4. Delete disappeared positions from open_positions
        5. Upsert remaining positions
        """
        try:
            # Query MT4 for current open positions
            command = GetOpenPositionsCommand()
            response = await self.mt4_client.send_command(command)

            # Handle both response formats
            is_success = response.get("success", False) or response.get("status") == "OK"
            if not response or not is_success:
                logger.warning("mt4_positions_query_failed", response=response)
                return False

            # Extract positions from either format
            if "data" in response:
                positions_data = response.get("data", {}).get("positions", [])
            else:
                positions_data = response.get("positions", [])

            # Get current MT4 tickets
            mt4_tickets = {str(pos.get("ticket", "")) for pos in positions_data}

            # Get current database tickets (live positions only)
            db_result = await session.execute(
                text("SELECT number FROM open_positions WHERE simulation = false")
            )

            # Filter out corrupted tickets (only keep valid integer strings)
            db_tickets_raw = {str(row[0]) for row in db_result}
            db_tickets = set()
            for ticket in db_tickets_raw:
                try:
                    int(ticket)  # Validate it's a clean integer string
                    db_tickets.add(ticket)
                except (ValueError, TypeError):
                    logger.debug("corrupted_ticket_in_db", ticket=str(ticket)[:50])

            # Find positions that DISAPPEARED (in DB but not in MT4)
            disappeared_tickets = db_tickets - mt4_tickets

            logger.info(
                "position_sync_comparison",
                mt4_count=len(mt4_tickets),
                db_count=len(db_tickets),
                disappeared_count=len(disappeared_tickets)
            )

            # Archive disappeared positions to trading_history
            if disappeared_tickets:
                await self._archive_closed_positions(session, disappeared_tickets)

            # Upsert positions that still exist in MT4
            upserted_count = 0
            for pos_data in positions_data:
                ticket = str(pos_data.get("ticket", ""))
                open_price = float(pos_data.get("openPrice", 0.0))
                cur_price = float(pos_data.get("curPrice", 0.0))
                lots = float(pos_data.get("lots", 0.0))
                position_type = pos_data.get("type", "BUY").upper()

                # Calculate P&L
                contract_size = 1000.0  # CrudeOIL contract size
                if position_type == "BUY":
                    pnl = (cur_price - open_price) * lots * contract_size
                else:
                    pnl = (open_price - cur_price) * lots * contract_size

                # Prepare values
                params = {
                    "number": ticket,
                    "size": lots,
                    "symbol": pos_data.get("symbol", ""),
                    "price": open_price,
                    "stop_loss": pos_data.get("sl"),
                    "take_profit": pos_data.get("tp"),
                    "commission": pos_data.get("commission", 0.0),
                    "last_profit": pnl,
                    "last_update": datetime.utcnow(),
                    "last_strategy": "MT4_LIVE",
                    "simulation": False,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }

                # UPSERT position
                upsert_sql = text(f"""
                    INSERT INTO open_positions (
                        number, type, size, symbol, price,
                        stop_loss, take_profit, commission, last_profit,
                        last_update, last_strategy, simulation, created_at, updated_at
                    ) VALUES (
                        :number, '{position_type}'::positiontype, :size, :symbol, :price,
                        :stop_loss, :take_profit, :commission, :last_profit,
                        :last_update, :last_strategy, :simulation, :created_at, :updated_at
                    )
                    ON CONFLICT (number) DO UPDATE SET
                        type = EXCLUDED.type,
                        price = EXCLUDED.price,
                        size = EXCLUDED.size,
                        stop_loss = EXCLUDED.stop_loss,
                        take_profit = EXCLUDED.take_profit,
                        commission = EXCLUDED.commission,
                        last_profit = EXCLUDED.last_profit,
                        last_update = EXCLUDED.last_update,
                        updated_at = EXCLUDED.updated_at
                """)

                await session.execute(upsert_sql, params)
                upserted_count += 1

            await session.commit()

            logger.info(
                "positions_synced",
                upserted=upserted_count,
                archived=len(disappeared_tickets)
            )

            return True

        except Exception as e:
            logger.error("sync_positions_failed", error=str(e), exc_info=True)
            await session.rollback()
            return False

    async def _archive_closed_positions(self, session: AsyncSession, tickets: set):
        """
        Archive closed positions to trading_history with complete close data.

        Args:
            session: Database session
            tickets: Set of ticket numbers that disappeared from MT4
        """
        try:
            for ticket in tickets:
                # Validate ticket is a clean integer string
                try:
                    ticket_int = int(ticket)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "corrupted_ticket_skipped",
                        ticket=str(ticket)[:100],  # Limit length for logging
                        error=str(e)
                    )
                    # Try to delete corrupted ticket without archiving
                    try:
                        await session.execute(
                            text("DELETE FROM open_positions WHERE number = :ticket"),
                            {"ticket": str(ticket)}
                        )
                    except Exception as delete_error:
                        logger.warning(
                            "corrupted_ticket_delete_failed",
                            ticket=str(ticket)[:100],
                            error=str(delete_error)[:200]
                        )
                    continue

                # Fetch close data from MT4 trade history
                history_response = await self.mt4_client.get_trade_history(ticket=ticket_int)

                if not history_response or history_response.get("status") != "OK":
                    logger.warning("trade_history_fetch_failed", ticket=ticket)
                    # Still delete from open_positions even if history fetch fails
                    await session.execute(
                        text("DELETE FROM open_positions WHERE number = :ticket"),
                        {"ticket": ticket}
                    )
                    continue

                trades = history_response.get("trades", [])
                if not trades:
                    logger.warning("trade_not_found_in_history", ticket=ticket)
                    await session.execute(
                        text("DELETE FROM open_positions WHERE number = :ticket"),
                        {"ticket": ticket}
                    )
                    continue

                # Get trade data (should be single trade for specific ticket)
                trade = trades[0]

                # Calculate days in trade
                open_time = datetime.fromtimestamp(trade.get("openTime", 0))
                close_time = datetime.fromtimestamp(trade.get("closeTime", 0))
                days_in_trade = (close_time - open_time).total_seconds() / 86400

                # Get order type and embed in SQL (same pattern as position upsert)
                order_type = trade.get("type", "BUY")

                # Insert into trading_history - use f-string for enum to avoid asyncpg syntax issues
                insert_sql = text(f"""
                    INSERT INTO trading_history (
                        time, symbol, order_type, volume, price,
                        sl, tp, commission, swap, profit,
                        order_number, days_in_trade, simulation,
                        created_at, updated_at
                    ) VALUES (
                        :close_time, :symbol, '{order_type}'::ordertype, :volume, :close_price,
                        :sl, :tp, :commission, :swap, :profit,
                        :order_number, :days_in_trade, false,
                        :created_at, :updated_at
                    )
                """)

                await session.execute(insert_sql, {
                    "close_time": close_time,
                    "symbol": trade.get("symbol", ""),
                    "volume": trade.get("lots", 0.0),
                    "close_price": trade.get("closePrice", 0.0),
                    "sl": trade.get("sl", 0.0) or None,
                    "tp": trade.get("tp", 0.0) or None,
                    "commission": trade.get("commission", 0.0),
                    "swap": trade.get("swap", 0.0),
                    "profit": trade.get("profit", 0.0),
                    "order_number": ticket,
                    "days_in_trade": days_in_trade,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                })

                # Delete from open_positions
                await session.execute(
                    text("DELETE FROM open_positions WHERE number = :ticket"),
                    {"ticket": ticket}
                )

                logger.info(
                    "position_archived",
                    ticket=ticket,
                    symbol=trade.get("symbol"),
                    profit=trade.get("profit"),
                    close_price=trade.get("closePrice")
                )

        except Exception as e:
            logger.error("archive_closed_positions_failed", error=str(e), exc_info=True)
            raise

    async def _stream_loop(self):
        """Listen to MT4 real-time stream and save market data."""
        logger.info("mt4_stream_loop_started")

        try:
            # Subscribe to MT4 PUB socket for real-time events
            await self.mt4_client.subscribe_to_events()
            logger.info("subscribed_to_mt4_events")

        except Exception as e:
            logger.error("failed_to_subscribe_to_mt4_events", error=str(e), exc_info=True)
            return

        while self.running:
            try:
                # Receive event from MT4 stream (with timeout to allow checking self.running)
                message = await self.mt4_client.receive_event(timeout_ms=1000)

                if message:
                    # Process message
                    await self._process_stream_message(message)

            except asyncio.CancelledError:
                logger.info("mt4_stream_loop_cancelled")
                break

            except Exception as e:
                logger.error(
                    "mt4_stream_loop_error",
                    error=str(e),
                    exc_info=True,
                )
                # Brief pause before retry
                await asyncio.sleep(2)

    async def _process_stream_message(self, message: dict):
        """Process a single stream message and save market data if present."""
        try:
            # Check if this is a real_time_update with price_data
            msg_type = message.get("type")
            if msg_type != "real_time_update":
                return

            price_data = message.get("price_data")
            if not price_data:
                return

            symbol = message.get("symbol", "CrudeOIL")
            timeframe = message.get("timeframe", 1)  # 1 = M1

            # Convert timeframe number to string
            timeframe_map = {
                1: "M1",
                5: "M5",
                15: "M15",
                30: "M30",
                60: "H1",
                240: "H4",
                1440: "D1",
            }
            timeframe_str = timeframe_map.get(timeframe, "M1")

            # Extract OHLC data
            candle_time = datetime.fromtimestamp(price_data.get("time", 0))
            open_price = str(price_data.get("open", 0.0))
            high_price = str(price_data.get("high", 0.0))
            low_price = str(price_data.get("low", 0.0))
            close_price = str(price_data.get("close", 0.0))
            volume = price_data.get("volume", 0)

            # Create market data record
            market_data_dict = {
                "time": candle_time,
                "symbol": symbol,
                "import_symbol": symbol,  # For MT4 live data, use the same symbol
                "timeframe": timeframe_str,
                "source": "MT4",  # MT4 is the valid enum value
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "last": close_price,
                "change": "0.0",  # Can be calculated if needed
                "change_percent": "0.0",  # Can be calculated if needed
                "volume": volume,
            }

            # Save to database using a new session
            async with self.async_session() as session:
                market_data_repo = MarketDataRepository(session)
                await market_data_repo.upsert(market_data_dict)
                await session.commit()

                logger.debug(
                    "market_data_saved",
                    symbol=symbol,
                    timeframe=timeframe_str,
                    time=candle_time.isoformat(),
                    close=close_price,
                )

        except Exception as e:
            logger.error(
                "process_stream_message_failed",
                error=str(e),
                message=message,
                exc_info=True,
            )


# Global service instance
_mt4_sync_service: Optional[MT4SyncService] = None


def get_mt4_sync_service() -> MT4SyncService:
    """Get or create the global MT4 sync service instance."""
    global _mt4_sync_service

    if _mt4_sync_service is None:
        # Import settings here to avoid circular import
        from src.api.config import settings

        _mt4_sync_service = MT4SyncService(
            sync_interval_seconds=settings.mt4_sync_interval_seconds,
        )

    return _mt4_sync_service
