"""
System Operations API Routes
"""
import time
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from src.agents.agent_coordinator import AgentCoordinator
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
