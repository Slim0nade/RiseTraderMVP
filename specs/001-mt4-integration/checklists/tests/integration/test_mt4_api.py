"""
Integration tests for MT4 API endpoints (T097).

Tests all REST API endpoints with realistic scenarios.
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.mt4 import router, init_mt4_service
from src.trading.execution.mt4_models import (
    AccountInfo,
    PositionInfo,
    PortfolioRiskState,
)


@pytest.fixture
def app():
    """Create FastAPI test app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_service():
    """Create mock MT4 integration service."""
    service = AsyncMock()
    service.order_repository = AsyncMock()
    service.connection_repository = AsyncMock()
    service.redis_client = AsyncMock()
    service.connection_pool = MagicMock()
    return service


@pytest.fixture
def init_service(mock_service):
    """Initialize service for API routes."""
    init_mt4_service(
        order_repository=mock_service.order_repository,
        connection_repository=mock_service.connection_repository,
        redis_client=mock_service.redis_client,
        symbol_loader=MagicMock(),
        connection_pool=mock_service.connection_pool
    )
    yield
    from src.api.routes import mt4
    mt4._service_instance = None


# Account query tests
@pytest.mark.asyncio
async def test_get_account_info_success(client, mock_service, init_service):
    """Test GET /mt4/account/{magic_number} - success."""
    account_info = AccountInfo(
        balance=Decimal("10000.50"),
        equity=Decimal("10250.75"),
        margin=Decimal("500.00"),
        free_margin=Decimal("9750.75"),
        margin_level=Decimal("2050.15"),
        profit=Decimal("250.25"),
        account_number=123456789,
        leverage=100,
        currency="USD",
        server="BrokerServer-Live",
        company="Broker Inc."
    )
    mock_service.query_account_info.return_value = account_info
    response = client.get("/mt4/account/100001")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_register_ea_success(client, mock_service, init_service):
    """Test POST /mt4/connections - register EA."""
    mock_service.register_ea.return_value = {
        "ea_id": "test_ea",
        "magic_number": 100001,
        "rep_port": 5555,
        "pub_port": 5556,
        "host": "localhost",
        "symbol": "CrudeOIL"
    }
    mock_connection = MagicMock(status="ACTIVE", last_heartbeat=None, encryption_enabled=True)
    mock_service.connection_repository.get_by_ea_id.return_value = mock_connection
    
    response = client.post("/mt4/connections", json={"ea_id": "test_ea", "symbol": "CrudeOIL"})
    assert response.status_code == 201
