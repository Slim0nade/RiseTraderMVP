"""
Autonomous Optimizer — Karpathy-style continuous improvement loop.

Runs in the background and, for each strategy group:
  1. Backtest with current parameters
  2. Analyze results (Sharpe, drawdown, profit factor)
  3. Perturb parameters in the direction that improves the target metric
  4. Repeat

This is NOT a brute-force grid search — it uses a simple hill-climbing
approach with random restarts, inspired by Andrej Karpathy's "most common
neural net mistakes" philosophy: measure → adjust → measure.

The optimizer writes its findings to the database (optimization_results table)
and logs every adjustment so the decision trail is auditable.

Usage:
    optimizer = AutonomousOptimizer()
    asyncio.create_task(optimizer.run())
"""
import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from src.services.backtesting.optimizer import StrategyOptimizer, OptimizationResult
from src.services.backtesting.vectorized_engine import (
    VectorizedBacktestConfig,
    VectorizedBacktestEngine,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Strategy groups — each group defines symbols × strategies to optimize
# ---------------------------------------------------------------------------
STRATEGY_GROUPS = {
    "energy": {
        "symbols": ["CrudeOIL", "BRENT_OIL"],
        "strategies": ["crude_oil_v3", "value_area", "ml_reversal"],
        "timeframe": "H1",
    },
    "equities": {
        "symbols": ["USA500"],
        "strategies": ["value_area", "ma_crossover", "ml_reversal"],
        "timeframe": "H1",
    },
    "forex": {
        "symbols": ["GBPJPY"],
        "strategies": ["gbpjpy_carry", "ma_crossover"],
        "timeframe": "H1",
    },
    "agriculture": {
        "symbols": ["CORN", "WHEAT"],
        "strategies": ["seasonal_ma_corn", "seasonal_ma_wheat"],
        "timeframe": "H1",
    },
}


@dataclass
class OptimizationRun:
    """Record of one optimization iteration."""
    strategy: str
    symbol: str
    timeframe: str
    params: Dict[str, Any]
    sharpe: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    win_rate: float
    total_trades: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "params": self.params,
            "sharpe": self.sharpe,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "timestamp": self.timestamp.isoformat(),
        }


