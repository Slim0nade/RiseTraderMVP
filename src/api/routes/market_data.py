"""
Market Data API Routes

Enhanced endpoints for accessing market data with Redis caching and keyset pagination.
Implements T049-T051 from 002-fastapi-dashboard-api specification.
"""
import structlog
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models.market_data import MarketData

from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.market_data_service import MarketDataService
from src.services.redis_subscriber_service import RedisSubscriberService
from src.utils.redis_client import MT4RedisClient
from fastapi.responses import StreamingResponse
from ..dependencies import get_db, get_redis_client
from ..models import (
    MarketDataListResponse,
    MarketDataResponse,
    SymbolInfoResponse,
    SymbolListResponse,
    ErrorResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


# ============================================================================
# IMPORTANT: Static routes must be defined BEFORE dynamic routes like /{symbol}
# to avoid FastAPI matching 'symbols' as a symbol name
# ============================================================================


def get_market_data_service(
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[MT4RedisClient] = Depends(get_redis_client),
) -> MarketDataService:
    """
    Dependency to create MarketDataService with repository and Redis client.

    Args:
        db: Database session
        redis_client: Optional Redis client for caching

    Returns:
        MarketDataService instance
    """
    repository = MarketDataRepository(db)
    return MarketDataService(repository, redis_client)


@router.get("/symbols", response_model=SymbolListResponse, responses={
    200: {"description": "List of available symbols with metadata"},
})
async def get_symbols(
    timeframe: Optional[str] = Query(None, description="Optional timeframe filter"),
    service: MarketDataService = Depends(get_market_data_service),
) -> SymbolListResponse:
    """
    Get list of available symbols with metadata (T051).

    Features:
    - Aggregated metadata (data points count, latest price, time range)
    - Optional timeframe filtering
    - Redis caching with 1-hour TTL

    Args:
        timeframe: Optional timeframe filter
        service: MarketDataService dependency

    Returns:
        SymbolListResponse with symbol metadata

    Example:
        GET /api/market-data/symbols
        GET /api/market-data/symbols?timeframe=M5
    """
    try:
        # Validate timeframe if provided
        if timeframe:
            valid_timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
            if timeframe not in valid_timeframes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid timeframe '{timeframe}'. Valid options: {', '.join(valid_timeframes)}",
                )

        # Get symbols with metadata
        symbols_data = await service.get_symbols(timeframe=timeframe)

        # Convert to SymbolInfoResponse objects
        symbol_infos = []
        for symbol_dict in symbols_data:
            symbol_info = SymbolInfoResponse(**symbol_dict)
            symbol_infos.append(symbol_info)

        logger.info(
            "get_symbols_success",
            count=len(symbol_infos),
            timeframe=timeframe,
        )

        return SymbolListResponse(
            symbols=symbol_infos,
            total=len(symbol_infos),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_symbols_failed",
            timeframe=timeframe,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve symbols: {str(e)}",
        )


@router.get("/timeframes/available", responses={
    200: {"description": "Available timeframes per symbol"},
})
async def get_available_timeframes(
    db: AsyncSession = Depends(get_db),
):
    """
    Get available timeframes for each symbol.

    Returns a mapping of symbol names to their available timeframes.
    Useful for UI to disable timeframe buttons when data doesn't exist.

    Example:
        GET /api/market-data/timeframes/available

    Response:
        {
            "CrudeOIL": ["M1", "M5", "H1"],
            "DXY": ["M1"],
            "VIX": ["M1"]
        }
    """
    try:
        # Query distinct symbol/timeframe combinations
        query = select(
            distinct(MarketData.symbol),
            MarketData.timeframe
        ).order_by(MarketData.symbol, MarketData.timeframe)

        result = await db.execute(query)
        rows = result.all()

        # Build dictionary of symbol -> [timeframes]
        timeframes_by_symbol = {}
        for symbol, timeframe in rows:
            if symbol not in timeframes_by_symbol:
                timeframes_by_symbol[symbol] = []
            timeframes_by_symbol[symbol].append(timeframe)

        logger.info(
            "get_available_timeframes_success",
            symbols=list(timeframes_by_symbol.keys()),
        )

        return timeframes_by_symbol

    except Exception as e:
        logger.error(
            "get_available_timeframes_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve available timeframes: {str(e)}",
        )


