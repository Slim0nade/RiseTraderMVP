"""
Backtesting engine for validating multi-agent trading decisions against historical data.

This module provides:
- Full agent pipeline mode: Real LLM-powered agent decisions
- Synthetic fast mode: Rule-based logic for hyperparameter search (100x+ faster)
- CrudeOIL V3 Strategy: MQL4-converted multi-indicator strategy
- ZILLIONS Optimizer: Batch parameter optimization with parallel execution
- Gymnasium RL environment: For training reinforcement learning agents
- Performance metrics: Sharpe ratio, drawdown, win rate, profit factor
- A/B testing: Statistical comparison of different configurations

Core components (Phase 2 - Foundational):
- PortfolioState: Portfolio state management with P&L tracking
- TradeSimulator: Trade execution simulation with slippage and commissions
- MetricsCalculator: Performance metrics calculation
- DataReplayEngine: Historical data streaming
- DataValidator: Data quality validation

Strategies:
- CrudeOilStrategy: Original MQL4 strategy with EMA, RSI, CCI, Momentum
- CrudeOilStrategyExtended: Extended with MACD, Bollinger, Stochastic, ADX, etc.

Optimization:
- BatchOptimizer: Parallel parameter grid search
- ParameterGrid: Define search space
- OptimizationResult: Backtest results with metrics
"""

from .backtest_service import BacktestService
from src.services.market_tick import MarketTick
from .data_replay_engine import DataReplayEngine
from .data_validator import DataValidator, ValidationResult
from .metrics_calculator import MetricsCalculator, PerformanceMetrics
from .portfolio_state import PortfolioState, Position
from .synthetic_engine import SyntheticEngine, SyntheticSignal
from .trade_simulator import TradeSimulator, TradeResult
from .crude_oil_strategy import (
    CrudeOilStrategy,
    CrudeOilParams,
    CrudeOilSignal,
    create_crude_oil_strategy,
)
from .crude_oil_strategy_extended import (
    CrudeOilStrategyExtended,
    CrudeOilParamsExtended,
    CrudeOilSignalExtended,
    create_crude_oil_strategy_extended,
)
from .value_area_strategy import (
    ValueAreaStrategy,
    ValueAreaParams,
    ValueAreaSignal,
    create_value_area_strategy,
)
from .batch_optimizer import (
    BatchOptimizer,
    ParameterGrid,
    ExtendedParameterGrid,
    OptimizationResult,
    create_quick_grid,
    create_comprehensive_grid,
    create_zillions_grid,
    random_search_grid,
)
from .gymnasium_env import BacktestTradingEnv, EpisodeStatistics
from .comparison import (
    ComparisonService,
    ComparisonResult,
    StatisticalTest,
    TradeOverlap,
)

__all__ = [
    # Phase 2 - Core classes
    "PortfolioState",
    "Position",
    "TradeSimulator",
    "TradeResult",
    "MetricsCalculator",
    "PerformanceMetrics",
    "DataReplayEngine",
    "MarketTick",
    "DataValidator",
    "ValidationResult",
    # Phase 3 - Orchestration & Engines
    "BacktestService",
    "SyntheticEngine",
    "SyntheticSignal",
    # CrudeOIL V3 Strategy (MQL4 Conversion)
    "CrudeOilStrategy",
    "CrudeOilParams",
    "CrudeOilSignal",
    "create_crude_oil_strategy",
    # Extended Strategy - ZILLIONS Edition 🚀
    "CrudeOilStrategyExtended",
    "CrudeOilParamsExtended",
    "CrudeOilSignalExtended",
    "create_crude_oil_strategy_extended",
    # Value Area Trading Strategy
    "ValueAreaStrategy",
    "ValueAreaParams",
    "ValueAreaSignal",
    "create_value_area_strategy",
    # Batch Optimization
    "BatchOptimizer",
    "ParameterGrid",
    "ExtendedParameterGrid",
    "OptimizationResult",
    "create_quick_grid",
    "create_comprehensive_grid",
    "create_zillions_grid",
    "random_search_grid",
    # Phase 5 - RL Environment (User Story 3)
    "BacktestTradingEnv",
    "EpisodeStatistics",
    # Phase 6 - A/B Testing (User Story 4)
    "ComparisonService",
    "ComparisonResult",
    "StatisticalTest",
    "TradeOverlap",
    # Phase 3+ - Future (to be implemented)
    "AgentIntegrator",
]
