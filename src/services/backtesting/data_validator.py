"""
Data quality validation for backtesting.

Validates market data quality, checks for gaps, outliers,
and ensures data suitability for backtesting.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np


@dataclass
class ValidationResult:
    """
    Result of data quality validation.

    Attributes:
        is_valid: Whether data passes validation
        warnings: List of warning messages
        errors: List of error messages
        statistics: Dictionary of data quality statistics
    """

    is_valid: bool
    warnings: List[str]
    errors: List[str]
    statistics: Dict


class DataValidator:
    """
    Validates market data quality for backtesting.

    Checks for:
    - Data gaps and missing candles
    - Price outliers and anomalies
    - Zero volume periods
    - Negative or zero prices
    - Data continuity
    """

    def __init__(
        self,
        max_gap_threshold: timedelta = timedelta(hours=24),
        outlier_std_threshold: float = 5.0,
        min_candles_required: int = 100,
    ):
        """
        Initialize data validator.

        Args:
            max_gap_threshold: Maximum acceptable gap between candles
            outlier_std_threshold: Standard deviations for outlier detection
            min_candles_required: Minimum candles needed for backtest
        """
        self.max_gap_threshold = max_gap_threshold
        self.outlier_std_threshold = outlier_std_threshold
        self.min_candles_required = min_candles_required

    def validate_price_data(
        self,
        timestamps: List[datetime],
        open_prices: List[Decimal],
        high_prices: List[Decimal],
        low_prices: List[Decimal],
        close_prices: List[Decimal],
        volumes: List[int],
    ) -> ValidationResult:
        """
        Validate price data quality comprehensively.

        Args:
            timestamps: List of candle timestamps
            open_prices: List of open prices
            high_prices: List of high prices
            low_prices: List of low prices
            close_prices: List of close prices
            volumes: List of volumes

        Returns:
            ValidationResult with detailed findings
        """
        warnings: List[str] = []
        errors: List[str] = []
        statistics: Dict = {}

        # Check minimum data requirement
        if len(timestamps) < self.min_candles_required:
            errors.append(
                f"Insufficient data: {len(timestamps)} candles (minimum {self.min_candles_required} required)"
            )
            return ValidationResult(
                is_valid=False,
                warnings=warnings,
                errors=errors,
                statistics={"total_candles": len(timestamps)},
            )

        # Check for zero or negative prices
        zero_price_count = 0
        negative_price_count = 0

        for i in range(len(close_prices)):
            if close_prices[i] <= 0:
                zero_price_count += 1
            if (
                open_prices[i] < 0
                or high_prices[i] < 0
                or low_prices[i] < 0
                or close_prices[i] < 0
            ):
                negative_price_count += 1

        if negative_price_count > 0:
            errors.append(f"Found {negative_price_count} candles with negative prices")

        if zero_price_count > 0:
            warnings.append(f"Found {zero_price_count} candles with zero/invalid prices")

        # Check OHLC consistency
        inconsistent_count = 0
        for i in range(len(timestamps)):
            # High must be >= low
            if high_prices[i] < low_prices[i]:
                inconsistent_count += 1
            # High must be >= open and close
            if high_prices[i] < open_prices[i] or high_prices[i] < close_prices[i]:
                inconsistent_count += 1
            # Low must be <= open and close
            if low_prices[i] > open_prices[i] or low_prices[i] > close_prices[i]:
                inconsistent_count += 1

        if inconsistent_count > 0:
            warnings.append(
                f"Found {inconsistent_count} candles with inconsistent OHLC values"
            )

        # Check for data gaps
        gaps = []
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            if gap > self.max_gap_threshold:
                gaps.append((timestamps[i - 1], timestamps[i], gap))

        if gaps:
            warnings.append(
                f"Found {len(gaps)} gaps larger than {self.max_gap_threshold}"
            )
            statistics["largest_gap"] = max(gap[2] for gap in gaps)

        # Check for price outliers using z-score
        close_array = np.array([float(p) for p in close_prices])
        returns = np.diff(np.log(close_array))

        if len(returns) > 0:
            mean_return = np.mean(returns)
            std_return = np.std(returns)

            if std_return > 0:
                z_scores = np.abs((returns - mean_return) / std_return)
                outliers = np.where(z_scores > self.outlier_std_threshold)[0]

                if len(outliers) > 0:
                    warnings.append(
                        f"Found {len(outliers)} potential price outliers (>{self.outlier_std_threshold} std)"
                    )
                    statistics["outlier_count"] = len(outliers)

        # Check for zero volume periods
        zero_volume_count = sum(1 for v in volumes if v == 0)
        if zero_volume_count > 0:
            warnings.append(
                f"Found {zero_volume_count} candles with zero volume ({zero_volume_count/len(volumes)*100:.1f}%)"
            )

        # Calculate statistics
        statistics.update(
            {
                "total_candles": len(timestamps),
                "date_range_days": (timestamps[-1] - timestamps[0]).days,
                "avg_close_price": float(np.mean(close_array)),
                "price_volatility": float(np.std(returns)) if len(returns) > 0 else 0.0,
                "zero_volume_pct": zero_volume_count / len(volumes) * 100,
                "gap_count": len(gaps),
                "inconsistent_ohlc_count": inconsistent_count,
            }
        )

        # Determine if valid
        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            statistics=statistics,
        )

    def validate_backtest_period(
        self,
        start_date: datetime,
        end_date: datetime,
        data_start: datetime,
        data_end: datetime,
    ) -> ValidationResult:
        """
        Validate that backtest period has complete data coverage.

        Args:
            start_date: Desired backtest start
            end_date: Desired backtest end
            data_start: Actual data start
            data_end: Actual data end

        Returns:
            ValidationResult indicating coverage
        """
        warnings: List[str] = []
        errors: List[str] = []

        # Check if data covers requested period
        if start_date < data_start:
            errors.append(
                f"Requested start {start_date} before data availability {data_start}"
            )

        if end_date > data_end:
            errors.append(
                f"Requested end {end_date} after data availability {data_end}"
            )

        # Check for reasonable backtest duration
        backtest_duration = (end_date - start_date).days
        if backtest_duration < 7:
            warnings.append(
                f"Very short backtest period: {backtest_duration} days (consider 30+ days)"
            )
        elif backtest_duration > 365 * 3:
            warnings.append(
                f"Very long backtest period: {backtest_duration} days (may be slow)"
            )

        statistics = {
            "backtest_duration_days": backtest_duration,
            "data_coverage_start": data_start.isoformat(),
            "data_coverage_end": data_end.isoformat(),
            "requested_start": start_date.isoformat(),
            "requested_end": end_date.isoformat(),
        }

        return ValidationResult(
            is_valid=len(errors) == 0,
            warnings=warnings,
            errors=errors,
            statistics=statistics,
        )

    def detect_price_spikes(
        self,
        close_prices: List[Decimal],
        spike_threshold_pct: float = 10.0,
    ) -> List[int]:
        """
        Detect sudden price spikes that may indicate bad data.

        Args:
            close_prices: List of close prices
            spike_threshold_pct: Percentage change threshold for spike detection

        Returns:
            List of indices where spikes were detected
        """
        spikes = []

        for i in range(1, len(close_prices)):
            prev_price = float(close_prices[i - 1])
            curr_price = float(close_prices[i])

            if prev_price > 0:
                pct_change = abs((curr_price - prev_price) / prev_price * 100)
                if pct_change > spike_threshold_pct:
                    spikes.append(i)

        return spikes

    def check_minimum_volatility(
        self, close_prices: List[Decimal], min_volatility: float = 0.001
    ) -> tuple[bool, float]:
        """
        Check if data has minimum volatility for meaningful backtesting.

        Args:
            close_prices: List of close prices
            min_volatility: Minimum required volatility (annualized)

        Returns:
            Tuple of (has_minimum_volatility, actual_volatility)
        """
        close_array = np.array([float(p) for p in close_prices])
        returns = np.diff(np.log(close_array))

        if len(returns) == 0:
            return False, 0.0

        # Annualized volatility (assuming daily returns, adjust if needed)
        volatility = float(np.std(returns) * np.sqrt(252))

        return volatility >= min_volatility, volatility

    def validate_for_backtesting(
        self,
        timestamps: List[datetime],
        open_prices: List[Decimal],
        high_prices: List[Decimal],
        low_prices: List[Decimal],
        close_prices: List[Decimal],
        volumes: List[int],
        start_date: datetime,
        end_date: datetime,
    ) -> ValidationResult:
        """
        Comprehensive validation for backtesting suitability.

        Combines all validation checks into a single result.

        Args:
            timestamps: Candle timestamps
            open_prices: Open prices
            high_prices: High prices
            low_prices: Low prices
            close_prices: Close prices
            volumes: Volumes
            start_date: Backtest start
            end_date: Backtest end

        Returns:
            ValidationResult with all checks
        """
        # Validate price data
        price_validation = self.validate_price_data(
            timestamps, open_prices, high_prices, low_prices, close_prices, volumes
        )

        # Validate backtest period
        if timestamps:
            period_validation = self.validate_backtest_period(
                start_date, end_date, timestamps[0], timestamps[-1]
            )
        else:
            period_validation = ValidationResult(
                is_valid=False,
                warnings=[],
                errors=["No data available"],
                statistics={},
            )

        # Check volatility
        has_volatility, volatility = self.check_minimum_volatility(close_prices)
        if not has_volatility:
            price_validation.warnings.append(
                f"Very low volatility ({volatility:.4f}) - may produce unrealistic results"
            )

        # Detect spikes
        spikes = self.detect_price_spikes(close_prices)
        if spikes:
            price_validation.warnings.append(
                f"Detected {len(spikes)} potential price spikes - review data quality"
            )

        # Combine results
        combined_warnings = price_validation.warnings + period_validation.warnings
        combined_errors = price_validation.errors + period_validation.errors
        combined_statistics = {
            **price_validation.statistics,
            **period_validation.statistics,
            "volatility_annualized": volatility,
            "price_spike_count": len(spikes),
        }

        return ValidationResult(
            is_valid=price_validation.is_valid and period_validation.is_valid,
            warnings=combined_warnings,
            errors=combined_errors,
            statistics=combined_statistics,
        )
