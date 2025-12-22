"""
Statistical comparison service for A/B testing different agent configurations.

Provides:
- Statistical significance testing (t-test for returns)
- Trade overlap analysis (consensus vs divergent trades)
- Equity curve alignment for visual comparison
- Performance breakdown by time period
- Comprehensive comparison reports

T103: Create ComparisonService class
T104: Implement compare_runs method for side-by-side metrics
T105: Add statistical significance testing (scipy.stats.ttest_ind)
T106: Implement trade overlap analysis
T107: Add equity curve alignment
T108: Implement performance breakdown by time period
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.backtest_repository import BacktestRepository


@dataclass
class StatisticalTest:
    """Result of statistical significance test."""

    t_statistic: float
    p_value: float
    is_significant: bool  # p < 0.05
    degrees_of_freedom: float
    confidence_interval: Optional[Tuple[float, float]] = None
    mean_difference: Optional[float] = None


@dataclass
class TradeOverlap:
    """Analysis of trade overlap between two runs."""

    consensus_trades: int  # Both runs took same trade
    divergent_trades_a: int  # Only run A took trade
    divergent_trades_b: int  # Only run B took trade
    overlap_rate: float  # consensus / (consensus + divergent_a + divergent_b)
    consensus_trade_details: List[Dict[str, Any]]


@dataclass
class ComparisonResult:
    """Complete A/B comparison result."""

    run_a_id: UUID
    run_b_id: UUID
    metrics_comparison: Dict[str, Any]
    statistical_tests: Dict[str, StatisticalTest]
    trade_overlap: TradeOverlap
    equity_curves: Dict[str, List[Any]]
    performance_breakdown: Dict[str, Dict[str, Any]]
    recommendation: str  # "run_a" | "run_b" | "no_significant_difference"


class ComparisonService:
    """
    Statistical comparison service for A/B testing.

    T103: Create ComparisonService class
    """

    def __init__(self):
        """Initialize comparison service."""
        self.significance_threshold = 0.05  # p < 0.05 for significance

    async def compare_runs(
        self,
        run_a_id: UUID,
        run_b_id: UUID,
        async_session: AsyncSession,
        time_window_minutes: int = 5,
    ) -> ComparisonResult:
        """
        Compare two backtest runs with statistical analysis.

        T104: Implement compare_runs method for side-by-side metrics

        Args:
            run_a_id: First backtest run ID
            run_b_id: Second backtest run ID
            async_session: Database session
            time_window_minutes: Time window for trade overlap (default 5 min)

        Returns:
            ComparisonResult with complete comparison analysis

        Raises:
            ValueError: If runs have different symbols or invalid data
        """
        repo = BacktestRepository(async_session)

        # Fetch both runs
        run_a = await repo.get_run_by_id(run_a_id)
        run_b = await repo.get_run_by_id(run_b_id)

        if run_a is None or run_b is None:
            raise ValueError("One or both run IDs not found")

        # Validate same symbol
        if run_a.symbol != run_b.symbol:
            raise ValueError(
                f"Cannot compare different symbols: {run_a.symbol} vs {run_b.symbol}"
            )

        # Get trades for both runs
        trades_a = await repo.get_trades_for_run(run_a_id)
        trades_b = await repo.get_trades_for_run(run_b_id)

        # Get equity curves
        equity_a = await repo.get_equity_curve(run_a_id)
        equity_b = await repo.get_equity_curve(run_b_id)

        # Side-by-side metrics
        metrics_comparison = {
            "run_a": {
                "total_return": float(run_a.total_return or 0),
                "sharpe_ratio": float(run_a.sharpe_ratio or 0),
                "max_drawdown": float(run_a.max_drawdown or 0),
                "win_rate": float(run_a.win_rate or 0),
                "profit_factor": float(run_a.profit_factor or 0),
                "total_trades": run_a.total_trades or 0,
            },
            "run_b": {
                "total_return": float(run_b.total_return or 0),
                "sharpe_ratio": float(run_b.sharpe_ratio or 0),
                "max_drawdown": float(run_b.max_drawdown or 0),
                "win_rate": float(run_b.win_rate or 0),
                "profit_factor": float(run_b.profit_factor or 0),
                "total_trades": run_b.total_trades or 0,
            },
        }

        # Statistical significance tests
        returns_a = self._extract_returns_from_trades(trades_a)
        returns_b = self._extract_returns_from_trades(trades_b)

        statistical_tests = {
            "returns_ttest": self.calculate_statistical_significance(
                returns_a, returns_b
            )
        }

        # Trade overlap analysis
        trade_overlap = self.analyze_trade_overlap(
            trades_a, trades_b, time_window_minutes
        )

        # Equity curve alignment
        equity_curves = self.align_equity_curves(equity_a, equity_b, normalize=False)

        # Performance breakdown
        performance_breakdown = {
            "run_a_by_month": self.breakdown_by_period(trades_a, period="month"),
            "run_b_by_month": self.breakdown_by_period(trades_b, period="month"),
        }

        # Generate recommendation
        recommendation = self._generate_recommendation(
            metrics_comparison, statistical_tests["returns_ttest"]
        )

        return ComparisonResult(
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            metrics_comparison=metrics_comparison,
            statistical_tests=statistical_tests,
            trade_overlap=trade_overlap,
            equity_curves=equity_curves,
            performance_breakdown=performance_breakdown,
            recommendation=recommendation,
        )

    def calculate_statistical_significance(
        self,
        returns_a: List[float],
        returns_b: List[float],
        confidence_level: float = 0.95,
    ) -> StatisticalTest:
        """
        Calculate statistical significance using Welch's t-test.

        T105: Add statistical significance testing (scipy.stats.ttest_ind)

        Uses Welch's t-test (unequal variances) for robustness.

        Args:
            returns_a: List of returns from run A
            returns_b: List of returns from run B
            confidence_level: Confidence level for intervals (default 0.95)

        Returns:
            StatisticalTest with t-statistic, p-value, and significance

        Raises:
            ValueError: If returns are empty
        """
        if len(returns_a) == 0 or len(returns_b) == 0:
            raise ValueError("Empty returns provided for statistical test")

        # Convert to numpy arrays
        arr_a = np.array(returns_a)
        arr_b = np.array(returns_b)

        # Welch's t-test (doesn't assume equal variances)
        t_statistic, p_value = stats.ttest_ind(arr_a, arr_b, equal_var=False)

        # Degrees of freedom for Welch's test
        var_a = np.var(arr_a, ddof=1)
        var_b = np.var(arr_b, ddof=1)
        n_a = len(arr_a)
        n_b = len(arr_b)

        if var_a == 0 and var_b == 0:
            # Both have zero variance - perfectly identical
            dof = n_a + n_b - 2
        elif var_a == 0 or var_b == 0:
            # One has zero variance
            dof = max(n_a, n_b) - 1
        else:
            # Welch-Satterthwaite equation
            dof = ((var_a / n_a + var_b / n_b) ** 2) / (
                (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
            )

        # Confidence interval for mean difference
        mean_diff = np.mean(arr_a) - np.mean(arr_b)
        se_diff = np.sqrt(var_a / n_a + var_b / n_b) if (var_a + var_b) > 0 else 0

        if se_diff > 0:
            t_critical = stats.t.ppf((1 + confidence_level) / 2, dof)
            ci_lower = mean_diff - t_critical * se_diff
            ci_upper = mean_diff + t_critical * se_diff
            confidence_interval = (float(ci_lower), float(ci_upper))
        else:
            confidence_interval = (float(mean_diff), float(mean_diff))

        return StatisticalTest(
            t_statistic=float(t_statistic) if not np.isnan(t_statistic) else 0.0,
            p_value=float(p_value) if not np.isnan(p_value) else 1.0,
            is_significant=float(p_value) < self.significance_threshold
            if not np.isnan(p_value)
            else False,
            degrees_of_freedom=float(dof),
            confidence_interval=confidence_interval,
            mean_difference=float(mean_diff),
        )

    def analyze_trade_overlap(
        self,
        trades_a: List[Dict[str, Any]],
        trades_b: List[Dict[str, Any]],
        time_window_minutes: int = 5,
    ) -> TradeOverlap:
        """
        Analyze trade overlap between two runs.

        T106: Implement trade overlap analysis (consensus vs divergent trades)

        Consensus trade = Both runs entered same direction within time window.
        Divergent trade = Only one run took the trade.

        Args:
            trades_a: Trades from run A
            trades_b: Trades from run B
            time_window_minutes: Time window for matching trades (default 5 min)

        Returns:
            TradeOverlap with consensus and divergent trade counts
        """
        if len(trades_a) == 0 and len(trades_b) == 0:
            return TradeOverlap(
                consensus_trades=0,
                divergent_trades_a=0,
                divergent_trades_b=0,
                overlap_rate=0.0,
                consensus_trade_details=[],
            )

        time_window = timedelta(minutes=time_window_minutes)
        consensus_trades = []
        matched_b_indices = set()

        # Find consensus trades (A matched with B)
        for trade_a in trades_a:
            entry_time_a = trade_a.get("entry_time") or trade_a.get("timestamp")
            direction_a = trade_a.get("direction") or trade_a.get("action")

            if entry_time_a is None or direction_a is None:
                continue

            for i, trade_b in enumerate(trades_b):
                if i in matched_b_indices:
                    continue  # Already matched

                entry_time_b = trade_b.get("entry_time") or trade_b.get("timestamp")
                direction_b = trade_b.get("direction") or trade_b.get("action")

                if entry_time_b is None or direction_b is None:
                    continue

                # Check if within time window and same direction
                time_diff = abs((entry_time_a - entry_time_b).total_seconds())
                if time_diff <= time_window.total_seconds() and direction_a == direction_b:
                    # Consensus trade found
                    consensus_trades.append(
                        {
                            "entry_time_a": entry_time_a,
                            "entry_time_b": entry_time_b,
                            "direction": direction_a,
                            "profit_a": trade_a.get("profit") or trade_a.get("pnl"),
                            "profit_b": trade_b.get("profit") or trade_b.get("pnl"),
                            "profit_diff": (trade_b.get("profit") or Decimal("0"))
                            - (trade_a.get("profit") or Decimal("0")),
                        }
                    )
                    matched_b_indices.add(i)
                    break  # Match found for trade_a

        # Count divergent trades
        consensus_count = len(consensus_trades)
        divergent_a = len(trades_a) - consensus_count
        divergent_b = len(trades_b) - consensus_count

        # Calculate overlap rate
        total_unique_trades = consensus_count + divergent_a + divergent_b
        overlap_rate = consensus_count / total_unique_trades if total_unique_trades > 0 else 0.0

        return TradeOverlap(
            consensus_trades=consensus_count,
            divergent_trades_a=divergent_a,
            divergent_trades_b=divergent_b,
            overlap_rate=float(overlap_rate),
            consensus_trade_details=consensus_trades,
        )

    def align_equity_curves(
        self,
        equity_a: List[Dict[str, Any]],
        equity_b: List[Dict[str, Any]],
        normalize: bool = False,
    ) -> Dict[str, List[Any]]:
        """
        Align equity curves to common timestamps for visual comparison.

        T107: Add equity curve alignment for visual comparison

        Args:
            equity_a: Equity curve from run A (list of {timestamp, equity})
            equity_b: Equity curve from run B
            normalize: If True, normalize to start at 1.0 (for % comparison)

        Returns:
            Dict with aligned timestamps and equity values
        """
        if len(equity_a) == 0 or len(equity_b) == 0:
            return {"timestamps": [], "equity_a": [], "equity_b": []}

        # Convert to pandas DataFrames
        df_a = pd.DataFrame(equity_a)
        df_b = pd.DataFrame(equity_b)

        if "timestamp" not in df_a.columns or "equity" not in df_a.columns:
            return {"timestamps": [], "equity_a": [], "equity_b": []}

        df_a = df_a[["timestamp", "equity"]].copy()
        df_b = df_b[["timestamp", "equity"]].copy()

        # Set timestamp as index
        df_a.set_index("timestamp", inplace=True)
        df_b.set_index("timestamp", inplace=True)

        # Merge on common timeline (outer join)
        df_merged = pd.merge(
            df_a, df_b, left_index=True, right_index=True, how="outer", suffixes=("_a", "_b")
        )

        # Sort by timestamp
        df_merged.sort_index(inplace=True)

        # Forward fill to interpolate missing values
        df_merged["equity_a"] = df_merged["equity_a"].fillna(method="ffill").fillna(method="bfill")
        df_merged["equity_b"] = df_merged["equity_b"].fillna(method="ffill").fillna(method="bfill")

        # Normalize if requested
        if normalize and len(df_merged) > 0:
            initial_a = df_merged["equity_a"].iloc[0]
            initial_b = df_merged["equity_b"].iloc[0]

            if initial_a > 0:
                df_merged["equity_a"] = df_merged["equity_a"] / initial_a
            if initial_b > 0:
                df_merged["equity_b"] = df_merged["equity_b"] / initial_b

        return {
            "timestamps": df_merged.index.tolist(),
            "equity_a": df_merged["equity_a"].tolist(),
            "equity_b": df_merged["equity_b"].tolist(),
        }

    def breakdown_by_period(
        self,
        trades: List[Dict[str, Any]],
        period: str = "month",
    ) -> Dict[str, Dict[str, Any]]:
        """
        Break down performance by time period.

        T108: Implement performance breakdown by time period

        Args:
            trades: List of trades
            period: "day" | "week" | "month"

        Returns:
            Dict mapping period to performance metrics
        """
        if len(trades) == 0:
            return {}

        # Convert to DataFrame
        df = pd.DataFrame(trades)

        if "entry_time" not in df.columns:
            if "timestamp" in df.columns:
                df["entry_time"] = df["timestamp"]
            else:
                return {}

        if "profit" not in df.columns:
            if "pnl" in df.columns:
                df["profit"] = df["pnl"]
            else:
                return {}

        # Add period column
        if period == "day":
            df["period"] = df["entry_time"].dt.strftime("%Y-%m-%d")
        elif period == "week":
            df["period"] = df["entry_time"].dt.strftime("%Y-W%U")
        elif period == "month":
            df["period"] = df["entry_time"].dt.strftime("%Y-%m")
        else:
            raise ValueError(f"Invalid period: {period}. Must be 'day', 'week', or 'month'.")

        # Group by period
        grouped = df.groupby("period")

        breakdown = {}
        for period_key, group in grouped:
            profits = group["profit"].astype(float)
            breakdown[period_key] = {
                "total_profit": float(profits.sum()),
                "num_trades": len(group),
                "win_rate": float(len(group[profits > 0]) / len(group))
                if len(group) > 0
                else 0.0,
                "avg_profit": float(profits.mean()) if len(group) > 0 else 0.0,
            }

        return breakdown

    def _extract_returns_from_trades(self, trades: List[Dict[str, Any]]) -> List[float]:
        """Extract returns from trades for statistical testing."""
        returns = []
        for trade in trades:
            profit = trade.get("profit") or trade.get("pnl")
            if profit is not None:
                # Convert to return % (assuming profit is in base currency)
                # For now, use raw profit as proxy for return
                returns.append(float(profit))
        return returns

    def _generate_recommendation(
        self,
        metrics_comparison: Dict[str, Any],
        returns_ttest: StatisticalTest,
    ) -> str:
        """
        Generate recommendation based on comparison results.

        Logic:
        - If statistically significant difference in returns, recommend better one
        - If no significant difference, check composite score (Sharpe, win rate, etc.)
        - If still unclear, return "no_significant_difference"
        """
        if returns_ttest.is_significant:
            # Statistically significant difference
            if returns_ttest.mean_difference > 0:
                return "run_a"  # Run A has higher mean return
            else:
                return "run_b"  # Run B has higher mean return
        else:
            # No statistical significance - use composite score
            score_a = self._calculate_composite_score(metrics_comparison["run_a"])
            score_b = self._calculate_composite_score(metrics_comparison["run_b"])

            if abs(score_a - score_b) > 0.1:  # 10% difference threshold
                return "run_a" if score_a > score_b else "run_b"
            else:
                return "no_significant_difference"

    def _calculate_composite_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate composite score for ranking.

        Weighted average of:
        - Sharpe ratio (30%)
        - Total return (25%)
        - Profit factor (20%)
        - Win rate (15%)
        - Max drawdown penalty (10%)
        """
        sharpe = metrics.get("sharpe_ratio", 0.0)
        total_return = metrics.get("total_return", 0.0)
        profit_factor = metrics.get("profit_factor", 0.0)
        win_rate = metrics.get("win_rate", 0.0)
        max_drawdown = metrics.get("max_drawdown", 0.0)

        # Normalize Sharpe (assume 0-3 range)
        sharpe_norm = min(sharpe / 3.0, 1.0) if sharpe > 0 else 0.0

        # Normalize total return (assume 0-100% range)
        return_norm = min(total_return, 1.0)

        # Normalize profit factor (assume 1-3 range)
        pf_norm = min((profit_factor - 1.0) / 2.0, 1.0) if profit_factor > 1.0 else 0.0

        # Win rate already 0-1

        # Drawdown penalty (0-1, lower is better)
        dd_penalty = min(abs(max_drawdown), 1.0)

        composite = (
            0.30 * sharpe_norm
            + 0.25 * return_norm
            + 0.20 * pf_norm
            + 0.15 * win_rate
            - 0.10 * dd_penalty
        )

        return float(composite)

    def generate_report(self, comparison: ComparisonResult) -> Dict[str, Any]:
        """
        Generate comprehensive comparison report.

        Returns:
            Dict with summary, recommendation, and detailed analysis
        """
        metrics_a = comparison.metrics_comparison["run_a"]
        metrics_b = comparison.metrics_comparison["run_b"]
        ttest = comparison.statistical_tests["returns_ttest"]

        report = {
            "summary": {
                "run_a_id": str(comparison.run_a_id),
                "run_b_id": str(comparison.run_b_id),
                "recommendation": comparison.recommendation,
                "statistically_significant": ttest.is_significant,
                "p_value": ttest.p_value,
            },
            "recommendation": comparison.recommendation,
            "detailed_metrics": {
                "run_a": metrics_a,
                "run_b": metrics_b,
                "differences": {
                    "total_return_diff": metrics_a["total_return"]
                    - metrics_b["total_return"],
                    "sharpe_diff": metrics_a["sharpe_ratio"] - metrics_b["sharpe_ratio"],
                    "win_rate_diff": metrics_a["win_rate"] - metrics_b["win_rate"],
                },
            },
            "statistical_analysis": {
                "t_statistic": ttest.t_statistic,
                "p_value": ttest.p_value,
                "is_significant": ttest.is_significant,
                "mean_difference": ttest.mean_difference,
                "confidence_interval": ttest.confidence_interval,
            },
            "trade_analysis": {
                "consensus_trades": comparison.trade_overlap.consensus_trades,
                "divergent_trades_a": comparison.trade_overlap.divergent_trades_a,
                "divergent_trades_b": comparison.trade_overlap.divergent_trades_b,
                "overlap_rate": comparison.trade_overlap.overlap_rate,
            },
            "performance_breakdown": comparison.performance_breakdown,
        }

        return report
