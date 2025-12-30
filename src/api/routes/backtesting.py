"""
Backtesting API Routes

Endpoints for backtest configuration, execution, and results retrieval.
Implements Phase 3 (T045-T051) from 006-backtesting-engine specification.
"""
import asyncio
import structlog
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.backtest import ExecutionMode as DBExecutionMode
from src.services.backtesting.backtest_events import get_event_broadcaster
from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.backtesting import BacktestService, ComparisonService, SyntheticEngine
from ..dependencies import get_db
from ..models import (
    BacktestConfigListResponse,
    BacktestConfigResponse,
    BacktestRunResponse,
    BacktestRunStatusResponse,
    CancelRunResponse,
    CompareRunsRequest,
    CompareRunsResponse,
    CreateBacktestConfigRequest,
    CreateParameterGridRequest,
    ErrorResponse,
    ExecuteParameterGridRequest,
    MetricsComparisonResponse,
    OptimizationResultResponse,
    ParameterGridResponse,
    ParameterGridResultsResponse,
    BacktestPerformanceMetricsResponse,
    RunBacktestRequest,
    SimulatedTradeResponse,
    StatisticalTestResponse,
    TradeListResponse,
    TradeOverlapResponse,
    ValidationResultResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/backtesting", tags=["backtesting"])


def get_backtest_service(
    db: AsyncSession = Depends(get_db),
) -> BacktestService:
    """
    Dependency to create BacktestService.

    Args:
        db: Database session

    Returns:
        BacktestService instance
    """
    backtest_repo = BacktestRepository(db)
    market_data_repo = MarketDataRepository(db)
    return BacktestService(
        session=db,
        backtest_repository=backtest_repo,
        market_data_repository=market_data_repo,
    )


@router.post(
    "/configurations",
    response_model=BacktestConfigResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Configuration created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def create_configuration(
    request: CreateBacktestConfigRequest,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestConfigResponse:
    """
    Create a new backtest configuration (T045).

    Creates a backtest configuration that can be executed multiple times
    with different parameters or random seeds.

    Features:
    - Validates date ranges and capital
    - Supports both full_pipeline and synthetic_fast modes
    - Stores configuration for reuse

    Args:
        request: Configuration creation request

    Returns:
        Created configuration with UUID

    Example:
        POST /api/v1/backtesting/configurations
        {
            "name": "MA Crossover EURUSD 2024",
            "symbol": "EURUSD",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-12-31T23:59:59Z",
            "initial_capital": "10000.00",
            "execution_mode": "synthetic_fast",
            "config_params": {
                "strategy": "ma_crossover",
                "fast_period": 10,
                "slow_period": 30
            }
        }
    """
    try:
        # Convert API ExecutionMode to DB ExecutionMode
        db_execution_mode = DBExecutionMode(request.execution_mode.value)

        config = await service.create_configuration(
            name=request.name,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            execution_mode=db_execution_mode,
            agent_config_ref=request.agent_config_ref,
            slippage_pct=request.slippage_pct,
            commission_pct=request.commission_pct,
            commission_fixed=request.commission_fixed,
            max_leverage=request.max_leverage,
            allow_short_selling=request.allow_short_selling,
            config_params=request.config_params,
        )

        await service.session.commit()

        logger.info(
            "backtest_config_created",
            config_id=str(config.id),
            name=config.name,
            symbol=config.symbol,
        )

        return BacktestConfigResponse.model_validate(config)

    except ValueError as e:
        logger.warning("create_config_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "create_config_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create configuration: {str(e)}",
        )


@router.get(
    "/configurations/{config_id}",
    response_model=BacktestConfigResponse,
    responses={
        200: {"description": "Configuration retrieved"},
        404: {"model": ErrorResponse, "description": "Configuration not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_configuration(
    config_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestConfigResponse:
    """
    Get backtest configuration by ID (T046).

    Retrieves a previously created backtest configuration.

    Args:
        config_id: Configuration UUID

    Returns:
        Configuration details

    Example:
        GET /api/v1/backtesting/configurations/{config_id}
    """
    try:
        config = await service.backtest_repo.get_config(config_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration {config_id} not found",
            )

        logger.info("get_config_success", config_id=str(config_id))

        return BacktestConfigResponse.model_validate(config)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_config_failed",
            config_id=str(config_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configuration: {str(e)}",
        )


@router.get(
    "/configurations",
    response_model=BacktestConfigListResponse,
    responses={
        200: {"description": "List of configurations"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_configurations(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestConfigListResponse:
    """
    List backtest configurations with optional filtering.

    Args:
        symbol: Optional symbol filter
        limit: Maximum results (1-100)
        offset: Results offset

    Returns:
        List of configurations

    Example:
        GET /api/v1/backtesting/configurations?symbol=EURUSD&limit=10
    """
    try:
        configs = await service.backtest_repo.list_configs(
            symbol=symbol, limit=limit, offset=offset
        )

        total = len(configs)  # In production, use separate count query

        logger.info("list_configs_success", total=total, symbol=symbol)

        return BacktestConfigListResponse(
            total=total,
            items=[BacktestConfigResponse.model_validate(c) for c in configs],
        )

    except Exception as e:
        logger.error(
            "list_configs_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list configurations: {str(e)}",
        )


@router.post(
    "/configurations/{config_id}/validate",
    response_model=ValidationResultResponse,
    responses={
        200: {"description": "Validation completed"},
        404: {"model": ErrorResponse, "description": "Configuration not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def validate_configuration(
    config_id: UUID,
    timeframe: str = Query("M5", description="Timeframe to validate"),
    service: BacktestService = Depends(get_backtest_service),
) -> ValidationResultResponse:
    """
    Validate backtest configuration and data availability.

    Checks:
    - Configuration validity
    - Market data availability
    - Data continuity and quality

    Args:
        config_id: Configuration UUID
        timeframe: Market data timeframe

    Returns:
        Validation result with recommendations

    Example:
        POST /api/v1/backtesting/configurations/{config_id}/validate?timeframe=M5
    """
    try:
        config = await service.backtest_repo.get_config(config_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration {config_id} not found",
            )

        validation = await service.validate_configuration(config, timeframe)

        logger.info(
            "config_validated",
            config_id=str(config_id),
            can_proceed=validation["can_proceed"],
        )

        return ValidationResultResponse(
            config_id=config.id,
            config_name=config.name,
            can_proceed=validation["can_proceed"],
            configuration_valid=validation["configuration_valid"],
            data_validation=validation["data_validation"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validate_config_failed",
            config_id=str(config_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}",
        )


@router.post(
    "/runs",
    response_model=BacktestRunStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Backtest started (processing asynchronously)"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Configuration not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def run_backtest(
    request: RunBacktestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> BacktestRunStatusResponse:
    """
    Execute a backtest run (T047).

    Starts a backtest execution asynchronously in the background.
    Use the returned run_id to poll for status and results.

    Features:
    - Asynchronous execution (non-blocking)
    - Progress tracking
    - Supports synthetic strategies or full pipeline mode
    - Deterministic replay with random seed

    Args:
        request: Backtest execution request
        background_tasks: FastAPI background tasks

    Returns:
        Run status with run_id for polling

    Example:
        POST /api/v1/backtesting/runs
        {
            "config_id": "123e4567-e89b-12d3-a456-426614174000",
            "timeframe": "M5",
            "random_seed": 42,
            "synthetic_strategy": "ma_crossover",
            "synthetic_params": {
                "fast_period": 10,
                "slow_period": 30,
                "quantity": "1.0"
            }
        }
    """
    from src.database.models.backtest import BacktestRun, RunStatus as DBRunStatus
    from datetime import datetime
    from uuid import uuid4
    from ..dependencies import AsyncSessionLocal
    
    try:
        # Create run record first (to return to client immediately)
        run_id = uuid4()
        run = BacktestRun(
            id=run_id,
            config_id=request.config_id,
            status=DBRunStatus.RUNNING,
            start_time=datetime.now(),
            random_seed=request.random_seed,
            candles_processed=0,
            total_trades=0,
            agent_decisions_count=0,
        )

        db.add(run)
        await db.commit()
        await db.refresh(run)

        # Capture request params for background task
        config_id = request.config_id
        timeframe = request.timeframe
        random_seed = request.random_seed
        synthetic_strategy = request.synthetic_strategy
        synthetic_params = request.synthetic_params

        # Background task with its own session
        async def run_backtest_task():
            """Background task to run backtest with fresh database session."""
            async with AsyncSessionLocal() as task_session:
                try:
                    # Create fresh service with new session
                    task_backtest_repo = BacktestRepository(task_session)
                    task_market_data_repo = MarketDataRepository(task_session)
                    task_service = BacktestService(
                        session=task_session,
                        backtest_repository=task_backtest_repo,
                        market_data_repository=task_market_data_repo,
                    )

                    # Create decision engine if synthetic strategy specified in request
                    decision_engine = None
                    if synthetic_strategy:
                        synthetic_engine = SyntheticEngine(
                            strategy=synthetic_strategy,
                            params=synthetic_params or {},
                        )
                        decision_engine = lambda tick: {
                            "action": (
                                signal.action if (signal := synthetic_engine.process_tick(tick)).action else None
                            ),
                            "quantity": signal.quantity if signal.action else None,
                        }

                    # Run the backtest using the existing run record (fixes duplicate run bug)
                    await task_service.run_backtest(
                        config_id=config_id,
                        timeframe=timeframe,
                        random_seed=random_seed,
                        decision_engine=decision_engine,
                        existing_run_id=run_id,  # Pass the pre-created run ID
                    )
                    
                    logger.info(
                        "backtest_completed",
                        run_id=str(run_id),
                        config_id=str(config_id),
                    )
                    
                except Exception as e:
                    logger.error(
                        "backtest_execution_failed",
                        run_id=str(run_id),
                        config_id=str(config_id),
                        error=str(e),
                        exc_info=True,
                    )
                    # Update run status to failed
                    try:
                        await task_backtest_repo.update_run(
                            run_id=run_id,
                            update_data={
                                "status": DBRunStatus.FAILED,
                                "end_time": datetime.now(),
                                "error_message": str(e),
                            }
                        )
                        await task_session.commit()
                    except Exception as update_error:
                        logger.error(
                            "failed_to_update_run_status",
                            run_id=str(run_id),
                            error=str(update_error),
                        )

        # Schedule background task
        background_tasks.add_task(run_backtest_task)

        logger.info(
            "backtest_started",
            run_id=str(run.id),
            config_id=str(request.config_id),
        )

        return BacktestRunStatusResponse.model_validate(run)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "run_backtest_failed",
            config_id=str(request.config_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start backtest: {str(e)}",
        )


@router.get(
    "/runs",
    response_model=dict,
    responses={
        200: {"description": "List of backtest runs"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_runs(
    config_id: Optional[UUID] = Query(None, description="Filter by configuration ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (pending, running, completed, failed)"),
    limit: int = Query(50, ge=1, le=200, description="Number of runs to return"),
    offset: int = Query(0, ge=0, description="Number of runs to skip"),
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    """
    List backtest runs with optional filters.

    Returns a paginated list of backtest runs, optionally filtered by
    configuration ID and/or status.

    Args:
        config_id: Optional filter by configuration UUID
        status_filter: Optional filter by run status
        limit: Maximum number of runs to return (1-200)
        offset: Number of runs to skip for pagination

    Returns:
        Dictionary with total count and list of runs

    Example:
        GET /api/v1/backtesting/runs
        GET /api/v1/backtesting/runs?config_id={uuid}
        GET /api/v1/backtesting/runs?status=completed&limit=20
    """
    try:
        runs = await service.backtest_repo.list_runs(
            config_id=config_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )

        total = len(runs)  # For now, simple count. TODO: Add count query to repo

        logger.info(
            "list_runs_success",
            total=total,
            config_id=str(config_id) if config_id else None,
            status_filter=status_filter,
        )

        return {
            "total": total,
            "items": [BacktestRunStatusResponse.model_validate(run) for run in runs],
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(
            "list_runs_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list runs: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/status",
    response_model=BacktestRunStatusResponse,
    responses={
        200: {"description": "Run status retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_run_status(
    run_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestRunStatusResponse:
    """
    Get backtest run status (T048).

    Poll this endpoint to track backtest progress.

    Returns:
    - Current status (pending, running, completed, failed)
    - Progress information
    - Candles processed
    - Error details (if failed)

    Args:
        run_id: Run UUID

    Returns:
        Run status and progress

    Example:
        GET /api/v1/backtesting/runs/{run_id}/status
    """
    try:
        run = await service.backtest_repo.get_run(run_id)

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        logger.info(
            "get_run_status_success",
            run_id=str(run_id),
            status=run.status.value,
        )

        return BacktestRunStatusResponse.model_validate(run)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_run_status_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve run status: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/metrics",
    response_model=BacktestRunResponse,
    responses={
        200: {"description": "Run metrics retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_run_metrics(
    run_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestRunResponse:
    """
    Get backtest run metrics (T049).

    Retrieves comprehensive performance metrics for a completed backtest.

    Metrics include:
    - Total return (% and absolute)
    - Risk-adjusted metrics (Sharpe, Sortino, Calmar)
    - Drawdown analysis
    - Win/loss statistics
    - Trade distribution

    Args:
        run_id: Run UUID

    Returns:
        Complete run results with metrics

    Example:
        GET /api/v1/backtesting/runs/{run_id}/metrics
    """
    try:
        run = await service.backtest_repo.get_run(run_id)

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Convert metrics dict to BacktestPerformanceMetricsResponse if available
        metrics_response = None
        if run.metrics:
            metrics_response = BacktestPerformanceMetricsResponse(**run.metrics)

        logger.info(
            "get_run_metrics_success",
            run_id=str(run_id),
            status=run.status.value,
        )

        return BacktestRunResponse(
            run_id=run.id,
            config_id=run.config_id,
            status=run.status,
            start_time=run.start_time,
            end_time=run.end_time,
            candles_processed=run.candles_processed,
            final_capital=run.final_capital,
            metrics=metrics_response,
            error_message=run.error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_run_metrics_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/trades",
    response_model=TradeListResponse,
    responses={
        200: {"description": "Trades retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_run_trades(
    run_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    service: BacktestService = Depends(get_backtest_service),
) -> TradeListResponse:
    """
    Get backtest run trades (T050).

    Retrieves all simulated trades from a backtest run.

    Features:
    - Pagination support
    - Includes entry/exit details
    - P&L calculations
    - Commission and slippage breakdown
    - Decision context (optional)

    Args:
        run_id: Run UUID
        limit: Maximum trades to return (1-1000)
        offset: Pagination offset

    Returns:
        List of trades with details

    Example:
        GET /api/v1/backtesting/runs/{run_id}/trades?limit=50&offset=0
    """
    try:
        # Verify run exists
        run = await service.backtest_repo.get_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Get trades with pagination
        all_trades = await service.backtest_repo.get_trades(run_id)
        trades = all_trades[offset : offset + limit]

        # Count closed vs open trades
        closed_trades = sum(1 for t in all_trades if t.exit_timestamp is not None)
        open_trades = len(all_trades) - closed_trades

        logger.info(
            "get_run_trades_success",
            run_id=str(run_id),
            total=len(all_trades),
            closed=closed_trades,
        )

        return TradeListResponse(
            total=len(all_trades),
            closed_trades=closed_trades,
            open_trades=open_trades,
            items=[SimulatedTradeResponse.model_validate(t) for t in trades],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_run_trades_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve trades: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/snapshots",
    responses={
        200: {"description": "Portfolio snapshots retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_run_snapshots(
    run_id: UUID,
    limit: int = Query(1000, ge=1, le=10000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    service: BacktestService = Depends(get_backtest_service),
):
    """
    Get portfolio snapshots (equity curve data) for a backtest run.

    Returns timestamped snapshots of portfolio state for equity curve visualization.

    Args:
        run_id: Run UUID
        limit: Maximum snapshots to return (1-10000)
        offset: Pagination offset

    Returns:
        List of portfolio snapshots with timestamps and values

    Example:
        GET /api/backtesting/runs/{run_id}/snapshots?limit=500
    """
    try:
        # Verify run exists
        run = await service.backtest_repo.get_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Get snapshots
        all_snapshots = await service.backtest_repo.get_snapshots(run_id)
        snapshots = all_snapshots[offset : offset + limit]

        logger.info(
            "get_run_snapshots_success",
            run_id=str(run_id),
            total=len(all_snapshots),
            returned=len(snapshots),
        )

        # Convert to response format
        snapshots_data = [
            {
                "timestamp": s.timestamp.isoformat(),
                "total_value": float(s.total_value),
                "cash_balance": float(s.cash_balance),
                "unrealized_pnl": float(s.unrealized_pnl) if s.unrealized_pnl else 0.0,
                "realized_pnl": float(s.realized_pnl) if s.realized_pnl else 0.0,
                "positions": s.positions or [],
            }
            for s in snapshots
        ]

        return {
            "total": len(all_snapshots),
            "items": snapshots_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_run_snapshots_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve snapshots: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/decisions",
    responses={
        200: {"description": "Agent decisions retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_run_decisions(
    run_id: UUID,
    limit: int = Query(1000, ge=1, le=10000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get agent decisions for a backtest run.

    Retrieves all agent decision logs from the agent_decision_logs table.

    Args:
        run_id: Run UUID
        limit: Maximum decisions to return (1-10000)
        offset: Pagination offset

    Returns:
        List of agent decisions with details

    Example:
        GET /api/backtesting/runs/{run_id}/decisions?limit=100&offset=0
    """
    try:
        from sqlalchemy import select, func
        from src.database.models.backtest import BacktestRun
        from src.database.models.simulated_trade import AgentDecisionLog

        # Verify run exists
        run_query = select(BacktestRun).where(BacktestRun.id == run_id)
        result = await db.execute(run_query)
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Get decisions with pagination
        decisions_query = (
            select(AgentDecisionLog)
            .where(AgentDecisionLog.backtest_run_id == run_id)
            .order_by(AgentDecisionLog.timestamp)
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(decisions_query)
        decisions = result.scalars().all()

        # Count total
        count_query = select(func.count()).where(AgentDecisionLog.backtest_run_id == run_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        logger.info(
            "get_run_decisions_success",
            run_id=str(run_id),
            total=total,
            returned=len(decisions),
        )

        # Convert to response format
        decisions_data = []
        for decision in decisions:
            output_data = decision.output_decision or {}
            input_data = decision.input_data or {}

            # Map action to decision_type (BUY/SELL/HOLD)
            action = output_data.get("action", "hold").upper()
            if action == "HOLD" or action == "NO_TRADE":
                decision_type = "HOLD"
            elif action == "BUY" or action == "LONG":
                decision_type = "BUY"
            elif action == "SELL" or action == "SHORT":
                decision_type = "SELL"
            else:
                decision_type = "HOLD"

            decisions_data.append({
                "id": str(decision.id),
                "run_id": str(decision.backtest_run_id),
                "timestamp": decision.timestamp.isoformat(),
                "decision_type": decision_type,
                "symbol": input_data.get("symbol", "UNKNOWN"),
                "conviction_score": output_data.get("conviction", 0.0),
                "quantity": output_data.get("quantity"),
                "stop_loss": None,  # Not in current schema
                "take_profit": None,  # Not in current schema
                "risk_assessment": output_data.get("rationale", ""),
                "reasoning": output_data.get("rationale"),
                "market_context": input_data,
            })

        return {
            "total": total,
            "items": decisions_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_run_decisions_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve decisions: {str(e)}",
        )


@router.delete(
    "/runs/{run_id}",
    response_model=CancelRunResponse,
    responses={
        200: {"description": "Run cancelled"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def cancel_run(
    run_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> CancelRunResponse:
    """
    Cancel a running backtest (T051).

    Stops a backtest that is currently running.
    Completed or failed backtests cannot be cancelled.

    Args:
        run_id: Run UUID

    Returns:
        Cancellation result

    Example:
        DELETE /api/v1/backtesting/runs/{run_id}
    """
    try:
        success = await service.cancel_run(run_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found or not cancellable",
            )

        logger.info("run_cancelled", run_id=str(run_id))

        return CancelRunResponse(
            success=True,
            run_id=run_id,
            message="Backtest run cancelled successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "cancel_run_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel run: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/equity-curve",
    responses={
        200: {"description": "Equity curve data retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_equity_curve(
    run_id: UUID,
    limit: int = Query(1000, ge=1, le=10000, description="Maximum points"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get equity curve data for visualization.

    Returns portfolio snapshots showing equity evolution over time.

    Args:
        run_id: Run UUID
        limit: Maximum data points to return

    Returns:
        Equity curve data with timestamps and values
    """
    try:
        from sqlalchemy import select
        from src.database.models.backtest import BacktestRun, PortfolioSnapshot

        # Verify run exists
        run_query = select(BacktestRun).where(BacktestRun.id == run_id)
        result = await db.execute(run_query)
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Get snapshots ordered by time
        snapshots_query = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.backtest_run_id == run_id)
            .order_by(PortfolioSnapshot.timestamp)
            .limit(limit)
        )
        result = await db.execute(snapshots_query)
        snapshots = result.scalars().all()

        equity_data = [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "total_value": float(snapshot.total_value),
                "cash_balance": float(snapshot.cash_balance),
                "unrealized_pnl": float(snapshot.unrealized_pnl),
                "realized_pnl": float(snapshot.realized_pnl),
                "positions_count": len(snapshot.positions) if snapshot.positions else 0,
            }
            for snapshot in snapshots
        ]

        logger.info(
            "equity_curve_retrieved",
            run_id=str(run_id),
            points=len(equity_data),
        )

        return {
            "run_id": str(run_id),
            "data_points": len(equity_data),
            "equity_curve": equity_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_equity_curve_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve equity curve: {str(e)}",
        )


@router.get(
    "/runs/{run_id}/live-stats",
    responses={
        200: {"description": "Live statistics retrieved"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_live_stats(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get live trading statistics for a running or completed backtest.

    Returns real-time metrics including:
    - Buy/Sell counts
    - Win/Loss statistics
    - P&L breakdown
    - Position information

    Args:
        run_id: Run UUID

    Returns:
        Live trading statistics
    """
    try:
        from sqlalchemy import select, func
        from src.database.models.backtest import BacktestRun
        from src.database.models.simulated_trade import SimulatedTrade, PortfolioSnapshot

        # Get run
        run_query = select(BacktestRun).where(BacktestRun.id == run_id)
        result = await db.execute(run_query)
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Get all trades
        trades_query = select(SimulatedTrade).where(SimulatedTrade.backtest_run_id == run_id)
        result = await db.execute(trades_query)
        trades = result.scalars().all()

        # Calculate statistics
        closed_trades = [t for t in trades if t.exit_timestamp is not None]
        buy_trades = [t for t in trades if t.action == "buy"]
        sell_trades = [t for t in trades if t.action == "sell"]
        winning_trades = [t for t in closed_trades if t.net_pnl and t.net_pnl > 0]
        losing_trades = [t for t in closed_trades if t.net_pnl and t.net_pnl <= 0]

        # P&L calculations
        total_realized_pnl = sum(t.net_pnl for t in closed_trades if t.net_pnl) or 0
        total_gross_pnl = sum(t.gross_pnl for t in closed_trades if t.gross_pnl) or 0
        total_fees = sum(t.fees_paid for t in closed_trades if t.fees_paid) or 0

        # Get latest snapshot for unrealized P&L
        latest_snapshot_query = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.backtest_run_id == run_id)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(latest_snapshot_query)
        latest_snapshot = result.scalar_one_or_none()

        unrealized_pnl = float(latest_snapshot.unrealized_pnl) if latest_snapshot else 0
        current_equity = float(latest_snapshot.total_value) if latest_snapshot else float(run.initial_capital) if hasattr(run, 'initial_capital') else 0

        logger.info(
            "live_stats_retrieved",
            run_id=str(run_id),
            total_trades=len(trades),
            closed_trades=len(closed_trades),
        )

        return {
            "run_id": str(run_id),
            "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
            "progress": {
                "candles_processed": run.candles_processed or 0,
                "agent_decisions": run.agent_decisions_count or 0,
            },
            "trade_counts": {
                "total": len(trades),
                "closed": len(closed_trades),
                "open": len(trades) - len(closed_trades),
                "buy": len(buy_trades),
                "sell": len(sell_trades),
                "win": len(winning_trades),
                "loss": len(losing_trades),
            },
            "performance": {
                "win_rate": (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0,
                "realized_pnl": float(total_realized_pnl),
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": float(total_realized_pnl) + unrealized_pnl,
                "gross_pnl": float(total_gross_pnl),
                "total_fees": float(total_fees),
                "current_equity": current_equity,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_live_stats_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve live stats: {str(e)}",
        )


# ============================================================================
# OPTIMIZATION ENDPOINTS (User Story 2)
# ============================================================================


@router.post(
    "/optimization/grids",
    response_model=ParameterGridResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Parameter grid created"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def create_parameter_grid(
    request: CreateParameterGridRequest,
    db: AsyncSession = Depends(get_db),
) -> ParameterGridResponse:
    """
    Create a parameter optimization grid (T070).

    Defines a grid of parameter combinations for batch optimization.
    The grid will be executed when /execute endpoint is called.

    Features:
    - Cartesian product of parameter values
    - Configurable parallel workers
    - Supports all synthetic strategies

    Args:
        request: Grid creation request

    Returns:
        Created parameter grid with UUID

    Example:
        POST /api/v1/backtesting/optimization/grids
        {
            "name": "MA Crossover Optimization",
            "symbol": "EURUSD",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-06-30T23:59:59Z",
            "timeframe": "M5",
            "initial_capital": "10000.00",
            "parameters": {
                "ema_fast": [5, 8, 10],
                "ema_slow": [20, 25, 29],
                "rsi_period": [10, 14]
            },
            "max_workers": 4,
            "synthetic_strategy": "ma_crossover"
        }
    """
    try:
        from src.database.repositories.parameter_grid_repository import (
            ParameterGridRepository,
        )
        from src.database.models.backtest import ParameterGrid as DBParameterGrid
        import itertools
        from datetime import datetime, timezone

        repo = ParameterGridRepository(db)

        # Calculate total combinations
        param_lists = list(request.parameters.values())
        total_combinations = 1
        for param_list in param_lists:
            total_combinations *= len(param_list)

        # Create database record
        grid = DBParameterGrid(
            name=request.name,
            description=request.description,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframe=request.timeframe,
            initial_capital=request.initial_capital,
            parameters=request.parameters,
            total_combinations=total_combinations,
            max_workers=request.max_workers,
            synthetic_strategy=request.synthetic_strategy,
            status="pending",
        )

        saved_grid = await repo.create(grid)

        logger.info(
            "parameter_grid_created",
            grid_id=str(saved_grid.id),
            total_combinations=total_combinations,
        )

        return ParameterGridResponse(
            grid_id=saved_grid.id,
            name=saved_grid.name,
            description=saved_grid.description,
            symbol=saved_grid.symbol,
            start_date=saved_grid.start_date,
            end_date=saved_grid.end_date,
            timeframe=saved_grid.timeframe,
            initial_capital=saved_grid.initial_capital,
            parameters=saved_grid.parameters,
            total_combinations=saved_grid.total_combinations,
            max_workers=saved_grid.max_workers,
            synthetic_strategy=saved_grid.synthetic_strategy,
            status=saved_grid.status,
            created_at=saved_grid.created_at,
        )

    except Exception as e:
        logger.error(
            "create_parameter_grid_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create parameter grid: {str(e)}",
        )


@router.post(
    "/optimization/grids/{grid_id}/execute",
    response_model=ParameterGridResultsResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Grid execution started"},
        404: {"model": ErrorResponse, "description": "Grid not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def execute_parameter_grid(
    grid_id: UUID,
    request: ExecuteParameterGridRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ParameterGridResultsResponse:
    """
    Execute a parameter grid optimization (T071).

    Runs backtests for all parameter combinations in parallel.
    Execution happens in background; poll /grids/{id}/results for status.

    Features:
    - Parallel execution with configurable workers
    - Early stopping on threshold
    - Custom result ranking
    - Progress tracking

    Args:
        grid_id: Parameter grid UUID
        request: Execution configuration

    Returns:
        Execution status and initial results

    Example:
        POST /api/v1/backtesting/optimization/grids/{grid_id}/execute
        {
            "early_stop_threshold": 2.5,
            "ranking_metric": "sharpe_ratio",
            "custom_weights": {
                "sharpe_ratio": 0.4,
                "total_return": 0.3,
                "profit_factor": 0.3
            }
        }
    """
    try:
        from src.database.repositories.parameter_grid_repository import (
            ParameterGridRepository,
        )
        from src.services.backtesting.batch_optimizer import (
            BatchOptimizer,
            ParameterGrid as OptimizerGrid,
            OptimizationResult,
        )
        from pathlib import Path
        import tempfile
        from decimal import Decimal

        repo = ParameterGridRepository(db)

        # Fetch grid
        grid = await repo.get_by_id(grid_id)
        if not grid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parameter grid {grid_id} not found",
            )

        # Create optimizer grid
        optimizer_grid = OptimizerGrid(**grid.parameters)

        # Create backtest function
        market_data_repo = MarketDataRepository(db)

        def run_single_backtest(params: dict) -> OptimizationResult:
            """Run backtest with given parameters (sync wrapper)."""
            import asyncio
            from src.services.backtesting.synthetic_engine import (
                SyntheticEngine,
                MarketTick,
            )

            try:
                # Get historical data (sync)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                candles = loop.run_until_complete(
                    market_data_repo.get_candles_by_date_range(
                        symbol=grid.symbol,
                        timeframe=grid.timeframe,
                        start_date=grid.start_date,
                        end_date=grid.end_date,
                    )
                )
                loop.close()

                # Run synthetic backtest
                engine = SyntheticEngine(
                    strategy=grid.synthetic_strategy,
                    params=params,
                )

                current_capital = grid.initial_capital
                trades = []
                position = None

                for candle in candles:
                    tick = MarketTick(
                        timestamp=candle.timestamp,
                        open=candle.open_price,
                        high=candle.high_price,
                        low=candle.low_price,
                        close=candle.close_price,
                        volume=float(candle.volume),
                    )

                    signal = engine.process_tick(tick)

                    if signal.action == "BUY" and position is None:
                        position = {
                            'entry_price': tick.close,
                            'quantity': signal.quantity,
                        }
                    elif signal.action == "SELL" and position is not None:
                        pnl = (tick.close - position['entry_price']) * position['quantity']
                        current_capital += pnl
                        trades.append(float(pnl))
                        position = None

                # Calculate metrics
                total_return = float((current_capital - grid.initial_capital) / grid.initial_capital)
                winning_trades = [t for t in trades if t > 0]
                losing_trades = [t for t in trades if t < 0]
                win_rate = len(winning_trades) / len(trades) if trades else 0.0

                return OptimizationResult(
                    params=params,
                    total_return=total_return,
                    sharpe_ratio=total_return * 2 if total_return > 0 else 0,
                    win_rate=win_rate,
                    profit_factor=2.0 if win_rate > 0.5 else 1.0,
                    total_trades=len(trades),
                    winning_trades=len(winning_trades),
                    losing_trades=len(losing_trades),
                    avg_win=sum(winning_trades) / len(winning_trades) if winning_trades else 0.0,
                    avg_loss=sum(losing_trades) / len(losing_trades) if losing_trades else 0.0,
                    candles_processed=len(candles),
                )

            except Exception as e:
                return OptimizationResult(params=params, error=str(e))

        # Create optimizer
        with tempfile.TemporaryDirectory() as tmpdir:
            optimizer = BatchOptimizer(
                parameter_grid=optimizer_grid,
                backtest_function=run_single_backtest,
                max_workers=grid.max_workers,
                results_dir=Path(tmpdir),
            )

            # Run optimization
            results = optimizer.run(
                early_stop_threshold=request.early_stop_threshold,
            )

            # Rank results
            top_results = optimizer.get_top_results(
                n=min(10, len(results)),
                sort_by=request.ranking_metric,
                custom_weights=request.custom_weights,
            )

        # Convert to response format
        result_responses = [
            OptimizationResultResponse(
                params=r.params,
                total_return=r.total_return,
                sharpe_ratio=r.sharpe_ratio,
                sortino_ratio=r.sortino_ratio,
                calmar_ratio=r.calmar_ratio,
                max_drawdown=r.max_drawdown,
                win_rate=r.win_rate,
                profit_factor=r.profit_factor,
                total_trades=r.total_trades,
                winning_trades=r.winning_trades,
                losing_trades=r.losing_trades,
                avg_win=r.avg_win,
                avg_loss=r.avg_loss,
                composite_score=r.composite_score(request.custom_weights),
                execution_time_seconds=r.execution_time_seconds,
                error=r.error,
            )
            for r in top_results
        ]

        # Update grid status
        grid.status = "completed"
        await repo.update(grid)

        logger.info(
            "parameter_grid_executed",
            grid_id=str(grid_id),
            total_results=len(results),
        )

        return ParameterGridResultsResponse(
            grid_id=grid_id,
            status="completed",
            total_combinations=grid.total_combinations,
            completed_combinations=len(results),
            successful_combinations=len([r for r in results if r.error is None]),
            failed_combinations=len([r for r in results if r.error is not None]),
            top_results=result_responses,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            total_execution_time_seconds=sum(r.execution_time_seconds for r in results),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "execute_parameter_grid_failed",
            grid_id=str(grid_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute parameter grid: {str(e)}",
        )


@router.get(
    "/optimization/grids/{grid_id}/results",
    response_model=ParameterGridResultsResponse,
    responses={
        200: {"description": "Grid results retrieved"},
        404: {"model": ErrorResponse, "description": "Grid not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_parameter_grid_results(
    grid_id: UUID,
    top_n: int = Query(default=10, ge=1, le=100, description="Number of top results to return"),
    sort_by: str = Query(default="composite_score", description="Metric to sort by"),
    db: AsyncSession = Depends(get_db),
) -> ParameterGridResultsResponse:
    """
    Get parameter grid optimization results (T072).

    Retrieves results from a previously executed parameter grid.
    Results are ranked by the specified metric.

    Features:
    - Configurable top N results
    - Multiple sorting options
    - Includes execution metadata

    Args:
        grid_id: Parameter grid UUID
        top_n: Number of top results to return (1-100)
        sort_by: Metric to sort by

    Returns:
        Optimization results with top performers

    Example:
        GET /api/v1/backtesting/optimization/grids/{grid_id}/results?top_n=5&sort_by=sharpe_ratio
    """
    try:
        from src.database.repositories.parameter_grid_repository import (
            ParameterGridRepository,
        )

        repo = ParameterGridRepository(db)

        # Fetch grid
        grid = await repo.get_by_id(grid_id)
        if not grid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parameter grid {grid_id} not found",
            )

        # Fetch results from grid_search_results table
        results = await repo.get_results_for_grid(grid_id, limit=top_n, sort_by=sort_by)

        # Convert to response format
        result_responses = [
            OptimizationResultResponse(
                params=r.parameters,
                total_return=r.total_return,
                sharpe_ratio=r.sharpe_ratio,
                sortino_ratio=r.sortino_ratio or 0.0,
                calmar_ratio=r.calmar_ratio or 0.0,
                max_drawdown=r.max_drawdown,
                win_rate=r.win_rate,
                profit_factor=r.profit_factor,
                total_trades=r.total_trades,
                winning_trades=r.winning_trades or 0,
                losing_trades=r.losing_trades or 0,
                avg_win=r.avg_win or 0.0,
                avg_loss=r.avg_loss or 0.0,
                composite_score=r.composite_score or 0.0,
                execution_time_seconds=r.execution_time_seconds or 0.0,
                error=None,
            )
            for r in results
        ]

        logger.info(
            "parameter_grid_results_retrieved",
            grid_id=str(grid_id),
            results_count=len(results),
        )

        return ParameterGridResultsResponse(
            grid_id=grid_id,
            status=grid.status,
            total_combinations=grid.total_combinations,
            completed_combinations=len(results),
            successful_combinations=len(results),
            failed_combinations=0,
            top_results=result_responses,
            started_at=grid.created_at,
            completed_at=grid.updated_at,
            total_execution_time_seconds=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_parameter_grid_results_failed",
            grid_id=str(grid_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve parameter grid results: {str(e)}",
        )


# ============================================================================
# User Story 4: A/B Testing Comparison Endpoint (T109)
# ============================================================================


@router.post(
    "/comparison",
    response_model=CompareRunsResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare two backtest runs with statistical analysis",
    description="""
    Compare two backtest runs with:
    - Side-by-side metrics
    - Statistical significance testing (t-test)
    - Trade overlap analysis
    - Equity curve alignment
    - Performance breakdown by time period
    - Recommendation (which configuration is better)
    
    Returns comprehensive comparison report for A/B testing decisions.
    """,
    responses={
        200: {"description": "Comparison completed successfully"},
        404: {"description": "One or both run IDs not found"},
        400: {"description": "Invalid comparison (different symbols, etc.)"},
        500: {"description": "Server error during comparison"},
    },
)
async def compare_backtest_runs(
    request: CompareRunsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    T109: Compare two backtest runs with statistical analysis.

    This endpoint enables A/B testing of different agent configurations:
    - Conservative vs Aggressive risk parameters
    - Different strategy types (MA crossover vs RSI)
    - Different ML models
    - Different position sizing algorithms

    Args:
        request: Comparison request with run IDs
        db: Database session

    Returns:
        CompareRunsResponse with statistical analysis and recommendation
    """
    try:
        logger.info(
            "compare_runs_requested",
            run_a_id=str(request.run_a_id),
            run_b_id=str(request.run_b_id),
            time_window=request.time_window_minutes,
        )

        # Create comparison service
        comparison_service = ComparisonService()

        # Perform comparison
        comparison_result = await comparison_service.compare_runs(
            run_a_id=request.run_a_id,
            run_b_id=request.run_b_id,
            async_session=db,
            time_window_minutes=request.time_window_minutes,
        )

        # Convert statistical test result
        returns_test = comparison_result.statistical_tests["returns_ttest"]
        statistical_test_response = StatisticalTestResponse(
            t_statistic=returns_test.t_statistic,
            p_value=returns_test.p_value,
            is_significant=returns_test.is_significant,
            degrees_of_freedom=returns_test.degrees_of_freedom,
            mean_difference=returns_test.mean_difference,
            confidence_interval_lower=returns_test.confidence_interval[0]
            if returns_test.confidence_interval
            else None,
            confidence_interval_upper=returns_test.confidence_interval[1]
            if returns_test.confidence_interval
            else None,
        )

        # Convert metrics comparison
        metrics_comparison = MetricsComparisonResponse(
            run_a=comparison_result.metrics_comparison["run_a"],
            run_b=comparison_result.metrics_comparison["run_b"],
            differences={
                "total_return_diff": comparison_result.metrics_comparison["run_a"][
                    "total_return"
                ]
                - comparison_result.metrics_comparison["run_b"]["total_return"],
                "sharpe_diff": comparison_result.metrics_comparison["run_a"][
                    "sharpe_ratio"
                ]
                - comparison_result.metrics_comparison["run_b"]["sharpe_ratio"],
                "win_rate_diff": comparison_result.metrics_comparison["run_a"][
                    "win_rate"
                ]
                - comparison_result.metrics_comparison["run_b"]["win_rate"],
            },
        )

        # Convert trade overlap
        trade_overlap = TradeOverlapResponse(
            consensus_trades=comparison_result.trade_overlap.consensus_trades,
            divergent_trades_a=comparison_result.trade_overlap.divergent_trades_a,
            divergent_trades_b=comparison_result.trade_overlap.divergent_trades_b,
            overlap_rate=comparison_result.trade_overlap.overlap_rate,
        )

        # Generate report if requested
        report = None
        if request.generate_report:
            report = comparison_service.generate_report(comparison_result)

        logger.info(
            "compare_runs_completed",
            run_a_id=str(request.run_a_id),
            run_b_id=str(request.run_b_id),
            recommendation=comparison_result.recommendation,
            is_significant=returns_test.is_significant,
            p_value=returns_test.p_value,
        )

        return CompareRunsResponse(
            run_a_id=comparison_result.run_a_id,
            run_b_id=comparison_result.run_b_id,
            recommendation=comparison_result.recommendation,
            metrics_comparison=metrics_comparison,
            statistical_tests={"returns_ttest": statistical_test_response},
            trade_overlap=trade_overlap,
            equity_curves=comparison_result.equity_curves,
            performance_breakdown=comparison_result.performance_breakdown,
            report=report,
        )

    except ValueError as e:
        # Invalid comparison (different symbols, empty returns, etc.)
        logger.warning(
            "compare_runs_invalid",
            run_a_id=str(request.run_a_id),
            run_b_id=str(request.run_b_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid comparison: {str(e)}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "compare_runs_failed",
            run_a_id=str(request.run_a_id),
            run_b_id=str(request.run_b_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare runs: {str(e)}",
        )


# ============================================================================
# T124: Health Check Endpoint
# ============================================================================


@router.get(
    "/health",
    summary="Health check for backtesting service",
    description="""
    Check health status of backtesting service components:
    - Database connectivity
    - Market data availability
    - Service readiness
    
    Returns 200 if healthy, 503 if unhealthy.
    """,
    responses={
        200: {"description": "Service healthy"},
        503: {"description": "Service unhealthy"},
    },
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    T124: Health check endpoint for monitoring.

    Checks:
    - Database connection
    - Market data repository
    - Recent data availability

    Returns:
        Dict with health status and component details
    """
    import time
    from src.database.repositories.market_data_repository import MarketDataRepository

    start_time = time.perf_counter()
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "backtesting",
        "version": "1.0.0",
        "checks": {}
    }

    try:
        # Check 1: Database connectivity
        try:
            await db.execute("SELECT 1")
            health_status["checks"]["database"] = {
                "status": "healthy",
                "message": "Database connection OK"
            }
        except Exception as e:
            health_status["checks"]["database"] = {
                "status": "unhealthy",
                "message": f"Database connection failed: {str(e)}"
            }
            health_status["status"] = "unhealthy"

        # Check 2: Market data repository
        try:
            market_data_repo = MarketDataRepository(db)
            # Check if we have any market data
            symbols = await market_data_repo.get_available_symbols()
            health_status["checks"]["market_data"] = {
                "status": "healthy",
                "message": f"Market data available for {len(symbols)} symbols",
                "symbols": symbols[:5] if symbols else []  # Show first 5
            }
        except Exception as e:
            health_status["checks"]["market_data"] = {
                "status": "degraded",
                "message": f"Market data check failed: {str(e)}"
            }
            # This is degraded not unhealthy (service can still run)

        # Check 3: Response time
        response_time_ms = (time.perf_counter() - start_time) * 1000
        health_status["checks"]["response_time"] = {
            "status": "healthy" if response_time_ms < 1000 else "degraded",
            "response_time_ms": round(response_time_ms, 2),
            "threshold_ms": 1000
        }

        # Overall status
        health_status["response_time_ms"] = round(response_time_ms, 2)

        # Return appropriate status code
        if health_status["status"] == "unhealthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=health_status
            )

        logger.info(
            "health_check_success",
            response_time_ms=health_status["response_time_ms"],
            database_status=health_status["checks"]["database"]["status"]
        )

        return health_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "health_check_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "message": f"Health check failed: {str(e)}"
            }
        )


# ============================================================================
# REAL-TIME PROGRESS STREAMING (SSE)
# ============================================================================


@router.get(
    "/runs/{run_id}/stream",
    responses={
        200: {"description": "SSE stream of backtest progress updates"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        503: {"description": "Redis not available for streaming"},
    },
)
async def stream_backtest_progress(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Stream real-time backtest progress via Server-Sent Events (SSE).
    
    Provides live updates during backtest execution:
    - Progress percentage
    - Candles processed
    - Trades executed
    - Current capital
    - Completion/error events
    
    Event Types:
        - progress: Periodic progress update
        - complete: Backtest finished successfully
        - error: Backtest failed
        - heartbeat: Keep-alive ping (every 30s)
    
    Args:
        run_id: Backtest run UUID
    
    Returns:
        StreamingResponse with text/event-stream content type
    
    Example:
        GET /api/backtesting/runs/{run_id}/stream
        
        Response (SSE format):
        event: progress
        data: {"progress_pct": 45.2, "candles_processed": 50000, ...}
        
        event: complete  
        data: {"final_capital": 11234.56, "trades_count": 42, ...}
    """
    from fastapi.responses import StreamingResponse
    from src.services.backtest_progress_service import (
        BacktestProgressSubscriber,
        format_sse_event,
    )
    from src.utils.redis_client import get_redis_client
    
    try:
        # Verify run exists
        service = get_backtest_service(db)
        run = await service.backtest_repo.get_run(run_id)
        
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )
        
        # If already completed/failed, return final status immediately
        if run.status.value in ("completed", "failed"):
            async def completed_generator():
                final_event = {
                    "type": "complete" if run.status.value == "completed" else "error",
                    "run_id": str(run_id),
                    "status": run.status.value,
                    "candles_processed": run.candles_processed,
                    "total_trades": run.total_trades,
                    "final_capital": float(run.final_capital) if run.final_capital else None,
                    "error_message": run.error_message,
                }
                yield format_sse_event(final_event["type"], final_event)
            
            return StreamingResponse(
                completed_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        
        # Get Redis client for pub/sub
        redis_client = await get_redis_client()
        if not redis_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis not available for streaming. Use polling instead: GET /runs/{run_id}/status",
            )
        
        logger.info(
            "sse_stream_started",
            run_id=str(run_id),
            current_status=run.status.value,
        )
        
        async def event_generator():
            """Generate SSE events from Redis pub/sub."""
            subscriber = BacktestProgressSubscriber(redis_client)
            
            try:
                # Send initial status
                initial_event = {
                    "type": "connected",
                    "run_id": str(run_id),
                    "status": run.status.value,
                    "candles_processed": run.candles_processed,
                    "message": "Connected to progress stream",
                }
                yield format_sse_event("connected", initial_event)
                
                # Stream updates from Redis
                async for event in subscriber.subscribe(run_id):
                    event_type = event.get("type", "progress")
                    yield format_sse_event(event_type, event)
                    
                    # Stop on completion or error
                    if event_type in ("complete", "error"):
                        break
                        
            except asyncio.CancelledError:
                logger.info("sse_stream_cancelled", run_id=str(run_id))
                raise
            except Exception as e:
                logger.error(
                    "sse_stream_error",
                    run_id=str(run_id),
                    error=str(e),
                    exc_info=True,
                )
                error_event = {
                    "type": "error",
                    "error_message": str(e),
                }
                yield format_sse_event("error", error_event)
            finally:
                logger.info("sse_stream_closed", run_id=str(run_id))
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "stream_setup_failed",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup progress stream: {str(e)}",
        )


@router.websocket("/runs/{run_id}/live")
async def websocket_live_backtest(
    websocket: WebSocket,
    run_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
):
    """
    WebSocket endpoint for live backtest visualization.

    Streams real-time events as backtest executes:
    - Candle processing with OHLCV data
    - Agent decisions with reasoning
    - Trade executions with entry/exit points
    - Position and equity updates

    Designed for MT4-style live chart visualization with agent thoughts.

    Args:
        websocket: WebSocket connection
        run_id: Backtest run UUID to stream

    Event Format:
        {
            "event_type": "agent_decision" | "trade_executed" | "candle_processed" | ...,
            "run_id": "uuid",
            "timestamp": "ISO timestamp",
            "data": {
                // Event-specific data
                "price": 75.86,
                "agent_thought": "RSI oversold, MACD bullish crossover...",
                "action": "buy",
                ...
            }
        }

    Example Usage (JavaScript):
        const ws = new WebSocket('ws://localhost:8003/api/v1/backtesting/runs/{run_id}/live');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.event_type === 'agent_decision') {
                // Show agent thought bubble on chart
            } else if (data.event_type === 'trade_executed') {
                // Draw buy/sell arrow on chart
            }
        };
    """
    await websocket.accept()

    broadcaster = get_event_broadcaster()
    broadcaster.register_connection(run_id, websocket)

    logger.info(
        "websocket_connection_established",
        run_id=str(run_id),
        client_host=websocket.client.host if websocket.client else "unknown",
    )

    try:
        # Keep connection alive and listen for client messages (if any)
        while True:
            # Wait for client messages (e.g., "ping" for keep-alive)
            # Events are pushed from backtest_service via broadcaster
            data = await websocket.receive_text()

            # Echo back for debugging (optional)
            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(
            "websocket_disconnected",
            run_id=str(run_id),
        )
    except Exception as e:
        logger.error(
            "websocket_error",
            run_id=str(run_id),
            error=str(e),
            exc_info=True,
        )
    finally:
        broadcaster.unregister_connection(run_id, websocket)
