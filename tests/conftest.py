"""
Pytest Configuration and Shared Fixtures for RiseTrader Tests

Provides:
- Database session fixtures
- Agent fixtures (EventBus, AgentRegistry, all 10 agents)
- Mock MT4 connection
- Sample market data
- Test event bus
- Redis fixtures
- API client fixtures
"""

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["MT4_HOST"] = "localhost"
os.environ["MT4_COMMAND_PORT"] = "5555"
os.environ["MT4_STREAM_PORT"] = "5556"

from src.agents.agent_registry import AgentRegistry, AgentStatus
from src.agents.base_agent import BaseAgent
from src.agents.event_bus import Event, EventBus, EventPriority
from src.agents.execution.execution import ExecutionAgent
from src.agents.execution.risk_manager import RiskManagerAgent
from src.agents.execution.signal_generator import SignalGeneratorAgent
from src.database.models.base import Base
from src.database.models.positions import OpenPosition
from src.database.models.market_data import MarketData
from src.database.models.trading_history import TradingHistory


# ============================================================================
# EVENT LOOP CONFIGURATION
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
async def async_engine():
    """Create async SQLite engine for testing"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing"""
    async_session = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


# ============================================================================
# REDIS FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def redis_client():
    """Mock Redis client for testing"""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    mock_redis.publish = AsyncMock(return_value=1)
    mock_redis.close = AsyncMock()
    
    # Mock pubsub
    mock_pubsub = AsyncMock()
    mock_pubsub.psubscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(return_value=None)
    mock_pubsub.close = AsyncMock()
    mock_redis.pubsub = Mock(return_value=mock_pubsub)
    
    return mock_redis


# ============================================================================
# EVENT BUS FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def event_bus(redis_client) -> AsyncGenerator[EventBus, None]:
    """Create EventBus for testing"""
    bus = EventBus(
        redis_url="redis://localhost:6379/1",
        max_queue_size=1000,
        retry_attempts=3,
        event_timeout=5.0,
    )
    
    # Mock Redis connections
    bus.redis_client = redis_client
    bus.redis_pubsub = redis_client.pubsub()
    
    await bus.start()
    
    yield bus
    
    await bus.stop()


@pytest.fixture
def sample_event() -> Event:
    """Create sample event for testing"""
    return Event(
        event_type="test_event",
        source_agent="test_agent",
        data={"test": "data"},
        priority=EventPriority.NORMAL,
    )


# ============================================================================
# AGENT REGISTRY FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def agent_registry(redis_client) -> AsyncGenerator[AgentRegistry, None]:
    """Create AgentRegistry for testing"""
    registry = AgentRegistry(
        redis_url="redis://localhost:6379/1",
        heartbeat_interval=1.0,
        heartbeat_timeout=3.0,
        circuit_breaker_enabled=True,
        failure_threshold=3,
        recovery_timeout=5.0,
    )
    
    # Mock Redis connection
    registry.redis_client = redis_client
    
    await registry.start()
    
    yield registry
    
    await registry.stop()


# ============================================================================
# AGENT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def signal_generator_agent(event_bus, agent_registry) -> AsyncGenerator[SignalGeneratorAgent, None]:
    """Create SignalGeneratorAgent for testing"""
    config = {
        "redis_url": "redis://localhost:6379/1",
        "strategies": [
            {"name": "momentum", "enabled": True, "weight": 0.3},
            {"name": "mean_reversion", "enabled": True, "weight": 0.25},
            {"name": "breakout", "enabled": True, "weight": 0.25},
            {"name": "ml_forecast", "enabled": True, "weight": 0.2},
        ],
        "signal_threshold": 0.6,
        "min_confidence": 0.5,
    }
    
    agent = SignalGeneratorAgent(
        agent_id="signal_generator_test",
        event_bus=event_bus,
        agent_registry=agent_registry,
        config=config,
    )
    
    # Mock Redis connection
    agent.redis_client = event_bus.redis_client
    
    await agent.start()
    
    yield agent
    
    await agent.stop()


