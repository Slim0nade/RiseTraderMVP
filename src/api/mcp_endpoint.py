"""
Embedded MCP Server for RiseTrader.

Runs inside FastAPI via SSE transport — no separate container needed.
Tools call service layer directly instead of proxying via HTTP.
Shares the API's MT4 client from mt4_sync_service (no redundant ZMQ connection).
"""
import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from src.api.dependencies import get_db_context
from src.services.mt4_sync_service import get_mt4_sync_service

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# MT4 client accessor — reuses the sync service's connection
# ---------------------------------------------------------------------------

async def _get_mt4_client():
    """Get MT4 client from the shared sync service (no duplicate ZMQ connection)."""
    sync = get_mt4_sync_service()
    if sync.mt4_client is None:
        await sync.start()
    return sync.mt4_client


# ---------------------------------------------------------------------------
# Tool definitions (reused for list_tools)
# ---------------------------------------------------------------------------

TOOLS: List[Tool] = [
    # ── Live Trading ──────────────────────────────────────────────
    Tool(
        name="place_market_order",
        description="Place a market order (executes immediately at current price)",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading symbol (e.g., 'CrudeOIL', 'EURUSD')"},
                "side": {"type": "string", "enum": ["buy", "sell"], "description": "Order side"},
                "quantity": {"type": "number", "description": "Position size in lots"},
                "stop_loss": {"type": "number", "description": "Stop loss price (optional)"},
                "take_profit": {"type": "number", "description": "Take profit price (optional)"},
            },
            "required": ["symbol", "side", "quantity"],
        },
    ),
    Tool(
        name="close_position",
        description="Close an open position by position ID",
        inputSchema={
            "type": "object",
            "properties": {"position_id": {"type": "integer", "description": "Position ID to close"}},
            "required": ["position_id"],
        },
    ),
    Tool(
        name="close_all_positions",
        description="Emergency close all open positions",
        inputSchema={
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Only close positions for this symbol (optional)"}},
        },
    ),
    Tool(
        name="get_open_positions",
        description="Get open trading positions with optional filtering",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Filter by symbol (optional)"},
                "live_only": {"type": "boolean", "description": "Only show live positions (default: true)", "default": True},
                "limit": {"type": "integer", "description": "Max positions to return (default: 20)", "default": 20},
            },
        },
    ),
    Tool(
        name="get_account_info",
        description="Get trading account information (balance, equity, margin)",
        inputSchema={"type": "object", "properties": {}},
    ),

    # ── Market Data ───────────────────────────────────────────────
    Tool(
        name="get_latest_candles",
        description="Get recent candle data for technical analysis",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading symbol"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"], "description": "Candle timeframe"},
                "limit": {"type": "integer", "description": "Number of candles (default 100)", "default": 100},
            },
            "required": ["symbol", "timeframe"],
        },
    ),
    Tool(
        name="get_symbols",
        description="Get list of available trading symbols",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_symbol_info",
        description="Get detailed symbol specifications (leverage, margin %, swap rates, trading hours, contract size).",
        inputSchema={
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Trading symbol"}},
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_all_symbols_info",
        description="Get detailed specifications for ALL trading symbols.",
        inputSchema={"type": "object", "properties": {}},
    ),

    # ── Backtesting ───────────────────────────────────────────────
    Tool(
        name="create_backtest",
        description="Create and run a new backtest. Returns IMMEDIATELY with run_id — backtest runs in background. Use get_backtest_results to poll for completion.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Backtest name"},
                "symbol": {"type": "string", "description": "Trading symbol"},
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "strategy": {"type": "string", "description": "Strategy name (e.g., 'crude_oil_v3', 'ma_crossover')"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "initial_capital": {"type": "number", "description": "Starting capital (default 10000)", "default": 10000},
            },
            "required": ["name", "symbol", "start_date", "end_date", "strategy", "timeframe"],
        },
    ),
    Tool(
        name="get_backtest_results",
        description="Get backtest results and performance metrics",
        inputSchema={
            "type": "object",
            "properties": {"backtest_id": {"type": "string", "description": "Backtest run ID"}},
            "required": ["backtest_id"],
        },
    ),
    Tool(
        name="get_backtest_status",
        description="Get current status and progress of a running backtest.",
        inputSchema={
            "type": "object",
            "properties": {"backtest_id": {"type": "string", "description": "Backtest run ID"}},
            "required": ["backtest_id"],
        },
    ),
    Tool(
        name="list_backtests",
        description="List all backtests",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max backtests to return (default 20)", "default": 20},
                "status": {"type": "string", "enum": ["running", "completed", "failed", "pending"], "description": "Filter by status (optional)"},
            },
        },
    ),
    Tool(
        name="cancel_backtest",
        description="Cancel a running backtest",
        inputSchema={
            "type": "object",
            "properties": {"backtest_id": {"type": "string", "description": "Backtest run ID"}},
            "required": ["backtest_id"],
        },
    ),
    Tool(
        name="cancel_all_backtests",
        description="Cancel all running backtests",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="cleanup_ghost_backtests",
        description="Mark ghost backtests (stuck at 0 candles for >1 hour) as failed",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="run_backtest_and_wait",
        description="Create a backtest and wait for completion (polls internally). Best for short backtests (<3 months). For longer backtests, use create_backtest + get_backtest_status.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Backtest name"},
                "symbol": {"type": "string", "description": "Trading symbol"},
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "strategy": {"type": "string", "description": "Strategy name"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "initial_capital": {"type": "number", "default": 10000},
                "timeout_seconds": {"type": "integer", "description": "Max wait seconds (default 120, max 300)", "default": 120},
            },
            "required": ["name", "symbol", "start_date", "end_date", "strategy", "timeframe"],
        },
    ),

    # ── ML / Forecasting ──────────────────────────────────────────
    Tool(
        name="get_forecast",
        description="Get ML price forecast for a symbol",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading symbol"},
                "horizon": {"type": "string", "description": "Forecast horizon (e.g., '1H', '4H', '1D')"},
            },
            "required": ["symbol"],
        },
    ),

    # ── Strategy Management ───────────────────────────────────────
    Tool(
        name="list_strategies",
        description="List available trading strategies",
        inputSchema={"type": "object", "properties": {}},
    ),

    # ── Pending Orders ────────────────────────────────────────────
    Tool(
        name="place_pending_order",
        description="Place a pending order (BUY_STOP, SELL_STOP, BUY_LIMIT, SELL_LIMIT)",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "order_type": {"type": "string", "enum": ["BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT"]},
                "entry_price": {"type": "number", "description": "Price at which order triggers"},
                "lot_size": {"type": "number"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
                "expiration": {"type": "string", "description": "ISO datetime (optional)"},
                "comment": {"type": "string"},
            },
            "required": ["symbol", "order_type", "entry_price", "lot_size"],
        },
    ),
    Tool(
        name="get_pending_orders",
        description="Get all pending orders (not yet triggered)",
        inputSchema={
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Filter by symbol (optional)"}},
        },
    ),
    Tool(
        name="cancel_pending_order",
        description="Cancel a specific pending order",
        inputSchema={
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "Pending order ID to cancel"}},
            "required": ["order_id"],
        },
    ),
    Tool(
        name="cancel_all_pending_orders",
        description="Cancel all pending orders (optionally filtered by symbol)",
        inputSchema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
        },
    ),
    Tool(
        name="load_pending_orders_strategy",
        description="Load pending orders from a strategy JSON file",
        inputSchema={
            "type": "object",
            "properties": {"strategy_file": {"type": "string", "description": "Path relative to config/pending_orders/"}},
            "required": ["strategy_file"],
        },
    ),
    Tool(
        name="save_pending_orders_strategy",
        description="Save current pending orders to a strategy JSON file",
        inputSchema={
            "type": "object",
            "properties": {
                "strategy_name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["strategy_name"],
        },
    ),

    # ── Position Modification & Institutional Stops ───────────────
    Tool(
        name="modify_position",
        description="Modify stop loss and/or take profit of an open position.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticket": {"type": "integer", "description": "Position ticket number"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
            },
            "required": ["ticket"],
        },
    ),
    Tool(
        name="calculate_institutional_stop",
        description="Calculate an institutional-grade stop loss using ATR with random offset to avoid obvious liquidity clusters.",
        inputSchema={
            "type": "object",
            "properties": {
                "entry_price": {"type": "number"},
                "direction": {"type": "string", "enum": ["long", "short"]},
                "atr_value": {"type": "number", "description": "Current ATR value in price terms"},
                "atr_multiplier": {"type": "number", "default": 2.0},
                "structure_level": {"type": "number", "description": "Key S/R level to position beyond"},
                "min_offset_pips": {"type": "number", "default": 5},
                "max_offset_pips": {"type": "number", "default": 15},
            },
            "required": ["entry_price", "direction", "atr_value"],
        },
    ),

    # ── Strategy Optimizer ────────────────────────────────────────
    Tool(
        name="optimize_strategy",
        description="Run MetaTrader-style strategy optimization. Tests parameter combinations and returns best parameters.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "strategy": {"type": "string"},
                "optimization_target": {"type": "string", "enum": ["sharpe_ratio", "total_return_pct", "profit_factor", "risk_adjusted_return"], "default": "sharpe_ratio"},
                "max_combinations": {"type": "integer", "default": 100},
                "initial_capital": {"type": "number", "default": 10000},
            },
            "required": ["symbol", "timeframe", "start_date", "end_date", "strategy"],
        },
    ),
    Tool(
        name="get_strategy_param_grid",
        description="Get the default parameter grid for a strategy optimization",
        inputSchema={
            "type": "object",
            "properties": {"strategy": {"type": "string"}},
            "required": ["strategy"],
        },
    ),

    # ── Enhanced Optimizer ────────────────────────────────────────
    Tool(
        name="rolling_window_optimize",
        description="Rolling window optimization: re-optimizes parameters at regular intervals using recent data.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "strategy": {"type": "string"},
                "optimization_target": {"type": "string", "default": "sharpe_ratio"},
                "train_months": {"type": "integer", "default": 3},
                "test_months": {"type": "integer", "default": 1},
                "step_months": {"type": "integer", "default": 1},
                "max_combinations": {"type": "integer", "default": 100},
                "initial_capital": {"type": "number", "default": 10000},
            },
            "required": ["symbol", "timeframe", "start_date", "end_date", "strategy"],
        },
    ),
    Tool(
        name="time_interval_optimize",
        description="Optimize parameters for specific time intervals (quarters, months, seasons).",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "strategy": {"type": "string"},
                "intervals": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}}}},
                "optimization_target": {"type": "string", "default": "sharpe_ratio"},
                "max_combinations": {"type": "integer", "default": 100},
                "initial_capital": {"type": "number", "default": 10000},
            },
            "required": ["symbol", "timeframe", "start_date", "end_date", "strategy", "intervals"],
        },
    ),
    Tool(
        name="sensitivity_analysis",
        description="Analyze how each parameter affects strategy performance.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "strategy": {"type": "string"},
                "base_params": {"type": "object"},
                "initial_capital": {"type": "number", "default": 10000},
            },
            "required": ["symbol", "timeframe", "start_date", "end_date", "strategy"],
        },
    ),
    Tool(
        name="monte_carlo_validate",
        description="Monte Carlo validation: shuffles trade order to estimate luck vs skill.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "strategy": {"type": "string"},
                "params": {"type": "object", "description": "Strategy parameters to test"},
                "num_simulations": {"type": "integer", "default": 100},
                "initial_capital": {"type": "number", "default": 10000},
            },
            "required": ["symbol", "timeframe", "start_date", "end_date", "strategy", "params"],
        },
    ),

    # ── Async Optimization Jobs ───────────────────────────────────
    Tool(
        name="submit_optimization_job",
        description="Submit an async optimization job. Returns immediately with job_id. Use get_optimization_job_status to poll.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "strategy": {"type": "string"},
                "param_grid": {"type": "object", "description": "Parameter grid (e.g., {'fast_period': [5, 10, 15]})", "additionalProperties": {"type": "array"}},
                "optimization_target": {"type": "string", "enum": ["sharpe_ratio", "total_return_pct", "profit_factor", "risk_adjusted_return"], "default": "sharpe_ratio"},
                "initial_capital": {"type": "number", "default": 10000},
            },
            "required": ["symbol", "timeframe", "start_date", "end_date", "strategy", "param_grid"],
        },
    ),
    Tool(
        name="get_optimization_job_status",
        description="Get the current status and progress of an optimization job",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
    Tool(
        name="cancel_optimization_job",
        description="Cancel a running optimization job",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
    Tool(
        name="list_optimization_jobs",
        description="List all active optimization jobs with their status",
        inputSchema={
            "type": "object",
            "properties": {"status_filter": {"type": "string", "enum": ["pending", "running", "completed", "failed", "cancelled"]}},
        },
    ),
    Tool(
        name="get_optimization_job_results",
        description="Get full results for a completed optimization job",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),

    # ── Price Alerts ──────────────────────────────────────────────
    Tool(
        name="set_price_alerts",
        description="Set multiple price alerts for a position (liquidity_sweep, breakeven, key_level, custom).",
        inputSchema={
            "type": "object",
            "properties": {
                "ticket": {"type": "integer", "description": "MT4 position ticket number"},
                "alerts": {"type": "array", "items": {"type": "object", "properties": {"alert_type": {"type": "string"}, "price_level": {"type": "number"}, "direction": {"type": "string", "enum": ["above", "below"]}, "metadata": {"type": "object"}}}, "description": "List of alert configs"},
            },
            "required": ["ticket", "alerts"],
        },
    ),
    Tool(
        name="get_position_alerts",
        description="Get all active alerts for a position",
        inputSchema={
            "type": "object",
            "properties": {"ticket": {"type": "integer"}},
            "required": ["ticket"],
        },
    ),
    Tool(
        name="clear_position_alerts",
        description="Clear all alerts for a position (e.g., when position is closed)",
        inputSchema={
            "type": "object",
            "properties": {"ticket": {"type": "integer"}},
            "required": ["ticket"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool handler implementations — call services directly
# ---------------------------------------------------------------------------

def _json_result(data: Any) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


async def _handle_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Route tool name to the correct service call."""

    # ── Live Trading (MT4 direct) ─────────────────────────────────
    if name == "place_market_order":
        return await _place_market_order(**args)
    if name == "close_position":
        return await _close_position(**args)
    if name == "close_all_positions":
        return await _close_all_positions(**args)
    if name == "get_open_positions":
        return await _get_open_positions(**args)
    if name == "get_account_info":
        return await _get_account_info()

    # ── Market Data ───────────────────────────────────────────────
    if name == "get_latest_candles":
        return await _get_latest_candles(**args)
    if name == "get_symbols":
        return await _get_symbols()
    if name == "get_symbol_info":
        return await _get_symbol_info(**args)
    if name == "get_all_symbols_info":
        return await _get_all_symbols_info()

    # ── Backtesting ───────────────────────────────────────────────
    if name == "create_backtest":
        return await _create_backtest(**args)
    if name == "get_backtest_results":
        return await _get_backtest_results(**args)
    if name == "get_backtest_status":
        return await _get_backtest_status(**args)
    if name == "list_backtests":
        return await _list_backtests(**args)
    if name == "cancel_backtest":
        return await _cancel_backtest(**args)
    if name == "cancel_all_backtests":
        return await _cancel_all_backtests()
    if name == "cleanup_ghost_backtests":
        return await _cleanup_ghost_backtests()
    if name == "run_backtest_and_wait":
        return await _run_backtest_and_wait(**args)

    # ── ML / Forecasting ──────────────────────────────────────────
    if name == "get_forecast":
        return await _get_forecast(**args)

    # ── Strategies ────────────────────────────────────────────────
    if name == "list_strategies":
        return await _list_strategies()

    # ── Pending Orders ────────────────────────────────────────────
    if name == "place_pending_order":
        return await _place_pending_order(**args)
    if name == "get_pending_orders":
        return await _get_pending_orders(**args)
    if name == "cancel_pending_order":
        return await _cancel_pending_order(**args)
    if name == "cancel_all_pending_orders":
        return await _cancel_all_pending_orders(**args)
    if name == "load_pending_orders_strategy":
        return await _load_pending_orders_strategy(**args)
    if name == "save_pending_orders_strategy":
        return await _save_pending_orders_strategy(**args)

    # ── Position Modification ─────────────────────────────────────
    if name == "modify_position":
        return await _modify_position(**args)
    if name == "calculate_institutional_stop":
        return await _calculate_institutional_stop(**args)

    # ── Optimizer ─────────────────────────────────────────────────
    if name == "optimize_strategy":
        return await _optimize_strategy(**args)
    if name == "get_strategy_param_grid":
        return await _get_strategy_param_grid(**args)
    if name == "rolling_window_optimize":
        return await _rolling_window_optimize(**args)
    if name == "time_interval_optimize":
        return await _time_interval_optimize(**args)
    if name == "sensitivity_analysis":
        return await _sensitivity_analysis(**args)
    if name == "monte_carlo_validate":
        return await _monte_carlo_validate(**args)

    # ── Async Optimization Jobs ───────────────────────────────────
    if name == "submit_optimization_job":
        return await _submit_optimization_job(**args)
    if name == "get_optimization_job_status":
        return await _get_optimization_job_status(**args)
    if name == "cancel_optimization_job":
        return await _cancel_optimization_job(**args)
    if name == "list_optimization_jobs":
        return await _list_optimization_jobs(**args)
    if name == "get_optimization_job_results":
        return await _get_optimization_job_results(**args)

    # ── Price Alerts ──────────────────────────────────────────────
    if name == "set_price_alerts":
        return await _set_price_alerts(**args)
    if name == "get_position_alerts":
        return await _get_position_alerts(**args)
    if name == "clear_position_alerts":
        return await _clear_position_alerts(**args)

    return {"error": f"Unknown tool: {name}"}


# =========================================================================
# TOOL IMPLEMENTATIONS — Direct service calls
# =========================================================================

# ── Live Trading ────────────────────────────────────────────────────────

async def _place_market_order(
    symbol: str, side: str, quantity: float,
    stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
) -> Dict[str, Any]:
    direction = side.upper()
    for attempt in range(2):
        try:
            mt4 = await _get_mt4_client()
            result = await mt4.create_instant_order(
                symbol=symbol, direction=direction, volume=Decimal(str(quantity)),
                stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                take_profit=Decimal(str(take_profit)) if take_profit else None,
                comment="MCP Market Order",
            )
            if result.success:
                return {"success": True, "ticket": result.ticket_number, "symbol": symbol, "direction": direction, "volume": quantity, "message": f"Market order placed: {result.ticket_number}"}
            return {"success": False, "error": result.error_message or "Failed to place order"}
        except ConnectionError:
            if attempt < 1:
                await asyncio.sleep(0.5)
                continue
            return {"success": False, "error": "MT4 connection failed after retry"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Failed after retries"}


async def _close_position(position_id: int) -> Dict[str, Any]:
    for attempt in range(2):
        try:
            mt4 = await _get_mt4_client()
            result = await mt4.close_position(ticket_number=position_id)
            success = result.get("success", False) or result.get("status") == "OK"
            if success:
                return {"success": True, "ticket": position_id, "message": f"Position {position_id} closed"}
            return {"success": False, "ticket": position_id, "error": result.get("error_message") or "Failed to close"}
        except ConnectionError:
            if attempt < 1:
                await asyncio.sleep(0.5)
                continue
            return {"success": False, "ticket": position_id, "error": "MT4 connection failed"}
        except Exception as e:
            return {"success": False, "ticket": position_id, "error": str(e)}
    return {"success": False, "ticket": position_id, "error": "Failed after retries"}


async def _close_all_positions(symbol: Optional[str] = None) -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_open_positions()
        positions = result.get("positions", [])
        closed, errors = [], []
        for pos in positions:
            s, t = pos.get("symbol"), pos.get("ticket")
            if symbol and s != symbol:
                continue
            if t:
                try:
                    r = await mt4.close_position(ticket_number=t)
                    if r.get("success", False) or r.get("status") == "OK":
                        closed.append({"ticket": t, "symbol": s})
                    else:
                        errors.append({"ticket": t, "error": r.get("message")})
                except Exception as e:
                    errors.append({"ticket": t, "error": str(e)})
        return {"closed_count": len(closed), "error_count": len(errors), "closed": closed, "errors": errors}
    except Exception as e:
        return {"success": False, "error": str(e), "closed_count": 0}


async def _get_open_positions(symbol: Optional[str] = None, live_only: bool = True, limit: int = 20) -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_open_positions()
        positions = result.get("positions", [])
        if symbol:
            positions = [p for p in positions if p.get("symbol") == symbol]
        positions = positions[:limit]
        return {"positions": positions, "total": len(positions), "live_only": True, "source": "MT4 (shared ZMQ)"}
    except Exception as e:
        return {"positions": [], "total": 0, "error": str(e), "note": "MT4 connection failed"}


async def _get_account_info() -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_account_info()
        if result.get("success", False) or result.get("status") == "OK":
            info = result.get("account_info", {})
            return {
                "balance": info.get("balance"),
                "equity": info.get("equity"),
                "margin": info.get("margin"),
                "free_margin": info.get("freeMargin"),
                "margin_level": info.get("marginLevel"),
                "profit": info.get("profit"),
                "currency": info.get("currency"),
                "leverage": info.get("leverage"),
            }
        return {"error": result.get("error_message", "Failed to get account info")}
    except Exception as e:
        return {"error": str(e), "note": "MT4 connection failed"}


# ── Market Data ─────────────────────────────────────────────────────────

async def _get_latest_candles(symbol: str, timeframe: str, limit: int = 100) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.database.repositories.market_data_repository import MarketDataRepository
        repo = MarketDataRepository(db)
        candles = await repo.get_latest_ticks(symbol=symbol, timeframe=timeframe, limit=limit)
        return {
            "symbol": symbol, "timeframe": timeframe,
            "candles": [{"timestamp": str(c.timestamp), "open": float(c.open), "high": float(c.high), "low": float(c.low), "close": float(c.close), "volume": float(c.volume)} for c in candles],
            "total": len(candles),
        }


async def _get_symbols() -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        symbols_list = await mt4.get_symbols()
        return {"symbols": [{"symbol": s, "description": s} for s in symbols_list], "total": len(symbols_list), "source": "MT4 (shared ZMQ)"}
    except Exception as e:
        return {"symbols": [], "error": str(e)}


async def _get_symbol_info(symbol: str) -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_symbol_info(symbol)
        if result.get("success", False):
            return {"success": True, "symbol": symbol, "specifications": result}
        return {"success": False, "error": result.get("error_message", f"Failed to get info for {symbol}")}
    except Exception as e:
        return {"success": False, "error": str(e), "symbol": symbol}


async def _get_all_symbols_info() -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_all_symbols_info()
        if not result.get("success", False):
            return {"success": False, "error": result.get("error_message", "Failed")}
        symbols_info = result.get("symbols", [])
        categories: Dict[str, list] = {"commodities": [], "forex": [], "indices": [], "stocks": [], "crypto": [], "other": []}
        for sym in symbols_info:
            name = sym.get("symbol", "").upper()
            if any(x in name for x in ["OIL", "GOLD", "SILVER", "GAS", "COPPER", "XAU", "XAG"]):
                categories["commodities"].append(sym)
            elif any(x in name for x in ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]) and len(name) <= 7:
                categories["forex"].append(sym)
            elif any(x in name for x in ["US500", "US30", "US100", "DAX", "FTSE", "SPX", "NDX", "NAS", "GER", "UK100", "JP225"]):
                categories["indices"].append(sym)
            elif any(x in name for x in ["BTC", "ETH", "XRP", "DOGE"]):
                categories["crypto"].append(sym)
            else:
                categories["other"].append(sym)
        for cat in categories:
            categories[cat] = sorted(categories[cat], key=lambda x: x.get("leverage", 0), reverse=True)
        return {"success": True, "total": len(symbols_info), "symbols": symbols_info, "by_category": categories}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Backtesting (calls API routes internally via service layer) ─────────

async def _create_backtest(name: str, symbol: str, start_date: str, end_date: str, strategy: str, timeframe: str, initial_capital: float = 10000) -> Dict[str, Any]:
    """Start a backtest via the BacktestService."""
    async with get_db_context() as db:
        from src.services.backtesting.backtest_service import BacktestService
        from src.database.repositories.backtest_repository import BacktestRepository
        from src.database.models.backtest import ExecutionMode
        svc = BacktestService(BacktestRepository(db))

        config = await svc.create_configuration(
            name=name, symbol=symbol,
            start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
            initial_capital=Decimal(str(initial_capital)), execution_mode=ExecutionMode.SYNTHETIC_FAST,
            config_params={"synthetic_strategy": strategy},
        )

        run = await svc.run_backtest(config_id=config.id, timeframe=timeframe)
        await db.commit()

        return {
            "success": True, "config_id": str(config.id), "run_id": str(run.id),
            "status": "running", "message": "Backtest started in background.",
            "next_steps": [f"Use get_backtest_results with backtest_id='{run.id}' to check status"],
        }


async def _run_backtest_and_wait(
    name: str, symbol: str, start_date: str, end_date: str, strategy: str,
    timeframe: str, initial_capital: float = 10000, timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Run vectorized backtest — returns results immediately."""
    import time
    t0 = time.time()
    async with get_db_context() as db:
        try:
            from src.services.backtesting.vectorized_engine import VectorizedBacktestEngine, VectorizedBacktestConfig
            config = VectorizedBacktestConfig(
                symbol=symbol, timeframe=timeframe, start_date=datetime.fromisoformat(start_date),
                end_date=datetime.fromisoformat(end_date), strategy=strategy,
                strategy_params=_get_default_strategy_params(strategy), initial_capital=initial_capital,
            )
            engine = VectorizedBacktestEngine()
            result = await engine.run(config, db)
            elapsed = time.time() - t0
            return {
                "success": True, "status": "completed", "run_id": result.run_id,
                "elapsed_seconds": round(elapsed, 2), "execution_time_ms": result.execution_time_ms,
                "candles_processed": result.candles_processed, "total_trades": result.total_trades,
                "initial_capital": result.initial_capital, "final_capital": result.final_capital,
                "total_return_pct": result.total_return_pct,
                "metrics": {
                    "sharpe_ratio": result.sharpe_ratio, "sortino_ratio": result.sortino_ratio,
                    "max_drawdown_pct": result.max_drawdown_pct, "win_rate": result.win_rate,
                    "profit_factor": result.profit_factor, "avg_trade_pnl": result.avg_trade_pnl,
                },
                "trades": result.trades[:10],
                "message": f"Backtest completed in {result.execution_time_ms:.0f}ms (vectorized)",
            }
        except Exception as e:
            return {"success": False, "status": "error", "error": str(e), "elapsed_seconds": round(time.time() - t0, 2)}


async def _get_backtest_results(backtest_id: str) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.database.repositories.backtest_repository import BacktestRepository
        repo = BacktestRepository(db)
        run = await repo.get_run(backtest_id)
        if not run:
            return {"error": f"Backtest {backtest_id} not found"}
        return {
            "run_id": backtest_id, "status": run.status,
            "candles_processed": run.candles_processed, "total_trades": run.total_trades,
            "final_capital": float(run.final_capital) if run.final_capital else None,
            "metrics": run.metrics,
        }


async def _get_backtest_status(backtest_id: str) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.database.repositories.backtest_repository import BacktestRepository
        repo = BacktestRepository(db)
        run = await repo.get_run(backtest_id)
        if not run:
            return {"run_id": backtest_id, "status": "not_found"}
        result = {
            "run_id": backtest_id, "status": run.status,
            "candles_processed": run.candles_processed, "total_trades": run.total_trades,
        }
        if run.status == "completed":
            result["final_capital"] = float(run.final_capital) if run.final_capital else None
            result["metrics"] = run.metrics
            result["message"] = "Backtest completed!"
        elif run.status == "running":
            result["message"] = f"In progress. {run.candles_processed or 0:,} candles processed."
        elif run.status == "failed":
            result["error"] = run.error_message
        return result


async def _list_backtests(limit: int = 20, status: Optional[str] = None) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.database.repositories.backtest_repository import BacktestRepository
        repo = BacktestRepository(db)
        runs = await repo.list_runs(limit=limit, status=status)
        return {
            "items": [{"id": str(r.id), "status": r.status, "candles_processed": r.candles_processed, "total_trades": r.total_trades, "start_time": str(r.created_at) if r.created_at else None} for r in runs],
            "total": len(runs),
        }


async def _cancel_backtest(backtest_id: str) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.database.repositories.backtest_repository import BacktestRepository
        repo = BacktestRepository(db)
        run = await repo.get_run(backtest_id)
        if run:
            run.status = "cancelled"
            await db.commit()
            return {"success": True, "backtest_id": backtest_id, "message": "Cancelled"}
        return {"success": False, "error": f"Backtest {backtest_id} not found"}


async def _cancel_all_backtests() -> Dict[str, Any]:
    result = await _list_backtests(limit=50, status="running")
    cancelled = []
    for run in result.get("items", []):
        r = await _cancel_backtest(run["id"])
        if r.get("success"):
            cancelled.append(run["id"])
    return {"cancelled_count": len(cancelled), "cancelled": cancelled}


async def _cleanup_ghost_backtests() -> Dict[str, Any]:
    result = await _list_backtests(limit=100, status="running")
    cleaned = []
    now = datetime.now(timezone.utc)
    for run in result.get("items", []):
        candles = run.get("candles_processed", 0)
        start_str = run.get("start_time")
        if start_str and candles == 0:
            try:
                start = datetime.fromisoformat(str(start_str).replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if (now - start) > timedelta(hours=1):
                    r = await _cancel_backtest(run["id"])
                    if r.get("success"):
                        cleaned.append(run["id"])
            except Exception:
                pass
    return {"cleaned_count": len(cleaned), "cleaned": cleaned}


# ── ML / Forecasting ───────────────────────────────────────────────────

async def _get_forecast(symbol: str, horizon: Optional[str] = None) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.database.repositories.forecast_repository import ForecastRepository
            repo = ForecastRepository(db)
            forecast = await repo.get_latest(symbol=symbol, horizon=horizon or "1H", model_version="latest")
            if forecast:
                return {"symbol": symbol, "horizon": horizon, "forecast": {"predicted_price": float(forecast.predicted_price) if forecast.predicted_price else None, "confidence": forecast.confidence, "direction": forecast.direction, "created_at": str(forecast.created_at)}}
            return {"error": "No forecast available", "symbol": symbol}
        except Exception as e:
            return {"error": "Forecast service unavailable", "message": str(e), "symbol": symbol}


# ── Strategy Management ────────────────────────────────────────────────

async def _list_strategies() -> Dict[str, Any]:
    try:
        from src.services.backtesting.synthetic_engine import SyntheticEngine
        descriptions = {
            # Phase 1 strategies
            "crude_oil_v3": "Multi-indicator strategy with EMA, RSI, CCI, and ATR-based stops",
            "ma_crossover": "Simple moving average crossover strategy",
            "rsi": "RSI overbought/oversold mean reversion strategy",
            "trend_following": "Simple trend following with momentum",
            "mean_reversion": "Statistical mean reversion with standard deviation bands",
            "value_area": "Volume Profile / TPO based mean-reversion from VAH/VAL to POC",
            # Phase 2 strategies
            "crack_spread": (
                "Crack spread mean-reversion: gasoline_barrel_price − crude_price. "
                "Multi-symbol (CrudeOIL + GASOLINE). Hedge ratio 0.42 gas lots per crude lot. "
                "Entry ±1.5σ, stop 2.5σ. Seasonal overlay widens entry in Q2-Q3."
            ),
            "wti_brent_spread": (
                "WTI-Brent spread mean-reversion: BRENT_OIL − CrudeOIL. "
                "Multi-symbol (CrudeOIL + BRENT_OIL). 1:1 lot ratio (same barrel units). "
                "Entry ±1.5σ, stop 2.5σ. Historical range $3-$7."
            ),
            "seasonal_ma_corn": (
                "CORN seasonal MA crossover. Long bias Mar-Jun (planting), "
                "Short Sep-Nov (harvest), neutral otherwise. Fast=10, Slow=30 SMA."
            ),
            "seasonal_ma_wheat": (
                "WHEAT seasonal MA crossover. Long bias Feb-May (weather risk premium), "
                "Short Jul-Sep (harvest supply glut), neutral otherwise. Fast=10, Slow=30 SMA."
            ),
            "gbpjpy_carry": (
                "GBPJPY long-only carry trade. Entry on 20-SMA pullback while above 50-SMA. "
                "Stop: 2× ATR(14). Exit: close below 50-SMA. Earns +8pts/day swap on long."
            ),
            # Phase 3 strategies
            "vix_regime": (
                "VIX-proxy regime detector using USA500 rolling drawdown. "
                "Normal: all 1.0x. Elevated (5d drop >3%): momentum 2.0x, carry 0.0x. "
                "Crisis (10d drop >7%): crude_oil_v3 2.5x, crash_portfolio 1.0x. "
                "This strategy does NOT trade directly — it emits regime multipliers."
            ),
            "crash_portfolio": (
                "Crisis pre-positioning portfolio. Triggers on USA500 drawdown >7% in 10 bars. "
                "SHORT: CrudeOIL, USA500, USA100 (60% allocation — demand destruction). "
                "LONG: GOLD, 30Y_T-BOND, DOLLAR_INDX (40% — safe havens). "
                "ATR-based stops (2.5× ATR + random 5-15 pip anti-hunt offset). "
                "Trailing stop at 2× ATR once profitable 1× ATR. "
                "Exit: USA500 recovers >3% from crash low. "
                "In backtest: primary_symbol (USA500) only; in live: all 6 symbols deploy."
            ),
        }
        all_strategy_names = [
            # Phase 1
            "crude_oil_v3", "ma_crossover", "rsi", "trend_following", "mean_reversion", "value_area",
            # Phase 2
            "crack_spread", "wti_brent_spread", "seasonal_ma_corn", "seasonal_ma_wheat", "gbpjpy_carry",
            # Phase 3
            "vix_regime", "crash_portfolio",
        ]
        strategies = []
        for name in all_strategy_names:
            params = SyntheticEngine._default_params(name)
            if params:
                strategies.append({
                    "name": name,
                    "description": descriptions.get(name, ""),
                    "parameters": {k: str(v) if hasattr(v, '__class__') and v.__class__.__name__ == 'Decimal' else v
                                   for k, v in params.items() if k != "quantity"},
                })
        return {"strategies": strategies, "total": len(strategies)}
    except Exception as e:
        return {"strategies": [], "error": str(e)}


# ── Pending Orders ─────────────────────────────────────────────────────

async def _place_pending_order(symbol: str, order_type: str, entry_price: float, lot_size: float,
                               stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                               expiration: Optional[str] = None, comment: Optional[str] = None) -> Dict[str, Any]:
    valid_types = ["BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT"]
    if order_type not in valid_types:
        return {"success": False, "error": f"Invalid order_type. Must be one of: {valid_types}"}
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.create_pending_order(
            symbol=symbol, order_type=order_type, volume=Decimal(str(lot_size)),
            price=Decimal(str(entry_price)),
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            take_profit=Decimal(str(take_profit)) if take_profit else None,
            comment=comment, expiration=expiration,
        )
        ticket = result.get("ticket_number")
        success = result.get("success", False) or result.get("status") == "OK"
        if success:
            risk_per_lot = abs(entry_price - stop_loss) * 100 if stop_loss else None
            reward_per_lot = abs(take_profit - entry_price) * 100 if take_profit else None
            rr = reward_per_lot / risk_per_lot if risk_per_lot and reward_per_lot else None
            return {"success": True, "ticket": ticket, "order": {"ticket": ticket, "symbol": symbol, "order_type": order_type, "entry_price": entry_price, "lot_size": lot_size, "stop_loss": stop_loss, "take_profit": take_profit},
                    "risk_metrics": {"risk_per_lot_usd": risk_per_lot, "reward_per_lot_usd": reward_per_lot, "risk_reward_ratio": round(rr, 2) if rr else None}}
        return {"success": False, "error": result.get("error_message") or "Failed to place order"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _get_pending_orders(symbol: Optional[str] = None) -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_pending_orders()
        orders = result.get("orders", [])
        if symbol:
            orders = [o for o in orders if o.get("symbol") == symbol]
        return {"success": True, "pending_orders": orders, "total": len(orders)}
    except Exception as e:
        return {"success": False, "error": str(e), "pending_orders": [], "total": 0}


async def _cancel_pending_order(order_id: str) -> Dict[str, Any]:
    try:
        ticket = int(order_id)
        mt4 = await _get_mt4_client()
        result = await mt4.delete_pending_order(ticket=ticket)
        if result.get("success", False) or result.get("status") == "OK":
            return {"success": True, "ticket": ticket, "message": f"Order {ticket} cancelled"}
        return {"success": False, "error": result.get("error_message") or "Failed to cancel"}
    except ValueError:
        return {"success": False, "error": f"Invalid order_id: {order_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _cancel_all_pending_orders(symbol: Optional[str] = None) -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.get_pending_orders()
        orders = result.get("orders", [])
        if symbol:
            orders = [o for o in orders if o.get("symbol") == symbol]
        cancelled, errors = [], []
        for o in orders:
            t = o.get("ticket")
            if t:
                try:
                    r = await mt4.delete_pending_order(ticket=t)
                    if r.get("success", False) or r.get("status") == "OK":
                        cancelled.append(t)
                    else:
                        errors.append({"ticket": t, "error": r.get("message")})
                except Exception as e:
                    errors.append({"ticket": t, "error": str(e)})
        return {"success": len(errors) == 0, "cancelled_count": len(cancelled), "cancelled_tickets": cancelled, "errors": errors or None}
    except Exception as e:
        return {"success": False, "error": str(e), "cancelled_count": 0}


async def _load_pending_orders_strategy(strategy_file: str) -> Dict[str, Any]:
    import os
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "config", "pending_orders", strategy_file)
    if not os.path.exists(path):
        return {"success": False, "error": f"Strategy file not found: {path}"}
    try:
        with open(path) as f:
            strategy = json.load(f)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {e}"}
    loaded, errors = [], []
    for order_def in strategy.get("pending_orders", []):
        if not order_def.get("enabled", True):
            continue
        try:
            r = await _place_pending_order(
                symbol=order_def["symbol"], order_type=order_def["order_type"],
                entry_price=order_def["entry_price"], lot_size=order_def["lot_size"],
                stop_loss=order_def.get("stop_loss"), take_profit=order_def.get("take_profit"),
                expiration=order_def.get("expiration"), comment=order_def.get("notes") or order_def.get("id"),
            )
            if r["success"]:
                loaded.append(r["order"])
            else:
                errors.append({"order": order_def.get("id"), "error": r["error"]})
        except Exception as e:
            errors.append({"order": order_def.get("id", "?"), "error": str(e)})
    return {"success": len(errors) == 0, "strategy_name": strategy.get("strategy_name"), "loaded_count": len(loaded), "errors": errors or None}


async def _save_pending_orders_strategy(strategy_name: str, description: Optional[str] = None) -> Dict[str, Any]:
    orders_result = await _get_pending_orders()
    orders = orders_result.get("pending_orders", [])
    if not orders:
        return {"success": False, "error": "No pending orders to save"}
    import os
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "config", "pending_orders", f"{strategy_name.lower().replace(' ', '_')}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    strategy = {
        "strategy_name": strategy_name, "created_at": datetime.utcnow().isoformat(),
        "description": description or f"Exported on {datetime.utcnow().strftime('%Y-%m-%d')}",
        "pending_orders": [{"symbol": o.get("symbol"), "order_type": o.get("order_type"), "entry_price": o.get("open_price"), "stop_loss": o.get("stop_loss"), "take_profit": o.get("take_profit"), "lot_size": o.get("volume"), "enabled": True} for o in orders],
    }
    with open(path, "w") as f:
        json.dump(strategy, f, indent=2)
    return {"success": True, "file_path": path, "orders_saved": len(orders)}


# ── Position Modification ──────────────────────────────────────────────

async def _modify_position(ticket: int, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Dict[str, Any]:
    try:
        mt4 = await _get_mt4_client()
        result = await mt4.modify_position(
            ticket=ticket,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            take_profit=Decimal(str(take_profit)) if take_profit else None,
        )
        return {"success": result.get("success", False) or result.get("status") == "OK", "ticket": ticket, "new_stop_loss": stop_loss, "new_take_profit": take_profit}
    except Exception as e:
        return {"success": False, "ticket": ticket, "error": str(e)}


async def _calculate_institutional_stop(
    entry_price: float, direction: str, atr_value: float,
    atr_multiplier: float = 2.0, structure_level: Optional[float] = None,
    min_offset_pips: float = 5, max_offset_pips: float = 15,
) -> Dict[str, Any]:
    pip_value = 0.01
    base_distance = atr_value * atr_multiplier
    offset = random.uniform(min_offset_pips, max_offset_pips) * pip_value
    if direction.lower() == "long":
        stop = entry_price - base_distance - offset
        if structure_level and stop > structure_level:
            stop = structure_level - offset
    else:
        stop = entry_price + base_distance + offset
        if structure_level and stop < structure_level:
            stop = structure_level + offset
    stop = round(stop, 2)
    dist = abs(entry_price - stop)
    return {
        "success": True, "stop_price": stop, "entry_price": entry_price, "direction": direction,
        "stop_distance_price": round(dist, 2), "stop_distance_pips": round(dist / pip_value, 1),
        "atr_multiplier": atr_multiplier, "random_offset_applied": round(offset, 3),
        "reasoning": f"ATR-based stop ({atr_multiplier}x ATR = {round(base_distance, 2)}) with random offset",
    }


# ── Strategy Optimizer ─────────────────────────────────────────────────

async def _optimize_strategy(symbol: str, timeframe: str, start_date: str, end_date: str,
                             strategy: str, optimization_target: str = "sharpe_ratio",
                             max_combinations: int = 100, initial_capital: float = 10000) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.backtesting.optimizer import StrategyOptimizer
            optimizer = StrategyOptimizer(db)
            result = await optimizer.optimize(
                symbol=symbol, timeframe=timeframe,
                start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
                strategy=strategy, optimization_target=optimization_target,
                max_combinations=max_combinations, initial_capital=initial_capital,
            )
            return {
                "success": True, "strategy": strategy, "symbol": symbol,
                "best_params": result.best_params if hasattr(result, "best_params") else None,
                "best_return_pct": result.best_return_pct if hasattr(result, "best_return_pct") else None,
                "best_sharpe": result.best_sharpe if hasattr(result, "best_sharpe") else None,
                "combinations_tested": result.combinations_tested if hasattr(result, "combinations_tested") else None,
                "top_results": result.top_results[:5] if hasattr(result, "top_results") else [],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _get_strategy_param_grid(strategy: str) -> Dict[str, Any]:
    try:
        from src.services.backtesting.optimizer import StrategyOptimizer
        grids = StrategyOptimizer.DEFAULT_PARAM_GRIDS
        if strategy not in grids:
            return {"error": f"Unknown strategy: {strategy}", "available": list(grids.keys())}
        grid = grids[strategy]
        total = 1
        for v in grid.values():
            total *= len(v)
        return {"strategy": strategy, "param_grid": grid, "total_combinations": total}
    except Exception as e:
        return {"error": str(e)}


async def _rolling_window_optimize(symbol: str, timeframe: str, start_date: str, end_date: str, strategy: str,
                                   optimization_target: str = "sharpe_ratio", train_months: int = 3,
                                   test_months: int = 1, step_months: int = 1, max_combinations: int = 100,
                                   initial_capital: float = 10000) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
            opt = EnhancedOptimizer(db)
            return await opt.rolling_window_optimize(
                symbol=symbol, timeframe=timeframe,
                start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
                strategy=strategy, optimization_target=optimization_target,
                train_months=train_months, test_months=test_months, step_months=step_months,
                max_combinations=max_combinations, initial_capital=initial_capital,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _time_interval_optimize(symbol: str, timeframe: str, start_date: str, end_date: str, strategy: str,
                                  intervals: List[Dict[str, str]], optimization_target: str = "sharpe_ratio",
                                  max_combinations: int = 100, initial_capital: float = 10000) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
            opt = EnhancedOptimizer(db)
            return await opt.time_interval_optimize(
                symbol=symbol, timeframe=timeframe,
                start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
                strategy=strategy, intervals=intervals, optimization_target=optimization_target,
                max_combinations=max_combinations, initial_capital=initial_capital,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _sensitivity_analysis(symbol: str, timeframe: str, start_date: str, end_date: str, strategy: str,
                                base_params: Optional[Dict[str, Any]] = None, initial_capital: float = 10000) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
            opt = EnhancedOptimizer(db)
            return await opt.full_sensitivity_analysis(
                symbol=symbol, timeframe=timeframe,
                start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
                strategy=strategy, base_params=base_params, initial_capital=initial_capital,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _monte_carlo_validate(symbol: str, timeframe: str, start_date: str, end_date: str, strategy: str,
                                params: Dict[str, Any], num_simulations: int = 100,
                                initial_capital: float = 10000) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.backtesting.enhanced_optimizer import EnhancedOptimizer
            opt = EnhancedOptimizer(db)
            return await opt.monte_carlo_validate(
                symbol=symbol, timeframe=timeframe,
                start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
                strategy=strategy, params=params, num_simulations=num_simulations, initial_capital=initial_capital,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── Async Optimization Jobs ───────────────────────────────────────────

async def _submit_optimization_job(symbol: str, timeframe: str, start_date: str, end_date: str,
                                   strategy: str, param_grid: Dict[str, List],
                                   optimization_target: str = "sharpe_ratio", initial_capital: float = 10000) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.optimization_job_service import OptimizationJobService
            svc = OptimizationJobService(db)
            return await svc.submit_job(
                strategy=strategy, symbol=symbol, timeframe=timeframe,
                start_date=datetime.fromisoformat(start_date), end_date=datetime.fromisoformat(end_date),
                param_grid=param_grid, optimization_target=optimization_target, initial_capital=initial_capital,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _get_optimization_job_status(job_id: str) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.services.optimization_job_service import OptimizationJobService
        svc = OptimizationJobService(db)
        result = await svc.get_job_status(job_id)
        return result or {"error": f"Job {job_id} not found"}


async def _cancel_optimization_job(job_id: str) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.services.optimization_job_service import OptimizationJobService
        svc = OptimizationJobService(db)
        return await svc.cancel_job(job_id)


async def _list_optimization_jobs(status_filter: Optional[str] = None) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.services.optimization_job_service import OptimizationJobService
        svc = OptimizationJobService(db)
        jobs = await svc.list_active_jobs(status_filter=status_filter)
        return {"jobs": jobs, "total": len(jobs)}


async def _get_optimization_job_results(job_id: str) -> Dict[str, Any]:
    async with get_db_context() as db:
        from src.services.optimization_job_service import OptimizationJobService
        svc = OptimizationJobService(db)
        result = await svc.get_job_results(job_id)
        return result or {"error": f"Job {job_id} not found or not completed"}


# ── Price Alerts ──────────────────────────────────────────────────────

async def _set_price_alerts(ticket: int, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.price_alert_service import get_price_alert_service
            svc = await get_price_alert_service(db)
            created = await svc.set_multiple_alerts(ticket=ticket, alerts=alerts)
            return {"success": True, "ticket": ticket, "alerts_created": len(created), "alerts": [{"id": str(a.id), "alert_type": a.alert_type, "price_level": float(a.price_level), "direction": a.direction} for a in created]}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _get_position_alerts(ticket: int) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.price_alert_service import get_price_alert_service
            svc = await get_price_alert_service(db)
            alerts = await svc.get_alerts_for_ticket(ticket)
            return {"success": True, "ticket": ticket, "alerts": [{"id": str(a.id), "alert_type": a.alert_type, "price_level": float(a.price_level), "direction": a.direction} for a in alerts], "total": len(alerts)}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _clear_position_alerts(ticket: int) -> Dict[str, Any]:
    async with get_db_context() as db:
        try:
            from src.services.price_alert_service import get_price_alert_service
            svc = await get_price_alert_service(db)
            deleted = await svc.clear_alerts_for_ticket(ticket)
            return {"success": True, "ticket": ticket, "deleted": deleted}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── Helper ──────────────────────────────────────────────────────────────

def _get_default_strategy_params(strategy: str) -> Dict[str, Any]:
    defaults = {
        "ma_crossover": {"fast_period": 10, "slow_period": 30},
        "rsi": {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
        "crude_oil_v3": {"ema_fast": 8, "ema_slow": 29, "rsi_period": 10, "rsi_overbought": 68, "rsi_oversold": 32, "cci_period": 20, "momentum_period": 10},
        "mean_reversion": {"lookback": 20, "std_threshold": 2.0},
        "value_area": {"lookback_periods": 24, "value_area_percent": 0.70, "tpo_resolution": 0.10, "stop_atr_multiplier": 1.5, "target_mode": "poc", "atr_period": 14},
    }
    return defaults.get(strategy, {})


# =========================================================================
# MCP SERVER FACTORY — creates Starlette app to mount in FastAPI
# =========================================================================

def create_mcp_app() -> Starlette:
    """
    Create a Starlette sub-application that serves MCP over SSE.

    Mount this on FastAPI with:
        app.mount("/mcp", create_mcp_app())

    Claude Code connects to:
        http://localhost:8003/mcp/sse
    """
    server = Server("risetrader")
    sse_transport = SseServerTransport("/mcp/messages/")

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            result = await _handle_tool(name, arguments)
            return _json_result(result)
        except Exception as e:
            logger.error("mcp_tool_error", tool=name, error=str(e), exc_info=True)
            return _json_result({"error": str(e)})

    async def handle_sse(request):
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
    )
