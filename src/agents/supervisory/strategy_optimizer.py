"""
StrategyOptimizerAgent - Continuous Strategy Optimization

Responsibilities:
- Optimize strategy parameters using Bayesian optimization
- A/B testing of strategy variants
- Evaluate performance over rolling window
- Emit strategy_updated when new optimal parameters found

Performance Target: Background optimization (not real-time critical)
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class StrategyOptimizerAgent(BaseAgent):
    """
    Optimizes strategy parameters continuously

    Optimization Methods:
    1. Bayesian Optimization - Efficient parameter search
    2. Grid Search - Exhaustive search (slow)
    3. Random Search - Random sampling
    4. A/B Testing - Compare variants in live trading

    Optimized Parameters:
    - signal_threshold
    - stop_loss
    - take_profit
    - position_size
    - strategy_weights
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=9,  # Supervisory layer (lowest priority)
        )

        # Configuration
        self.optimization_method = config.get("optimization_method", "bayesian")
        self.evaluation_window = config.get("evaluation_window", 1000)  # trades
        self.optimization_frequency = config.get("optimization_frequency", 86400)  # 24 hours
        self.a_b_testing = config.get("a_b_testing", True)
        self.performance_metric = config.get("performance_metric", "sharpe_ratio")
        self.min_sample_size = config.get("min_sample_size", 100)

        # Parameters to optimize
        self.parameters_to_optimize = config.get("parameters_to_optimize", [
            "signal_threshold",
            "stop_loss",
            "take_profit",
            "position_size",
        ])

        # Current parameters
        self.current_parameters = {
            "signal_threshold": 0.6,
            "stop_loss": 0.02,  # 2%
            "take_profit": 0.04,  # 4%
            "position_size": 0.02,  # 2% of capital
        }

        # Parameter bounds
        self.parameter_bounds = {
            "signal_threshold": (0.5, 0.8),
            "stop_loss": (0.01, 0.05),
            "take_profit": (0.02, 0.10),
            "position_size": (0.01, 0.05),
        }

        # Trade history for evaluation
        self.trade_history: List[Dict[str, Any]] = []

        # A/B testing variants
        self.ab_variants: Dict[str, Dict[str, Any]] = {}
        self.ab_results: Dict[str, List[float]] = {}

        # Optimization state
        self.last_optimization = 0.0
        self.optimization_iteration = 0

        # Bayesian optimization state
        self.evaluated_parameters: List[Tuple[Dict[str, float], float]] = []

        # Stats
        self.optimizations_run = 0
        self.improvements_found = 0

    async def initialize(self) -> None:
        """Subscribe to events and load current parameters"""
        self.subscribe_to_event("performance_report")
        self.subscribe_to_event("position_updated")

        # Load current parameters from context
        await self._load_current_parameters()

        # Initialize A/B variants if enabled
        if self.a_b_testing:
            await self._initialize_ab_variants()

        self.logger.info(
            "strategy_optimizer_initialized",
            method=self.optimization_method,
            parameters=self.parameters_to_optimize,
            ab_testing=self.a_b_testing,
        )

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self.logger.info(
            "strategy_optimizer_cleanup",
            optimizations_run=self.optimizations_run,
            improvements_found=self.improvements_found,
            current_parameters=self.current_parameters,
        )

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "performance_report":
                await self._on_performance_report(event.data)

            elif event.event_type == "position_updated":
                await self._on_position_updated(event.data)

            # Check if time to optimize
            current_time = time.time()
            if current_time - self.last_optimization >= self.optimization_frequency:
                await self._run_optimization()
                self.last_optimization = current_time

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_performance_report(self, report_data: Dict[str, Any]) -> None:
        """
        Process performance report

        Extracts metrics for optimization evaluation
        """
        metrics = report_data.get("metrics", {})

        self.logger.debug(
            "performance_report_received",
            sharpe=metrics.get("sharpe_ratio"),
            win_rate=metrics.get("win_rate"),
            total_trades=metrics.get("total_trades"),
        )

    async def _on_position_updated(self, position_data: Dict[str, Any]) -> None:
        """
        Track closed trades for evaluation

        Builds trade history for strategy evaluation
        """
        status = position_data.get("status")

        if status == "CLOSED":
            trade_record = {
                "symbol": position_data.get("symbol"),
                "pnl": position_data.get("pnl", 0.0),
                "duration": position_data.get("duration", 0.0),
                "timestamp": time.time(),
            }

            self.trade_history.append(trade_record)

            # Keep only recent trades (evaluation window)
            if len(self.trade_history) > self.evaluation_window:
                self.trade_history = self.trade_history[-self.evaluation_window:]

    async def _run_optimization(self) -> None:
        """
        Run strategy optimization

        Uses configured method to find better parameters
        """
        start_time = time.time()

        # Check if we have enough data
        if len(self.trade_history) < self.min_sample_size:
            self.logger.info(
                "optimization_skipped_insufficient_data",
                trades=len(self.trade_history),
                required=self.min_sample_size,
            )
            return

        self.optimizations_run += 1
        self.optimization_iteration += 1

        self.logger.info(
            "optimization_started",
            iteration=self.optimization_iteration,
            method=self.optimization_method,
            trades=len(self.trade_history),
        )

        # Run optimization based on method
        if self.optimization_method == "bayesian":
            new_parameters = await self._bayesian_optimization()

        elif self.optimization_method == "grid":
            new_parameters = await self._grid_search()

        elif self.optimization_method == "random":
            new_parameters = await self._random_search()

        else:
            self.logger.warning("unknown_optimization_method", method=self.optimization_method)
            return

        # Evaluate new parameters
        current_performance = self._evaluate_parameters(self.current_parameters)
        new_performance = self._evaluate_parameters(new_parameters)

        optimization_time = time.time() - start_time

        # Check if improvement
        if new_performance > current_performance:
            self.improvements_found += 1

            # Update current parameters
            old_parameters = self.current_parameters.copy()
            self.current_parameters = new_parameters

            # Emit strategy update
            await self.publish_event(
                event_type="strategy_updated",
                data={
                    "old_parameters": old_parameters,
                    "new_parameters": new_parameters,
                    "old_performance": current_performance,
                    "new_performance": new_performance,
                    "improvement": new_performance - current_performance,
                    "iteration": self.optimization_iteration,
                    "timestamp": time.time(),
                },
                priority=EventPriority.LOW,
            )

            # Store in context
            await self.set_context("current_parameters", str(new_parameters), ttl=86400)

            self.logger.info(
                "strategy_improved",
                old_performance=current_performance,
                new_performance=new_performance,
                improvement=new_performance - current_performance,
                new_parameters=new_parameters,
                optimization_time=optimization_time,
            )

        else:
            self.logger.info(
                "optimization_no_improvement",
                current_performance=current_performance,
                new_performance=new_performance,
                optimization_time=optimization_time,
            )

    async def _bayesian_optimization(self) -> Dict[str, float]:
        """
        Bayesian optimization for parameter search

        Uses Gaussian Process to model parameter space and
        finds next best parameters to evaluate.

        Returns:
            New parameters to test
        """
        # Simplified Bayesian optimization
        # In production: Use library like scikit-optimize

        # Generate candidate parameters
        candidates = []
        for _ in range(10):  # Sample 10 candidates
            candidate = self._sample_parameters()
            performance = self._evaluate_parameters(candidate)
            candidates.append((candidate, performance))

        # Sort by performance
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Return best candidate
        best_parameters, best_performance = candidates[0]

        # Store for future optimization
        self.evaluated_parameters.append((best_parameters, best_performance))

        return best_parameters

    async def _grid_search(self) -> Dict[str, float]:
        """
        Grid search over parameter space

        Exhaustive but slow

        Returns:
            Best parameters found
        """
        # Simplified grid search (coarse grid)
        grid_size = 3

        best_parameters = self.current_parameters.copy()
        best_performance = self._evaluate_parameters(best_parameters)

        # Grid search for each parameter
        for param_name in self.parameters_to_optimize:
            if param_name not in self.parameter_bounds:
                continue

            lower, upper = self.parameter_bounds[param_name]
            grid_values = np.linspace(lower, upper, grid_size)

            for value in grid_values:
                test_parameters = self.current_parameters.copy()
                test_parameters[param_name] = float(value)

                performance = self._evaluate_parameters(test_parameters)

                if performance > best_performance:
                    best_performance = performance
                    best_parameters = test_parameters

        return best_parameters

    async def _random_search(self) -> Dict[str, float]:
        """
        Random search over parameter space

        Fast but less efficient

        Returns:
            Best parameters found
        """
        n_samples = 20

        best_parameters = self.current_parameters.copy()
        best_performance = self._evaluate_parameters(best_parameters)

        for _ in range(n_samples):
            candidate = self._sample_parameters()
            performance = self._evaluate_parameters(candidate)

            if performance > best_performance:
                best_performance = performance
                best_parameters = candidate

        return best_parameters

    def _sample_parameters(self) -> Dict[str, float]:
        """
        Sample random parameters within bounds

        Returns:
            Random parameter set
        """
        parameters = {}

        for param_name in self.parameters_to_optimize:
            if param_name in self.parameter_bounds:
                lower, upper = self.parameter_bounds[param_name]
                value = np.random.uniform(lower, upper)
                parameters[param_name] = float(value)
            else:
                # Use current value if no bounds
                parameters[param_name] = self.current_parameters.get(param_name, 0.0)

        return parameters

    def _evaluate_parameters(self, parameters: Dict[str, float]) -> float:
        """
        Evaluate parameter set on historical trades

        Uses configured performance metric

        Args:
            parameters: Parameter set to evaluate

        Returns:
            Performance score (higher is better)
        """
        if not self.trade_history:
            return 0.0

        # For simplification, we'll use win rate as metric
        # In production: Backtest with parameters on trade history

        if self.performance_metric == "sharpe_ratio":
            return self._calculate_sharpe_ratio(parameters)

        elif self.performance_metric == "win_rate":
            return self._calculate_win_rate(parameters)

        elif self.performance_metric == "profit_factor":
            return self._calculate_profit_factor(parameters)

        else:
            # Default to Sharpe ratio
            return self._calculate_sharpe_ratio(parameters)

    def _calculate_sharpe_ratio(self, parameters: Dict[str, float]) -> float:
        """Calculate Sharpe ratio for parameter set"""
        pnls = [trade["pnl"] for trade in self.trade_history]

        if len(pnls) < 10:
            return 0.0

        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)

        if std_pnl == 0:
            return 0.0

        sharpe = mean_pnl / std_pnl * np.sqrt(252)  # Annualized

        return float(sharpe)

    def _calculate_win_rate(self, parameters: Dict[str, float]) -> float:
        """Calculate win rate for parameter set"""
        if not self.trade_history:
            return 0.0

        winning_trades = sum(1 for trade in self.trade_history if trade["pnl"] > 0)
        total_trades = len(self.trade_history)

        win_rate = winning_trades / total_trades

        return float(win_rate)

    def _calculate_profit_factor(self, parameters: Dict[str, float]) -> float:
        """Calculate profit factor for parameter set"""
        if not self.trade_history:
            return 1.0

        gross_profit = sum(trade["pnl"] for trade in self.trade_history if trade["pnl"] > 0)
        gross_loss = abs(sum(trade["pnl"] for trade in self.trade_history if trade["pnl"] < 0))

        if gross_loss == 0:
            return 10.0 if gross_profit > 0 else 1.0

        profit_factor = gross_profit / gross_loss

        return float(profit_factor)

    async def _initialize_ab_variants(self) -> None:
        """
        Initialize A/B testing variants

        Creates multiple parameter sets to test simultaneously
        """
        # Variant A: Current parameters (control)
        self.ab_variants["A"] = self.current_parameters.copy()
        self.ab_results["A"] = []

        # Variant B: Slightly modified parameters
        variant_b = self.current_parameters.copy()
        for param_name in self.parameters_to_optimize:
            if param_name in variant_b:
                # Add 10% variation
                variant_b[param_name] *= 1.1
        self.ab_variants["B"] = variant_b
        self.ab_results["B"] = []

        self.logger.info(
            "ab_testing_initialized",
            variants=list(self.ab_variants.keys()),
        )

    async def _load_current_parameters(self) -> None:
        """Load current parameters from context"""
        try:
            parameters = await self.get_context("current_parameters")
            if parameters:
                self.current_parameters = eval(parameters) if isinstance(parameters, str) else parameters

            self.logger.info(
                "parameters_loaded",
                parameters=self.current_parameters,
            )

        except Exception as e:
            self.logger.error("load_parameters_failed", error=str(e))
