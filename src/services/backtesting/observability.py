"""
Observability instrumentation for backtesting service.

T122: Add Prometheus metrics for backtest duration, candles/sec, memory usage
T123: Add structured logging for all error conditions

Provides:
- Prometheus metrics collection
- Structured logging helpers
- Performance monitoring
- Error tracking
"""
import time
import psutil
import os
from typing import Optional, Dict, Any
from contextlib import contextmanager

try:
    from prometheus_client import Counter, Histogram, Gauge, Info
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # No-op classes when prometheus_client not available
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self

    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def time(self): return _NoOpContext()

    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def dec(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self

    class Info:
        def __init__(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass

    class _NoOpContext:
        def __enter__(self): return self
        def __exit__(self, *args): pass


# ============================================================================
# T122: Prometheus Metrics
# ============================================================================

# Backtest execution metrics
backtest_runs_total = Counter(
    'backtest_runs_total',
    'Total number of backtest runs',
    ['mode', 'symbol', 'status']
)

backtest_duration_seconds = Histogram(
    'backtest_duration_seconds',
    'Backtest execution duration in seconds',
    ['mode', 'symbol'],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)
)

backtest_candles_processed = Histogram(
    'backtest_candles_processed',
    'Number of candles processed per backtest',
    ['mode', 'symbol'],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000, 500000)
)

backtest_candles_per_second = Gauge(
    'backtest_candles_per_second',
    'Processing speed in candles per second',
    ['mode', 'symbol']
)

backtest_trades_generated = Histogram(
    'backtest_trades_generated',
    'Number of trades generated per backtest',
    ['mode', 'symbol'],
    buckets=(0, 10, 50, 100, 500, 1000, 5000)
)

backtest_memory_bytes = Gauge(
    'backtest_memory_bytes',
    'Memory usage during backtest',
    ['mode', 'symbol']
)

backtest_errors_total = Counter(
    'backtest_errors_total',
    'Total number of backtest errors',
    ['mode', 'symbol', 'error_type']
)

# Performance metrics
backtest_sharpe_ratio = Histogram(
    'backtest_sharpe_ratio',
    'Sharpe ratio from backtests',
    ['mode', 'symbol'],
    buckets=(-2, -1, 0, 0.5, 1, 1.5, 2, 2.5, 3, 5)
)

backtest_total_return = Histogram(
    'backtest_total_return',
    'Total return percentage from backtests',
    ['mode', 'symbol'],
    buckets=(-0.5, -0.2, 0, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0)
)

backtest_max_drawdown = Histogram(
    'backtest_max_drawdown',
    'Maximum drawdown from backtests',
    ['mode', 'symbol'],
    buckets=(0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0)
)

# Optimization metrics
optimization_runs_total = Counter(
    'optimization_runs_total',
    'Total number of optimization runs',
    ['strategy']
)

optimization_combinations_tested = Histogram(
    'optimization_combinations_tested',
    'Number of parameter combinations tested',
    ['strategy'],
    buckets=(10, 50, 100, 500, 1000, 5000, 10000)
)

optimization_duration_seconds = Histogram(
    'optimization_duration_seconds',
    'Optimization execution duration',
    ['strategy'],
    buckets=(10, 30, 60, 300, 600, 1800, 3600, 7200)
)

# RL environment metrics
rl_episodes_total = Counter(
    'rl_episodes_total',
    'Total number of RL training episodes',
    ['symbol', 'reward_type']
)

rl_episode_reward = Histogram(
    'rl_episode_reward',
    'Reward per RL episode',
    ['symbol', 'reward_type'],
    buckets=(-1000, -500, -100, 0, 100, 500, 1000, 5000)
)

rl_episode_length = Histogram(
    'rl_episode_length',
    'Episode length in steps',
    ['symbol'],
    buckets=(10, 50, 100, 500, 1000, 5000)
)

# System info
backtest_info = Info(
    'backtest_info',
    'Backtesting system information'
)

# Initialize system info
if PROMETHEUS_AVAILABLE:
    backtest_info.info({
        'version': '1.0.0',
        'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
        'prometheus_available': 'true',
    })


# ============================================================================
# T123: Structured Logging Helpers
# ============================================================================

