"""
Prometheus metrics collectors for MT4 integration.

Tracks performance metrics, error rates, and connection health.
"""
from prometheus_client import Counter, Gauge, Histogram, Info


# =============================================================================
# Connection Metrics
# =============================================================================

mt4_connection_status = Gauge(
    'mt4_connection_status',
    'MT4 EA connection status (1=ACTIVE, 0=INACTIVE/ERROR)',
    ['ea_id', 'magic_number', 'symbol']
)

mt4_connection_errors_total = Counter(
    'mt4_connection_errors_total',
    'Total number of MT4 connection errors',
    ['ea_id', 'error_type']
)

mt4_heartbeat_latency_seconds = Histogram(
    'mt4_heartbeat_latency_seconds',
    'MT4 heartbeat latency in seconds',
    ['ea_id'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

mt4_connection_info = Info(
    'mt4_connection_info',
    'MT4 connection information',
    ['ea_id', 'magic_number', 'symbol', 'host', 'encryption_enabled']
)


# =============================================================================
# Order Metrics
# =============================================================================

mt4_orders_total = Counter(
    'mt4_orders_total',
    'Total number of orders submitted',
    ['ea_id', 'symbol', 'direction', 'order_type']
)

mt4_orders_confirmed_total = Counter(
    'mt4_orders_confirmed_total',
    'Total number of orders confirmed by MT4',
    ['ea_id', 'symbol', 'direction']
)

mt4_orders_executed_total = Counter(
    'mt4_orders_executed_total',
    'Total number of orders executed (filled)',
    ['ea_id', 'symbol', 'direction']
)

mt4_orders_rejected_total = Counter(
    'mt4_orders_rejected_total',
    'Total number of orders rejected',
    ['ea_id', 'symbol', 'error_code']
)

mt4_order_latency_seconds = Histogram(
    'mt4_order_latency_seconds',
    'Order confirmation latency from submission to confirmation',
    ['ea_id', 'symbol'],
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)
)

mt4_order_execution_latency_seconds = Histogram(
    'mt4_order_execution_latency_seconds',
    'Order execution latency from submission to fill',
    ['ea_id', 'symbol'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

mt4_active_orders = Gauge(
    'mt4_active_orders',
    'Number of active orders (PENDING or CONFIRMED)',
    ['ea_id', 'symbol']
)


# =============================================================================
# Position Metrics
# =============================================================================

mt4_open_positions = Gauge(
    'mt4_open_positions',
    'Number of open positions',
    ['ea_id', 'symbol', 'direction']
)

mt4_position_pnl = Gauge(
    'mt4_position_pnl',
    'Unrealized P&L for open positions',
    ['ea_id', 'ticket_number', 'symbol']
)

mt4_positions_closed_total = Counter(
    'mt4_positions_closed_total',
    'Total number of closed positions',
    ['ea_id', 'symbol', 'close_reason']
)

mt4_position_holding_time_seconds = Histogram(
    'mt4_position_holding_time_seconds',
    'Position holding time from open to close',
    ['ea_id', 'symbol'],
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400, 28800, 86400)  # 1min to 1day
)


# =============================================================================
# Market Data Metrics
# =============================================================================

mt4_market_ticks_total = Counter(
    'mt4_market_ticks_total',
    'Total number of market ticks received',
    ['symbol']
)

mt4_market_tick_latency_seconds = Histogram(
    'mt4_market_tick_latency_seconds',
    'Market data latency (from MT4 timestamp to receipt)',
    ['symbol'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)


# =============================================================================
# Portfolio Risk Metrics
# =============================================================================

mt4_portfolio_equity = Gauge(
    'mt4_portfolio_equity',
    'Total portfolio equity across all EAs',
)

mt4_portfolio_margin_used = Gauge(
    'mt4_portfolio_margin_used',
    'Total margin used across all EAs',
)

mt4_portfolio_margin_level = Gauge(
    'mt4_portfolio_margin_level',
    'Portfolio margin level percentage',
)

mt4_portfolio_exposure = Gauge(
    'mt4_portfolio_exposure',
    'Portfolio exposure by symbol',
    ['symbol']
)

mt4_ea_margin_usage = Gauge(
    'mt4_ea_margin_usage',
    'Margin usage per EA',
    ['ea_id', 'magic_number']
)


# =============================================================================
# Performance Metrics
# =============================================================================

mt4_zmq_command_duration_seconds = Histogram(
    'mt4_zmq_command_duration_seconds',
    'ZMQ command execution duration',
    ['command_type'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

mt4_zmq_command_errors_total = Counter(
    'mt4_zmq_command_errors_total',
    'Total ZMQ command errors',
    ['command_type', 'error_type']
)

mt4_circuit_breaker_state = Gauge(
    'mt4_circuit_breaker_state',
    'Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)',
    ['ea_id']
)

mt4_circuit_breaker_failures_total = Counter(
    'mt4_circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['ea_id']
)


# =============================================================================
# System Health Metrics
# =============================================================================

mt4_service_up = Gauge(
    'mt4_service_up',
    'MT4 integration service health (1=UP, 0=DOWN)'
)

mt4_database_connections = Gauge(
    'mt4_database_connections',
    'Active database connections'
)

mt4_redis_connections = Gauge(
    'mt4_redis_connections',
    'Active Redis connections'
)


# =============================================================================
# Metric Helper Functions
# =============================================================================

def record_order_submitted(ea_id: str, symbol: str, direction: str, order_type: str):
    """Record order submission."""
    mt4_orders_total.labels(
        ea_id=ea_id,
        symbol=symbol,
        direction=direction,
        order_type=order_type
    ).inc()


def record_order_confirmed(ea_id: str, symbol: str, direction: str, latency_seconds: float):
    """Record order confirmation."""
    mt4_orders_confirmed_total.labels(
        ea_id=ea_id,
        symbol=symbol,
        direction=direction
    ).inc()

    mt4_order_latency_seconds.labels(
        ea_id=ea_id,
        symbol=symbol
    ).observe(latency_seconds)


def record_order_executed(ea_id: str, symbol: str, direction: str, execution_latency_seconds: float):
    """Record order execution."""
    mt4_orders_executed_total.labels(
        ea_id=ea_id,
        symbol=symbol,
        direction=direction
    ).inc()

    mt4_order_execution_latency_seconds.labels(
        ea_id=ea_id,
        symbol=symbol
    ).observe(execution_latency_seconds)


def record_order_rejected(ea_id: str, symbol: str, error_code: str):
    """Record order rejection."""
    mt4_orders_rejected_total.labels(
        ea_id=ea_id,
        symbol=symbol,
        error_code=error_code
    ).inc()


def update_connection_status(ea_id: str, magic_number: int, symbol: str, is_active: bool):
    """Update connection status."""
    mt4_connection_status.labels(
        ea_id=ea_id,
        magic_number=str(magic_number),
        symbol=symbol
    ).set(1 if is_active else 0)


def record_connection_error(ea_id: str, error_type: str):
    """Record connection error."""
    mt4_connection_errors_total.labels(
        ea_id=ea_id,
        error_type=error_type
    ).inc()


def update_open_positions_count(ea_id: str, symbol: str, direction: str, count: int):
    """Update open positions gauge."""
    mt4_open_positions.labels(
        ea_id=ea_id,
        symbol=symbol,
        direction=direction
    ).set(count)


def update_position_pnl(ea_id: str, ticket_number: int, symbol: str, pnl: float):
    """Update position P&L."""
    mt4_position_pnl.labels(
        ea_id=ea_id,
        ticket_number=str(ticket_number),
        symbol=symbol
    ).set(pnl)


def record_position_closed(ea_id: str, symbol: str, close_reason: str, holding_time_seconds: float):
    """Record position closure."""
    mt4_positions_closed_total.labels(
        ea_id=ea_id,
        symbol=symbol,
        close_reason=close_reason
    ).inc()

    mt4_position_holding_time_seconds.labels(
        ea_id=ea_id,
        symbol=symbol
    ).observe(holding_time_seconds)


def record_market_tick(symbol: str, latency_seconds: float):
    """Record market tick reception."""
    mt4_market_ticks_total.labels(symbol=symbol).inc()
    mt4_market_tick_latency_seconds.labels(symbol=symbol).observe(latency_seconds)


# =============================================================================
# Account Query Metrics (T088 - User Story 4)
# =============================================================================

mt4_account_query_latency_seconds = Histogram(
    'mt4_account_query_latency_seconds',
    'Account info query latency in seconds',
    ['ea_id'],
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)
)

mt4_positions_query_latency_seconds = Histogram(
    'mt4_positions_query_latency_seconds',
    'Open positions query latency in seconds',
    ['ea_id'],
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)
)

mt4_account_queries_total = Counter(
    'mt4_account_queries_total',
    'Total number of account info queries',
    ['ea_id', 'status']  # status: success, error, timeout
)

mt4_positions_queries_total = Counter(
    'mt4_positions_queries_total',
    'Total number of positions queries',
    ['ea_id', 'status']
)


def record_account_query(ea_id: str, latency_seconds: float, status: str = "success"):
    """Record account info query metrics."""
    mt4_account_queries_total.labels(ea_id=ea_id, status=status).inc()
    if status == "success":
        mt4_account_query_latency_seconds.labels(ea_id=ea_id).observe(latency_seconds)


def record_positions_query(ea_id: str, latency_seconds: float, status: str = "success"):
    """Record positions query metrics."""
    mt4_positions_queries_total.labels(ea_id=ea_id, status=status).inc()
    if status == "success":
        mt4_positions_query_latency_seconds.labels(ea_id=ea_id).observe(latency_seconds)


# =============================================================================
# Portfolio Metrics Functions (T074 - User Story 5)
# =============================================================================

def update_portfolio_metrics(
    total_equity: float,
    total_margin_used: float,
    margin_level: float,
    exposure_by_symbol: dict = None,
    exposure_by_ea: dict = None
):
    """
    Update portfolio-level metrics (T074).

    Args:
        total_equity: Total portfolio equity
        total_margin_used: Total margin used
        margin_level: Margin level percentage
        exposure_by_symbol: Optional dict of symbol -> exposure
        exposure_by_ea: Optional dict of ea_id -> margin usage
    """
    # Update portfolio gauges
    mt4_portfolio_equity.set(total_equity)
    mt4_portfolio_margin_used.set(total_margin_used)
    mt4_portfolio_margin_level.set(margin_level)

    # Update symbol exposure if provided
    if exposure_by_symbol:
        for symbol, exposure in exposure_by_symbol.items():
            mt4_portfolio_exposure.labels(symbol=symbol).set(float(exposure))

    # Update EA margin usage if provided
    if exposure_by_ea:
        for ea_id, margin in exposure_by_ea.items():
            magic_number = ea_id  # ea_id can be magic_number string
            mt4_ea_margin_usage.labels(
                ea_id=f"ea_{ea_id}",
                magic_number=str(magic_number)
            ).set(float(margin))


def record_zmq_command(command_type: str, duration_seconds: float):
    """Record ZMQ command execution."""
    mt4_zmq_command_duration_seconds.labels(
        command_type=command_type
    ).observe(duration_seconds)


def record_zmq_error(command_type: str, error_type: str):
    """Record ZMQ command error."""
    mt4_zmq_command_errors_total.labels(
        command_type=command_type,
        error_type=error_type
    ).inc()


def update_circuit_breaker_state(ea_id: str, state: str):
    """Update circuit breaker state (CLOSED=0, OPEN=1, HALF_OPEN=2) - T096."""
    state_map = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}
    mt4_circuit_breaker_state.labels(ea_id=ea_id).set(state_map.get(state, 0))


def record_circuit_breaker_failure(ea_id: str):
    """Record circuit breaker failure (T096)."""
    mt4_circuit_breaker_failures_total.labels(ea_id=ea_id).inc()


def set_service_health(is_healthy: bool):
    """Set overall service health status."""
    mt4_service_up.set(1 if is_healthy else 0)
