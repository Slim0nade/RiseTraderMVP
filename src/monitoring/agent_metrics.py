"""
Prometheus Metrics for Agent System.

Tracks:
- Agent decision counts and latency
- MCP tool call performance
- Event bus throughput
- Team orchestration metrics
- LLM costs and token usage
"""

from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

logger = structlog.get_logger(__name__)

# ============================================================================
# Agent Decision Metrics
# ============================================================================

agent_decision_total = Counter(
    "agent_decision_total",
    "Total number of agent decisions",
    ["agent_type", "symbol", "decision_type"],
)

agent_decision_duration_seconds = Histogram(
    "agent_decision_duration_seconds",
    "Agent decision latency in seconds",
    ["agent_type", "symbol"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

agent_decision_success_total = Counter(
    "agent_decision_success_total",
    "Successful agent decisions",
    ["agent_type", "symbol"],
)

agent_decision_error_total = Counter(
    "agent_decision_error_total",
    "Failed agent decisions",
    ["agent_type", "symbol", "error_type"],
)

agent_active_count = Gauge(
    "agent_active_count",
    "Number of active agents",
    ["agent_type", "symbol"],
)

agent_state_gauge = Gauge(
    "agent_state",
    "Agent state (0=idle, 1=processing, 2=error, 3=paused, 4=stopped)",
    ["agent_id", "agent_type", "agent_name"],
)

# ============================================================================
# MCP Tool Metrics
# ============================================================================

mcp_tool_call_total = Counter(
    "mcp_tool_call_total",
    "Total MCP tool calls",
    ["tool_name", "symbol"],
)

mcp_tool_call_duration_seconds = Histogram(
    "mcp_tool_call_duration_seconds",
    "MCP tool call latency in seconds",
    ["tool_name", "symbol"],
    buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
)

mcp_tool_success_total = Counter(
    "mcp_tool_success_total",
    "Successful MCP tool calls",
    ["tool_name", "symbol"],
)

mcp_tool_error_total = Counter(
    "mcp_tool_error_total",
    "Failed MCP tool calls",
    ["tool_name", "symbol", "error_type"],
)

mcp_tool_cache_hit_total = Counter(
    "mcp_tool_cache_hit_total",
    "MCP tool cache hits",
    ["tool_name"],
)

mcp_tool_cache_miss_total = Counter(
    "mcp_tool_cache_miss_total",
    "MCP tool cache misses",
    ["tool_name"],
)

# ============================================================================
# Event Bus Metrics
# ============================================================================

agent_event_published_total = Counter(
    "agent_event_published_total",
    "Events published to event bus",
    ["event_type", "source_agent", "symbol"],
)

agent_event_consumed_total = Counter(
    "agent_event_consumed_total",
    "Events consumed by agents",
    ["event_type", "consumer_agent", "symbol"],
)

agent_event_processing_duration_seconds = Histogram(
    "agent_event_processing_duration_seconds",
    "Event processing latency",
    ["event_type", "consumer_agent"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

agent_event_queue_size = Gauge(
    "agent_event_queue_size",
    "Current event queue size",
    ["queue_name"],
)

# ============================================================================
# Team Orchestration Metrics
# ============================================================================

team_run_total = Counter(
    "team_run_total",
    "Total team runs",
    ["team_type", "symbol"],
)

team_run_duration_seconds = Histogram(
    "team_run_duration_seconds",
    "Team run duration",
    ["team_type", "symbol"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

team_message_count = Histogram(
    "team_message_count",
    "Messages exchanged in team run",
    ["team_type", "symbol"],
    buckets=(1, 3, 5, 10, 20, 50),
)

team_success_total = Counter(
    "team_success_total",
    "Successful team runs",
    ["team_type", "symbol"],
)

team_error_total = Counter(
    "team_error_total",
    "Failed team runs",
    ["team_type", "symbol", "error_type"],
)

# ============================================================================
# LLM Usage Metrics
# ============================================================================

llm_request_total = Counter(
    "llm_request_total",
    "Total LLM API requests",
    ["model_provider", "model_name", "tier"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request latency",
    ["model_provider", "model_name"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0),
)

llm_tokens_used_total = Counter(
    "llm_tokens_used_total",
    "Total tokens used",
    ["model_provider", "model_name", "token_type"],
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Total LLM costs in USD",
    ["model_provider", "model_name"],
)

llm_error_total = Counter(
    "llm_error_total",
    "LLM request errors",
    ["model_provider", "model_name", "error_type"],
)

# ============================================================================
# Performance Metrics
# ============================================================================

agent_cpu_usage_percent = Gauge(
    "agent_cpu_usage_percent",
    "Agent CPU usage percentage",
    ["agent_id", "agent_type"],
)

agent_memory_usage_mb = Gauge(
    "agent_memory_usage_mb",
    "Agent memory usage in MB",
    ["agent_id", "agent_type"],
)

# ============================================================================
# Helper Functions
# ============================================================================


def record_agent_decision(
    agent_type: str,
    symbol: str,
    decision_type: str,
    duration_seconds: float,
    success: bool = True,
    error_type: str = None,
):
    """
    Record agent decision metrics.

    Args:
        agent_type: Type of agent
        symbol: Trading symbol
        decision_type: Type of decision
        duration_seconds: Decision latency
        success: Whether decision succeeded
        error_type: Error type if failed
    """
    agent_decision_total.labels(
        agent_type=agent_type,
        symbol=symbol,
        decision_type=decision_type,
    ).inc()

    agent_decision_duration_seconds.labels(
        agent_type=agent_type,
        symbol=symbol,
    ).observe(duration_seconds)

    if success:
        agent_decision_success_total.labels(
            agent_type=agent_type,
            symbol=symbol,
        ).inc()
    else:
        agent_decision_error_total.labels(
            agent_type=agent_type,
            symbol=symbol,
            error_type=error_type or "unknown",
        ).inc()


def record_mcp_tool_call(
    tool_name: str,
    symbol: str,
    duration_seconds: float,
    success: bool = True,
    error_type: str = None,
    cache_hit: bool = False,
):
    """
    Record MCP tool call metrics.

    Args:
        tool_name: Name of MCP tool
        symbol: Trading symbol
        duration_seconds: Tool call latency
        success: Whether call succeeded
        error_type: Error type if failed
        cache_hit: Whether result came from cache
    """
    mcp_tool_call_total.labels(
        tool_name=tool_name,
        symbol=symbol,
    ).inc()

    mcp_tool_call_duration_seconds.labels(
        tool_name=tool_name,
        symbol=symbol,
    ).observe(duration_seconds)

    if success:
        mcp_tool_success_total.labels(
            tool_name=tool_name,
            symbol=symbol,
        ).inc()
    else:
        mcp_tool_error_total.labels(
            tool_name=tool_name,
            symbol=symbol,
            error_type=error_type or "unknown",
        ).inc()

    if cache_hit:
        mcp_tool_cache_hit_total.labels(tool_name=tool_name).inc()
    else:
        mcp_tool_cache_miss_total.labels(tool_name=tool_name).inc()


def record_team_run(
    team_type: str,
    symbol: str,
    duration_seconds: float,
    message_count: int,
    success: bool = True,
    error_type: str = None,
):
    """
    Record team orchestration metrics.

    Args:
        team_type: Type of team (analysis, debate, pipeline)
        symbol: Trading symbol
        duration_seconds: Team run duration
        message_count: Messages exchanged
        success: Whether run succeeded
        error_type: Error type if failed
    """
    team_run_total.labels(
        team_type=team_type,
        symbol=symbol,
    ).inc()

    team_run_duration_seconds.labels(
        team_type=team_type,
        symbol=symbol,
    ).observe(duration_seconds)

    team_message_count.labels(
        team_type=team_type,
        symbol=symbol,
    ).observe(message_count)

    if success:
        team_success_total.labels(
            team_type=team_type,
            symbol=symbol,
        ).inc()
    else:
        team_error_total.labels(
            team_type=team_type,
            symbol=symbol,
            error_type=error_type or "unknown",
        ).inc()


def record_llm_request(
    model_provider: str,
    model_name: str,
    tier: str,
    duration_seconds: float,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float = 0.0,
    success: bool = True,
    error_type: str = None,
):
    """
    Record LLM request metrics.

    Args:
        model_provider: Provider (ollama, openai, anthropic, google)
        model_name: Model name
        tier: LLM tier (quick_think, deep_think, structured)
        duration_seconds: Request latency
        prompt_tokens: Prompt tokens used
        completion_tokens: Completion tokens generated
        cost_usd: Request cost in USD
        success: Whether request succeeded
        error_type: Error type if failed
    """
    llm_request_total.labels(
        model_provider=model_provider,
        model_name=model_name,
        tier=tier,
    ).inc()

    llm_request_duration_seconds.labels(
        model_provider=model_provider,
        model_name=model_name,
    ).observe(duration_seconds)

    llm_tokens_used_total.labels(
        model_provider=model_provider,
        model_name=model_name,
        token_type="prompt",
    ).inc(prompt_tokens)

    llm_tokens_used_total.labels(
        model_provider=model_provider,
        model_name=model_name,
        token_type="completion",
    ).inc(completion_tokens)

    if cost_usd > 0:
        llm_cost_usd_total.labels(
            model_provider=model_provider,
            model_name=model_name,
        ).inc(cost_usd)

    if not success:
        llm_error_total.labels(
            model_provider=model_provider,
            model_name=model_name,
            error_type=error_type or "unknown",
        ).inc()


logger.info("agent_metrics_initialized")
