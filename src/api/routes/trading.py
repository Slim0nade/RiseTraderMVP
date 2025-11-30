"""
Trading Operations API Routes

Enhanced endpoints for account info, positions, and trading history with caching.
Implements Phase 4 (T059-T080) from 002-fastapi-dashboard-api specification.
"""
import structlog
from datetime import datetime
from typing import Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.trading_repository import TradingRepository
from src.services.trading_service import TradingService
from src.utils.redis_client import MT4RedisClient
from ..dependencies import get_db, get_redis_client
from ..models import (
    AccountResponse,
    ClosePositionRequest,
    ClosePositionResponse,
    OrderResponse,
    PlaceOrderRequest,
    PositionListResponse,
    PositionResponse,
    TradingHistoryListResponse,
    TradingHistoryResponse,
    ErrorResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/trading", tags=["trading"])


def get_trading_service(
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[MT4RedisClient] = Depends(get_redis_client),
) -> TradingService:
    """
    Dependency to create TradingService.

    Args:
        db: Database session
        redis_client: Optional Redis client for caching

    Returns:
        TradingService instance
    """
    repository = TradingRepository(db)
    return TradingService(repository, redis_client, redis_client)


@router.get("/account", response_model=AccountResponse, responses={
    200: {"description": "Account information retrieved"},
})
async def get_account(
    service: TradingService = Depends(get_trading_service),
) -> AccountResponse:
    """
    Get trading account information with caching (T059).

    Features:
    - Redis caching with 10-second TTL
    - Real-time balance, equity, margin information
    - Cached to reduce database load

    Returns:
        AccountResponse with account details

    Example:
        GET /api/trading/account
    """
    try:
        account_info = await service.get_account_info()

        logger.info(
            "get_account_success",
            account_number=account_info.get("account_number"),
            balance=account_info.get("balance"),
        )

        return AccountResponse(**account_info)

    except Exception as e:
        logger.error(
            "get_account_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve account information: {str(e)}",
        )


@router.get("/positions", response_model=PositionListResponse, responses={
    200: {"description": "List of open positions"},
})
async def get_positions(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    service: TradingService = Depends(get_trading_service),
) -> PositionListResponse:
    """
    Get all open positions with optional symbol filter (T060).

    Features:
    - Redis caching with 5-second TTL
    - Optional symbol filtering
    - Real-time position updates

    Args:
        symbol: Optional symbol filter
        service: TradingService dependency

    Returns:
        PositionListResponse with list of positions

    Example:
        GET /api/trading/positions
        GET /api/trading/positions?symbol=CrudeOIL
    """
    try:
        positions = await service.get_open_positions(symbol=symbol)

        logger.info(
            "get_positions_success",
            symbol=symbol,
            count=len(positions),
        )

        return PositionListResponse(
            positions=[PositionResponse.from_orm(pos) for pos in positions],
            total=len(positions),
            page=1,
            page_size=len(positions),
        )

    except Exception as e:
        logger.error(
            "get_positions_failed",
            symbol=symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve positions: {str(e)}",
        )


@router.get("/positions/summary", responses={
    200: {"description": "Position summary statistics"},
})
async def get_position_summary(
    service: TradingService = Depends(get_trading_service),
):
    """
    Get summary statistics for open positions (T061).

    Returns aggregate statistics:
    - Total positions count
    - Total volume
    - Total profit/loss
    - Breakdown by symbol
    - Breakdown by trade type (BUY/SELL)

    Returns:
        Dictionary with summary statistics

    Example:
        GET /api/trading/positions/summary
    """
    try:
        summary = await service.get_position_summary()

        logger.info(
            "get_position_summary_success",
            total_positions=summary["total_positions"],
            total_profit=summary["total_profit"],
        )

        return summary

    except Exception as e:
        logger.error(
            "get_position_summary_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve position summary: {str(e)}",
        )


@router.get("/positions/{position_id}", response_model=PositionResponse, responses={
    404: {"model": ErrorResponse, "description": "Position not found"},
})
async def get_position(
    position_id: int,
    service: TradingService = Depends(get_trading_service),
) -> PositionResponse:
    """
    Get details of a specific position (T062).

    Args:
        position_id: Position ID
        service: TradingService dependency

    Returns:
        PositionResponse with position details

    Raises:
        404: Position not found

    Example:
        GET /api/trading/positions/123
    """
    try:
        position = await service.get_position_by_id(position_id)

        if not position:
            logger.info("position_not_found", position_id=position_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position not found: {position_id}",
            )

        logger.info(
            "get_position_success",
            position_id=position_id,
            symbol=position.symbol,
        )

        return PositionResponse.from_orm(position)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_position_failed",
            position_id=position_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve position: {str(e)}",
        )


