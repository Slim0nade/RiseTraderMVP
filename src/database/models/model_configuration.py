"""
ModelConfiguration database model for storing agent model configurations.
Supports both LLM configs and RL model configs with versioning.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ModelConfiguration(Base, TimestampMixin):
    """
    ModelConfiguration model for versioned agent configuration storage.

    Stores two types of configurations:
    1. LLM configurations (prompts, system messages, tool definitions)
    2. RL model configurations (reward functions, environment params)

    Supports A/B testing by allowing multiple active configs per agent type.
    """

    __tablename__ = "model_configurations"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique configuration identifier"
    )

    # Configuration identity
    config_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Human-readable config name (e.g., 'gold-position-sizing-v2.1')"
    )

    config_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Configuration type: llm, rl"
    )

    agent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Agent type this config applies to (e.g., 'position_sizing', 'technical_analyst')"
    )

    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Semantic version (e.g., '2.1.0')"
    )

    # LLM configuration (for config_type='llm')
    llm_system_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="System prompt template for LLM agent"
    )

    llm_user_prompt_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User prompt template with {variable} placeholders"
    )

    llm_tools: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="MCP tool definitions available to this agent"
    )

    llm_parameters: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="LLM parameters (temperature, max_tokens, top_p, etc.)"
    )

    # RL configuration (for config_type='rl')
    rl_reward_function: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Reward function config (sharpe_weight, drawdown_weight, etc.)"
    )

    rl_action_space: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Action space definition (discrete/continuous, bounds)"
    )

    rl_observation_space: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Observation space definition (features, normalization)"
    )

    rl_environment_params: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Environment parameters (transaction costs, slippage, etc.)"
    )

    # Status and deployment
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether this config is currently active (can have multiple for A/B testing)"
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this is the default config for this agent type"
    )

    deployed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp when config was deployed to production"
    )

    # A/B testing metadata
    ab_test_group: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="A/B test group identifier (e.g., 'control', 'variant_a')"
    )

    ab_test_allocation_pct: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="Traffic allocation percentage for A/B test (0-100)"
    )

    # Performance tracking
    performance_metrics: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Performance metrics for this config (Sharpe, win rate, etc.)"
    )

    # Metadata
    created_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
        comment="User or system that created this config"
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Configuration notes and change log"
    )

    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Custom tags for organization (e.g., {'env': 'prod', 'experiment': 'prompt-v2'})"
    )

    def __repr__(self) -> str:
        return (
            f"<ModelConfiguration(id={self.id}, name='{self.config_name}', "
            f"type='{self.config_type}', version='{self.version}', active={self.is_active})>"
        )
