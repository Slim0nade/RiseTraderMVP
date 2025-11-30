#!/usr/bin/env python3
"""
Standalone script to run MT4IntegrationService with database persistence.

This script:
1. Connects to PostgreSQL
2. Initializes MT4IntegrationService with all repositories
3. Subscribes to real-time MT4 updates via ZMQ
4. Persists OHLC + indicators to database

Usage:
    python3 scripts/run_mt4_service_with_persistence.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import zmq
import zmq.asyncio
import json
from datetime import datetime

from src.database.repositories.mt4_order_repository import MT4OrderRepository
from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
from src.database.repositories.market_data_repository import MarketDataRepository
from src.database.repositories.indicators_repository import IndicatorsRepository
from src.services.mt4_integration_service import MT4IntegrationService
from src.utils.redis_client import MT4RedisClient
from src.trading.execution.symbol_loader import SymbolLoader


async def main():
    """Run MT4 service with database persistence."""

    # Database configuration
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
    )

    # MT4 configuration
    MT4_HOST = os.getenv("MT4_HOST", "75.154.254.186")
    MT4_PUB_PORT = int(os.getenv("MT4_PUB_PORT", "5556"))

    # Redis configuration
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

    print("=" * 80)
    print("🚀 Starting MT4 Integration Service with Database Persistence")
    print("=" * 80)
    print(f"📊 Database: {DATABASE_URL.replace('risetrader2024', '****')}")
    print(f"📡 MT4 PUB Socket: tcp://{MT4_HOST}:{MT4_PUB_PORT}")
    print(f"💾 Redis: {REDIS_URL}")
    print("=" * 80)

    # Create async database engine
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )

    # Create session factory
    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Initialize Redis client
    mt4_redis_client = MT4RedisClient(redis_url=REDIS_URL)

    # Create ZMQ context for subscribing
    zmq_context = zmq.asyncio.Context()
    subscriber = zmq_context.socket(zmq.SUB)
    subscriber.connect(f"tcp://{MT4_HOST}:{MT4_PUB_PORT}")
    subscriber.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages

    print("\n✅ Connected to MT4 PUB socket")
    print("⏳ Waiting for real-time updates...\n")

    message_count = 0

    try:
        while True:
            try:
                # Receive message from MT4 EA
                raw_message = await subscriber.recv_string()
                message_count += 1

                # Parse JSON
                event_data = json.loads(raw_message)
                event_type = event_data.get("type", event_data.get("event_type", "unknown"))

                if event_type == "real_time_update":
                    symbol = event_data.get("symbol", "N/A")
                    price_data = event_data.get("price_data", {})

                    print(f"📨 Message #{message_count}: {event_type}")
                    print(f"   Symbol: {symbol}")
                    print(f"   Price: O={price_data.get('open')} H={price_data.get('high')} "
                          f"L={price_data.get('low')} C={price_data.get('close')}")

                    # Create new database session for this transaction
                    async with async_session_factory() as session:
                        async with session.begin():
                            # Initialize repositories
                            order_repo = MT4OrderRepository(session)
                            connection_repo = MT4ConnectionRepository(session)
                            market_data_repo = MarketDataRepository(session)
                            indicators_repo = IndicatorsRepository(session)

                            # Initialize symbol loader
                            symbol_loader = SymbolLoader()

                            # Initialize service
                            service = MT4IntegrationService(
                                order_repository=order_repo,
                                redis_client=mt4_redis_client,
                                connection_repository=connection_repo,
                                symbol_loader=symbol_loader,
                                connection_pool=None,
                                market_data_repository=market_data_repo,
                                indicators_repository=indicators_repo,
                            )

                            # Process the event
                            await service.handle_market_tick_event(event_data)

                            print(f"   ✅ Persisted to database (market_data + indicators)")

                    print()

            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse message: {e}")
            except Exception as e:
                print(f"❌ Error processing message: {e}")
                import traceback
                traceback.print_exc()

    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print(f"✋ Stopped by user after {message_count} messages")
        print("=" * 80)

    finally:
        # Cleanup
        subscriber.close()
        zmq_context.term()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
