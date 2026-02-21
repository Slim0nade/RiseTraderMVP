"""
A/B Test Service for comparing model configurations in the agent trading system.

Manages experiments that compare different LLM models (e.g., qwen3:14b vs deepseek-r1:14b)
or strategy configurations by tracking per-variant trade results and computing
statistical significance via Welch's t-test.

Uses the existing model_configurations table for persistent storage and
the ModelConfigurationRepository for data access.
"""

import random
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import numpy as np
from pydantic import BaseModel, Field
from scipy import stats as scipy_stats
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.model_configuration import ModelConfiguration
from src.database.repositories.model_configuration_repository import ModelConfigurationRepository
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ExperimentStatus(str, Enum):
    """Status of an A/B test experiment."""
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VariantDefinition(BaseModel):
    """Definition of a single variant in an A/B test."""
    name: str = Field(..., description="Variant name (e.g., 'qwen3:14b')")
    traffic_pct: int = Field(..., ge=0, le=100, description="Traffic allocation percentage")
    config: Dict[str, Any] = Field(default_factory=dict, description="Model/strategy configuration")


class ExperimentCreate(BaseModel):
    """Payload for creating a new A/B test experiment."""
    name: str = Field(..., max_length=100, description="Experiment name")
    description: str = Field(default="", description="Experiment description")
    agent_type: str = Field(default="signal_generator", description="Agent type being tested")
    variants: List[VariantDefinition] = Field(..., min_length=1, description="Variant definitions")


class VariantResult(BaseModel):
    """Recorded result for a single trade under a variant."""
    variant_id: UUID
    return_pct: float = Field(..., description="Trade return percentage")
    pnl: float = Field(default=0.0, description="Absolute P&L in USD")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra metrics")


class VariantStatistics(BaseModel):
    """Computed statistics for a single variant."""
    variant_id: UUID
    variant_name: str
    trade_count: int
    mean_return: float
    std_return: float
    total_pnl: float
    win_rate: float
    sharpe_ratio: Optional[float] = None


class ExperimentStatistics(BaseModel):
    """Full statistical comparison between experiment variants."""
    experiment_id: UUID
    experiment_name: str
    status: ExperimentStatus
    variants: List[VariantStatistics]
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None
    confidence_interval_95: Optional[Tuple[float, float]] = None
    winner: Optional[str] = None
    is_significant: bool = False


class ExperimentSummary(BaseModel):
    """Lightweight experiment info for listing."""
    experiment_id: UUID
    name: str
    status: ExperimentStatus
    variant_count: int
    total_results: int
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Pure statistical functions (testable without DB)
# ---------------------------------------------------------------------------

