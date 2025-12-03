"""
Agent Pipeline API Routes

Endpoints for running intelligent agent pipelines:
- Analysis pipeline (Technical, Fundamental, Sentiment)
- Decision pipeline (Position Sizing, Stop-Loss, Take-Profit)
- Full trading pipeline (Analysis → Decision)
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.agent_service import AgentService
from src.api.dependencies import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent-pipelines", tags=["agent-pipelines"])


# ============================================================================
# Request/Response Schemas
# ============================================================================

class AnalysisRequest(BaseModel):
    """Request schema for analysis pipeline."""

    symbol: str = Field(..., description="Trading symbol (e.g., 'Gold', 'CrudeOIL')")
    timeframe: str = Field(default="4H", description="Analysis timeframe ('1H', '4H', '1D')")
    strategy_team_id: Optional[UUID] = Field(None, description="Optional strategy team ID")


class DecisionRequest(BaseModel):
    """Request schema for decision pipeline."""

    symbol: str = Field(..., description="Trading symbol")
    analysis: Dict[str, Any] = Field(..., description="Analysis pipeline output")
    trade_context: Dict[str, Any] = Field(
        ...,
        description="Trading context (account_balance, current_drawdown, etc.)",
    )
    strategy_team_id: Optional[UUID] = Field(None, description="Optional strategy team ID")


class FullPipelineRequest(BaseModel):
    """Request schema for full trading pipeline."""

    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(default="4H", description="Analysis timeframe")
    trade_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Trading context (account_balance, drawdown, etc.)",
    )
    strategy_team_id: Optional[UUID] = Field(None, description="Optional strategy team ID")

    class Config:
        schema_extra = {
            "example": {
                "symbol": "Gold",
                "timeframe": "4H",
                "trade_context": {
                    "account_balance": 50000.0,
                    "current_drawdown": 0.03,
                    "trade_conviction": 0.75,
                    "win_rate": 0.60,
                    "avg_win": 125,
                    "avg_loss": 50,
                    "correlation_with_existing": 0.0,
                    "major_event_within_24h": False,
                    "major_event_within_48h": True,
                },
            }
        }


class RegistryHealthResponse(BaseModel):
    """Response schema for registry health check."""

    timestamp: str
    total_agents: int
    healthy: int
    unhealthy: int
    overall_status: str
    agents: list


class RegistryStatsResponse(BaseModel):
    """Response schema for registry statistics."""

    total_agents: int
    by_type: Dict[str, int]
    by_symbol: Dict[str, int]
    by_state: Dict[str, int]


# ============================================================================
# Analysis Pipeline Endpoints
# ============================================================================

@router.post("/analysis", response_model=Dict[str, Any])
async def run_analysis_pipeline(
    request: AnalysisRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Run analysis pipeline for a symbol.

    Executes in parallel:
    - Technical analysis (ML forecasts, indicators, regime)
    - Fundamental analysis (macro conditions, events)
    - Sentiment analysis (positioning, crowd psychology)

    Returns:
        Analysis results with technical, fundamental, and sentiment reports
    """
    try:
        logger.info(
            "analysis_pipeline_request",
            symbol=request.symbol,
            timeframe=request.timeframe,
        )

        service = AgentService(session)

        result = await service.run_analysis_pipeline(
            symbol=request.symbol,
            timeframe=request.timeframe,
            strategy_team_id=request.strategy_team_id,
        )

        logger.info(
            "analysis_pipeline_success",
            symbol=request.symbol,
            execution_time=result["metadata"]["execution_time_seconds"],
        )

        return result

    except Exception as e:
        logger.error(
            "analysis_pipeline_failed",
            symbol=request.symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis pipeline failed: {str(e)}",
        )


# ============================================================================
# Decision Pipeline Endpoints
# ============================================================================

@router.post("/decision", response_model=Dict[str, Any])
async def run_decision_pipeline(
    request: DecisionRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Run decision pipeline for a trade.

    Executes sequentially:
    - Position sizing (dynamic Kelly-based)
    - Stop-loss placement (structure + ATR adaptive)
    - Take-profit targeting (probabilistic EV optimization)

    Returns:
        Decision results with position size, stop-loss, and take-profit
    """
    try:
        logger.info(
            "decision_pipeline_request",
            symbol=request.symbol,
        )

        service = AgentService(session)

        result = await service.run_decision_pipeline(
            symbol=request.symbol,
            analysis=request.analysis,
            trade_context=request.trade_context,
            strategy_team_id=request.strategy_team_id,
        )

        logger.info(
            "decision_pipeline_success",
            symbol=request.symbol,
            execution_time=result["metadata"]["execution_time_seconds"],
            lot_quantity=result["position_size"]["lot_quantity"],
        )

        return result

    except Exception as e:
        logger.error(
            "decision_pipeline_failed",
            symbol=request.symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Decision pipeline failed: {str(e)}",
        )


# ============================================================================
# Full Pipeline Endpoint
# ============================================================================

@router.post("/full", response_model=Dict[str, Any])
async def run_full_pipeline(
    request: FullPipelineRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Run complete trading pipeline: Analysis → Decision.

    This is the primary endpoint for generating complete trade recommendations.

    Returns:
        Complete pipeline results with analysis and decisions
    """
    try:
        logger.info(
            "full_pipeline_request",
            symbol=request.symbol,
            timeframe=request.timeframe,
        )

        service = AgentService(session)

        result = await service.run_full_trading_pipeline(
            symbol=request.symbol,
            timeframe=request.timeframe,
            trade_context=request.trade_context,
            strategy_team_id=request.strategy_team_id,
        )

        logger.info(
            "full_pipeline_success",
            symbol=request.symbol,
            execution_time=result["metadata"]["total_execution_time_seconds"],
        )

        return result

    except Exception as e:
        logger.error(
            "full_pipeline_failed",
            symbol=request.symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Full pipeline failed: {str(e)}",
        )


# ============================================================================
# Registry & Health Endpoints
# ============================================================================

@router.get("/health", response_model=RegistryHealthResponse)
async def get_registry_health(
    session: AsyncSession = Depends(get_db),
) -> RegistryHealthResponse:
    """
    Get health status of all registered agents.

    Returns:
        Health status with agent details
    """
    try:
        service = AgentService(session)
        health = await service.get_registry_health()

        return RegistryHealthResponse(**health)

    except Exception as e:
        logger.error(
            "registry_health_check_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )


@router.get("/stats", response_model=RegistryStatsResponse)
async def get_registry_stats(
    session: AsyncSession = Depends(get_db),
) -> RegistryStatsResponse:
    """
    Get agent registry statistics.

    Returns:
        Statistics about registered agents
    """
    try:
        service = AgentService(session)
        stats = service.get_registry_stats()

        return RegistryStatsResponse(**stats)

    except Exception as e:
        logger.error(
            "registry_stats_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stats retrieval failed: {str(e)}",
        )


@router.post("/shutdown", response_model=Dict[str, str])
async def shutdown_all_agents(
    session: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """
    Gracefully shutdown all registered agents.

    Returns:
        Shutdown confirmation
    """
    try:
        logger.warning("shutdown_all_agents_requested")

        service = AgentService(session)
        await service.shutdown_all_agents()

        return {"status": "success", "message": "All agents shutdown successfully"}

    except Exception as e:
        logger.error(
            "shutdown_all_agents_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Shutdown failed: {str(e)}",
        )
