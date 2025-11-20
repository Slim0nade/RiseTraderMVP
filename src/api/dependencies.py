"""
FastAPI Dependencies

Provides dependency injection for database sessions, agent coordinator,
authentication, and rate limiting.
"""
import time
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.agents.agent_coordinator import AgentCoordinator
from .config import settings

# Database engine
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
    echo=settings.debug,
)

# Session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Global agent coordinator instance
_agent_coordinator: Optional[AgentCoordinator] = None

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# API Key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency.

    Yields:
        AsyncSession for database operations

    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_agent_coordinator() -> None:
    """
    Initialize the global agent coordinator.

    Should be called during FastAPI startup event.
    """
    global _agent_coordinator

    if _agent_coordinator is None:
        _agent_coordinator = AgentCoordinator(
            config_path=settings.agent_config_path,
            redis_url=settings.redis_url,
            database_url=settings.database_url,
        )
        await _agent_coordinator.start()


async def shutdown_agent_coordinator() -> None:
    """
    Shutdown the global agent coordinator.

    Should be called during FastAPI shutdown event.
    """
    global _agent_coordinator

    if _agent_coordinator is not None:
        await _agent_coordinator.stop()
        _agent_coordinator = None


def get_agent_coordinator() -> AgentCoordinator:
    """
    Get the agent coordinator dependency.

    Returns:
        AgentCoordinator instance

    Raises:
        HTTPException: If coordinator not initialized

    Example:
        @app.get("/agents")
        async def get_agents(
            coordinator: AgentCoordinator = Depends(get_agent_coordinator)
        ):
            ...
    """
    if _agent_coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent coordinator not initialized",
        )
    return _agent_coordinator


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """
    Verify API key authentication.

    Args:
        api_key: API key from header

    Returns:
        Validated API key

    Raises:
        HTTPException: If API key is invalid

    Example:
        @app.get("/protected")
        async def protected_route(
            api_key: str = Depends(verify_api_key)
        ):
            ...
    """
    # In development mode, allow requests without API key
    if not settings.valid_api_keys:
        return "development"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "API-Key"},
        )

    if api_key not in settings.valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key


def get_rate_limiter() -> Limiter:
    """
    Get rate limiter instance.

    Returns:
        Limiter instance
    """
    return limiter


# Request ID context
class RequestContext:
    """
    Request context for tracking request information.
    """

    def __init__(self):
        self.request_id: Optional[str] = None
        self.start_time: float = time.time()
        self.user_id: Optional[str] = None
        self.api_key: Optional[str] = None

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since request start."""
        return time.time() - self.start_time


async def get_request_context() -> RequestContext:
    """
    Get request context dependency.

    Returns:
        RequestContext instance

    Example:
        @app.get("/endpoint")
        async def endpoint(ctx: RequestContext = Depends(get_request_context)):
            print(f"Elapsed: {ctx.elapsed_time}ms")
    """
    return RequestContext()


# Pagination dependencies
class PaginationParams:
    """
    Pagination parameters for list endpoints.
    """

    def __init__(
        self,
        page: int = 1,
        page_size: int = settings.default_page_size,
    ):
        """
        Initialize pagination parameters.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
        """
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), settings.max_page_size)

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit for database query."""
        return self.page_size


def get_pagination_params(
    page: int = 1,
    page_size: int = settings.default_page_size,
) -> PaginationParams:
    """
    Get pagination parameters dependency.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        PaginationParams instance

    Example:
        @app.get("/items")
        async def get_items(
            pagination: PaginationParams = Depends(get_pagination_params)
        ):
            ...
    """
    return PaginationParams(page=page, page_size=page_size)


# Optional API key (for endpoints that work with or without auth)
async def optional_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> Optional[str]:
    """
    Optional API key authentication.

    Validates if provided, but doesn't require it.

    Args:
        api_key: API key from header

    Returns:
        Validated API key or None

    Raises:
        HTTPException: If API key is provided but invalid
    """
    if not api_key:
        return None

    if settings.valid_api_keys and api_key not in settings.valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key