@router.post("/positions/{position_id}/close", response_model=ClosePositionResponse, responses={
    404: {"model": ErrorResponse, "description": "Position not found"},
    400: {"model": ErrorResponse, "description": "Invalid close parameters"},
})
async def close_position(
    position_id: int,
    request: ClosePositionRequest,
    service: TradingService = Depends(get_trading_service),
) -> ClosePositionResponse:
    """
    Close a position (fully or partially) (T063).

    Features:
    - Full or partial position closing
    - MT4 integration for order execution
    - Cache invalidation on success

    Args:
        position_id: Position ID to close
        request: Close request with optional volume
        service: TradingService dependency

    Returns:
        ClosePositionResponse with close operation result

    Raises:
        404: Position not found
        400: Invalid close parameters

    Example:
        POST /api/trading/positions/123/close
        Body: {"volume": null}  # Close full position

        POST /api/trading/positions/123/close
        Body: {"volume": 0.5}  # Close half position
    """
    try:
        result = await service.close_position(
            position_id=position_id,
            volume=Decimal(str(request.volume)) if request.volume else None,
        )

        # Invalidate positions cache on successful close
        if result.get("success"):
            await service.invalidate_positions_cache()

        logger.info(
            "close_position_result",
            position_id=position_id,
            success=result.get("success"),
            message=result.get("message"),
        )

        return ClosePositionResponse(
            success=result["success"],
            message=result["message"],
            position_id=result.get("position_id"),
            ticket=result.get("ticket"),
        )

    except ValueError as e:
        # Invalid parameters
        logger.warning(
            "close_position_invalid",
            position_id=position_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "close_position_failed",
            position_id=position_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}",
        )


@router.get("/history", response_model=TradingHistoryListResponse, responses={
    200: {"description": "Trading history with pagination"},
})
async def get_trading_history(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    trade_type: Optional[str] = Query(None, description="Trade type (BUY/SELL)"),
    limit: int = Query(50, ge=1, le=200, description="Records per page"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    service: TradingService = Depends(get_trading_service),
) -> TradingHistoryListResponse:
    """
    Get trading history with keyset pagination (T064-T065).

    Features:
    - Keyset pagination for consistent performance
    - Multiple filter options (symbol, date range, trade type)
    - Cursor-based pagination

    Args:
        symbol: Optional symbol filter
        start_date: Optional start date (ISO 8601)
        end_date: Optional end date (ISO 8601)
        trade_type: Optional trade type filter (BUY or SELL)
        limit: Records per page (1-200)
        cursor: Pagination cursor
        service: TradingService dependency

    Returns:
        TradingHistoryListResponse with paginated trade history

    Example:
        GET /api/trading/history?limit=50
        GET /api/trading/history?symbol=CrudeOIL&limit=50
        GET /api/trading/history?start_date=2024-11-01T00:00:00&limit=50
        GET /api/trading/history?cursor=2024-11-26T10:30:00_123&limit=50
    """
    try:
        # Validate trade_type if provided
        if trade_type and trade_type not in ["BUY", "SELL"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="trade_type must be 'BUY' or 'SELL'",
            )

        # Validate date range
        if start_date and end_date and start_date >= end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before end_date",
            )

        trades, next_cursor, total = await service.get_trading_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            trade_type=trade_type,
            cursor=cursor,
            limit=limit,
        )

        logger.info(
            "get_trading_history_success",
            symbol=symbol,
            count=len(trades),
            total=total,
            has_next_page=next_cursor is not None,
        )

        return TradingHistoryListResponse(
            trades=[TradingHistoryResponse.from_orm(trade) for trade in trades],
            total=total,
            page=1,
            page_size=limit,
            next_cursor=next_cursor,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_trading_history_failed",
            symbol=symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve trading history: {str(e)}",
        )


@router.get("/history/{trade_id}", response_model=TradingHistoryResponse, responses={
    404: {"model": ErrorResponse, "description": "Trade not found"},
})
async def get_trade(
    trade_id: int,
    service: TradingService = Depends(get_trading_service),
) -> TradingHistoryResponse:
    """
    Get details of a specific trade (T066).

    Args:
        trade_id: Trade ID
        service: TradingService dependency

    Returns:
        TradingHistoryResponse with trade details

    Raises:
        404: Trade not found

    Example:
        GET /api/trading/history/456
    """
    try:
        # Get from repository directly
        trade = await service.repository.get_trade_by_id(trade_id)

        if not trade:
            logger.info("trade_not_found", trade_id=trade_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trade not found: {trade_id}",
            )

        logger.info(
            "get_trade_success",
            trade_id=trade_id,
            symbol=trade.symbol,
        )

        return TradingHistoryResponse.from_orm(trade)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_trade_failed",
            trade_id=trade_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve trade: {str(e)}",
        )


@router.post("/orders", response_model=OrderResponse, responses={
    400: {"model": ErrorResponse, "description": "Invalid order parameters"},
})
async def place_order(
    request: PlaceOrderRequest,
    service: TradingService = Depends(get_trading_service),
) -> OrderResponse:
    """
    Place a new trading order (T067).

    Note: This endpoint is currently a placeholder.
    Full implementation requires ExecutionAgent integration.

    Args:
        request: Order placement request
        service: TradingService dependency

    Returns:
        OrderResponse with order placement result

    Example:
        POST /api/trading/orders
        Body: {
          "symbol": "CrudeOIL",
          "order_type": "BUY",
          "volume": 0.1,
          "stop_loss": 71.50,
          "take_profit": 73.00
        }
    """
    try:
        logger.warning(
            "place_order_not_implemented",
            symbol=request.symbol,
            order_type=request.order_type,
            message="Order placement requires ExecutionAgent integration",
        )

        return OrderResponse(
            success=False,
            message="Order placement not yet implemented - requires ExecutionAgent integration",
            order_id=None,
            ticket=None,
        )

    except Exception as e:
        logger.error(
            "place_order_failed",
            symbol=request.symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place order: {str(e)}",
        )
