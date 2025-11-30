"""
Trading Strategies API Routes

Endpoints for retrieving trading strategy information, allocations, and performance metrics.
"""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.api.models.strategies import (
    StrategyResponse,
    StrategyListResponse,
    StrategyAllocationResponse,
    StrategyAllocationListResponse,
    StrategyPerformanceResponse,
)
from src.api.models.common import ErrorResponse
from src.api.dependencies import get_db, get_redis
from src.services.strategy_service import StrategyService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get(
    "",
    response_model=StrategyListResponse,
    responses={
        200: {"description": "Strategies retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_all_strategies(
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
) -> StrategyListResponse:
    """
    Get all trading strategies.

    Returns list of all configured trading strategies with their current
    status, allocated capital, and parameters. Results are cached for 1 hour.

    Args:
        db: Database session
        redis: Redis client for caching

    Returns:
        StrategyListResponse with list of all strategies
    """
    try:
        logger.info("get_all_strategies")

        service = StrategyService(db, redis)
        strategies = await service.get_all_strategies()

        return StrategyListResponse(
            data=[StrategyResponse.model_validate(s) for s in strategies],
            total=len(strategies)
        )

    except Exception as e:
        logger.error(
            "get_all_strategies_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve strategies: {str(e)}"
        )


@router.get(
    "/{strategy_id}/allocations",
    response_model=StrategyAllocationListResponse,
    responses={
        200: {"description": "Strategy allocations retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Strategy not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_strategy_allocations(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
) -> StrategyAllocationListResponse:
    """
    Get capital allocation history for a strategy.

    Returns the historical record of capital allocations for the specified strategy,
    ordered by date (most recent first). Shows how capital allocation has changed over time.

    Args:
        strategy_id: Strategy identifier
        db: Database session
        redis: Redis client for caching

    Returns:
        StrategyAllocationListResponse with allocation history
    """
    try:
        logger.info(
            "get_strategy_allocations",
            strategy_id=strategy_id
        )

        service = StrategyService(db, redis)

        # First check if strategy exists
        strategy = await service.repository.get_strategy_by_id(strategy_id)
        if not strategy:
            logger.warning(
                "strategy_not_found",
                strategy_id=strategy_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with ID {strategy_id} not found"
            )

        allocations = await service.get_strategy_allocations(strategy_id)

        return StrategyAllocationListResponse(
            data=[StrategyAllocationResponse.model_validate(a) for a in allocations],
            total=len(allocations)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_strategy_allocations_failed",
            strategy_id=strategy_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve allocations for strategy {strategy_id}: {str(e)}"
        )


@router.get(
    "/{strategy_id}/performance",
    response_model=StrategyPerformanceResponse,
    responses={
        200: {"description": "Strategy performance retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Strategy or performance data not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_strategy_performance(
    strategy_id: int,
    period: str = Query("monthly", description="Performance period (daily, weekly, monthly, all_time)"),
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
) -> StrategyPerformanceResponse:
    """
    Get performance metrics for a strategy.

    Returns comprehensive performance statistics including win rate, profit/loss,
    Sharpe ratio, and drawdown metrics for the specified period.

    Args:
        strategy_id: Strategy identifier
        period: Performance period filter (daily, weekly, monthly, all_time)
        db: Database session
        redis: Redis client for caching

    Returns:
        StrategyPerformanceResponse with performance metrics
    """
    try:
        logger.info(
            "get_strategy_performance",
            strategy_id=strategy_id,
            period=period
        )

        # Validate period
        valid_periods = ["daily", "weekly", "monthly", "all_time"]
        if period not in valid_periods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}"
            )

        service = StrategyService(db, redis)

        # First check if strategy exists
        strategy = await service.repository.get_strategy_by_id(strategy_id)
        if not strategy:
            logger.warning(
                "strategy_not_found",
                strategy_id=strategy_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with ID {strategy_id} not found"
            )

        performance = await service.get_strategy_performance(strategy_id, period)

        if not performance:
            logger.warning(
                "performance_not_found",
                strategy_id=strategy_id,
                period=period
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No performance data found for strategy {strategy_id} in period {period}"
            )

        return StrategyPerformanceResponse.model_validate(performance)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_strategy_performance_failed",
            strategy_id=strategy_id,
            period=period,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve performance for strategy {strategy_id}: {str(e)}"
        )