@router.get("/{symbol}", response_model=MarketDataListResponse, responses={
    404: {"model": ErrorResponse, "description": "Symbol not found"},
    400: {"model": ErrorResponse, "description": "Invalid timeframe"},
})
async def get_market_data(
    symbol: str,
    timeframe: str = Query(..., description="Timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    cursor: Optional[str] = Query(None, description="Cursor for keyset pagination"),
    service: MarketDataService = Depends(get_market_data_service),
) -> MarketDataListResponse:
    """
    Get latest market data for a symbol with caching and keyset pagination (T049).

    Features:
    - Redis caching with 5-second TTL for latest prices
    - Keyset pagination for consistent performance
    - Composite index optimization for sub-2s response time

    Args:
        symbol: Trading symbol (e.g., "CrudeOIL")
        timeframe: Timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)
        limit: Maximum records to return (1-500)
        cursor: Optional cursor for pagination (format: "timestamp_id")
        service: MarketDataService dependency

    Returns:
        MarketDataListResponse with data, pagination info, and next_cursor

    Example:
        GET /api/market-data/CrudeOIL?timeframe=M5&limit=50
        GET /api/market-data/CrudeOIL?timeframe=M5&limit=50&cursor=2024-11-26T10:30:00_123
    """
    try:
        # Validate timeframe
        valid_timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
        if timeframe not in valid_timeframes:
            logger.warning(
                "invalid_timeframe",
                symbol=symbol,
                timeframe=timeframe,
                valid_timeframes=valid_timeframes,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid timeframe '{timeframe}'. Valid options: {', '.join(valid_timeframes)}",
            )

        # Get market data with caching
        data, next_cursor, total = await service.get_market_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            cursor=cursor,
        )

        # Check if symbol has data
        if total == 0:
            logger.info("symbol_not_found", symbol=symbol, timeframe=timeframe)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data available for symbol '{symbol}' with timeframe '{timeframe}'",
            )

        logger.info(
            "get_market_data_success",
            symbol=symbol,
            timeframe=timeframe,
            returned_count=len(data),
            total=total,
            has_next_page=next_cursor is not None,
        )

        return MarketDataListResponse(
            data=[MarketDataResponse.model_validate(tick) for tick in data],
            total=total,
            page=1,  # Keyset pagination doesn't use page numbers
            page_size=limit,
            symbol=symbol,
            next_cursor=next_cursor,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "get_market_data_failed",
            symbol=symbol,
            timeframe=timeframe,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve market data: {str(e)}",
        )


@router.get("/{symbol}/range", response_model=MarketDataListResponse, responses={
    404: {"model": ErrorResponse, "description": "No data in range"},
    400: {"model": ErrorResponse, "description": "Invalid parameters"},
})
async def get_market_data_range(
    symbol: str,
    start_time: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end_time: datetime = Query(..., description="End timestamp (ISO 8601)"),
    timeframe: str = Query(..., description="Timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)"),
    limit: int = Query(500, ge=1, le=500, description="Maximum records per page"),
    cursor: Optional[str] = Query(None, description="Cursor for keyset pagination"),
    service: MarketDataService = Depends(get_market_data_service),
) -> MarketDataListResponse:
    """
    Get market data for a specific time range with caching (T050).

    Features:
    - Redis caching with 1-hour TTL for historical data
    - Keyset pagination for large time ranges
    - Efficient composite index usage

    Args:
        symbol: Trading symbol
        start_time: Start timestamp (ISO 8601 format)
        end_time: End timestamp (ISO 8601 format)
        timeframe: Timeframe
        limit: Maximum records per page (1-500)
        cursor: Optional cursor for pagination
        service: MarketDataService dependency

    Returns:
        MarketDataListResponse with data in time range

    Example:
        GET /api/market-data/CrudeOIL/range?start_time=2024-11-01T00:00:00&end_time=2024-11-26T23:59:59&timeframe=M5
    """
    try:
        # Validate timeframe
        valid_timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
        if timeframe not in valid_timeframes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid timeframe '{timeframe}'. Valid options: {', '.join(valid_timeframes)}",
            )

        # Validate time range
        if start_time >= end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_time must be before end_time",
            )

        # Get market data range with caching
        data, next_cursor, total = await service.get_market_data_range(
            symbol=symbol,
            timeframe=timeframe,
            start=start_time,
            end=end_time,
            cursor=cursor,
            limit=limit,
        )

        # Check if any data in range
        if total == 0:
            logger.info(
                "no_data_in_range",
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data available for '{symbol}' in specified time range",
            )

        logger.info(
            "get_market_data_range_success",
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            returned_count=len(data),
            total=total,
            has_next_page=next_cursor is not None,
        )

        return MarketDataListResponse(
            data=[MarketDataResponse.model_validate(tick) for tick in data],
            total=total,
            page=1,
            page_size=limit,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            next_cursor=next_cursor,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_market_data_range_failed",
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve market data range: {str(e)}",
        )


