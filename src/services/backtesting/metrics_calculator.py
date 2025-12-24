"""
Performance metrics calculation for backtesting.

Computes Sharpe ratio, maximum drawdown, win rate, profit factor,
and other trading performance metrics from backtest results.

T119: Optional Numba JIT compilation for 10-20x performance boost.
Set USE_OPTIMIZED_METRICS=True to enable (requires: pip install numba).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
import os

import math
import numpy as np
from scipy import stats

# T119: Optional optimized metrics (Numba JIT)
# Enable with environment variable: USE_OPTIMIZED_METRICS=1
USE_OPTIMIZED_METRICS = os.getenv("USE_OPTIMIZED_METRICS", "0") == "1"

if USE_OPTIMIZED_METRICS:
    try:
        from .metrics_optimized import (
            calculate_sharpe_ratio_fast,
            calculate_sortino_ratio_fast,
            calculate_max_drawdown_fast,
            calculate_consecutive_trades_fast,
            calculate_profit_factor_fast,
            calculate_win_rate_fast,
            is_numba_available,
        )
        OPTIMIZED_AVAILABLE = is_numba_available()
    except ImportError:
        OPTIMIZED_AVAILABLE = False
        USE_OPTIMIZED_METRICS = False
else:
    OPTIMIZED_AVAILABLE = False


@dataclass
class PerformanceMetrics:
    """
    Complete set of backtest performance metrics.

    Attributes:
        total_return_pct: Total return percentage
        sharpe_ratio: Annualized Sharpe ratio
        max_drawdown_pct: Maximum drawdown percentage
        max_drawdown_duration_days: Longest drawdown duration
        win_rate: Percentage of winning trades (0-1)
        total_trades: Total number of closed trades
        avg_trade_duration_hours: Average holding period
        profit_factor: Gross profit / gross loss ratio
        final_capital: Ending account balance
        avg_win: Average winning trade P&L
        avg_loss: Average losing trade P&L
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
        consecutive_wins_max: Maximum consecutive wins
        consecutive_losses_max: Maximum consecutive losses
        sortino_ratio: Sortino ratio (downside deviation)
        calmar_ratio: Calmar ratio (return / max drawdown)
    """

    total_return_pct: Decimal
    sharpe_ratio: Decimal
    max_drawdown_pct: Decimal
    max_drawdown_duration_days: int
    win_rate: Decimal
    total_trades: int
    avg_trade_duration_hours: Decimal
    profit_factor: Decimal
    final_capital: Decimal
    avg_win: Decimal
    avg_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    consecutive_wins_max: int
    consecutive_losses_max: int
    sortino_ratio: Decimal
    calmar_ratio: Decimal

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for JSON serialization."""
        # Helper to sanitize Decimal values before converting to float
        def safe_float(value: Decimal) -> float:
            f = float(value)
            return 0.0 if (math.isnan(f) or math.isinf(f)) else f

        # Calculate absolute returns and drawdown
        total_return_abs = safe_float(self.final_capital - (self.final_capital / (1 + self.total_return_pct / 100)))
        max_drawdown_abs = safe_float(self.final_capital * (self.max_drawdown_pct / 100))

        # Calculate winning/losing trade counts from metrics
        winning_trades = int(self.total_trades * safe_float(self.win_rate))
        losing_trades = self.total_trades - winning_trades

        return {
            "total_return_pct": safe_float(self.total_return_pct),
            "total_return_abs": total_return_abs,
            "sharpe_ratio": safe_float(self.sharpe_ratio),
            "sortino_ratio": safe_float(self.sortino_ratio),
            "max_drawdown_pct": safe_float(self.max_drawdown_pct),
            "max_drawdown_abs": max_drawdown_abs,
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "win_rate": safe_float(self.win_rate),
            "total_trades": self.total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_win": safe_float(self.avg_win),
            "avg_loss": safe_float(self.avg_loss),
            "profit_factor": safe_float(self.profit_factor),
            "avg_trade_duration_hours": safe_float(self.avg_trade_duration_hours),
            "max_consecutive_wins": self.consecutive_wins_max,
            "max_consecutive_losses": self.consecutive_losses_max,
            "calmar_ratio": safe_float(self.calmar_ratio),
        }


