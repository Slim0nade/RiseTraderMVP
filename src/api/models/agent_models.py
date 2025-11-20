"""
Pydantic models for Agent API endpoints.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Request Models
class AgentCommandRequest(BaseModel):
    """Request model for sending commands to agents."""

    action: str = Field(..., description="Action to execute")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Action parameters"
    )


# Response Models
class AgentStatusResponse(BaseModel):
    """Response model for agent status."""

    agent_id: str
    status: str  # STARTING, RUNNING, PAUSED, STOPPED, ERROR
    priority: int
    uptime_seconds: Optional[float] = None
    events_processed: Optional[int] = None
    errors_count: Optional[int] = None
    last_heartbeat: Optional[datetime] = None
    health_status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "signal_generator",
                "status": "RUNNING",
                "priority": 1,
                "uptime_seconds": 3600.5,
                "events_processed": 1523,
                "errors_count": 0,
                "last_heartbeat": "2024-01-15T10:30:00Z",
                "health_status": "healthy",
                "metadata": {"version": "1.0.0"},
            }
        }


class AgentMetricsResponse(BaseModel):
    """Response model for agent metrics."""

    agent_id: str
    events_processed: int
    events_failed: int
    average_processing_time_ms: float
    last_processed_at: Optional[datetime] = None
    circuit_breaker_status: Optional[str] = None
    failure_count: int = 0
    success_rate: float = 0.0

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "execution",
                "events_processed": 542,
                "events_failed": 3,
                "average_processing_time_ms": 45.2,
                "last_processed_at": "2024-01-15T10:35:00Z",
                "circuit_breaker_status": "CLOSED",
                "failure_count": 3,
                "success_rate": 99.45,
            }
        }


class AgentLogEntry(BaseModel):
    """Log entry for an agent."""

    timestamp: datetime
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message: str
    context: Optional[Dict[str, Any]] = None


class AgentLogsResponse(BaseModel):
    """Response model for agent logs."""

    agent_id: str
    logs: List[AgentLogEntry]
    total_count: int
    page: int
    page_size: int


class AgentListResponse(BaseModel):
    """Response model for listing all agents."""

    agents: List[AgentStatusResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "agents": [
                    {
                        "agent_id": "signal_generator",
                        "status": "RUNNING",
                        "priority": 1,
                        "uptime_seconds": 3600.5,
                        "events_processed": 1523,
                    }
                ],
                "total": 10,
            }
        }


class CommandResponse(BaseModel):
    """Response model for agent commands."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Command executed successfully",
                "data": {"result": "Signal generated for CrudeOIL"},
            }
        }


class AgentOperationResponse(BaseModel):
    """Response for agent start/stop/restart operations."""

    success: bool
    message: str
    agent_id: str
    new_status: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Agent started successfully",
                "agent_id": "market_data",
                "new_status": "RUNNING",
            }
        }