@router.get("/stream/{symbol}", responses={
    200: {"description": "Server-Sent Events stream of market data updates"},
    400: {"model": ErrorResponse, "description": "Invalid parameters"},
})
async def stream_market_data(
    symbol: str,
    timeframe: Optional[str] = Query(None, description="Optional timeframe filter"),
    redis_client: Optional[MT4RedisClient] = Depends(get_redis_client),
):
    """
    Stream real-time market data updates via Server-Sent Events (T054).

    Features:
    - Real-time market data updates via Redis pub/sub
    - Server-Sent Events (SSE) for browser compatibility
    - Automatic heartbeat every 30 seconds
    - Graceful error handling and connection management

    Args:
        symbol: Trading symbol to stream
        timeframe: Optional timeframe filter (if None, streams all timeframes)
        redis_client: Redis client for pub/sub

    Returns:
        StreamingResponse with text/event-stream content type

    Example:
        GET /api/market-data/stream/CrudeOIL
        GET /api/market-data/stream/CrudeOIL?timeframe=M5

    SSE Event Types:
        - market_data: New market data tick
        - heartbeat: Keep-alive ping
        - error: Error notification
    """
    try:
        # Validate timeframe if provided
        if timeframe:
            valid_timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
            if timeframe not in valid_timeframes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid timeframe '{timeframe}'. Valid options: {', '.join(valid_timeframes)}",
                )

        # Check Redis client available
        if not redis_client:
            logger.error("sse_stream_no_redis", symbol=symbol)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis pub/sub not available for streaming",
            )

        logger.info(
            "sse_stream_started",
            symbol=symbol,
            timeframe=timeframe,
        )

        async def event_generator():
            """Generate SSE events from Redis pub/sub."""
            subscriber = RedisSubscriberService(redis_client)

            try:
                # Build channel name
                channel = RedisSubscriberService.get_market_data_channel(
                    symbol, timeframe
                )

                # Subscribe to channel
                await subscriber.subscribe([channel])

                logger.info("subscribed_to_redis_channel", channel=channel)

                # Stream events
                async for event in subscriber.listen(heartbeat_interval=30):
                    event_type = event.get("type", "unknown")

                    if event_type == "data":
                        # Market data update
                        yield RedisSubscriberService.format_sse_event(
                            "market_data", event["data"]
                        )

                    elif event_type == "heartbeat":
                        # Heartbeat ping
                        yield RedisSubscriberService.format_sse_event(
                            "heartbeat",
                            {"timestamp": event["timestamp"]},
                        )

                    elif event_type == "error":
                        # Error event
                        yield RedisSubscriberService.format_sse_event(
                            "error",
                            {
                                "error": event.get("error", "Unknown"),
                                "detail": event.get("detail", "An error occurred"),
                                "timestamp": event["timestamp"],
                            },
                        )
                        break  # Stop streaming on error

            except Exception as e:
                logger.error(
                    "sse_stream_error",
                    symbol=symbol,
                    timeframe=timeframe,
                    error=str(e),
                    exc_info=True,
                )
                # Send error event before closing
                yield RedisSubscriberService.format_sse_event(
                    "error",
                    {
                        "error": "StreamError",
                        "detail": str(e),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            finally:
                logger.info(
                    "sse_stream_closed",
                    symbol=symbol,
                    timeframe=timeframe,
                )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "stream_setup_failed",
            symbol=symbol,
            timeframe=timeframe,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup stream: {str(e)}",
        )


@router.get("/availability/{symbol}")
async def get_data_availability(
    symbol: str,
    timeframe: str = Query("M5", description="Timeframe (M1, M5, M15, H1, H4, D1)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get data availability information for intelligent date picker.

    Returns date range, trading days, and gaps for a symbol/timeframe.
    Used by frontend to validate backtest date selection.
    """
    try:
        # Get date range and total candles
        range_query = select(
            func.min(MarketData.time).label('first_date'),
            func.max(MarketData.time).label('last_date'),
            func.count(MarketData.id).label('total_candles')
        ).where(
            and_(
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe
            )
        )

        result = await db.execute(range_query)
        row = result.first()

        if not row or not row.first_date:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {symbol} {timeframe}"
            )

        first_date = row.first_date
        last_date = row.last_date
        total_candles = row.total_candles

        # Get dates with data (grouped by day) - last 180 days for performance
        recent_cutoff = last_date - timedelta(days=180)

        date_trunc_expr = func.date_trunc('day', MarketData.time)
        dates_query = select(
            date_trunc_expr.label('date'),
            func.count(MarketData.id).label('candle_count')
        ).where(
            and_(
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
                MarketData.time >= recent_cutoff
            )
        ).group_by(
            date_trunc_expr
        ).order_by(
            date_trunc_expr.desc()
        )

        dates_result = await db.execute(dates_query)
        trading_days = [
            row.date.date().isoformat()
            for row in dates_result.all()
        ]

        # Recommended backtest period (last 6 months, ending 1 month ago)
        recommended_end = last_date - timedelta(days=30)
        recommended_start = recommended_end - timedelta(days=180)
        if recommended_start < first_date:
            recommended_start = first_date

        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'first_date': first_date.isoformat(),
            'last_date': last_date.isoformat(),
            'recommended_start': recommended_start.isoformat(),
            'recommended_end': recommended_end.isoformat(),
            'total_candles': total_candles,
            'trading_days': trading_days,  # Last 180 days with data
            'has_data': True,
            'summary': {
                'total_days_with_data': len(trading_days),
                'avg_candles_per_day': total_candles / max(len(trading_days), 1),
                'data_quality': 'good' if total_candles > 10000 else 'limited'
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("data_availability_error", error=str(e), symbol=symbol, timeframe=timeframe)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get data availability: {str(e)}"
        )


@router.get("/preview/{symbol}")
async def get_candle_preview(
    symbol: str,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    timeframe: str = Query("M5", description="Timeframe (M1, M5, M15, H1, H4, D1)"),
    max_candles: int = Query(200, description="Maximum candles to return (default 200)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get sample candle data for chart preview.
    Returns evenly-spaced candles from the selected period for visualization.
    """
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)

        # Get total candles in range
        count_query = select(func.count(MarketData.id)).where(
            and_(
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
                MarketData.time >= start_dt,
                MarketData.time <= end_dt
            )
        )
        count_result = await db.execute(count_query)
        total_candles = count_result.scalar()

        if not total_candles:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol} {timeframe} in date range")

        # Calculate sampling interval
        sample_interval = max(1, total_candles // max_candles)

        # Fetch sampled candles using PostgreSQL row_number for efficient sampling
        # This uses a subquery with row_number() to select every Nth row
        from sqlalchemy import literal_column

        # Use PostgreSQL's efficient OFFSET/LIMIT sampling
        # If we need every 300th candle, fetch every sample_interval-th row
        if sample_interval > 1:
            # Use modulo-based sampling in database for large datasets
            sampled_query = select(MarketData).where(
                and_(
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                    MarketData.time >= start_dt,
                    MarketData.time <= end_dt,
                    # Use id modulo for pseudo-random but consistent sampling
                    literal_column(f"(id::bigint % {sample_interval}) = 0")
                )
            ).order_by(MarketData.time).limit(max_candles)
        else:
            # If sample_interval is 1, just limit the results
            sampled_query = select(MarketData).where(
                and_(
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                    MarketData.time >= start_dt,
                    MarketData.time <= end_dt
                )
            ).order_by(MarketData.time).limit(max_candles)

        result = await db.execute(sampled_query)
        sampled_candles = result.scalars().all()

        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'start_date': start_date,
            'end_date': end_date,
            'total_candles': total_candles,
            'sampled_candles': len(sampled_candles),
            'candles': [
                {
                    'time': candle.time.isoformat(),
                    'open': float(candle.open),
                    'high': float(candle.high),
                    'low': float(candle.low),
                    'close': float(candle.close),
                    'volume': int(candle.volume) if candle.volume else 0,
                }
                for candle in sampled_candles
            ]
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.error("candle_preview_error", error=str(e), symbol=symbol, timeframe=timeframe)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get candle preview: {str(e)}"
        )
