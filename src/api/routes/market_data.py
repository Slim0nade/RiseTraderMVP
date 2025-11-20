"""
Market Data API Routes

Endpoints for accessing market data and controlling data streams.
"""
import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import MarketData
from ..dependencies import get_db, get_pagination_params, PaginationParams
from ..models import (
    MarketDataListResponse,
    MarketDataResponse,
    StreamControlRequest,
    StreamControlResponse,
    SymbolInfoResponse,
    SymbolListResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/{symbol}", response_model=MarketDataListResponse)
async def get_market_data(
    symbol: str,
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_db),
) -> MarketDataListResponse:
    """
    Get latest market data ticks for a symbol.

    Args:
        symbol: Trading symbol
        pagination: Pagination parameters
        db: Database session

    Returns:
        List of market data ticks
    """
    try:
        # Build query
        query = (
            select(MarketData)
            .where(MarketData.symbol == symbol)
            .order_by(desc(MarketData.time))
        )

        # Count total
        count_query = select(func.count()).select_from(MarketData).where(MarketData.symbol == symbol)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = query.offset(pagination.offset).limit(pagination.limit)
        result = await db.execute(query)
        data = result.scalars().all()

        return MarketDataListResponse(
            data=[MarketDataResponse(**tick.to_dict()) for tick in data],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            symbol=symbol,
        )

    except Exception as e:
        logger.error("get_market_data_failed", symbol=symbol, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve market data: {str(e)}",
        )


@router.get("/{symbol}/range", response_model=MarketDataListResponse)
async def get_market_data_range(
    symbol: str,
    start_time: datetime = Query(..., description="Start timestamp"),
    end_time: datetime = Query(..., description="End timestamp"),
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_db),
) -> MarketDataListResponse:
    """
    Get market data for a specific time range.

    Args:
        symbol: Trading symbol
        start_time: Start timestamp
        end_time: End timestamp
        pagination: Pagination parameters
        db: Database session

    Returns:
        List of market data ticks
    """
    try:
        # Build query
        query = (
            select(MarketData)
            .where(MarketData.symbol == symbol)
            .where(MarketData.time >= start_time)
            .where(MarketData.time <= end_time)
            .order_by(desc(MarketData.time))
        )

        # Count total
        count_query = (
            select(func.count())
            .select_from(MarketData)
            .where(MarketData.symbol == symbol)
            .where(MarketData.time >= start_time)
            .where(MarketData.time <= end_time)
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = query.offset(pagination.offset).limit(pagination.limit)
        result = await db.execute(query)
        data = result.scalars().all()

        return MarketDataListResponse(
            data=[MarketDataResponse(**tick.to_dict()) for tick in data],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )

    except Exception as e:
        logger.error("get_market_data_range_failed", symbol=symbol, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve market data range: {str(e)}",
        )


@router.get("/symbols", response_model=SymbolListResponse)
async def get_symbols(
    db: AsyncSession = Depends(get_db),
) -> SymbolListResponse:
    """
    Get list of available trading symbols.

    Args:
        db: Database session

    Returns:
        List of symbols with metadata
    """
    try:
        # Get distinct symbols
        query = select(MarketData.symbol).distinct()
        result = await db.execute(query)
        symbols = result.scalars().all()

        symbol_infos = []
        for symbol in symbols:
            # Get latest data point
            latest_query = (
                select(MarketData)
                .where(MarketData.symbol == symbol)
                .order_by(desc(MarketData.time))
                .limit(1)
            )
            latest_result = await db.execute(latest_query)
            latest = latest_result.scalar_one_or_none()

            # Count data points
            count_query = select(func.count()).select_from(MarketData).where(MarketData.symbol == symbol)
            count_result = await db.execute(count_query)
            count = count_result.scalar() or 0

            symbol_infos.append(
                SymbolInfoResponse(
                    symbol=symbol,
                    latest_price=latest.close if latest else None,
                    latest_timestamp=latest.timestamp if latest else None,
                    data_points_count=count,
                    last_timestamp=latest.timestamp if latest else None,
                )
            )

        return SymbolListResponse(
            symbols=symbol_infos,
            total=len(symbol_infos),
        )

    except Exception as e:
        logger.error("get_symbols_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve symbols: {str(e)}",
        )


@router.post("/stream/start", response_model=StreamControlResponse)
async def start_stream(
    request: StreamControlRequest,
) -> StreamControlResponse:
    """
    Start market data streaming for a symbol.

    Args:
        request: Stream control request

    Returns:
        Stream control result
    """
    try:
        # TODO: Implement streaming via MarketDataAgent
        logger.warning(
            "start_stream_not_implemented",
            symbol=request.symbol,
            message="Data streaming not yet implemented - requires MarketDataAgent integration",
        )

        return StreamControlResponse(
            success=False,
            message="Data streaming not yet implemented - requires MarketDataAgent integration",
            symbol=request.symbol,
        )

    except Exception as e:
        logger.error("start_stream_failed", symbol=request.symbol, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start stream: {str(e)}",
        )


@router.post("/stream/stop", response_model=StreamControlResponse)
async def stop_stream(
    request: StreamControlRequest,
) -> StreamControlResponse:
    """
    Stop market data streaming for a symbol.

    Args:
        request: Stream control request

    Returns:
        Stream control result
    """
    try:
        # TODO: Implement streaming control via MarketDataAgent
        logger.warning(
            "stop_stream_not_implemented",
            symbol=request.symbol,
            message="Data streaming control not yet implemented - requires MarketDataAgent integration",
        )

        return StreamControlResponse(
            success=False,
            message="Data streaming control not yet implemented - requires MarketDataAgent integration",
            symbol=request.symbol,
        )

    except Exception as e:
        logger.error("stop_stream_failed", symbol=request.symbol, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop stream: {str(e)}",
        )
