"""
Agent database model for multi-agent trading system.
Stores configuration and state for all 12 autonomous agents.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Agent(Base, TimestampMixin):
    """
    Agent model representing a single autonomous trading agent.

    Supports 12 agent types across 5 layers:
    - Analysis Layer: Technical Analyst, Fundamental Analyst, Sentiment Analyst
    - Debate Layer: Devil's Advocate
    - Decision Layer: Position Sizing, Stop Loss, Take Profit, Entry Timing
    - Execution Layer: Trade Executor, Order Monitor
    - Supervisory Layer: Portfolio Allocator, Performance Tracker

    Each agent operates within a strategy team and can be trained with RL.
    """

    __tablename__ = "agents"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique agent identifier"
    )

    # Agent identity
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable agent name (e.g., 'Gold Technical Analyst')"
    )

    agent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Agent type (e.g., 'technical_analyst', 'position_sizing', 'trade_executor')"
    )

    layer: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Agent layer: analysis, debate, decision, execution, supervisory"
    )

    # Strategy team association
    strategy_team_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="FK to strategy_teams table (NULL for global supervisory agents)"
    )

    # LLM configuration
    llm_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ollama",
        comment="LLM provider: ollama, openai, anthropic"
    )

    llm_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model name (e.g., 'qwen2.5:14b', 'deepseek-r1:14b')"
    )

    llm_tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="quick_think",
        comment="LLM tier: quick_think (routine), deep_think (complex reasoning)"
    )

    temperature: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.1,
        comment="LLM temperature (0.0-1.0)"
    )

    max_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=500,
        comment="Maximum tokens per LLM response"
    )

    # RL configuration
    rl_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this agent uses RL for decision-making"
    )

    rl_algorithm: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="RL algorithm: ppo, sac (NULL if rl_enabled=False)"
    )

    rl_model_registry_uri: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="MLflow model URI (e.g., 'models:/position-sizing-gold-v3/Production')"
    )

    # Agent state
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether agent is actively processing events"
    )

    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="idle",
        comment="Current state: idle, processing, error, paused"
    )

    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp of last activity (message processed)"
    )

    # Configuration overrides (JSON)
    config_overrides: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Agent-specific config overrides (e.g., custom prompts, tool settings)"
    )

    # Performance metadata
    total_decisions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total decisions made by this agent"
    )

    avg_decision_time_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Average decision latency in milliseconds"
    )

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

    def __repr__(self) -> str:
        return (
            f"<Agent(id={self.id}, name='{self.name}', type='{self.agent_type}', "
            f"layer='{self.layer}', active={self.is_active})>"
        )
