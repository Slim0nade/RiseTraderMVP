"""
Conftest for backtesting integration tests.

Provides async_session fixture connected to the real PostgreSQL database
(not SQLite in-memory). All backtesting integration tests need real market
data from the 13.5M-candle database.

NOTE: The root tests/conftest.py sets DATABASE_URL to SQLite at import time.
We explicitly use the real Postgres URL here, reading from .env if available.
"""
from pathlib import Path
from typing import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Default real Postgres URL (root conftest overrides DATABASE_URL to SQLite)
_DEFAULT_PG_URL = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"


def _read_pg_url_from_dotenv() -> str:
    """Read DATABASE_URL from .env file, bypassing os.environ override."""
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL=") and "asyncpg" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return _DEFAULT_PG_URL


REAL_DATABASE_URL = _read_pg_url_from_dotenv()


@pytest_asyncio.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session for integration tests.

    Creates a fresh engine per test to avoid event loop conflicts.
    Uses the real PostgreSQL database with actual market data.
    Each test gets its own session that rolls back on teardown
    to avoid polluting the database.
    """
    engine = create_async_engine(
        REAL_DATABASE_URL,
        echo=False,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()

    await engine.dispose()
