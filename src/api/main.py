"""
RiseTrader FastAPI Application

Main application entry point with middleware, routes, and lifecycle management.
"""
import asyncio
import os
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
from .routes import agents, trading, market_data, forecasts, performance, strategies, system, ml_forecasting, agent_pipelines, backtesting, vectorized_backtesting, data_sync, optimizer, stealth_stops, reversals, eda, events, alerts
from src.services.mt4_sync_service import get_mt4_sync_service
from src.services.stealth_stop_manager import StealthStopManager, DynamicTrailConfig
from src.services.price_alert_service import get_price_alert_service
from src.services.candle_aggregator_service import CandleAggregatorService
from src.services.live_trading_service import get_live_trading_service
from src.api.mcp_endpoint import create_mcp_app

# Configure structured logging
setup_logging()

logger = structlog.get_logger(__name__)

# Application startup time
_app_start_time = time.time()

# Global stealth stop manager instance
_stealth_stop_manager: StealthStopManager | None = None
_stealth_stop_task: asyncio.Task | None = None

# Global price alert monitoring task
_price_alert_task: asyncio.Task | None = None

# Global candle aggregator task (M1 → H1 real-time aggregation)
_candle_aggregator_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    global _stealth_stop_manager, _stealth_stop_task, _price_alert_task, _candle_aggregator_task
    
    # Startup
    logger.info("application_starting", version=settings.app_version)

    try:
        # Initialize agent coordinator
        # TODO: Fix config structure mismatch between agents.yaml and agent_coordinator.py
        # Current config uses "strategy_teams" but coordinator expects "agents" dict
        # await init_agent_coordinator()
        # logger.info("agent_coordinator_initialized")
        logger.info("agent_coordinator_init_skipped", reason="Config structure mismatch - needs refactoring")

        # Start MT4 sync service for real-time position/account updates
        # Make it non-blocking to prevent API startup delays
        try:
            mt4_sync = get_mt4_sync_service()
            await asyncio.wait_for(mt4_sync.start(), timeout=3.0)
            logger.info("mt4_sync_service_started")
        except asyncio.TimeoutError:
            logger.warning("mt4_sync_service_start_timeout", message="MT4 sync will retry in background")
        except Exception as e:
            logger.warning("mt4_sync_service_start_failed", error=str(e), message="MT4 sync will retry in background")
        
        # Start Stealth Stop Manager for automated trailing stops
        # Make it non-blocking and only start if MT4 is accessible
        stealth_stops_enabled = os.getenv("STEALTH_STOPS_ENABLED", "false").lower() == "true"
        if stealth_stops_enabled:
            try:
                mt4_host = os.getenv("MT4_HOST", "192.168.0.123")
                mt4_port = int(os.getenv("MT4_PORT", "5555"))
                poll_interval = int(os.getenv("STEALTH_STOP_POLL_INTERVAL", "5"))

                # Dynamic configuration from environment
                config = DynamicTrailConfig(
                    atr_multiplier_initial=float(os.getenv("ATR_MULTIPLIER_INITIAL", "2.0")),
                    atr_multiplier_trail=float(os.getenv("ATR_MULTIPLIER_TRAIL", "1.5")),
                    trail_trigger_atr=float(os.getenv("TRAIL_TRIGGER_ATR", "1.0")),
                    breakeven_trigger_atr=float(os.getenv("BREAKEVEN_TRIGGER_ATR", "1.5")),
                    min_offset_pips=float(os.getenv("MIN_OFFSET_PIPS", "5")),
                    max_offset_pips=float(os.getenv("MAX_OFFSET_PIPS", "15")),
                    pip_value=float(os.getenv("PIP_VALUE", "0.01")),
                )

                _stealth_stop_manager = StealthStopManager(
                    mt4_host=mt4_host,
                    mt4_port=mt4_port,
                    poll_interval=poll_interval,
                    config=config
                )
                _stealth_stop_task = asyncio.create_task(_stealth_stop_manager.run())
                logger.info("stealth_stop_manager_started", mt4_host=mt4_host, mt4_port=mt4_port)
            except Exception as e:
                logger.warning("stealth_stop_manager_start_failed", error=str(e))
        else:
            logger.info("stealth_stop_manager_disabled")

        # Start Price Alert Monitoring Service (T063)
        # Monitors price levels and emits SSE events when breached
        price_alerts_enabled = os.getenv("PRICE_ALERTS_ENABLED", "true").lower() == "true"
        if price_alerts_enabled:
            try:
                # Get database session for price alert service
                from src.api.dependencies import get_db_context
                
                async def start_price_alert_monitor():
                    async with get_db_context() as db:
                        service = await get_price_alert_service(db)
                        await service.start()
                        logger.info("price_alert_service_started")
                        # Keep db session alive while monitor runs
                        while service.is_running:
                            await asyncio.sleep(1)
                
                _price_alert_task = asyncio.create_task(start_price_alert_monitor())
                logger.info("price_alert_monitoring_scheduled")
            except Exception as e:
                logger.warning("price_alert_service_start_failed", error=str(e))
        else:
            logger.info("price_alert_service_disabled")

        # Start Candle Aggregator Service (M1 → H1 real-time aggregation)
        # Runs every 60s regardless of MT4 connection status — it reads from
        # the DB (populated by mt4_sync_service) and writes H1 candles back.
        try:
            aggregator = CandleAggregatorService()
            _candle_aggregator_task = asyncio.create_task(aggregator.run())
            logger.info("candle_aggregator_service_scheduled")
        except Exception as e:
            logger.warning("candle_aggregator_service_start_failed", error=str(e))

        # Start Live Trading Service (autonomous signal → risk → execute loop)
        # Controlled by LIVE_TRADING_ENABLED env var (default: false)
        try:
            live_svc = get_live_trading_service()
            await live_svc.start()
        except Exception as e:
            logger.warning("live_trading_service_start_failed", error=str(e))

    except Exception as e:
        logger.error("startup_failed", error=str(e), exc_info=True)
        raise

    logger.info("application_started", version=settings.app_version)

    yield

    # Shutdown
    logger.info("application_shutting_down")

    try:
        # Stop Price Alert Monitoring (T063)
        if _price_alert_task:
            _price_alert_task.cancel()
            try:
                await _price_alert_task
            except asyncio.CancelledError:
                pass
            logger.info("price_alert_service_stopped")

        # Stop Stealth Stop Manager
        if _stealth_stop_manager:
            _stealth_stop_manager.stop()
            if _stealth_stop_task:
                _stealth_stop_task.cancel()
                try:
                    await _stealth_stop_task
                except asyncio.CancelledError:
                    pass
            logger.info("stealth_stop_manager_stopped")
        
        # Stop Candle Aggregator Service
        if _candle_aggregator_task:
            _candle_aggregator_task.cancel()
            try:
                await _candle_aggregator_task
            except asyncio.CancelledError:
                pass
            logger.info("candle_aggregator_service_stopped")

        # Stop Live Trading Service
        try:
            live_svc = get_live_trading_service()
            live_svc.stop()
            await live_svc.wait_stopped()
            logger.info("live_trading_service_stopped")
        except Exception as e:
            logger.warning("live_trading_service_stop_failed", error=str(e))

        # Stop MT4 sync service
        mt4_sync = get_mt4_sync_service()
        await mt4_sync.stop()
        logger.info("mt4_sync_service_stopped")

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
app.include_router(agent_pipelines.router, prefix="/api")  # New intelligent agent pipelines
app.include_router(backtesting.router, prefix="/api")  # Backtesting endpoints
app.include_router(vectorized_backtesting.router, prefix="/api")  # Fast vectorized backtesting
app.include_router(trading.router, prefix="/api")
app.include_router(market_data.router, prefix="/api")
app.include_router(forecasts.router, prefix="/api")
app.include_router(performance.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(system.admin_router, prefix="/api")  # Admin endpoints (thresholds, etc.)
app.include_router(ml_forecasting.router)  # ML forecasting endpoints
app.include_router(data_sync.router, prefix="/api")  # Data sync endpoints
app.include_router(optimizer.router, prefix="/api")  # Strategy optimizer
app.include_router(stealth_stops.router, prefix="/api")  # Stealth Stop Manager
app.include_router(reversals.router)  # Reversal predictions (ZigZag ML classifier)
app.include_router(eda.router, prefix="/api")  # EDA - Automated Data Quality Analysis
app.include_router(events.router, prefix="/api")  # SSE Events streaming
app.include_router(alerts.router, prefix="/api")  # Price Alerts

# OAuth discovery stub — Claude Code MCP client probes these before connecting.
# Must return an OAuth-spec-compliant body ({"error": "<string>", ...}) so the
# SDK's zod validator accepts it and falls through to unauthenticated mode,
# instead of the app's default JSON error envelope which has `error` as an object.
_OAUTH_NO_AUTH_BODY = {
    "error": "not_supported",
    "error_description": "This MCP server does not require authentication",
}


@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/oauth-authorization-server/mcp")
@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
@app.get("/.well-known/openid-configuration")
async def oauth_discovery_stub():
    return JSONResponse(status_code=404, content=_OAUTH_NO_AUTH_BODY)


# RFC 7591 dynamic client registration + RFC 6749 authorize/token endpoints.
# Claude Code falls back to these at the base URL when discovery returns 404.
@app.post("/register")
@app.post("/oauth/register")
@app.post("/mcp/register")
async def oauth_register_stub():
    return JSONResponse(status_code=404, content=_OAUTH_NO_AUTH_BODY)


@app.api_route("/authorize", methods=["GET", "POST"])
@app.api_route("/oauth/authorize", methods=["GET", "POST"])
@app.api_route("/mcp/authorize", methods=["GET", "POST"])
async def oauth_authorize_stub():
    return JSONResponse(status_code=404, content=_OAUTH_NO_AUTH_BODY)


@app.post("/token")
@app.post("/oauth/token")
@app.post("/mcp/token")
async def oauth_token_stub():
    return JSONResponse(status_code=404, content=_OAUTH_NO_AUTH_BODY)

# Mount MCP server (SSE transport for Claude Code / Claude Desktop)
app.mount("/mcp", create_mcp_app())

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
