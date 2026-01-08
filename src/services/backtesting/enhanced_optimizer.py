"""
Enhanced Strategy Optimizer

Extends the base optimizer with:
- Rolling window optimization (re-optimize at intervals)
- Time-interval specific parameters (different params for different market regimes)
- Multi-period validation
- Parameter sensitivity analysis
- Monte Carlo simulation for robustness
"""
import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Callable
from uuid import uuid4
import time
import random

import numpy as np
import pandas as pd
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.backtesting.vectorized_engine import (
    VectorizedBacktestConfig,
    VectorizedBacktestEngine,
    VectorizedBacktestResult,
)
from src.services.backtesting.optimizer import (
    OptimizationResult,
    OptimizationSummary,
    StrategyOptimizer,
)
from src.services.backtesting.timeframe_aggregator import (
    TimeframeAggregator,
    TimeframeConverter,
)

logger = structlog.get_logger(__name__)


@dataclass
class RollingWindowResult:
    """Result from a single rolling optimization window."""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: Dict[str, Any]
    train_return: float
    train_sharpe: float
    test_return: float
    test_sharpe: float
    test_trades: int
    test_profit_factor: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "train_period": f"{self.train_start.date()} to {self.train_end.date()}",
            "test_period": f"{self.test_start.date()} to {self.test_end.date()}",
            "best_params": self.best_params,
            "train_return_pct": round(self.train_return, 2),
            "train_sharpe": round(self.train_sharpe, 2),
            "test_return_pct": round(self.test_return, 2),
            "test_sharpe": round(self.test_sharpe, 2),
            "test_trades": self.test_trades,
            "test_profit_factor": round(self.test_profit_factor, 2),
        }


@dataclass
class TimeIntervalParams:
    """Optimal parameters for a specific time interval."""
    interval_name: str
    start_date: datetime
    end_date: datetime
    best_params: Dict[str, Any]
    return_pct: float
    sharpe_ratio: float
    profit_factor: float
    total_trades: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interval_name": self.interval_name,
            "period": f"{self.start_date.date()} to {self.end_date.date()}",
            "best_params": self.best_params,
            "return_pct": round(self.return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "profit_factor": round(self.profit_factor, 2),
            "total_trades": self.total_trades,
        }


@dataclass
class SensitivityResult:
    """Parameter sensitivity analysis result."""
    param_name: str
    values: List[Any]
    returns: List[float]
    sharpes: List[float]
    optimal_value: Any
    sensitivity_score: float  # How much the param affects performance
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "param_name": self.param_name,
            "values": self.values,
            "returns": [round(r, 2) for r in self.returns],
            "sharpes": [round(s, 2) for s in self.sharpes],
            "optimal_value": self.optimal_value,
            "sensitivity_score": round(self.sensitivity_score, 2),
        }


