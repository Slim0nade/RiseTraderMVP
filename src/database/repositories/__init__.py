"""
Database repositories for RiseTrader.

All repository classes for database operations.
"""
from .agent_repository import AgentRepository
from .backtest_repository import BacktestRepository
from .base import BaseRepository
from .decision_log_repository import DecisionLogRepository
from .forecasts_repository import ForecastsRepository
from .indicators_repository import IndicatorsRepository
from .market_data_repository import MarketDataRepository
from .mcp_tool_repository import MCPToolRepository
from .model_configuration_repository import ModelConfigurationRepository
from .mt4_account_phase_repository import MT4AccountPhaseRepository
from .mt4_connection_repository import MT4ConnectionRepository
from .mt4_order_repository import MT4OrderRepository
from .parameter_grid_repository import ParameterGridRepository
from .portfolio_allocation_repository import PortfolioAllocationRepository
from .positions_repository import PositionsRepository
from .rl_training_run_repository import RLTrainingRunRepository
from .strategy_repository import StrategyRepository
from .strategy_team_repository import StrategyTeamRepository
from .trading_history_repository import TradingHistoryRepository
from .trading_repository import TradingRepository
from .optimization_repository import OptimizationRepository

__all__ = [
    "BaseRepository",
    # Core trading repositories
    "MarketDataRepository",
    "IndicatorsRepository",
    "PositionsRepository",
    "StrategyRepository",
    "TradingHistoryRepository",
    "TradingRepository",
    "ForecastsRepository",
    # MT4 integration repositories
    "MT4AccountPhaseRepository",
    "MT4ConnectionRepository",
    "MT4OrderRepository",
    # Agent system repositories (Feature 005)
    "AgentRepository",
    "DecisionLogRepository",
    "RLTrainingRunRepository",
    "ModelConfigurationRepository",
    "PortfolioAllocationRepository",
    "StrategyTeamRepository",
    "MCPToolRepository",
    # Backtesting repositories (Feature 006)
    "BacktestRepository",
    "ParameterGridRepository",
    # Optimization repositories (Feature 008)
    "OptimizationRepository",
]
