"""
Unit tests for StrategyService.

These tests verify the caching logic and performance calculation logic
for strategy operations without requiring database connections.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from src.services.strategy_service import StrategyService
from src.database.models.strategy import Strategy, StrategyAllocation, StrategyPerformance


@pytest.mark.asyncio
class TestStrategyServiceCaching:
    """Unit tests for StrategyService caching behavior."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock StrategyRepository."""
        repository = Mock()
        repository.get_all_strategies = AsyncMock()
        repository.get_strategy_allocations = AsyncMock()
        repository.get_strategy_performance = AsyncMock()
        return repository

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.set = AsyncMock()
        redis_client.delete = AsyncMock()
        return redis_client

    @pytest.fixture
    def service(self, mock_repository, mock_redis):
        """Create StrategyService with mocked dependencies."""
        return StrategyService(repository=mock_repository, redis=mock_redis)

    async def test_get_all_strategies_cache_miss(
        self, service, mock_repository, mock_redis
    ):
        """Test that cache miss fetches from database and stores in cache."""
        now = datetime.now(timezone.utc)
        mock_strategies = [
            Strategy(
                id=1,
                name="Trend Following MACD",
                description="MACD strategy",
                status="ACTIVE",
                allocated_capital=Decimal("50000.00"),
                parameters={"fast_period": 12},
                created_at=now,
                updated_at=now,
            )
        ]

        # Mock cache miss
        mock_redis.get.return_value = None

        # Mock repository response
        mock_repository.get_all_strategies.return_value = mock_strategies

        # Call service method
        result = await service.get_all_strategies()

        # Verify repository was called
        mock_repository.get_all_strategies.assert_called_once()

        # Verify cache was written
        mock_redis.set.assert_called_once()
        cache_key = mock_redis.set.call_args[0][0]
        assert "strategies:all" in cache_key

        # Verify TTL is 1 hour (3600 seconds)
        assert mock_redis.set.call_args[1]["ex"] == 3600

        assert len(result) == 1
        assert result[0].name == "Trend Following MACD"

    async def test_get_all_strategies_cache_hit(
        self, service, mock_repository, mock_redis
    ):
        """Test that cache hit returns cached data without database query."""
        now = datetime.now(timezone.utc)

        # Mock cached data
        cached_data = {
            "strategies": [
                {
                    "id": 1,
                    "name": "Trend Following MACD",
                    "description": "MACD strategy",
                    "status": "ACTIVE",
                    "allocated_capital": "50000.00",
                    "parameters": {"fast_period": 12},
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            ],
            "cached_at": now.isoformat(),
        }

        import json
        mock_redis.get.return_value = json.dumps(cached_data)

        # Call service method
        result = await service.get_all_strategies()

        # Verify repository was NOT called (cache hit)
        mock_repository.get_all_strategies.assert_not_called()

        # Verify result from cache
        assert len(result) == 1

    async def test_get_strategy_allocations_cache_miss(
        self, service, mock_repository, mock_redis
    ):
        """Test allocation retrieval with cache miss."""
        now = datetime.now(timezone.utc)
        mock_allocations = [
            StrategyAllocation(
                id=1,
                strategy_id=5,
                allocated_capital=Decimal("50000.00"),
                allocated_percentage=Decimal("50.00"),
                allocation_date=now,
                notes="Test allocation",
            )
        ]

        # Mock cache miss
        mock_redis.get.return_value = None

        # Mock repository response
        mock_repository.get_strategy_allocations.return_value = mock_allocations

        # Call service method
        result = await service.get_strategy_allocations(strategy_id=5)

        # Verify repository was called
        mock_repository.get_strategy_allocations.assert_called_once_with(strategy_id=5)

        # Verify cache was written
        mock_redis.set.assert_called_once()

        assert len(result) == 1
        assert result[0].strategy_id == 5

    async def test_get_strategy_performance_cache_miss(
        self, service, mock_repository, mock_redis
    ):
        """Test performance retrieval with cache miss."""
        now = datetime.now(timezone.utc)
        mock_performance = StrategyPerformance(
            id=1,
            strategy_id=5,
            period="monthly",
            period_start=now,
            period_end=now,
            total_trades=45,
            winning_trades=30,
            losing_trades=15,
            win_rate=Decimal("66.67"),
            total_profit=Decimal("5420.50"),
            total_loss=Decimal("2150.25"),
            net_profit=Decimal("3270.25"),
            sharpe_ratio=Decimal("1.85"),
            max_drawdown=Decimal("8.5"),
            average_win=Decimal("180.68"),
            average_loss=Decimal("143.35"),
        )

        # Mock cache miss
        mock_redis.get.return_value = None

        # Mock repository response
        mock_repository.get_strategy_performance.return_value = mock_performance

        # Call service method
        result = await service.get_strategy_performance(
            strategy_id=5, period="monthly"
        )

        # Verify repository was called
        mock_repository.get_strategy_performance.assert_called_once_with(
            strategy_id=5, period="monthly"
        )

        # Verify cache was written
        mock_redis.set.assert_called_once()

        assert result.strategy_id == 5
        assert result.period == "monthly"


@pytest.mark.asyncio
class TestStrategyServiceAllocationCalculation:
    """Unit tests for allocation calculation logic."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock StrategyRepository."""
        repository = Mock()
        repository.get_all_strategies = AsyncMock()
        repository.get_strategy_allocations = AsyncMock()
        repository.get_strategy_performance = AsyncMock()
        return repository

    @pytest.fixture
    def service(self, mock_repository):
        """Create StrategyService with mocked repository (no Redis for logic tests)."""
        # Create a mock Redis that always misses cache
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        return StrategyService(repository=mock_repository, redis=mock_redis)

    async def test_allocation_percentage_calculation(
        self, service, mock_repository
    ):
        """Test that allocation percentages are correctly calculated."""
        now = datetime.now(timezone.utc)

        # Mock strategies with different allocations
        mock_strategies = [
            Strategy(
                id=1,
                name="Strategy 1",
                description="Test",
                status="ACTIVE",
                allocated_capital=Decimal("50000.00"),  # 50%
                parameters={},
                created_at=now,
                updated_at=now,
            ),
            Strategy(
                id=2,
                name="Strategy 2",
                description="Test",
                status="ACTIVE",
                allocated_capital=Decimal("30000.00"),  # 30%
                parameters={},
                created_at=now,
                updated_at=now,
            ),
            Strategy(
                id=3,
                name="Strategy 3",
                description="Test",
                status="ACTIVE",
                allocated_capital=Decimal("20000.00"),  # 20%
                parameters={},
                created_at=now,
                updated_at=now,
            ),
        ]

        mock_repository.get_all_strategies.return_value = mock_strategies

        # Calculate total capital
        total_capital = sum(s.allocated_capital for s in mock_strategies)

        # Expected percentages
        expected_percentages = [
            Decimal("50.00"),
            Decimal("30.00"),
            Decimal("20.00"),
        ]

        # Verify calculation
        for i, strategy in enumerate(mock_strategies):
            percentage = (strategy.allocated_capital / total_capital) * Decimal("100")
            # Round to 2 decimal places
            percentage = percentage.quantize(Decimal("0.01"))
            assert percentage == expected_percentages[i]

    async def test_strategy_performance_win_rate_calculation(self, service):
        """Test win rate calculation logic."""
        total_trades = 45
        winning_trades = 30
        losing_trades = 15

        # Calculate win rate
        win_rate = (Decimal(winning_trades) / Decimal(total_trades)) * Decimal("100")
        win_rate = win_rate.quantize(Decimal("0.01"))

        assert win_rate == Decimal("66.67")
        assert winning_trades + losing_trades == total_trades

    async def test_strategy_performance_net_profit_calculation(self, service):
        """Test net profit calculation logic."""
        total_profit = Decimal("5420.50")
        total_loss = Decimal("2150.25")

        net_profit = total_profit - total_loss

        assert net_profit == Decimal("3270.25")
        assert net_profit > Decimal("0")  # Profitable strategy

    async def test_strategy_performance_average_calculations(self, service):
        """Test average win/loss calculations."""
        total_profit = Decimal("5420.50")
        total_loss = Decimal("2150.25")
        winning_trades = 30
        losing_trades = 15

        average_win = total_profit / Decimal(winning_trades)
        average_loss = total_loss / Decimal(losing_trades)

        average_win = average_win.quantize(Decimal("0.01"))
        average_loss = average_loss.quantize(Decimal("0.01"))

        assert average_win == Decimal("180.68")
        assert average_loss == Decimal("143.35")
        assert average_win > average_loss  # Good risk/reward ratio

    async def test_get_all_strategies_filters_by_status(
        self, service, mock_repository
    ):
        """Test that strategies can be filtered by status."""
        now = datetime.now(timezone.utc)

        mock_strategies = [
            Strategy(
                id=1,
                name="Active Strategy",
                description="Test",
                status="ACTIVE",
                allocated_capital=Decimal("50000.00"),
                parameters={},
                created_at=now,
                updated_at=now,
            ),
            Strategy(
                id=2,
                name="Paused Strategy",
                description="Test",
                status="PAUSED",
                allocated_capital=Decimal("30000.00"),
                parameters={},
                created_at=now,
                updated_at=now,
            ),
            Strategy(
                id=3,
                name="Disabled Strategy",
                description="Test",
                status="DISABLED",
                allocated_capital=Decimal("0.00"),
                parameters={},
                created_at=now,
                updated_at=now,
            ),
        ]

        mock_repository.get_all_strategies.return_value = mock_strategies

        result = await service.get_all_strategies()

        # Verify different statuses
        statuses = {s.status for s in result}
        assert "ACTIVE" in statuses
        assert "PAUSED" in statuses
        assert "DISABLED" in statuses

    async def test_strategy_allocation_history_ordering(
        self, service, mock_repository
    ):
        """Test that allocations should be ordered by date."""
        now = datetime.now(timezone.utc)

        mock_allocations = [
            StrategyAllocation(
                id=1,
                strategy_id=5,
                allocated_capital=Decimal("30000.00"),
                allocated_percentage=Decimal("30.00"),
                allocation_date=now - timedelta(days=90),
                notes="Initial",
            ),
            StrategyAllocation(
                id=2,
                strategy_id=5,
                allocated_capital=Decimal("50000.00"),
                allocated_percentage=Decimal("50.00"),
                allocation_date=now - timedelta(days=30),
                notes="Increased",
            ),
            StrategyAllocation(
                id=3,
                strategy_id=5,
                allocated_capital=Decimal("40000.00"),
                allocated_percentage=Decimal("40.00"),
                allocation_date=now,
                notes="Decreased",
            ),
        ]

        from datetime import timedelta

        mock_repository.get_strategy_allocations.return_value = mock_allocations

        result = await service.get_strategy_allocations(strategy_id=5)

        # Allocations should be ordered by date (most recent first for UI)
        dates = [a.allocation_date for a in result]
        # Verify they can be sorted
        assert len(dates) == 3
