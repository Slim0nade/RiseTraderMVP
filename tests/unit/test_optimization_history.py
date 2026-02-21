"""
Unit tests for optimization history persistence (T032-T034).

These tests verify:
- T032: save_optimization_run() stores results correctly
- T033: list_optimization_runs() returns paginated results
- T034: get_optimization_run() retrieves specific run with full results
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.optimization import OptimizationRun, OptimizationStatus
from src.database.repositories.optimization_repository import OptimizationRepository


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def sample_optimization_run():
    """Create a sample optimization run for testing."""
    run = OptimizationRun(
        id=uuid4(),
        job_id="job-123-abc",
        strategy="ma_crossover",
        symbol="CrudeOIL",
        timeframe="H1",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
        param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
        total_combinations=4,
        optimization_target="sharpe_ratio",
        initial_capital=Decimal("10000.00"),
        status=OptimizationStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    return run


@pytest.mark.asyncio
class TestSaveOptimizationRun:
    """Tests for T032: save_optimization_run() stores results correctly."""

    async def test_create_run_stores_all_fields(self, mock_session):
        """Test that create_run stores all provided fields."""
        repo = OptimizationRepository(mock_session)

        # Mock the flush to simulate DB assignment
        async def mock_flush():
            pass
        mock_session.flush = mock_flush

        run = await repo.create_run(
            job_id="test-job-001",
            strategy="ma_crossover",
            symbol="CrudeOIL",
            timeframe="H1",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
            param_grid={"fast": [5, 10], "slow": [20, 30]},
            total_combinations=4,
            optimization_target="sharpe_ratio",
            initial_capital=10000.0,
        )

        # Verify the run object was created correctly
        assert run.job_id == "test-job-001"
        assert run.strategy == "ma_crossover"
        assert run.symbol == "CrudeOIL"
        assert run.timeframe == "H1"
        assert run.param_grid == {"fast": [5, 10], "slow": [20, 30]}
        assert run.total_combinations == 4
        assert run.optimization_target == "sharpe_ratio"
        assert run.initial_capital == Decimal("10000")
        assert run.status == OptimizationStatus.PENDING.value

        # Verify session.add was called
        mock_session.add.assert_called_once_with(run)

    async def test_save_results_updates_run(self, mock_session):
        """Test that save_results updates run with results and completion."""
        repo = OptimizationRepository(mock_session)

        results = {
            "all_results": [
                {"params": {"fast": 5, "slow": 20}, "sharpe_ratio": 1.2},
                {"params": {"fast": 10, "slow": 30}, "sharpe_ratio": 1.8},
            ],
            "best_index": 1,
        }
        best_params = {"fast": 10, "slow": 30}

        await repo.save_results(
            job_id="test-job-001",
            results=results,
            best_params=best_params,
            best_metric_value=1.8,
            combinations_tested=4,
        )

        # Verify execute was called (for the update statement)
        mock_session.execute.assert_called_once()

    async def test_update_status_sets_timestamps(self, mock_session):
        """Test that update_status sets appropriate timestamps."""
        repo = OptimizationRepository(mock_session)

        started_at = datetime.now(timezone.utc)

        await repo.update_status(
            job_id="test-job-001",
            status=OptimizationStatus.RUNNING.value,
            started_at=started_at,
        )

        mock_session.execute.assert_called_once()

    async def test_update_status_with_error(self, mock_session):
        """Test that update_status stores error message on failure."""
        repo = OptimizationRepository(mock_session)

        await repo.update_status(
            job_id="test-job-001",
            status=OptimizationStatus.FAILED.value,
            error_message="Database connection failed",
        )

        mock_session.execute.assert_called_once()


@pytest.mark.asyncio
class TestListOptimizationRuns:
    """Tests for T033: list_optimization_runs() returns paginated results."""

    async def test_list_runs_returns_all_when_no_filters(self, mock_session):
        """Test listing runs without any filters."""
        repo = OptimizationRepository(mock_session)

        # Create mock runs
        runs = [
            MagicMock(
                id=uuid4(),
                job_id=f"job-{i}",
                strategy="ma_crossover",
                status=OptimizationStatus.COMPLETED.value,
            )
            for i in range(3)
        ]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = runs
        mock_session.execute.return_value = mock_result

        result = await repo.list_runs(limit=10)

        assert len(result) == 3
        mock_session.execute.assert_called_once()

    async def test_list_runs_filters_by_strategy(self, mock_session):
        """Test filtering runs by strategy name."""
        repo = OptimizationRepository(mock_session)

        runs = [MagicMock(strategy="rsi_strategy")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = runs
        mock_session.execute.return_value = mock_result

        result = await repo.list_runs(strategy="rsi_strategy")

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_list_runs_filters_by_symbol(self, mock_session):
        """Test filtering runs by trading symbol."""
        repo = OptimizationRepository(mock_session)

        runs = [MagicMock(symbol="XAUUSD")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = runs
        mock_session.execute.return_value = mock_result

        result = await repo.list_runs(symbol="XAUUSD")

        assert len(result) == 1

    async def test_list_runs_filters_by_status(self, mock_session):
        """Test filtering runs by status."""
        repo = OptimizationRepository(mock_session)

        runs = [MagicMock(status=OptimizationStatus.RUNNING.value)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = runs
        mock_session.execute.return_value = mock_result

        result = await repo.list_runs(status=OptimizationStatus.RUNNING.value)

        assert len(result) == 1

    async def test_list_runs_pagination(self, mock_session):
        """Test pagination with limit and offset."""
        repo = OptimizationRepository(mock_session)

        runs = [MagicMock() for _ in range(5)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = runs
        mock_session.execute.return_value = mock_result

        # Request page 2 with 5 items per page
        result = await repo.list_runs(limit=5, offset=5)

        assert len(result) == 5
        mock_session.execute.assert_called_once()

    async def test_list_runs_multiple_filters(self, mock_session):
        """Test combining multiple filters."""
        repo = OptimizationRepository(mock_session)

        runs = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = runs
        mock_session.execute.return_value = mock_result

        result = await repo.list_runs(
            strategy="ma_crossover",
            symbol="CrudeOIL",
            status=OptimizationStatus.COMPLETED.value,
            limit=10,
        )

        assert len(result) == 1


@pytest.mark.asyncio
class TestGetOptimizationRun:
    """Tests for T034: get_optimization_run() retrieves specific run with full results."""

    async def test_get_by_job_id_returns_run(self, mock_session, sample_optimization_run):
        """Test retrieving a run by job_id."""
        repo = OptimizationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_optimization_run
        mock_session.execute.return_value = mock_result

        run = await repo.get_by_job_id("job-123-abc")

        assert run is not None
        assert run.job_id == "job-123-abc"
        assert run.strategy == "ma_crossover"

    async def test_get_by_job_id_returns_none_when_not_found(self, mock_session):
        """Test that get_by_job_id returns None for non-existent job."""
        repo = OptimizationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        run = await repo.get_by_job_id("non-existent-job")

        assert run is None

    async def test_get_run_with_results(self, mock_session, sample_optimization_run):
        """Test retrieving a run by UUID with full results."""
        repo = OptimizationRepository(mock_session)

        # Add results to the sample run
        sample_optimization_run.results = {
            "all_results": [
                {"params": {"fast": 5}, "sharpe_ratio": 1.2},
                {"params": {"fast": 10}, "sharpe_ratio": 1.8},
            ]
        }
        sample_optimization_run.best_params = {"fast": 10}
        sample_optimization_run.best_metric_value = Decimal("1.8")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_optimization_run
        mock_session.execute.return_value = mock_result

        run = await repo.get_run_with_results(sample_optimization_run.id)

        assert run is not None
        assert run.results is not None
        assert run.best_params == {"fast": 10}
        assert run.best_metric_value == Decimal("1.8")

    async def test_get_run_with_results_returns_none_when_not_found(self, mock_session):
        """Test that get_run_with_results returns None for non-existent run."""
        repo = OptimizationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        run = await repo.get_run_with_results(uuid4())

        assert run is None


@pytest.mark.asyncio
class TestDeleteOldRuns:
    """Tests for cleaning up old optimization runs."""

    async def test_delete_old_runs(self, mock_session):
        """Test deleting runs older than specified days."""
        repo = OptimizationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        deleted_count = await repo.delete_old_runs(days=90)

        assert deleted_count == 5
        mock_session.execute.assert_called_once()

    async def test_delete_old_runs_with_no_matches(self, mock_session):
        """Test delete when no runs match the age threshold."""
        repo = OptimizationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        deleted_count = await repo.delete_old_runs(days=30)

        assert deleted_count == 0


@pytest.mark.asyncio
class TestPriceAlertOperations:
    """Tests for price alert CRUD operations."""

    async def test_create_alert(self, mock_session):
        """Test creating a price alert."""
        repo = OptimizationRepository(mock_session)

        alert = await repo.create_alert(
            ticket=12345,
            alert_type="liquidity_sweep",
            price_level=56.50,
            direction="below",
            metadata={"reason": "ATR-based stop"},
        )

        assert alert.ticket == 12345
        assert alert.alert_type == "liquidity_sweep"
        assert alert.price_level == Decimal("56.50")
        assert alert.direction == "below"
        mock_session.add.assert_called_once()

    async def test_get_active_alerts(self, mock_session):
        """Test retrieving active (untriggered) alerts."""
        repo = OptimizationRepository(mock_session)

        alerts = [MagicMock(triggered=False) for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = alerts
        mock_session.execute.return_value = mock_result

        result = await repo.get_active_alerts()

        assert len(result) == 3

    async def test_get_active_alerts_by_ticket(self, mock_session):
        """Test filtering active alerts by position ticket."""
        repo = OptimizationRepository(mock_session)

        alerts = [MagicMock(ticket=12345, triggered=False)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = alerts
        mock_session.execute.return_value = mock_result

        result = await repo.get_active_alerts(ticket=12345)

        assert len(result) == 1
        assert result[0].ticket == 12345

    async def test_trigger_alert(self, mock_session):
        """Test marking an alert as triggered."""
        repo = OptimizationRepository(mock_session)
        alert_id = uuid4()

        await repo.trigger_alert(alert_id)

        mock_session.execute.assert_called_once()

    async def test_delete_alerts_for_ticket(self, mock_session):
        """Test deleting all alerts for a position."""
        repo = OptimizationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        deleted_count = await repo.delete_alerts_for_ticket(12345)

        assert deleted_count == 3
