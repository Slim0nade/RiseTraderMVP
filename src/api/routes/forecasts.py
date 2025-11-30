"""
ML Forecasts API Routes

Endpoints for retrieving ML price forecasts with caching and pagination.
"""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.api.models.forecasts import ForecastResponse, ForecastListResponse
from src.api.models.common import ErrorResponse
from src.api.dependencies import get_db, get_redis
from src.services.forecast_service import ForecastService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get(
    "/latest",
    response_model=ForecastListResponse,
    responses={
        200: {"description": "Latest forecasts retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_latest_forecasts(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    horizon: Optional[str] = Query(None, description="Filter by forecast horizon (e.g., 1h, 4h, 24h)"),
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
) -> ForecastListResponse:
    """
    Get latest forecasts across all symbols or filtered by symbol/horizon.

    This endpoint returns the most recent forecasts, optionally filtered by
    trading symbol and/or forecast horizon. Results are cached for 1 hour.

    Args:
        symbol: Optional symbol filter (e.g., 'CrudeOIL', 'GOLD')
        horizon: Optional horizon filter (e.g., '1h', '4h', '24h')
        db: Database session
        redis: Redis client for caching

    Returns:
        ForecastListResponse with list of forecasts and metadata
    """
    try:
        logger.info(
            "get_latest_forecasts",
            symbol=symbol,
            horizon=horizon
        )

        service = ForecastService(db, redis)
        forecasts = await service.get_latest_forecasts(symbol=symbol, horizon=horizon)

        return ForecastListResponse(
            data=[ForecastResponse.model_validate(f) for f in forecasts],
            total=len(forecasts),
            page=1,
            page_size=max(len(forecasts), 1),  # Ensure page_size is at least 1
            next_cursor=None
        )

    except Exception as e:
        logger.error(
            "get_latest_forecasts_failed",
            symbol=symbol,
            horizon=horizon,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve latest forecasts: {str(e)}"
        )


@router.get(
    "/{symbol}",
    response_model=ForecastListResponse,
    responses={
        200: {"description": "Symbol forecasts retrieved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid cursor format"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_forecasts_by_symbol(
    symbol: str,
    cursor: Optional[str] = Query(None, description="Pagination cursor (ISO timestamp)"),
    page_size: int = Query(50, ge=1, le=1000, description="Number of forecasts per page"),
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
) -> ForecastListResponse:
    """
    Get forecasts for a specific symbol with keyset pagination.

    Returns forecasts for the specified symbol, ordered by creation time (most recent first).
    Supports keyset pagination using cursor-based pagination for efficient large dataset traversal.

    Args:
        symbol: Trading symbol (e.g., 'CrudeOIL', 'GOLD', 'EUR_USD')
        cursor: Optional pagination cursor (ISO timestamp from previous response)
        page_size: Number of items per page (1-1000, default 50)
        db: Database session
        redis: Redis client for caching

    Returns:
        ForecastListResponse with paginated forecasts and next_cursor
    """
    try:
        logger.info(
            "get_forecasts_by_symbol",
            symbol=symbol,
            cursor=cursor,
            page_size=page_size
        )

        service = ForecastService(db, redis)
        forecasts, next_cursor = await service.get_forecasts_by_symbol(
            symbol=symbol,
            cursor=cursor,
            limit=page_size
        )

        return ForecastListResponse(
            data=[ForecastResponse.model_validate(f) for f in forecasts],
            total=len(forecasts),  # Note: Total across all pages not available with keyset pagination
            page=1,
            page_size=page_size,
            next_cursor=next_cursor
        )

    except ValueError as e:
        logger.warning(
            "invalid_cursor_format",
            symbol=symbol,
            cursor=cursor,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cursor format: {str(e)}"
        )
    except Exception as e:
        logger.error(
            "get_forecasts_by_symbol_failed",
            symbol=symbol,
            cursor=cursor,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve forecasts for symbol {symbol}: {str(e)}"
        )
