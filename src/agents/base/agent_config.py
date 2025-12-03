"""
Agent configuration and state schemas.
Core schemas for agent initialization and state management.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class AgentLayer(str, Enum):
    """Agent layer classification."""

    ANALYSIS = "analysis"
    DEBATE = "debate"
    DECISION = "decision"
    EXECUTION = "execution"
    SUPERVISORY = "supervisory"


class AgentType(str, Enum):
    """Agent type enumeration."""

    # Analysis Layer
    TECHNICAL_ANALYST = "technical_analyst"
    FUNDAMENTAL_ANALYST = "fundamental_analyst"
    SENTIMENT_ANALYST = "sentiment_analyst"

    # Debate Layer
    DEVILS_ADVOCATE = "devils_advocate"

    # Decision Layer
    POSITION_SIZING = "position_sizing"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    ENTRY_TIMING = "entry_timing"

    # Execution Layer
    TRADE_EXECUTOR = "trade_executor"
    ORDER_MONITOR = "order_monitor"

    # Supervisory Layer
    PORTFOLIO_ALLOCATOR = "portfolio_allocator"
    PERFORMANCE_TRACKER = "performance_tracker"


class AgentState(str, Enum):
    """Agent operational state."""

    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    ERROR = "error"
    PAUSED = "paused"
    STOPPED = "stopped"


class LLMTier(str, Enum):
    """LLM tier for cost optimization."""

    QUICK_THINK = "quick_think"  # Qwen2.5:14b - routine tasks
    DEEP_THINK = "deep_think"  # DeepSeek-R1:14b - complex reasoning


class RLAlgorithm(str, Enum):
    """Reinforcement learning algorithm."""

    PPO = "ppo"  # Proximal Policy Optimization (discrete actions)
    SAC = "sac"  # Soft Actor-Critic (continuous actions)


class AgentConfig(BaseModel):
    """
    Agent configuration schema.

    Defines the complete configuration for an agent instance,
    including LLM settings, RL settings, and agent-specific parameters.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Gold Technical Analyst",
                "agent_type": "technical_analyst",
                "layer": "analysis",
                "strategy_team_id": "550e8400-e29b-41d4-a716-446655440000",
                "llm_provider": "ollama",
                "llm_model": "qwen2.5:14b",
                "llm_tier": "quick_think",
                "temperature": 0.1,
                "max_tokens": 500
            }
        }
    )

    # Agent identity
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Human-readable agent name"
    )

    agent_type: AgentType = Field(
        ...,
        description="Agent type classification"
    )

    layer: AgentLayer = Field(
        ...,
        description="Agent layer in the multi-agent architecture"
    )

    strategy_team_id: Optional[UUID] = Field(
        None,
        description="Strategy team this agent belongs to (NULL for global agents)"
    )

    # LLM configuration
    llm_provider: str = Field(
        default="ollama",
        description="LLM provider: ollama, openai, anthropic"
    )

    llm_model: str = Field(
        ...,
        description="LLM model name (e.g., 'qwen2.5:14b', 'deepseek-r1:14b')"
    )

    llm_tier: LLMTier = Field(
        default=LLMTier.QUICK_THINK,
        description="LLM tier for cost optimization"
    )

    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM temperature (0.0-2.0)"
    )

    max_tokens: int = Field(
        default=500,
        gt=0,
        le=4096,
        description="Maximum tokens per LLM response"
    )

    system_prompt: Optional[str] = Field(
        None,
        description="Custom system prompt (overrides default)"
    )

    # RL configuration
    rl_enabled: bool = Field(
        default=False,
        description="Whether this agent uses RL for decision-making"
    )

    rl_algorithm: Optional[RLAlgorithm] = Field(
        None,
        description="RL algorithm if rl_enabled=True"
    )

    rl_model_uri: Optional[str] = Field(
        None,
        description="MLflow model URI if RL-enabled"
    )

    # MCP tools
    available_tools: List[str] = Field(
        default_factory=list,
        description="List of MCP tool names available to this agent"
    )

    # Agent-specific parameters
    config_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific configuration overrides"
    )

    # Operational settings
    max_concurrent_tasks: int = Field(
        default=1,
        ge=1,
        description="Maximum concurrent tasks this agent can handle"
    )

    task_timeout_seconds: int = Field(
        default=60,
        gt=0,
        description="Task timeout in seconds"
    )

    retry_on_error: bool = Field(
        default=True,
        description="Whether to retry tasks on error"
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts"
    )

    # Logging and monitoring
    log_decisions: bool = Field(
        default=True,
        description="Whether to log decisions to decision_log table"
    )

    enable_telemetry: bool = Field(
        default=True,
        description="Whether to emit telemetry events"
    )