def compute_t_test(
    returns_a: List[float],
    returns_b: List[float],
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Compute Welch's t-test between two arrays of returns.

    Args:
        returns_a: Returns for variant A.
        returns_b: Returns for variant B.
        alpha: Significance level (default 0.05 for 95% confidence).

    Returns:
        Dictionary with t_statistic, p_value, confidence_interval_95,
        is_significant, and winner.
    """
    arr_a = np.array(returns_a, dtype=np.float64)
    arr_b = np.array(returns_b, dtype=np.float64)

    if len(arr_a) < 2 or len(arr_b) < 2:
        return {
            "t_statistic": None,
            "p_value": None,
            "confidence_interval_95": None,
            "is_significant": False,
            "winner": None,
        }

    t_stat, p_val = scipy_stats.ttest_ind(arr_a, arr_b, equal_var=False)

    # Confidence interval for the difference in means
    mean_diff = float(np.mean(arr_a) - np.mean(arr_b))
    se_diff = float(np.sqrt(np.var(arr_a, ddof=1) / len(arr_a) + np.var(arr_b, ddof=1) / len(arr_b)))

    # Degrees of freedom via Welch-Satterthwaite
    var_a = np.var(arr_a, ddof=1)
    var_b = np.var(arr_b, ddof=1)
    n_a = len(arr_a)
    n_b = len(arr_b)
    denom = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
    if denom > 0:
        df = ((var_a / n_a + var_b / n_b) ** 2) / denom
    else:
        df = min(n_a, n_b) - 1

    t_crit = float(scipy_stats.t.ppf(1 - alpha / 2, df))
    ci_lower = mean_diff - t_crit * se_diff
    ci_upper = mean_diff + t_crit * se_diff

    is_significant = float(p_val) < alpha

    winner = None
    if is_significant:
        winner = "A" if float(np.mean(arr_a)) > float(np.mean(arr_b)) else "B"

    return {
        "t_statistic": float(t_stat),
        "p_value": float(p_val),
        "confidence_interval_95": (float(ci_lower), float(ci_upper)),
        "is_significant": is_significant,
        "winner": winner,
    }


def compute_variant_stats(returns: List[float], pnls: List[float]) -> Dict[str, Any]:
    """
    Compute summary statistics for a single variant.

    Args:
        returns: List of per-trade return percentages.
        pnls: List of per-trade absolute P&L values.

    Returns:
        Dictionary with mean_return, std_return, total_pnl, win_rate, sharpe_ratio.
    """
    if not returns:
        return {
            "trade_count": 0,
            "mean_return": 0.0,
            "std_return": 0.0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "sharpe_ratio": None,
        }

    arr = np.array(returns, dtype=np.float64)
    mean_ret = float(np.mean(arr))
    std_ret = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    total_pnl = float(np.sum(pnls)) if pnls else 0.0
    wins = int(np.sum(arr > 0))
    win_rate = wins / len(arr)

    # Annualized Sharpe (assume daily returns, ~252 trading days)
    sharpe = None
    if std_ret > 0:
        sharpe = float((mean_ret / std_ret) * np.sqrt(252))

    return {
        "trade_count": len(arr),
        "mean_return": mean_ret,
        "std_return": std_ret,
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe,
    }


def select_variant_weighted(
    variant_ids: List[UUID],
    weights: List[int],
) -> UUID:
    """
    Select a variant ID using weighted random selection.

    Args:
        variant_ids: List of variant UUIDs.
        weights: Corresponding traffic allocation weights (percentages).

    Returns:
        Selected variant UUID.

    Raises:
        ValueError: If inputs are empty or mismatched.
    """
    if not variant_ids or not weights:
        raise ValueError("variant_ids and weights must be non-empty")
    if len(variant_ids) != len(weights):
        raise ValueError("variant_ids and weights must have same length")

    total = sum(weights)
    if total == 0:
        raise ValueError("Total weight must be > 0")

    normalized = [w / total for w in weights]
    idx = random.choices(range(len(variant_ids)), weights=normalized, k=1)[0]
    return variant_ids[idx]


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class ABTestService:
    """
    Service for managing A/B test experiments on agent model configurations.

    Stores experiment data in the model_configurations table using the
    ab_test_group and ab_test_allocation_pct columns, plus the tags and
    performance_metrics JSON columns for results storage.

    Constructor follows the same pattern as StrategyService: takes an
    AsyncSession, wraps a repository.
    """

    # Tag keys used in ModelConfiguration.tags for experiment metadata
    _TAG_EXPERIMENT_ID = "ab_experiment_id"
    _TAG_EXPERIMENT_NAME = "ab_experiment_name"
    _TAG_EXPERIMENT_STATUS = "ab_experiment_status"
    _TAG_EXPERIMENT_DESC = "ab_experiment_description"
    _TAG_VARIANT_INDEX = "ab_variant_index"
    _TAG_RESULTS = "ab_results"

    def __init__(self, session: AsyncSession):
        """
        Initialize ABTestService.

        Args:
            session: SQLAlchemy async session.
        """
        self.session = session
        self.repo = ModelConfigurationRepository(session)
        logger.info("ab_test_service_initialized")

    # ------------------------------------------------------------------
    # Create experiment
    # ------------------------------------------------------------------

    async def create_experiment(
        self,
        name: str,
        description: str = "",
        variants: Optional[List[VariantDefinition]] = None,
        traffic_split: Optional[List[int]] = None,
        agent_type: str = "signal_generator",
    ) -> Dict[str, Any]:
        """
        Create a new A/B test experiment.

        Each variant is persisted as a row in model_configurations with
        matching ab_test_group = experiment_id.

        Args:
            name: Experiment name.
            description: Human-readable description.
            variants: List of VariantDefinition objects.
            traffic_split: Traffic percentages (must match variants length).
                           If None, derived from variants[].traffic_pct.
            agent_type: Agent type being tested.

        Returns:
            Dictionary with experiment_id and variant_ids.
        """
        if not variants or len(variants) == 0:
            raise ValueError("At least one variant is required")

        # Apply traffic_split override if provided
        if traffic_split is not None:
            if len(traffic_split) != len(variants):
                raise ValueError("traffic_split length must match variants length")
            for i, pct in enumerate(traffic_split):
                variants[i].traffic_pct = pct

        # Validate traffic sums to 100
        total_traffic = sum(v.traffic_pct for v in variants)
        if total_traffic != 100:
            raise ValueError(f"Traffic split must sum to 100, got {total_traffic}")

        experiment_id = uuid4()
        variant_ids: List[UUID] = []

        for idx, variant in enumerate(variants):
            variant_id = uuid4()
            variant_ids.append(variant_id)

            config = await self.repo.create(
                id=variant_id,
                config_name=f"{name}::variant_{idx}::{variant.name}",
                config_type="llm",
                agent_type=agent_type,
                version="1.0.0",
                is_active=True,
                is_default=False,
                ab_test_group=str(experiment_id),
                ab_test_allocation_pct=variant.traffic_pct,
                llm_parameters=variant.config if variant.config else None,
                performance_metrics={},
                tags={
                    self._TAG_EXPERIMENT_ID: str(experiment_id),
                    self._TAG_EXPERIMENT_NAME: name,
                    self._TAG_EXPERIMENT_STATUS: ExperimentStatus.RUNNING.value,
                    self._TAG_EXPERIMENT_DESC: description,
                    self._TAG_VARIANT_INDEX: idx,
                    self._TAG_RESULTS: [],
                },
                created_by="ab_test_service",
                notes=f"A/B test variant: {variant.name}",
            )

        logger.info(
            "ab_experiment_created",
            experiment_id=str(experiment_id),
            name=name,
            variant_count=len(variants),
        )

        return {
            "experiment_id": experiment_id,
            "variant_ids": variant_ids,
            "name": name,
            "status": ExperimentStatus.RUNNING.value,
        }

    # ------------------------------------------------------------------
    # List active experiments
    # ------------------------------------------------------------------

    async def get_active_experiments(self) -> List[ExperimentSummary]:
        """
        List all running A/B test experiments.

        Returns:
            List of ExperimentSummary for active experiments.
        """
        configs = await self.repo.get_active_configs()

        # Group by experiment_id
        experiments: Dict[str, List[ModelConfiguration]] = {}
        for cfg in configs:
            if cfg.tags and self._TAG_EXPERIMENT_ID in cfg.tags:
                exp_id = cfg.tags[self._TAG_EXPERIMENT_ID]
                status = cfg.tags.get(self._TAG_EXPERIMENT_STATUS, "")
                if status == ExperimentStatus.RUNNING.value:
                    experiments.setdefault(exp_id, []).append(cfg)

        summaries: List[ExperimentSummary] = []
        for exp_id, cfgs in experiments.items():
            first = cfgs[0]
            total_results = 0
            for c in cfgs:
                results = (c.tags or {}).get(self._TAG_RESULTS, [])
                total_results += len(results)

            summaries.append(ExperimentSummary(
                experiment_id=UUID(exp_id),
                name=first.tags.get(self._TAG_EXPERIMENT_NAME, "unknown"),
                status=ExperimentStatus.RUNNING,
                variant_count=len(cfgs),
                total_results=total_results,
                created_at=first.created_at,
            ))

        return summaries

    # ------------------------------------------------------------------
    # Select variant
    # ------------------------------------------------------------------

    async def select_variant(self, experiment_id: UUID) -> UUID:
        """
        Select a variant based on traffic allocation weights.

        Args:
            experiment_id: Experiment UUID.

        Returns:
            Selected variant UUID.

        Raises:
            ValueError: If experiment not found or no active variants.
        """
        configs = await self._get_experiment_configs(experiment_id)
        if not configs:
            raise ValueError(f"No variants found for experiment {experiment_id}")

        variant_ids = [cfg.id for cfg in configs]
        weights = [cfg.ab_test_allocation_pct or 0 for cfg in configs]

        selected = select_variant_weighted(variant_ids, weights)

        logger.debug(
            "ab_variant_selected",
            experiment_id=str(experiment_id),
            variant_id=str(selected),
        )

        return selected

    # ------------------------------------------------------------------
    # Record result
    # ------------------------------------------------------------------

    async def record_result(
        self,
        experiment_id: UUID,
        variant_id: UUID,
        metrics: Dict[str, Any],
    ) -> None:
        """
        Record a trade result for a variant.

        Appends to the ab_results list in the variant's tags JSON.

        Args:
            experiment_id: Experiment UUID.
            variant_id: Variant UUID.
            metrics: Dictionary with at least 'return_pct' key. May also
                     contain 'pnl', 'symbol', 'timestamp', etc.
        """
        config = await self.repo.get_by_id(variant_id)
        if config is None:
            raise ValueError(f"Variant {variant_id} not found")

        exp_id_from_tags = (config.tags or {}).get(self._TAG_EXPERIMENT_ID)
        if exp_id_from_tags != str(experiment_id):
            raise ValueError(
                f"Variant {variant_id} does not belong to experiment {experiment_id}"
            )

        # Append result
        tags = dict(config.tags or {})
        results = list(tags.get(self._TAG_RESULTS, []))
        results.append({
            "return_pct": metrics.get("return_pct", 0.0),
            "pnl": metrics.get("pnl", 0.0),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in metrics.items() if k not in ("return_pct", "pnl")},
        })
        tags[self._TAG_RESULTS] = results
        config.tags = tags

        # Also update performance_metrics with running totals
        vstats = compute_variant_stats(
            returns=[r["return_pct"] for r in results],
            pnls=[r.get("pnl", 0.0) for r in results],
        )
        config.performance_metrics = vstats

        await self.session.commit()

        logger.info(
            "ab_result_recorded",
            experiment_id=str(experiment_id),
            variant_id=str(variant_id),
            result_count=len(results),
        )

    # ------------------------------------------------------------------
    # Compute statistics
    # ------------------------------------------------------------------

    async def compute_statistics(self, experiment_id: UUID) -> ExperimentStatistics:
        """
        Compute statistical comparison between experiment variants.

        For 2 variants uses Welch's t-test on returns.
        For 1 or 3+ variants, returns per-variant stats without t-test.

        Args:
            experiment_id: Experiment UUID.

        Returns:
            ExperimentStatistics with per-variant stats and t-test results.
        """
        configs = await self._get_experiment_configs(experiment_id)
        if not configs:
            raise ValueError(f"Experiment {experiment_id} not found")

        first = configs[0]
        exp_name = (first.tags or {}).get(self._TAG_EXPERIMENT_NAME, "unknown")
        exp_status_str = (first.tags or {}).get(
            self._TAG_EXPERIMENT_STATUS, ExperimentStatus.RUNNING.value
        )
        exp_status = ExperimentStatus(exp_status_str)

        # Build per-variant stats
        variant_stats_list: List[VariantStatistics] = []
        all_returns: List[List[float]] = []

        for cfg in configs:
            results = (cfg.tags or {}).get(self._TAG_RESULTS, [])
            returns = [r["return_pct"] for r in results]
            pnls = [r.get("pnl", 0.0) for r in results]
            all_returns.append(returns)

            vstats = compute_variant_stats(returns, pnls)

            # Extract variant name from config_name: "exp::variant_N::name"
            parts = cfg.config_name.split("::")
            variant_name = parts[-1] if len(parts) >= 3 else cfg.config_name

            variant_stats_list.append(VariantStatistics(
                variant_id=cfg.id,
                variant_name=variant_name,
                trade_count=vstats["trade_count"],
                mean_return=vstats["mean_return"],
                std_return=vstats["std_return"],
                total_pnl=vstats["total_pnl"],
                win_rate=vstats["win_rate"],
                sharpe_ratio=vstats["sharpe_ratio"],
            ))

        # T-test (only for exactly 2 variants)
        t_stat = None
        p_val = None
        ci_95 = None
        winner = None
        is_sig = False

        if len(all_returns) == 2:
            ttest = compute_t_test(all_returns[0], all_returns[1])
            t_stat = ttest["t_statistic"]
            p_val = ttest["p_value"]
            ci_95 = ttest["confidence_interval_95"]
            is_sig = ttest["is_significant"]
            if ttest["winner"] == "A":
                winner = variant_stats_list[0].variant_name
            elif ttest["winner"] == "B":
                winner = variant_stats_list[1].variant_name

        return ExperimentStatistics(
            experiment_id=experiment_id,
            experiment_name=exp_name,
            status=exp_status,
            variants=variant_stats_list,
            t_statistic=t_stat,
            p_value=p_val,
            confidence_interval_95=ci_95,
            winner=winner,
            is_significant=is_sig,
        )

    # ------------------------------------------------------------------
    # Promote winner
    # ------------------------------------------------------------------

    async def promote_winner(self, experiment_id: UUID) -> Dict[str, Any]:
        """
        Mark experiment as completed and promote the winning variant.

        The winner is determined by highest mean return among variants.
        The winning variant is set as is_default=True for its agent_type,
        and all variants are marked inactive (experiment over).

        Args:
            experiment_id: Experiment UUID.

        Returns:
            Dictionary with winner info.
        """
        configs = await self._get_experiment_configs(experiment_id)
        if not configs:
            raise ValueError(f"Experiment {experiment_id} not found")

        # Find the best variant by mean_return
        best_config = None
        best_mean = float("-inf")

        for cfg in configs:
            results = (cfg.tags or {}).get(self._TAG_RESULTS, [])
            if results:
                returns = [r["return_pct"] for r in results]
                mean_ret = float(np.mean(returns))
                if mean_ret > best_mean:
                    best_mean = mean_ret
                    best_config = cfg

        if best_config is None:
            # No results recorded - pick first variant
            best_config = configs[0]

        # Update all variant configs
        for cfg in configs:
            tags = dict(cfg.tags or {})
            tags[self._TAG_EXPERIMENT_STATUS] = ExperimentStatus.COMPLETED.value
            cfg.tags = tags
            cfg.is_active = False
            cfg.is_default = (cfg.id == best_config.id)
            if cfg.id == best_config.id:
                cfg.deployed_at = datetime.now(timezone.utc)

        await self.session.commit()

        parts = best_config.config_name.split("::")
        winner_name = parts[-1] if len(parts) >= 3 else best_config.config_name

        logger.info(
            "ab_experiment_promoted",
            experiment_id=str(experiment_id),
            winner_variant_id=str(best_config.id),
            winner_name=winner_name,
            mean_return=best_mean,
        )

        return {
            "experiment_id": experiment_id,
            "winner_variant_id": best_config.id,
            "winner_name": winner_name,
            "mean_return": best_mean,
            "status": ExperimentStatus.COMPLETED.value,
        }

    # ------------------------------------------------------------------
    # Get experiment results
    # ------------------------------------------------------------------

    async def get_experiment_results(self, experiment_id: UUID) -> Dict[str, Any]:
        """
        Get full experiment results with per-variant metrics.

        Args:
            experiment_id: Experiment UUID.

        Returns:
            Dictionary with experiment info and statistics.
        """
        stats = await self.compute_statistics(experiment_id)
        configs = await self._get_experiment_configs(experiment_id)

        variant_details = []
        for cfg in configs:
            results = (cfg.tags or {}).get(self._TAG_RESULTS, [])
            parts = cfg.config_name.split("::")
            variant_name = parts[-1] if len(parts) >= 3 else cfg.config_name

            variant_details.append({
                "variant_id": str(cfg.id),
                "variant_name": variant_name,
                "traffic_pct": cfg.ab_test_allocation_pct,
                "result_count": len(results),
                "performance_metrics": cfg.performance_metrics or {},
                "is_default": cfg.is_default,
            })

        return {
            "experiment_id": str(experiment_id),
            "experiment_name": stats.experiment_name,
            "status": stats.status.value,
            "variants": variant_details,
            "statistics": {
                "t_statistic": stats.t_statistic,
                "p_value": stats.p_value,
                "confidence_interval_95": stats.confidence_interval_95,
                "is_significant": stats.is_significant,
                "winner": stats.winner,
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_experiment_configs(
        self, experiment_id: UUID
    ) -> List[ModelConfiguration]:
        """
        Fetch all ModelConfiguration rows belonging to an experiment.

        Uses a direct query filtering on the ab_test_group column.
        """
        query = (
            select(ModelConfiguration)
            .where(ModelConfiguration.ab_test_group == str(experiment_id))
            .order_by(ModelConfiguration.config_name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
