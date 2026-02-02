"""
EDA Service - Automated Exploratory Data Analysis for Trading Data.

Implements the "Lazy Data Scientist" approach:
- 80% of data quality insights with 20% of the effort
- Automated profiling of OHLCV data
- Distribution analysis, outlier detection, correlation matrices
- Train/test split validation for ML model data
- Gap detection in tick data
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData

logger = structlog.get_logger(__name__)


class EDAService:
    """Service for automated exploratory data analysis on trading data."""

    def __init__(self, db: AsyncSession):
        """
        Initialize EDA Service.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_data_quality_summary(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive data quality summary.

        Checks for:
        - Missing values
        - Duplicate timestamps
        - Outliers (using IQR method)
        - Data gaps
        - Volume anomalies
        - Price consistency (high >= low, etc.)

        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with data quality metrics and issues
        """
        try:
            # Build base query
            query = select(MarketData).where(
                and_(
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                )
            )

            if start_date:
                query = query.where(MarketData.time >= start_date)
            if end_date:
                query = query.where(MarketData.time <= end_date)

            query = query.order_by(MarketData.time)

            result = await self.db.execute(query)
            rows = result.scalars().all()

            if not rows:
                return {
                    "status": "error",
                    "message": f"No data found for {symbol} {timeframe}",
                    "data_points": 0,
                }

            # Convert to DataFrame for analysis
            df = pd.DataFrame([
                {
                    "time": r.time,
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": int(r.volume) if r.volume else 0,
                }
                for r in rows
            ])

            # Run all quality checks
            quality_report = {
                "symbol": symbol,
                "timeframe": timeframe,
                "data_points": len(df),
                "date_range": {
                    "start": df["time"].min().isoformat(),
                    "end": df["time"].max().isoformat(),
                },
                "checks": {},
                "issues": [],
                "score": 100,  # Start with perfect score
            }

            # 1. Missing Values Check
            missing = df.isnull().sum().to_dict()
            missing_total = sum(missing.values())
            quality_report["checks"]["missing_values"] = {
                "status": "pass" if missing_total == 0 else "fail",
                "details": missing,
                "total_missing": missing_total,
            }
            if missing_total > 0:
                quality_report["issues"].append({
                    "type": "missing_values",
                    "severity": "high",
                    "message": f"Found {missing_total} missing values",
                })
                quality_report["score"] -= 15

            # 2. Duplicate Timestamps Check
            duplicates = df["time"].duplicated().sum()
            quality_report["checks"]["duplicate_timestamps"] = {
                "status": "pass" if duplicates == 0 else "fail",
                "count": int(duplicates),
            }
            if duplicates > 0:
                quality_report["issues"].append({
                    "type": "duplicate_timestamps",
                    "severity": "high",
                    "message": f"Found {duplicates} duplicate timestamps",
                })
                quality_report["score"] -= 20

            # 3. Price Consistency Check (high >= low, etc.)
            inconsistent = (
                (df["high"] < df["low"]).sum() +
                (df["high"] < df["open"]).sum() +
                (df["high"] < df["close"]).sum() +
                (df["low"] > df["open"]).sum() +
                (df["low"] > df["close"]).sum()
            )
            quality_report["checks"]["price_consistency"] = {
                "status": "pass" if inconsistent == 0 else "fail",
                "inconsistent_candles": int(inconsistent),
            }
            if inconsistent > 0:
                quality_report["issues"].append({
                    "type": "price_consistency",
                    "severity": "critical",
                    "message": f"Found {inconsistent} candles with invalid OHLC relationships",
                })
                quality_report["score"] -= 25

            # 4. Outlier Detection (IQR method on close prices)
            Q1 = df["close"].quantile(0.25)
            Q3 = df["close"].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 3 * IQR
            upper_bound = Q3 + 3 * IQR
            outliers = ((df["close"] < lower_bound) | (df["close"] > upper_bound)).sum()
            outlier_pct = (outliers / len(df)) * 100

            quality_report["checks"]["outliers"] = {
                "status": "pass" if outlier_pct < 1 else "warning" if outlier_pct < 5 else "fail",
                "count": int(outliers),
                "percentage": round(outlier_pct, 2),
                "bounds": {"lower": round(lower_bound, 4), "upper": round(upper_bound, 4)},
            }
            if outlier_pct >= 1:
                quality_report["issues"].append({
                    "type": "outliers",
                    "severity": "medium" if outlier_pct < 5 else "high",
                    "message": f"Found {outliers} outliers ({outlier_pct:.2f}%)",
                })
                quality_report["score"] -= 5 if outlier_pct < 5 else 10

            # 5. Volume Anomalies (zero or extremely high volume)
            zero_volume = (df["volume"] == 0).sum()
            if df["volume"].std() > 0:
                volume_zscore = (df["volume"] - df["volume"].mean()) / df["volume"].std()
                high_volume = (volume_zscore > 3).sum()
            else:
                high_volume = 0

            quality_report["checks"]["volume_anomalies"] = {
                "status": "pass" if zero_volume < len(df) * 0.1 else "warning",
                "zero_volume_candles": int(zero_volume),
                "extreme_volume_candles": int(high_volume),
            }
            if zero_volume > len(df) * 0.1:
                quality_report["issues"].append({
                    "type": "volume_anomalies",
                    "severity": "medium",
                    "message": f"Found {zero_volume} candles with zero volume ({(zero_volume/len(df)*100):.1f}%)",
                })
                quality_report["score"] -= 5

            # 6. Gap Detection
            df["time_diff"] = df["time"].diff()
            expected_gap = self._get_expected_gap(timeframe)
            gaps = df[df["time_diff"] > expected_gap * 3]  # Gaps > 3x expected interval
            
            quality_report["checks"]["data_gaps"] = {
                "status": "pass" if len(gaps) == 0 else "warning",
                "gap_count": len(gaps),
                "largest_gaps": [
                    {
                        "start": row["time"].isoformat(),
                        "duration_minutes": row["time_diff"].total_seconds() / 60,
                    }
                    for _, row in gaps.nlargest(5, "time_diff").iterrows()
                ] if len(gaps) > 0 else [],
            }
            if len(gaps) > 0:
                quality_report["issues"].append({
                    "type": "data_gaps",
                    "severity": "low",
                    "message": f"Found {len(gaps)} significant data gaps",
                })
                quality_report["score"] -= 5

            # Ensure score doesn't go below 0
            quality_report["score"] = max(0, quality_report["score"])

            # Overall status
            if quality_report["score"] >= 90:
                quality_report["status"] = "excellent"
            elif quality_report["score"] >= 70:
                quality_report["status"] = "good"
            elif quality_report["score"] >= 50:
                quality_report["status"] = "fair"
            else:
                quality_report["status"] = "poor"

            logger.info(
                "data_quality_analysis_complete",
                symbol=symbol,
                timeframe=timeframe,
                score=quality_report["score"],
                issues=len(quality_report["issues"]),
            )

            return quality_report

        except Exception as e:
            logger.error("data_quality_analysis_failed", error=str(e), exc_info=True)
            return {
                "status": "error",
                "message": str(e),
            }

    async def get_distribution_analysis(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Analyze distributions of OHLCV data.

        Returns statistics for each column:
        - Mean, median, std, min, max
        - Skewness, kurtosis
        - Histogram bins for visualization

        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Distribution analysis for each numeric column
        """
        try:
            # Fetch data
            query = select(MarketData).where(
                and_(
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                )
            )

            if start_date:
                query = query.where(MarketData.time >= start_date)
            if end_date:
                query = query.where(MarketData.time <= end_date)

            result = await self.db.execute(query)
            rows = result.scalars().all()

            if not rows:
                return {"status": "error", "message": "No data found"}

            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": int(r.volume) if r.volume else 0,
                }
                for r in rows
            ])

            # Add derived features
            df["returns"] = df["close"].pct_change() * 100
            df["range"] = df["high"] - df["low"]
            df["body"] = abs(df["close"] - df["open"])

            distributions = {}
            for col in ["open", "high", "low", "close", "volume", "returns", "range", "body"]:
                series = df[col].dropna()
                if len(series) == 0:
                    continue

                # Calculate histogram bins
                hist, bin_edges = np.histogram(series, bins=50)

                distributions[col] = {
                    "count": len(series),
                    "mean": round(float(series.mean()), 6),
                    "median": round(float(series.median()), 6),
                    "std": round(float(series.std()), 6),
                    "min": round(float(series.min()), 6),
                    "max": round(float(series.max()), 6),
                    "q25": round(float(series.quantile(0.25)), 6),
                    "q75": round(float(series.quantile(0.75)), 6),
                    "skewness": round(float(series.skew()), 4),
                    "kurtosis": round(float(series.kurtosis()), 4),
                    "histogram": {
                        "counts": hist.tolist(),
                        "bin_edges": [round(float(b), 6) for b in bin_edges.tolist()],
                    },
                }

            return {
                "status": "success",
                "symbol": symbol,
                "timeframe": timeframe,
                "data_points": len(df),
                "distributions": distributions,
            }

        except Exception as e:
            logger.error("distribution_analysis_failed", error=str(e), exc_info=True)
            return {"status": "error", "message": str(e)}

    async def get_correlation_matrix(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_indicators: bool = True,
    ) -> Dict[str, Any]:
        """
        Calculate correlation matrix for price data and derived features.

        Useful for:
        - Identifying redundant features
        - Understanding relationships between indicators
        - Feature selection for ML models

        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            start_date: Optional start date filter
            end_date: Optional end date filter
            include_indicators: Whether to include technical indicators

        Returns:
            Correlation matrix with feature names
        """
        try:
            # Fetch data
            query = select(MarketData).where(
                and_(
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                )
            )

            if start_date:
                query = query.where(MarketData.time >= start_date)
            if end_date:
                query = query.where(MarketData.time <= end_date)

            query = query.order_by(MarketData.time)

            result = await self.db.execute(query)
            rows = result.scalars().all()

            if not rows:
                return {"status": "error", "message": "No data found"}

            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": int(r.volume) if r.volume else 0,
                }
                for r in rows
            ])

            # Add derived features
            df["returns"] = df["close"].pct_change()
            df["range"] = df["high"] - df["low"]
            df["body"] = abs(df["close"] - df["open"])
            df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
            df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]

            if include_indicators:
                # Simple technical indicators (no external dependencies)
                df["sma_10"] = df["close"].rolling(10).mean()
                df["sma_20"] = df["close"].rolling(20).mean()
                df["ema_10"] = df["close"].ewm(span=10).mean()
                df["std_20"] = df["close"].rolling(20).std()
                df["volume_sma"] = df["volume"].rolling(20).mean()

                # RSI approximation
                delta = df["close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                df["rsi"] = 100 - (100 / (1 + rs))

                # ATR approximation
                tr = pd.concat([
                    df["high"] - df["low"],
                    (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs(),
                ], axis=1).max(axis=1)
                df["atr"] = tr.rolling(14).mean()

            # Drop NaN rows for correlation
            df_clean = df.dropna()

            # Calculate correlation matrix
            corr_matrix = df_clean.corr()

            # Convert to serializable format
            features = corr_matrix.columns.tolist()
            matrix = corr_matrix.values.tolist()

            # Find highly correlated pairs (excluding self-correlation)
            high_correlations = []
            for i, f1 in enumerate(features):
                for j, f2 in enumerate(features):
                    if i < j:  # Upper triangle only
                        corr = corr_matrix.iloc[i, j]
                        if abs(corr) > 0.8:
                            high_correlations.append({
                                "feature_1": f1,
                                "feature_2": f2,
                                "correlation": round(float(corr), 4),
                            })

            return {
                "status": "success",
                "symbol": symbol,
                "timeframe": timeframe,
                "data_points": len(df_clean),
                "features": features,
                "matrix": [[round(float(v), 4) for v in row] for row in matrix],
                "high_correlations": sorted(
                    high_correlations,
                    key=lambda x: abs(x["correlation"]),
                    reverse=True,
                ),
            }

        except Exception as e:
            logger.error("correlation_analysis_failed", error=str(e), exc_info=True)
            return {"status": "error", "message": str(e)}

    async def compare_periods(
        self,
        symbol: str,
        timeframe: str,
        period1_start: datetime,
        period1_end: datetime,
        period2_start: datetime,
        period2_end: datetime,
    ) -> Dict[str, Any]:
        """
        Compare two time periods for distribution shifts.

        Essential for:
        - Train/test split validation
        - Detecting regime changes
        - Validating backtest vs live data

        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            period1_start: Start of first period
            period1_end: End of first period
            period2_start: Start of second period
            period2_end: End of second period

        Returns:
            Comparison metrics between the two periods
        """
        try:
            # Fetch both periods
            async def fetch_period(start: datetime, end: datetime) -> pd.DataFrame:
                query = select(MarketData).where(
                    and_(
                        MarketData.symbol == symbol,
                        MarketData.timeframe == timeframe,
                        MarketData.time >= start,
                        MarketData.time <= end,
                    )
                )
                result = await self.db.execute(query)
                rows = result.scalars().all()
                return pd.DataFrame([
                    {
                        "open": float(r.open),
                        "high": float(r.high),
                        "low": float(r.low),
                        "close": float(r.close),
                        "volume": int(r.volume) if r.volume else 0,
                    }
                    for r in rows
                ])

            df1 = await fetch_period(period1_start, period1_end)
            df2 = await fetch_period(period2_start, period2_end)

            if len(df1) == 0 or len(df2) == 0:
                return {"status": "error", "message": "Insufficient data in one or both periods"}

            # Add derived features
            for df in [df1, df2]:
                df["returns"] = df["close"].pct_change() * 100
                df["range"] = df["high"] - df["low"]

            comparison = {
                "status": "success",
                "symbol": symbol,
                "timeframe": timeframe,
                "period1": {
                    "start": period1_start.isoformat(),
                    "end": period1_end.isoformat(),
                    "data_points": len(df1),
                },
                "period2": {
                    "start": period2_start.isoformat(),
                    "end": period2_end.isoformat(),
                    "data_points": len(df2),
                },
                "comparisons": {},
                "warnings": [],
            }

            # Compare distributions for key metrics
            for col in ["close", "returns", "range", "volume"]:
                s1 = df1[col].dropna()
                s2 = df2[col].dropna()

                if len(s1) == 0 or len(s2) == 0:
                    continue

                # Calculate distribution metrics
                mean_shift = (s2.mean() - s1.mean()) / s1.std() if s1.std() > 0 else 0
                std_ratio = s2.std() / s1.std() if s1.std() > 0 else 1

                comparison["comparisons"][col] = {
                    "period1": {
                        "mean": round(float(s1.mean()), 6),
                        "std": round(float(s1.std()), 6),
                        "min": round(float(s1.min()), 6),
                        "max": round(float(s1.max()), 6),
                    },
                    "period2": {
                        "mean": round(float(s2.mean()), 6),
                        "std": round(float(s2.std()), 6),
                        "min": round(float(s2.min()), 6),
                        "max": round(float(s2.max()), 6),
                    },
                    "mean_shift_std": round(float(mean_shift), 4),
                    "std_ratio": round(float(std_ratio), 4),
                }

                # Flag significant shifts
                if abs(mean_shift) > 1:
                    comparison["warnings"].append({
                        "type": "distribution_shift",
                        "feature": col,
                        "message": f"Significant mean shift in {col} ({mean_shift:.2f} std)",
                    })

                if std_ratio < 0.5 or std_ratio > 2:
                    comparison["warnings"].append({
                        "type": "volatility_change",
                        "feature": col,
                        "message": f"Significant volatility change in {col} (ratio: {std_ratio:.2f})",
                    })

            return comparison

        except Exception as e:
            logger.error("period_comparison_failed", error=str(e), exc_info=True)
            return {"status": "error", "message": str(e)}

    async def get_automated_eda_report(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive automated EDA report.

        Combines all analysis into a single report:
        - Data quality summary
        - Distribution analysis
        - Correlation matrix
        - Recommendations

        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Complete EDA report
        """
        try:
            # Run all analyses in parallel
            quality_task = self.get_data_quality_summary(symbol, timeframe, start_date, end_date)
            distribution_task = self.get_distribution_analysis(symbol, timeframe, start_date, end_date)
            correlation_task = self.get_correlation_matrix(symbol, timeframe, start_date, end_date)

            quality, distributions, correlations = await asyncio.gather(
                quality_task, distribution_task, correlation_task
            )

            # Generate recommendations
            recommendations = []

            # Quality-based recommendations
            if quality.get("score", 100) < 70:
                recommendations.append({
                    "priority": "high",
                    "category": "data_quality",
                    "action": "Review and clean data before using for backtests or ML training",
                })

            if quality.get("checks", {}).get("outliers", {}).get("percentage", 0) > 2:
                recommendations.append({
                    "priority": "medium",
                    "category": "outliers",
                    "action": "Consider winsorizing or removing outliers for more robust analysis",
                })

            if quality.get("checks", {}).get("data_gaps", {}).get("gap_count", 0) > 10:
                recommendations.append({
                    "priority": "medium",
                    "category": "data_gaps",
                    "action": "Investigate data gaps - may indicate market closures or data feed issues",
                })

            # Distribution-based recommendations
            returns_dist = distributions.get("distributions", {}).get("returns", {})
            if returns_dist.get("skewness", 0) > 1 or returns_dist.get("skewness", 0) < -1:
                recommendations.append({
                    "priority": "low",
                    "category": "distribution",
                    "action": f"Returns distribution is skewed ({returns_dist.get('skewness', 0):.2f}). Consider using robust estimators.",
                })

            # Correlation-based recommendations
            high_corr = correlations.get("high_correlations", [])
            if len(high_corr) > 3:
                recommendations.append({
                    "priority": "medium",
                    "category": "feature_engineering",
                    "action": f"Found {len(high_corr)} highly correlated feature pairs. Consider feature selection to reduce redundancy.",
                })

            return {
                "status": "success",
                "symbol": symbol,
                "timeframe": timeframe,
                "generated_at": datetime.utcnow().isoformat(),
                "quality_summary": quality,
                "distributions": distributions,
                "correlations": correlations,
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error("automated_eda_failed", error=str(e), exc_info=True)
            return {"status": "error", "message": str(e)}

    def _get_expected_gap(self, timeframe: str) -> timedelta:
        """Get expected time gap between candles for a timeframe."""
        gaps = {
            "M1": timedelta(minutes=1),
            "M5": timedelta(minutes=5),
            "M15": timedelta(minutes=15),
            "M30": timedelta(minutes=30),
            "H1": timedelta(hours=1),
            "H4": timedelta(hours=4),
            "D1": timedelta(days=1),
        }
        return gaps.get(timeframe, timedelta(minutes=5))
