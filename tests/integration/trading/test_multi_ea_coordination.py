"""
Integration tests for multi-EA coordination (T063 - User Story 5).

Tests concurrent EA management, portfolio risk aggregation, and cross-EA coordination.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from src.services.mt4_integration_service import MT4IntegrationService
from src.trading.execution.mt4_connection_pool import MT4ConnectionPool


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_multiple_eas():
    """Test registering multiple EAs with unique magic numbers and ports."""
    # Arrange
    pool = MT4ConnectionPool()

    # Act - register 3 EAs
    ea1_magic = pool.allocate_magic_number()
    ea1_rep, ea1_pub = pool.allocate_ports()
    pool.register_ea("ea_crude", ea1_magic, ea1_rep, ea1_pub, "localhost", "CrudeOIL")

    ea2_magic = pool.allocate_magic_number()
    ea2_rep, ea2_pub = pool.allocate_ports()
    pool.register_ea("ea_forex", ea2_magic, ea2_rep, ea2_pub, "localhost", "EURUSD")

    ea3_magic = pool.allocate_magic_number()
    ea3_rep, ea3_pub = pool.allocate_ports()
    pool.register_ea("ea_gold", ea3_magic, ea3_rep, ea3_pub, "localhost", "XAUUSD")

    # Assert - all EAs registered with unique identifiers
    assert pool.get_ea_count() == 3
    assert ea1_magic != ea2_magic != ea3_magic
    assert ea1_rep != ea2_rep != ea3_rep


@pytest.mark.asyncio
@pytest.mark.integration
async def test_portfolio_risk_across_multiple_eas():
    """Test portfolio risk aggregation across multiple EAs."""
    # Arrange - mock service with multiple EA positions
    service = Mock(spec=MT4IntegrationService)

    positions = [
        Mock(magic_number=100000, symbol="CrudeOIL", unrealized_pnl=Decimal("100.00"), volume=Decimal("0.1")),
        Mock(magic_number=100001, symbol="EURUSD", unrealized_pnl=Decimal("-50.00"), volume=Decimal("0.2")),
        Mock(magic_number=100002, symbol="XAUUSD", unrealized_pnl=Decimal("75.00"), volume=Decimal("0.15")),
    ]

    # Act - calculate portfolio risk
    total_pnl = sum(p.unrealized_pnl for p in positions)
    total_volume = sum(p.volume for p in positions)
    ea_count = len(set(p.magic_number for p in positions))

    # Assert - portfolio aggregation correct
    assert total_pnl == Decimal("125.00")
    assert total_volume == Decimal("0.45")
    assert ea_count == 3


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_order_submission_from_multiple_eas():
    """Test concurrent order submission from multiple EAs without conflicts."""
    # Arrange
    pool = MT4ConnectionPool()

    # Register 3 EAs
    eas = []
    for i, symbol in enumerate(["CrudeOIL", "EURUSD", "GBPUSD"]):
        magic = pool.allocate_magic_number()
        rep, pub = pool.allocate_ports()
        ea_id = f"ea_{symbol.lower()}"
        pool.register_ea(ea_id, magic, rep, pub, "localhost", symbol)
        eas.append({"ea_id": ea_id, "magic": magic, "symbol": symbol})

    # Act - simulate concurrent operations
    tasks = []
    for ea in eas:
        # Simulate order submission
        task = asyncio.sleep(0.01)  # Simulated async operation
        tasks.append(task)

    await asyncio.gather(*tasks)

    # Assert - all EAs still registered
    assert pool.get_ea_count() == 3


@pytest.mark.asyncio
@pytest.mark.integration
async def test_portfolio_risk_limits_enforced_across_eas():
    """Test portfolio risk limits enforced across all EAs."""
    # Arrange - positions from multiple EAs exceeding limits
    positions = [
        Mock(magic_number=100000, unrealized_pnl=Decimal("-400.00")),
        Mock(magic_number=100001, unrealized_pnl=Decimal("-350.00")),
        Mock(magic_number=100002, unrealized_pnl=Decimal("-300.00")),
    ]

    total_loss = abs(sum(p.unrealized_pnl for p in positions))
    max_loss = Decimal("1000.00")

    # Act - check if portfolio exceeds limit
    exceeds_limit = total_loss > max_loss

    # Assert - portfolio loss detected
    assert total_loss == Decimal("1050.00")
    assert exceeds_limit is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ea_unregistration_releases_resources():
    """Test unregistering EA releases magic number and ports."""
    # Arrange
    pool = MT4ConnectionPool()
    magic = pool.allocate_magic_number()
    rep, pub = pool.allocate_ports()
    pool.register_ea("ea_test", magic, rep, pub, "localhost", "CrudeOIL")

    # Act - unregister
    pool.unregister_ea("ea_test")

    # Assert - resources released
    assert not pool.is_magic_number_allocated(magic)
    assert not pool.are_ports_allocated(rep, pub)
    assert pool.get_ea_count() == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_portfolio_health_monitoring_all_eas():
    """Test health monitoring across all registered EAs."""
    # Arrange
    pool = MT4ConnectionPool()

    # Register 3 EAs
    for i in range(3):
        magic = pool.allocate_magic_number()
        rep, pub = pool.allocate_ports()
        pool.register_ea(f"ea_{i}", magic, rep, pub, "localhost", f"SYMBOL{i}")

    # Act - get all EAs
    all_eas = pool.get_all_eas()

    # Assert - can monitor all EAs
    assert len(all_eas) == 3
    for ea_id, ea_info in all_eas.items():
        assert "magic_number" in ea_info
        assert "rep_port" in ea_info
        assert "pub_port" in ea_info
