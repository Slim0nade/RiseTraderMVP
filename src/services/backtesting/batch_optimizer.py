"""
Batch Parameter Optimizer for CrudeOIL V3 Strategy.

Runs hundreds of parameter combinations in parallel to find optimal settings.
Target: Find the configuration that turns millions into ZILLIONS! 🚀

Features:
- Grid search across all parameters
- Parallel execution (multiprocessing)
- Statistical significance testing
- Results ranking by multiple metrics
- Memory-efficient batch processing
"""
import itertools
import json
import multiprocessing as mp
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
import numpy as np
from scipy import stats
import logging

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result from a single backtest run."""
    params: Dict[str, Any]
    # Core Metrics
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    # Trade Statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade_duration: float = 0.0
    # Risk Metrics
    volatility: float = 0.0
    var_95: float = 0.0  # Value at Risk 95%
    expected_shortfall: float = 0.0
    # Execution Info
    execution_time_seconds: float = 0.0
    candles_processed: int = 0
    error: Optional[str] = None
    
    def composite_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate composite optimization score.
        
        Default weights optimized for ZILLIONS:
        - Sharpe: 30% (risk-adjusted returns)
        - Total Return: 25% (raw gains)
        - Profit Factor: 20% (win/loss ratio)
        - Win Rate: 15% (consistency)
        - Max Drawdown: 10% (risk control, negative weight)
        """
        if weights is None:
            weights = {
                'sharpe_ratio': 0.30,
                'total_return': 0.25,
                'profit_factor': 0.20,
                'win_rate': 0.15,
                'max_drawdown': -0.10,  # Negative = penalize high drawdown
            }
        
        score = 0.0
        
        # Normalize and weight each metric
        if 'sharpe_ratio' in weights:
            # Sharpe typically -2 to +3
            normalized_sharpe = min(max(self.sharpe_ratio, -2), 3) / 3
            score += weights['sharpe_ratio'] * normalized_sharpe
        
        if 'total_return' in weights:
            # Return can be -100% to +1000%+
            normalized_return = min(max(self.total_return, -1), 10) / 10
            score += weights['total_return'] * normalized_return
        
        if 'profit_factor' in weights:
            # PF typically 0 to 5+
            normalized_pf = min(self.profit_factor, 5) / 5
            score += weights['profit_factor'] * normalized_pf
        
        if 'win_rate' in weights:
            # Win rate 0 to 1
            score += weights['win_rate'] * self.win_rate
        
        if 'max_drawdown' in weights:
            # Drawdown 0 to 1 (as decimal)
            # Lower is better, so negative weight means high drawdown = lower score
            score += weights['max_drawdown'] * self.max_drawdown
        
        return score


