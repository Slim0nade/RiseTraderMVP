"""
Market Data API Routes

Enhanced endpoints for accessing market data with Redis caching and keyset pagination.
Implements T049-T051 from 002-fastapi-dashboard-api specification.
"""
import structlog
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.market_data_service import MarketDataService
from src.services.redis_subscriber_service import RedisSubscriberService
from src.trading.execution.mt4_client import MT4RedisClient, get_redis_client
from fastapi.responses import StreamingResponse
from ..dependencies import get_db
from ..models import (
    MarketDataListResponse,
    MarketDataResponse,
    SymbolInfoResponse,
    SymbolListResponse,
    ErrorResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


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
            data=[MarketDataResponse.from_orm(tick) for tick in data],
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
            data=[MarketDataResponse.from_orm(tick) for tick in data],
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
