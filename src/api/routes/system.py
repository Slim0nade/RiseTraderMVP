"""
System Operations API Routes
"""
import time
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from pydantic import BaseModel

from src.agents.agent_coordinator import AgentCoordinator
from src.config.network_config import (
    NetworkLocation,
    NetworkLocationManager,
    get_network_manager,
)
from ..config import settings
from ..dependencies import get_agent_coordinator, engine
from ..models import (
    EmergencyStopRequest,
    EmergencyStopResponse,
    HealthCheckResponse,
    RestartRequest,
    RestartResponse,
    SystemStatusResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/system", tags=["system"])

_system_start_time = time.time()


# Network Location Models
class NetworkLocationResponse(BaseModel):
    """Network location response."""
    location: str
    mt4_host: str
    mt4_command_endpoint: str
    mt4_stream_endpoint: str
    ollama_base_url: str
    ollama_timeout: int
    ollama_max_retries: int


class NetworkLocationUpdateRequest(BaseModel):
    """Network location update request."""
    location: str  # "local" or "remote"


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> HealthCheckResponse:
    """Comprehensive health check."""
    try:
        uptime = time.time() - _system_start_time

        # Check database
        db_status = "healthy"
        try:
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
        except:
            db_status = "unhealthy"

        # Check agents
        agents_status = "healthy"
        try:
            agents = coordinator.get_all_agents()
            if not agents or len(agents) == 0:
                agents_status = "degraded"
        except:
            agents_status = "unhealthy"

        overall_status = "healthy"
        if db_status == "unhealthy" or agents_status == "unhealthy":
            overall_status = "unhealthy"
        elif db_status == "degraded" or agents_status == "degraded":
            overall_status = "degraded"

        return HealthCheckResponse(
            status=overall_status,
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            uptime_seconds=round(uptime, 2),
            components={
                "database": db_status,
                "redis": "unknown",  # TODO: Check Redis
                "mcp_server": agents_status,
                "agents": agents_status,
            },
        )
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Health check failed")


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> SystemStatusResponse:
    """Detailed system status."""
    try:
        uptime = time.time() - _system_start_time
        agents = coordinator.get_all_agents()

        # Count agent statuses
        running = sum(1 for a in agents if a.status.value == "RUNNING")
        paused = sum(1 for a in agents if a.status.value == "PAUSED")
        stopped = sum(1 for a in agents if a.status.value == "STOPPED")
        error = sum(1 for a in agents if a.status.value == "ERROR")

        # Database connection check
        db_connected = True
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            logger.warning("database_connection_check_failed", error=str(e))
            db_connected = False

        return SystemStatusResponse(
            status="healthy" if db_connected and running > 0 else "degraded",
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            uptime_seconds=round(uptime, 2),
            database_connected=db_connected,
            database_pool_size=settings.database_pool_size,
            database_active_connections=0,  # TODO: Get from engine
            redis_connected=True,  # TODO: Check Redis
            redis_memory_used=None,
            total_agents=len(agents),
            running_agents=running,
            paused_agents=paused,
            stopped_agents=stopped,
            agents_in_error=error,
            mcp_server_running=coordinator.running,
            event_queue_size=0,  # TODO: Get from event bus
            events_processed_total=0,  # TODO: Get from metrics
            open_positions_count=0,  # TODO: Query database
            total_trades_today=0,  # TODO: Query database
            paper_trading_enabled=settings.enable_paper_trading,
            live_trading_enabled=settings.enable_live_trading,
        )
    except Exception as e:
        logger.error("get_system_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency-stop", response_model=EmergencyStopResponse)
async def emergency_stop(
    request: EmergencyStopRequest,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> EmergencyStopResponse:
    """Emergency stop all trading (placeholder)."""
    logger.critical("emergency_stop_triggered", reason=request.reason)

    # TODO: Implement actual emergency stop
    # 1. Close all positions
    # 2. Stop all agents
    # 3. Disable trading

    return EmergencyStopResponse(
        success=False,
        message="Emergency stop not fully implemented",
        timestamp=datetime.utcnow(),
        positions_closed=0,
        agents_stopped=0,
        details={"reason": request.reason},
    )


@router.post("/restart", response_model=RestartResponse)
async def restart_system(
    request: RestartRequest,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> RestartResponse:
    """Restart system (placeholder)."""
    logger.info("restart_triggered", reason=request.reason)

    # TODO: Implement system restart
    # 1. Stop all agents
    # 2. Reload configuration
    # 3. Restart agents

    return RestartResponse(
        success=False,
        message="System restart not fully implemented",
        timestamp=datetime.utcnow(),
        agents_restarted=0,
        config_reloaded=False,
    )


@router.get("/network-location", response_model=NetworkLocationResponse)
async def get_network_location():
    """
    Get current network location configuration.

    Returns current network settings for MT4 and Ollama.
    No restart required - changes take effect immediately!
    """
    try:
        manager = get_network_manager()
        mt4_config = manager.get_mt4_config()
        ollama_config = manager.get_ollama_config()

        return NetworkLocationResponse(
            location=manager.location.value,
            mt4_host=mt4_config.host,
            mt4_command_endpoint=mt4_config.command_endpoint,
            mt4_stream_endpoint=mt4_config.stream_endpoint,
            ollama_base_url=ollama_config.base_url,
            ollama_timeout=ollama_config.timeout,
            ollama_max_retries=ollama_config.max_retries,
        )
    except Exception as e:
        logger.error("get_network_location_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/network-location", response_model=NetworkLocationResponse)
async def set_network_location(request: NetworkLocationUpdateRequest):
    """
    Switch network location (local/remote).

    Updates MT4 and Ollama endpoints dynamically - NO RESTART NEEDED!

    Args:
        request: Network location ("local" or "remote")

    Returns:
        Updated network configuration
    """
    try:
        # Validate location
        if request.location not in ["local", "remote"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid location: {request.location}. Must be 'local' or 'remote'"
            )

        location = NetworkLocation(request.location)
        manager = get_network_manager()

        # Switch location
        old_location = manager.location.value
        manager.set_location(location)

        # Get new config
        mt4_config = manager.get_mt4_config()
        ollama_config = manager.get_ollama_config()

        logger.info(
            "network_location_switched_via_ui",
            old_location=old_location,
            new_location=location.value,
            mt4_host=mt4_config.host,
            ollama_url=ollama_config.base_url,
        )

        return NetworkLocationResponse(
            location=manager.location.value,
            mt4_host=mt4_config.host,
            mt4_command_endpoint=mt4_config.command_endpoint,
            mt4_stream_endpoint=mt4_config.stream_endpoint,
            ollama_base_url=ollama_config.base_url,
            ollama_timeout=ollama_config.timeout,
            ollama_max_retries=ollama_config.max_retries,
        )

    except ValueError as e:
        logger.error("invalid_network_location", location=request.location, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("set_network_location_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
