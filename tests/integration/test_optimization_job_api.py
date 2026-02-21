"""
Integration tests for async optimization job API endpoints.

These tests verify the complete flow from API request through service layer
for optimization job operations, using mocked Redis to avoid external dependencies.

Coverage:
- POST /api/optimizer/jobs - Submit optimization job
- GET /api/optimizer/jobs - List optimization jobs
- GET /api/optimizer/jobs/{job_id} - Get job status
- DELETE /api/optimizer/jobs/{job_id} - Cancel job
- GET /api/optimizer/jobs/{job_id}/results - Get job results
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient


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


@pytest.mark.asyncio
class TestOptimizationJobAPIIntegration:
    """Integration tests for optimization job API endpoints."""

    async def test_submit_job_and_get_status(self, api_client: AsyncClient, mock_redis):
        """Test full lifecycle: submit job, get status, verify progress."""
        job_id = str(uuid4())

        with patch("src.services.optimization_job_service.get_redis_client", return_value=mock_redis):
            with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
                # Setup mock service
                mock_service = AsyncMock()
                mock_service.submit_job.return_value = {
                    "job_id": job_id,
                    "status": "pending",
                    "total_combinations": 16,
                    "estimated_duration_minutes": 5,
                }
                mock_service.get_job_status.return_value = {
                    "job_id": job_id,
                    "status": "running",
                    "strategy": "ma_crossover",
                    "symbol": "CrudeOIL",
                    "timeframe": "H1",
                    "progress_pct": 25.0,
                    "combinations_tested": 4,
                    "total_combinations": 16,
                    "best_params": {"fast_period": 10, "slow_period": 30},
                    "best_metric_value": 1.5,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                mock_get_service.return_value = mock_service

                # Submit job
                response = await api_client.post(
                    "/api/optimizer/jobs",
                    json={
                        "symbol": "CrudeOIL",
                        "timeframe": "H1",
                        "start_date": "2024-01-01",
                        "end_date": "2024-03-01",
                        "strategy": "ma_crossover",
                        "param_grid": {
                            "fast_period": [5, 10, 15, 20],
                            "slow_period": [20, 30, 40, 50],
                        },
                        "optimization_target": "sharpe_ratio",
                        "initial_capital": 10000,
                    },
                )

                assert response.status_code == 202
                data = response.json()
                assert "job_id" in data
                assert data["status"] == "pending"
                assert data["total_combinations"] == 16

                # Get job status
                status_response = await api_client.get(f"/api/optimizer/jobs/{job_id}")
                assert status_response.status_code == 200
                status_data = status_response.json()
                assert status_data["status"] == "running"
                assert status_data["progress_pct"] == 25.0

    async def test_cancel_running_job(self, api_client: AsyncClient, mock_redis):
        """Test cancelling a running job."""
        job_id = str(uuid4())

        with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
            mock_service = AsyncMock()
            mock_service.cancel_job.return_value = {
                "job_id": job_id,
                "status": "cancelled",
                "combinations_tested": 8,
            }
            mock_get_service.return_value = mock_service

            response = await api_client.delete(f"/api/optimizer/jobs/{job_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cancelled"
            assert data["job_id"] == job_id

    async def test_list_jobs_with_filter(self, api_client: AsyncClient, mock_redis):
        """Test listing jobs with status filter."""
        job_ids = [str(uuid4()), str(uuid4())]

        with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
            mock_service = AsyncMock()
            mock_service.list_active_jobs.return_value = [
                {
                    "job_id": job_ids[0],
                    "strategy": "ma_crossover",
                    "symbol": "CrudeOIL",
                    "status": "running",
                    "progress_pct": 50.0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            ]
            mock_get_service.return_value = mock_service

            response = await api_client.get("/api/optimizer/jobs?status=running")

            assert response.status_code == 200
            data = response.json()
            assert "jobs" in data
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["status"] == "running"

    async def test_get_completed_job_results(self, api_client: AsyncClient, mock_redis):
        """Test getting full results for a completed job."""
        job_id = str(uuid4())

        with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_job_results.return_value = {
                "job_id": job_id,
                "best_params": {"fast_period": 10, "slow_period": 30},
                "best_metric_value": 1.85,
                "all_results": [
                    {"params": {"fast_period": 5, "slow_period": 20}, "sharpe_ratio": 1.2},
                    {"params": {"fast_period": 10, "slow_period": 30}, "sharpe_ratio": 1.85},
                ],
                "summary": {
                    "total_combinations": 16,
                    "duration_seconds": 120,
                    "strategy": "ma_crossover",
                    "symbol": "CrudeOIL",
                },
            }
            mock_get_service.return_value = mock_service

            response = await api_client.get(f"/api/optimizer/jobs/{job_id}/results")

            assert response.status_code == 200
            data = response.json()
            assert data["best_params"] == {"fast_period": 10, "slow_period": 30}
            assert data["best_metric_value"] == 1.85
            assert len(data["all_results"]) == 2

    async def test_get_results_for_incomplete_job(self, api_client: AsyncClient, mock_redis):
        """Test getting results for an incomplete job returns 400."""
        job_id = str(uuid4())

        with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_job_results.side_effect = ValueError("Job not yet completed")
            mock_get_service.return_value = mock_service

            response = await api_client.get(f"/api/optimizer/jobs/{job_id}/results")

            assert response.status_code == 400

    async def test_cancel_nonexistent_job(self, api_client: AsyncClient, mock_redis):
        """Test cancelling a non-existent job returns 404."""
        with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
            mock_service = AsyncMock()
            mock_service.cancel_job.side_effect = ValueError("Job not found")
            mock_get_service.return_value = mock_service

            response = await api_client.delete("/api/optimizer/jobs/nonexistent-id")

            assert response.status_code == 404


@pytest.mark.asyncio
class TestOptimizationJobFullLifecycle:
    """Test complete job lifecycle from submit to results."""

    async def test_complete_optimization_workflow(self, api_client: AsyncClient, mock_redis):
        """Test the complete workflow: submit → poll status → get results."""
        job_id = str(uuid4())

        with patch("src.api.routes.optimizer.get_job_service") as mock_get_service:
            mock_service = AsyncMock()

            # Phase 1: Submit
            mock_service.submit_job.return_value = {
                "job_id": job_id,
                "status": "pending",
                "total_combinations": 4,
                "estimated_duration_minutes": 2,
            }

            mock_get_service.return_value = mock_service

            submit_response = await api_client.post(
                "/api/optimizer/jobs",
                json={
                    "symbol": "CrudeOIL",
                    "timeframe": "H1",
                    "start_date": "2024-01-01",
                    "end_date": "2024-02-01",
                    "strategy": "ma_crossover",
                    "param_grid": {
                        "fast_period": [5, 10],
                        "slow_period": [20, 30],
                    },
                },
            )
            assert submit_response.status_code == 202
            assert submit_response.json()["job_id"] == job_id

            # Phase 2: Poll status (simulating progress)
            mock_service.get_job_status.return_value = {
                "job_id": job_id,
                "status": "running",
                "progress_pct": 50.0,
                "combinations_tested": 2,
                "total_combinations": 4,
                "best_params": None,
                "best_metric_value": None,
                "strategy": "ma_crossover",
                "symbol": "CrudeOIL",
                "timeframe": "H1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            status_response = await api_client.get(f"/api/optimizer/jobs/{job_id}")
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "running"
            assert status_response.json()["progress_pct"] == 50.0

            # Phase 3: Job completes
            mock_service.get_job_status.return_value = {
                "job_id": job_id,
                "status": "completed",
                "progress_pct": 100.0,
                "combinations_tested": 4,
                "total_combinations": 4,
                "best_params": {"fast_period": 10, "slow_period": 30},
                "best_metric_value": 2.1,
                "strategy": "ma_crossover",
                "symbol": "CrudeOIL",
                "timeframe": "H1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            final_status = await api_client.get(f"/api/optimizer/jobs/{job_id}")
            assert final_status.status_code == 200
            assert final_status.json()["status"] == "completed"

            # Phase 4: Get full results
            mock_service.get_job_results.return_value = {
                "job_id": job_id,
                "best_params": {"fast_period": 10, "slow_period": 30},
                "best_metric_value": 2.1,
                "all_results": [
                    {"params": {"fast_period": 5, "slow_period": 20}, "sharpe_ratio": 1.2},
                    {"params": {"fast_period": 5, "slow_period": 30}, "sharpe_ratio": 1.5},
                    {"params": {"fast_period": 10, "slow_period": 20}, "sharpe_ratio": 1.8},
                    {"params": {"fast_period": 10, "slow_period": 30}, "sharpe_ratio": 2.1},
                ],
                "summary": {
                    "total_combinations": 4,
                    "duration_seconds": 60,
                    "strategy": "ma_crossover",
                    "symbol": "CrudeOIL",
                },
            }

            results_response = await api_client.get(f"/api/optimizer/jobs/{job_id}/results")
            assert results_response.status_code == 200
            results = results_response.json()
            assert results["best_metric_value"] == 2.1
            assert len(results["all_results"]) == 4
