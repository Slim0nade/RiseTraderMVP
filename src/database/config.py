"""
Database configuration and session management.
"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from .models.base import Base


class DatabaseConfig:
    """
    Database configuration manager.

    Handles async engine creation, session management, and connection pooling.
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
        pool_recycle: int = 3600,
    ):
        """
        Initialize database configuration.

        Args:
            database_url: PostgreSQL connection URL (must use asyncpg driver)
            echo: Enable SQL query logging
            pool_size: Number of connections to maintain in pool
            max_overflow: Maximum overflow connections beyond pool_size
            pool_pre_ping: Test connection liveness before using
            pool_recycle: Recycle connections after N seconds
        """
        self.database_url = database_url
        self.echo = echo

        # Create async engine with connection pooling
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            pool_recycle=pool_recycle,
            # Use psycopg2 pool implementation for asyncpg
            poolclass=None,  # Use default QueuePool
        )

        # Create async session factory
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.

        Usage:
            async with db_config.get_session() as session:
                # Use session here
                pass

        Yields:
            AsyncSession instance
        """
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self) -> None:
        """
        Create all database tables.

        WARNING: This will create tables but won't drop existing ones.
        Use Alembic migrations for production.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """
        Drop all database tables.

        WARNING: This will delete all data! Use with caution.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def close(self) -> None:
        """Close the database engine and all connections."""
        await self.engine.dispose()

    async def health_check(self) -> bool:
        """
        Check database connection health.

        Returns:
            True if database is accessible, False otherwise
        """
        try:
            async with self.get_session() as session:
                await session.execute("SELECT 1")
            return True
        except Exception:
            return False


# Global database configuration instance
_db_config: Optional[DatabaseConfig] = None


def initialize_database(
    database_url: Optional[str] = None,
    echo: bool = False,
    pool_size: int = 20,
    max_overflow: int = 10,
) -> DatabaseConfig:
    """
    Initialize global database configuration.

    Args:
        database_url: PostgreSQL connection URL (defaults to env var)
        echo: Enable SQL query logging
        pool_size: Connection pool size
        max_overflow: Maximum overflow connections

    Returns:
        DatabaseConfig instance
    """
    global _db_config

    if database_url is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader",
        )

    _db_config = DatabaseConfig(
        database_url=database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )

    return _db_config


def get_database() -> DatabaseConfig:
    """
    Get the global database configuration.

    Returns:
        DatabaseConfig instance

    Raises:
        RuntimeError: If database not initialized
    """
    if _db_config is None:
        raise RuntimeError(
            "Database not initialized. Call initialize_database() first."
        )
    return _db_config


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function for FastAPI to get database session.

    Usage in FastAPI:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            # Use session here
            pass

    Yields:
        AsyncSession instance
    """
    db = get_database()
    async with db.get_session() as session:
        yield session


# Alternative: Create engine directly from environment variable
def create_engine_from_env(echo: bool = False) -> AsyncEngine:
    """
    Create async engine from environment variable.

    Args:
        echo: Enable SQL query logging

    Returns:
        AsyncEngine instance
    """
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader",
    )

    return create_async_engine(
        database_url,
        echo=echo,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


# Session factory for direct use
def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create a session factory from an engine.

    Args:
        engine: AsyncEngine instance

    Returns:
        async_sessionmaker instance
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
