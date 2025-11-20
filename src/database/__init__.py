"""
RiseTrader Database Layer.

Complete database abstraction with SQLAlchemy async models and repositories.
"""
from .config import (
    DatabaseConfig,
    create_engine_from_env,
    create_session_factory,
    get_database,
    get_session,
    initialize_database,
)
from .models import (
    AccountInfo,
    Base,
    Forecast,
    Indicators,
    MarketData,
    ModelPerformance,
    NewsEvent,
    OpenPosition,
    OptimalTrade,
    TimestampMixin,
    TradingHistory,
    TradingSimulation,
)
from .repositories import (
    BaseRepository,
    ForecastsRepository,
    IndicatorsRepository,
    MarketDataRepository,
    PositionsRepository,
    TradingHistoryRepository,
)

__all__ = [
    # Configuration
    "DatabaseConfig",
    "initialize_database",
    "get_database",
    "get_session",
    "create_engine_from_env",
    "create_session_factory",
    # Models
    "Base",
    "TimestampMixin",
    "MarketData",
    "Indicators",
    "OpenPosition",
    "TradingHistory",
    "Forecast",
    "TradingSimulation",
    "OptimalTrade",
    "NewsEvent",
    "AccountInfo",
    "ModelPerformance",
    # Repositories
    "BaseRepository",
    "MarketDataRepository",
    "IndicatorsRepository",
    "PositionsRepository",
    "TradingHistoryRepository",
    "ForecastsRepository",
]
