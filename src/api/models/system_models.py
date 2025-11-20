"""
Pydantic models for System API endpoints.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Response Models
class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str  # healthy, degraded, unhealthy
    version: str
    timestamp: datetime
    uptime_seconds: float
    components: Dict[str, str]  # component_name -> status

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2024-01-15T10:30:00Z",
                "uptime_seconds": 3600.5,
                "components": {
                    "database": "healthy",
                    "redis": "healthy",
                    "mcp_server": "healthy",
                    "agents": "healthy",
                },
            }
        }


class SystemStatusResponse(BaseModel):
    """Detailed system status."""

    status: str
    version: str
    timestamp: datetime
    uptime_seconds: float

    # Database
    database_connected: bool
    database_pool_size: int
    database_active_connections: int

    # Redis
    redis_connected: bool
    redis_memory_used: Optional[int] = None

    # Agents
    total_agents: int
    running_agents: int
    paused_agents: int
    stopped_agents: int
    agents_in_error: int

    # MCP Server
    mcp_server_running: bool
    event_queue_size: int
    events_processed_total: int

    # Trading
    open_positions_count: int
    total_trades_today: int
    paper_trading_enabled: bool
    live_trading_enabled: bool

    # Performance
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2024-01-15T10:30:00Z",
                "uptime_seconds": 3600.5,
                "database_connected": True,
                "database_pool_size": 20,
                "database_active_connections": 5,
                "redis_connected": True,
                "total_agents": 10,
                "running_agents": 10,
                "paused_agents": 0,
                "stopped_agents": 0,
                "agents_in_error": 0,
                "mcp_server_running": True,
                "event_queue_size": 15,
                "events_processed_total": 5420,
                "open_positions_count": 5,
                "total_trades_today": 25,
                "paper_trading_enabled": True,
                "live_trading_enabled": False,
                "cpu_percent": 15.5,
                "memory_percent": 45.2,
                "disk_percent": 60.1,
            }
        }


class MetricsResponse(BaseModel):
    """Prometheus metrics response."""

    metrics: str  # Prometheus text format

    class Config:
        json_schema_extra = {
            "example": {
                "metrics": "# HELP api_requests_total Total API requests\n# TYPE api_requests_total counter\napi_requests_total{method=\"GET\",endpoint=\"/health\"} 150\n"
            }
        }


class EmergencyStopRequest(BaseModel):
    """Request for emergency stop."""

    reason: str = Field(..., description="Reason for emergency stop")
    close_positions: bool = Field(
        True, description="Whether to close all open positions"
    )
    stop_agents: bool = Field(True, description="Whether to stop all agents")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Market volatility detected",
                "close_positions": True,
                "stop_agents": True,
            }
        }


class EmergencyStopResponse(BaseModel):
    """Response for emergency stop operation."""

    success: bool
    message: str
    timestamp: datetime
    positions_closed: int
    agents_stopped: int
    details: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Emergency stop completed successfully",
                "timestamp": "2024-01-15T10:30:00Z",
                "positions_closed": 5,
                "agents_stopped": 10,
                "details": {
                    "reason": "Market volatility detected",
                    "total_pnl": -150.0,
                },
            }
        }


class RestartRequest(BaseModel):
    """Request for system restart."""

    restart_agents: bool = Field(True, description="Restart all agents")
    reload_config: bool = Field(True, description="Reload configuration")
    reason: Optional[str] = Field(None, description="Reason for restart")

    class Config:
        json_schema_extra = {
            "example": {
                "restart_agents": True,
                "reload_config": True,
                "reason": "Configuration update",
            }
        }


class RestartResponse(BaseModel):
    """Response for system restart operation."""

    success: bool
    message: str
    timestamp: datetime
    agents_restarted: int
    config_reloaded: bool

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "System restarted successfully",
                "timestamp": "2024-01-15T10:30:00Z",
                "agents_restarted": 10,
                "config_reloaded": True,
            }
        }


class ComponentHealthResponse(BaseModel):
    """Individual component health status."""

    component: str
    status: str  # healthy, degraded, unhealthy
    message: Optional[str] = None
    last_check: datetime
    details: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "component": "database",
                "status": "healthy",
                "message": "Database connection active",
                "last_check": "2024-01-15T10:30:00Z",
                "details": {
                    "pool_size": 20,
                    "active_connections": 5,
                    "response_time_ms": 2.5,
                },
            }
        }


class ComponentHealthListResponse(BaseModel):
    """List of component health statuses."""

    components: List[ComponentHealthResponse]
    overall_status: str
    timestamp: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "components": [],
                "overall_status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }
