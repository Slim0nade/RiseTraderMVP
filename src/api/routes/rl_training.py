"""
RL Training API Routes.

Endpoints for triggering and monitoring reinforcement learning training runs.
Part of User Story 5 (Phase 7) - Reinforcement Learning Training.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from ...services.rl_training_service import (
    RLTrainingService,
    RLAlgorithm,
    TrainingStatus,
)
from ..database import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rl-training", tags=["rl-training"])


# ============================================================================
# Request/Response Models
# ============================================================================

class StartTrainingRequest(BaseModel):
    """Request to start RL training."""
    agent_type: str = Field(
        ...,
        description="Agent type to train",
        pattern="^(position_sizing|stop_loss|take_profit|trade_decision)$",
    )
    algorithm: RLAlgorithm = Field(
        default=RLAlgorithm.PPO,
        description="RL algorithm (PPO for discrete, SAC for continuous)",
    )
    episodes: int = Field(
        default=1000,
        ge=100,
        le=100000,
        description="Number of training episodes",
    )
    symbol: str = Field(
        default="Gold",
        description="Training symbol",
    )
    timeframe: str = Field(
        default="4H",
        pattern="^(1H|4H|1D)$",
        description="Training timeframe",
    )
    walk_forward: bool = Field(
        default=False,
        description="Enable walk-forward validation",
    )
    walk_forward_windows: int = Field(
        default=5,
        ge=2,
        le=20,
        description="Number of walk-forward windows",
    )


class StartTrainingResponse(BaseModel):
    """Response after starting training."""
    run_id: UUID = Field(..., description="Training run ID")
    status: str = Field(..., description="Initial status")
    message: str = Field(..., description="Status message")


class TrainingStatusResponse(BaseModel):
    """Training run status."""
    run_id: UUID
    agent_type: str
    algorithm: str
    status: str
    progress: Optional[float] = Field(None, ge=0.0, le=1.0, description="Training progress (0-1)")
    current_episode: Optional[int] = None
    total_episodes: Optional[int] = None
    metrics: Optional[dict] = Field(None, description="Training metrics")
    mlflow_run_id: Optional[str] = Field(None, description="MLflow experiment run ID")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None


class TrainingListResponse(BaseModel):
    """List of training runs."""
    runs: List[TrainingStatusResponse]
    total: int


class ModelInfo(BaseModel):
    """Trained model information."""
    run_id: UUID
    agent_type: str
    algorithm: str
    metrics: dict
    mlflow_run_id: str
    environment: str  # "staging" or "production"
    deployed_at: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/start", response_model=StartTrainingResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_training(
    request: StartTrainingRequest,
    db: AsyncSession = Depends(get_db),
) -> StartTrainingResponse:
    """
    Start offline RL training for an agent.

    This endpoint triggers asynchronous training that runs in the background.
    Use the returned run_id to poll for status and metrics.

    **Note**: This is a skeleton implementation for Phase 7 (User Story 5).
    Full implementation includes:
    - Gymnasium trading environments
    - PPO/SAC training with Stable-Baselines3
    - Walk-forward validation
    - MLflow experiment tracking

    Args:
        request: Training configuration

    Returns:
        Training run ID and initial status
    """
    try:
        service = RLTrainingService(db)

        # Start training (async - returns immediately)
        run_id = await service.start_training(
            agent_type=request.agent_type,
            algorithm=request.algorithm,
            episodes=request.episodes,
            symbol=request.symbol,
            timeframe=request.timeframe,
            walk_forward=request.walk_forward,
            walk_forward_windows=request.walk_forward_windows,
        )

        logger.info(
            "rl_training_started",
            run_id=run_id,
            agent_type=request.agent_type,
            algorithm=request.algorithm,
        )

        return StartTrainingResponse(
            run_id=run_id,
            status=TrainingStatus.PENDING.value,
            message=f"Training started for {request.agent_type} agent. Skeleton implementation - Phase 7 (US5).",
        )

    except Exception as e:
        logger.error("start_training_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training: {str(e)}",
        )


@router.get("/{run_id}", response_model=TrainingStatusResponse)
async def get_training_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TrainingStatusResponse:
    """
    Get status and metrics for a training run.

    Args:
        run_id: Training run ID

    Returns:
        Training status with metrics
    """
    try:
        service = RLTrainingService(db)
        status_data = await service.get_training_status(run_id)

        return TrainingStatusResponse(
            run_id=run_id,
            agent_type=status_data.get("agent_type", "unknown"),
            algorithm=status_data.get("algorithm", "ppo"),
            status=status_data.get("status", TrainingStatus.PENDING.value),
            progress=status_data.get("progress"),
            current_episode=status_data.get("current_episode"),
            total_episodes=status_data.get("total_episodes"),
            metrics=status_data.get("metrics"),
            mlflow_run_id=status_data.get("mlflow_run_id"),
        )

    except Exception as e:
        logger.error("get_training_status_failed", run_id=run_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training run not found: {run_id}",
        )


@router.post("/{run_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_training(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Cancel a running training job.

    Args:
        run_id: Training run ID

    Returns:
        Cancellation confirmation
    """
    try:
        service = RLTrainingService(db)
        cancelled = await service.cancel_training(run_id)

        if cancelled:
            logger.info("training_cancelled", run_id=run_id)
            return {"run_id": str(run_id), "status": "cancelled"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Training run cannot be cancelled (may already be completed)",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("cancel_training_failed", run_id=run_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel training: {str(e)}",
        )


