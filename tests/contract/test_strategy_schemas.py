"""
Contract tests for strategy API schemas.

These tests verify that API responses conform to expected schemas
for strategy-related endpoints. They validate structure, field types,
and required fields without testing business logic.

Coverage:
- GET /api/strategies - List all strategies
- GET /api/strategies/{id}/allocations - Strategy allocations
- GET /api/strategies/{id}/performance - Strategy performance metrics
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import ValidationError

from src.api.models.strategies import (
    StrategyResponse,
    StrategyListResponse,
    StrategyAllocationResponse,
    StrategyAllocationListResponse,
    StrategyPerformanceResponse,
)


class TestStrategyResponseSchema:
    """Contract tests for StrategyResponse model."""

    def test_strategy_response_valid_data(self):
        """Test that valid strategy data passes validation."""
        data = {
            "id": 1,
            "name": "Trend Following MACD",
            "description": "Long-term trend following using MACD crossovers",
            "status": "ACTIVE",
            "allocated_capital": Decimal("50000.00"),
            "parameters": {
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
            },
            "created_at": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        }

        response = StrategyResponse(**data)

        assert response.id == 1
        assert response.name == "Trend Following MACD"
        assert response.status == "ACTIVE"
        assert response.allocated_capital == Decimal("50000.00")
        assert response.parameters["fast_period"] == 12

    def test_strategy_response_different_statuses(self):
        """Test that all valid status values are accepted."""
        base_data = {
            "id": 1,
            "name": "Test Strategy",
            "description": "Test",
            "allocated_capital": Decimal("10000.00"),
            "parameters": {},
            "created_at": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        }

        for status in ["ACTIVE", "PAUSED", "DISABLED"]:
            data = {**base_data, "status": status}
            response = StrategyResponse(**data)
            assert response.status == status

    def test_strategy_response_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        data = {
            "id": 1,
            "name": "Test Strategy",
            # Missing other required fields
        }

        with pytest.raises(ValidationError) as exc_info:
            StrategyResponse(**data)

        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}

        assert "status" in missing_fields
        assert "allocated_capital" in missing_fields

    def test_strategy_response_from_orm(self):
        """Test that from_attributes=True allows ORM model conversion."""
        class MockStrategyModel:
            id = 1
            name = "Test Strategy"
            description = "Test description"
            status = "ACTIVE"
            allocated_capital = Decimal("50000.00")
            parameters = {"test": "value"}
            created_at = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
            updated_at = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)

        mock_model = MockStrategyModel()
        response = StrategyResponse.model_validate(mock_model)

        assert response.id == 1
        assert response.name == "Test Strategy"


class TestStrategyListResponseSchema:
    """Contract tests for StrategyListResponse model."""

    def test_strategy_list_response_valid_data(self):
        """Test that valid strategy list data passes validation."""
        strategy_data = {
            "id": 1,
            "name": "Test Strategy",
            "description": "Test",
            "status": "ACTIVE",
            "allocated_capital": Decimal("50000.00"),
            "parameters": {},
            "created_at": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        }

        data = {
            "data": [strategy_data],
            "total": 1,
        }

        response = StrategyListResponse(**data)

        assert len(response.data) == 1
        assert response.total == 1

    def test_strategy_list_response_empty_list(self):
        """Test that empty strategy list is valid."""
        data = {
            "data": [],
            "total": 0,
        }

        response = StrategyListResponse(**data)

        assert len(response.data) == 0
        assert response.total == 0


class TestStrategyAllocationResponseSchema:
    """Contract tests for StrategyAllocationResponse model."""

    def test_allocation_response_valid_data(self):
        """Test that valid allocation data passes validation."""
        data = {
            "id": 1,
            "strategy_id": 5,
            "allocated_capital": Decimal("50000.00"),
            "allocated_percentage": Decimal("25.00"),
            "allocation_date": datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            "notes": "Q1 2025 allocation increase",
        }

        response = StrategyAllocationResponse(**data)

        assert response.id == 1
        assert response.strategy_id == 5
        assert response.allocated_capital == Decimal("50000.00")
        assert response.allocated_percentage == Decimal("25.00")
        assert response.notes == "Q1 2025 allocation increase"

    def test_allocation_response_missing_optional_fields(self):
        """Test that optional fields can be omitted."""
        data = {
            "id": 1,
            "strategy_id": 5,
            "allocated_capital": Decimal("50000.00"),
            "allocated_percentage": Decimal("25.00"),
            "allocation_date": datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
            # notes is optional
        }

        response = StrategyAllocationResponse(**data)

        assert response.id == 1
        assert response.notes is None

    def test_allocation_response_from_orm(self):
        """Test that from_attributes=True allows ORM model conversion."""
        class MockAllocationModel:
            id = 1
            strategy_id = 5
            allocated_capital = Decimal("50000.00")
            allocated_percentage = Decimal("25.00")
            allocation_date = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
            notes = "Test note"

        mock_model = MockAllocationModel()
        response = StrategyAllocationResponse.model_validate(mock_model)

        assert response.id == 1
        assert response.strategy_id == 5


class TestStrategyAllocationListResponseSchema:
    """Contract tests for StrategyAllocationListResponse model."""

    def test_allocation_list_response_valid_data(self):
        """Test that valid allocation list data passes validation."""
        allocation_data = {
            "id": 1,
            "strategy_id": 5,
            "allocated_capital": Decimal("50000.00"),
            "allocated_percentage": Decimal("25.00"),
            "allocation_date": datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
        }

        data = {
            "data": [allocation_data],
            "total": 1,
        }

        response = StrategyAllocationListResponse(**data)

        assert len(response.data) == 1
        assert response.total == 1


class TestStrategyPerformanceResponseSchema:
    """Contract tests for StrategyPerformanceResponse model."""

    def test_performance_response_valid_data(self):
        """Test that valid performance data passes validation."""
        data = {
            "id": 1,
            "strategy_id": 5,
            "period": "monthly",
            "period_start": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            "period_end": datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
            "total_trades": 45,
            "winning_trades": 30,
            "losing_trades": 15,
            "win_rate": Decimal("66.67"),
            "total_profit": Decimal("5420.50"),
            "total_loss": Decimal("2150.25"),
            "net_profit": Decimal("3270.25"),
            "sharpe_ratio": Decimal("1.85"),
            "max_drawdown": Decimal("8.5"),
            "average_win": Decimal("180.68"),
            "average_loss": Decimal("143.35"),
        }

        response = StrategyPerformanceResponse(**data)

        assert response.id == 1
        assert response.strategy_id == 5
        assert response.period == "monthly"
        assert response.total_trades == 45
        assert response.win_rate == Decimal("66.67")
        assert response.sharpe_ratio == Decimal("1.85")

    def test_performance_response_different_periods(self):
        """Test that all valid period values are accepted."""
        base_data = {
            "id": 1,
            "strategy_id": 5,
            "period_start": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            "period_end": datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
            "total_trades": 10,
            "winning_trades": 6,
            "losing_trades": 4,
            "win_rate": Decimal("60.00"),
            "total_profit": Decimal("1000.00"),
            "total_loss": Decimal("400.00"),
            "net_profit": Decimal("600.00"),
            "sharpe_ratio": Decimal("1.5"),
            "max_drawdown": Decimal("5.0"),
            "average_win": Decimal("166.67"),
            "average_loss": Decimal("100.00"),
        }

        for period in ["daily", "weekly", "monthly", "all_time"]:
            data = {**base_data, "period": period}
            response = StrategyPerformanceResponse(**data)
            assert response.period == period

    def test_performance_response_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        data = {
            "id": 1,
            "strategy_id": 5,
            "period": "monthly",
            # Missing other required fields
        }

        with pytest.raises(ValidationError) as exc_info:
            StrategyPerformanceResponse(**data)

        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}

        assert "total_trades" in missing_fields
        assert "win_rate" in missing_fields
        assert "net_profit" in missing_fields

    def test_performance_response_from_orm(self):
        """Test that from_attributes=True allows ORM model conversion."""
        class MockPerformanceModel:
            id = 1
            strategy_id = 5
            period = "monthly"
            period_start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
            period_end = datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
            total_trades = 45
            winning_trades = 30
            losing_trades = 15
            win_rate = Decimal("66.67")
            total_profit = Decimal("5420.50")
            total_loss = Decimal("2150.25")
            net_profit = Decimal("3270.25")
            sharpe_ratio = Decimal("1.85")
            max_drawdown = Decimal("8.5")
            average_win = Decimal("180.68")
            average_loss = Decimal("143.35")

        mock_model = MockPerformanceModel()
        response = StrategyPerformanceResponse.model_validate(mock_model)

        assert response.id == 1
        assert response.total_trades == 45
        assert response.win_rate == Decimal("66.67")
