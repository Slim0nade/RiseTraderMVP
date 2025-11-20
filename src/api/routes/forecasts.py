"""
ML Forecasts API Routes
"""
import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Forecast
from ..dependencies import get_db, get_pagination_params, PaginationParams
from ..models import (
    ForecastListResponse,
    ForecastResponse,
    GenerateForecastRequest,
    GenerateForecastResponse,
    LatestForecastsResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/{symbol}", response_model=LatestForecastsResponse)
async def get_latest_forecasts(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> LatestForecastsResponse:
    """Get latest forecasts for a symbol."""
    try:
        query = (
            select(Forecast)
            .where(Forecast.symbol == symbol)
            .order_by(desc(Forecast.prediction_timestamp))
            .limit(10)
        )
        result = await db.execute(query)
        forecasts = result.scalars().all()

        return LatestForecastsResponse(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            forecasts=[ForecastResponse(**f.to_dict()) for f in forecasts],
        )
    except Exception as e:
        logger.error("get_latest_forecasts_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/history", response_model=ForecastListResponse)
async def get_forecast_history(
    symbol: str,
    model_type: str = Query(None, description="Filter by model type"),
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_db),
) -> ForecastListResponse:
    """Get historical forecasts."""
    try:
        query = select(Forecast).where(Forecast.symbol == symbol)
        if model_type:
            query = query.where(Forecast.model_type == model_type)
        query = query.order_by(desc(Forecast.prediction_timestamp))

        count_query = select(func.count()).select_from(Forecast).where(Forecast.symbol == symbol)
        if model_type:
            count_query = count_query.where(Forecast.model_type == model_type)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset(pagination.offset).limit(pagination.limit)
        result = await db.execute(query)
        forecasts = result.scalars().all()

        return ForecastListResponse(
            forecasts=[ForecastResponse(**f.to_dict()) for f in forecasts],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            symbol=symbol,
            model_type=model_type,
        )
    except Exception as e:
        logger.error("get_forecast_history_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=GenerateForecastResponse)
async def generate_forecasts(
    request: GenerateForecastRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateForecastResponse:
    """Trigger forecast generation (placeholder - requires MLPredictionAgent)."""
    logger.warning("generate_forecasts_not_implemented", symbol=request.symbol)
    return GenerateForecastResponse(
        success=False,
        message="Forecast generation not implemented - requires MLPredictionAgent integration",
        symbol=request.symbol,
        forecasts_generated=0,
    )
