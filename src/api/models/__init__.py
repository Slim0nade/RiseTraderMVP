"""
API Pydantic Models

Request and response models for all API endpoints.
"""
from .agent_models import (
    AgentCommandRequest,
    AgentListResponse,
    AgentLogsResponse,
    AgentMetricsResponse,
    AgentOperationResponse,
    AgentStatusResponse,
    CommandResponse,
)
from .forecast_models import (
    ForecastAccuracyResponse,
    ForecastListResponse,
    ForecastResponse,
    GenerateForecastRequest,
    GenerateForecastResponse,
    LatestForecastsResponse,
)
from .market_data_models import (
    MarketDataListResponse,
    MarketDataResponse,
    StreamControlRequest,
    StreamControlResponse,
    SymbolInfoResponse,
    SymbolListResponse,
)
from .performance_models import (
    PerformanceByStrategyResponse,
    PerformanceChartResponse,
    PerformanceMetricsResponse,
    PerformanceSummaryResponse,
    MonthlyPerformanceResponse,
)
from .strategy_models import (
    StrategyListResponse,
    StrategyOperationResponse,
    StrategyPerformanceResponse,
    StrategyResponse,
    StrategyUpdateResponse,
    UpdateStrategyRequest,
)
from .system_models import (
    ComponentHealthListResponse,
    EmergencyStopRequest,
    EmergencyStopResponse,
    HealthCheckResponse,
    RestartRequest,
    RestartResponse,
    SystemStatusResponse,
)
from .trading_models import (
    ClosePositionRequest,
    ClosePositionResponse,
    OrderResponse,
    PlaceOrderRequest,
    PositionListResponse,
    PositionResponse,
    TradingHistoryListResponse,
    TradingHistoryResponse,
)

__all__ = [
    # Agent models
    "AgentCommandRequest",
    "AgentListResponse",
    "AgentLogsResponse",
    "AgentMetricsResponse",
    "AgentOperationResponse",
    "AgentStatusResponse",
    "CommandResponse",
    # Forecast models
    "ForecastAccuracyResponse",
    "ForecastListResponse",
    "ForecastResponse",
    "GenerateForecastRequest",
    "GenerateForecastResponse",
    "LatestForecastsResponse",
    # Market data models
    "MarketDataListResponse",
    "MarketDataResponse",
    "StreamControlRequest",
    "StreamControlResponse",
    "SymbolInfoResponse",
    "SymbolListResponse",
    # Performance models
    "PerformanceByStrategyResponse",
    "PerformanceChartResponse",
    "PerformanceMetricsResponse",
    "PerformanceSummaryResponse",
    "MonthlyPerformanceResponse",
    # Strategy models
    "StrategyListResponse",
    "StrategyOperationResponse",
    "StrategyPerformanceResponse",
    "StrategyResponse",
    "StrategyUpdateResponse",
    "UpdateStrategyRequest",
    # System models
    "ComponentHealthListResponse",
    "EmergencyStopRequest",
    "EmergencyStopResponse",
    "HealthCheckResponse",
    "RestartRequest",
    "RestartResponse",
    "SystemStatusResponse",
    # Trading models
    "ClosePositionRequest",
    "ClosePositionResponse",
    "OrderResponse",
    "PlaceOrderRequest",
    "PositionListResponse",
    "PositionResponse",
    "TradingHistoryListResponse",
    "TradingHistoryResponse",
]