@router.get("", response_model=TrainingListResponse)
async def list_training_runs(
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    status: Optional[TrainingStatus] = Query(None, description="Filter by status"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of runs to return"),
    db: AsyncSession = Depends(get_db),
) -> TrainingListResponse:
    """
    List recent training runs with optional filtering.

    Args:
        agent_type: Filter by agent type
        status: Filter by training status
        limit: Maximum number of runs

    Returns:
        List of training runs
    """
    try:
        service = RLTrainingService(db)
        runs = await service.list_training_runs(
            agent_type=agent_type,
            status=status,
            limit=limit,
        )

        # Convert to response models
        run_responses = [
            TrainingStatusResponse(
                run_id=UUID(run["run_id"]),
                agent_type=run.get("agent_type", "unknown"),
                algorithm=run.get("algorithm", "ppo"),
                status=run.get("status", TrainingStatus.PENDING.value),
                progress=run.get("progress"),
                current_episode=run.get("current_episode"),
                total_episodes=run.get("total_episodes"),
                metrics=run.get("metrics"),
                mlflow_run_id=run.get("mlflow_run_id"),
            )
            for run in runs
        ]

        return TrainingListResponse(
            runs=run_responses,
            total=len(run_responses),
        )

    except Exception as e:
        logger.error("list_training_runs_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list training runs: {str(e)}",
        )


@router.get("/models/best/{agent_type}", response_model=ModelInfo)
async def get_best_model(
    agent_type: str,
    metric: str = Query("sharpe_ratio", description="Performance metric to compare"),
    db: AsyncSession = Depends(get_db),
) -> ModelInfo:
    """
    Get best performing model for an agent type.

    Args:
        agent_type: Type of agent
        metric: Performance metric (e.g., "sharpe_ratio", "sortino_ratio", "max_drawdown")

    Returns:
        Best model info with metrics
    """
    try:
        service = RLTrainingService(db)
        model_info = await service.get_best_model(agent_type, metric)

        if not model_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No trained models found for agent type: {agent_type}",
            )

        return ModelInfo(**model_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_best_model_failed", agent_type=agent_type, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get best model: {str(e)}",
        )


@router.post("/models/{run_id}/deploy", status_code=status.HTTP_200_OK)
async def deploy_model(
    run_id: UUID,
    environment: str = Query("staging", pattern="^(staging|production)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Deploy trained model to staging or production.

    **Warning**: Production deployment will replace the current model and
    affect live trading agents. Use with caution.

    Args:
        run_id: Training run ID
        environment: Deployment environment ("staging" or "production")

    Returns:
        Deployment confirmation
    """
    try:
        service = RLTrainingService(db)
        deployed = await service.deploy_model(run_id, environment)

        if deployed:
            logger.info(
                "model_deployed",
                run_id=run_id,
                environment=environment,
            )
            return {
                "run_id": str(run_id),
                "environment": environment,
                "status": "deployed",
                "message": f"Model deployed to {environment}. Skeleton implementation - Phase 7 (US5).",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model deployment failed validation checks",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("deploy_model_failed", run_id=run_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deploy model: {str(e)}",
        )
