"""
RLTrainingRun database model for tracking reinforcement learning training experiments.
Integrates with MLflow for artifact storage and experiment tracking.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class RLTrainingRun(Base, TimestampMixin):
    """
    RLTrainingRun model for tracking RL training experiments.

    Tracks training runs for RL-enabled agents (Position Sizing, Stop Loss, etc.)
    using walk-forward validation with Sharpe ratio >1.2 OOS requirement.

    Integrates with MLflow for:
    - Experiment tracking
    - Model artifact storage
    - Model registry (Production, Staging, Archived)
    """

    __tablename__ = "rl_training_runs"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique training run identifier"
    )

    # Agent association
    agent_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="FK to agents table (the agent being trained)"
    )

    agent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Agent type (denormalized for query performance)"
    )

    strategy_team_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="FK to strategy_teams table (NULL for global agents)"
    )

    # MLflow integration
    mlflow_run_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="MLflow run ID for this training run"
    )

    mlflow_experiment_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="MLflow experiment ID"
    )

    # Training configuration
    algorithm: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="RL algorithm: ppo (discrete), sac (continuous)"
    )

    hyperparameters: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Training hyperparameters (learning_rate, gamma, batch_size, etc.)"
    )

    # Walk-forward validation configuration
    train_start_date: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="Training data start date"
    )

    train_end_date: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="Training data end date"
    )

    test_start_date: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="Out-of-sample test data start date"
    )

    test_end_date: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="Out-of-sample test data end date"
    )

    # Training progress
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        index=True,
        comment="Status: running, completed, failed, cancelled"
    )

    total_timesteps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total training timesteps (RL environment steps)"
    )

    current_timestep: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Current training timestep"
    )

    training_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total training duration in seconds"
    )

    # In-sample (training) performance
    train_mean_reward: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Mean episodic reward on training data"
    )

    train_sharpe_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Sharpe ratio on training data"
    )

    train_max_drawdown: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Maximum drawdown on training data (negative value)"
    )

    # Out-of-sample (test) performance
    test_mean_reward: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Mean episodic reward on OOS test data"
    )

    test_sharpe_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        index=True,
        comment="Sharpe ratio on OOS test data (MUST be >1.2 for promotion)"
    )

    test_max_drawdown: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Maximum drawdown on OOS test data (negative value)"
    )

    test_win_rate: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Win rate on OOS test data (0.0-1.0)"
    )

    # Model deployment
    passed_validation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether model passed OOS Sharpe >1.2 threshold"
    )

    model_registry_uri: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="MLflow model registry URI if promoted (e.g., 'models:/position-sizing-gold/Production')"
    )

    deployed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp when model was deployed to production"
    )

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if training failed"
    )

    # Metadata
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="manual",
        comment="Who/what triggered training: manual, scheduled, performance_degradation"
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Training notes and observations"
    )

    def __repr__(self) -> str:
        return (
            f"<RLTrainingRun(id={self.id}, agent_type='{self.agent_type}', "
            f"algorithm='{self.algorithm}', status='{self.status}', "
            f"test_sharpe={self.test_sharpe_ratio})>"
        )