class AutonomousOptimizer:
    """
    Continuously improves strategy parameters via hill-climbing.

    Algorithm per (strategy, symbol):
      1. Start with current best params (or defaults from StrategyOptimizer).
      2. Run a backtest → measure Sharpe.
      3. Perturb one parameter by ±step.
      4. Run backtest with perturbed params.
      5. If Sharpe improved → accept. Otherwise → reject.
      6. Every N iterations, random restart to escape local optima.
      7. Log every decision.
      8. Sleep cycle_seconds between iterations.
    """

    def __init__(
        self,
        cycle_seconds: int = 600,
        lookback_days: int = 365,
        random_restart_every: int = 20,
        improvement_threshold: float = 0.05,
        initial_capital: float = 10000.0,
    ):
        self.cycle_seconds = cycle_seconds
        self.lookback_days = lookback_days
        self.random_restart_every = random_restart_every
        self.improvement_threshold = improvement_threshold
        self.initial_capital = initial_capital

        self.running = False

        # Best known params and Sharpe per (strategy, symbol)
        self._best: Dict[Tuple[str, str], OptimizationRun] = {}
        self._iteration_count: Dict[Tuple[str, str], int] = {}

        # Full history for analysis
        self._history: List[OptimizationRun] = []

        logger.info(
            "autonomous_optimizer_initialized",
            cycle_seconds=cycle_seconds,
            lookback_days=lookback_days,
            groups=list(STRATEGY_GROUPS.keys()),
        )

    @property
    def best_params(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Return current best params for each (strategy, symbol) pair."""
        return {k: v.params for k, v in self._best.items()}

    @property
    def history(self) -> List[OptimizationRun]:
        return self._history

    async def run(self) -> None:
        """Main loop — cycles through all strategy groups continuously."""
        self.running = True
        logger.info("autonomous_optimizer_started")

        while self.running:
            for group_name, group in STRATEGY_GROUPS.items():
                if not self.running:
                    break
                for symbol in group["symbols"]:
                    for strategy in group["strategies"]:
                        if not self.running:
                            break
                        try:
                            await self._optimize_one(
                                strategy=strategy,
                                symbol=symbol,
                                timeframe=group["timeframe"],
                            )
                        except Exception:
                            logger.exception(
                                "autonomous_opt_error",
                                strategy=strategy,
                                symbol=symbol,
                            )

            # Sleep between full cycles
            try:
                await asyncio.sleep(self.cycle_seconds)
            except asyncio.CancelledError:
                self.running = False
                break

        logger.info("autonomous_optimizer_stopped")

    def stop(self) -> None:
        self.running = False

    async def _optimize_one(
        self, strategy: str, symbol: str, timeframe: str
    ) -> None:
        """
        Run one hill-climbing iteration for a single (strategy, symbol) pair.
        """
        from src.api.dependencies import get_db_context

        key = (strategy, symbol)
        iteration = self._iteration_count.get(key, 0)
        self._iteration_count[key] = iteration + 1

        end_date = datetime.now(tz=timezone.utc)
        start_date = end_date - timedelta(days=self.lookback_days)

        # Get default param grid for this strategy
        param_grid = StrategyOptimizer.DEFAULT_PARAM_GRIDS.get(strategy)
        if not param_grid:
            return

        # Determine current best params or use defaults
        if key in self._best:
            current_params = dict(self._best[key].params)
        else:
            # Use midpoint of each parameter range as starting point
            current_params = {}
            for pname, pvalues in param_grid.items():
                if isinstance(pvalues[0], bool):
                    current_params[pname] = pvalues[0]
                else:
                    mid_idx = len(pvalues) // 2
                    current_params[pname] = pvalues[mid_idx]

        # Random restart periodically to escape local optima
        if iteration > 0 and iteration % self.random_restart_every == 0:
            current_params = self._random_params(param_grid)
            logger.info(
                "autonomous_opt_random_restart",
                strategy=strategy,
                symbol=symbol,
                iteration=iteration,
            )

        # Run baseline backtest with current params
        async with get_db_context() as session:
            baseline = await self._backtest(
                session, strategy, symbol, timeframe, current_params, start_date, end_date
            )

        if baseline is None:
            return

        # Perturb one random parameter
        perturbed_params = self._perturb(current_params, param_grid)

        # Run perturbed backtest
        async with get_db_context() as session:
            candidate = await self._backtest(
                session, strategy, symbol, timeframe, perturbed_params, start_date, end_date
            )

        if candidate is None:
            return

        # Compare Sharpe ratios
        baseline_sharpe = baseline.sharpe_ratio
        candidate_sharpe = candidate.sharpe_ratio

        accepted = candidate_sharpe > baseline_sharpe + self.improvement_threshold

        run = OptimizationRun(
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            params=perturbed_params if accepted else current_params,
            sharpe=candidate_sharpe if accepted else baseline_sharpe,
            total_return_pct=candidate.total_return_pct if accepted else baseline.total_return_pct,
            max_drawdown_pct=candidate.max_drawdown_pct if accepted else baseline.max_drawdown_pct,
            profit_factor=candidate.profit_factor if accepted else baseline.profit_factor,
            win_rate=candidate.win_rate if accepted else baseline.win_rate,
            total_trades=candidate.total_trades if accepted else baseline.total_trades,
        )

        self._history.append(run)
        # Cap history to prevent memory leak
        if len(self._history) > 5000:
            self._history = self._history[-2500:]

        if accepted:
            self._best[key] = run
            logger.info(
                "autonomous_opt_improvement",
                strategy=strategy,
                symbol=symbol,
                old_sharpe=round(baseline_sharpe, 3),
                new_sharpe=round(candidate_sharpe, 3),
                delta=round(candidate_sharpe - baseline_sharpe, 3),
                params=perturbed_params,
                iteration=iteration,
            )
        else:
            # Keep current best
            if key not in self._best:
                self._best[key] = run
            logger.debug(
                "autonomous_opt_no_improvement",
                strategy=strategy,
                symbol=symbol,
                baseline_sharpe=round(baseline_sharpe, 3),
                candidate_sharpe=round(candidate_sharpe, 3),
                iteration=iteration,
            )

    async def _backtest(
        self,
        session,
        strategy: str,
        symbol: str,
        timeframe: str,
        params: Dict[str, Any],
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[OptimizationResult]:
        """Run a single backtest and return the result."""
        try:
            optimizer = StrategyOptimizer(session)
            result = await optimizer._run_single_backtest(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                strategy=strategy,
                params=params,
                initial_capital=self.initial_capital,
            )

            if result.total_trades < 5:
                return None

            return OptimizationResult(
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
        except Exception as e:
            logger.debug("backtest_failed", strategy=strategy, symbol=symbol, error=str(e))
            return None

    def _perturb(
        self, params: Dict[str, Any], param_grid: Dict[str, list]
    ) -> Dict[str, Any]:
        """
        Perturb one random parameter by moving to an adjacent value
        in the param grid.
        """
        result = dict(params)
        tunable = [k for k in param_grid if k in result and len(param_grid[k]) > 1]
        if not tunable:
            return result

        key = random.choice(tunable)
        grid_values = param_grid[key]
        current_val = result[key]

        # Find closest index
        try:
            idx = grid_values.index(current_val)
        except ValueError:
            # Current value not in grid — pick a random one
            result[key] = random.choice(grid_values)
            return result

        # Move ±1 step
        if idx == 0:
            new_idx = 1
        elif idx == len(grid_values) - 1:
            new_idx = idx - 1
        else:
            new_idx = idx + random.choice([-1, 1])

        result[key] = grid_values[new_idx]
        return result

    def _random_params(self, param_grid: Dict[str, list]) -> Dict[str, Any]:
        """Generate a fully random parameter set from the grid."""
        return {k: random.choice(v) for k, v in param_grid.items()}

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of all best results found so far."""
        summary = {}
        for (strategy, symbol), run in self._best.items():
            summary[f"{strategy}_{symbol}"] = {
                "sharpe": round(run.sharpe, 3),
                "return_pct": round(run.total_return_pct, 2),
                "max_dd_pct": round(run.max_drawdown_pct, 2),
                "profit_factor": round(run.profit_factor, 2),
                "trades": run.total_trades,
                "params": run.params,
            }
        return summary
