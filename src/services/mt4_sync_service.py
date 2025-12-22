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

from src.api.config import settings
from src.config.network_config import get_network_manager
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.mt4_models import (
    GetAccountInfoCommand,
    GetOpenPositionsCommand,
)
from src.database.models.account import AccountInfo
from src.database.models.positions import OpenPosition

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
    ):
        """
        Initialize MT4 sync service.

        Args:
            sync_interval_seconds: Seconds between sync cycles
            enable_position_sync: Enable position synchronization
            enable_account_sync: Enable account info synchronization
        """
        self.sync_interval = sync_interval_seconds
        self.enable_position_sync = enable_position_sync
        self.enable_account_sync = enable_account_sync

        self.mt4_client: Optional[MT4Client] = None
        self.engine = None
        self.async_session = None
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None

        logger.info(
            "mt4_sync_service_initialized",
            interval=sync_interval_seconds,
            positions_enabled=enable_position_sync,
            account_enabled=enable_account_sync,
        )

    async def start(self):
        """Start the sync service."""
        if self.running:
            logger.warning("mt4_sync_service_already_running")
            return

        logger.info("mt4_sync_service_starting")

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
        """Sync open positions from MT4."""
        try:
            # Query MT4
            command = GetOpenPositionsCommand()
            response = await self.mt4_client.send_command(command)

            # Handle both response formats:
            # New format: {"success": true, "data": {"positions": [...]}}
            # Old format: {"status": "OK", "positions": [...]}
            is_success = response.get("success", False) or response.get("status") == "OK"

            if not response or not is_success:
                logger.warning("mt4_positions_query_failed", response=response)
                return False

            # Extract positions from either format
            if "data" in response:
                positions_data = response.get("data", {}).get("positions", [])
            else:
                positions_data = response.get("positions", [])

            # DEBUG: Log the raw position data to see what MT4 is actually sending
            logger.info("mt4_positions_received",
                       count=len(positions_data),
                       raw_data=positions_data[:2] if positions_data else [])  # Log first 2

            # Upsert positions: INSERT new or UPDATE existing
            upserted_count = 0

            for pos_data in positions_data:
                ticket = str(pos_data.get("ticket", ""))

                # MT4 returns camelCase field names: openPrice, curPrice, not open_price
                open_price = float(pos_data.get("openPrice", 0.0))
                cur_price = float(pos_data.get("curPrice", 0.0))
                lots = float(pos_data.get("lots", 0.0))
                position_type = pos_data.get("type", "BUY").upper()

                # Calculate P&L: (current_price - open_price) * lots * contract_size
                # For commodities like CrudeOIL, contract size is typically 1000 barrels
                # For now, use simplified calculation: (cur_price - open_price) * lots * 1000
                contract_size = 1000.0  # CrudeOIL contract size
                if position_type == "BUY":
                    pnl = (cur_price - open_price) * lots * contract_size
                else:  # SELL
                    pnl = (open_price - cur_price) * lots * contract_size

                # Prepare values
                params = {
                    "number": ticket,
                    "pos_type": position_type,
                    "size": lots,
                    "symbol": pos_data.get("symbol", ""),
                    "price": open_price,
                    "stop_loss": pos_data.get("sl"),  # MT4 uses "sl" not "stop_loss"
                    "take_profit": pos_data.get("tp"),  # MT4 uses "tp" not "take_profit"
                    "commission": pos_data.get("commission", 0.0),
                    "last_profit": pnl,
                    "last_update": datetime.utcnow(),
                    "last_strategy": "MT4_LIVE",
                    "simulation": False,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }

                # Use UPSERT (INSERT ... ON CONFLICT) to handle both new and existing positions
                # Create SQL with literal enum value to avoid parameter mixing issues
                # Constraint is on 'number' only, not (number, simulation)
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

                # Remove pos_type from params since it's now in the SQL string
                params_without_type = {k: v for k, v in params.items() if k != "pos_type"}
                await session.execute(upsert_sql, params_without_type)

                upserted_count += 1

            await session.commit()

            logger.debug("positions_upserted", count=upserted_count)

            return True

        except Exception as e:
            logger.error("sync_positions_failed", error=str(e))
            await session.rollback()
            return False


# Global service instance
_mt4_sync_service: Optional[MT4SyncService] = None


def get_mt4_sync_service() -> MT4SyncService:
    """Get or create the global MT4 sync service instance."""
    global _mt4_sync_service

    if _mt4_sync_service is None:
        _mt4_sync_service = MT4SyncService(
            sync_interval_seconds=settings.mt4_sync_interval_seconds,
        )

    return _mt4_sync_service
