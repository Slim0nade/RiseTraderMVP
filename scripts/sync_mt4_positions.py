#!/usr/bin/env python3
"""
Sync MT4 Positions to Database

This script queries MT4 for current positions and account info,
then stores them in the database for the dashboard to display.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_models import GetAccountInfoCommand, GetOpenPositionsCommand
from src.database.models.account import AccountInfo
from src.database.models.positions import OpenPosition
from src.database.repositories.trading_repository import TradingRepository

logger = structlog.get_logger(__name__)


async def sync_account_info(mt4_client: MT4Client, session: AsyncSession):
    """Query and sync account information from MT4."""
    try:
        logger.info("querying_mt4_account_info")

        # Query MT4 for account info
        command = GetAccountInfoCommand()
        response = await mt4_client.send_command(command)

        if not response or response.get("success") is False:
            logger.error("mt4_account_query_failed", response=response)
            return None

        # Extract account data
        account_data = response.get("data", {})

        # Create AccountInfo record
        account = AccountInfo(
            account_number=str(account_data.get("account_number", "UNKNOWN")),
            balance=account_data.get("balance", 0.0),
            equity=account_data.get("equity", 0.0),
            margin=account_data.get("margin", 0.0),
            free_margin=account_data.get("free_margin", 0.0),
            margin_level=account_data.get("margin_level"),
            profit=account_data.get("profit", 0.0),
            currency=account_data.get("currency", "USD"),
            leverage=account_data.get("leverage"),
        )

        session.add(account)
        await session.commit()

        logger.info(
            "account_info_synced",
            account_number=account.account_number,
            balance=float(account.balance),
            equity=float(account.equity),
            profit=float(account.profit),
        )

        return account

    except Exception as e:
        logger.error("sync_account_failed", error=str(e), exc_info=True)
        return None


async def sync_positions(mt4_client: MT4Client, session: AsyncSession):
    """Query and sync open positions from MT4."""
    try:
        logger.info("querying_mt4_positions")

        # Query MT4 for positions
        command = GetOpenPositionsCommand()
        response = await mt4_client.send_command(command)

        if not response or response.get("success") is False:
            logger.error("mt4_positions_query_failed", response=response)
            return []

        # Extract positions
        positions_data = response.get("data", {}).get("positions", [])
        logger.info("mt4_positions_received", count=len(positions_data))

        # Clear existing positions (simple strategy - could be improved with update logic)
        await session.execute("DELETE FROM open_positions WHERE simulation = false")

        synced_positions = []

        for pos_data in positions_data:
            position = OpenPosition(
                number=str(pos_data.get("ticket", "")),
                type=pos_data.get("type", "BUY"),
                size=pos_data.get("lots", 0.0),
                symbol=pos_data.get("symbol", ""),
                price=pos_data.get("open_price", 0.0),
                stop_loss=pos_data.get("stop_loss"),
                take_profit=pos_data.get("take_profit"),
                commission=pos_data.get("commission", 0.0),
                last_profit=pos_data.get("profit", 0.0),
                last_strategy="MT4_SYNC",
                simulation=False,  # Real MT4 position
            )

            session.add(position)
            synced_positions.append(position)

            logger.info(
                "position_synced",
                ticket=position.number,
                symbol=position.symbol,
                type=position.type,
                size=float(position.size),
                profit=float(position.last_profit or 0),
            )

        await session.commit()

        logger.info("positions_sync_complete", total=len(synced_positions))
        return synced_positions

    except Exception as e:
        logger.error("sync_positions_failed", error=str(e), exc_info=True)
        await session.rollback()
        return []


async def main():
    """Main sync process."""
    logger.info("mt4_sync_starting")

    # Create database engine
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )

    # Create session factory
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create MT4 client
    mt4_client = MT4Client()

    try:
        # Initialize MT4 client
        await mt4_client.connect()
        logger.info("mt4_client_connected")

        async with async_session() as session:
            # Sync account info
            account = await sync_account_info(mt4_client, session)

            # Sync positions
            positions = await sync_positions(mt4_client, session)

            # Summary
            print("\n" + "="*60)
            print("MT4 SYNC COMPLETE")
            print("="*60)

            if account:
                print(f"\nAccount: {account.account_number}")
                print(f"Balance: ${float(account.balance):,.2f}")
                print(f"Equity:  ${float(account.equity):,.2f}")
                print(f"Profit:  ${float(account.profit):,.2f}")

            print(f"\nPositions Synced: {len(positions)}")

            if positions:
                print("\nOpen Positions:")
                for pos in positions:
                    print(f"  {pos.symbol:10s} {pos.type:4s} {float(pos.size):7.2f} lots @ {float(pos.price):8.2f} | P&L: ${float(pos.last_profit or 0):+8.2f}")

            print("\n" + "="*60 + "\n")

    except Exception as e:
        logger.error("mt4_sync_failed", error=str(e), exc_info=True)
        print(f"\n❌ Sync failed: {e}\n")
        return 1

    finally:
        # Cleanup
        await mt4_client.disconnect()
        await engine.dispose()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
