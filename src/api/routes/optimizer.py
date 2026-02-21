"""
Optimizer API Routes

Endpoints for running strategy optimization similar to MetaTrader.
Includes both synchronous endpoints and async job queue endpoints.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.services.backtesting.optimizer import (
    StrategyOptimizer,
    OptimizationSummary,
)
from src.services.optimization_job_service import OptimizationJobService
from src.utils.grid_search import GridSizeExceededError

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/optimizer", tags=["optimizer"])


# =============================================================================
# Request/Response Models
# =============================================================================

class OptimizationRequest(BaseModel):
    """Request to run optimization."""
    
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Candle timeframe")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    strategy: str = Field(..., description="Strategy name")
    param_grid: Optional[Dict[str, List[Any]]] = Field(
        default=None,
        description="Parameter grid to search (None = use defaults)"
    )
    optimization_target: str = Field(
        default="sharpe_ratio",
        description="Metric to optimize: sharpe_ratio, total_return_pct, profit_factor, risk_adjusted_return"
    )
    initial_capital: float = Field(default=10000.0)
    max_combinations: Optional[int] = Field(
        default=None,
        description="Limit combinations for random search"
    )
    min_trades: int = Field(default=10, description="Minimum trades for valid result")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "timeframe": "M5",
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "strategy": "crude_oil_v3",
                "param_grid": {
                    "ema_fast": [5, 8, 10, 12],
                    "ema_slow": [20, 25, 29, 35],
                    "rsi_oversold": [25, 30, 35],
                    "use_time_filter": [True, False]
                },
                "optimization_target": "sharpe_ratio",
                "max_combinations": 100
            }
        }


class QuickScanRequest(BaseModel):
    """Request for quick random search."""
    
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    strategy: str
    num_samples: int = Field(default=100, description="Number of random samples")
    initial_capital: float = Field(default=10000.0)


class WalkForwardRequest(BaseModel):
    """Request for walk-forward optimization."""
    
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    strategy: str
    param_grid: Optional[Dict[str, List[Any]]] = None
    optimization_target: str = Field(default="sharpe_ratio")
    train_pct: float = Field(default=0.7, description="Training percentage (0-1)")
    num_folds: int = Field(default=4, description="Number of walk-forward folds")
    initial_capital: float = Field(default=10000.0)


class OptimizationResponse(BaseModel):
    """Response from optimization."""
    
    success: bool
    optimization_id: str
    strategy: str
    symbol: str
    timeframe: str
    
    # Search space
    total_combinations: int
    combinations_tested: int
    
    # Best result
    best_params: Dict[str, Any]
    best_return_pct: float
    best_sharpe: float
    best_profit_factor: float
    
    # Timing
    total_time_seconds: float
    avg_time_per_test_ms: float
    
    # Top results
    top_results: List[Dict[str, Any]]


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/run",
    response_model=OptimizationResponse,
    summary="Run grid search optimization",
    description="""
    Run MetaTrader-style parameter optimization.
    
    **Process:**
    1. Generates all parameter combinations from grid
    2. Runs backtest for each combination
    3. Ranks results by optimization target
    4. Returns best parameters and top results
    
    **Optimization Targets:**
    - `sharpe_ratio`: Risk-adjusted returns (recommended)
    - `total_return_pct`: Raw returns
    - `profit_factor`: Gross profit / gross loss
    - `risk_adjusted_return`: Return / max drawdown
    - `win_rate`: Percentage of winning trades
    
    **Performance:**
    - 100 combinations: ~30-60 seconds
    - 500 combinations: ~2-5 minutes
    - 1000+ combinations: Use quick_scan first
    """,
)
async def run_optimization(
    request: OptimizationRequest,
    db: AsyncSession = Depends(get_db),
) -> OptimizationResponse:
    """Run grid search optimization."""
    try:
        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        # Run optimization
        optimizer = StrategyOptimizer(db)
        result = await optimizer.optimize(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            param_grid=request.param_grid,
            optimization_target=request.optimization_target,
            initial_capital=request.initial_capital,
            max_combinations=request.max_combinations,
            min_trades=request.min_trades,
        )
        
        return OptimizationResponse(
            success=True,
            optimization_id=result.optimization_id,
            strategy=result.strategy,
            symbol=result.symbol,
            timeframe=result.timeframe,
            total_combinations=result.total_combinations,
            combinations_tested=result.combinations_tested,
            best_params=result.best_params,
            best_return_pct=result.best_return_pct,
            best_sharpe=result.best_sharpe,
            best_profit_factor=result.best_profit_factor,
            total_time_seconds=result.total_time_seconds,
            avg_time_per_test_ms=result.avg_time_per_test_ms,
            top_results=[r.to_dict() for r in result.all_results[:20]],
        )
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/quick-scan",
    response_model=OptimizationResponse,
    summary="Quick random search (faster)",
    description="""
    Fast random search for initial parameter exploration.
    
    Randomly samples from the default parameter grid.
    Good for quickly finding promising parameter ranges
    before running full grid search.
    
    **Recommended workflow:**
    1. Run quick_scan with 50-100 samples
    2. Identify promising parameter ranges
    3. Run full optimization with narrowed grid
    """,
)
async def quick_scan(
    request: QuickScanRequest,
    db: AsyncSession = Depends(get_db),
) -> OptimizationResponse:
    """Run quick random search."""
    try:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        optimizer = StrategyOptimizer(db)
        result = await optimizer.quick_scan(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            num_samples=request.num_samples,
            initial_capital=request.initial_capital,
        )
        
        return OptimizationResponse(
            success=True,
            optimization_id=result.optimization_id,
            strategy=result.strategy,
            symbol=result.symbol,
            timeframe=result.timeframe,
            total_combinations=result.total_combinations,
            combinations_tested=result.combinations_tested,
            best_params=result.best_params,
            best_return_pct=result.best_return_pct,
            best_sharpe=result.best_sharpe,
            best_profit_factor=result.best_profit_factor,
            total_time_seconds=result.total_time_seconds,
            avg_time_per_test_ms=result.avg_time_per_test_ms,
            top_results=[r.to_dict() for r in result.all_results[:20]],
        )
        
    except Exception as e:
        logger.error(f"Quick scan failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/walk-forward",
    summary="Walk-forward optimization (robustness test)",
    description="""
    Walk-forward optimization to test strategy robustness.
    
    **Process:**
    1. Splits data into multiple folds
    2. For each fold: optimize on training, test on validation
    3. Compares in-sample vs out-of-sample performance
    4. Calculates robustness ratio
    
    **Interpretation:**
    - Robustness > 0.7: Safe to deploy
    - Robustness 0.5-0.7: Use with caution
    - Robustness < 0.5: Overfitting detected
    
    **Note:** Takes longer than regular optimization.
    """,
)
async def walk_forward_optimization(
    request: WalkForwardRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Run walk-forward optimization."""
    try:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        optimizer = StrategyOptimizer(db)
        result = await optimizer.walk_forward_optimize(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            param_grid=request.param_grid,
            optimization_target=request.optimization_target,
            train_pct=request.train_pct,
            num_folds=request.num_folds,
            initial_capital=request.initial_capital,
        )
        
        return {"success": True, **result}
        
    except Exception as e:
        logger.error(f"Walk-forward optimization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/param-grids/{strategy}",
    summary="Get default parameter grid for strategy",
)
async def get_param_grid(strategy: str) -> Dict[str, Any]:
    """Get default parameter grid for a strategy."""
    grids = StrategyOptimizer.DEFAULT_PARAM_GRIDS
    
    if strategy not in grids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown strategy: {strategy}. Available: {list(grids.keys())}"
        )
    
    return {
        "strategy": strategy,
        "param_grid": grids[strategy],
        "total_combinations": _calculate_combinations(grids[strategy]),
    }


@router.get(
    "/strategies",
    summary="List available strategies and their parameters",
)
async def list_strategies() -> Dict[str, Any]:
    """List all available strategies with their parameter grids."""
    grids = StrategyOptimizer.DEFAULT_PARAM_GRIDS
    
    strategies = []
    for name, grid in grids.items():
        strategies.append({
            "name": name,
            "parameters": list(grid.keys()),
            "total_combinations": _calculate_combinations(grid),
        })
    
    return {
        "strategies": strategies,
        "optimization_targets": StrategyOptimizer.OPTIMIZATION_TARGETS,
    }


def _calculate_combinations(param_grid: Dict[str, List]) -> int:
    """Calculate total combinations in parameter grid."""
    total = 1
    for values in param_grid.values():
        total *= len(values)
    return total


# =============================================================================
# Async Job Queue Endpoints (Feature 008)
# =============================================================================

class AsyncOptimizationRequest(BaseModel):
    """Request to submit async optimization job."""

    strategy: str = Field(..., description="Strategy name")
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Candle timeframe")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    param_grid: Optional[Dict[str, List[Any]]] = Field(
        default=None,
        description="Parameter grid to search (None = use defaults)"
    )
    optimization_target: str = Field(
        default="sharpe_ratio",
        description="Metric to optimize"
    )
    initial_capital: float = Field(default=10000.0)

    class Config:
        json_schema_extra = {
            "example": {
                "strategy": "crude_oil_v3",
                "symbol": "CrudeOIL",
                "timeframe": "H1",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "param_grid": {
                    "ema_fast": [5, 10, 15],
                    "ema_slow": [20, 30, 40],
                },
                "optimization_target": "sharpe_ratio",
            }
        }


class JobSubmittedResponse(BaseModel):
    """Response when job is submitted."""

    job_id: str
    status: str
    total_combinations: int
    estimated_duration_minutes: Optional[float] = None


class JobStatusResponse(BaseModel):
    """Response for job status query."""

    job_id: str
    status: str
    strategy: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    progress_pct: float = 0
    combinations_tested: int = 0
    total_combinations: int = 0
    best_params: Optional[Dict[str, Any]] = None
    best_metric_value: Optional[float] = None
    current_params: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    error_message: Optional[str] = None


class JobCancelledResponse(BaseModel):
    """Response when job is cancelled."""

    job_id: str
    status: str
    combinations_tested: int


@router.post(
    "/jobs",
    response_model=JobSubmittedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit async optimization job",
    description="""
    Starts a new optimization job asynchronously.

    Returns immediately with job_id for tracking.
    Use GET /jobs/{job_id} to poll for progress.
    Use SSE /events/stream for real-time updates.

    **Max Grid Size:** 10,000 combinations
    """,
)
async def submit_optimization_job(
    request: AsyncOptimizationRequest,
    db: AsyncSession = Depends(get_db),
) -> JobSubmittedResponse:
    """Submit a new async optimization job."""
    try:
        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")

        # Get param grid (use defaults if not provided)
        param_grid = request.param_grid
        if param_grid is None:
            grids = StrategyOptimizer.DEFAULT_PARAM_GRIDS
            if request.strategy not in grids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown strategy: {request.strategy}"
                )
            param_grid = grids[request.strategy]

        # Submit job
        job_service = OptimizationJobService(db)
        result = await job_service.submit_job(
            strategy=request.strategy,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            param_grid=param_grid,
            optimization_target=request.optimization_target,
            initial_capital=request.initial_capital,
        )

        return JobSubmittedResponse(**result)

    except GridSizeExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Job submission failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/jobs",
    summary="List optimization jobs",
    description="List all active and recent optimization jobs.",
)
async def list_optimization_jobs(
    status_filter: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all active jobs."""
    try:
        job_service = OptimizationJobService(db)
        jobs = await job_service.list_active_jobs(status_filter=status_filter)
        return jobs[:limit]
    except Exception as e:
        logger.error(f"List jobs failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Get current status and progress of an optimization job.",
)
async def get_optimization_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobStatusResponse:
    """Get job status and details."""
    try:
        job_service = OptimizationJobService(db)
        status_data = await job_service.get_job_status(job_id)

        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}"
            )

        return JobStatusResponse(**status_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get job status failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete(
    "/jobs/{job_id}",
    response_model=JobCancelledResponse,
    summary="Cancel optimization job",
    description="Cancel a running or pending optimization job.",
)
async def cancel_optimization_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCancelledResponse:
    """Cancel a running job."""
    try:
        job_service = OptimizationJobService(db)
        result = await job_service.cancel_job(job_id)
        return JobCancelledResponse(**result)

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
    except Exception as e:
        logger.error(f"Cancel job failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/jobs/{job_id}/results",
    summary="Get optimization results",
    description="Get full results for a completed optimization job.",
)
async def get_optimization_results(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get full results for a completed job."""
    try:
        job_service = OptimizationJobService(db)
        results = await job_service.get_job_results(job_id)

        if results is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}"
            )

        return results

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get results failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# Enhanced Optimization Endpoints
# =============================================================================

class RollingWindowRequest(BaseModel):
    """Request for rolling window optimization."""
    
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    strategy: str
    param_grid: Optional[Dict[str, List[Any]]] = None
    optimization_target: str = Field(default="sharpe_ratio")
    train_months: int = Field(default=3, description="Months for training window")
    test_months: int = Field(default=1, description="Months for testing window")
    step_months: int = Field(default=1, description="Months to step forward")
    initial_capital: float = Field(default=10000.0)
    max_combinations: int = Field(default=100)


class TimeIntervalRequest(BaseModel):
    """Request for time-interval specific optimization."""
    
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    strategy: str
    intervals: List[Dict[str, str]] = Field(
        ...,
        description="List of intervals: [{name, start_date, end_date}, ...]"
    )
    param_grid: Optional[Dict[str, List[Any]]] = None
    optimization_target: str = Field(default="sharpe_ratio")
    initial_capital: float = Field(default=10000.0)
    max_combinations: int = Field(default=100)


class SensitivityRequest(BaseModel):
    """Request for sensitivity analysis."""
    
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    strategy: str
    base_params: Optional[Dict[str, Any]] = None
    initial_capital: float = Field(default=10000.0)


class MonteCarloRequest(BaseModel):
    """Request for Monte Carlo validation."""
    
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    strategy: str
    params: Dict[str, Any]
    num_simulations: int = Field(default=100)
    initial_capital: float = Field(default=10000.0)


@router.post(
    "/rolling-window",
    summary="Rolling window optimization",
    description="""
    Re-optimizes parameters at regular intervals using recent data.
    
    Simulates real-world trading where you periodically re-calibrate.
    
    **Process:**
    1. Train on [t-train_months, t]
    2. Test on [t, t+test_months]
    3. Step forward by step_months
    4. Repeat until end of data
    
    **Metrics:**
    - Cumulative capital tracks actual compounded growth
    - Robustness ratio = % of windows with positive returns
    """,
)
async def rolling_window_optimization(
    request: RollingWindowRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Run rolling window optimization."""
    try:
        from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
        
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        optimizer = EnhancedOptimizer(db)
        result = await optimizer.rolling_window_optimize(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            param_grid=request.param_grid,
            optimization_target=request.optimization_target,
            train_months=request.train_months,
            test_months=request.test_months,
            step_months=request.step_months,
            initial_capital=request.initial_capital,
            max_combinations=request.max_combinations,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Rolling window optimization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/time-intervals",
    summary="Time-interval specific optimization",
    description="""
    Optimizes parameters for specific time periods.
    
    Useful for:
    - Quarterly re-optimization
    - Seasonal analysis
    - Regime-specific parameters
    
    Returns optimal parameters for each interval plus
    analysis of parameter stability across periods.
    """,
)
async def time_interval_optimization(
    request: TimeIntervalRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Run time-interval optimization."""
    try:
        from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
        
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        optimizer = EnhancedOptimizer(db)
        result = await optimizer.time_interval_optimize(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            intervals=request.intervals,
            param_grid=request.param_grid,
            optimization_target=request.optimization_target,
            initial_capital=request.initial_capital,
            max_combinations=request.max_combinations,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Time interval optimization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/sensitivity",
    summary="Parameter sensitivity analysis",
    description="""
    Analyzes how each parameter affects strategy performance.
    
    Returns:
    - Sensitivity ranking (which params matter most)
    - Performance curves for each parameter
    - Optimal values for each parameter
    """,
)
async def sensitivity_analysis(
    request: SensitivityRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Run sensitivity analysis on all parameters."""
    try:
        from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
        
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        optimizer = EnhancedOptimizer(db)
        result = await optimizer.full_sensitivity_analysis(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            base_params=request.base_params,
            initial_capital=request.initial_capital,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Sensitivity analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/monte-carlo",
    summary="Monte Carlo validation",
    description="""
    Validates strategy with Monte Carlo simulation.
    
    Shuffles trade order many times to estimate:
    - Distribution of possible outcomes
    - How much performance is due to luck
    - Confidence intervals for returns
    
    **Interpretation:**
    - If actual return is above 75th percentile: "Lucky"
    - If actual return is below 25th percentile: "Unlucky"
    - Otherwise: "Typical" - results are not due to unusual luck
    """,
)
async def monte_carlo_validation(
    request: MonteCarloRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Run Monte Carlo validation."""
    try:
        from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
        
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        optimizer = EnhancedOptimizer(db)
        result = await optimizer.monte_carlo_validate(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            params=request.params,
            num_simulations=request.num_simulations,
            initial_capital=request.initial_capital,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Monte Carlo validation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# HISTORY ENDPOINTS (User Story 3)
# =============================================================================


class HistoryListResponse(BaseModel):
    """Response model for listing optimization history."""
    runs: List[Dict[str, Any]]
    total: int
    page: int
    per_page: int


@router.get(
    "/history",
    summary="List optimization history",
    description="""
    List all saved optimization runs from the database.
    
    **Filters:**
    - `strategy`: Filter by strategy name
    - `symbol`: Filter by trading symbol
    - `status`: Filter by status (completed, failed, cancelled)
    
    **Pagination:**
    - `page`: Page number (1-indexed)
    - `per_page`: Items per page (max 100)
    """,
)
async def list_optimization_history(
    strategy: Optional[str] = Query(None, description="Filter by strategy"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List optimization history from database."""
    try:
        from src.database.repositories.optimization_repository import OptimizationRepository
        
        repo = OptimizationRepository(db)
        offset = (page - 1) * per_page
        
        runs = await repo.list_runs(
            strategy=strategy,
            symbol=symbol,
            status=status,
            limit=per_page,
            offset=offset,
        )
        
        return {
            "runs": [run.to_dict() for run in runs],
            "total": len(runs),  # TODO: Add count query for proper pagination
            "page": page,
            "per_page": per_page,
        }
        
    except Exception as e:
        logger.error(f"Failed to list optimization history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/history/{run_id}",
    summary="Get optimization run details",
    description="""
    Get full details for a specific optimization run.
    
    Includes:
    - Configuration (strategy, symbol, timeframe, dates)
    - Parameter grid used
    - All tested combinations with results
    - Best parameters and metrics
    """,
)
async def get_optimization_run(
    run_id: str = Path(..., description="Optimization run UUID"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get optimization run details by ID."""
    try:
        from uuid import UUID
        from src.database.repositories.optimization_repository import OptimizationRepository
        
        repo = OptimizationRepository(db)
        run = await repo.get_run_with_results(UUID(run_id))
        
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Optimization run not found: {run_id}"
            )
        
        result = run.to_dict()
        # Include full results if available
        if run.results:
            result["all_results"] = run.results.get("all_results", [])
        
        return result
        
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {run_id}"
        )
    except Exception as e:
        logger.error(f"Failed to get optimization run: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
