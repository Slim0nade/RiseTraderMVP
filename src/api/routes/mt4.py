"""
MT4 Connection Management API Routes

Endpoints for EA registration, connection health monitoring,
account info, positions, orders, and portfolio risk.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..models.mt4_models import (
    AccountInfoResponse,
    EAInfoResponse,
    EAListResponse,
    MT4OrderListResponse,
    MT4OrderResponse,
    MT4PositionListResponse,
    MT4PositionResponse,
    PortfolioHealthResponse,
    PortfolioRiskResponse,
    RegisterEARequest,
    RegisterEAResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mt4", tags=["mt4"])


# =============================================================================
# Service Dependency
# =============================================================================

# Module-level singleton for the MT4 integration service
_mt4_service_instance = None


async def get_mt4_service():
    """
    Get or create the MT4IntegrationService singleton.

    Returns the cached instance if available, otherwise creates a new one
    with the required repositories, Redis client, and connection pool.

    Returns:
        MT4IntegrationService instance

    Raises:
        HTTPException: If service initialization fails
    """
    global _mt4_service_instance

    if _mt4_service_instance is not None:
        return _mt4_service_instance

    try:
        from src.services.mt4_integration_service import MT4IntegrationService
        from src.trading.execution.mt4_connection_pool import MT4ConnectionPool
        from src.trading.execution.symbol_loader import SymbolLoader
        from src.database.repositories.mt4_order_repository import MT4OrderRepository
        from src.database.repositories.mt4_connection_repository import MT4ConnectionRepository
        from src.utils.redis_client import MT4RedisClient

        order_repository = MT4OrderRepository()
        connection_repository = MT4ConnectionRepository()
        redis_client = MT4RedisClient()
        symbol_loader = SymbolLoader()
        connection_pool = MT4ConnectionPool()

        _mt4_service_instance = MT4IntegrationService(
            order_repository=order_repository,
            redis_client=redis_client,
            connection_repository=connection_repository,
            symbol_loader=symbol_loader,
            connection_pool=connection_pool,
        )

        logger.info("mt4_service_initialized")
        return _mt4_service_instance

    except Exception as e:
        logger.error("mt4_service_initialization_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MT4 integration service unavailable: {str(e)}",
        )


# =============================================================================
# EA Connection Management
# =============================================================================

@router.post("/connections", response_model=RegisterEAResponse, status_code=status.HTTP_201_CREATED)
async def register_ea(
    request: RegisterEARequest,
    service=Depends(get_mt4_service),
) -> RegisterEAResponse:
    """
    Register a new Expert Advisor in the connection pool.

    Allocates a magic number and port pair, registers the EA in the pool
    and persists to the database.

    Args:
        request: EA registration parameters
        service: MT4 integration service

    Returns:
        Registration details including allocated magic number and ports
    """
    try:
        kwargs = {}
        if request.strategy_name:
            kwargs["strategy_name"] = request.strategy_name
        if request.max_positions is not None:
            kwargs["max_positions"] = request.max_positions

        result = await service.register_ea(
            ea_id=request.name,
            symbol=request.symbol,
            host=request.host,
            **kwargs,
        )

        logger.info(
            "ea_registered_via_api",
            ea_id=result["ea_id"],
            magic_number=result["magic_number"],
        )

        return RegisterEAResponse(
            ea_id=result["ea_id"],
            magic_number=result["magic_number"],
            rep_port=result["rep_port"],
            pub_port=result["pub_port"],
            host=result["host"],
            symbol=result["symbol"],
        )

    except ValueError as e:
        logger.warning("ea_registration_conflict", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error("ea_registration_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register EA: {str(e)}",
        )


@router.get("/connections", response_model=EAListResponse)
async def list_eas(
    service=Depends(get_mt4_service),
) -> EAListResponse:
    """
    List all registered Expert Advisors with their connection info and health.

    Returns:
        List of all registered EAs with health status
    """
    try:
        all_eas = service.connection_pool.get_all_eas()
        all_health = service.connection_pool.get_all_ea_health()

        ea_list = []
        for ea_id, ea_info in all_eas.items():
            health = all_health.get(ea_id, {})

            ea_list.append(
                EAInfoResponse(
                    ea_id=ea_id,
                    magic_number=ea_info["magic_number"],
                    rep_port=ea_info["rep_port"],
                    pub_port=ea_info["pub_port"],
                    host=ea_info["host"],
                    symbol=ea_info["symbol"],
                    strategy_name=ea_info.get("strategy_name"),
                    registered_at=ea_info.get("registered_at"),
                    health_status=health.get("health_status"),
                    last_heartbeat=health.get("last_heartbeat"),
                    is_healthy=health.get("is_healthy"),
                )
            )

        return EAListResponse(eas=ea_list, total=len(ea_list))

    except Exception as e:
        logger.error("list_eas_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list EAs: {str(e)}",
        )


@router.get("/connections/{ea_id}", response_model=EAInfoResponse)
async def get_ea(
    ea_id: str,
    service=Depends(get_mt4_service),
) -> EAInfoResponse:
    """
    Get information and health status for a specific EA.

    Args:
        ea_id: EA identifier
        service: MT4 integration service

    Returns:
        EA connection info and health status
    """
    try:
        ea_info = service.connection_pool.get_ea_info(ea_id)
        if not ea_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EA not found: {ea_id}",
            )

        health = service.connection_pool.get_ea_health(ea_id) or {}

        return EAInfoResponse(
            ea_id=ea_id,
            magic_number=ea_info["magic_number"],
            rep_port=ea_info["rep_port"],
            pub_port=ea_info["pub_port"],
            host=ea_info["host"],
            symbol=ea_info["symbol"],
            strategy_name=ea_info.get("strategy_name"),
            registered_at=ea_info.get("registered_at"),
            health_status=health.get("health_status"),
            last_heartbeat=health.get("last_heartbeat"),
            is_healthy=health.get("is_healthy"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_ea_failed", ea_id=ea_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get EA info: {str(e)}",
        )


@router.delete("/connections/{ea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_ea(
    ea_id: str,
    service=Depends(get_mt4_service),
) -> None:
    """
    Unregister an EA and release its allocated resources.

    Disconnects the MT4 client, releases magic number and ports,
    and updates the database status to INACTIVE.

    Args:
        ea_id: EA identifier to unregister
        service: MT4 integration service
    """
    try:
        ea_info = service.connection_pool.get_ea_info(ea_id)
        if not ea_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EA not found: {ea_id}",
            )

        await service.unregister_ea(ea_id)

        logger.info("ea_unregistered_via_api", ea_id=ea_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("unregister_ea_failed", ea_id=ea_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unregister EA: {str(e)}",
        )


@router.post("/connections/{ea_id}/reconnect")
async def reconnect_ea(
    ea_id: str,
    service=Depends(get_mt4_service),
) -> dict:
    """
    Trigger reconnection for a specific EA.

    Disconnects the existing MT4 client (if any) and removes it from the
    client cache so the next operation will create a fresh connection.

    Args:
        ea_id: EA identifier to reconnect
        service: MT4 integration service

    Returns:
        Reconnection status
    """
    try:
        ea_info = service.connection_pool.get_ea_info(ea_id)
        if not ea_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EA not found: {ea_id}",
            )

        magic_number = ea_info["magic_number"]

        # Disconnect existing client if present
        if magic_number in service._clients:
            client = service._clients[magic_number]
            try:
                await client.disconnect()
            except Exception as disconnect_err:
                logger.warning(
                    "disconnect_during_reconnect_failed",
                    ea_id=ea_id,
                    error=str(disconnect_err),
                )
            del service._clients[magic_number]

        # Force a fresh connection by requesting the client
        await service._get_client(magic_number)

        # Update health status
        service.connection_pool.update_ea_health(
            ea_id=ea_id,
            status="ACTIVE",
        )

        logger.info("ea_reconnected_via_api", ea_id=ea_id, magic_number=magic_number)

        return {
            "success": True,
            "ea_id": ea_id,
            "magic_number": magic_number,
            "message": f"EA '{ea_id}' reconnected successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("reconnect_ea_failed", ea_id=ea_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reconnect EA: {str(e)}",
        )


# =============================================================================
# Orders
# =============================================================================

@router.get("/orders", response_model=MT4OrderListResponse)
async def get_orders(
    symbol: str = Query(None, description="Filter by trading symbol"),
    order_status: str = Query(None, alias="status", description="Filter by order status (PENDING, CONFIRMED, REJECTED, CLOSED)"),
    service=Depends(get_mt4_service),
) -> MT4OrderListResponse:
    """
    Query MT4 orders with optional filters.

    Args:
        symbol: Optional symbol filter
        order_status: Optional status filter
        service: MT4 integration service

    Returns:
        List of matching orders
    """
    try:
        filters = {}
        if symbol:
            filters["symbol"] = symbol
        if order_status:
            filters["status"] = order_status

        orders = await service.order_repository.get_all(**filters)

        order_responses = []
        for order in orders:
            order_responses.append(
                MT4OrderResponse(
                    ticket=getattr(order, "ticket_number", None),
                    order_id=getattr(order, "order_id", None),
                    symbol=order.symbol,
                    type=getattr(order, "order_type", "MARKET"),
                    direction=order.direction,
                    lots=order.volume,
                    price=getattr(order, "execution_price", None),
                    sl=getattr(order, "stop_loss", None),
                    tp=getattr(order, "take_profit", None),
                    status=order.status,
                    submitted_at=getattr(order, "submitted_at", None),
                    confirmed_at=getattr(order, "confirmed_at", None),
                    error_message=getattr(order, "error_message", None),
                )
            )

        return MT4OrderListResponse(orders=order_responses, total=len(order_responses))

    except Exception as e:
        logger.error("get_orders_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve orders: {str(e)}",
        )


# =============================================================================
# Positions
# =============================================================================

@router.get("/positions", response_model=MT4PositionListResponse)
async def get_mt4_positions(
    symbol: str = Query(None, description="Filter by trading symbol"),
    service=Depends(get_mt4_service),
) -> MT4PositionListResponse:
    """
    Query open positions from MT4 via the connection pool.

    Retrieves positions from the first active EA client. If a symbol filter
    is provided, only matching positions are returned.

    Args:
        symbol: Optional symbol filter
        service: MT4 integration service

    Returns:
        List of open MT4 positions
    """
    try:
        positions = []

        # Iterate through connected clients and gather positions
        for magic_number, client in service._clients.items():
            try:
                response = await client.get_open_positions()
                if response.success:
                    for pos in response.positions:
                        if symbol and pos.symbol != symbol:
                            continue
                        positions.append(
                            MT4PositionResponse(
                                ticket=pos.ticket_number,
                                symbol=pos.symbol,
                                direction=pos.direction,
                                lots=pos.volume,
                                entry_price=pos.open_price,
                                current_price=pos.current_price,
                                sl=pos.stop_loss,
                                tp=pos.take_profit,
                                profit=pos.unrealized_pnl,
                                open_time=pos.open_time,
                                magic_number=pos.magic_number,
                                comment=getattr(pos, "comment", None),
                            )
                        )
            except Exception as client_err:
                logger.warning(
                    "get_positions_from_client_failed",
                    magic_number=magic_number,
                    error=str(client_err),
                )

        return MT4PositionListResponse(positions=positions, total=len(positions))

    except Exception as e:
        logger.error("get_mt4_positions_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve MT4 positions: {str(e)}",
        )


# =============================================================================
# Account Info
# =============================================================================

@router.get("/account", response_model=AccountInfoResponse)
async def get_account_info(
    service=Depends(get_mt4_service),
) -> AccountInfoResponse:
    """
    Get MT4 account information from the first active client.

    Retrieves balance, equity, margin, free margin, and leverage
    from the connected MT4 terminal.

    Returns:
        Account information
    """
    try:
        # Use the first available client
        if not service._clients:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No active MT4 connections. Register and connect an EA first.",
            )

        magic_number = next(iter(service._clients))
        client = service._clients[magic_number]

        response = await client.get_account_info()

        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"MT4 account info request failed: {response.error_message or 'Unknown error'}",
            )

        return AccountInfoResponse(
            balance=response.balance,
            equity=response.equity,
            margin=response.margin,
            free_margin=response.free_margin,
            leverage=response.leverage,
            account_number=response.account_number,
            margin_level=response.margin_level,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_account_info_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve account info: {str(e)}",
        )


# =============================================================================
# Portfolio Risk & Health
# =============================================================================

@router.get("/portfolio/risk", response_model=PortfolioRiskResponse)
async def get_portfolio_risk(
    service=Depends(get_mt4_service),
) -> PortfolioRiskResponse:
    """
    Get portfolio-level risk state aggregated across all EAs.

    Returns cached risk state if available and fresh (< 5s old),
    otherwise calculates a new snapshot.

    Returns:
        Portfolio risk metrics including exposure by symbol and EA
    """
    try:
        # Try cached first
        cached = await service.get_cached_portfolio_risk(cache_ttl_seconds=5)

        if cached:
            risk_state = cached
        else:
            # Calculate fresh -- need a position repository
            from src.database.repositories.mt4_position_repository import MT4PositionRepository

            position_repo = MT4PositionRepository()
            risk_state = await service.update_portfolio_risk_cache(
                position_repository=position_repo,
                publish_event=False,
            )

        # Convert Decimal dict values to float for JSON serialization
        exposure_symbol = {
            k: float(v) for k, v in risk_state.exposure_by_symbol.items()
        }
        exposure_ea = {
            k: float(v) for k, v in risk_state.exposure_by_ea.items()
        }

        return PortfolioRiskResponse(
            total_equity=risk_state.total_equity,
            total_margin_used=risk_state.total_margin_used,
            margin_level=risk_state.margin_level,
            total_open_positions=risk_state.total_open_positions,
            exposure_by_symbol=exposure_symbol,
            exposure_by_ea=exposure_ea,
            is_margin_critical=risk_state.is_margin_critical,
            last_updated=risk_state.last_updated,
        )

    except Exception as e:
        logger.error("get_portfolio_risk_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve portfolio risk: {str(e)}",
        )


@router.get("/portfolio/health", response_model=PortfolioHealthResponse)
async def get_portfolio_health(
    service=Depends(get_mt4_service),
) -> PortfolioHealthResponse:
    """
    System-level MT4 health check.

    Reports overall connection status, number of active EAs,
    and per-EA health details.

    Returns:
        Portfolio health status with per-EA connection details
    """
    try:
        all_eas = service.connection_pool.get_all_eas()
        all_health = service.connection_pool.get_all_ea_health()

        total_eas = len(all_eas)
        active_count = 0
        connection_status = {}

        for ea_id, health_info in all_health.items():
            is_healthy = health_info.get("is_healthy", False)
            if is_healthy:
                active_count += 1
            connection_status[ea_id] = {
                "is_healthy": is_healthy,
                "health_status": health_info.get("health_status", "UNKNOWN"),
                "seconds_since_heartbeat": health_info.get("seconds_since_heartbeat"),
                "magic_number": health_info.get("magic_number"),
            }

        # Determine overall status
        if total_eas == 0:
            overall_status = "unhealthy"
        elif active_count == total_eas:
            overall_status = "healthy"
        elif active_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return PortfolioHealthResponse(
            status=overall_status,
            active_eas=active_count,
            total_eas=total_eas,
            connection_status=connection_status,
        )

    except Exception as e:
        logger.error("get_portfolio_health_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve portfolio health: {str(e)}",
        )