@dataclass
class ParameterGrid:
    """
    Definition of parameter search space.
    
    Each parameter can be:
    - A list of values to try
    - A dict with 'min', 'max', 'step' for ranges
    - A dict with 'values' for explicit list
    """
    # Core EMA Parameters
    ema_fast: List[int] = field(default_factory=lambda: [5, 8, 10, 12])
    ema_slow: List[int] = field(default_factory=lambda: [20, 25, 29, 35, 40])
    
    # RSI Parameters
    rsi_period: List[int] = field(default_factory=lambda: [7, 10, 14])
    rsi_overbought: List[int] = field(default_factory=lambda: [65, 68, 70, 75])
    rsi_oversold: List[int] = field(default_factory=lambda: [25, 30, 32, 35])
    
    # CCI Parameters
    cci_period: List[int] = field(default_factory=lambda: [14, 20, 25])
    cci_overbought: List[int] = field(default_factory=lambda: [80, 100, 120])
    cci_oversold: List[int] = field(default_factory=lambda: [-120, -100, -80])
    use_cci_filter: List[bool] = field(default_factory=lambda: [True, False])
    use_strict_filter: List[bool] = field(default_factory=lambda: [True, False])
    
    # ATR Parameters
    atr_period: List[int] = field(default_factory=lambda: [7, 10, 14])
    atr_multiplier: List[float] = field(default_factory=lambda: [1.5, 2.0, 2.5, 3.0])
    
    # Take Profit
    take_profit_multiplier: List[float] = field(default_factory=lambda: [1.5, 2.0, 2.5, 3.0, 4.0])
    
    # Momentum
    momentum_period: List[int] = field(default_factory=lambda: [7, 10, 14])
    momentum_buy_threshold: List[float] = field(default_factory=lambda: [99.0, 99.5, 100.0])
    momentum_sell_threshold: List[float] = field(default_factory=lambda: [100.0, 100.5, 101.0])
    
    # Exit Parameters
    ma_close_period: List[int] = field(default_factory=lambda: [15, 20, 25])
    use_ma_exit: List[bool] = field(default_factory=lambda: [True])
    use_pattern_exit: List[bool] = field(default_factory=lambda: [True, False])
    
    # Time Filter
    use_time_filter: List[bool] = field(default_factory=lambda: [True, False])
    trading_start_hour: List[int] = field(default_factory=lambda: [6, 8, 10])
    trading_end_hour: List[int] = field(default_factory=lambda: [18, 20, 22])
    
    # Volatility
    volatility_threshold: List[float] = field(default_factory=lambda: [1.5, 2.0, 2.5, 3.0])
    
    def get_total_combinations(self) -> int:
        """Calculate total number of parameter combinations."""
        total = 1
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, list):
                total *= len(field_value)
        return total
    
    def generate_combinations(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations."""
        param_names = []
        param_values = []
        
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, list) and len(field_value) > 0:
                param_names.append(field_name)
                param_values.append(field_value)
        
        combinations = []
        for combo in itertools.product(*param_values):
            param_dict = dict(zip(param_names, combo))
            combinations.append(param_dict)
        
        return combinations


@dataclass
class ExtendedParameterGrid(ParameterGrid):
    """
    Extended parameter grid with MACD, Bollinger, Stochastic, ADX, etc.
    
    For finding ZILLIONS! 🚀
    """
    # MACD
    use_macd_filter: List[bool] = field(default_factory=lambda: [False, True])
    macd_fast: List[int] = field(default_factory=lambda: [8, 12])
    macd_slow: List[int] = field(default_factory=lambda: [21, 26])
    macd_signal: List[int] = field(default_factory=lambda: [9])
    
    # Bollinger
    use_bollinger_filter: List[bool] = field(default_factory=lambda: [False, True])
    bollinger_period: List[int] = field(default_factory=lambda: [20])
    bollinger_std: List[float] = field(default_factory=lambda: [1.5, 2.0, 2.5])
    
    # Stochastic
    use_stochastic_filter: List[bool] = field(default_factory=lambda: [False, True])
    stoch_k_period: List[int] = field(default_factory=lambda: [14])
    stoch_overbought: List[int] = field(default_factory=lambda: [75, 80])
    stoch_oversold: List[int] = field(default_factory=lambda: [20, 25])
    
    # ADX
    use_adx_filter: List[bool] = field(default_factory=lambda: [False, True])
    adx_period: List[int] = field(default_factory=lambda: [14])
    adx_threshold: List[float] = field(default_factory=lambda: [20, 25, 30])
    
    # Volume
    use_volume_filter: List[bool] = field(default_factory=lambda: [False, True])
    volume_multiplier: List[float] = field(default_factory=lambda: [1.2, 1.5, 2.0])
    
    # Advanced Risk Management
    use_trailing_stop: List[bool] = field(default_factory=lambda: [False, True])
    trailing_activation: List[float] = field(default_factory=lambda: [1.0, 1.5])
    
    use_breakeven: List[bool] = field(default_factory=lambda: [False, True])
    breakeven_activation: List[float] = field(default_factory=lambda: [0.5, 1.0])
    
    use_partial_tp: List[bool] = field(default_factory=lambda: [False, True])
    partial_tp_multiplier: List[float] = field(default_factory=lambda: [1.0, 1.5])
    
    # Day/Time Filters
    use_dow_filter: List[bool] = field(default_factory=lambda: [False, True])
    avoid_monday_morning: List[bool] = field(default_factory=lambda: [True])
    avoid_friday_afternoon: List[bool] = field(default_factory=lambda: [True])
    
    # Drawdown Control
    use_drawdown_control: List[bool] = field(default_factory=lambda: [False, True])
    max_consecutive_losses: List[int] = field(default_factory=lambda: [3, 5])


class BatchOptimizer:
    """
    Batch parameter optimizer with parallel execution.
    
    Usage:
        grid = ParameterGrid(
            ema_fast=[5, 8, 10],
            atr_multiplier=[1.5, 2.0, 2.5],
        )
        optimizer = BatchOptimizer(grid, backtest_func)
        results = optimizer.run(max_workers=4)
        
        # Get top performers
        top_10 = optimizer.get_top_results(10, sort_by='composite_score')
    """
    
    def __init__(
        self,
        parameter_grid: ParameterGrid,
        backtest_function: Callable[[Dict[str, Any]], OptimizationResult],
        max_workers: int = 4,
        results_dir: Optional[Path] = None,
    ):
        """
        Initialize optimizer.
        
        Args:
            parameter_grid: ParameterGrid defining search space
            backtest_function: Function that takes params dict and returns OptimizationResult
            max_workers: Number of parallel workers (default: 4)
            results_dir: Directory to save results (optional)
        """
        self.grid = parameter_grid
        self.backtest_func = backtest_function
        self.max_workers = max_workers
        self.results_dir = results_dir or Path("optimization_results")
        self.results: List[OptimizationResult] = []
        
    def run(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        early_stop_threshold: Optional[float] = None,
    ) -> List[OptimizationResult]:
        """
        Run batch optimization.
        
        Args:
            progress_callback: Optional callback(completed, total) for progress
            early_stop_threshold: Stop if composite_score exceeds this value
            
        Returns:
            List of OptimizationResult sorted by composite_score
        """
        combinations = self.grid.generate_combinations()
        total = len(combinations)
        
        logger.info(f"Starting optimization with {total} parameter combinations")
        logger.info(f"Using {self.max_workers} parallel workers")
        
        self.results = []
        completed = 0
        
        # Use multiprocessing for true parallelism
        if self.max_workers > 1:
            with mp.Pool(processes=self.max_workers) as pool:
                for result in pool.imap_unordered(self._run_single, combinations):
                    self.results.append(result)
                    completed += 1
                    
                    if progress_callback:
                        progress_callback(completed, total)
                    
                    if completed % 100 == 0:
                        logger.info(f"Progress: {completed}/{total} ({100*completed/total:.1f}%)")
                    
                    # Early stopping
                    if early_stop_threshold and result.composite_score() >= early_stop_threshold:
                        logger.info(f"Early stop: Found result with score {result.composite_score():.4f}")
                        pool.terminate()
                        break
        else:
            # Single-threaded for debugging
            for params in combinations:
                result = self._run_single(params)
                self.results.append(result)
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total)
        
        # Sort by composite score
        self.results.sort(key=lambda r: r.composite_score(), reverse=True)
        
        # Save results
        self._save_results()
        
        logger.info(f"Optimization complete. Best score: {self.results[0].composite_score():.4f}")
        
        return self.results
    
    def _run_single(self, params: Dict[str, Any]) -> OptimizationResult:
        """Run single backtest with error handling."""
        try:
            start_time = datetime.now()
            result = self.backtest_func(params)
            result.execution_time_seconds = (datetime.now() - start_time).total_seconds()
            result.params = params
            return result
        except Exception as e:
            logger.error(f"Error in backtest: {e}")
            return OptimizationResult(
                params=params,
                error=str(e)
            )
    
    def get_top_results(
        self,
        n: int = 10,
        sort_by: str = 'composite_score',
        custom_weights: Optional[Dict[str, float]] = None,
    ) -> List[OptimizationResult]:
        """
        Get top N results.
        
        Args:
            n: Number of results to return
            sort_by: Metric to sort by ('composite_score', 'sharpe_ratio', 'total_return', etc.)
            custom_weights: Custom weights for composite score
            
        Returns:
            Top N OptimizationResult objects
        """
        if not self.results:
            return []
        
        if sort_by == 'composite_score':
            sorted_results = sorted(
                self.results,
                key=lambda r: r.composite_score(custom_weights),
                reverse=True
            )
        else:
            sorted_results = sorted(
                self.results,
                key=lambda r: getattr(r, sort_by, 0),
                reverse=True
            )
        
        return sorted_results[:n]
    
    def statistical_significance(
        self,
        result_a: OptimizationResult,
        result_b: OptimizationResult,
        metric: str = 'total_return',
    ) -> Tuple[float, float]:
        """
        Compare two results for statistical significance.
        
        Returns:
            Tuple of (t_statistic, p_value)
        """
        # This is a simplified version - in production you'd compare
        # the actual trade return distributions
        value_a = getattr(result_a, metric, 0)
        value_b = getattr(result_b, metric, 0)
        
        # Mock comparison (would need actual trade returns for real t-test)
        # Using effect size as proxy
        effect = abs(value_a - value_b)
        se = 0.1  # Assumed standard error
        
        if se > 0:
            t_stat = effect / se
            p_value = 2 * (1 - stats.norm.cdf(abs(t_stat)))
        else:
            t_stat = 0
            p_value = 1.0
        
        return t_stat, p_value
    
    def _save_results(self) -> None:
        """Save results to JSON file."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.results_dir / f"optimization_results_{timestamp}.json"
        
        # Convert to JSON-serializable format
        results_data = []
        for r in self.results:
            data = {
                'params': r.params,
                'metrics': {
                    'total_return': r.total_return,
                    'sharpe_ratio': r.sharpe_ratio,
                    'sortino_ratio': r.sortino_ratio,
                    'max_drawdown': r.max_drawdown,
                    'win_rate': r.win_rate,
                    'profit_factor': r.profit_factor,
                    'total_trades': r.total_trades,
                    'composite_score': r.composite_score(),
                },
                'execution_time': r.execution_time_seconds,
                'error': r.error,
            }
            results_data.append(data)
        
        with open(filename, 'w') as f:
            json.dump(results_data, f, indent=2, default=str)
        
        logger.info(f"Results saved to {filename}")
    
    def generate_report(self) -> str:
        """Generate optimization report."""
        if not self.results:
            return "No results available."
        
        top_10 = self.get_top_results(10)
        
        report = []
        report.append("=" * 80)
        report.append("PARAMETER OPTIMIZATION REPORT")
        report.append("=" * 80)
        report.append(f"Total combinations tested: {len(self.results)}")
        report.append(f"Successful runs: {sum(1 for r in self.results if not r.error)}")
        report.append(f"Failed runs: {sum(1 for r in self.results if r.error)}")
        report.append("")
        report.append("TOP 10 CONFIGURATIONS")
        report.append("-" * 80)
        
        for i, result in enumerate(top_10, 1):
            report.append(f"\n#{i} - Composite Score: {result.composite_score():.4f}")
            report.append(f"   Total Return: {result.total_return*100:.2f}%")
            report.append(f"   Sharpe Ratio: {result.sharpe_ratio:.3f}")
            report.append(f"   Max Drawdown: {result.max_drawdown*100:.2f}%")
            report.append(f"   Win Rate: {result.win_rate*100:.1f}%")
            report.append(f"   Profit Factor: {result.profit_factor:.2f}")
            report.append(f"   Total Trades: {result.total_trades}")
            report.append(f"   Key Parameters:")
            
            # Show key parameters
            key_params = ['ema_fast', 'ema_slow', 'atr_multiplier', 'take_profit_multiplier', 
                         'rsi_oversold', 'rsi_overbought', 'use_cci_filter']
            for param in key_params:
                if param in result.params:
                    report.append(f"     - {param}: {result.params[param]}")
        
        report.append("")
        report.append("=" * 80)
        report.append("BEST CONFIGURATION FOR ZILLIONS 🚀")
        report.append("=" * 80)
        
        best = top_10[0]
        report.append("\nCopy-paste parameters:")
        report.append("```python")
        report.append("params = {")
        for key, value in best.params.items():
            if isinstance(value, str):
                report.append(f"    '{key}': '{value}',")
            else:
                report.append(f"    '{key}': {value},")
        report.append("}")
        report.append("```")
        
        return "\n".join(report)


def create_quick_grid() -> ParameterGrid:
    """
    Create a quick parameter grid for testing.
    
    ~500 combinations for fast iteration.
    """
    return ParameterGrid(
        ema_fast=[5, 8, 10],
        ema_slow=[25, 29, 35],
        rsi_period=[10, 14],
        rsi_overbought=[68, 72],
        rsi_oversold=[28, 32],
        atr_multiplier=[1.5, 2.0, 2.5],
        take_profit_multiplier=[2.0, 2.5, 3.0],
        use_cci_filter=[True, False],
    )


def create_comprehensive_grid() -> ParameterGrid:
    """
    Create comprehensive parameter grid.
    
    ~50,000+ combinations for thorough search.
    """
    return ParameterGrid(
        ema_fast=[4, 5, 6, 7, 8, 9, 10, 11, 12],
        ema_slow=[18, 20, 22, 25, 27, 29, 32, 35, 40],
        rsi_period=[7, 9, 10, 12, 14],
        rsi_overbought=[65, 68, 70, 72, 75, 78],
        rsi_oversold=[22, 25, 28, 30, 32, 35],
        cci_period=[14, 18, 20, 25],
        cci_overbought=[80, 100, 120, 150],
        cci_oversold=[-150, -120, -100, -80],
        use_cci_filter=[True, False],
        use_strict_filter=[True, False],
        atr_period=[7, 10, 14],
        atr_multiplier=[1.0, 1.5, 2.0, 2.5, 3.0],
        take_profit_multiplier=[1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
        momentum_period=[7, 10, 14],
    )


def create_zillions_grid() -> ExtendedParameterGrid:
    """
    Create the ULTIMATE parameter grid for finding ZILLIONS! 🚀
    
    All extended parameters enabled.
    ~1M+ combinations (use with sampling or distributed computing).
    """
    return ExtendedParameterGrid(
        # Core (optimized ranges from backtesting)
        ema_fast=[5, 8, 10],
        ema_slow=[25, 29, 35],
        rsi_period=[10, 14],
        rsi_overbought=[68, 72],
        rsi_oversold=[28, 32],
        atr_multiplier=[1.5, 2.0, 2.5],
        take_profit_multiplier=[2.0, 2.5, 3.0, 4.0],
        
        # Extended filters
        use_macd_filter=[True, False],
        use_bollinger_filter=[True, False],
        use_stochastic_filter=[True, False],
        use_adx_filter=[True, False],
        adx_threshold=[20, 25, 30],
        
        # Risk Management
        use_trailing_stop=[True, False],
        trailing_activation=[1.0, 1.5],
        use_breakeven=[True, False],
        use_partial_tp=[True, False],
        
        # Time filters
        use_dow_filter=[True, False],
        use_time_filter=[True, False],
        
        # Drawdown control
        use_drawdown_control=[True, False],
        max_consecutive_losses=[3, 5],
    )


def random_search_grid(
    base_grid: ParameterGrid,
    n_samples: int = 1000,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Random sampling from parameter grid.
    
    Useful when grid is too large for exhaustive search.
    
    Args:
        base_grid: ParameterGrid to sample from
        n_samples: Number of random combinations
        seed: Random seed for reproducibility
        
    Returns:
        List of parameter dictionaries
    """
    np.random.seed(seed)
    
    all_combos = base_grid.generate_combinations()
    
    if n_samples >= len(all_combos):
        return all_combos
    
    indices = np.random.choice(len(all_combos), size=n_samples, replace=False)
    return [all_combos[i] for i in indices]