@pytest_asyncio.fixture
async def risk_manager_agent(event_bus, agent_registry, db_session) -> AsyncGenerator[RiskManagerAgent, None]:
    """Create RiskManagerAgent for testing"""
    config = {
        "redis_url": "redis://localhost:6379/1",
        "max_position_size": 10.0,
        "max_open_positions": 5,
        "max_daily_loss": 1000.0,
        "max_position_risk": 0.02,
        "min_account_balance": 1000.0,
    }
    
    agent = RiskManagerAgent(
        agent_id="risk_manager_test",
        event_bus=event_bus,
        agent_registry=agent_registry,
        config=config,
    )
    
    # Mock Redis connection
    agent.redis_client = event_bus.redis_client
    
    # Mock database session
    agent.db_session = db_session
    
    await agent.start()
    
    yield agent
    
    await agent.stop()


@pytest_asyncio.fixture
async def execution_agent(event_bus, agent_registry) -> AsyncGenerator[ExecutionAgent, None]:
    """Create ExecutionAgent for testing"""
    config = {
        "redis_url": "redis://localhost:6379/1",
        "mt4_host": "localhost",
        "mt4_command_port": "5555",
        "max_retries": 3,
        "retry_delay": 1.0,
        "execution_timeout": 5.0,
    }
    
    agent = ExecutionAgent(
        agent_id="execution_test",
        event_bus=event_bus,
        agent_registry=agent_registry,
        config=config,
    )
    
    # Mock Redis connection
    agent.redis_client = event_bus.redis_client
    
    # Mock MT4 connection
    agent.mt4_socket = AsyncMock()
    agent.mt4_socket.send_json = AsyncMock(return_value=True)
    agent.mt4_socket.recv_json = AsyncMock(return_value={"status": "success", "order_id": "123456"})
    
    await agent.start()
    
    yield agent
    
    await agent.stop()