class EnhancedOptimizer(StrategyOptimizer):
    """
    Enhanced optimizer with advanced features.
    
    Extends base optimizer with:
    - Rolling window optimization
    - Time-interval specific parameters
    - Sensitivity analysis
    - Monte Carlo validation
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize enhanced optimizer."""
        super().__init__(session)
        self.aggregator = TimeframeAggregator(session)
    
    async def rolling_window_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        param_grid: Optional[Dict[str, List[Any]]] = None,
        optimization_target: str = "sharpe_ratio",
        train_months: int = 3,
        test_months: int = 1,
        step_months: int = 1,
        initial_capital: float = 10000.0,
        max_combinations: int = 100,
    ) -> Dict[str, Any]:
        """
        Rolling window optimization.
        
        Re-optimizes parameters every `step_months` using the last `train_months`
        of data, then tests on the next `test_months`.
        
        This simulates real-world trading where you periodically re-optimize.
        
        Args:
            train_months: Months of data for training
            test_months: Months of data for testing
            step_months: How often to re-optimize
            
        Returns:
            Dict with all window results and aggregate performance
        """
        optimization_id = str(uuid4())[:8]
        start_time = time.perf_counter()
        
        logger.info(
            "rolling_window_optimization_starting",
            optimization_id=optimization_id,
            strategy=strategy,
            train_months=train_months,
            test_months=test_months,
        )
        
        # Calculate windows
        windows = []
        current_start = start_date
        window_id = 0
        
        while True:
            train_end = current_start + timedelta(days=train_months * 30)
            test_start = train_end
            test_end = test_start + timedelta(days=test_months * 30)
            
            if test_end > end_date:
                break
            
            windows.append({
                "id": window_id,
                "train_start": current_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            })
            
            window_id += 1
            current_start += timedelta(days=step_months * 30)
        
        if not windows:
            return {"error": "Date range too short for rolling optimization"}
        
        logger.info(f"Created {len(windows)} rolling windows")
        
        # Process each window
        results: List[RollingWindowResult] = []
        cumulative_capital = initial_capital
        
        for window in windows:
            # Optimize on training period
            train_result = await self.optimize(
                symbol=symbol,
                timeframe=timeframe,
                start_date=window["train_start"],
                end_date=window["train_end"],
                strategy=strategy,
                param_grid=param_grid,
                optimization_target=optimization_target,
                initial_capital=initial_capital,
                max_combinations=max_combinations,
            )
            
            if not train_result.best_params:
                continue
            
            # Test on out-of-sample period
            test_config = VectorizedBacktestConfig(
                symbol=symbol,
                timeframe=timeframe,
                start_date=window["test_start"],
                end_date=window["test_end"],
                strategy=strategy,
                strategy_params=train_result.best_params,
                initial_capital=cumulative_capital,
            )
            
            test_result = await self.engine.run(test_config)
            
            # Update cumulative capital
            cumulative_capital = test_result.final_capital
            
            results.append(RollingWindowResult(
                window_id=window["id"],
                train_start=window["train_start"],
                train_end=window["train_end"],
                test_start=window["test_start"],
                test_end=window["test_end"],
                best_params=train_result.best_params,
                train_return=train_result.best_return_pct,
                train_sharpe=train_result.best_sharpe,
                test_return=test_result.total_return_pct,
                test_sharpe=test_result.sharpe_ratio,
                test_trades=test_result.total_trades,
                test_profit_factor=test_result.profit_factor,
            ))
            
            logger.info(
                f"Window {window['id']}: Train={train_result.best_return_pct:.1f}%, "
                f"Test={test_result.total_return_pct:.1f}%"
            )
        
        # Calculate aggregate metrics
        if results:
            total_test_return = (cumulative_capital / initial_capital - 1) * 100
            avg_train_return = np.mean([r.train_return for r in results])
            avg_test_return = np.mean([r.test_return for r in results])
            avg_train_sharpe = np.mean([r.train_sharpe for r in results])
            avg_test_sharpe = np.mean([r.test_sharpe for r in results])
            total_trades = sum(r.test_trades for r in results)
            
            # Robustness metrics
            positive_windows = sum(1 for r in results if r.test_return > 0)
            robustness_ratio = positive_windows / len(results) if results else 0
        else:
            total_test_return = 0
            avg_train_return = avg_test_return = 0
            avg_train_sharpe = avg_test_sharpe = 0
            total_trades = 0
            robustness_ratio = 0
        
        total_time = time.perf_counter() - start_time
        
        return {
            "success": True,
            "optimization_id": optimization_id,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "config": {
                "train_months": train_months,
                "test_months": test_months,
                "step_months": step_months,
                "total_windows": len(windows),
            },
            "windows": [r.to_dict() for r in results],
            "aggregate": {
                "initial_capital": initial_capital,
                "final_capital": round(cumulative_capital, 2),
                "total_return_pct": round(total_test_return, 2),
                "avg_train_return_pct": round(avg_train_return, 2),
                "avg_test_return_pct": round(avg_test_return, 2),
                "avg_train_sharpe": round(avg_train_sharpe, 2),
                "avg_test_sharpe": round(avg_test_sharpe, 2),
                "total_trades": total_trades,
                "positive_windows": positive_windows if results else 0,
                "robustness_ratio": round(robustness_ratio, 2),
            },
            "recommendation": self._get_rolling_recommendation(robustness_ratio, avg_test_sharpe),
            "total_time_seconds": round(total_time, 2),
        }
    
    async def time_interval_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        intervals: List[Dict[str, Any]],
        param_grid: Optional[Dict[str, List[Any]]] = None,
        optimization_target: str = "sharpe_ratio",
        initial_capital: float = 10000.0,
        max_combinations: int = 100,
    ) -> Dict[str, Any]:
        """
        Optimize parameters for specific time intervals.
        
        Useful for identifying regime-specific parameters:
        - Different params for trending vs ranging markets
        - Seasonal adjustments
        - Different params for different market sessions
        
        Args:
            intervals: List of dicts with keys: name, start_date, end_date
                Example: [
                    {"name": "Q1_2024", "start_date": "2024-01-01", "end_date": "2024-04-01"},
                    {"name": "Q2_2024", "start_date": "2024-04-01", "end_date": "2024-07-01"},
                ]
                
        Returns:
            Dict with optimal params for each interval
        """
        optimization_id = str(uuid4())[:8]
        start_time = time.perf_counter()
        
        logger.info(
            "time_interval_optimization_starting",
            optimization_id=optimization_id,
            strategy=strategy,
            num_intervals=len(intervals),
        )
        
        results: List[TimeIntervalParams] = []
        
        for interval in intervals:
            interval_start = interval.get("start_date")
            interval_end = interval.get("end_date")
            interval_name = interval.get("name", f"{interval_start}_to_{interval_end}")
            
            # Parse dates if strings
            if isinstance(interval_start, str):
                interval_start = datetime.fromisoformat(interval_start)
            if isinstance(interval_end, str):
                interval_end = datetime.fromisoformat(interval_end)
            
            logger.info(f"Optimizing interval: {interval_name}")
            
            # Run optimization for this interval
            opt_result = await self.optimize(
                symbol=symbol,
                timeframe=timeframe,
                start_date=interval_start,
                end_date=interval_end,
                strategy=strategy,
                param_grid=param_grid,
                optimization_target=optimization_target,
                initial_capital=initial_capital,
                max_combinations=max_combinations,
            )
            
            results.append(TimeIntervalParams(
                interval_name=interval_name,
                start_date=interval_start,
                end_date=interval_end,
                best_params=opt_result.best_params,
                return_pct=opt_result.best_return_pct,
                sharpe_ratio=opt_result.best_sharpe,
                profit_factor=opt_result.best_profit_factor,
                total_trades=opt_result.all_results[0].total_trades if opt_result.all_results else 0,
            ))
        
        # Find common optimal values
        param_stability = self._analyze_param_stability(results)
        
        total_time = time.perf_counter() - start_time
        
        return {
            "success": True,
            "optimization_id": optimization_id,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "intervals": [r.to_dict() for r in results],
            "param_stability": param_stability,
            "recommendation": self._get_interval_recommendation(param_stability),
            "total_time_seconds": round(total_time, 2),
        }
    
    async def sensitivity_analysis(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        base_params: Dict[str, Any],
        param_to_test: str,
        test_values: List[Any],
        initial_capital: float = 10000.0,
    ) -> SensitivityResult:
        """
        Analyze how sensitive the strategy is to a specific parameter.
        
        Tests the strategy with different values of one parameter while
        keeping others fixed. Helps identify which parameters matter most.
        
        Args:
            base_params: Starting parameter values
            param_to_test: Which parameter to vary
            test_values: Values to test
            
        Returns:
            SensitivityResult with performance at each value
        """
        returns = []
        sharpes = []
        
        for value in test_values:
            # Create params with this value
            test_params = base_params.copy()
            test_params[param_to_test] = value
            
            config = VectorizedBacktestConfig(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                strategy=strategy,
                strategy_params=test_params,
                initial_capital=initial_capital,
            )
            
            result = await self.engine.run(config)
            returns.append(result.total_return_pct)
            sharpes.append(result.sharpe_ratio)
        
        # Find optimal value
        best_idx = np.argmax(sharpes)
        optimal_value = test_values[best_idx]
        
        # Calculate sensitivity score (normalized std of sharpes)
        sharpe_std = np.std(sharpes)
        sharpe_range = max(sharpes) - min(sharpes)
        sensitivity_score = sharpe_range / (abs(np.mean(sharpes)) + 0.001)
        
        return SensitivityResult(
            param_name=param_to_test,
            values=test_values,
            returns=returns,
            sharpes=sharpes,
            optimal_value=optimal_value,
            sensitivity_score=sensitivity_score,
        )
    
    async def full_sensitivity_analysis(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        base_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Run sensitivity analysis on all parameters.
        
        Returns rankings of which parameters affect performance most.
        """
        if base_params is None:
            base_params = self._get_default_params(strategy)
        
        param_grid = self.DEFAULT_PARAM_GRIDS.get(strategy, {})
        
        results = []
        for param_name, values in param_grid.items():
            if len(values) < 2:
                continue
            
            logger.info(f"Testing sensitivity of {param_name}")
            
            result = await self.sensitivity_analysis(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                strategy=strategy,
                base_params=base_params,
                param_to_test=param_name,
                test_values=values,
                initial_capital=initial_capital,
            )
            results.append(result)
        
        # Rank by sensitivity
        results.sort(key=lambda r: r.sensitivity_score, reverse=True)
        
        return {
            "success": True,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "base_params": base_params,
            "sensitivity_rankings": [r.to_dict() for r in results],
            "most_sensitive_params": [r.param_name for r in results[:3]],
            "least_sensitive_params": [r.param_name for r in results[-3:]],
        }
    
    async def monte_carlo_validate(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        params: Dict[str, Any],
        num_simulations: int = 100,
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Monte Carlo validation of strategy parameters.
        
        Runs the backtest multiple times with randomized trade order
        to estimate the distribution of possible outcomes.
        
        This helps assess how much of the performance is due to
        luck vs skill.
        """
        # First, run the actual backtest to get trades
        config = VectorizedBacktestConfig(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=strategy,
            strategy_params=params,
            initial_capital=initial_capital,
        )
        
        base_result = await self.engine.run(config)
        
        if base_result.total_trades < 10:
            return {
                "success": False,
                "error": "Not enough trades for Monte Carlo simulation",
                "total_trades": base_result.total_trades,
            }
        
        # Extract trade PnLs
        trade_pnls = [t["net_pnl"] for t in base_result.trades]
        
        # Run Monte Carlo simulations
        simulated_returns = []
        simulated_drawdowns = []
        
        for _ in range(num_simulations):
            # Shuffle trades
            shuffled_pnls = trade_pnls.copy()
            random.shuffle(shuffled_pnls)
            
            # Calculate equity curve
            equity = initial_capital
            peak = equity
            max_dd = 0
            
            for pnl in shuffled_pnls:
                equity += pnl
                peak = max(peak, equity)
                dd = (peak - equity) / peak * 100
                max_dd = max(max_dd, dd)
            
            final_return = (equity / initial_capital - 1) * 100
            simulated_returns.append(final_return)
            simulated_drawdowns.append(max_dd)
        
        # Calculate statistics
        return {
            "success": True,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "params": params,
            "base_result": {
                "return_pct": round(base_result.total_return_pct, 2),
                "sharpe": round(base_result.sharpe_ratio, 2),
                "max_drawdown_pct": round(base_result.max_drawdown_pct, 2),
                "total_trades": base_result.total_trades,
            },
            "monte_carlo": {
                "num_simulations": num_simulations,
                "return_pct": {
                    "mean": round(np.mean(simulated_returns), 2),
                    "std": round(np.std(simulated_returns), 2),
                    "min": round(np.min(simulated_returns), 2),
                    "max": round(np.max(simulated_returns), 2),
                    "p5": round(np.percentile(simulated_returns, 5), 2),
                    "p25": round(np.percentile(simulated_returns, 25), 2),
                    "p50": round(np.percentile(simulated_returns, 50), 2),
                    "p75": round(np.percentile(simulated_returns, 75), 2),
                    "p95": round(np.percentile(simulated_returns, 95), 2),
                },
                "max_drawdown_pct": {
                    "mean": round(np.mean(simulated_drawdowns), 2),
                    "std": round(np.std(simulated_drawdowns), 2),
                    "p95": round(np.percentile(simulated_drawdowns, 95), 2),  # 95th percentile worst case
                },
            },
            "interpretation": self._interpret_monte_carlo(
                base_result.total_return_pct,
                simulated_returns,
            ),
        }
    
    def _get_default_params(self, strategy: str) -> Dict[str, Any]:
        """Get default/middle parameter values for a strategy."""
        param_grid = self.DEFAULT_PARAM_GRIDS.get(strategy, {})
        defaults = {}
        for name, values in param_grid.items():
            if isinstance(values[0], bool):
                defaults[name] = True
            else:
                # Use middle value
                defaults[name] = values[len(values) // 2]
        return defaults
    
    def _analyze_param_stability(self, results: List[TimeIntervalParams]) -> Dict[str, Any]:
        """Analyze how stable parameters are across intervals."""
        if not results:
            return {}
        
        # Collect all param values across intervals
        param_values = {}
        for result in results:
            for param, value in result.best_params.items():
                if param not in param_values:
                    param_values[param] = []
                param_values[param].append(value)
        
        # Calculate stability for each param
        stability = {}
        for param, values in param_values.items():
            if isinstance(values[0], bool):
                # For booleans, check consistency
                stability[param] = {
                    "values": values,
                    "most_common": max(set(values), key=values.count),
                    "consistency": values.count(max(set(values), key=values.count)) / len(values),
                }
            else:
                # For numerics, calculate CV
                stability[param] = {
                    "values": values,
                    "mean": round(np.mean(values), 2),
                    "std": round(np.std(values), 2),
                    "cv": round(np.std(values) / np.mean(values), 2) if np.mean(values) != 0 else 0,
                }
        
        return stability
    
    def _get_rolling_recommendation(self, robustness: float, avg_sharpe: float) -> str:
        """Get recommendation based on rolling optimization results."""
        if robustness >= 0.7 and avg_sharpe > 0.5:
            return "STRONG: Strategy maintains profitability across most windows. Consider deploying."
        elif robustness >= 0.5 and avg_sharpe > 0:
            return "MODERATE: Strategy shows inconsistent performance. Use with tight risk limits."
        elif robustness >= 0.3:
            return "WEAK: Strategy has high variance. Consider improving signal quality."
        else:
            return "AVOID: Strategy fails in most market conditions. Do not deploy."
    
    def _get_interval_recommendation(self, param_stability: Dict[str, Any]) -> str:
        """Get recommendation based on parameter stability."""
        if not param_stability:
            return "Unable to analyze parameter stability."
        
        # Check consistency of params
        consistent = 0
        total = 0
        for param, stats in param_stability.items():
            total += 1
            if "consistency" in stats:
                if stats["consistency"] >= 0.7:
                    consistent += 1
            elif "cv" in stats:
                if stats["cv"] < 0.3:
                    consistent += 1
        
        ratio = consistent / total if total > 0 else 0
        
        if ratio >= 0.7:
            return "STABLE: Parameters are consistent across intervals. Use averaged values."
        elif ratio >= 0.5:
            return "VARIABLE: Some parameters change significantly. Consider regime-specific configs."
        else:
            return "UNSTABLE: Parameters vary widely. Strategy may need fundamental redesign."
    
    def _interpret_monte_carlo(
        self,
        actual_return: float,
        simulated_returns: List[float],
    ) -> str:
        """Interpret Monte Carlo results."""
        percentile = sum(1 for r in simulated_returns if r < actual_return) / len(simulated_returns) * 100
        
        if percentile < 25:
            return (
                f"UNLUCKY: Actual return ({actual_return:.1f}%) is below 25th percentile. "
                "The strategy may perform better with different trade ordering."
            )
        elif percentile > 75:
            return (
                f"LUCKY: Actual return ({actual_return:.1f}%) is above 75th percentile. "
                "Expect mean reversion - future returns may be lower."
            )
        else:
            return (
                f"TYPICAL: Actual return ({actual_return:.1f}%) is within expected range. "
                "Performance is not due to unusual luck."
            )
