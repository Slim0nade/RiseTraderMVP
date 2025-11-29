"""
RiseTrader FastAPI Application

Main application entry point with middleware, routes, and lifecycle management.
"""
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings, get_cors_origins
from .dependencies import (
    init_agent_coordinator,
    shutdown_agent_coordinator,
    limiter,
)
from .middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    register_exception_handlers,
    setup_logging,
)
from .routes import agents, trading, market_data, forecasts, performance, strategies, system

# Configure structured logging
setup_logging()

logger = structlog.get_logger(__name__)

# Application startup time
_app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("application_starting", version=settings.app_version)

    try:
        # Initialize agent coordinator
        await init_agent_coordinator()
        logger.info("agent_coordinator_initialized")

    except Exception as e:
        logger.error("startup_failed", error=str(e), exc_info=True)
        raise

    logger.info("application_started", version=settings.app_version)

    yield

    # Shutdown
    logger.info("application_shutting_down")

    try:
        # Shutdown agent coordinator
        await shutdown_agent_coordinator()
        logger.info("agent_coordinator_shutdown")

    except Exception as e:
        logger.error("shutdown_failed", error=str(e), exc_info=True)

    logger.info("application_shutdown_complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware
if settings.cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=settings.cors_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )

# Add custom middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(MetricsMiddleware)

# Register exception handlers
register_exception_handlers(app)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(agents.router, prefix="/api")
app.include_router(trading.router, prefix="/api")
app.include_router(market_data.router, prefix="/api")
app.include_router(forecasts.router, prefix="/api")
app.include_router(performance.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(system.router, prefix="/api")

# Mount Prometheus metrics endpoint
if settings.prometheus_enabled:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint with API information.

    Returns:
        API information
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": settings.app_description,
        "docs": "/docs",
        "health": "/api/system/health",
    }


# Health check endpoint (simple, no dependencies)
@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.

    Returns:
        Health status
    """
    uptime = time.time() - _app_start_time

    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "version": settings.app_version,
            "uptime_seconds": round(uptime, 2),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
        workers=settings.workers if not settings.reload else 1,
    )