# ============================================================================
# MT4 MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_mt4_connection():
    """Mock MT4 ZMQ connection"""
    mock_socket = MagicMock()
    mock_socket.connect = Mock()
    mock_socket.send_json = Mock(return_value=True)
    mock_socket.recv_json = Mock(return_value={
        "status": "success",
        "order_id": "123456",
        "price": 1850.50,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    mock_socket.close = Mock()
    
    return mock_socket


@pytest.fixture
def mock_mt4_order_response():
    """Mock MT4 order response"""
    return {
        "status": "success",
        "order_id": "123456",
        "symbol": "CrudeOIL",
        "type": "BUY",
        "size": 1.0,
        "price": 1850.50,
        "stop_loss": 1840.00,
        "take_profit": 1870.00,
        "commission": 5.00,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_market_data():
    """Generate sample market data (OHLCV)"""
    return {
        "symbol": "CrudeOIL",
        "timestamp": datetime.now(timezone.utc),
        "open": 1850.00,
        "high": 1855.50,
        "low": 1848.00,
        "close": 1852.50,
        "volume": 10000,
        "timeframe": "1H",
    }


@pytest.fixture
def sample_tick_data():
    """Generate sample tick data"""
    return {
        "symbol": "CrudeOIL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bid": 1852.30,
        "ask": 1852.50,
        "last": 1852.40,
        "volume": 100,
    }


@pytest.fixture
def sample_signal():
    """Generate sample trading signal"""
    return {
        "symbol": "CrudeOIL",
        "action": "BUY",
        "score": 0.75,
        "confidence": 0.82,
        "strategy_votes": {
            "momentum": {"score": 0.8, "confidence": 0.7},
            "breakout": {"score": 0.7, "confidence": 0.65},
        },
        "current_price": 1852.50,
        "regime": "trending_up",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }


@pytest.fixture
def sample_position():
    """Generate sample open position"""
    return OpenPosition(
        number="ORD123456",
        type="BUY",
        size=Decimal("1.0"),
        symbol="CrudeOIL",
        price=Decimal("1850.50"),
        stop_loss=Decimal("1840.00"),
        take_profit=Decimal("1870.00"),
        commission=Decimal("5.00"),
        last_profit=Decimal("0.00"),
        last_update=datetime.now(timezone.utc),
        last_strategy="momentum",
        simulation=False,
    )


@pytest.fixture
def sample_forecast():
    """Generate sample ML forecast"""
    return {
        "symbol": "CrudeOIL",
        "prediction": 0.72,  # Probability of upward movement
        "confidence": 0.85,
        "model": "xgboost_ensemble",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {
            "rsi": 65.5,
            "macd": 2.3,
            "volume_ma_ratio": 1.2,
        },
    }


@pytest.fixture
def sample_regime():
    """Generate sample market regime"""
    return {
        "regime": "trending_up",
        "previous_regime": "ranging",
        "confidence": 0.78,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "indicators": {
            "volatility": "low",
            "trend_strength": 0.8,
        },
    }


# ============================================================================
# PRICE HISTORY FIXTURES
# ============================================================================

@pytest.fixture
def price_history_100():
    """Generate 100 bars of realistic price history"""
    import numpy as np
    
    base_price = 1850.0
    bars = []
    
    for i in range(100):
        # Simulate price movement with trend and noise
        trend = 0.1 * i  # Slight uptrend
        noise = np.random.normal(0, 5)
        
        open_price = base_price + trend + noise
        high_price = open_price + abs(np.random.normal(2, 1))
        low_price = open_price - abs(np.random.normal(2, 1))
        close_price = np.random.uniform(low_price, high_price)
        
        bars.append({
            "timestamp": datetime.now(timezone.utc).timestamp() + i * 3600,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": int(np.random.uniform(1000, 5000)),
        })
    
    return bars


# ============================================================================
# API FIXTURES
# ============================================================================

@pytest.fixture
def api_client():
    """Create FastAPI test client"""
    from src.api.main import app
    
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers():
    """Generate authentication headers for API"""
    return {
        "Authorization": "Bearer test_token",
        "X-API-Key": "test_api_key",
    }


# ============================================================================
# CONFIGURATION FIXTURES
# ============================================================================

@pytest.fixture
def agent_config():
    """Default agent configuration"""
    return {
        "redis_url": "redis://localhost:6379/1",
        "heartbeat_interval": 1.0,
        "log_level": "DEBUG",
    }


@pytest.fixture
def risk_config():
    """Risk management configuration"""
    return {
        "max_position_size": 10.0,
        "max_open_positions": 5,
        "max_daily_loss": 1000.0,
        "max_position_risk": 0.02,
        "min_account_balance": 1000.0,
        "max_leverage": 10.0,
        "max_drawdown": 0.15,
    }


@pytest.fixture
def strategy_config():
    """Trading strategy configuration"""
    return {
        "strategies": [
            {"name": "momentum", "enabled": True, "weight": 0.3},
            {"name": "mean_reversion", "enabled": True, "weight": 0.25},
            {"name": "breakout", "enabled": True, "weight": 0.25},
            {"name": "ml_forecast", "enabled": True, "weight": 0.2},
        ],
        "signal_threshold": 0.6,
        "min_confidence": 0.5,
    }


# ============================================================================
# HELPER FIXTURES
# ============================================================================

@pytest.fixture
def mock_time(monkeypatch):
    """Mock time.time() for deterministic tests"""
    fixed_time = 1700000000.0
    monkeypatch.setattr("time.time", lambda: fixed_time)
    return fixed_time


@pytest.fixture
async def wait_for_event(event_bus):
    """Helper to wait for specific event"""
    async def _wait(event_type: str, timeout: float = 1.0):
        events = []
        
        async def handler(event: Event):
            events.append(event)
        
        event_bus.subscribe(event_type, "test_waiter", handler)
        
        try:
            await asyncio.wait_for(
                asyncio.sleep(timeout),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            pass
        
        event_bus.unsubscribe(event_type, "test_waiter")
        
        return events
    
    return _wait


# ============================================================================
# CLEANUP
# ============================================================================

@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Cleanup after each test"""
    yield
    # Add any cleanup logic here
    await asyncio.sleep(0.1)  # Allow pending tasks to complete