class MetricsCalculator:
    """
    Calculates trading performance metrics from equity curve and trade data.

    Uses vectorized operations (numpy) for efficiency with large datasets.
    """

    @staticmethod
    def _sanitize_float(value: float, default: float = 0.0) -> float:
        """
        Convert NaN or inf values to a safe default for database storage.

        Args:
            value: Float value to sanitize
            default: Default value to use if NaN or inf

        Returns:
            Sanitized float value
        """
        if math.isnan(value) or math.isinf(value):
            return default
        return value

    @staticmethod
    def calculate_sharpe_ratio(
        returns: np.ndarray, risk_free_rate: float = 0.0, periods_per_year: int = 252
    ) -> float:
        """
        Calculate annualized Sharpe ratio.

        Args:
            returns: Array of period returns (not cumulative)
            risk_free_rate: Annual risk-free rate (default 0.0)
            periods_per_year: Trading periods per year (252 for daily, 8760 for hourly)

        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - (risk_free_rate / periods_per_year)

        if np.std(excess_returns, ddof=1) == 0:
            return 0.0

        sharpe = np.mean(excess_returns) / np.std(excess_returns, ddof=1)
        return sharpe * np.sqrt(periods_per_year)

    @staticmethod
    def calculate_sortino_ratio(
        returns: np.ndarray, risk_free_rate: float = 0.0, periods_per_year: int = 252
    ) -> float:
        """
        Calculate annualized Sortino ratio (uses downside deviation).

        Args:
            returns: Array of period returns
            risk_free_rate: Annual risk-free rate
            periods_per_year: Trading periods per year

        Returns:
            Annualized Sortino ratio
        """
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - (risk_free_rate / periods_per_year)

        # Downside deviation (only negative returns)
        downside_returns = excess_returns[excess_returns < 0]
        if len(downside_returns) == 0:
            return 0.0

        downside_std = np.std(downside_returns, ddof=1)
        if downside_std == 0:
            return 0.0

        sortino = np.mean(excess_returns) / downside_std
        return sortino * np.sqrt(periods_per_year)

    @staticmethod
    def calculate_max_drawdown(equity_curve: np.ndarray) -> tuple[float, int]:
        """
        Calculate maximum drawdown and its duration.

        Args:
            equity_curve: Array of portfolio values over time

        Returns:
            Tuple of (max_drawdown_pct, duration_in_periods)
        """
        if len(equity_curve) == 0:
            return 0.0, 0

        # Calculate running maximum
        running_max = np.maximum.accumulate(equity_curve)

        # Calculate drawdown at each point
        drawdown = (equity_curve - running_max) / running_max * 100

        # Maximum drawdown
        max_dd = np.min(drawdown)

        # Calculate drawdown duration
        # Find periods where we're in drawdown
        in_drawdown = drawdown < -0.01  # 0.01% threshold to avoid noise

        if not np.any(in_drawdown):
            return abs(max_dd), 0

        # Find consecutive drawdown periods
        drawdown_periods = []
        current_period = 0

        for is_dd in in_drawdown:
            if is_dd:
                current_period += 1
            else:
                if current_period > 0:
                    drawdown_periods.append(current_period)
                current_period = 0

        if current_period > 0:
            drawdown_periods.append(current_period)

        max_duration = max(drawdown_periods) if drawdown_periods else 0

        return abs(max_dd), max_duration

    @staticmethod
    def calculate_win_rate(pnl_values: List[Decimal]) -> float:
        """
        Calculate win rate (percentage of profitable trades).

        Args:
            pnl_values: List of trade P&L values

        Returns:
            Win rate (0.0 to 1.0)
        """
        if not pnl_values:
            return 0.0

        winning_trades = sum(1 for pnl in pnl_values if pnl > 0)
        return winning_trades / len(pnl_values)

    @staticmethod
    def calculate_profit_factor(pnl_values: List[Decimal]) -> float:
        """
        Calculate profit factor (gross profit / gross loss).

        Args:
            pnl_values: List of trade P&L values

        Returns:
            Profit factor (>1 means profitable)
        """
        if not pnl_values:
            return 0.0

        gross_profit = sum(pnl for pnl in pnl_values if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnl_values if pnl < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return float(gross_profit / gross_loss)

    @staticmethod
    def calculate_consecutive_trades(pnl_values: List[Decimal]) -> tuple[int, int]:
        """
        Calculate maximum consecutive wins and losses.

        Args:
            pnl_values: List of trade P&L values

        Returns:
            Tuple of (max_consecutive_wins, max_consecutive_losses)
        """
        if not pnl_values:
            return 0, 0

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for pnl in pnl_values:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                # Breakeven trade
                current_wins = 0
                current_losses = 0

        return max_wins, max_losses

    @staticmethod
    def calculate_avg_trade_duration(
        entry_times: List[datetime], exit_times: List[datetime]
    ) -> float:
        """
        Calculate average trade duration in hours.

        Args:
            entry_times: List of entry timestamps
            exit_times: List of exit timestamps

        Returns:
            Average duration in hours
        """
        if not entry_times or not exit_times or len(entry_times) != len(exit_times):
            return 0.0

        durations = [
            (exit - entry).total_seconds() / 3600
            for entry, exit in zip(entry_times, exit_times)
        ]

        return sum(durations) / len(durations) if durations else 0.0

    @staticmethod
    def calculate_all_metrics(
        initial_capital: Decimal,
        final_capital: Decimal,
        equity_curve: List[Decimal],
        timestamps: List[datetime],
        trade_pnls: List[Decimal],
        entry_times: List[datetime],
        exit_times: List[datetime],
    ) -> PerformanceMetrics:
        """
        Calculate complete set of performance metrics.

        Args:
            initial_capital: Starting capital
            final_capital: Ending capital
            equity_curve: Portfolio values over time
            timestamps: Timestamps for equity curve
            trade_pnls: P&L for each closed trade
            entry_times: Entry timestamps for trades
            exit_times: Exit timestamps for trades

        Returns:
            PerformanceMetrics instance with all computed metrics
        """
        # Convert to numpy for efficient calculation
        equity_array = np.array([float(val) for val in equity_curve])

        # Calculate returns
        returns = np.diff(equity_array) / equity_array[:-1] if len(equity_array) > 1 else np.array([])

        # Determine periods per year based on timestamp frequency
        if len(timestamps) > 1:
            avg_period = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
            periods_per_year = int(timedelta(days=365).total_seconds() / avg_period.total_seconds())
        else:
            periods_per_year = 252  # Default to daily

        # Calculate Sharpe ratio
        sharpe = MetricsCalculator.calculate_sharpe_ratio(
            returns, periods_per_year=periods_per_year
        )

        # Calculate Sortino ratio
        sortino = MetricsCalculator.calculate_sortino_ratio(
            returns, periods_per_year=periods_per_year
        )

        # Calculate max drawdown
        max_dd_pct, max_dd_duration = MetricsCalculator.calculate_max_drawdown(equity_array)

        # Calculate win rate
        win_rate = MetricsCalculator.calculate_win_rate(trade_pnls)

        # Calculate profit factor
        profit_factor = MetricsCalculator.calculate_profit_factor(trade_pnls)

        # Calculate total return
        total_return_pct = (
            (final_capital - initial_capital) / initial_capital * 100
            if initial_capital > 0
            else Decimal("0.0")
        )

        # Calculate trade statistics
        winning_trades = [pnl for pnl in trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in trade_pnls if pnl < 0]

        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else Decimal("0.0")
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else Decimal("0.0")
        largest_win = max(winning_trades) if winning_trades else Decimal("0.0")
        largest_loss = min(losing_trades) if losing_trades else Decimal("0.0")

        # Calculate consecutive streaks
        max_wins, max_losses = MetricsCalculator.calculate_consecutive_trades(trade_pnls)

        # Calculate average trade duration
        avg_duration = MetricsCalculator.calculate_avg_trade_duration(entry_times, exit_times)

        # Calculate Calmar ratio (return / max drawdown)
        calmar = (
            float(total_return_pct) / abs(max_dd_pct) if abs(max_dd_pct) > 0.01 else 0.0
        )

        # Convert max_dd_duration from periods to days
        max_dd_duration_days = int(
            max_dd_duration * avg_period.total_seconds() / 86400
        ) if len(timestamps) > 1 else 0

        # Sanitize float values to prevent NaN/inf in database
        sharpe_clean = MetricsCalculator._sanitize_float(sharpe, 0.0)
        sortino_clean = MetricsCalculator._sanitize_float(sortino, 0.0)
        max_dd_pct_clean = MetricsCalculator._sanitize_float(max_dd_pct, 0.0)
        win_rate_clean = MetricsCalculator._sanitize_float(win_rate, 0.0)
        profit_factor_clean = MetricsCalculator._sanitize_float(profit_factor, 0.0)
        avg_duration_clean = MetricsCalculator._sanitize_float(avg_duration, 0.0)
        calmar_clean = MetricsCalculator._sanitize_float(calmar, 0.0)

        return PerformanceMetrics(
            total_return_pct=Decimal(str(total_return_pct)),
            sharpe_ratio=Decimal(str(round(sharpe_clean, 4))),
            max_drawdown_pct=Decimal(str(round(max_dd_pct_clean, 4))),
            max_drawdown_duration_days=max_dd_duration_days,
            win_rate=Decimal(str(round(win_rate_clean, 4))),
            total_trades=len(trade_pnls),
            avg_trade_duration_hours=Decimal(str(round(avg_duration_clean, 2))),
            profit_factor=Decimal(str(round(profit_factor_clean, 4))),
            final_capital=final_capital,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            consecutive_wins_max=max_wins,
            consecutive_losses_max=max_losses,
            sortino_ratio=Decimal(str(round(sortino_clean, 4))),
            calmar_ratio=Decimal(str(round(calmar_clean, 4))),
        )
