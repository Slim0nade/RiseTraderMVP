"""
Async optimization job service.

Provides job queue management for long-running strategy optimizations:
- Submit jobs asynchronously (returns immediately with job_id)
- Track job progress via Redis
- Run optimization in background workers
- Cancel running jobs
- Persist completed results to database
"""

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.optimization import OptimizationRun, OptimizationStatus
from src.utils.grid_search import (
    generate_grid_combinations,
    calculate_grid_size,
    validate_grid_size,
    GridSizeExceededError,
    MAX_COMBINATIONS,
)
from src.utils.redis_client import (
    get_redis_client,
    get_optimization_job_key,
    get_optimization_jobs_list_key,
)
from src.utils.sse_events import get_sse_manager

logger = structlog.get_logger(__name__)

# Job TTL in Redis (24 hours)
JOB_TTL_SECONDS = 86400

# Progress update frequency (every N combinations or N%)
PROGRESS_UPDATE_INTERVAL = 5  # percentage


class OptimizationJobService:
    """
    Service for managing async optimization jobs.

    Handles the full job lifecycle:
    1. Job submission with validation
    2. Background worker execution
    3. Progress tracking via Redis
    4. Result persistence to database
    5. Job cancellation
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the job service.

        Args:
            db_session: SQLAlchemy async session for database operations
        """
        self.db = db_session
        self._running_jobs: Dict[str, asyncio.Task] = {}
        self._cancelled_jobs: set = set()

    async def submit_job(
        self,
        strategy: str,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        param_grid: Dict[str, List[Any]],
        optimization_target: str = "sharpe_ratio",
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Submit a new optimization job.

        Validates the parameter grid, creates job state in Redis,
        and starts a background worker. Returns immediately.

        Args:
            strategy: Strategy name (e.g., "crude_oil_v3")
            symbol: Trading symbol (e.g., "CrudeOIL")
            timeframe: Candle timeframe (e.g., "H1")
            start_date: Optimization period start
            end_date: Optimization period end
            param_grid: Parameter grid to search
            optimization_target: Metric to optimize
            initial_capital: Starting capital for backtests

        Returns:
            Dict with job_id, status, and total_combinations

        Raises:
            GridSizeExceededError: If grid exceeds MAX_COMBINATIONS
            ValueError: If parameters are invalid
        """
        # Validate grid size
        total_combinations = validate_grid_size(param_grid)

        # Generate job ID
        job_id = str(uuid4())

        # Get Redis client
        redis = await get_redis_client()
        if not redis:
            # Fallback to synchronous execution
            logger.warning(
                "redis_unavailable_falling_back_to_sync",
                strategy=strategy,
                symbol=symbol,
                total_combinations=total_combinations,
            )
            return await self._run_sync_optimization(
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                param_grid=param_grid,
                optimization_target=optimization_target,
                initial_capital=initial_capital,
                total_combinations=total_combinations,
            )

        # Create job state in Redis
        job_key = get_optimization_job_key(job_id)
        job_state = {
            "status": "pending",
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "param_grid": json.dumps(param_grid),
            "optimization_target": optimization_target,
            "initial_capital": str(initial_capital),
            "total_combinations": str(total_combinations),
            "combinations_tested": "0",
            "progress_pct": "0",
            "best_params": "",
            "best_metric": "",
            "current_params": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": "",
            "error": "",
        }

        # Store in Redis with TTL
        await redis.hset(job_key, mapping=job_state)
        await redis.expire(job_key, JOB_TTL_SECONDS)

        # Add to active jobs list
        await redis.sadd(get_optimization_jobs_list_key(), job_id)

        logger.info(
            "optimization_job_submitted",
            job_id=job_id,
            strategy=strategy,
            symbol=symbol,
            total_combinations=total_combinations,
        )

        # Start background worker
        task = asyncio.create_task(self._run_worker(job_id))
        self._running_jobs[job_id] = task

        return {
            "job_id": job_id,
            "status": "pending",
            "total_combinations": total_combinations,
            "estimated_duration_minutes": self._estimate_duration(total_combinations),
        }

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a job.

        Args:
            job_id: Job identifier

        Returns:
            Job status dict or None if not found
        """
        redis = await get_redis_client()
        if not redis:
            return None

        job_key = get_optimization_job_key(job_id)
        job_data = await redis.hgetall(job_key)

        if not job_data:
            return None

        # Parse numeric and JSON fields
        return {
            "job_id": job_id,
            "status": job_data.get("status", "unknown"),
            "strategy": job_data.get("strategy"),
            "symbol": job_data.get("symbol"),
            "timeframe": job_data.get("timeframe"),
            "start_date": job_data.get("start_date"),
            "end_date": job_data.get("end_date"),
            "optimization_target": job_data.get("optimization_target"),
            "progress_pct": float(job_data.get("progress_pct", "0")),
            "combinations_tested": int(job_data.get("combinations_tested", "0")),
            "total_combinations": int(job_data.get("total_combinations", "0")),
            "best_params": json.loads(job_data["best_params"]) if job_data.get("best_params") else None,
            "best_metric_value": float(job_data["best_metric"]) if job_data.get("best_metric") else None,
            "current_params": json.loads(job_data["current_params"]) if job_data.get("current_params") else None,
            "created_at": job_data.get("created_at"),
            "started_at": job_data.get("started_at") or None,
            "error_message": job_data.get("error") or None,
        }

    async def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel a running job.

        Args:
            job_id: Job identifier

        Returns:
            Cancellation result

        Raises:
            ValueError: If job not found or already completed
        """
        # Get current status
        status = await self.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job not found: {job_id}")

        if status["status"] in ["completed", "failed", "cancelled"]:
            raise ValueError(f"Job already {status['status']}: {job_id}")

        # Mark as cancelled
        self._cancelled_jobs.add(job_id)

        # Cancel the asyncio task if running
        if job_id in self._running_jobs:
            task = self._running_jobs[job_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._running_jobs[job_id]

        # Update Redis state
        redis = await get_redis_client()
        if redis:
            job_key = get_optimization_job_key(job_id)
            await redis.hset(job_key, "status", "cancelled")

        # Emit SSE event
        sse_manager = await get_sse_manager()
        await sse_manager.emit_job_cancelled(job_id)

        logger.info(
            "optimization_job_cancelled",
            job_id=job_id,
            combinations_tested=status["combinations_tested"],
        )

        return {
            "job_id": job_id,
            "status": "cancelled",
            "combinations_tested": status["combinations_tested"],
        }

    async def list_active_jobs(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all active jobs.

        Args:
            status_filter: Optional status to filter by

        Returns:
            List of job summaries
        """
        redis = await get_redis_client()
        if not redis:
            return []

        # Get all job IDs from the active set
        job_ids = await redis.smembers(get_optimization_jobs_list_key())
        if not job_ids:
            return []

        jobs = []
        for job_id in job_ids:
            status = await self.get_job_status(job_id)
            if status:
                if status_filter is None or status["status"] == status_filter:
                    jobs.append({
                        "job_id": job_id,
                        "strategy": status["strategy"],
                        "symbol": status["symbol"],
                        "status": status["status"],
                        "progress_pct": status["progress_pct"],
                        "created_at": status["created_at"],
                    })

        # Sort by creation time (newest first)
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs

    async def get_job_results(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full results for a completed job.

        Args:
            job_id: Job identifier

        Returns:
            Full results dict or None

        Raises:
            ValueError: If job not completed
        """
        status = await self.get_job_status(job_id)
        if not status:
            return None

        if status["status"] != "completed":
            raise ValueError(f"Job not yet completed (status: {status['status']})")

        # Get results from Redis
        redis = await get_redis_client()
        if not redis:
            return None

        job_key = get_optimization_job_key(job_id)
        results_json = await redis.hget(job_key, "results")

        if not results_json:
            # Try to get from database
            return await self._get_results_from_db(job_id)

        results = json.loads(results_json)
        return {
            "job_id": job_id,
            "best_params": status["best_params"],
            "best_metric_value": status["best_metric_value"],
            "all_results": results.get("all_results", []),
            "summary": {
                "total_combinations": status["total_combinations"],
                "duration_seconds": results.get("duration_seconds", 0),
                "strategy": status["strategy"],
                "symbol": status["symbol"],
            },
        }

    async def _run_worker(self, job_id: str) -> None:
        """
        Background worker that executes the optimization.

        Args:
            job_id: Job identifier
        """
        redis = await get_redis_client()
        sse_manager = await get_sse_manager()
        job_key = get_optimization_job_key(job_id)

        try:
            # Mark as running
            started_at = datetime.now(timezone.utc)
            await redis.hset(job_key, mapping={
                "status": "running",
                "started_at": started_at.isoformat(),
            })

            # Get job parameters
            job_data = await redis.hgetall(job_key)
            param_grid = json.loads(job_data["param_grid"])
            strategy = job_data["strategy"]
            symbol = job_data["symbol"]
            timeframe = job_data["timeframe"]
            start_date = datetime.fromisoformat(job_data["start_date"])
            end_date = datetime.fromisoformat(job_data["end_date"])
            optimization_target = job_data["optimization_target"]
            initial_capital = float(job_data["initial_capital"])
            total_combinations = int(job_data["total_combinations"])

            # Emit job started event
            await sse_manager.emit_job_started(job_id, strategy, total_combinations)

            # Generate all combinations
            combinations = generate_grid_combinations(param_grid, validate=False)

            # Track best result
            best_params = None
            best_metric = float("-inf")
            all_results = []
            last_progress_pct = 0

            # Import optimizer here to avoid circular imports
            from src.services.backtesting.optimizer import StrategyOptimizer

            # Run each combination
            for i, params in enumerate(combinations):
                # Check for cancellation
                if job_id in self._cancelled_jobs:
                    logger.info("optimization_job_cancelled_during_run", job_id=job_id)
                    return

                # Update current params
                await redis.hset(job_key, "current_params", json.dumps(params))

                # Run single backtest
                try:
                    optimizer = StrategyOptimizer(self.db)
                    result = await optimizer._run_single_backtest(
                        symbol=symbol,
                        timeframe=timeframe,
                        start_date=start_date,
                        end_date=end_date,
                        strategy=strategy,
                        params=params,
                        initial_capital=initial_capital,
                    )

                    # Extract metric
                    metric_value = self._get_metric_value(result, optimization_target)

                    # Store result
                    all_results.append({
                        "params": params,
                        "sharpe_ratio": result.sharpe_ratio,
                        "total_return_pct": result.total_return_pct,
                        "max_drawdown_pct": result.max_drawdown_pct,
                        "total_trades": result.total_trades,
                        "profit_factor": result.profit_factor,
                    })

                    # Update best if improved
                    if metric_value > best_metric:
                        best_metric = metric_value
                        best_params = params

                except Exception as e:
                    logger.warning(
                        "backtest_failed_in_optimization",
                        job_id=job_id,
                        params=params,
                        error=str(e),
                    )
                    all_results.append({
                        "params": params,
                        "error": str(e),
                    })

                # Update progress
                combinations_tested = i + 1
                progress_pct = (combinations_tested / total_combinations) * 100

                await redis.hset(job_key, mapping={
                    "combinations_tested": str(combinations_tested),
                    "progress_pct": str(round(progress_pct, 1)),
                    "best_params": json.dumps(best_params) if best_params else "",
                    "best_metric": str(best_metric) if best_metric > float("-inf") else "",
                })

                # Emit progress event at intervals
                if progress_pct - last_progress_pct >= PROGRESS_UPDATE_INTERVAL or i == len(combinations) - 1:
                    await sse_manager.emit_job_progress(
                        job_id=job_id,
                        progress_pct=progress_pct,
                        combinations_tested=combinations_tested,
                        total_combinations=total_combinations,
                        best_params=best_params,
                        best_metric=best_metric if best_metric > float("-inf") else None,
                    )
                    last_progress_pct = progress_pct

            # Optimization complete
            completed_at = datetime.now(timezone.utc)
            duration_seconds = (completed_at - started_at).total_seconds()

            # Sort results by target metric
            all_results.sort(
                key=lambda r: self._get_metric_from_result(r, optimization_target),
                reverse=True,
            )

            # Store final state
            await redis.hset(job_key, mapping={
                "status": "completed",
                "results": json.dumps({
                    "all_results": all_results,
                    "duration_seconds": duration_seconds,
                }),
            })

            # Emit completion event
            await sse_manager.emit_job_complete(
                job_id=job_id,
                best_params=best_params or {},
                best_metric=best_metric if best_metric > float("-inf") else 0,
                total_tested=total_combinations,
            )

            # Persist to database
            await self._save_to_database(
                job_id=job_id,
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                param_grid=param_grid,
                results=all_results,
                total_combinations=total_combinations,
                best_params=best_params,
                best_metric=best_metric,
                optimization_target=optimization_target,
                initial_capital=initial_capital,
                started_at=started_at,
                completed_at=completed_at,
            )

            logger.info(
                "optimization_job_completed",
                job_id=job_id,
                total_combinations=total_combinations,
                duration_seconds=round(duration_seconds, 1),
                best_metric=best_metric,
            )

        except asyncio.CancelledError:
            # Job was cancelled
            logger.info("optimization_worker_cancelled", job_id=job_id)
            raise

        except Exception as e:
            # Job failed
            error_msg = str(e)
            logger.error(
                "optimization_job_failed",
                job_id=job_id,
                error=error_msg,
                exc_info=True,
            )

            # Update Redis state
            await redis.hset(job_key, mapping={
                "status": "failed",
                "error": error_msg,
            })

            # Emit failure event
            await sse_manager.emit_job_failed(job_id, error_msg)

        finally:
            # Remove from running jobs
            if job_id in self._running_jobs:
                del self._running_jobs[job_id]

            # Remove from active set after 1 hour
            # (keep for a while so clients can check final status)
            asyncio.create_task(self._cleanup_job(job_id, delay_seconds=3600))

    async def _cleanup_job(self, job_id: str, delay_seconds: int) -> None:
        """Remove job from active set after delay."""
        await asyncio.sleep(delay_seconds)
        redis = await get_redis_client()
        if redis:
            await redis.srem(get_optimization_jobs_list_key(), job_id)

    async def _save_to_database(
        self,
        job_id: str,
        strategy: str,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        param_grid: Dict[str, List[Any]],
        results: List[Dict[str, Any]],
        total_combinations: int,
        best_params: Optional[Dict[str, Any]],
        best_metric: float,
        optimization_target: str,
        initial_capital: float,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        """Persist optimization run to database."""
        try:
            optimization_run = OptimizationRun(
                job_id=job_id,
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                param_grid=param_grid,
                results={"all_results": results},
                status="completed",
                total_combinations=total_combinations,
                combinations_tested=total_combinations,
                best_params=best_params,
                best_metric_value=Decimal(str(best_metric)) if best_metric > float("-inf") else None,
                optimization_target=optimization_target,
                initial_capital=Decimal(str(initial_capital)),
                started_at=started_at,
                completed_at=completed_at,
            )

            self.db.add(optimization_run)
            await self.db.commit()

            logger.info("optimization_run_saved_to_db", job_id=job_id)

        except Exception as e:
            logger.error(
                "failed_to_save_optimization_to_db",
                job_id=job_id,
                error=str(e),
            )
            await self.db.rollback()

    async def _get_results_from_db(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch results from database if not in Redis."""
        from sqlalchemy import select

        try:
            result = await self.db.execute(
                select(OptimizationRun).where(OptimizationRun.job_id == job_id)
            )
            run = result.scalar_one_or_none()

            if not run:
                return None

            return {
                "job_id": run.job_id,
                "best_params": run.best_params,
                "best_metric_value": float(run.best_metric_value) if run.best_metric_value else None,
                "all_results": run.results.get("all_results", []) if run.results else [],
                "summary": {
                    "total_combinations": run.total_combinations,
                    "duration_seconds": (run.completed_at - run.started_at).total_seconds() if run.completed_at and run.started_at else 0,
                    "strategy": run.strategy,
                    "symbol": run.symbol,
                },
            }

        except Exception as e:
            logger.error("failed_to_get_results_from_db", job_id=job_id, error=str(e))
            return None

    def _get_metric_value(self, result: Any, target: str) -> float:
        """Extract the target metric value from a backtest result."""
        if target == "sharpe_ratio":
            return result.sharpe_ratio or 0
        elif target == "total_return_pct":
            return result.total_return_pct or 0
        elif target == "profit_factor":
            return result.profit_factor or 0
        elif target == "risk_adjusted_return":
            if result.max_drawdown_pct and result.max_drawdown_pct > 0:
                return (result.total_return_pct or 0) / abs(result.max_drawdown_pct)
            return 0
        else:
            return result.sharpe_ratio or 0

    def _get_metric_from_result(self, result: Dict[str, Any], target: str) -> float:
        """Extract metric value from result dict."""
        if "error" in result:
            return float("-inf")
        return result.get(target, result.get("sharpe_ratio", 0)) or 0

    def _estimate_duration(self, total_combinations: int) -> Optional[float]:
        """Estimate job duration in minutes based on combination count."""
        # Rough estimate: 0.5-1 second per combination
        seconds_per_combo = 0.75
        return round((total_combinations * seconds_per_combo) / 60, 1)

    async def _run_sync_optimization(
        self,
        strategy: str,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        param_grid: Dict[str, List[Any]],
        optimization_target: str,
        initial_capital: float,
        total_combinations: int,
    ) -> Dict[str, Any]:
        """
        Fallback synchronous optimization when Redis is unavailable.

        Runs the full optimization in the current request context and returns
        complete results. Use this only for small grid sizes as it blocks.

        Args:
            strategy: Strategy name
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_date: Optimization period start
            end_date: Optimization period end
            param_grid: Parameter grid to search
            optimization_target: Metric to optimize
            initial_capital: Starting capital
            total_combinations: Pre-calculated grid size

        Returns:
            Complete optimization results (same structure as get_job_results)
        """
        job_id = f"sync-{uuid4()}"
        started_at = datetime.now(timezone.utc)

        logger.info(
            "sync_optimization_started",
            job_id=job_id,
            strategy=strategy,
            symbol=symbol,
            total_combinations=total_combinations,
        )

        # Generate all combinations
        combinations = generate_grid_combinations(param_grid, validate=False)

        # Track best result
        best_params = None
        best_metric = float("-inf")
        all_results = []

        # Import optimizer
        from src.services.backtesting.optimizer import StrategyOptimizer

        # Run each combination
        for i, params in enumerate(combinations):
            try:
                optimizer = StrategyOptimizer(self.db)
                result = await optimizer._run_single_backtest(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    strategy=strategy,
                    params=params,
                    initial_capital=initial_capital,
                )

                # Extract metric
                metric_value = self._get_metric_value(result, optimization_target)

                # Store result
                all_results.append({
                    "params": params,
                    "sharpe_ratio": result.sharpe_ratio,
                    "total_return_pct": result.total_return_pct,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "total_trades": result.total_trades,
                    "profit_factor": result.profit_factor,
                })

                # Update best if improved
                if metric_value > best_metric:
                    best_metric = metric_value
                    best_params = params

            except Exception as e:
                logger.warning(
                    "sync_backtest_failed",
                    job_id=job_id,
                    params=params,
                    error=str(e),
                )
                all_results.append({
                    "params": params,
                    "error": str(e),
                })

        # Sort results by target metric
        all_results.sort(
            key=lambda r: self._get_metric_from_result(r, optimization_target),
            reverse=True,
        )

        completed_at = datetime.now(timezone.utc)
        duration_seconds = (completed_at - started_at).total_seconds()

        # Persist to database
        await self._save_to_database(
            job_id=job_id,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            param_grid=param_grid,
            results=all_results,
            total_combinations=total_combinations,
            best_params=best_params,
            best_metric=best_metric,
            optimization_target=optimization_target,
            initial_capital=initial_capital,
            started_at=started_at,
            completed_at=completed_at,
        )

        logger.info(
            "sync_optimization_completed",
            job_id=job_id,
            total_combinations=total_combinations,
            duration_seconds=round(duration_seconds, 1),
            best_metric=best_metric,
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "mode": "sync",  # Indicates fallback mode was used
            "total_combinations": total_combinations,
            "best_params": best_params,
            "best_metric_value": best_metric if best_metric > float("-inf") else None,
            "all_results": all_results,
            "summary": {
                "duration_seconds": duration_seconds,
                "strategy": strategy,
                "symbol": symbol,
            },
        }


# Global service instance (initialized with db session per request)
_job_service: Optional[OptimizationJobService] = None


async def get_job_service(db: AsyncSession) -> OptimizationJobService:
    """Get or create the optimization job service."""
    global _job_service
    if _job_service is None:
        _job_service = OptimizationJobService(db)
    return _job_service
