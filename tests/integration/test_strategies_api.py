"""
Integration tests for strategies API endpoints.

These tests verify the complete flow from API request through service layer
to database for strategy-related operations.

Coverage:
- GET /api/strategies - List all strategies
- GET /api/strategies/{id}/allocations - Strategy allocation history
- GET /api/strategies/{id}/performance - Strategy performance metrics
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.strategy import Strategy, StrategyAllocation, StrategyPerformance


@pytest.mark.asyncio
class TestStrategiesAPIIntegration:
    """Integration tests for strategies API endpoints."""

    @pytest.fixture(autouse=True)
    async def setup_strategy_data(self, async_session: AsyncSession):
        """Create test strategy data before each test."""
        now = datetime.now(timezone.utc)

        # Create test strategies
        strategies = [
            Strategy(
                name="Trend Following MACD",
                description="Long-term trend following using MACD crossovers",
                status="ACTIVE",
                allocated_capital=Decimal("50000.00"),
                parameters={
                    "fast_period": 12,
                    "slow_period": 26,
                    "signal_period": 9,
                },
                created_at=now - timedelta(days=90),
                updated_at=now,
            ),
            Strategy(
                name="Mean Reversion RSI",
                description="Short-term mean reversion using RSI oversold/overbought",
                status="ACTIVE",
                allocated_capital=Decimal("30000.00"),
                parameters={
                    "rsi_period": 14,
                    "oversold_threshold": 30,
                    "overbought_threshold": 70,
                },
                created_at=now - timedelta(days=60),
                updated_at=now,
            ),
            Strategy(
                name="Breakout Trading",
                description="Channel breakout strategy",
                status="PAUSED",
                allocated_capital=Decimal("20000.00"),
                parameters={
                    "lookback_period": 20,
                    "breakout_threshold": 0.02,
                },
                created_at=now - timedelta(days=30),
                updated_at=now,
            ),
        ]

        async_session.add_all(strategies)
        await async_session.flush()

        # Create allocations for first strategy
        allocations = [
            StrategyAllocation(
                strategy_id=strategies[0].id,
                allocated_capital=Decimal("30000.00"),
                allocated_percentage=Decimal("30.00"),
                allocation_date=now - timedelta(days=90),
                notes="Initial allocation",
            ),
            StrategyAllocation(
                strategy_id=strategies[0].id,
                allocated_capital=Decimal("50000.00"),
                allocated_percentage=Decimal("50.00"),
                allocation_date=now - timedelta(days=30),
                notes="Increased allocation due to strong performance",
            ),
        ]

        async_session.add_all(allocations)
        await async_session.flush()

        # Create performance records for first strategy
        performances = [
            StrategyPerformance(
                strategy_id=strategies[0].id,
                period="monthly",
                period_start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                period_end=datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
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
            ),
            StrategyPerformance(
                strategy_id=strategies[0].id,
                period="weekly",
                period_start=datetime(2025, 1, 22, 0, 0, tzinfo=timezone.utc),
                period_end=datetime(2025, 1, 28, 23, 59, 59, tzinfo=timezone.utc),
                total_trades=12,
                winning_trades=8,
                losing_trades=4,
                win_rate=Decimal("66.67"),
                total_profit=Decimal("1200.00"),
                total_loss=Decimal("450.00"),
                net_profit=Decimal("750.00"),
                sharpe_ratio=Decimal("1.92"),
                max_drawdown=Decimal("5.2"),
                average_win=Decimal("150.00"),
                average_loss=Decimal("112.50"),
            ),
        ]

        async_session.add_all(performances)
        await async_session.commit()

        self.strategies = strategies
        self.allocations = allocations
        self.performances = performances

        yield

        # Cleanup
        for perf in performances:
            await async_session.delete(perf)
        for alloc in allocations:
            await async_session.delete(alloc)
        for strategy in strategies:
            await async_session.delete(strategy)
        await async_session.commit()

    async def test_get_all_strategies(self, async_client: AsyncClient):
        """Test retrieving all strategies."""
        response = await async_client.get("/api/strategies")

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "total" in data
        assert isinstance(data["data"], list)
        assert data["total"] >= 3  # At least our 3 test strategies

        # Verify response structure
        if data["data"]:
            strategy = data["data"][0]
            assert "id" in strategy
            assert "name" in strategy
            assert "description" in strategy
            assert "status" in strategy
            assert "allocated_capital" in strategy
            assert "parameters" in strategy
            assert "created_at" in strategy
            assert "updated_at" in strategy

    async def test_strategies_grouped_by_status(self, async_client: AsyncClient):
        """Test that strategies can be filtered by status."""
        response = await async_client.get("/api/strategies")

        assert response.status_code == 200
        data = response.json()

        active_count = sum(1 for s in data["data"] if s["status"] == "ACTIVE")
        paused_count = sum(1 for s in data["data"] if s["status"] == "PAUSED")

        assert active_count >= 2  # At least 2 active
        assert paused_count >= 1  # At least 1 paused

    async def test_get_strategy_allocations(self, async_client: AsyncClient):
        """Test retrieving allocation history for a strategy."""
        strategy_id = self.strategies[0].id

        response = await async_client.get(f"/api/strategies/{strategy_id}/allocations")

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "total" in data
        assert data["total"] >= 2  # 2 allocation records

        # Verify response structure
        if data["data"]:
            allocation = data["data"][0]
            assert "id" in allocation
            assert "strategy_id" in allocation
            assert "allocated_capital" in allocation
            assert "allocated_percentage" in allocation
            assert "allocation_date" in allocation
            assert allocation["strategy_id"] == strategy_id

    async def test_get_strategy_allocations_ordering(self, async_client: AsyncClient):
        """Test that allocations are ordered by date (most recent first)."""
        strategy_id = self.strategies[0].id

        response = await async_client.get(f"/api/strategies/{strategy_id}/allocations")

        assert response.status_code == 200
        data = response.json()

        # Allocations should be ordered by date DESC
        if len(data["data"]) >= 2:
            dates = [
                datetime.fromisoformat(a["allocation_date"].replace("Z", "+00:00"))
                for a in data["data"]
            ]
            assert dates == sorted(dates, reverse=True)

    async def test_get_strategy_performance(self, async_client: AsyncClient):
        """Test retrieving performance metrics for a strategy."""
        strategy_id = self.strategies[0].id

        response = await async_client.get(f"/api/strategies/{strategy_id}/performance")

        assert response.status_code == 200
        data = response.json()

        assert "id" in data
        assert "strategy_id" in data
        assert "period" in data
        assert "total_trades" in data
        assert "win_rate" in data
        assert "net_profit" in data
        assert "sharpe_ratio" in data
        assert "max_drawdown" in data

    async def test_get_strategy_performance_with_period_filter(
        self, async_client: AsyncClient
    ):
        """Test filtering performance by period."""
        strategy_id = self.strategies[0].id

        # Test each period
        for period in ["weekly", "monthly", "all_time"]:
            response = await async_client.get(
                f"/api/strategies/{strategy_id}/performance?period={period}"
            )

            assert response.status_code == 200
            data = response.json()

            if period in ["weekly", "monthly"]:
                # Should return specific period data
                assert data["period"] == period

    async def test_get_strategy_allocations_nonexistent(
        self, async_client: AsyncClient
    ):
        """Test retrieving allocations for non-existent strategy."""
        response = await async_client.get("/api/strategies/99999/allocations")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data

    async def test_get_strategy_performance_nonexistent(
        self, async_client: AsyncClient
    ):
        """Test retrieving performance for non-existent strategy."""
        response = await async_client.get("/api/strategies/99999/performance")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data

    async def test_strategy_data_types(self, async_client: AsyncClient):
        """Test that strategy response fields have correct data types."""
        response = await async_client.get("/api/strategies")

        assert response.status_code == 200
        data = response.json()

        if data["data"]:
            strategy = data["data"][0]

            # Numeric fields should be strings (Decimal serialization)
            assert isinstance(strategy["allocated_capital"], str)

            # Allocated capital should be non-negative
            capital = Decimal(strategy["allocated_capital"])
            assert capital >= Decimal("0")

            # Parameters should be a dict
            assert isinstance(strategy["parameters"], dict)

    async def test_performance_metrics_calculations(self, async_client: AsyncClient):
        """Test that performance metrics are correctly calculated."""
        strategy_id = self.strategies[0].id

        response = await async_client.get(
            f"/api/strategies/{strategy_id}/performance?period=monthly"
        )

        assert response.status_code == 200
        data = response.json()

        # Win rate calculation check
        win_rate = Decimal(data["win_rate"])
        expected_win_rate = (
            Decimal(data["winning_trades"])
            / Decimal(data["total_trades"])
            * Decimal("100")
        )
        assert abs(win_rate - expected_win_rate) < Decimal("0.01")

        # Net profit calculation check
        net_profit = Decimal(data["net_profit"])
        total_profit = Decimal(data["total_profit"])
        total_loss = Decimal(data["total_loss"])
        assert net_profit == total_profit - total_loss

    async def test_strategies_caching_behavior(self, async_client: AsyncClient):
        """Test that strategies are properly cached."""
        # First request
        response1 = await async_client.get("/api/strategies")
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request should return same data (from cache)
        response2 = await async_client.get("/api/strategies")
        assert response2.status_code == 200
        data2 = response2.json()

        assert data1 == data2
