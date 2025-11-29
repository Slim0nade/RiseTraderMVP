"""
FastAPI routes for MT4 integration management.

Provides REST API endpoints for EA management, account queries, order tracking,
and portfolio monitoring.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from src.api.models.mt4_models import (
    # Account queries (T086)
    AccountInfoResponse,
    OpenPositionsResponse,
    # EA management (T098-T102)
    RegisterEARequest,
    EAConnectionResponse,
    EAConnectionListResponse,
    ReconnectEAResponse,
    # Orders (T103)
    OrderListResponse,
    OrderResponse,
    # Portfolio (T105)
    PortfolioRiskResponse,
    # Health (T106)
    ServiceHealthResponse,
    # Common
    ErrorResponse,
    SuccessResponse,
)
from src.services.mt4_integration_service import MT4IntegrationService
from src.database.repositories.mt4_order_repository import MT4OrderRepository
from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
from src.utils.redis_client import MT4RedisClient
from src.trading.execution.symbol_loader import SymbolLoader
from src.trading.execution.mt4_connection_pool import MT4ConnectionPool
from src.utils.mt4_helpers import get_mt4_logger


logger = get_mt4_logger("mt4_api")
router = APIRouter(prefix="/mt4", tags=["MT4 Integration"])


# =============================================================================
# Dependency Injection
# =============================================================================

# TODO: Replace these with proper dependency injection from your FastAPI app
# This is a placeholder - in production, you'd inject these via Depends()
_service_instance: Optional[MT4IntegrationService] = None


def get_mt4_service() -> MT4IntegrationService:
    """
    Get MT4 integration service instance.
    
    This should be replaced with proper FastAPI dependency injection.
    """
    global _service_instance
    if _service_instance is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MT4 integration service not initialized"
        )
    return _service_instance


def init_mt4_service(
    order_repository: MT4OrderRepository,
    connection_repository: MT4ConnectionRepository,
    redis_client: MT4RedisClient,
    symbol_loader: SymbolLoader,
    connection_pool: Optional[MT4ConnectionPool] = None
):
    """Initialize the MT4 service for API routes."""
    global _service_instance
    _service_instance = MT4IntegrationService(
        order_repository=order_repository,
        redis_client=redis_client,
        connection_repository=connection_repository,
        symbol_loader=symbol_loader,
        connection_pool=connection_pool
    )


# =============================================================================
# Account Query Endpoints (T086 - User Story 4)
# =============================================================================

@router.get(
    "/account/{magic_number}",
    response_model=AccountInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get account information",
    description="Query MT4 account information for a specific EA by magic number",
    responses={
        200: {"description": "Account information retrieved successfully"},
        404: {"model": ErrorResponse, "description": "EA not found"},
        503: {"model": ErrorResponse, "description": "MT4 connection unavailable"},
    }
)
async def get_account_info(
    magic_number: int,
    use_cache: bool = Query(True, description="Whether to use cached data"),
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Get account information from MT4 (T086).
    
    Returns balance, equity, margin, and other account metrics for the EA
    identified by the magic number.
    """
    try:
        logger.info("api_account_info_request", magic_number=magic_number)
        
        account_info = await service.query_account_info(
            magic_number=magic_number,
            use_cache=use_cache
        )
        
        return AccountInfoResponse(**account_info.dict())
    
    except ValueError as e:
        logger.warning("account_info_not_found", magic_number=magic_number, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EA with magic number {magic_number} not found"
        )
    except ConnectionError as e:
        logger.error("account_info_connection_error", magic_number=magic_number, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MT4 connection unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error("account_info_error", magic_number=magic_number, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query account information: {str(e)}"
        )


@router.get(
    "/positions",
    response_model=OpenPositionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get open positions",
    description="Query open positions, optionally filtered by EA magic number",
    responses={
        200: {"description": "Positions retrieved successfully"},
        503: {"model": ErrorResponse, "description": "MT4 connection unavailable"},
    }
)
async def get_open_positions(
    magic_number: Optional[int] = Query(None, description="Filter by EA magic number"),
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Get open positions from MT4 (T086).
    
    Returns all open positions, optionally filtered by EA magic number.
    """
    try:
        logger.info("api_positions_request", magic_number=magic_number)
        
        positions = await service.query_open_positions(magic_number=magic_number)
        
        position_responses = [
            PositionInfoResponse(**pos.dict()) for pos in positions
        ]
        
        return OpenPositionsResponse(
            positions=position_responses,
            count=len(position_responses)
        )
    
    except ConnectionError as e:
        logger.error("positions_connection_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MT4 connection unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error("positions_query_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query positions: {str(e)}"
        )


# =============================================================================
# EA Connection Management Endpoints (T098-T102)
# =============================================================================

@router.post(
    "/connections",
    response_model=EAConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new EA",
    description="Register a new Expert Advisor and allocate resources",
    responses={
        201: {"description": "EA registered successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        409: {"model": ErrorResponse, "description": "EA already exists"},
    }
)
async def register_ea(
    request: RegisterEARequest,
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Register a new Expert Advisor (T098).
    
    Allocates magic number and port pair for the EA.
    """
    try:
        logger.info("api_register_ea_request", ea_id=request.ea_id)
        
        registration = await service.register_ea(
            ea_id=request.ea_id,
            symbol=request.symbol,
            host=request.host,
            strategy_name=request.strategy_name,
            max_positions=request.max_positions
        )
        
        # Get connection details
        connection = await service.connection_repository.get_by_ea_id(request.ea_id)
        
        return EAConnectionResponse(
            ea_id=registration["ea_id"],
            magic_number=registration["magic_number"],
            rep_port=registration["rep_port"],
            pub_port=registration["pub_port"],
            host=registration["host"],
            symbol=registration["symbol"],
            status=connection.status if connection else "ACTIVE",
            last_heartbeat=connection.last_heartbeat if connection else None,
            encryption_enabled=connection.encryption_enabled if connection else True
        )
    
    except ValueError as e:
        logger.warning("ea_registration_failed", ea_id=request.ea_id, error=str(e))
        if "already registered" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"EA {request.ea_id} is already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("ea_registration_error", ea_id=request.ea_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register EA: {str(e)}"
        )


@router.get(
    "/connections",
    response_model=EAConnectionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all EA connections",
    description="Get list of all registered EA connections with their status",
)
async def list_ea_connections(
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    List all EA connections (T099).
    """
    try:
        logger.info("api_list_connections_request")
        
        connections = await service.connection_repository.get_all()
        
        connection_responses = [
            EAConnectionResponse(
                ea_id=conn.ea_id,
                magic_number=conn.magic_number,
                rep_port=conn.rep_port,
                pub_port=conn.pub_port,
                host=conn.mt4_server_host,
                symbol="",  # TODO: Store symbol in connection table
                status=conn.status,
                last_heartbeat=conn.last_heartbeat,
                encryption_enabled=conn.encryption_enabled
            )
            for conn in connections
        ]
        
        return EAConnectionListResponse(
            connections=connection_responses,
            count=len(connection_responses)
        )
    
    except Exception as e:
        logger.error("list_connections_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list connections: {str(e)}"
        )


@router.get(
    "/connections/{ea_id}",
    response_model=EAConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get EA connection details",
    description="Get detailed information about a specific EA connection",
    responses={
        200: {"description": "Connection details retrieved"},
        404: {"model": ErrorResponse, "description": "EA not found"},
    }
)
async def get_ea_connection(
    ea_id: str,
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Get specific EA connection details (T100).
    """
    try:
        logger.info("api_get_connection_request", ea_id=ea_id)
        
        connection = await service.connection_repository.get_by_ea_id(ea_id)
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EA {ea_id} not found"
            )
        
        return EAConnectionResponse(
            ea_id=connection.ea_id,
            magic_number=connection.magic_number,
            rep_port=connection.rep_port,
            pub_port=connection.pub_port,
            host=connection.mt4_server_host,
            symbol="",  # TODO: Store symbol in connection table
            status=connection.status,
            last_heartbeat=connection.last_heartbeat,
            encryption_enabled=connection.encryption_enabled
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_connection_error", ea_id=ea_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get connection details: {str(e)}"
        )


@router.delete(
    "/connections/{ea_id}",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Unregister EA",
    description="Unregister an EA and release its resources",
    responses={
        200: {"description": "EA unregistered successfully"},
        404: {"model": ErrorResponse, "description": "EA not found"},
    }
)
async def unregister_ea(
    ea_id: str,
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Unregister an EA (T101).
    """
    try:
        logger.info("api_unregister_ea_request", ea_id=ea_id)
        
        await service.unregister_ea(ea_id)
        
        return SuccessResponse(
            success=True,
            message=f"EA {ea_id} unregistered successfully"
        )
    
    except ValueError as e:
        logger.warning("ea_unregister_not_found", ea_id=ea_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EA {ea_id} not found"
        )
    except Exception as e:
        logger.error("ea_unregister_error", ea_id=ea_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unregister EA: {str(e)}"
        )


@router.post(
    "/connections/{ea_id}/reconnect",
    response_model=ReconnectEAResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconnect EA",
    description="Trigger reconnection for an EA connection",
    responses={
        200: {"description": "Reconnection initiated"},
        404: {"model": ErrorResponse, "description": "EA not found"},
    }
)
async def reconnect_ea(
    ea_id: str,
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Reconnect an EA (T102).
    
    Note: This triggers a reconnection attempt. Actual reconnection
    is handled asynchronously by the MT4Client.
    """
    try:
        logger.info("api_reconnect_ea_request", ea_id=ea_id)
        
        # Check if EA exists
        connection = await service.connection_repository.get_by_ea_id(ea_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EA {ea_id} not found"
            )
        
        # Get client and trigger reconnection
        client = await service.get_or_create_client(connection.magic_number)
        
        # Reconnect (this will be implemented in Circuit Breaker phase)
        # For now, just return status
        await service.connection_repository.update_status(
            ea_id=ea_id,
            status="RECONNECTING"
        )
        
        return ReconnectEAResponse(
            ea_id=ea_id,
            status="RECONNECTING",
            message=f"Reconnection initiated for EA {ea_id}"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ea_reconnect_error", ea_id=ea_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reconnect EA: {str(e)}"
        )


# =============================================================================
# Order Query Endpoint (T103)
# =============================================================================

@router.get(
    "/orders",
    response_model=OrderListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query orders",
    description="Query order history with optional filters",
)
async def query_orders(
    magic_number: Optional[int] = Query(None, description="Filter by magic number"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=1000, description="Result limit"),
    offset: int = Query(0, ge=0, description="Result offset"),
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Query order history (T103).
    """
    try:
        logger.info(
            "api_query_orders_request",
            magic_number=magic_number,
            symbol=symbol,
            status=status_filter,
            limit=limit,
            offset=offset
        )
        
        # Build filter dictionary
        filters = {}
        if magic_number:
            filters["magic_number"] = magic_number
        if symbol:
            filters["symbol"] = symbol
        if status_filter:
            filters["status"] = status_filter
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        
        # Query orders from repository
        orders = await service.order_repository.find_with_filters(
            filters=filters,
            limit=limit,
            offset=offset
        )
        
        total_count = await service.order_repository.count_with_filters(filters)
        
        order_responses = [
            OrderResponse(
                order_id=order.order_id,
                magic_number=order.magic_number,
                symbol=order.symbol,
                direction=order.direction,
                volume=order.volume,
                status=order.status,
                ticket_number=order.ticket_number,
                execution_price=order.execution_price,
                created_at=order.created_at,
                updated_at=order.updated_at
            )
            for order in orders
        ]
        
        return OrderListResponse(
            orders=order_responses,
            count=total_count,
            limit=limit,
            offset=offset
        )
    
    except Exception as e:
        logger.error("query_orders_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query orders: {str(e)}"
        )


# =============================================================================
# Portfolio Endpoints (T104-T105)
# =============================================================================

@router.get(
    "/positions",
    response_model=OpenPositionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Query open positions",
    description="Query open positions across all or specific EAs",
)
async def query_positions(
    magic_number: Optional[int] = Query(None, description="Filter by EA magic number"),
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Query open positions (T104).
    
    This is an alias/duplicate of the /positions endpoint for consistency with task list.
    """
    return await get_open_positions(magic_number=magic_number, service=service)


@router.get(
    "/portfolio/risk",
    response_model=PortfolioRiskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get portfolio risk state",
    description="Get aggregated portfolio risk metrics across all EAs",
)
async def get_portfolio_risk(
    use_cache: bool = Query(True, description="Whether to use cached data"),
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Get portfolio risk state (T105).
    """
    try:
        logger.info("api_portfolio_risk_request")
        
        if use_cache:
            risk_state = await service.get_cached_portfolio_risk()
        else:
            # Force recalculation - requires position_repository
            # This will be implemented with full repository access
            risk_state = await service.get_cached_portfolio_risk()
        
        if not risk_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio risk data not available"
            )
        
        return PortfolioRiskResponse(
            total_equity=risk_state.total_equity,
            total_margin_used=risk_state.total_margin_used,
            margin_level=risk_state.margin_level,
            total_open_positions=risk_state.total_open_positions,
            exposure_by_symbol=risk_state.exposure_by_symbol,
            exposure_by_ea=risk_state.exposure_by_ea,
            last_updated=risk_state.last_updated,
            is_margin_critical=risk_state.is_margin_critical,
            available_margin_pct=risk_state.available_margin_pct
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio_risk_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get portfolio risk: {str(e)}"
        )


# =============================================================================
# Health Check Endpoint (T106)
# =============================================================================

@router.get(
    "/portfolio/health",
    response_model=ServiceHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    description="Get MT4 integration service health status",
)
async def get_service_health(
    service: MT4IntegrationService = Depends(get_mt4_service)
):
    """
    Get service health status (T106).
    """
    try:
        logger.info("api_health_check_request")
        
        issues = []
        
        # Check database connectivity
        try:
            await service.connection_repository.get_all()
            db_healthy = True
        except Exception as e:
            db_healthy = False
            issues.append(f"Database connection error: {str(e)}")
        
        # Check Redis connectivity
        try:
            await service.redis_client.ping()
            redis_healthy = True
        except Exception as e:
            redis_healthy = False
            issues.append(f"Redis connection error: {str(e)}")
        
        # Get active connections
        connections = await service.connection_repository.get_all()
        active_connections = len([c for c in connections if c.status == "ACTIVE"])
        
        # Get MT4 connection health
        healthy_connections = 0
        for conn in connections:
            health = service.connection_pool.get_ea_health(conn.ea_id)
            if health and health.get("status") == "ACTIVE":
                healthy_connections += 1
        
        # Get order stats (today)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        orders_today = await service.order_repository.count_with_filters({
            "start_date": today_start
        })
        
        # Get open positions count
        # This would need position_repository access
        positions_open = 0  # Placeholder
        
        # Calculate overall status
        if not db_healthy or not redis_healthy:
            overall_status = "unhealthy"
        elif healthy_connections < active_connections * 0.5:
            overall_status = "degraded"
            issues.append(f"Only {healthy_connections}/{active_connections} MT4 connections healthy")
        else:
            overall_status = "healthy"
        
        return ServiceHealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            uptime_seconds=0.0,  # TODO: Track service start time
            active_connections=active_connections,
            total_orders_today=orders_today,
            total_positions_open=positions_open,
            errors_last_hour=0,  # TODO: Track error metrics
            avg_order_latency_ms=None,  # TODO: Get from metrics
            database_healthy=db_healthy,
            redis_healthy=redis_healthy,
            mt4_connections_healthy=healthy_connections,
            issues=issues
        )
    
    except Exception as e:
        logger.error("health_check_error", error=str(e))
        # Return unhealthy status instead of error
        return ServiceHealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            uptime_seconds=0.0,
            active_connections=0,
            total_orders_today=0,
            total_positions_open=0,
            errors_last_hour=0,
            avg_order_latency_ms=None,
            database_healthy=False,
            redis_healthy=False,
            mt4_connections_healthy=0,
            issues=[f"Health check failed: {str(e)}"]
        )
