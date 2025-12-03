"""
MCPTool database model for Model Context Protocol tool registry.
Tracks available tools that agents can use for specialized calculations.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class MCPTool(Base, TimestampMixin):
    """
    MCPTool model for registering MCP tools available to agents.

    MCP (Model Context Protocol) tools provide specialized capabilities:
    - ML Forecast Tool: Get price predictions from ML models
    - Regime Detection Tool: Identify current market regime
    - Technical Indicator Tool: Calculate custom indicators
    - Risk Calculator Tool: Compute position risk metrics
    - Sentiment Analysis Tool: Analyze market sentiment

    Tools are registered here and made available to specific agent types.
    """

    __tablename__ = "mcp_tools"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique tool identifier"
    )

    # Tool identity
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique tool name (e.g., 'ml_forecast', 'regime_detection')"
    )

    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable display name (e.g., 'ML Price Forecast Tool')"
    )

    tool_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Tool category: ml_prediction, calculation, data_retrieval, analysis"
    )

    # Tool definition (MCP spec)
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Tool description for LLM (what the tool does and when to use it)"
    )

    input_schema: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON schema for tool input parameters (Pydantic-compatible)"
    )

    output_schema: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON schema for tool output (Pydantic-compatible)"
    )

    # Implementation details
    implementation_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Python import path (e.g., 'src.ml.tools.ml_forecast_tool.MLForecastTool')"
    )

    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
        comment="Tool version (semantic versioning)"
    )

    # Access control
    allowed_agent_types: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=[],
        comment=(
            "List of agent types allowed to use this tool "
            "(e.g., ['technical_analyst', 'position_sizing']). Empty list = all agents."
        )
    )

    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether tool usage requires human approval (for high-risk operations)"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether tool is currently available"
    )

    is_beta: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether tool is in beta testing"
    )

    # Performance tracking
    total_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of times this tool has been called"
    )

    successful_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of successful tool calls"
    )

    avg_execution_time_ms: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Average execution time in milliseconds"
    )

    last_called_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp of last tool call"
    )

    # Error tracking
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total errors encountered"
    )

    last_error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Most recent error message for debugging"
    )

    # Configuration
    config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Tool-specific configuration (e.g., API endpoints, model URIs, timeouts)"
    )

    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Rate limit for this tool (calls per minute). NULL = no limit."
    )

    timeout_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=30,
        comment="Tool execution timeout in seconds"
    )

    # Metadata
    created_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
        comment="User or system that created this tool"
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Tool notes and usage guidelines"
    )

    documentation_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL to tool documentation"
    )

    def __repr__(self) -> str:
        return (
            f"<MCPTool(id={self.id}, name='{self.tool_name}', type='{self.tool_type}', "
            f"version='{self.version}', active={self.is_active}, calls={self.total_calls})>"
        )
