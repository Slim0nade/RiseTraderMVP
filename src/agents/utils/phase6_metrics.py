"""
Phase 6 Prometheus Metrics - Monitoring for adversarial safety pipeline.

Provides comprehensive metrics for:
- Bull/Bear debate layer performance
- Risk debate team performance
- Fund Manager approval decisions
- Pipeline latency and throughput
- Decision quality scores

All metrics are exposed via Prometheus client for Grafana dashboards.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# Debate Layer Metrics (Bull/Bear Adversarial Debate)
# =============================================================================

debate_decisions_total = Counter(
    "debate_decisions_total",
    "Total number of debate decisions made",
    ["symbol", "direction", "consensus_reached"]
)

debate_latency_seconds = Histogram(
    "debate_latency_seconds",
    "Debate decision latency in seconds",
    ["symbol"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

debate_consensus_confidence = Gauge(
    "debate_consensus_confidence",
    "Current debate consensus confidence score (0.0-1.0)",
    ["symbol"]
)

debate_conflicts_total = Counter(
    "debate_conflicts_total",
    "Total number of debate conflicts (bull vs bear disagreement)",
    ["symbol", "conflict_severity"]
)

# =============================================================================
# Risk Debate Team Metrics (3-Way Position Sizing Validation)
# =============================================================================

risk_debate_decisions_total = Counter(
    "risk_debate_decisions_total",
    "Total number of risk debate decisions",
    ["symbol", "consensus_reached"]
)

risk_debate_latency_seconds = Histogram(
    "risk_debate_latency_seconds",
    "Risk debate decision latency in seconds",
    ["symbol"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

risk_debate_consensus_adjustment = Histogram(
    "risk_debate_consensus_adjustment",
    "Risk debate consensus adjustment factor (0.0-2.0, 1.0 = no change)",
    ["symbol"],
    buckets=[0.0, 0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5, 2.0]
)

risk_debate_position_size_change = Histogram(
    "risk_debate_position_size_change_percent",
    "Percentage change in position size after risk debate",
    ["symbol", "direction"],  # direction: increase, decrease, unchanged
    buckets=[-50, -30, -20, -10, -5, 0, 5, 10, 20, 30, 50]
)

risk_debate_warnings_total = Counter(
    "risk_debate_warnings_total",
    "Total number of risk warnings raised during debate",
    ["symbol", "warning_type"]
)

# =============================================================================
# Fund Manager Approval Metrics (Final Safety Gate)
# =============================================================================

fund_manager_decisions_total = Counter(
    "fund_manager_decisions_total",
    "Total number of fund manager decisions",
    ["symbol", "decision"]  # decision: APPROVE, MODIFY, REJECT
)

fund_manager_latency_seconds = Histogram(
    "fund_manager_latency_seconds",
    "Fund manager decision latency in seconds",
    ["symbol"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

fund_manager_trade_quality = Histogram(
    "fund_manager_trade_quality_score",
    "Fund manager assessed trade quality score (0.0-1.0)",
    ["symbol", "decision"],
    buckets=[0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

fund_manager_confidence = Histogram(
    "fund_manager_confidence_score",
    "Fund manager decision confidence (0.0-1.0)",
    ["symbol", "decision"],
    buckets=[0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

fund_manager_hard_limits_violations = Counter(
    "fund_manager_hard_limits_violations_total",
    "Total number of hard limit violations",
    ["symbol", "limit_type"]  # limit_type: max_account_risk, max_portfolio_risk, etc.
)

fund_manager_portfolio_risk_after = Gauge(
    "fund_manager_portfolio_risk_percent",
    "Portfolio risk percentage after trade approval",
    ["symbol"]
)

fund_manager_modifications_total = Counter(
    "fund_manager_modifications_total",
    "Total number of trade modifications",
    ["symbol", "modification_type"]  # modification_type: size_reduction, stop_tightening, etc.
)

# =============================================================================
# Pipeline Performance Metrics
# =============================================================================

pipeline_executions_total = Counter(
    "phase6_pipeline_executions_total",
    "Total number of Phase 6 pipeline executions",
    ["symbol", "final_decision"]  # final_decision: EXECUTE, MODIFY, REJECT
)

pipeline_latency_seconds = Histogram(
    "phase6_pipeline_latency_seconds",
    "End-to-end Phase 6 pipeline latency in seconds",
    ["symbol"],
    buckets=[1.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0]
)

pipeline_stage_latency_seconds = Histogram(
    "phase6_pipeline_stage_latency_seconds",
    "Individual pipeline stage latency in seconds",
    ["symbol", "stage"],  # stage: analysis, debate, decision, sizing, stop, tp, risk_debate, approval
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

pipeline_errors_total = Counter(
    "phase6_pipeline_errors_total",
    "Total number of pipeline errors",
    ["symbol", "stage", "error_type"]
)

# =============================================================================
# LLM Performance Metrics
# =============================================================================

llm_calls_total = Counter(
    "phase6_llm_calls_total",
    "Total number of LLM calls in Phase 6",
    ["symbol", "agent_type", "model"]
)

llm_latency_seconds = Histogram(
    "phase6_llm_latency_seconds",
    "LLM inference latency in seconds",
    ["agent_type", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
)

llm_tokens_total = Counter(
    "phase6_llm_tokens_total",
    "Total tokens consumed by LLM calls",
    ["agent_type", "model", "token_type"]  # token_type: input, output
)

llm_retries_total = Counter(
    "phase6_llm_retries_total",
    "Total number of LLM retry attempts",
    ["agent_type", "model", "reason"]  # reason: schema_validation, timeout, error
)

# =============================================================================
# Decision Quality Metrics
# =============================================================================

decision_consensus_score = Histogram(
    "phase6_decision_consensus_score",
    "Decision consensus score across all layers (0.0-1.0)",
    ["symbol"],
    buckets=[0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

decision_risk_reward_ratio = Histogram(
    "phase6_decision_risk_reward_ratio",
    "Risk-reward ratio of approved trades",
    ["symbol"],
    buckets=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
)

decision_position_size_lots = Histogram(
    "phase6_decision_position_size_lots",
    "Final approved position size in lots",
    ["symbol"],
    buckets=[0.1, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
)

decision_risk_percentage = Histogram(
    "phase6_decision_risk_percentage",
    "Final approved risk percentage per trade",
    ["symbol"],
    buckets=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
)

# =============================================================================
# Helper Functions for Recording Metrics
# =============================================================================


def record_debate_decision(
    symbol: str,
    direction: str,
    consensus_reached: bool,
    confidence: float,
    latency_seconds: float,
    has_conflicts: bool = False,
    conflict_severity: str = "low"
):
    """
    Record metrics for a debate decision.

    Args:
        symbol: Trading symbol
        direction: Trade direction (LONG, SHORT, NEUTRAL)
        consensus_reached: Whether consensus was reached
        confidence: Consensus confidence score (0.0-1.0)
        latency_seconds: Decision latency in seconds
        has_conflicts: Whether conflicts occurred
        conflict_severity: Conflict severity (low, medium, high)
    """
    debate_decisions_total.labels(
        symbol=symbol,
        direction=direction,
        consensus_reached=str(consensus_reached)
    ).inc()

    debate_latency_seconds.labels(symbol=symbol).observe(latency_seconds)
    debate_consensus_confidence.labels(symbol=symbol).set(confidence)

    if has_conflicts:
        debate_conflicts_total.labels(
            symbol=symbol,
            conflict_severity=conflict_severity
        ).inc()

    logger.info(
        "debate_metrics_recorded",
        symbol=symbol,
        direction=direction,
        consensus_reached=consensus_reached,
        latency_seconds=latency_seconds
    )


def record_risk_debate_decision(
    symbol: str,
    consensus_reached: bool,
    consensus_adjustment: float,
    baseline_size: float,
    final_size: float,
    latency_seconds: float,
    warnings: list = None
):
    """
    Record metrics for a risk debate decision.

    Args:
        symbol: Trading symbol
        consensus_reached: Whether consensus was reached
        consensus_adjustment: Consensus adjustment factor (0.0-2.0)
        baseline_size: Baseline position size before debate
        final_size: Final position size after debate
        latency_seconds: Decision latency in seconds
        warnings: List of risk warnings raised
    """
    risk_debate_decisions_total.labels(
        symbol=symbol,
        consensus_reached=str(consensus_reached)
    ).inc()

    risk_debate_latency_seconds.labels(symbol=symbol).observe(latency_seconds)
    risk_debate_consensus_adjustment.labels(symbol=symbol).observe(consensus_adjustment)

    # Calculate percentage change
    if baseline_size > 0:
        pct_change = ((final_size - baseline_size) / baseline_size) * 100
        direction = "increase" if pct_change > 0 else ("decrease" if pct_change < 0 else "unchanged")
        risk_debate_position_size_change.labels(symbol=symbol, direction=direction).observe(pct_change)

    # Record warnings
    if warnings:
        for warning in warnings:
            risk_debate_warnings_total.labels(
                symbol=symbol,
                warning_type=warning[:50]  # Truncate long warning types
            ).inc()

    logger.info(
        "risk_debate_metrics_recorded",
        symbol=symbol,
        consensus_adjustment=consensus_adjustment,
        latency_seconds=latency_seconds,
        warnings_count=len(warnings) if warnings else 0
    )


def record_fund_manager_decision(
    symbol: str,
    decision: str,
    trade_quality: float,
    confidence: float,
    latency_seconds: float,
    portfolio_risk_after: float,
    hard_limits_passed: bool,
    violated_limits: list = None,
    modifications: list = None
):
    """
    Record metrics for a fund manager approval decision.

    Args:
        symbol: Trading symbol
        decision: APPROVE, MODIFY, or REJECT
        trade_quality: Trade quality score (0.0-1.0)
        confidence: Decision confidence (0.0-1.0)
        latency_seconds: Decision latency in seconds
        portfolio_risk_after: Portfolio risk percentage after trade
        hard_limits_passed: Whether all hard limits passed
        violated_limits: List of violated limit types
        modifications: List of modification types
    """
    fund_manager_decisions_total.labels(symbol=symbol, decision=decision).inc()
    fund_manager_latency_seconds.labels(symbol=symbol).observe(latency_seconds)
    fund_manager_trade_quality.labels(symbol=symbol, decision=decision).observe(trade_quality)
    fund_manager_confidence.labels(symbol=symbol, decision=decision).observe(confidence)
    fund_manager_portfolio_risk_after.labels(symbol=symbol).set(portfolio_risk_after)

    # Record hard limit violations
    if not hard_limits_passed and violated_limits:
        for limit in violated_limits:
            fund_manager_hard_limits_violations.labels(
                symbol=symbol,
                limit_type=limit[:50]
            ).inc()

    # Record modifications
    if modifications:
        for mod in modifications:
            fund_manager_modifications_total.labels(
                symbol=symbol,
                modification_type=mod.get("type", "unknown")[:50] if isinstance(mod, dict) else str(mod)[:50]
            ).inc()

    logger.info(
        "fund_manager_metrics_recorded",
        symbol=symbol,
        decision=decision,
        trade_quality=trade_quality,
        latency_seconds=latency_seconds
    )


def record_pipeline_execution(
    symbol: str,
    final_decision: str,
    total_latency_seconds: float,
    stage_latencies: dict = None
):
    """
    Record metrics for complete pipeline execution.

    Args:
        symbol: Trading symbol
        final_decision: EXECUTE, MODIFY, or REJECT
        total_latency_seconds: Total pipeline latency in seconds
        stage_latencies: Dictionary of stage name -> latency in seconds
    """
    pipeline_executions_total.labels(symbol=symbol, final_decision=final_decision).inc()
    pipeline_latency_seconds.labels(symbol=symbol).observe(total_latency_seconds)

    # Record individual stage latencies
    if stage_latencies:
        for stage, latency in stage_latencies.items():
            pipeline_stage_latency_seconds.labels(symbol=symbol, stage=stage).observe(latency)

    logger.info(
        "pipeline_metrics_recorded",
        symbol=symbol,
        final_decision=final_decision,
        total_latency_seconds=total_latency_seconds
    )


def record_llm_call(
    symbol: str,
    agent_type: str,
    model: str,
    latency_seconds: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    retry_count: int = 0,
    retry_reason: str = None
):
    """
    Record metrics for LLM API calls.

    Args:
        symbol: Trading symbol
        agent_type: Type of agent making the call
        model: LLM model name
        latency_seconds: LLM call latency in seconds
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        retry_count: Number of retries attempted
        retry_reason: Reason for retry (if any)
    """
    llm_calls_total.labels(symbol=symbol, agent_type=agent_type, model=model).inc()
    llm_latency_seconds.labels(agent_type=agent_type, model=model).observe(latency_seconds)

    if input_tokens > 0:
        llm_tokens_total.labels(agent_type=agent_type, model=model, token_type="input").inc(input_tokens)

    if output_tokens > 0:
        llm_tokens_total.labels(agent_type=agent_type, model=model, token_type="output").inc(output_tokens)

    if retry_count > 0 and retry_reason:
        llm_retries_total.labels(
            agent_type=agent_type,
            model=model,
            reason=retry_reason
        ).inc(retry_count)

    logger.debug(
        "llm_metrics_recorded",
        symbol=symbol,
        agent_type=agent_type,
        model=model,
        latency_seconds=latency_seconds,
        total_tokens=input_tokens + output_tokens
    )
