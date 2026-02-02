"""
Data Quality Analysis Service

Automated data quality checks for market data:
- Missing values detection
- Duplicate timestamps
- Price consistency validation
- Outlier detection
- Volume anomalies
- Data gaps analysis
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)


class DataQualityAnalyzer:
    """Automated data quality analysis for trading data."""

    def __init__(self, df: pd.DataFrame):
        """
        Initialize with market data DataFrame.

        Args:
            df: DataFrame with columns [time, open, high, low, close, volume]
        """
        self.df = df.copy()
        if 'time' in self.df.columns and not pd.api.types.is_datetime64_any_dtype(self.df['time']):
            self.df['time'] = pd.to_datetime(self.df['time'])
        self.df = self.df.sort_values('time').reset_index(drop=True)

    def check_missing_values(self) -> Dict[str, Any]:
        """Check for missing values in OHLCV columns."""
        columns = ['open', 'high', 'low', 'close', 'volume']
        missing = {}
        total_missing = 0

        for col in columns:
            if col in self.df.columns:
                count = self.df[col].isnull().sum()
                missing[col] = int(count)
                total_missing += count

        status = "pass" if total_missing == 0 else "warning" if total_missing < len(self.df) * 0.01 else "fail"

        return {
            "status": status,
            "details": missing,
            "total_missing": int(total_missing)
        }

    def check_duplicate_timestamps(self) -> Dict[str, Any]:
        """Check for duplicate timestamps."""
        if 'time' not in self.df.columns:
            return {"status": "skip", "count": 0}

        duplicates = self.df['time'].duplicated().sum()
        status = "pass" if duplicates == 0 else "fail"

        return {
            "status": status,
            "count": int(duplicates)
        }

    def check_price_consistency(self) -> Dict[str, Any]:
        """Check OHLC price consistency (High >= Low, etc.)."""
        required_cols = ['open', 'high', 'low', 'close']
        if not all(col in self.df.columns for col in required_cols):
            return {"status": "skip", "inconsistent_candles": 0}

        # Check: High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close
        inconsistent = (
            (self.df['high'] < self.df['low']) |
            (self.df['high'] < self.df['open']) |
            (self.df['high'] < self.df['close']) |
            (self.df['low'] > self.df['open']) |
            (self.df['low'] > self.df['close'])
        ).sum()

        status = "pass" if inconsistent == 0 else "fail"

        return {
            "status": status,
            "inconsistent_candles": int(inconsistent)
        }

    def check_outliers(self, column: str = 'close', std_threshold: float = 4.0) -> Dict[str, Any]:
        """Detect outliers using z-score method."""
        if column not in self.df.columns:
            return {"status": "skip", "count": 0, "percentage": 0.0, "bounds": {"lower": 0, "upper": 0}}

        # Convert to numeric, handling string values
        values = pd.to_numeric(self.df[column], errors='coerce').dropna()

        if len(values) == 0:
            return {"status": "skip", "count": 0, "percentage": 0.0, "bounds": {"lower": 0, "upper": 0}}

        mean = values.mean()
        std = values.std()

        lower_bound = mean - std_threshold * std
        upper_bound = mean + std_threshold * std

        outliers = ((values < lower_bound) | (values > upper_bound)).sum()
        percentage = (outliers / len(values)) * 100

        status = "pass" if percentage < 1.0 else "warning" if percentage < 5.0 else "fail"

        return {
            "status": status,
            "count": int(outliers),
            "percentage": float(percentage),
            "bounds": {
                "lower": float(lower_bound),
                "upper": float(upper_bound)
            }
        }

    def check_volume_anomalies(self) -> Dict[str, Any]:
        """Check for zero volume and extreme volume candles."""
        if 'volume' not in self.df.columns:
            return {"status": "skip", "zero_volume_candles": 0, "extreme_volume_candles": 0}

        volumes = pd.to_numeric(self.df['volume'], errors='coerce')

        zero_volume = (volumes == 0).sum()

        # Extreme volume: > 10x median
        median_vol = volumes.median()
        extreme_volume = (volumes > median_vol * 10).sum() if median_vol > 0 else 0

        status = "pass" if zero_volume < len(self.df) * 0.01 else "warning"

        return {
            "status": status,
            "zero_volume_candles": int(zero_volume),
            "extreme_volume_candles": int(extreme_volume)
        }

    def check_data_gaps(self, expected_interval_minutes: int = 1) -> Dict[str, Any]:
        """Check for gaps in time series data."""
        if 'time' not in self.df.columns or len(self.df) < 2:
            return {"status": "skip", "gap_count": 0, "largest_gaps": []}

        time_diffs = self.df['time'].diff().dt.total_seconds() / 60  # Minutes
        expected = expected_interval_minutes

        # Gaps are intervals > 2x expected (allows some tolerance)
        gaps = time_diffs[time_diffs > expected * 2]

        # Get largest gaps
        largest_gaps = []
        if len(gaps) > 0:
            gap_indices = gaps.nlargest(5).index
            for idx in gap_indices:
                largest_gaps.append({
                    "start": self.df.loc[idx - 1, 'time'].isoformat() if idx > 0 else None,
                    "duration_minutes": int(time_diffs.loc[idx])
                })

        gap_count = len(gaps)
        status = "pass" if gap_count == 0 else "warning" if gap_count < 10 else "fail"

        return {
            "status": status,
            "gap_count": int(gap_count),
            "largest_gaps": largest_gaps
        }

    def generate_quality_score(self, checks: Dict[str, Dict[str, Any]]) -> int:
        """
        Calculate overall data quality score (0-100).

        Scoring:
        - Pass: +20 points per check
        - Warning: +10 points per check
        - Fail/Skip: +0 points per check
        """
        score = 0
        max_score = len(checks) * 20

        for check_name, result in checks.items():
            status = result.get('status', 'fail')
            if status == 'pass':
                score += 20
            elif status == 'warning':
                score += 10

        return int((score / max_score) * 100) if max_score > 0 else 0

    def analyze(self) -> Dict[str, Any]:
        """
        Run all data quality checks and return comprehensive report.

        Returns:
            Dictionary with all check results, issues list, and quality score
        """
        logger.info("data_quality_analysis_started", rows=len(self.df))

        checks = {
            "missing_values": self.check_missing_values(),
            "duplicate_timestamps": self.check_duplicate_timestamps(),
            "price_consistency": self.check_price_consistency(),
            "outliers": self.check_outliers(),
            "volume_anomalies": self.check_volume_anomalies(),
            "data_gaps": self.check_data_gaps()
        }

        # Generate issues list
        issues = []

        if checks["missing_values"]["status"] != "pass":
            issues.append({
                "type": "missing_values",
                "severity": "high" if checks["missing_values"]["status"] == "fail" else "medium",
                "message": f"Found {checks['missing_values']['total_missing']} missing values in OHLCV data"
            })

        if checks["duplicate_timestamps"]["count"] > 0:
            issues.append({
                "type": "duplicate_timestamps",
                "severity": "high",
                "message": f"Found {checks['duplicate_timestamps']['count']} duplicate timestamps"
            })

        if checks["price_consistency"]["inconsistent_candles"] > 0:
            issues.append({
                "type": "price_consistency",
                "severity": "critical",
                "message": f"Found {checks['price_consistency']['inconsistent_candles']} candles with invalid OHLC relationships"
            })

        if checks["outliers"]["percentage"] > 1.0:
            issues.append({
                "type": "outliers",
                "severity": "medium",
                "message": f"Found {checks['outliers']['count']} outliers ({checks['outliers']['percentage']:.2f}% of data)"
            })

        if checks["volume_anomalies"]["zero_volume_candles"] > len(self.df) * 0.01:
            issues.append({
                "type": "volume_anomalies",
                "severity": "medium",
                "message": f"Found {checks['volume_anomalies']['zero_volume_candles']} candles with zero volume"
            })

        if checks["data_gaps"]["gap_count"] > 10:
            issues.append({
                "type": "data_gaps",
                "severity": "high",
                "message": f"Found {checks['data_gaps']['gap_count']} gaps in time series data"
            })

        score = self.generate_quality_score(checks)

        logger.info("data_quality_analysis_completed", score=score, issues=len(issues))

        return {
            "checks": checks,
            "issues": issues,
            "score": score
        }
