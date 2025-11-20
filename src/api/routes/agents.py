"""
Agent Management API Routes

Endpoints for managing and monitoring trading agents.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.agents.agent_coordinator import AgentCoordinator
from src.agents.agent_registry import AgentStatus
from ..dependencies import get_agent_coordinator, get_pagination_params, PaginationParams
from ..models import (
    AgentCommandRequest,
    AgentListResponse,
    AgentLogsResponse,
    AgentMetricsResponse,
    AgentOperationResponse,
    AgentStatusResponse,
    CommandResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents(
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentListResponse:
    """
    List all agents with their current status.

    Returns:
        List of all agents and their statuses
    """
    try:
        agents = coordinator.get_all_agents()

        agent_statuses = []
        for agent in agents:
            status_data = await agent.get_status()
            agent_statuses.append(AgentStatusResponse(**status_data))

        return AgentListResponse(
            agents=agent_statuses,
            total=len(agent_statuses),
        )

    except Exception as e:
        logger.error("list_agents_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.get("/{agent_id}", response_model=AgentStatusResponse)
async def get_agent(
    agent_id: str,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentStatusResponse:
    """
    Get detailed status for a specific agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent status details
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        status_data = await agent.get_status()
        return AgentStatusResponse(**status_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_agent_failed", agent_id=agent_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent status: {str(e)}",
        )


@router.post("/{agent_id}/start", response_model=AgentOperationResponse)
async def start_agent(
    agent_id: str,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentOperationResponse:
    """
    Start a specific agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Operation result
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        # Check if already running
        if agent.status == AgentStatus.RUNNING:
            return AgentOperationResponse(
                success=True,
                message=f"Agent already running: {agent_id}",
                agent_id=agent_id,
                new_status="RUNNING",
            )

        await agent.start()

        logger.info("agent_started", agent_id=agent_id)

        return AgentOperationResponse(
            success=True,
            message=f"Agent started successfully: {agent_id}",
            agent_id=agent_id,
            new_status="RUNNING",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("start_agent_failed", agent_id=agent_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start agent: {str(e)}",
        )


@router.post("/{agent_id}/stop", response_model=AgentOperationResponse)
async def stop_agent(
    agent_id: str,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentOperationResponse:
    """
    Stop a specific agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Operation result
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        # Check if already stopped
        if agent.status == AgentStatus.STOPPED:
            return AgentOperationResponse(
                success=True,
                message=f"Agent already stopped: {agent_id}",
                agent_id=agent_id,
                new_status="STOPPED",
            )

        await agent.stop()

        logger.info("agent_stopped", agent_id=agent_id)

        return AgentOperationResponse(
            success=True,
            message=f"Agent stopped successfully: {agent_id}",
            agent_id=agent_id,
            new_status="STOPPED",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("stop_agent_failed", agent_id=agent_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop agent: {str(e)}",
        )


@router.post("/{agent_id}/restart", response_model=AgentOperationResponse)
async def restart_agent(
    agent_id: str,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentOperationResponse:
    """
    Restart a specific agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Operation result
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        # Stop if running
        if agent.status != AgentStatus.STOPPED:
            await agent.stop()

        # Start agent
        await agent.start()

        logger.info("agent_restarted", agent_id=agent_id)

        return AgentOperationResponse(
            success=True,
            message=f"Agent restarted successfully: {agent_id}",
            agent_id=agent_id,
            new_status="RUNNING",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("restart_agent_failed", agent_id=agent_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart agent: {str(e)}",
        )


@router.get("/{agent_id}/metrics", response_model=AgentMetricsResponse)
async def get_agent_metrics(
    agent_id: str,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentMetricsResponse:
    """
    Get performance metrics for a specific agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent metrics
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        # Get metrics from agent
        metrics = agent.metrics

        # Calculate success rate
        total_events = metrics.get("events_processed", 0) + metrics.get("events_failed", 0)
        success_rate = 0.0
        if total_events > 0:
            success_rate = (metrics.get("events_processed", 0) / total_events) * 100

        return AgentMetricsResponse(
            agent_id=agent_id,
            events_processed=metrics.get("events_processed", 0),
            events_failed=metrics.get("events_failed", 0),
            average_processing_time_ms=metrics.get("average_processing_time_ms", 0.0),
            last_processed_at=metrics.get("last_processed_at"),
            circuit_breaker_status=metrics.get("circuit_breaker_status", "UNKNOWN"),
            failure_count=metrics.get("failure_count", 0),
            success_rate=round(success_rate, 2),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_agent_metrics_failed", agent_id=agent_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent metrics: {str(e)}",
        )


@router.get("/{agent_id}/logs", response_model=AgentLogsResponse)
async def get_agent_logs(
    agent_id: str,
    pagination: PaginationParams = Depends(get_pagination_params),
    level: str = Query(None, description="Filter by log level"),
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentLogsResponse:
    """
    Get recent logs for a specific agent.

    Args:
        agent_id: Agent identifier
        pagination: Pagination parameters
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Agent logs
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        # TODO: Implement log retrieval from centralized logging system
        # For now, return empty logs with placeholder
        logs = []

        return AgentLogsResponse(
            agent_id=agent_id,
            logs=logs,
            total_count=0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_agent_logs_failed", agent_id=agent_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent logs: {str(e)}",
        )


@router.post("/{agent_id}/command", response_model=CommandResponse)
async def send_agent_command(
    agent_id: str,
    request: AgentCommandRequest,
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> CommandResponse:
    """
    Send a command to a specific agent.

    Args:
        agent_id: Agent identifier
        request: Command request with action and parameters

    Returns:
        Command execution result
    """
    try:
        agent = coordinator.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_id}",
            )

        # Check if agent supports commands
        if not hasattr(agent, "handle_command"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agent does not support commands: {agent_id}",
            )

        # Execute command
        result = await agent.handle_command(request.action, request.parameters)

        logger.info(
            "agent_command_executed",
            agent_id=agent_id,
            action=request.action,
        )

        return CommandResponse(
            success=True,
            message="Command executed successfully",
            data=result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "send_agent_command_failed",
            agent_id=agent_id,
            action=request.action,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute command: {str(e)}",
        )