class AgentStateModel(BaseModel):
    """
    Agent state model for runtime state tracking.

    Represents the current operational state of an agent instance.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_type": "technical_analyst",
                "state": "processing",
                "current_task": "analyze_market_data",
                "tasks_completed": 42,
                "total_errors": 1
            }
        }
    )

    # Agent identification
    agent_id: UUID = Field(
        ...,
        description="Agent instance ID"
    )

    agent_type: AgentType = Field(
        ...,
        description="Agent type"
    )

    # Current state
    state: AgentState = Field(
        default=AgentState.IDLE,
        description="Current operational state"
    )

    last_state_change: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of last state change"
    )

    # Current activity
    current_task: Optional[str] = Field(
        None,
        description="Description of current task if processing"
    )

    current_event_id: Optional[UUID] = Field(
        None,
        description="Event ID being processed"
    )

    task_started_at: Optional[datetime] = Field(
        None,
        description="Timestamp when current task started"
    )

    # Performance metrics
    tasks_completed: int = Field(
        default=0,
        ge=0,
        description="Total tasks completed"
    )

    avg_task_duration_ms: Optional[float] = Field(
        None,
        ge=0,
        description="Average task duration in milliseconds"
    )

    last_active_at: Optional[datetime] = Field(
        None,
        description="Timestamp of last activity"
    )

    # Error tracking
    total_errors: int = Field(
        default=0,
        ge=0,
        description="Total errors encountered"
    )

    last_error: Optional[str] = Field(
        None,
        description="Last error message"
    )

    last_error_at: Optional[datetime] = Field(
        None,
        description="Timestamp of last error"
    )

    # Resource usage
    memory_usage_mb: Optional[float] = Field(
        None,
        ge=0,
        description="Current memory usage in MB"
    )

    cpu_usage_percent: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Current CPU usage percentage"
    )

    # Health status
    is_healthy: bool = Field(
        default=True,
        description="Overall health status"
    )

    health_check_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of last health check"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional state metadata"
    )


class AgentPerformanceMetrics(BaseModel):
    """
    Agent performance metrics for monitoring and optimization.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_type": "position_sizing",
                "total_decisions": 156,
                "avg_decision_time_ms": 125.5,
                "decision_accuracy": 0.68,
                "sharpe_contribution": 0.45
            }
        }
    )

    # Agent identification
    agent_id: UUID = Field(
        ...,
        description="Agent instance ID"
    )

    agent_type: AgentType = Field(
        ...,
        description="Agent type"
    )

    # Decision metrics
    total_decisions: int = Field(
        default=0,
        ge=0,
        description="Total decisions made"
    )

    avg_decision_time_ms: Optional[float] = Field(
        None,
        ge=0,
        description="Average decision latency in milliseconds"
    )

    decisions_per_hour: Optional[float] = Field(
        None,
        ge=0,
        description="Decision throughput (decisions/hour)"
    )

    # Accuracy metrics (where applicable)
    decision_accuracy: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Decision accuracy score (0.0-1.0) if measurable"
    )

    profitable_decisions: Optional[int] = Field(
        None,
        ge=0,
        description="Number of decisions that led to profitable trades"
    )

    # Impact metrics
    total_pnl_impact_usd: Optional[float] = Field(
        None,
        description="Total P&L impact of this agent's decisions (USD)"
    )

    sharpe_contribution: Optional[float] = Field(
        None,
        description="Contribution to portfolio Sharpe ratio"
    )

    # Error metrics
    total_errors: int = Field(
        default=0,
        ge=0,
        description="Total errors encountered"
    )

    error_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Error rate (errors / total decisions)"
    )

    # Timestamp
    metrics_updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when metrics were last updated"
    )

    # Evaluation period
    evaluation_start_date: Optional[datetime] = Field(
        None,
        description="Start of evaluation period"
    )

    evaluation_end_date: Optional[datetime] = Field(
        None,
        description="End of evaluation period"
    )
