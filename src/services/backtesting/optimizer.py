"""
Strategy Optimizer for Vectorized Backtesting Engine

Implements MetaTrader-style optimization:
- Grid search over parameter space
- Walk-forward optimization
- Multi-objective optimization (return, sharpe, drawdown)
- Parallel execution for speed

Usage:
    optimizer = StrategyOptimizer(session)
    results = await optimizer.optimize(
        symbol="CrudeOIL",
        timeframe="M5",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 1),
        strategy="crude_oil_v3",
        param_grid={
            "ema_fast": [5, 8, 10, 12],
            "ema_slow": [20, 25, 29, 35],
            "rsi_period": [8, 10, 14],
            "rsi_oversold": [25, 30, 32, 35],
            "rsi_overbought": [65, 68, 70, 75],
        },
        optimization_target="sharpe_ratio",  # or "total_return_pct", "profit_factor"
    )
"""
import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import time

import numpy as np
import pandas as pd
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.backtesting.vectorized_engine import (
    VectorizedBacktestConfig,
    VectorizedBacktestEngine,
    VectorizedBacktestResult,
)

logger = structlog.get_logger(__name__)


@dataclass
class OptimizationResult:
    """Single optimization run result."""
    params: Dict[str, Any]
    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    win_rate: float
    total_trades: int
    avg_trade_pnl: float
    execution_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "params": self.params,
            "total_return_pct": self.total_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "avg_trade_pnl": self.avg_trade_pnl,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class OptimizationSummary:
    """Summary of optimization run."""
    optimization_id: str
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    
    # Search space
    total_combinations: int
    combinations_tested: int
    param_grid: Dict[str, List[Any]]
    
    # Best results
    best_params: Dict[str, Any]
    best_return_pct: float
    best_sharpe: float
    best_profit_factor: float
    
    # All results sorted by target
    all_results: List[OptimizationResult]
    optimization_target: str
    
    # Timing
    total_time_seconds: float
    avg_time_per_test_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "optimization_id": self.optimization_id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_combinations": self.total_combinations,
            "combinations_tested": self.combinations_tested,
            "param_grid": self.param_grid,
            "best_params": self.best_params,
            "best_return_pct": self.best_return_pct,
            "best_sharpe": self.best_sharpe,
            "best_profit_factor": self.best_profit_factor,
            "optimization_target": self.optimization_target,
            "total_time_seconds": self.total_time_seconds,
            "avg_time_per_test_ms": self.avg_time_per_test_ms,
            "top_10_results": [r.to_dict() for r in self.all_results[:10]],
        }


