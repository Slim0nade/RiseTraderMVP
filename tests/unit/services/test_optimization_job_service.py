"""
Unit tests for OptimizationJobService.

These tests verify async job submission, status retrieval, cancellation,
and the grid search worker logic using mocked Redis and dependencies.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.optimization_job_service import (
    OptimizationJobService,
    JOB_TTL_SECONDS,
    PROGRESS_UPDATE_INTERVAL,
)
from src.utils.grid_search import GridSizeExceededError


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hgetall = AsyncMock(return_value={})
    redis.expire = AsyncMock()
    redis.sadd = AsyncMock()
    redis.srem = AsyncMock()
    redis.smembers = AsyncMock(return_value=set())
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_db_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def job_service(mock_redis, mock_db_session):
    """Create OptimizationJobService with mocked Redis and DB session."""
    service = OptimizationJobService(db_session=mock_db_session)
    return service


class TestJobSubmission:
    """Test job submission functionality (T010)."""

    @pytest.mark.asyncio
    async def test_submit_job_success(self, mock_redis):
        """Test successful job submission creates Redis state and returns job_id."""
        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())

            # Prevent worker from actually running
            with patch.object(service, "_run_worker", new_callable=AsyncMock) as mock_worker:
                result = await service.submit_job(
                    strategy="ma_crossover",
                    symbol="CrudeOIL",
                    timeframe="H1",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 3, 1),
                    param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
                    optimization_target="sharpe_ratio",
                    initial_capital=10000.0,
                )

                # Verify result structure
                assert "job_id" in result
                assert result["status"] == "pending"
                assert result["total_combinations"] == 4  # 2 x 2
                assert "estimated_duration_minutes" in result

                # Verify Redis calls
                mock_redis.hset.assert_called()
                mock_redis.expire.assert_called()
                mock_redis.sadd.assert_called()

    @pytest.mark.asyncio
    async def test_submit_job_validates_grid_size(self, mock_redis):
        """Test job submission validates grid size and raises GridSizeExceededError."""
        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())

            # Create a param grid that exceeds MAX_COMBINATIONS (10,000)
            large_grid = {
                "param1": list(range(100)),
                "param2": list(range(100)),
                "param3": list(range(2)),
            }  # 100 * 100 * 2 = 20,000 combinations

            with pytest.raises(GridSizeExceededError):
                await service.submit_job(
                    strategy="ma_crossover",
                    symbol="CrudeOIL",
                    timeframe="H1",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 3, 1),
                    param_grid=large_grid,
                )

    @pytest.mark.asyncio
    async def test_submit_job_redis_unavailable(self):
        """Test job submission falls back to sync mode when Redis is unavailable."""
        with patch("src.services.optimization_job_service.get_redis_client", new_callable=AsyncMock, return_value=None):
            service = OptimizationJobService(db_session=AsyncMock())

            # Mock the sync fallback to avoid importing gymnasium
            sync_result = {
                "job_id": "sync-test",
                "status": "completed",
                "total_combinations": 2,
            }
            with patch.object(service, "_run_sync_optimization", new_callable=AsyncMock, return_value=sync_result):
                result = await service.submit_job(
                    strategy="ma_crossover",
                    symbol="CrudeOIL",
                    timeframe="H1",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 3, 1),
                    param_grid={"fast_period": [5, 10]},
                )

                assert result["status"] == "completed"
                assert result["total_combinations"] == 2


class TestJobStatusRetrieval:
    """Test job status retrieval functionality (T011)."""

    @pytest.mark.asyncio
    async def test_get_job_status_success(self, mock_redis):
        """Test retrieving status of an existing job."""
        job_id = str(uuid4())
        mock_redis.hgetall.return_value = {
            "status": "running",
            "strategy": "ma_crossover",
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-03-01T00:00:00",
            "optimization_target": "sharpe_ratio",
            "progress_pct": "25.5",
            "combinations_tested": "10",
            "total_combinations": "40",
            "best_params": json.dumps({"fast_period": 10, "slow_period": 30}),
            "best_metric": "1.25",
            "current_params": json.dumps({"fast_period": 5, "slow_period": 20}),
            "created_at": "2024-01-15T10:00:00+00:00",
            "started_at": "2024-01-15T10:01:00+00:00",
            "error": "",
        }

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())
            status = await service.get_job_status(job_id)

            assert status is not None
            assert status["job_id"] == job_id
            assert status["status"] == "running"
            assert status["progress_pct"] == 25.5
            assert status["combinations_tested"] == 10
            assert status["best_params"] == {"fast_period": 10, "slow_period": 30}
            assert status["best_metric_value"] == 1.25

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, mock_redis):
        """Test retrieving status of a non-existent job returns None."""
        mock_redis.hgetall.return_value = {}

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())
            status = await service.get_job_status("nonexistent-job-id")

            assert status is None


class TestJobCancellation:
    """Test job cancellation functionality (T012)."""

    @pytest.mark.asyncio
    async def test_cancel_running_job(self, mock_redis):
        """Test cancelling a running job."""
        job_id = str(uuid4())
        mock_redis.hgetall.return_value = {
            "status": "running",
            "strategy": "ma_crossover",
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-03-01T00:00:00",
            "optimization_target": "sharpe_ratio",
            "progress_pct": "50",
            "combinations_tested": "20",
            "total_combinations": "40",
            "best_params": "",
            "best_metric": "",
            "current_params": "",
            "created_at": "2024-01-15T10:00:00+00:00",
            "started_at": "2024-01-15T10:01:00+00:00",
            "error": "",
        }

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            with patch("src.services.optimization_job_service.get_sse_manager") as mock_sse:
                mock_sse_manager = AsyncMock()
                mock_sse.return_value = mock_sse_manager

                service = OptimizationJobService(db_session=AsyncMock())
                result = await service.cancel_job(job_id)

                assert result["job_id"] == job_id
                assert result["status"] == "cancelled"
                mock_redis.hset.assert_called()
                mock_sse_manager.emit_job_cancelled.assert_called_with(job_id)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self, mock_redis):
        """Test cancelling a non-existent job raises ValueError."""
        mock_redis.hgetall.return_value = {}

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())

            with pytest.raises(ValueError, match="Job not found"):
                await service.cancel_job("nonexistent-job-id")

    @pytest.mark.asyncio
    async def test_cancel_completed_job(self, mock_redis):
        """Test cancelling a completed job raises ValueError."""
        job_id = str(uuid4())
        mock_redis.hgetall.return_value = {
            "status": "completed",
            "strategy": "ma_crossover",
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-03-01T00:00:00",
            "optimization_target": "sharpe_ratio",
            "progress_pct": "100",
            "combinations_tested": "40",
            "total_combinations": "40",
            "best_params": "",
            "best_metric": "",
            "current_params": "",
            "created_at": "2024-01-15T10:00:00+00:00",
            "started_at": "2024-01-15T10:01:00+00:00",
            "error": "",
        }

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())

            with pytest.raises(ValueError, match="already completed"):
                await service.cancel_job(job_id)


class TestListActiveJobs:
    """Test listing active jobs."""

    @pytest.mark.asyncio
    async def test_list_all_active_jobs(self, mock_redis):
        """Test listing all active jobs."""
        job_ids = {str(uuid4()), str(uuid4())}
        mock_redis.smembers.return_value = job_ids

        # Mock job statuses
        job_statuses = {}
        for i, job_id in enumerate(job_ids):
            job_statuses[job_id] = {
                "status": "running" if i == 0 else "pending",
                "strategy": "ma_crossover",
                "symbol": "CrudeOIL",
                "timeframe": "H1",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-03-01T00:00:00",
                "optimization_target": "sharpe_ratio",
                "progress_pct": "50" if i == 0 else "0",
                "combinations_tested": "20" if i == 0 else "0",
                "total_combinations": "40",
                "best_params": "",
                "best_metric": "",
                "current_params": "",
                "created_at": "2024-01-15T10:00:00+00:00",
                "started_at": "" if i == 1 else "2024-01-15T10:01:00+00:00",
                "error": "",
            }

        def hgetall_side_effect(key):
            for job_id in job_ids:
                if job_id in key:
                    return job_statuses[job_id]
            return {}

        mock_redis.hgetall.side_effect = hgetall_side_effect

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())
            jobs = await service.list_active_jobs()

            assert len(jobs) == 2
            assert all("job_id" in job for job in jobs)
            assert all("status" in job for job in jobs)

    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(self, mock_redis):
        """Test listing jobs with status filter."""
        job_ids = {str(uuid4()), str(uuid4())}
        mock_redis.smembers.return_value = job_ids

        job_list = list(job_ids)
        job_statuses = {
            job_list[0]: {
                "status": "running",
                "strategy": "ma_crossover",
                "symbol": "CrudeOIL",
                "timeframe": "H1",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-03-01T00:00:00",
                "optimization_target": "sharpe_ratio",
                "progress_pct": "50",
                "combinations_tested": "20",
                "total_combinations": "40",
                "best_params": "",
                "best_metric": "",
                "current_params": "",
                "created_at": "2024-01-15T10:00:00+00:00",
                "started_at": "2024-01-15T10:01:00+00:00",
                "error": "",
            },
            job_list[1]: {
                "status": "completed",
                "strategy": "ma_crossover",
                "symbol": "CrudeOIL",
                "timeframe": "H1",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-03-01T00:00:00",
                "optimization_target": "sharpe_ratio",
                "progress_pct": "100",
                "combinations_tested": "40",
                "total_combinations": "40",
                "best_params": "",
                "best_metric": "",
                "current_params": "",
                "created_at": "2024-01-15T09:00:00+00:00",
                "started_at": "2024-01-15T09:01:00+00:00",
                "error": "",
            },
        }

        def hgetall_side_effect(key):
            for job_id in job_ids:
                if job_id in key:
                    return job_statuses[job_id]
            return {}

        mock_redis.hgetall.side_effect = hgetall_side_effect

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())
            jobs = await service.list_active_jobs(status_filter="running")

            assert len(jobs) == 1
            assert jobs[0]["status"] == "running"


class TestGetJobResults:
    """Test getting full results for completed jobs."""

    @pytest.mark.asyncio
    async def test_get_results_success(self, mock_redis):
        """Test getting full results for a completed job."""
        job_id = str(uuid4())
        mock_redis.hgetall.return_value = {
            "status": "completed",
            "strategy": "ma_crossover",
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-03-01T00:00:00",
            "optimization_target": "sharpe_ratio",
            "progress_pct": "100",
            "combinations_tested": "4",
            "total_combinations": "4",
            "best_params": json.dumps({"fast_period": 10, "slow_period": 30}),
            "best_metric": "1.85",
            "current_params": "",
            "created_at": "2024-01-15T10:00:00+00:00",
            "started_at": "2024-01-15T10:01:00+00:00",
            "error": "",
        }

        results_data = {
            "all_results": [
                {"params": {"fast_period": 5, "slow_period": 20}, "sharpe_ratio": 1.2},
                {"params": {"fast_period": 5, "slow_period": 30}, "sharpe_ratio": 1.5},
                {"params": {"fast_period": 10, "slow_period": 20}, "sharpe_ratio": 1.6},
                {"params": {"fast_period": 10, "slow_period": 30}, "sharpe_ratio": 1.85},
            ],
            "duration_seconds": 120,
        }
        mock_redis.hget.return_value = json.dumps(results_data)

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())
            results = await service.get_job_results(job_id)

            assert results is not None
            assert results["job_id"] == job_id
            assert results["best_params"] == {"fast_period": 10, "slow_period": 30}
            assert results["best_metric_value"] == 1.85
            assert len(results["all_results"]) == 4

    @pytest.mark.asyncio
    async def test_get_results_job_not_completed(self, mock_redis):
        """Test getting results for a non-completed job raises ValueError."""
        job_id = str(uuid4())
        mock_redis.hgetall.return_value = {
            "status": "running",
            "strategy": "ma_crossover",
            "symbol": "CrudeOIL",
            "timeframe": "H1",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-03-01T00:00:00",
            "optimization_target": "sharpe_ratio",
            "progress_pct": "50",
            "combinations_tested": "20",
            "total_combinations": "40",
            "best_params": "",
            "best_metric": "",
            "current_params": "",
            "created_at": "2024-01-15T10:00:00+00:00",
            "started_at": "2024-01-15T10:01:00+00:00",
            "error": "",
        }

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            service = OptimizationJobService(db_session=AsyncMock())

            with pytest.raises(ValueError, match="not yet completed"):
                await service.get_job_results(job_id)
