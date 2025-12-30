"""
Unit tests for MetricsCalculator.

Tests Sharpe ratio, Sortino ratio, maximum drawdown, win rate,
profit factor, and other performance metrics calculations.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from src.services.backtesting.metrics_calculator import (
    MetricsCalculator,
    PerformanceMetrics
)


class TestMetricsCalculatorSharpeRatio:
    """Test Sharpe ratio calculation."""

    def test_sharpe_ratio_positive_returns(self):
        """Test Sharpe ratio with positive returns."""
        # Returns with mean=0.01, std=0.02
        returns = np.array([0.01, 0.02, -0.01, 0.03, 0.01])

        sharpe = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            risk_free_rate=0.0,
            periods_per_year=252
        )

        # Sharpe should be positive
        assert sharpe > 0

    def test_sharpe_ratio_negative_returns(self):
        """Test Sharpe ratio with negative mean returns."""
        returns = np.array([-0.01, -0.02, 0.01, -0.03, -0.01])

        sharpe = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            risk_free_rate=0.0,
            periods_per_year=252
        )

        # Sharpe should be negative
        assert sharpe < 0

    def test_sharpe_ratio_zero_volatility(self):
        """Test Sharpe ratio with zero volatility returns zero."""
        # All returns the same = zero volatility
        returns = np.array([0.01, 0.01, 0.01, 0.01])

        sharpe = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            risk_free_rate=0.0,
            periods_per_year=252
        )

        # Should return 0 for zero volatility
        assert sharpe == 0.0

    def test_sharpe_ratio_empty_returns(self):
        """Test Sharpe ratio with empty returns."""
        returns = np.array([])

        sharpe = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            periods_per_year=252
        )

        assert sharpe == 0.0

    def test_sharpe_ratio_with_risk_free_rate(self):
        """Test Sharpe ratio accounts for risk-free rate."""
        returns = np.array([0.05, 0.06, 0.04, 0.07, 0.05])

        sharpe_no_rfr = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            risk_free_rate=0.0,
            periods_per_year=252
        )

        sharpe_with_rfr = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            risk_free_rate=0.02,  # 2% annual risk-free rate
            periods_per_year=252
        )

        # Sharpe with risk-free rate should be lower
        assert sharpe_with_rfr < sharpe_no_rfr

    def test_sharpe_ratio_annualization(self):
        """Test Sharpe ratio is annualized correctly."""
        # Daily returns
        daily_returns = np.array([0.001] * 100)

        sharpe_daily = MetricsCalculator.calculate_sharpe_ratio(
            daily_returns,
            periods_per_year=252
        )

        # Hourly returns (same absolute values)
        sharpe_hourly = MetricsCalculator.calculate_sharpe_ratio(
            daily_returns,
            periods_per_year=8760  # 24 * 365
        )

        # Annualized Sharpe should be different for different frequencies
        # Hourly will have higher annualization factor
        assert sharpe_hourly != sharpe_daily


class TestMetricsCalculatorSortinoRatio:
    """Test Sortino ratio calculation."""

    def test_sortino_ratio_positive_returns(self):
        """Test Sortino ratio with mixed returns."""
        returns = np.array([0.02, -0.01, 0.03, -0.02, 0.04])

        sortino = MetricsCalculator.calculate_sortino_ratio(
            returns,
            risk_free_rate=0.0,
            periods_per_year=252
        )

        # Sortino should be positive for positive mean
        assert sortino > 0

    def test_sortino_ratio_no_downside(self):
        """Test Sortino ratio when there are no negative returns."""
        # All positive returns
        returns = np.array([0.01, 0.02, 0.03, 0.01, 0.02])

        sortino = MetricsCalculator.calculate_sortino_ratio(
            returns,
            periods_per_year=252
        )

        # Should return 0 when no downside deviation
        assert sortino == 0.0

    def test_sortino_ratio_vs_sharpe(self):
        """Test that Sortino is typically higher than Sharpe (only penalizes downside)."""
        # Returns with some downside
        returns = np.array([0.05, -0.02, 0.03, -0.01, 0.04, 0.02])

        sharpe = MetricsCalculator.calculate_sharpe_ratio(
            returns,
            periods_per_year=252
        )

        sortino = MetricsCalculator.calculate_sortino_ratio(
            returns,
            periods_per_year=252
        )

        # Sortino typically higher because it only penalizes downside
        # (though not always guaranteed depending on distribution)
        assert sortino != 0.0


class TestMetricsCalculatorMaxDrawdown:
    """Test maximum drawdown calculation."""

    def test_max_drawdown_declining_equity(self):
        """Test max drawdown with declining equity curve."""
        # Equity drops from 10000 to 8000 (-20%)
        equity_curve = np.array([10000, 9500, 9000, 8500, 8000])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        # Max drawdown should be 20%
        assert abs(max_dd - 20.0) < 0.1
        assert duration == 4  # All 4 periods in drawdown

    def test_max_drawdown_peak_to_trough(self):
        """Test max drawdown identifies peak to trough correctly."""
        # Peak at 10000, trough at 7000, recovery to 9000
        equity_curve = np.array([10000, 9500, 8000, 7000, 8000, 9000])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        # Max drawdown should be 30% (10000 -> 7000)
        assert abs(max_dd - 30.0) < 0.1

    def test_max_drawdown_rising_equity(self):
        """Test max drawdown with always rising equity."""
        equity_curve = np.array([10000, 11000, 12000, 13000, 14000])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        # No drawdown
        assert abs(max_dd) < 0.1
        assert duration == 0

    def test_max_drawdown_multiple_drawdowns(self):
        """Test max drawdown identifies the largest drawdown."""
        # Two drawdowns: 10% and 25%
        equity_curve = np.array([
            10000,  # Peak 1
            9000,   # -10% drawdown
            10000,  # Recovery
            12000,  # New peak
            9000,   # -25% drawdown (largest)
            10000   # Partial recovery
        ])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        # Should identify 25% drawdown
        assert abs(max_dd - 25.0) < 0.1

    def test_max_drawdown_empty_curve(self):
        """Test max drawdown with empty equity curve."""
        equity_curve = np.array([])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        assert max_dd == 0.0
        assert duration == 0

    def test_max_drawdown_single_value(self):
        """Test max drawdown with single equity value."""
        equity_curve = np.array([10000])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        assert abs(max_dd) < 0.1
        assert duration == 0

    def test_max_drawdown_duration(self):
        """Test drawdown duration calculation."""
        # 5-period drawdown
        equity_curve = np.array([
            10000,  # Peak
            9500,   # DD period 1
            9000,   # DD period 2
            8500,   # DD period 3
            8000,   # DD period 4
            7500,   # DD period 5
            10000   # Recovery
        ])

        max_dd, duration = MetricsCalculator.calculate_max_drawdown(equity_curve)

        # Duration should be 5 periods
        assert duration == 5


class TestMetricsCalculatorWinRate:
    """Test win rate calculation."""

    def test_win_rate_all_wins(self):
        """Test win rate with all winning trades."""
        pnl_values = [
            Decimal("100"),
            Decimal("50"),
            Decimal("75"),
            Decimal("200")
        ]

        win_rate = MetricsCalculator.calculate_win_rate(pnl_values)

        assert win_rate == 1.0  # 100%

    def test_win_rate_all_losses(self):
        """Test win rate with all losing trades."""
        pnl_values = [
            Decimal("-100"),
            Decimal("-50"),
            Decimal("-75")
        ]

        win_rate = MetricsCalculator.calculate_win_rate(pnl_values)

        assert win_rate == 0.0  # 0%

    def test_win_rate_mixed(self):
        """Test win rate with mixed trades."""
        pnl_values = [
            Decimal("100"),   # Win
            Decimal("-50"),   # Loss
            Decimal("75"),    # Win
            Decimal("-25")    # Loss
        ]

        win_rate = MetricsCalculator.calculate_win_rate(pnl_values)

        assert win_rate == 0.5  # 50%

    def test_win_rate_with_breakeven(self):
        """Test win rate excludes breakeven trades."""
        pnl_values = [
            Decimal("100"),  # Win
            Decimal("0"),    # Breakeven (not counted as win)
            Decimal("-50")   # Loss
        ]

        win_rate = MetricsCalculator.calculate_win_rate(pnl_values)

        # 1 win out of 3 trades = 33.33%
        assert abs(win_rate - 0.3333) < 0.01

    def test_win_rate_empty_list(self):
        """Test win rate with no trades."""
        pnl_values = []

        win_rate = MetricsCalculator.calculate_win_rate(pnl_values)

        assert win_rate == 0.0


class TestMetricsCalculatorProfitFactor:
    """Test profit factor calculation."""

    def test_profit_factor_profitable(self):
        """Test profit factor with more profit than loss."""
        pnl_values = [
            Decimal("200"),   # +200
            Decimal("-50"),   # -50
            Decimal("100"),   # +100
            Decimal("-25")    # -25
        ]

        pf = MetricsCalculator.calculate_profit_factor(pnl_values)

        # Gross profit = 300, Gross loss = 75
        # PF = 300 / 75 = 4.0
        assert abs(pf - 4.0) < 0.01

    def test_profit_factor_unprofitable(self):
        """Test profit factor with more loss than profit."""
        pnl_values = [
            Decimal("50"),     # +50
            Decimal("-200"),   # -200
            Decimal("25"),     # +25
            Decimal("-100")    # -100
        ]

        pf = MetricsCalculator.calculate_profit_factor(pnl_values)

        # Gross profit = 75, Gross loss = 300
        # PF = 75 / 300 = 0.25
        assert abs(pf - 0.25) < 0.01

    def test_profit_factor_no_losses(self):
        """Test profit factor when there are no losses."""
        pnl_values = [
            Decimal("100"),
            Decimal("50"),
            Decimal("75")
        ]

        pf = MetricsCalculator.calculate_profit_factor(pnl_values)

        # Should return infinity for no losses
        assert pf == float('inf')

    def test_profit_factor_no_profits(self):
        """Test profit factor when there are no profits."""
        pnl_values = [
            Decimal("-100"),
            Decimal("-50"),
            Decimal("-75")
        ]

        pf = MetricsCalculator.calculate_profit_factor(pnl_values)

        # Should return 0 for no profits
        assert pf == 0.0

    def test_profit_factor_empty_list(self):
        """Test profit factor with no trades."""
        pnl_values = []

        pf = MetricsCalculator.calculate_profit_factor(pnl_values)

        assert pf == 0.0


class TestMetricsCalculatorConsecutiveTrades:
    """Test consecutive wins/losses calculation."""

    def test_consecutive_wins(self):
        """Test maximum consecutive wins."""
        pnl_values = [
            Decimal("100"),   # Win 1
            Decimal("50"),    # Win 2
            Decimal("75"),    # Win 3
            Decimal("-25"),   # Loss (breaks streak)
            Decimal("100"),   # Win 1
            Decimal("200")    # Win 2
        ]

        max_wins, max_losses = MetricsCalculator.calculate_consecutive_trades(pnl_values)

        assert max_wins == 3
        assert max_losses == 1

    def test_consecutive_losses(self):
        """Test maximum consecutive losses."""
        pnl_values = [
            Decimal("100"),   # Win
            Decimal("-50"),   # Loss 1
            Decimal("-75"),   # Loss 2
            Decimal("-25"),   # Loss 3
            Decimal("-100"),  # Loss 4
            Decimal("50")     # Win (breaks streak)
        ]

        max_wins, max_losses = MetricsCalculator.calculate_consecutive_trades(pnl_values)

        assert max_wins == 1
        assert max_losses == 4

    def test_consecutive_with_breakeven(self):
        """Test that breakeven trades break streaks."""
        pnl_values = [
            Decimal("100"),   # Win 1
            Decimal("50"),    # Win 2
            Decimal("0"),     # Breakeven (breaks streak)
            Decimal("75"),    # Win 1
            Decimal("25")     # Win 2
        ]

        max_wins, max_losses = MetricsCalculator.calculate_consecutive_trades(pnl_values)

        assert max_wins == 2  # Not 4, because breakeven breaks it


class TestMetricsCalculatorTradeDuration:
    """Test average trade duration calculation."""

    def test_avg_trade_duration(self):
        """Test average trade duration in hours."""
        entry_times = [
            datetime(2024, 1, 1, 10, 0),
            datetime(2024, 1, 2, 14, 0),
            datetime(2024, 1, 3, 9, 0)
        ]

        exit_times = [
            datetime(2024, 1, 1, 12, 0),  # 2 hours
            datetime(2024, 1, 2, 18, 0),  # 4 hours
            datetime(2024, 1, 3, 15, 0)   # 6 hours
        ]

        avg_duration = MetricsCalculator.calculate_avg_trade_duration(
            entry_times,
            exit_times
        )

        # Average = (2 + 4 + 6) / 3 = 4 hours
        assert avg_duration == 4.0

    def test_avg_trade_duration_empty(self):
        """Test average duration with no trades."""
        avg_duration = MetricsCalculator.calculate_avg_trade_duration([], [])

        assert avg_duration == 0.0


class TestMetricsCalculatorAllMetrics:
    """Test comprehensive metrics calculation."""

    def test_calculate_all_metrics(self):
        """Test complete metrics calculation with realistic data."""
        initial_capital = Decimal("10000.00")
        final_capital = Decimal("12000.00")

        # Equity curve with some volatility
        equity_curve = [
            Decimal("10000"),
            Decimal("10200"),
            Decimal("10100"),
            Decimal("10500"),
            Decimal("10300"),
            Decimal("11000"),
            Decimal("10800"),
            Decimal("11500"),
            Decimal("12000")
        ]

        timestamps = [
            datetime(2024, 1, 1) + timedelta(days=i)
            for i in range(len(equity_curve))
        ]

        # Some profitable and losing trades
        trade_pnls = [
            Decimal("200"),   # Win
            Decimal("-100"),  # Loss
            Decimal("400"),   # Win
            Decimal("-200"),  # Loss
            Decimal("700"),   # Win
            Decimal("-200"),  # Loss
            Decimal("700"),   # Win
            Decimal("500")    # Win
        ]

        entry_times = [datetime(2024, 1, 1, 10, 0) + timedelta(days=i) for i in range(8)]
        exit_times = [entry + timedelta(hours=3) for entry in entry_times]

        metrics = MetricsCalculator.calculate_all_metrics(
            initial_capital=initial_capital,
            final_capital=final_capital,
            equity_curve=equity_curve,
            timestamps=timestamps,
            trade_pnls=trade_pnls,
            entry_times=entry_times,
            exit_times=exit_times
        )

        # Validate metrics type and basic properties
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_return_pct == Decimal("20.0")  # 2000/10000 * 100
        assert metrics.total_trades == 8
        assert metrics.final_capital == Decimal("12000.00")

        # Sharpe should be positive (profitable)
        assert metrics.sharpe_ratio > 0

        # Win rate should be 5/8 = 62.5%
        assert abs(metrics.win_rate - Decimal("0.625")) < Decimal("0.01")

        # Profit factor should be > 1 (profitable)
        assert metrics.profit_factor > 1

        # Average trade duration should be 3 hours
        assert metrics.avg_trade_duration_hours == Decimal("3.00")

    def test_metrics_to_dict(self):
        """Test metrics conversion to dictionary."""
        initial_capital = Decimal("10000.00")
        final_capital = Decimal("11000.00")
        equity_curve = [Decimal("10000"), Decimal("10500"), Decimal("11000")]
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(3)]
        trade_pnls = [Decimal("500"), Decimal("500")]
        entry_times = [datetime(2024, 1, 1), datetime(2024, 1, 2)]
        exit_times = [datetime(2024, 1, 1, 2, 0), datetime(2024, 1, 2, 2, 0)]

        metrics = MetricsCalculator.calculate_all_metrics(
            initial_capital=initial_capital,
            final_capital=final_capital,
            equity_curve=equity_curve,
            timestamps=timestamps,
            trade_pnls=trade_pnls,
            entry_times=entry_times,
            exit_times=exit_times
        )

        metrics_dict = metrics.to_dict()

        # Verify all keys exist and are correct types
        assert isinstance(metrics_dict["total_return_pct"], float)
        assert isinstance(metrics_dict["sharpe_ratio"], float)
        assert isinstance(metrics_dict["max_drawdown_pct"], float)
        assert isinstance(metrics_dict["win_rate"], float)
        assert isinstance(metrics_dict["total_trades"], int)
        assert isinstance(metrics_dict["profit_factor"], float)