class StrategyOptimizer:
    """
    MetaTrader-style strategy optimizer.
    
    Supports:
    - Grid search: Test all parameter combinations
    - Random search: Sample from parameter space
    - Walk-forward: Train/test split optimization
    - Multi-objective: Optimize for multiple targets
    """
    
    # Default parameter grids for each strategy
    DEFAULT_PARAM_GRIDS = {
        "ma_crossover": {
            "fast_period": [5, 8, 10, 12, 15],
            "slow_period": [20, 25, 30, 35, 40, 50],
        },
        "rsi": {
            "rsi_period": [7, 10, 14, 21],
            "rsi_oversold": [20, 25, 30, 35],
            "rsi_overbought": [65, 70, 75, 80],
        },
        "crude_oil_v3": {
            "ema_fast": [5, 8, 10, 12, 15],
            "ema_slow": [20, 25, 29, 35, 40],
            "rsi_period": [7, 10, 14],
            "rsi_oversold": [25, 30, 32, 35, 40],
            "rsi_overbought": [60, 65, 68, 70, 75],
            "cci_period": [14, 20, 25],
            "cci_oversold": [-100, -80, -60],
            "cci_overbought": [80, 100, 120],
            "atr_period": [10, 14, 20],
            "atr_sl_multiplier": [1.5, 2.0, 2.5, 3.0],
            "atr_tp_multiplier": [2.0, 2.5, 3.0, 4.0],
            "use_time_filter": [True, False],
            "trade_start_hour": [8],
            "trade_end_hour": [20],
        },
        "mean_reversion": {
            "lookback": [10, 15, 20, 25, 30],
            "std_threshold": [1.5, 2.0, 2.5, 3.0],
        },
        "value_area": {
            "lookback_periods": [12, 18, 24, 36, 48],
            "value_area_percent": [0.65, 0.68, 0.70, 0.72, 0.75],
            "tpo_resolution": [0.05, 0.10, 0.15],
            "stop_atr_multiplier": [1.0, 1.5, 2.0, 2.5],
            "min_penetration_atr": [0.2, 0.3, 0.5],
            "max_penetration_atr": [1.5, 2.0, 2.5],
        },
    }
    
    # Optimization targets
    OPTIMIZATION_TARGETS = [
        "total_return_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "profit_factor",
        "win_rate",
        # Composite targets
        "risk_adjusted_return",  # return / max_drawdown
        "expectancy",  # avg_trade_pnl * win_rate
    ]
    
    def __init__(self, session: AsyncSession):
        """Initialize optimizer with database session."""
        self.session = session
        self.engine = VectorizedBacktestEngine(session)
    
    async def optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        param_grid: Optional[Dict[str, List[Any]]] = None,
        optimization_target: str = "sharpe_ratio",
        initial_capital: float = 10000.0,
        max_combinations: Optional[int] = None,
        min_trades: int = 10,
        progress_callback: Optional[callable] = None,
    ) -> OptimizationSummary:
        """
        Run grid search optimization.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_date: Backtest start date
            end_date: Backtest end date
            strategy: Strategy name
            param_grid: Parameter grid to search (None = use defaults)
            optimization_target: Metric to optimize
            initial_capital: Starting capital
            max_combinations: Limit number of combinations (for random search)
            min_trades: Minimum trades required for valid result
            progress_callback: Callback for progress updates
            
        Returns:
            OptimizationSummary with all results
        """
        optimization_id = str(uuid4())[:8]
        start_time = time.perf_counter()
        
        logger.info(
            "optimization_starting",
            optimization_id=optimization_id,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
        )
        
        # Get parameter grid
        if param_grid is None:
            param_grid = self.DEFAULT_PARAM_GRIDS.get(strategy, {})
        
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        all_combinations = list(itertools.product(*param_values))
        total_combinations = len(all_combinations)
        
        # Limit combinations if requested
        if max_combinations and total_combinations > max_combinations:
            # Random sample
            indices = np.random.choice(
                total_combinations, 
                size=max_combinations, 
                replace=False
            )
            all_combinations = [all_combinations[i] for i in indices]
        
        logger.info(f"Testing {len(all_combinations)} parameter combinations")
        
        # Run all backtests
        results: List[OptimizationResult] = []
        tested = 0
        
        for combo in all_combinations:
            params = dict(zip(param_names, combo))
            
            try:
                # Run backtest with these params
                config = VectorizedBacktestConfig(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    strategy=strategy,
                    strategy_params=params,
                    initial_capital=initial_capital,
                )
                
                result = await self.engine.run(config)
                
                # Skip if not enough trades
                if result.total_trades < min_trades:
                    tested += 1
                    continue
                
                # Store result
                opt_result = OptimizationResult(
                    params=params,
                    total_return_pct=result.total_return_pct,
                    sharpe_ratio=result.sharpe_ratio,
                    sortino_ratio=result.sortino_ratio,
                    max_drawdown_pct=result.max_drawdown_pct,
                    profit_factor=result.profit_factor,
                    win_rate=result.win_rate,
                    total_trades=result.total_trades,
                    avg_trade_pnl=result.avg_trade_pnl,
                    execution_time_ms=result.execution_time_ms,
                )
                results.append(opt_result)
                
            except Exception as e:
                logger.warning(f"Backtest failed for params {params}: {e}")
            
            tested += 1
            
            # Progress callback
            if progress_callback:
                progress_callback(tested, len(all_combinations))
            
            # Log progress every 100 tests
            if tested % 100 == 0:
                logger.info(f"Progress: {tested}/{len(all_combinations)} ({100*tested/len(all_combinations):.1f}%)")
        
        # Sort results by optimization target
        if optimization_target == "risk_adjusted_return":
            results.sort(
                key=lambda r: r.total_return_pct / abs(r.max_drawdown_pct) if r.max_drawdown_pct != 0 else 0,
                reverse=True
            )
        elif optimization_target == "expectancy":
            results.sort(
                key=lambda r: r.avg_trade_pnl * (r.win_rate / 100),
                reverse=True
            )
        else:
            # Standard targets
            reverse = optimization_target not in ["max_drawdown_pct"]
            results.sort(key=lambda r: getattr(r, optimization_target, 0), reverse=reverse)
        
        # Calculate timing
        total_time = time.perf_counter() - start_time
        avg_time_per_test = (total_time * 1000) / tested if tested > 0 else 0
        
        # Get best result
        best = results[0] if results else None
        
        logger.info(
            "optimization_completed",
            optimization_id=optimization_id,
            combinations_tested=tested,
            valid_results=len(results),
            total_time_seconds=round(total_time, 2),
            best_return=round(best.total_return_pct, 2) if best else None,
            best_sharpe=round(best.sharpe_ratio, 2) if best else None,
        )
        
        return OptimizationSummary(
            optimization_id=optimization_id,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            total_combinations=total_combinations,
            combinations_tested=tested,
            param_grid=param_grid,
            best_params=best.params if best else {},
            best_return_pct=round(best.total_return_pct, 2) if best else 0,
            best_sharpe=round(best.sharpe_ratio, 2) if best else 0,
            best_profit_factor=round(best.profit_factor, 2) if best else 0,
            all_results=results,
            optimization_target=optimization_target,
            total_time_seconds=round(total_time, 2),
            avg_time_per_test_ms=round(avg_time_per_test, 2),
        )
    
    async def walk_forward_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        param_grid: Optional[Dict[str, List[Any]]] = None,
        optimization_target: str = "sharpe_ratio",
        train_pct: float = 0.7,
        num_folds: int = 4,
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Walk-forward optimization.
        
        Splits data into training and test periods, optimizes on training,
        validates on test. Repeats across multiple folds.
        
        Args:
            train_pct: Percentage of each fold for training (0.7 = 70%)
            num_folds: Number of walk-forward periods
            
        Returns:
            Dict with fold results and overall performance
        """
        total_days = (end_date - start_date).days
        fold_days = total_days // num_folds
        
        fold_results = []
        
        for fold in range(num_folds):
            # Calculate fold dates
            fold_start = start_date + timedelta(days=fold * fold_days)
            fold_end = fold_start + timedelta(days=fold_days)
            
            # Split into train/test
            train_days = int(fold_days * train_pct)
            train_end = fold_start + timedelta(days=train_days)
            test_start = train_end
            test_end = fold_end
            
            logger.info(
                f"Walk-forward fold {fold + 1}/{num_folds}",
                train_period=f"{fold_start.date()} to {train_end.date()}",
                test_period=f"{test_start.date()} to {test_end.date()}",
            )
            
            # Optimize on training period
            train_result = await self.optimize(
                symbol=symbol,
                timeframe=timeframe,
                start_date=fold_start,
                end_date=train_end,
                strategy=strategy,
                param_grid=param_grid,
                optimization_target=optimization_target,
                initial_capital=initial_capital,
            )
            
            # Test on out-of-sample period with best params
            test_config = VectorizedBacktestConfig(
                symbol=symbol,
                timeframe=timeframe,
                start_date=test_start,
                end_date=test_end,
                strategy=strategy,
                strategy_params=train_result.best_params,
                initial_capital=initial_capital,
            )
            
            test_result = await self.engine.run(test_config)
            
            fold_results.append({
                "fold": fold + 1,
                "train_period": f"{fold_start.date()} to {train_end.date()}",
                "test_period": f"{test_start.date()} to {test_end.date()}",
                "best_params": train_result.best_params,
                "train_return_pct": train_result.best_return_pct,
                "train_sharpe": train_result.best_sharpe,
                "test_return_pct": round(test_result.total_return_pct, 2),
                "test_sharpe": round(test_result.sharpe_ratio, 2),
                "test_trades": test_result.total_trades,
            })
        
        # Calculate overall metrics
        avg_train_return = np.mean([f["train_return_pct"] for f in fold_results])
        avg_test_return = np.mean([f["test_return_pct"] for f in fold_results])
        avg_train_sharpe = np.mean([f["train_sharpe"] for f in fold_results])
        avg_test_sharpe = np.mean([f["test_sharpe"] for f in fold_results])
        
        # Robustness ratio (test/train performance)
        robustness_return = avg_test_return / avg_train_return if avg_train_return != 0 else 0
        robustness_sharpe = avg_test_sharpe / avg_train_sharpe if avg_train_sharpe != 0 else 0
        
        return {
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "num_folds": num_folds,
            "train_pct": train_pct,
            "fold_results": fold_results,
            "summary": {
                "avg_train_return_pct": round(avg_train_return, 2),
                "avg_test_return_pct": round(avg_test_return, 2),
                "avg_train_sharpe": round(avg_train_sharpe, 2),
                "avg_test_sharpe": round(avg_test_sharpe, 2),
                "robustness_ratio_return": round(robustness_return, 2),
                "robustness_ratio_sharpe": round(robustness_sharpe, 2),
            },
            "recommendation": self._get_recommendation(robustness_return, robustness_sharpe),
        }
    
    def _get_recommendation(self, robustness_return: float, robustness_sharpe: float) -> str:
        """Get recommendation based on walk-forward results."""
        if robustness_return >= 0.7 and robustness_sharpe >= 0.7:
            return "STRONG: Strategy shows good out-of-sample performance. Safe to deploy."
        elif robustness_return >= 0.5 and robustness_sharpe >= 0.5:
            return "MODERATE: Strategy has reasonable robustness. Consider with caution."
        elif robustness_return >= 0.3 or robustness_sharpe >= 0.3:
            return "WEAK: Strategy shows significant overfitting. Needs improvement."
        else:
            return "AVOID: Strategy is heavily overfit to historical data. Do not deploy."
    
    async def quick_scan(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str,
        num_samples: int = 100,
        initial_capital: float = 10000.0,
    ) -> OptimizationSummary:
        """
        Quick random search for fast parameter discovery.
        
        Randomly samples from parameter space for faster iteration.
        Good for initial exploration before full grid search.
        """
        param_grid = self.DEFAULT_PARAM_GRIDS.get(strategy, {})
        
        return await self.optimize(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=strategy,
            param_grid=param_grid,
            max_combinations=num_samples,
            initial_capital=initial_capital,
        )