def log_backtest_start(
    mode: str,
    symbol: str,
    start_date: str,
    end_date: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Create structured log entry for backtest start.

    Returns:
        Dict with structured log fields
    """
    return {
        "event": "backtest_started",
        "mode": mode,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        **kwargs
    }


def log_backtest_complete(
    mode: str,
    symbol: str,
    duration_seconds: float,
    candles_processed: int,
    trades_generated: int,
    sharpe_ratio: float,
    total_return: float,
    **kwargs
) -> Dict[str, Any]:
    """
    Create structured log entry for backtest completion.

    Returns:
        Dict with structured log fields
    """
    candles_per_sec = candles_processed / duration_seconds if duration_seconds > 0 else 0

    return {
        "event": "backtest_completed",
        "mode": mode,
        "symbol": symbol,
        "duration_seconds": duration_seconds,
        "candles_processed": candles_processed,
        "candles_per_second": candles_per_sec,
        "trades_generated": trades_generated,
        "sharpe_ratio": sharpe_ratio,
        "total_return": total_return,
        **kwargs
    }


def log_backtest_error(
    mode: str,
    symbol: str,
    error_type: str,
    error_message: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Create structured log entry for backtest error.

    Returns:
        Dict with structured log fields
    """
    return {
        "event": "backtest_error",
        "mode": mode,
        "symbol": symbol,
        "error_type": error_type,
        "error_message": error_message,
        **kwargs
    }


# ============================================================================
# Context Managers for Metrics Collection
# ============================================================================

@contextmanager
def track_backtest_metrics(mode: str, symbol: str):
    """
    Context manager to track backtest execution metrics.

    Usage:
        with track_backtest_metrics("synthetic", "EURUSD"):
            result = await backtest_service.run_backtest(config)
            # Metrics automatically recorded
    """
    start_time = time.perf_counter()
    process = psutil.Process()
    start_memory = process.memory_info().rss

    try:
        yield
        # Success
        duration = time.perf_counter() - start_time
        backtest_runs_total.labels(mode=mode, symbol=symbol, status="success").inc()
        backtest_duration_seconds.labels(mode=mode, symbol=symbol).observe(duration)

    except Exception as e:
        # Error
        duration = time.perf_counter() - start_time
        error_type = type(e).__name__
        backtest_runs_total.labels(mode=mode, symbol=symbol, status="error").inc()
        backtest_errors_total.labels(mode=mode, symbol=symbol, error_type=error_type).inc()
        raise

    finally:
        # Memory usage
        final_memory = process.memory_info().rss
        memory_used = final_memory - start_memory
        backtest_memory_bytes.labels(mode=mode, symbol=symbol).set(memory_used)


def record_backtest_result(
    mode: str,
    symbol: str,
    candles_processed: int,
    trades_generated: int,
    sharpe_ratio: float,
    total_return: float,
    max_drawdown: float,
    duration_seconds: float,
):
    """
    Record backtest performance metrics to Prometheus.

    Args:
        mode: Execution mode (synthetic/agent)
        symbol: Trading symbol
        candles_processed: Number of candles processed
        trades_generated: Number of trades generated
        sharpe_ratio: Sharpe ratio result
        total_return: Total return percentage
        max_drawdown: Maximum drawdown percentage
        duration_seconds: Execution duration
    """
    # Processing metrics
    backtest_candles_processed.labels(mode=mode, symbol=symbol).observe(candles_processed)
    backtest_trades_generated.labels(mode=mode, symbol=symbol).observe(trades_generated)

    # Processing speed
    candles_per_sec = candles_processed / duration_seconds if duration_seconds > 0 else 0
    backtest_candles_per_second.labels(mode=mode, symbol=symbol).set(candles_per_sec)

    # Performance metrics
    backtest_sharpe_ratio.labels(mode=mode, symbol=symbol).observe(sharpe_ratio)
    backtest_total_return.labels(mode=mode, symbol=symbol).observe(total_return)
    backtest_max_drawdown.labels(mode=mode, symbol=symbol).observe(abs(max_drawdown))


def record_optimization_metrics(
    strategy: str,
    combinations_tested: int,
    duration_seconds: float,
):
    """
    Record optimization metrics to Prometheus.

    Args:
        strategy: Strategy name
        combinations_tested: Number of parameter combinations
        duration_seconds: Execution duration
    """
    optimization_runs_total.labels(strategy=strategy).inc()
    optimization_combinations_tested.labels(strategy=strategy).observe(combinations_tested)
    optimization_duration_seconds.labels(strategy=strategy).observe(duration_seconds)


def record_rl_episode(
    symbol: str,
    reward_type: str,
    episode_reward: float,
    episode_length: int,
):
    """
    Record RL training episode metrics.

    Args:
        symbol: Trading symbol
        reward_type: Reward shaping type
        episode_reward: Total episode reward
        episode_length: Episode length in steps
    """
    rl_episodes_total.labels(symbol=symbol, reward_type=reward_type).inc()
    rl_episode_reward.labels(symbol=symbol, reward_type=reward_type).observe(episode_reward)
    rl_episode_length.labels(symbol=symbol).observe(episode_length)


def is_prometheus_available() -> bool:
    """Check if Prometheus metrics are available."""
    return PROMETHEUS_AVAILABLE


# ============================================================================
# Metrics Export
# ============================================================================

def get_metrics_summary() -> Dict[str, Any]:
    """
    Get summary of current metrics (for debugging/testing).

    Returns:
        Dict with metrics summary
    """
    if not PROMETHEUS_AVAILABLE:
        return {"prometheus_available": False}

    return {
        "prometheus_available": True,
        "note": "Metrics are exported at /metrics endpoint",
        "available_metrics": [
            "backtest_runs_total",
            "backtest_duration_seconds",
            "backtest_candles_processed",
            "backtest_candles_per_second",
            "backtest_trades_generated",
            "backtest_memory_bytes",
            "backtest_errors_total",
            "backtest_sharpe_ratio",
            "backtest_total_return",
            "backtest_max_drawdown",
            "optimization_runs_total",
            "optimization_combinations_tested",
            "optimization_duration_seconds",
            "rl_episodes_total",
            "rl_episode_reward",
            "rl_episode_length",
        ]
    }


if __name__ == "__main__":
    print("="*60)
    print("BACKTESTING OBSERVABILITY MODULE")
    print("="*60)
    print(f"Prometheus Available: {PROMETHEUS_AVAILABLE}")

    if PROMETHEUS_AVAILABLE:
        print("\n✅ Prometheus metrics active")
        print("\nMetrics Summary:")
        summary = get_metrics_summary()
        print(f"  Total metrics: {len(summary['available_metrics'])}")
        print("\nAvailable metrics:")
        for metric in summary['available_metrics']:
            print(f"  - {metric}")
    else:
        print("\n⚠️  Prometheus not installed")
        print("Install with: pip install prometheus-client")
        print("\nMetrics will be no-ops until installed")
