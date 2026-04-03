"""
RiseTrader MCP Server

Exposes comprehensive trading platform capabilities to Claude and other LLMs
via the Model Context Protocol (MCP).

This server provides tools for:
- Live trading (place/close orders)
- Pending orders (limit/stop orders)
- Market data access
- Backtesting
- Portfolio management
- ML/forecasting
- Strategy management
- Risk management
"""
import asyncio
import json
import logging
import os
import sys
import warnings
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

# CRITICAL: Suppress stdout during imports to prevent MCP JSON protocol corruption
# Some libraries (zmq, aiohttp) may print debug info to stdout
warnings.filterwarnings('ignore')
os.environ.setdefault('PYTHONWARNINGS', 'ignore')

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging to stderr (stdout is reserved for MCP JSON protocol)
logging.basicConfig(
    level=logging.WARNING,  # Reduced from INFO to minimize output
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stderr  # CRITICAL: MCP requires stdout for JSON only
)

# Suppress verbose loggers
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("zmq").setLevel(logging.WARNING)

logger = logging.getLogger("risetrader-mcp")


class RiseTraderMCP:
    """MCP Server for RiseTrader platform."""

    def __init__(self, api_base_url: str = "http://localhost:8003", mt4_host: str = "localhost", mt4_port: int = 5555):
        """
        Initialize MCP server.

        Args:
            api_base_url: Base URL for RiseTrader API
            mt4_host: MT4 ZMQ server host
            mt4_port: MT4 ZMQ server port
        """
        self.api_base_url = api_base_url
        self.mt4_host = mt4_host
        self.mt4_port = mt4_port
        self.server = Server("risetrader")
        
        # MT4 Client for direct ZMQ communication (lazy initialization)
        self._mt4_client = None

        # Register all tool handlers
        self._register_tools()

        logger.info(f"RiseTrader MCP Server initialized (API: {api_base_url}, MT4: {mt4_host}:{mt4_port})")

    async def _get_mt4_client(self):
        """Get or create MT4 client connection."""
        if self._mt4_client is None:
            from src.trading.execution.mt4_client import MT4Client
            from src.trading.execution.mt4_encryption import MT4EncryptionManager
            
            encryption_manager = MT4EncryptionManager(encryption_enabled=False)
            self._mt4_client = MT4Client(
                host=self.mt4_host,
                rep_port=self.mt4_port,
                pub_port=self.mt4_port + 1,
                magic_number=123456,
                encryption_manager=encryption_manager,
                timeout_ms=10000
            )
            await self._mt4_client.connect()
            logger.info("MT4 Client connected via ZMQ")
        return self._mt4_client

    def _register_tools(self):
        """Register all MCP tools."""

        # =====================================================================
        # LIVE TRADING TOOLS
        # =====================================================================

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List all available tools."""
            return [
                # Live Trading
                Tool(
                    name="place_market_order",
                    description="Place a market order (executes immediately at current price)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol (e.g., 'CrudeOIL', 'EURUSD')"
                            },
                            "side": {
                                "type": "string",
                                "enum": ["buy", "sell"],
                                "description": "Order side (buy or sell)"
                            },
                            "quantity": {
                                "type": "number",
                                "description": "Position size in lots"
                            },
                            "stop_loss": {
                                "type": "number",
                                "description": "Stop loss price (optional)"
                            },
                            "take_profit": {
                                "type": "number",
                                "description": "Take profit price (optional)"
                            }
                        },
                        "required": ["symbol", "side", "quantity"]
                    }
                ),
                Tool(
                    name="close_position",
                    description="Close an open position by position ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "position_id": {
                                "type": "integer",
                                "description": "Position ID to close"
                            }
                        },
                        "required": ["position_id"]
                    }
                ),
                Tool(
                    name="close_all_positions",
                    description="Emergency close all open positions",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Only close positions for this symbol (optional)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_open_positions",
                    description="Get open trading positions with optional filtering",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Filter by symbol (optional)"
                            },
                            "live_only": {
                                "type": "boolean",
                                "description": "Only show live (non-simulated) positions (default: true)",
                                "default": True
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum positions to return (default: 20)",
                                "default": 20
                            }
                        }
                    }
                ),
                Tool(
                    name="get_account_info",
                    description="Get trading account information (balance, equity, margin)",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),

                # Market Data
                Tool(
                    name="get_latest_candles",
                    description="Get recent candle data for technical analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol"
                            },
                            "timeframe": {
                                "type": "string",
                                "enum": ["M1", "M5", "M15", "H1", "H4", "D1"],
                                "description": "Candle timeframe"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of candles to fetch (default 100)",
                                "default": 100
                            }
                        },
                        "required": ["symbol", "timeframe"]
                    }
                ),
                Tool(
                    name="get_symbols",
                    description="Get list of available trading symbols",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="get_symbol_info",
                    description="Get detailed symbol specifications (leverage, margin %, swap rates, trading hours, contract size). Essential for Dalio-style portfolio diversification and risk management.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol (e.g., 'CrudeOIL', 'EURUSD')"
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="get_all_symbols_info",
                    description="Get detailed specifications for ALL trading symbols. Returns leverage, margin %, swap rates for portfolio analysis and finding high-leverage opportunities.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),

                # Backtesting
                Tool(
                    name="create_backtest",
                    description="Create and run a new backtest. Returns IMMEDIATELY with run_id - backtest runs in background (1-10+ min). Use get_backtest_results to poll for completion.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Backtest name"
                            },
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)"
                            },
                            "strategy": {
                                "type": "string",
                                "description": "Strategy name (e.g., 'crude_oil_v3', 'ma_crossover')"
                            },
                            "timeframe": {
                                "type": "string",
                                "enum": ["M1", "M5", "M15", "H1", "H4", "D1"],
                                "description": "Candle timeframe"
                            },
                            "initial_capital": {
                                "type": "number",
                                "description": "Starting capital (default 10000)",
                                "default": 10000
                            }
                        },
                        "required": ["name", "symbol", "start_date", "end_date", "strategy", "timeframe"]
                    }
                ),
                Tool(
                    name="get_backtest_results",
                    description="Get backtest results and performance metrics",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "backtest_id": {
                                "type": "string",
                                "description": "Backtest run ID"
                            }
                        },
                        "required": ["backtest_id"]
                    }
                ),
                Tool(
                    name="get_backtest_status",
                    description="Get current status and progress of a running backtest. Use this to poll for completion after create_backtest.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "backtest_id": {
                                "type": "string",
                                "description": "Backtest run ID"
                            }
                        },
                        "required": ["backtest_id"]
                    }
                ),
                Tool(
                    name="list_backtests",
                    description="List all backtests",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of backtests to return (default 20)",
                                "default": 20
                            },
                            "status": {
                                "type": "string",
                                "enum": ["running", "completed", "failed", "pending"],
                                "description": "Filter by status (optional)"
                            }
                        }
                    }
                ),
                Tool(
                    name="cancel_backtest",
                    description="Cancel a running backtest",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "backtest_id": {
                                "type": "string",
                                "description": "Backtest run ID to cancel"
                            }
                        },
                        "required": ["backtest_id"]
                    }
                ),
                Tool(
                    name="cancel_all_backtests",
                    description="Cancel all running backtests",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="cleanup_ghost_backtests",
                    description="Mark ghost backtests (stuck at 0 candles for >1 hour) as failed",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="run_backtest_and_wait",
                    description="Create a backtest and wait for completion (polls internally). Best for short backtests (<3 months). For longer backtests, use create_backtest + get_backtest_status to poll manually.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Backtest name"
                            },
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)"
                            },
                            "strategy": {
                                "type": "string",
                                "description": "Strategy name (e.g., 'crude_oil_v3', 'ma_crossover')"
                            },
                            "timeframe": {
                                "type": "string",
                                "enum": ["M1", "M5", "M15", "H1", "H4", "D1"],
                                "description": "Candle timeframe"
                            },
                            "initial_capital": {
                                "type": "number",
                                "description": "Starting capital (default 10000)",
                                "default": 10000
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Maximum time to wait in seconds (default 120, max 300)",
                                "default": 120
                            }
                        },
                        "required": ["name", "symbol", "start_date", "end_date", "strategy", "timeframe"]
                    }
                ),

                # ML/Forecasting
                Tool(
                    name="get_forecast",
                    description="Get ML price forecast for a symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol"
                            },
                            "horizon": {
                                "type": "string",
                                "description": "Forecast horizon (e.g., '1H', '4H', '1D')"
                            }
                        },
                        "required": ["symbol"]
                    }
                ),

                # Strategy Management
                Tool(
                    name="list_strategies",
                    description="List available trading strategies",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),

                # Pending Orders Management
                Tool(
                    name="place_pending_order",
                    description="Place a pending order (BUY_STOP, SELL_STOP, BUY_LIMIT, SELL_LIMIT) that triggers at specified price",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol (e.g., 'CrudeOIL', 'XAUUSD')"
                            },
                            "order_type": {
                                "type": "string",
                                "enum": ["BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT"],
                                "description": "Pending order type"
                            },
                            "entry_price": {
                                "type": "number",
                                "description": "Price at which order triggers"
                            },
                            "lot_size": {
                                "type": "number",
                                "description": "Position size in lots"
                            },
                            "stop_loss": {
                                "type": "number",
                                "description": "Stop loss price"
                            },
                            "take_profit": {
                                "type": "number",
                                "description": "Take profit price"
                            },
                            "expiration": {
                                "type": "string",
                                "description": "Order expiration datetime (ISO format, optional)"
                            },
                            "comment": {
                                "type": "string",
                                "description": "Order comment/label"
                            }
                        },
                        "required": ["symbol", "order_type", "entry_price", "lot_size"]
                    }
                ),
                Tool(
                    name="get_pending_orders",
                    description="Get all pending orders (not yet triggered)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Filter by symbol (optional)"
                            }
                        }
                    }
                ),
                Tool(
                    name="cancel_pending_order",
                    description="Cancel a specific pending order",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "string",
                                "description": "Pending order ID to cancel"
                            }
                        },
                        "required": ["order_id"]
                    }
                ),
                Tool(
                    name="cancel_all_pending_orders",
                    description="Cancel all pending orders (optionally filtered by symbol)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Only cancel orders for this symbol (optional)"
                            }
                        }
                    }
                ),
                Tool(
                    name="load_pending_orders_strategy",
                    description="Load pending orders from a strategy JSON file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "strategy_file": {
                                "type": "string",
                                "description": "Path to strategy JSON file (relative to config/pending_orders/)"
                            }
                        },
                        "required": ["strategy_file"]
                    }
                ),
                Tool(
                    name="save_pending_orders_strategy",
                    description="Save current pending orders to a strategy JSON file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "strategy_name": {
                                "type": "string",
                                "description": "Name for the strategy file"
                            },
                            "description": {
                                "type": "string",
                                "description": "Strategy description"
                            }
                        },
                        "required": ["strategy_name"]
                    }
                ),

                # =========================================================
                # INSTITUTIONAL STOP-HUNTING AVOIDANCE TOOLS
                # =========================================================
                Tool(
                    name="modify_position",
                    description="Modify stop loss and/or take profit of an open position. Use for adjusting stops to non-obvious levels (anti-stop-hunting), trailing stops, or moving to breakeven.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "ticket": {
                                "type": "integer",
                                "description": "Position ticket number to modify"
                            },
                            "stop_loss": {
                                "type": "number",
                                "description": "New stop loss price (optional, None keeps existing)"
                            },
                            "take_profit": {
                                "type": "number",
                                "description": "New take profit price (optional, None keeps existing)"
                            }
                        },
                        "required": ["ticket"]
                    }
                ),
                Tool(
                    name="calculate_institutional_stop",
                    description="Calculate an institutional-grade stop loss using ATR with random offset to avoid obvious liquidity clusters. Returns a 'weird' price like $56.37 instead of $56.50.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "entry_price": {
                                "type": "number",
                                "description": "Entry price of the position"
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["long", "short"],
                                "description": "Trade direction (long or short)"
                            },
                            "atr_value": {
                                "type": "number",
                                "description": "Current ATR value in price terms"
                            },
                            "atr_multiplier": {
                                "type": "number",
                                "description": "ATR multiplier (1.5-3.0, default 2.0 for normal volatility)",
                                "default": 2.0
                            },
                            "structure_level": {
                                "type": "number",
                                "description": "Optional key support/resistance level to position beyond"
                            },
                            "min_offset_pips": {
                                "type": "number",
                                "description": "Minimum random offset in pips (default 5)",
                                "default": 5
                            },
                            "max_offset_pips": {
                                "type": "number",
                                "description": "Maximum random offset in pips (default 15)",
                                "default": 15
                            }
                        },
                        "required": ["entry_price", "direction", "atr_value"]
                    }
                ),

                # =========================================================
                # STRATEGY OPTIMIZER TOOLS
                # =========================================================
                Tool(
                    name="optimize_strategy",
                    description="Run MetaTrader-style strategy optimization. Tests parameter combinations and returns best parameters for maximum returns/Sharpe ratio.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol (e.g., 'CrudeOIL')"
                            },
                            "timeframe": {
                                "type": "string",
                                "enum": ["M1", "M5", "M15", "H1", "H4", "D1"],
                                "description": "Candle timeframe"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)"
                            },
                            "strategy": {
                                "type": "string",
                                "description": "Strategy name (crude_oil_v3, ma_crossover, rsi, mean_reversion)"
                            },
                            "optimization_target": {
                                "type": "string",
                                "enum": ["sharpe_ratio", "total_return_pct", "profit_factor", "risk_adjusted_return"],
                                "description": "Metric to optimize (default: sharpe_ratio)",
                                "default": "sharpe_ratio"
                            },
                            "max_combinations": {
                                "type": "integer",
                                "description": "Maximum parameter combinations to test (default: 100 for quick scan)",
                                "default": 100
                            },
                            "initial_capital": {
                                "type": "number",
                                "description": "Starting capital (default 10000)",
                                "default": 10000
                            }
                        },
                        "required": ["symbol", "timeframe", "start_date", "end_date", "strategy"]
                    }
                ),
                Tool(
                    name="get_strategy_param_grid",
                    description="Get the default parameter grid for a strategy optimization",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "strategy": {
                                "type": "string",
                                "description": "Strategy name (crude_oil_v3, ma_crossover, rsi, mean_reversion)"
                            }
                        },
                        "required": ["strategy"]
                    }
                ),
                
                # =========================================================
                # ENHANCED OPTIMIZER TOOLS
                # =========================================================
                Tool(
                    name="rolling_window_optimize",
                    description="Rolling window optimization: re-optimizes parameters at regular intervals using recent data. Simulates real-world periodic re-calibration. Returns cumulative capital growth and robustness ratio.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Trading symbol"},
                            "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                            "strategy": {"type": "string", "description": "Strategy name"},
                            "optimization_target": {"type": "string", "default": "sharpe_ratio"},
                            "train_months": {"type": "integer", "default": 3, "description": "Training window months"},
                            "test_months": {"type": "integer", "default": 1, "description": "Testing window months"},
                            "step_months": {"type": "integer", "default": 1, "description": "Step forward months"},
                            "max_combinations": {"type": "integer", "default": 100},
                            "initial_capital": {"type": "number", "default": 10000}
                        },
                        "required": ["symbol", "timeframe", "start_date", "end_date", "strategy"]
                    }
                ),
                Tool(
                    name="time_interval_optimize",
                    description="Optimize parameters for specific time intervals (quarters, months, seasons). Returns best parameters per interval with stability analysis.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Trading symbol"},
                            "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                            "start_date": {"type": "string", "description": "Overall start date"},
                            "end_date": {"type": "string", "description": "Overall end date"},
                            "strategy": {"type": "string", "description": "Strategy name"},
                            "intervals": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "start_date": {"type": "string"},
                                        "end_date": {"type": "string"}
                                    }
                                },
                                "description": "List of intervals [{name, start_date, end_date}]"
                            },
                            "optimization_target": {"type": "string", "default": "sharpe_ratio"},
                            "max_combinations": {"type": "integer", "default": 100},
                            "initial_capital": {"type": "number", "default": 10000}
                        },
                        "required": ["symbol", "timeframe", "start_date", "end_date", "strategy", "intervals"]
                    }
                ),
                Tool(
                    name="sensitivity_analysis",
                    description="Analyze how each parameter affects strategy performance. Returns sensitivity rankings and optimal values.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Trading symbol"},
                            "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                            "strategy": {"type": "string", "description": "Strategy name"},
                            "base_params": {"type": "object", "description": "Base parameters (optional)"},
                            "initial_capital": {"type": "number", "default": 10000}
                        },
                        "required": ["symbol", "timeframe", "start_date", "end_date", "strategy"]
                    }
                ),
                Tool(
                    name="monte_carlo_validate",
                    description="Monte Carlo validation: shuffles trade order to estimate luck vs skill. Returns confidence intervals and percentile ranking.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Trading symbol"},
                            "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                            "strategy": {"type": "string", "description": "Strategy name"},
                            "params": {"type": "object", "description": "Strategy parameters to test"},
                            "num_simulations": {"type": "integer", "default": 100, "description": "Number of Monte Carlo simulations"},
                            "initial_capital": {"type": "number", "default": 10000}
                        },
                        "required": ["symbol", "timeframe", "start_date", "end_date", "strategy", "params"]
                    }
                ),

                # =========================================================
                # ASYNC OPTIMIZATION JOB TOOLS
                # =========================================================
                Tool(
                    name="submit_optimization_job",
                    description="Submit an async optimization job. Returns immediately with job_id. Use get_optimization_job_status to poll for progress. Best for large parameter grids that take minutes to hours.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Trading symbol (e.g., 'CrudeOIL')"},
                            "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1"]},
                            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                            "strategy": {"type": "string", "description": "Strategy name (crude_oil_v3, ma_crossover, rsi, mean_reversion)"},
                            "param_grid": {
                                "type": "object",
                                "description": "Parameter grid to search (e.g., {'fast_period': [5, 10, 15], 'slow_period': [20, 30, 40]})",
                                "additionalProperties": {"type": "array"}
                            },
                            "optimization_target": {
                                "type": "string",
                                "enum": ["sharpe_ratio", "total_return_pct", "profit_factor", "risk_adjusted_return"],
                                "default": "sharpe_ratio"
                            },
                            "initial_capital": {"type": "number", "default": 10000}
                        },
                        "required": ["symbol", "timeframe", "start_date", "end_date", "strategy", "param_grid"]
                    }
                ),
                Tool(
                    name="get_optimization_job_status",
                    description="Get the current status and progress of an optimization job",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "job_id": {"type": "string", "description": "Job ID returned from submit_optimization_job"}
                        },
                        "required": ["job_id"]
                    }
                ),
                Tool(
                    name="cancel_optimization_job",
                    description="Cancel a running optimization job",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "job_id": {"type": "string", "description": "Job ID to cancel"}
                        },
                        "required": ["job_id"]
                    }
                ),
                Tool(
                    name="list_optimization_jobs",
                    description="List all active optimization jobs with their status",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "status_filter": {
                                "type": "string",
                                "enum": ["pending", "running", "completed", "failed", "cancelled"],
                                "description": "Filter by status (optional)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_optimization_job_results",
                    description="Get full results for a completed optimization job, including all tested parameter combinations and metrics",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "job_id": {"type": "string", "description": "Job ID of the completed job"}
                        },
                        "required": ["job_id"]
                    }
                ),

                # ML Pipeline
                Tool(
                    name="compute_indicators",
                    description="Compute technical indicators (RSI, MACD, ATR, Bollinger Bands, MAs) for symbols and store in DB. Required before training ML models.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbols": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Trading symbols (e.g., ['CrudeOIL', 'XAUUSD'])"
                            },
                            "timeframes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Timeframes (e.g., ['H1', 'M30'])",
                                "default": ["H1"]
                            },
                            "force": {
                                "type": "boolean",
                                "description": "Recompute even if indicators exist (default: false)",
                                "default": False
                            }
                        },
                        "required": ["symbols"]
                    }
                ),
                Tool(
                    name="train_reversal_models",
                    description="Full ML training pipeline: compute indicators → ZigZag labeling → train XGBoost/LSTM reversal classifiers → save best model to disk. Returns F1 scores and model path.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol (e.g., 'CrudeOIL')"
                            },
                            "timeframe": {
                                "type": "string",
                                "description": "Candle timeframe (e.g., 'H1')",
                                "default": "H1"
                            },
                            "skip_indicators": {
                                "type": "boolean",
                                "description": "Skip indicator computation (assume already computed)",
                                "default": False
                            },
                            "skip_labels": {
                                "type": "boolean",
                                "description": "Skip ZigZag labeling (assume already labeled)",
                                "default": False
                            },
                            "model_configs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Config names to train (e.g., ['XGB-default', 'LSTM-default']). Default: all 4 configs."
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="run_ml_backtest",
                    description="Backtest ML reversal model predictions for P&L evaluation. Uses the trained model to predict peaks/valleys and generates buy/sell signals. Compare results against baseline strategies.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Trading symbol (e.g., 'CrudeOIL')"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)"
                            },
                            "timeframe": {
                                "type": "string",
                                "description": "Candle timeframe (e.g., 'H1')",
                                "default": "H1"
                            },
                            "model_type": {
                                "type": "string",
                                "enum": ["xgboost", "lstm"],
                                "description": "Model type to use (default: xgboost)",
                                "default": "xgboost"
                            },
                            "min_confidence": {
                                "type": "number",
                                "description": "Minimum prediction confidence threshold (default: 0.55)",
                                "default": 0.55
                            },
                            "initial_capital": {
                                "type": "number",
                                "description": "Starting capital (default: 10000)",
                                "default": 10000
                            }
                        },
                        "required": ["symbol", "start_date", "end_date"]
                    }
                ),

                # =========================================================
                # INFORMED FLOW DETECTION TOOLS
                # =========================================================
                Tool(
                    name="detect_informed_flow",
                    description=(
                        "Detect potential informed-flow (pre-announcement unusual activity) for a symbol. "
                        "Runs PriceVelocityDetector (M1 velocity anomaly), TickClusteringDetector (tick burst), "
                        "CrossAssetMonitor (correlation shifts), and NewsFeedService (news catalyst check). "
                        "Returns a composite InformedFlowStatus with overall_confidence, per-detector flags, "
                        "and a BUY/SELL/HOLD recommendation."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "MT4 trading symbol (e.g., 'CrudeOIL', 'XAUUSD')"
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="get_trump_posts",
                    description=(
                        "Return recent market-relevant posts from the TruthSocialMonitor. "
                        "Posts are pre-filtered for oil/market keywords and classified with "
                        "bullish/bearish/neutral sentiment. Returns an empty list when the monitor "
                        "is disabled (TRUTH_SOCIAL_ENABLED != 'true') or no posts match."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "hours_back": {
                                "type": "integer",
                                "description": "Look-back window in hours (default: 24)",
                                "default": 24
                            }
                        }
                    }
                ),
                Tool(
                    name="check_news_catalyst",
                    description=(
                        "Check whether a news catalyst exists for a symbol within a recent time window. "
                        "Queries NewsAPI.org (primary) and Finnhub (fallback). Returns has_catalyst flag, "
                        "article count, and a list of articles with headline, source, published_at, and url. "
                        "Results are cached per symbol for 5 minutes."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "MT4 trading symbol (e.g., 'CrudeOIL', 'XAUUSD')"
                            },
                            "minutes_back": {
                                "type": "integer",
                                "description": "Look-back window in minutes (default: 30)",
                                "default": 30
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
            ]

        # =====================================================================
        # TOOL HANDLERS
        # =====================================================================

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""

            try:
                # Route to appropriate handler
                if name == "place_market_order":
                    result = await self._place_market_order(**arguments)
                elif name == "close_position":
                    result = await self._close_position(**arguments)
                elif name == "close_all_positions":
                    result = await self._close_all_positions(**arguments)
                elif name == "get_open_positions":
                    result = await self._get_open_positions(**arguments)
                elif name == "get_account_info":
                    result = await self._get_account_info()
                elif name == "get_latest_candles":
                    result = await self._get_latest_candles(**arguments)
                elif name == "get_symbols":
                    result = await self._get_symbols()
                elif name == "get_symbol_info":
                    result = await self._get_symbol_info(**arguments)
                elif name == "get_all_symbols_info":
                    result = await self._get_all_symbols_info()
                elif name == "create_backtest":
                    result = await self._create_backtest(**arguments)
                elif name == "get_backtest_results":
                    result = await self._get_backtest_results(**arguments)
                elif name == "get_backtest_status":
                    result = await self._get_backtest_status(**arguments)
                elif name == "list_backtests":
                    result = await self._list_backtests(**arguments)
                elif name == "cancel_backtest":
                    result = await self._cancel_backtest(**arguments)
                elif name == "cancel_all_backtests":
                    result = await self._cancel_all_backtests()
                elif name == "cleanup_ghost_backtests":
                    result = await self._cleanup_ghost_backtests()
                elif name == "run_backtest_and_wait":
                    result = await self._run_backtest_and_wait(**arguments)
                elif name == "get_forecast":
                    result = await self._get_forecast(**arguments)
                elif name == "list_strategies":
                    result = await self._list_strategies()
                # Pending Orders
                elif name == "place_pending_order":
                    result = await self._place_pending_order(**arguments)
                elif name == "get_pending_orders":
                    result = await self._get_pending_orders(**arguments)
                elif name == "cancel_pending_order":
                    result = await self._cancel_pending_order(**arguments)
                elif name == "cancel_all_pending_orders":
                    result = await self._cancel_all_pending_orders(**arguments)
                elif name == "load_pending_orders_strategy":
                    result = await self._load_pending_orders_strategy(**arguments)
                elif name == "save_pending_orders_strategy":
                    result = await self._save_pending_orders_strategy(**arguments)
                # Institutional Stop-Hunting Avoidance
                elif name == "modify_position":
                    result = await self._modify_position(**arguments)
                elif name == "calculate_institutional_stop":
                    result = await self._calculate_institutional_stop(**arguments)
                # Strategy Optimizer
                elif name == "optimize_strategy":
                    result = await self._optimize_strategy(**arguments)
                elif name == "get_strategy_param_grid":
                    result = await self._get_strategy_param_grid(**arguments)
                # Enhanced Optimizer
                elif name == "rolling_window_optimize":
                    result = await self._rolling_window_optimize(**arguments)
                elif name == "time_interval_optimize":
                    result = await self._time_interval_optimize(**arguments)
                elif name == "sensitivity_analysis":
                    result = await self._sensitivity_analysis(**arguments)
                elif name == "monte_carlo_validate":
                    result = await self._monte_carlo_validate(**arguments)

                # Async optimization job tools
                elif name == "submit_optimization_job":
                    result = await self._submit_optimization_job(**arguments)
                elif name == "get_optimization_job_status":
                    result = await self._get_optimization_job_status(**arguments)
                elif name == "cancel_optimization_job":
                    result = await self._cancel_optimization_job(**arguments)
                elif name == "list_optimization_jobs":
                    result = await self._list_optimization_jobs(**arguments)
                elif name == "get_optimization_job_results":
                    result = await self._get_optimization_job_results(**arguments)

                # ML Pipeline
                elif name == "compute_indicators":
                    result = await self._compute_indicators(**arguments)
                elif name == "train_reversal_models":
                    result = await self._train_reversal_models(**arguments)
                elif name == "run_ml_backtest":
                    result = await self._run_ml_backtest(**arguments)

                # Informed Flow Detection
                elif name == "detect_informed_flow":
                    result = await self._detect_informed_flow(**arguments)
                elif name == "get_trump_posts":
                    result = await self._get_trump_posts(**arguments)
                elif name == "check_news_catalyst":
                    result = await self._check_news_catalyst(**arguments)
                else:
                    result = {"error": f"Unknown tool: {name}"}

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str)
                )]

            except Exception as e:
                logger.error(f"Tool '{name}' failed: {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]

    # =========================================================================
    # IMPLEMENTATION METHODS (API calls to RiseTrader backend)
    # =========================================================================

    async def _api_call(self, method: str, endpoint: str, timeout: int = 30, **kwargs) -> Dict[str, Any]:
        """Make API call to RiseTrader backend."""
        import aiohttp

        url = f"{self.api_base_url}{endpoint}"
        logger.info(f"API call: {method} {url}")

        # Use timeout to prevent hanging
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise Exception(f"API error ({response.status}): {text}")
                return await response.json()

    async def _place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """Place a market order using direct MT4 connection."""
        max_retries = 2
        last_error = None

        # Map side to MT4 direction (BUY/SELL uppercase)
        direction = side.upper()

        for attempt in range(max_retries):
            try:
                mt4_client = await self._get_mt4_client()

                # Convert to Decimal for MT4 client
                result = await mt4_client.create_instant_order(
                    symbol=symbol,
                    direction=direction,
                    volume=Decimal(str(quantity)),
                    stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                    take_profit=Decimal(str(take_profit)) if take_profit else None,
                    comment="MCP Market Order"
                )

                # Check if order was successful
                if result.success:
                    return {
                        "success": True,
                        "ticket": result.ticket_number,
                        "order_number": result.ticket_number,
                        "symbol": symbol,
                        "direction": direction,
                        "volume": quantity,
                        "message": f"Market order placed successfully: {result.ticket_number}"
                    }
                else:
                    return {
                        "success": False,
                        "error": result.error_message or "Failed to place market order"
                    }

            except ConnectionError as e:
                last_error = e
                logger.warning(f"Place market order attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    # Wait briefly before retry
                    await asyncio.sleep(0.5)
                    continue
            except Exception as e:
                logger.error(f"Error placing market order {symbol} {direction} {quantity}: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e)
                }

        return {
            "success": False,
            "error": str(last_error) if last_error else "Failed after retries"
        }

    async def _close_position(self, position_id: int) -> Dict[str, Any]:
        """Close a position using direct MT4 connection (position_id is the MT4 ticket number)."""
        max_retries = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                mt4_client = await self._get_mt4_client()
                result = await mt4_client.close_position(ticket_number=position_id)
                
                success = result.get("success", False) or result.get("status") == "OK"
                
                if success:
                    return {
                        "success": True,
                        "ticket": position_id,
                        "message": f"Position {position_id} closed successfully"
                    }
                else:
                    return {
                        "success": False,
                        "ticket": position_id,
                        "error": result.get("error_message") or result.get("message") or "Failed to close position"
                    }
            except ConnectionError as e:
                last_error = e
                logger.warning(f"Close position attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    # Wait briefly before retry (socket recovery should have been triggered)
                    await asyncio.sleep(0.5)
                    continue
            except Exception as e:
                logger.error(f"Error closing position {position_id}: {e}", exc_info=True)
                return {
                    "success": False,
                    "ticket": position_id,
                    "error": str(e)
                }
        
        return {
            "success": False,
            "ticket": position_id,
            "error": str(last_error) if last_error else "Failed after retries"
        }

    async def _close_all_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Close all positions using direct MT4 connection (optionally filtered by symbol)."""
        try:
            mt4_client = await self._get_mt4_client()
            
            # Get positions directly from MT4
            result = await mt4_client.get_open_positions()
            positions = result.get("positions", [])
            
            closed = []
            errors = []

            for pos in positions:
                pos_symbol = pos.get("symbol")
                ticket = pos.get("ticket")
                
                if symbol and pos_symbol != symbol:
                    continue
                
                if ticket:
                    try:
                        close_result = await mt4_client.close_position(ticket_number=ticket)
                        success = close_result.get("success", False) or close_result.get("status") == "OK"
                        if success:
                            closed.append({"ticket": ticket, "symbol": pos_symbol})
                        else:
                            errors.append({"ticket": ticket, "error": close_result.get("message")})
                    except Exception as e:
                        errors.append({"ticket": ticket, "error": str(e)})

            return {
                "closed_count": len(closed),
                "error_count": len(errors),
                "closed": closed,
                "errors": errors
            }
        except Exception as e:
            logger.error(f"Error closing all positions: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "closed_count": 0,
                "error_count": 0
            }

    async def _get_open_positions(
        self,
        symbol: Optional[str] = None,
        live_only: bool = True,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get open positions directly from MT4 via ZMQ."""
        try:
            # Get positions directly from MT4
            mt4_client = await self._get_mt4_client()
            result = await mt4_client.get_open_positions()

            positions = result.get("positions", [])

            # Filter by symbol if specified
            if symbol:
                positions = [p for p in positions if p.get("symbol") == symbol]

            # Apply limit
            positions = positions[:limit]

            return {
                "positions": positions,
                "total": len(positions),
                "live_only": True,  # MT4 positions are always live
                "limit": limit,
                "source": "MT4 (direct ZMQ connection)"
            }
        except Exception as e:
            logger.error(f"Error getting positions from MT4: {e}")
            return {
                "positions": [],
                "total": 0,
                "error": f"Could not fetch positions from MT4: {str(e)}",
                "note": "MT4 connection failed - ensure EA is running"
            }

    async def _get_account_info(self) -> Dict[str, Any]:
        """Get account information directly from MT4 via ZMQ."""
        try:
            mt4_client = await self._get_mt4_client()
            result = await mt4_client.get_account_info()

            is_success = result.get("success", False) or result.get("status") == "OK"
            if is_success:
                # Account data may be nested under "account_info" key
                acct = result.get("account_info", result)
                return {
                    "account_number": acct.get("account_number"),
                    "balance": acct.get("balance"),
                    "equity": acct.get("equity"),
                    "margin": acct.get("margin"),
                    "free_margin": acct.get("free_margin") or acct.get("freeMargin"),
                    "margin_level": acct.get("margin_level") or acct.get("marginLevel"),
                    "profit": acct.get("profit"),
                    "currency": acct.get("currency", "USD"),
                    "leverage": acct.get("leverage"),
                    "source": "MT4 (direct ZMQ connection)"
                }
            else:
                return {
                    "error": result.get("error_message", "Failed to get account info"),
                    "source": "MT4"
                }
        except Exception as e:
            logger.error(f"Error getting account info from MT4: {e}")
            return {
                "error": f"Could not fetch account info from MT4: {str(e)}",
                "note": "MT4 connection failed - ensure EA is running"
            }

    async def _get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get latest candles."""
        params = {
            "timeframe": timeframe,
            "limit": limit
        }
        return await self._api_call("GET", f"/api/market-data/{symbol}", params=params)

    async def _get_symbols(self) -> Dict[str, Any]:
        """Get available symbols directly from MT4 via ZMQ."""
        try:
            # Get symbols directly from MT4
            mt4_client = await self._get_mt4_client()
            symbols_list = await mt4_client.get_symbols()

            # Transform to expected format
            symbols = [{"symbol": sym, "description": sym} for sym in symbols_list]

            return {
                "symbols": symbols,
                "total": len(symbols),
                "source": "MT4 (direct ZMQ connection)"
            }
        except Exception as e:
            logger.warning(f"Failed to fetch symbols from MT4: {e}")
            return {
                "symbols": [],
                "error": f"Could not fetch symbols from MT4: {str(e)}",
                "note": "MT4 connection failed - ensure EA is running"
            }

    async def _get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Get detailed symbol specifications directly from MT4 via ZMQ."""
        try:
            mt4_client = await self._get_mt4_client()
            result = await mt4_client.get_symbol_info(symbol)

            if result.get("success", False):
                return {
                    "success": True,
                    "symbol": symbol,
                    "specifications": result,
                    "source": "MT4 (direct ZMQ connection)"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error_message", f"Failed to get info for {symbol}"),
                    "symbol": symbol
                }
        except Exception as e:
            logger.warning(f"Failed to fetch symbol info from MT4: {e}")
            return {
                "success": False,
                "error": f"Could not fetch symbol info from MT4: {str(e)}",
                "symbol": symbol,
                "note": "MT4 connection failed - ensure EA is running"
            }

    async def _get_all_symbols_info(self) -> Dict[str, Any]:
        """Get detailed specifications for all symbols directly from MT4 via ZMQ."""
        try:
            mt4_client = await self._get_mt4_client()
            result = await mt4_client.get_all_symbols_info()

            if result.get("success", False):
                symbols_info = result.get("symbols", [])

                # Categorize symbols by type for Dalio-style analysis
                categories = {
                    "commodities": [],
                    "forex": [],
                    "indices": [],
                    "stocks": [],
                    "crypto": [],
                    "other": []
                }

                for sym in symbols_info:
                    symbol_name = sym.get("symbol", "").upper()

                    # Simple categorization logic
                    if any(x in symbol_name for x in ["OIL", "GOLD", "SILVER", "GAS", "COPPER", "PLATINUM", "PALLADIUM", "WHEAT", "CORN", "COFFEE", "SUGAR", "COCOA", "BRENT", "WTI", "XAU", "XAG"]):
                        categories["commodities"].append(sym)
                    elif any(x in symbol_name for x in ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]) and len(symbol_name) <= 7:
                        categories["forex"].append(sym)
                    elif any(x in symbol_name for x in ["US500", "US30", "US100", "DAX", "FTSE", "NIKKEI", "SPX", "NDX", "DJI", "NAS", "GER", "UK100", "JP225"]):
                        categories["indices"].append(sym)
                    elif any(x in symbol_name for x in ["AAPL", "AMZN", "GOOGL", "MSFT", "TSLA", "NVDA", "META", "NFLX"]):
                        categories["stocks"].append(sym)
                    elif any(x in symbol_name for x in ["BTC", "ETH", "XRP", "LTC", "BCH", "DOGE", "CRYPTO"]):
                        categories["crypto"].append(sym)
                    else:
                        categories["other"].append(sym)

                # Sort each category by leverage (highest first)
                for cat in categories:
                    categories[cat] = sorted(
                        categories[cat],
                        key=lambda x: x.get("leverage", 0),
                        reverse=True
                    )

                return {
                    "success": True,
                    "total": len(symbols_info),
                    "symbols": symbols_info,
                    "by_category": categories,
                    "top_leverage": {
                        cat: [{"symbol": s.get("symbol"), "leverage": s.get("leverage"), "margin_pct": s.get("margin_pct")}
                              for s in syms[:5]]
                        for cat, syms in categories.items() if syms
                    },
                    "source": "MT4 (direct ZMQ connection)"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error_message", "Failed to get symbols info")
                }
        except Exception as e:
            logger.warning(f"Failed to fetch all symbols info from MT4: {e}")
            return {
                "success": False,
                "error": f"Could not fetch symbols info from MT4: {str(e)}",
                "note": "MT4 connection failed - ensure EA is running"
            }

    async def _create_backtest(
        self,
        name: str,
        symbol: str,
        start_date: str,
        end_date: str,
        strategy: str,
        timeframe: str,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """
        Create and run a backtest.
        
        This returns IMMEDIATELY after starting the backtest.
        Backtests are long-running (1-10+ minutes for large date ranges).
        Use get_backtest_results to check status and get results.
        """
        # Create config
        config_payload = {
            "name": name,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "execution_mode": "synthetic_fast",
            "initial_capital": initial_capital,
            "config_params": {
                "synthetic_strategy": strategy
            }
        }

        config = await self._api_call("POST", "/api/backtesting/configurations", json=config_payload)

        # Run backtest (API returns 202 immediately, backtest runs in background)
        run_payload = {
            "config_id": config["id"],
            "timeframe": timeframe
        }

        run = await self._api_call("POST", "/api/backtesting/runs", json=run_payload, timeout=15)
        run_id = run.get("id") or run.get("run_id")
        
        # Estimate completion time based on date range
        # Rough estimate: ~100k candles per year of M5 data, ~10s to process 100k candles
        from datetime import datetime
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00') if 'Z' in start_date else start_date)
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00') if 'Z' in end_date else end_date)
            days = (end - start).days
            estimated_candles = days * 288 if timeframe == "M5" else days * 24  # M5 = 288/day, H1 = 24/day
            estimated_seconds = max(5, estimated_candles // 10000)  # ~10k candles per second
            estimated_time = f"{estimated_seconds}s" if estimated_seconds < 60 else f"{estimated_seconds // 60}m {estimated_seconds % 60}s"
        except:
            estimated_time = "1-5 minutes (depending on date range)"

        return {
            "success": True,
            "config_id": config["id"],
            "run_id": run_id,
            "status": "running",
            "message": f"Backtest started successfully. Processing in background.",
            "estimated_time": estimated_time,
            "next_steps": [
                f"Use get_backtest_results with backtest_id='{run_id}' to check status",
                "Status will be 'running' until complete, then 'completed' or 'failed'",
                "For real-time progress, use the dashboard SSE stream at /api/backtesting/runs/{run_id}/stream"
            ]
        }

    async def _run_backtest_and_wait(
        self,
        name: str,
        symbol: str,
        start_date: str,
        end_date: str,
        strategy: str,
        timeframe: str,
        initial_capital: float = 10000,
        timeout_seconds: int = 120
    ) -> Dict[str, Any]:
        """
        Run a backtest using the FAST vectorized engine.
        
        This uses the new vectorized backtest endpoint which processes
        500K+ candles in <1 second instead of 30-60 seconds.
        
        Returns complete results immediately - no polling needed!
        """
        import time
        start_time = time.time()
        
        # Use vectorized endpoint for instant results
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": strategy,
            "strategy_params": self._get_default_strategy_params(strategy),
            "initial_capital": initial_capital,
        }
        
        try:
            # Call vectorized endpoint (returns instantly)
            result = await self._api_call(
                "POST", 
                "/api/backtesting/vectorized/run",
                json=payload,
                timeout=60  # Should complete in <5s
            )
            
            elapsed = time.time() - start_time
            
            if result.get("success"):
                return {
                    "success": True,
                    "status": "completed",
                    "run_id": result.get("run_id"),
                    "elapsed_seconds": round(elapsed, 2),
                    "execution_time_ms": result.get("execution_time_ms"),
                    "candles_processed": result.get("candles_processed"),
                    "total_trades": result.get("total_trades"),
                    "initial_capital": result.get("initial_capital"),
                    "final_capital": result.get("final_capital"),
                    "total_return_pct": result.get("total_return_pct"),
                    "metrics": {
                        "sharpe_ratio": result.get("sharpe_ratio"),
                        "sortino_ratio": result.get("sortino_ratio"),
                        "max_drawdown_pct": result.get("max_drawdown_pct"),
                        "max_drawdown_duration_days": result.get("max_drawdown_duration_days"),
                        "win_rate": result.get("win_rate"),
                        "profit_factor": result.get("profit_factor"),
                        "winning_trades": result.get("winning_trades"),
                        "losing_trades": result.get("losing_trades"),
                        "avg_trade_pnl": result.get("avg_trade_pnl"),
                    },
                    "trades": result.get("trades", [])[:10],  # First 10 trades
                    "message": f"Backtest completed in {result.get('execution_time_ms', 0):.0f}ms (vectorized engine)"
                }
            else:
                return {
                    "success": False,
                    "status": "failed",
                    "error": result.get("detail", "Unknown error"),
                    "elapsed_seconds": round(elapsed, 2),
                }
                
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            
            # If vectorized endpoint not available, fall back to legacy
            if "404" in error_msg or "Not Found" in error_msg:
                logger.warning("Vectorized endpoint not available, falling back to legacy")
                return await self._run_backtest_legacy(
                    name=name,
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    strategy=strategy,
                    timeframe=timeframe,
                    initial_capital=initial_capital,
                    timeout_seconds=timeout_seconds
                )
            
            return {
                "success": False,
                "status": "error",
                "error": error_msg,
                "elapsed_seconds": round(elapsed, 2),
            }
    
    def _get_default_strategy_params(self, strategy: str) -> Dict[str, Any]:
        """Get default parameters for a strategy."""
        defaults = {
            "ma_crossover": {"fast_period": 10, "slow_period": 30},
            "rsi": {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
            "crude_oil_v3": {
                "ema_fast": 8,
                "ema_slow": 29,
                "rsi_period": 10,
                "rsi_overbought": 68,
                "rsi_oversold": 32,
                "cci_period": 20,
                "momentum_period": 10,
            },
            "mean_reversion": {"lookback": 20, "std_threshold": 2.0},
            "value_area": {
                "lookback_periods": 24,
                "value_area_percent": 0.70,
                "tpo_resolution": 0.10,
                "stop_atr_multiplier": 1.5,
                "target_mode": "poc",
                "atr_period": 14,
            },
        }
        return defaults.get(strategy, {})
    
    async def _run_backtest_legacy(
        self,
        name: str,
        symbol: str,
        start_date: str,
        end_date: str,
        strategy: str,
        timeframe: str,
        initial_capital: float = 10000,
        timeout_seconds: int = 120
    ) -> Dict[str, Any]:
        """
        Legacy backtest using row-by-row processing (slower fallback).
        Polls until completion or timeout.
        """
        import time
        
        # Clamp timeout to reasonable bounds
        timeout_seconds = max(30, min(300, timeout_seconds))
        poll_interval = 3  # seconds between status checks
        
        # Step 1: Create the backtest
        try:
            create_result = await self._create_backtest(
                name=name,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                strategy=strategy,
                timeframe=timeframe,
                initial_capital=initial_capital
            )
            
            if not create_result.get("success"):
                return {
                    "success": False,
                    "error": "Failed to create backtest",
                    "details": create_result
                }
            
            run_id = create_result.get("run_id")
            if not run_id:
                return {
                    "success": False,
                    "error": "No run_id returned from create",
                    "details": create_result
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create backtest: {str(e)}"
            }
        
        # Step 2: Poll for completion
        start_time = time.time()
        last_status = None
        last_candles = 0
        poll_count = 0
        
        while (time.time() - start_time) < timeout_seconds:
            poll_count += 1
            
            try:
                status = await self._get_backtest_status(backtest_id=run_id)
                current_status = status.get("status", "unknown")
                candles = status.get("candles_processed", 0)
                
                # Log progress for debugging
                if candles != last_candles:
                    logger.info(f"Backtest {run_id}: {candles:,} candles processed, status={current_status}")
                    last_candles = candles
                
                # Check for completion
                if current_status == "completed":
                    # Get full results
                    try:
                        results = await self._api_call("GET", f"/api/backtesting/runs/{run_id}/metrics")
                    except:
                        results = status
                    
                    elapsed = time.time() - start_time
                    return {
                        "success": True,
                        "status": "completed",
                        "run_id": run_id,
                        "elapsed_seconds": round(elapsed, 1),
                        "poll_count": poll_count,
                        "candles_processed": status.get("candles_processed", 0),
                        "total_trades": status.get("total_trades", 0),
                        "final_capital": status.get("final_capital"),
                        "metrics": status.get("metrics") or results.get("metrics"),
                        "message": f"Backtest completed in {elapsed:.1f}s"
                    }
                
                elif current_status == "failed":
                    elapsed = time.time() - start_time
                    return {
                        "success": False,
                        "status": "failed",
                        "run_id": run_id,
                        "elapsed_seconds": round(elapsed, 1),
                        "error": status.get("error") or status.get("error_message") or "Backtest failed",
                        "candles_processed": status.get("candles_processed", 0)
                    }
                
                last_status = current_status
                
            except Exception as e:
                logger.warning(f"Poll error (continuing): {e}")
            
            # Wait before next poll
            await asyncio.sleep(poll_interval)
        
        # Timeout reached
        elapsed = time.time() - start_time
        return {
            "success": False,
            "status": "timeout",
            "run_id": run_id,
            "elapsed_seconds": round(elapsed, 1),
            "poll_count": poll_count,
            "last_status": last_status,
            "candles_processed": last_candles,
            "message": f"Backtest still running after {timeout_seconds}s timeout. Use get_backtest_status(backtest_id='{run_id}') to check progress.",
            "next_steps": [
                f"Poll status: get_backtest_status(backtest_id='{run_id}')",
                f"Get results when done: get_backtest_results(backtest_id='{run_id}')",
                f"Cancel if needed: cancel_backtest(backtest_id='{run_id}')"
            ]
        }

    async def _get_backtest_results(self, backtest_id: str) -> Dict[str, Any]:
        """Get backtest results (status + metrics if completed)."""
        return await self._api_call("GET", f"/api/backtesting/runs/{backtest_id}/status")
    
    async def _get_backtest_status(self, backtest_id: str) -> Dict[str, Any]:
        """
        Get detailed backtest status for polling.
        
        Returns current status, progress, and helpful next steps.
        """
        try:
            status = await self._api_call("GET", f"/api/backtesting/runs/{backtest_id}/status")
            
            # Calculate progress percentage if we have the data
            candles_processed = status.get("candles_processed", 0)
            progress_pct = status.get("progress_pct")
            
            result = {
                "run_id": backtest_id,
                "status": status.get("status"),
                "candles_processed": candles_processed,
                "progress_pct": progress_pct,
                "total_trades": status.get("total_trades", 0),
                "start_time": status.get("start_time"),
                "end_time": status.get("end_time"),
            }
            
            # Add status-specific info
            current_status = status.get("status", "unknown")
            if current_status == "running":
                result["message"] = f"Backtest in progress. {candles_processed:,} candles processed."
                result["next_step"] = "Poll again in a few seconds to check progress"
            elif current_status == "completed":
                result["message"] = "Backtest completed successfully!"
                result["next_step"] = f"Use get_backtest_results with backtest_id='{backtest_id}' to get full metrics"
                result["final_capital"] = status.get("final_capital")
                result["metrics"] = status.get("metrics")
            elif current_status == "failed":
                result["message"] = "Backtest failed"
                result["error"] = status.get("error_message")
            else:
                result["message"] = f"Status: {current_status}"
            
            return result
            
        except Exception as e:
            return {
                "run_id": backtest_id,
                "status": "error",
                "message": f"Failed to get status: {str(e)}"
            }

    async def _list_backtests(
        self, 
        limit: int = 20,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """List backtests with optional status filter."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        return await self._api_call("GET", "/api/backtesting/runs", params=params)

    async def _cancel_backtest(self, backtest_id: str) -> Dict[str, Any]:
        """Cancel a running backtest."""
        try:
            result = await self._api_call("DELETE", f"/api/backtesting/runs/{backtest_id}")
            return {
                "success": True,
                "backtest_id": backtest_id,
                "message": "Backtest cancelled successfully",
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "backtest_id": backtest_id,
                "error": str(e)
            }

    async def _cancel_all_backtests(self) -> Dict[str, Any]:
        """Cancel all running backtests."""
        # Get running backtests
        running = await self._list_backtests(limit=50, status="running")
        
        cancelled = []
        errors = []
        
        for run in running.get("items", []):
            run_id = run.get("id")
            if run_id:
                result = await self._cancel_backtest(run_id)
                if result.get("success"):
                    cancelled.append(run_id)
                else:
                    errors.append({"id": run_id, "error": result.get("error")})
        
        return {
            "cancelled_count": len(cancelled),
            "error_count": len(errors),
            "cancelled": cancelled,
            "errors": errors
        }

    async def _cleanup_ghost_backtests(self) -> Dict[str, Any]:
        """
        Clean up ghost backtests that are stuck at 0 candles.
        These are created by the duplicate run bug.
        """
        from datetime import datetime, timedelta, timezone
        
        # Get all running backtests
        running = await self._list_backtests(limit=100, status="running")
        
        cleaned = []
        errors = []
        now = datetime.now(timezone.utc)
        
        for run in running.get("items", []):
            run_id = run.get("id")
            candles = run.get("candles_processed", 0)
            start_time_str = run.get("start_time")
            
            # Parse start time
            if start_time_str:
                try:
                    # Handle various datetime formats
                    if start_time_str.endswith('Z'):
                        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    else:
                        start_time = datetime.fromisoformat(start_time_str)
                    
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    
                    age = now - start_time
                    
                    # If running for > 1 hour with 0 candles, it's a ghost
                    if candles == 0 and age > timedelta(hours=1):
                        result = await self._cancel_backtest(run_id)
                        if result.get("success"):
                            cleaned.append({
                                "id": run_id,
                                "age_hours": age.total_seconds() / 3600
                            })
                        else:
                            errors.append({"id": run_id, "error": result.get("error")})
                            
                except Exception as e:
                    errors.append({"id": run_id, "error": f"Date parse error: {e}"})
        
        return {
            "cleaned_count": len(cleaned),
            "error_count": len(errors),
            "cleaned": cleaned,
            "errors": errors,
            "message": f"Cleaned {len(cleaned)} ghost backtests"
        }

    async def _get_forecast(
        self,
        symbol: str,
        horizon: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get price forecast."""
        params = {"symbol": symbol}
        if horizon:
            params["horizon"] = horizon
        try:
            return await self._api_call("GET", "/api/forecasts/latest", params=params)
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg or "UndefinedColumn" in error_msg:
                return {
                    "error": "Forecast service unavailable",
                    "message": "No ML forecasts are currently available. The forecasting pipeline may not be running.",
                    "symbol": symbol,
                    "horizon": horizon
                }
            raise

    async def _list_strategies(self) -> Dict[str, Any]:
        """List available backtesting strategies from SyntheticEngine."""
        # Import SyntheticEngine to get available strategies dynamically
        try:
            from src.services.backtesting.synthetic_engine import SyntheticEngine

            # Get all strategy default params (this defines available strategies)
            strategies = []
            strategy_descriptions = {
                "crude_oil_v3": "Multi-indicator strategy with EMA, RSI, CCI, and ATR-based stops",
                "ma_crossover": "Simple moving average crossover strategy",
                "rsi": "RSI overbought/oversold mean reversion strategy",
                "trend_following": "Simple trend following with momentum",
                "mean_reversion": "Statistical mean reversion with standard deviation bands",
                "value_area": "Volume Profile / TPO based mean-reversion from VAH/VAL to POC"
            }

            for strategy_name in ["crude_oil_v3", "ma_crossover", "rsi", "trend_following", "mean_reversion", "value_area"]:
                params = SyntheticEngine._default_params(strategy_name)
                if params:  # Only include if params exist
                    # Remove quantity from display params
                    display_params = {k: v for k, v in params.items() if k != 'quantity'}
                    strategies.append({
                        "name": strategy_name,
                        "description": strategy_descriptions.get(strategy_name, ""),
                        "parameters": display_params
                    })

            return {
                "strategies": strategies,
                "total": len(strategies),
                "source": "SyntheticEngine (dynamic)"
            }
        except Exception as e:
            logger.error(f"Error listing strategies: {e}")
            return {
                "strategies": [],
                "error": str(e)
            }

    # =========================================================================
    # PENDING ORDERS IMPLEMENTATION
    # =========================================================================
    
    # In-memory storage for pending orders (would be database in production)
    _pending_orders: Dict[str, Dict[str, Any]] = {}
    _order_counter: int = 0

    async def _place_pending_order(
        self,
        symbol: str,
        order_type: str,
        entry_price: float,
        lot_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        expiration: Optional[str] = None,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a pending order via MT4 ZMQ bridge.
        
        Pending orders are sent directly to MT4 and executed when price hits entry level.
        """
        # Validate order type
        valid_types = ["BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT"]
        if order_type not in valid_types:
            return {
                "success": False,
                "error": f"Invalid order_type. Must be one of: {valid_types}"
            }
        
        try:
            # Get MT4 client
            mt4_client = await self._get_mt4_client()
            
            # Place pending order via ZMQ
            result = await mt4_client.create_pending_order(
                symbol=symbol,
                order_type=order_type,
                volume=Decimal(str(lot_size)),
                price=Decimal(str(entry_price)),
                stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                take_profit=Decimal(str(take_profit)) if take_profit else None,
                comment=comment,
                expiration=expiration
            )
            
            # Calculate risk metrics
            risk_per_lot = abs(entry_price - stop_loss) * 100 if stop_loss else None
            reward_per_lot = abs(take_profit - entry_price) * 100 if take_profit else None
            risk_reward = reward_per_lot / risk_per_lot if risk_per_lot and reward_per_lot else None
            
            # Extract ticket from response
            ticket = result.get("ticket_number")
            success = result.get("success", False) or result.get("status") == "OK"
            
            if success:
                return {
                    "success": True,
                    "ticket": ticket,
                    "order": {
                        "ticket": ticket,
                        "symbol": symbol,
                        "order_type": order_type,
                        "entry_price": entry_price,
                        "lot_size": lot_size,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "comment": comment
                    },
                    "risk_metrics": {
                        "risk_per_lot_usd": risk_per_lot,
                        "reward_per_lot_usd": reward_per_lot,
                        "risk_reward_ratio": round(risk_reward, 2) if risk_reward else None,
                        "total_risk_usd": risk_per_lot * lot_size if risk_per_lot else None
                    },
                    "message": f"Pending {order_type} order placed at {entry_price} (ticket: {ticket})"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error_message") or result.get("message") or "Failed to place pending order"
                }
                
        except Exception as e:
            logger.error(f"Error placing pending order: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_pending_orders(
        self,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all pending orders from MT4 via ZMQ, optionally filtered by symbol."""
        try:
            mt4_client = await self._get_mt4_client()
            result = await mt4_client.get_pending_orders()
            
            orders = result.get("orders", [])
            
            # Filter by symbol if specified
            if symbol:
                orders = [o for o in orders if o.get("symbol") == symbol]
            
            return {
                "success": True,
                "pending_orders": orders,
                "total": len(orders),
                "filter": {"symbol": symbol} if symbol else None
            }
            
        except Exception as e:
            logger.error(f"Error getting pending orders: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "pending_orders": [],
                "total": 0
            }

    async def _cancel_pending_order(
        self,
        order_id: str
    ) -> Dict[str, Any]:
        """Cancel a specific pending order via MT4 ZMQ (order_id is MT4 ticket number)."""
        try:
            # order_id is the MT4 ticket number
            ticket = int(order_id)
            
            mt4_client = await self._get_mt4_client()
            result = await mt4_client.delete_pending_order(ticket=ticket)
            
            success = result.get("success", False) or result.get("status") == "OK"
            
            if success:
                return {
                    "success": True,
                    "ticket": ticket,
                    "message": f"Pending order {ticket} cancelled successfully"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error_message") or result.get("message") or f"Failed to cancel order {ticket}"
                }
                
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid order_id: {order_id}. Must be a numeric MT4 ticket number."
            }
        except Exception as e:
            logger.error(f"Error cancelling pending order: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _cancel_all_pending_orders(
        self,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel all pending orders via MT4 ZMQ, optionally filtered by symbol."""
        try:
            mt4_client = await self._get_mt4_client()
            
            # First get all pending orders
            result = await mt4_client.get_pending_orders()
            orders = result.get("orders", [])
            
            # Filter by symbol if specified
            if symbol:
                orders = [o for o in orders if o.get("symbol") == symbol]
            
            # Cancel each order
            cancelled = []
            errors = []
            
            for order in orders:
                ticket = order.get("ticket")
                if ticket:
                    try:
                        cancel_result = await mt4_client.delete_pending_order(ticket=ticket)
                        if cancel_result.get("success", False) or cancel_result.get("status") == "OK":
                            cancelled.append(ticket)
                        else:
                            errors.append({"ticket": ticket, "error": cancel_result.get("message")})
                    except Exception as e:
                        errors.append({"ticket": ticket, "error": str(e)})
            
            return {
                "success": len(errors) == 0,
                "cancelled_count": len(cancelled),
                "cancelled_tickets": cancelled,
                "errors": errors if errors else None,
                "filter": {"symbol": symbol} if symbol else None
            }
            
        except Exception as e:
            logger.error(f"Error cancelling all pending orders: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "cancelled_count": 0
            }

    async def _load_pending_orders_strategy(
        self,
        strategy_file: str
    ) -> Dict[str, Any]:
        """
        Load pending orders from a strategy JSON file.
        
        Args:
            strategy_file: Filename (relative to config/pending_orders/)
        """
        import os
        
        # Construct full path
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        file_path = os.path.join(base_path, "config", "pending_orders", strategy_file)
        
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"Strategy file not found: {file_path}"
            }
        
        try:
            with open(file_path, 'r') as f:
                strategy = json.load(f)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON in strategy file: {e}"
            }
        
        # Load orders from strategy
        loaded_orders = []
        errors = []
        
        for order_def in strategy.get("pending_orders", []):
            if not order_def.get("enabled", True):
                continue
            
            try:
                result = await self._place_pending_order(
                    symbol=order_def["symbol"],
                    order_type=order_def["order_type"],
                    entry_price=order_def["entry_price"],
                    lot_size=order_def["lot_size"],
                    stop_loss=order_def.get("stop_loss"),
                    take_profit=order_def.get("take_profit"),
                    expiration=order_def.get("expiration"),
                    comment=order_def.get("notes") or order_def.get("id")
                )
                if result["success"]:
                    loaded_orders.append(result["order"])
                else:
                    errors.append({"order": order_def["id"], "error": result["error"]})
            except Exception as e:
                errors.append({"order": order_def.get("id", "unknown"), "error": str(e)})
        
        return {
            "success": len(errors) == 0,
            "strategy_name": strategy.get("strategy_name"),
            "description": strategy.get("description"),
            "loaded_count": len(loaded_orders),
            "error_count": len(errors),
            "loaded_orders": loaded_orders,
            "errors": errors if errors else None,
            "execution_playbook": strategy.get("execution_playbook"),
            "key_levels": strategy.get("key_levels"),
            "timeline": strategy.get("timeline")
        }

    async def _save_pending_orders_strategy(
        self,
        strategy_name: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save current pending orders to a strategy JSON file.
        """
        import os
        from datetime import datetime
        
        if not hasattr(self, '_pending_orders_store'):
            self._pending_orders_store = {}
        
        # Get active pending orders
        active_orders = [
            order for order in self._pending_orders_store.values()
            if order["status"] == "pending"
        ]
        
        if not active_orders:
            return {
                "success": False,
                "error": "No active pending orders to save"
            }
        
        # Create strategy structure
        strategy = {
            "strategy_name": strategy_name,
            "created_at": datetime.utcnow().isoformat(),
            "description": description or f"Strategy exported on {datetime.utcnow().strftime('%Y-%m-%d')}",
            "pending_orders": [
                {
                    "id": order["id"],
                    "order_type": order["order_type"],
                    "symbol": order["symbol"],
                    "entry_price": order["entry_price"],
                    "stop_loss": order["stop_loss"],
                    "take_profit": order["take_profit"],
                    "lot_size": order["lot_size"],
                    "notes": order.get("comment"),
                    "expiration": order.get("expiration"),
                    "enabled": True
                }
                for order in active_orders
            ]
        }
        
        # Save to file
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        file_path = os.path.join(
            base_path, "config", "pending_orders",
            f"{strategy_name.lower().replace(' ', '_')}.json"
        )
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(strategy, f, indent=2)
        
        return {
            "success": True,
            "file_path": file_path,
            "strategy_name": strategy_name,
            "orders_saved": len(active_orders),
            "message": f"Strategy saved to {file_path}"
        }

    # =========================================================================
    # INSTITUTIONAL STOP-HUNTING AVOIDANCE METHODS
    # =========================================================================

    async def _modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Modify stop loss and/or take profit of an open position.
        
        Uses direct MT4 ZMQ connection for immediate execution.
        """
        try:
            mt4_client = await self._get_mt4_client()
            
            result = await mt4_client.modify_position(
                ticket=ticket,
                stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                take_profit=Decimal(str(take_profit)) if take_profit else None
            )
            
            return {
                "success": result.get("success", False) or result.get("status") == "OK",
                "ticket": ticket,
                "new_stop_loss": stop_loss,
                "new_take_profit": take_profit,
                "message": result.get("message", "Position modified successfully")
            }
            
        except Exception as e:
            logger.error(f"Error modifying position {ticket}: {e}", exc_info=True)
            return {
                "success": False,
                "ticket": ticket,
                "error": str(e)
            }

    async def _calculate_institutional_stop(
        self,
        entry_price: float,
        direction: str,
        atr_value: float,
        atr_multiplier: float = 2.0,
        structure_level: Optional[float] = None,
        min_offset_pips: float = 5,
        max_offset_pips: float = 15
    ) -> Dict[str, Any]:
        """
        Calculate an institutional-grade stop loss using ATR with random offset.
        
        This avoids obvious liquidity clusters by:
        1. Using ATR-based distance (not fixed pips)
        2. Adding random offset to avoid round numbers
        3. Positioning beyond key structure levels
        
        Returns a 'weird' price like $56.37 instead of $56.50.
        """
        import random
        
        # Calculate base stop distance using ATR
        base_stop_distance = atr_value * atr_multiplier
        
        # Generate random offset (converted from pips to price)
        # For crude oil, 1 pip = 0.01, for forex majors 1 pip = 0.0001
        pip_value = 0.01  # Crude oil pip value
        random_offset = random.uniform(min_offset_pips, max_offset_pips) * pip_value
        
        # Calculate initial stop price
        if direction.lower() == "long":
            # For long: stop below entry
            initial_stop = entry_price - base_stop_distance
            # Add random offset (push stop further away from obvious level)
            stop_price = initial_stop - random_offset
            
            # If structure level provided, ensure stop is below it
            if structure_level and stop_price > structure_level:
                stop_price = structure_level - random_offset
                
        else:  # short
            # For short: stop above entry
            initial_stop = entry_price + base_stop_distance
            # Add random offset (push stop further away from obvious level)
            stop_price = initial_stop + random_offset
            
            # If structure level provided, ensure stop is above it
            if structure_level and stop_price < structure_level:
                stop_price = structure_level + random_offset
        
        # Round to 2 decimal places (appropriate for crude oil)
        stop_price = round(stop_price, 2)
        
        # Calculate actual stop distance in price and pips
        actual_distance = abs(entry_price - stop_price)
        actual_distance_pips = actual_distance / pip_value
        
        # Determine if price looks "institutional" (not at obvious level)
        is_institutional = not (
            stop_price == round(stop_price) or  # Not a round number
            (stop_price * 10) % 5 == 0  # Not at .X0 or .X5 level
        )
        
        return {
            "success": True,
            "stop_price": stop_price,
            "entry_price": entry_price,
            "direction": direction,
            "stop_distance_price": round(actual_distance, 2),
            "stop_distance_pips": round(actual_distance_pips, 1),
            "atr_value": atr_value,
            "atr_multiplier": atr_multiplier,
            "random_offset_applied": round(random_offset, 3),
            "structure_level_used": structure_level,
            "is_institutional_level": is_institutional,
            "reasoning": f"ATR-based stop ({atr_multiplier}x ATR = {round(base_stop_distance, 2)}) with {round(random_offset / pip_value, 1)} pip random offset to avoid obvious liquidity clusters"
        }

    # =========================================================================
    # STRATEGY OPTIMIZER METHODS
    # =========================================================================

    async def _optimize_strategy(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        optimization_target: str = "sharpe_ratio",
        max_combinations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """
        Run strategy optimization via API.
        
        Tests parameter combinations and returns best parameters.
        """
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "optimization_target": optimization_target,
                "max_combinations": max_combinations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/run",
                json=payload,
                timeout=300  # 5 minutes for optimization
            )
            
            return {
                "success": result.get("success", True),
                "optimization_id": result.get("optimization_id"),
                "strategy": strategy,
                "symbol": symbol,
                "timeframe": timeframe,
                "optimization_target": optimization_target,
                "total_combinations": result.get("total_combinations"),
                "combinations_tested": result.get("combinations_tested"),
                "best_params": result.get("best_params"),
                "best_return_pct": result.get("best_return_pct"),
                "best_sharpe": result.get("best_sharpe"),
                "best_profit_factor": result.get("best_profit_factor"),
                "total_time_seconds": result.get("total_time_seconds"),
                "top_results": result.get("top_results", [])[:5],
                "message": f"Optimization complete. Best return: {result.get('best_return_pct', 0):.2f}%, Best Sharpe: {result.get('best_sharpe', 0):.2f}"
            }
            
        except Exception as e:
            logger.error(f"Optimization failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_strategy_param_grid(
        self,
        strategy: str
    ) -> Dict[str, Any]:
        """
        Get the default parameter grid for a strategy.
        """
        try:
            result = await self._api_call(
                "GET",
                f"/api/optimizer/param-grids/{strategy}"
            )
            return result
            
        except Exception as e:
            # Return defaults if API not available
            grids = {
                "ma_crossover": {
                    "fast_period": [5, 8, 10, 12, 15],
                    "slow_period": [20, 25, 30, 35, 40, 50],
                },
                "rsi": {
                    "rsi_period": [7, 10, 14, 21],
                    "rsi_oversold": [20, 25, 30, 35],
                    "rsi_overbought": [65, 70, 75, 80],
                },
                "crude_oil_v3": {
                    "ema_fast": [5, 8, 10, 12, 15],
                    "ema_slow": [20, 25, 29, 35, 40],
                    "rsi_period": [7, 10, 14],
                    "rsi_oversold": [25, 30, 32, 35, 40],
                    "rsi_overbought": [60, 65, 68, 70, 75],
                    "cci_period": [14, 20, 25],
                    "cci_oversold": [-100, -80, -60],
                    "cci_overbought": [80, 100, 120],
                    "use_time_filter": [True, False],
                    "trade_start_hour": [8],
                    "trade_end_hour": [20],
                },
                "mean_reversion": {
                    "lookback": [10, 15, 20, 25, 30],
                    "std_threshold": [1.5, 2.0, 2.5, 3.0],
                },
            }
            
            if strategy not in grids:
                return {
                    "error": f"Unknown strategy: {strategy}",
                    "available_strategies": list(grids.keys())
                }
            
            grid = grids[strategy]
            total_combinations = 1
            for values in grid.values():
                total_combinations *= len(values)
            
            return {
                "strategy": strategy,
                "param_grid": grid,
                "total_combinations": total_combinations,
                "note": "Returns from local defaults (API not available)"
            }


    async def _rolling_window_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        optimization_target: str = "sharpe_ratio",
        train_months: int = 3,
        test_months: int = 1,
        step_months: int = 1,
        max_combinations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run rolling window optimization via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "optimization_target": optimization_target,
                "train_months": train_months,
                "test_months": test_months,
                "step_months": step_months,
                "max_combinations": max_combinations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/rolling-window",
                json=payload,
                timeout=600  # 10 minutes for rolling window
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Rolling window optimization failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _time_interval_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        intervals: List[Dict[str, str]],
        optimization_target: str = "sharpe_ratio",
        max_combinations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run time-interval specific optimization via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "intervals": intervals,
                "optimization_target": optimization_target,
                "max_combinations": max_combinations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/time-intervals",
                json=payload,
                timeout=600
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Time interval optimization failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _sensitivity_analysis(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        base_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run sensitivity analysis via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "initial_capital": initial_capital,
            }
            if base_params:
                payload["base_params"] = base_params
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/sensitivity",
                json=payload,
                timeout=600
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Sensitivity analysis failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _monte_carlo_validate(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        params: Dict[str, Any],
        num_simulations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run Monte Carlo validation via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "params": params,
                "num_simulations": num_simulations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/monte-carlo",
                json=payload,
                timeout=300
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Monte Carlo validation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


    async def _rolling_window_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        optimization_target: str = "sharpe_ratio",
        train_months: int = 3,
        test_months: int = 1,
        step_months: int = 1,
        max_combinations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run rolling window optimization via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "optimization_target": optimization_target,
                "train_months": train_months,
                "test_months": test_months,
                "step_months": step_months,
                "max_combinations": max_combinations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/rolling-window",
                json=payload,
                timeout=600  # 10 minutes for rolling window
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Rolling window optimization failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _time_interval_optimize(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        intervals: List[Dict[str, str]],
        optimization_target: str = "sharpe_ratio",
        max_combinations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run time-interval specific optimization via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "intervals": intervals,
                "optimization_target": optimization_target,
                "max_combinations": max_combinations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/time-intervals",
                json=payload,
                timeout=600
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Time interval optimization failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _sensitivity_analysis(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        base_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run sensitivity analysis via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "initial_capital": initial_capital,
            }
            if base_params:
                payload["base_params"] = base_params
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/sensitivity",
                json=payload,
                timeout=600
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Sensitivity analysis failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _monte_carlo_validate(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        params: Dict[str, Any],
        num_simulations: int = 100,
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Run Monte Carlo validation via API."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "params": params,
                "num_simulations": num_simulations,
                "initial_capital": initial_capital,
            }
            
            result = await self._api_call(
                "POST",
                "/api/optimizer/monte-carlo",
                json=payload,
                timeout=300
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Monte Carlo validation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Async Optimization Job Tools
    # =========================================================================

    async def _submit_optimization_job(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy: str,
        param_grid: Dict[str, Any],
        optimization_target: str = "sharpe_ratio",
        initial_capital: float = 10000
    ) -> Dict[str, Any]:
        """Submit an async optimization job. Returns immediately with job_id."""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": strategy,
                "param_grid": param_grid,
                "optimization_target": optimization_target,
                "initial_capital": initial_capital,
            }
            result = await self._api_call(
                "POST",
                "/api/optimizer/jobs",
                json=payload,
                timeout=30  # Should return immediately
            )
            return {
                "success": True,
                "job_id": result.get("job_id"),
                "status": result.get("status", "submitted"),
                "message": f"Optimization job submitted. Use get_optimization_job_status with job_id='{result.get('job_id')}' to check progress."
            }
        except Exception as e:
            logger.error(f"Submit optimization job failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_optimization_job_status(
        self,
        job_id: str
    ) -> Dict[str, Any]:
        """Get the current status and progress of an optimization job."""
        try:
            result = await self._api_call(
                "GET",
                f"/api/optimizer/jobs/{job_id}",
                timeout=15
            )
            return result
        except Exception as e:
            logger.error(f"Get job status failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _cancel_optimization_job(
        self,
        job_id: str
    ) -> Dict[str, Any]:
        """Cancel a running optimization job."""
        try:
            result = await self._api_call(
                "DELETE",
                f"/api/optimizer/jobs/{job_id}",
                timeout=15
            )
            return result
        except Exception as e:
            logger.error(f"Cancel job failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _list_optimization_jobs(
        self,
        status_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all active optimization jobs with their status."""
        try:
            params = {}
            if status_filter:
                params["status_filter"] = status_filter
            result = await self._api_call(
                "GET",
                "/api/optimizer/jobs",
                params=params,
                timeout=15
            )
            return result
        except Exception as e:
            logger.error(f"List jobs failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_optimization_job_results(
        self,
        job_id: str
    ) -> Dict[str, Any]:
        """Get full results for a completed optimization job."""
        try:
            result = await self._api_call(
                "GET",
                f"/api/optimizer/jobs/{job_id}/results",
                timeout=30
            )
            return result
        except Exception as e:
            logger.error(f"Get job results failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Price Alert MCP Tools (T062)
    # =========================================================================

    async def _set_price_alerts(
        self,
        ticket: int,
        alerts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Set multiple price alerts for a position.

        Args:
            ticket: MT4 position ticket number
            alerts: List of alert configurations, each with:
                - alert_type: liquidity_sweep, breakeven, key_level, custom
                - price_level: Price level to monitor
                - direction: above or below
                - metadata: Optional additional data

        Returns:
            Created alerts with IDs
        """
        try:
            result = await self._api_call(
                "POST",
                "/api/alerts/batch",
                json={
                    "ticket": ticket,
                    "alerts": alerts
                },
                timeout=15
            )

            return {
                "success": True,
                "ticket": ticket,
                "alerts_created": result.get("total", 0),
                "alerts": result.get("alerts", []),
            }

        except Exception as e:
            logger.error(f"Set price alerts failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_position_alerts(
        self,
        ticket: int
    ) -> Dict[str, Any]:
        """
        Get all active alerts for a position.

        Args:
            ticket: MT4 position ticket number

        Returns:
            List of alerts for the position
        """
        try:
            result = await self._api_call(
                "GET",
                f"/api/alerts/position/{ticket}",
                timeout=10
            )

            return {
                "success": True,
                "ticket": ticket,
                "alerts": result.get("alerts", []),
                "total": result.get("total", 0),
            }

        except Exception as e:
            logger.error(f"Get position alerts failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _clear_position_alerts(
        self,
        ticket: int
    ) -> Dict[str, Any]:
        """
        Clear all alerts for a position (e.g., when position is closed).

        Args:
            ticket: MT4 position ticket number

        Returns:
            Number of alerts deleted
        """
        try:
            result = await self._api_call(
                "DELETE",
                f"/api/alerts/position/{ticket}",
                timeout=10
            )

            return {
                "success": True,
                "ticket": ticket,
                "deleted": result.get("deleted", 0),
            }

        except Exception as e:
            logger.error(f"Clear position alerts failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # =========================================================================
    # ML Pipeline Tools
    # =========================================================================

    async def _compute_indicators(
        self,
        symbols: List[str],
        timeframes: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Compute technical indicators for symbols and store in DB."""
        timeframes = timeframes or ["H1"]
        try:
            from src.database.config import initialize_database, get_database
            from src.services.indicator_compute_service import IndicatorComputeService

            initialize_database()
            db = get_database()

            async with db.get_session() as session:
                service = IndicatorComputeService(session)
                results = await service.compute_batch(symbols, timeframes, force=force)

            return {
                "success": True,
                "results": results,
                "total_symbols": len(symbols),
                "total_timeframes": len(timeframes),
            }
        except Exception as e:
            logger.error(f"Compute indicators failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _train_reversal_models(
        self,
        symbol: str,
        timeframe: str = "H1",
        skip_indicators: bool = False,
        skip_labels: bool = False,
        model_configs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run full ML training pipeline for a symbol."""
        try:
            from src.database.config import initialize_database, get_database
            from src.services.reversal_training_service import (
                ReversalTrainingService,
                DEFAULT_MODEL_CONFIGS,
            )

            initialize_database()
            db = get_database()

            # Filter configs by name if specified
            active_configs = DEFAULT_MODEL_CONFIGS
            if model_configs:
                active_configs = [c for c in DEFAULT_MODEL_CONFIGS if c["name"] in model_configs]
                if not active_configs:
                    return {"success": False, "error": f"No matching configs: {model_configs}"}

            async with db.get_session() as session:
                service = ReversalTrainingService(session)
                result = await service.train_pipeline(
                    symbol=symbol,
                    timeframe=timeframe,
                    skip_indicators=skip_indicators,
                    skip_labels=skip_labels,
                    model_configs=active_configs,
                )

            return {"success": True, **result}

        except Exception as e:
            logger.error(f"Train reversal models failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _run_ml_backtest(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = "H1",
        model_type: str = "xgboost",
        min_confidence: float = 0.55,
        initial_capital: float = 10000,
    ) -> Dict[str, Any]:
        """Backtest ML model predictions for P&L evaluation."""
        # Delegate to existing backtest infrastructure with ml_reversal strategy
        strategy_params = {
            "symbol": symbol,
            "timeframe": timeframe,
            "model_type": model_type,
            "min_confidence": min_confidence,
        }

        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": "ml_reversal",
            "strategy_params": strategy_params,
            "initial_capital": initial_capital,
        }

        try:
            import time as _time
            start_time = _time.time()

            result = await self._api_call(
                "POST",
                "/api/backtesting/vectorized/run",
                json=payload,
                timeout=120,
            )

            elapsed = _time.time() - start_time

            if result.get("success"):
                return {
                    "success": True,
                    "status": "completed",
                    "strategy": "ml_reversal",
                    "model_type": model_type,
                    "min_confidence": min_confidence,
                    "elapsed_seconds": round(elapsed, 2),
                    "execution_time_ms": result.get("execution_time_ms"),
                    "candles_processed": result.get("candles_processed"),
                    "total_trades": result.get("total_trades"),
                    "initial_capital": result.get("initial_capital"),
                    "final_capital": result.get("final_capital"),
                    "total_return_pct": result.get("total_return_pct"),
                    "metrics": {
                        "sharpe_ratio": result.get("sharpe_ratio"),
                        "sortino_ratio": result.get("sortino_ratio"),
                        "max_drawdown_pct": result.get("max_drawdown_pct"),
                        "win_rate": result.get("win_rate"),
                        "profit_factor": result.get("profit_factor"),
                        "winning_trades": result.get("winning_trades"),
                        "losing_trades": result.get("losing_trades"),
                        "avg_trade_pnl": result.get("avg_trade_pnl"),
                    },
                    "trades": result.get("trades", [])[:10],
                    "message": f"ML backtest completed in {result.get('execution_time_ms', 0):.0f}ms",
                }
            else:
                return {
                    "success": False,
                    "status": "failed",
                    "error": result.get("detail", "Unknown error"),
                    "elapsed_seconds": round(elapsed, 2),
                }

        except Exception as e:
            logger.error(f"ML backtest failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # =========================================================================
    # INFORMED FLOW DETECTION METHODS
    # =========================================================================

    async def _detect_informed_flow(self, symbol: str) -> Dict[str, Any]:
        """Run all informed-flow detectors for the given symbol and return a composite status.

        Args:
            symbol: MT4 symbol string (e.g. 'CrudeOIL').

        Returns:
            Dict with keys:
                symbol (str), timestamp (str ISO-8601 UTC),
                overall_confidence (float 0.0-1.0),
                has_price_velocity (bool), has_tick_cluster (bool),
                has_cross_asset_signal (bool), has_news_catalyst (bool),
                recommendation (str: 'BUY'|'SELL'|'HOLD'),
                alerts (list of dicts, one per firing detector),
                cross_asset_correlations (dict 'SYM1/SYM2' -> float).
            On error: {"success": False, "error": str}.
        """
        try:
            # Lazy imports to avoid circular dependencies at module load time.
            from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector  # noqa: PLC0415
            from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector  # noqa: PLC0415
            from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor  # noqa: PLC0415
            from src.services.news.news_feed_service import NewsFeedService  # noqa: PLC0415
            from src.services.informed_flow.schemas import InformedFlowStatus  # noqa: PLC0415
            from datetime import datetime, timezone  # noqa: PLC0415

            velocity_detector = PriceVelocityDetector()
            tick_detector = TickClusteringDetector()
            cross_monitor = CrossAssetMonitor()
            news_service = NewsFeedService()

            # --- Run detectors concurrently ---
            velocity_alert, tick_result, cross_alerts, has_catalyst = await asyncio.gather(
                velocity_detector.detect_from_db(symbol, timeframe="M1", limit=120),
                tick_detector.analyze_from_db(symbol, timeframe="M1", limit=120),
                cross_monitor.check_all_pairs(),
                news_service.has_catalyst(symbol, window_minutes=30),
                return_exceptions=True,
            )

            # Treat exceptions from individual detectors as non-firing (degrade gracefully).
            if isinstance(velocity_alert, Exception):
                logger.warning(f"velocity detector failed: {velocity_alert}")
                velocity_alert = None
            if isinstance(tick_result, Exception):
                logger.warning(f"tick detector failed: {tick_result}")
                tick_result = None
            if isinstance(cross_alerts, Exception):
                logger.warning(f"cross asset monitor failed: {cross_alerts}")
                cross_alerts = []
            if isinstance(has_catalyst, Exception):
                logger.warning(f"news feed failed: {has_catalyst}")
                has_catalyst = False

            # --- Assemble composite status ---
            firing_alerts = []
            confidences = []

            if velocity_alert is not None:
                firing_alerts.append({
                    "detector": "price_velocity",
                    "alert_type": velocity_alert.alert_type,
                    "confidence": velocity_alert.confidence,
                    "direction": velocity_alert.direction,
                    "price_change_pct": velocity_alert.price_change_pct,
                    "z_score": velocity_alert.z_score,
                    "details": velocity_alert.details,
                    "timestamp": velocity_alert.timestamp.isoformat(),
                })
                confidences.append(velocity_alert.confidence)

            has_tick_cluster = tick_result is not None and tick_result.is_anomaly
            if has_tick_cluster:
                confidences.append(tick_result.confidence)
                firing_alerts.append({
                    "detector": "tick_cluster",
                    "alert_type": "tick_cluster",
                    "confidence": tick_result.confidence,
                    "direction": tick_result.price_direction,
                    "tick_z_score": tick_result.tick_z_score,
                    "tick_count": tick_result.tick_count,
                    "baseline_mean": tick_result.baseline_mean,
                })

            # Cross-asset: flag if any pair exceeded its threshold.
            has_cross_asset = any(a.threshold_exceeded for a in (cross_alerts or []))
            cross_corr_summary = cross_monitor.summarise_alerts(cross_alerts or [])

            # --- Overall confidence: mean of firing detector confidences ---
            if confidences:
                overall_confidence = round(sum(confidences) / len(confidences), 4)
            else:
                overall_confidence = 0.0

            # --- Recommendation: follow the highest-confidence velocity direction ---
            recommendation = "HOLD"
            if velocity_alert is not None and velocity_alert.confidence >= 0.6:
                recommendation = "BUY" if velocity_alert.direction == "up" else "SELL"
            elif has_tick_cluster and tick_result.confidence >= 0.6:
                recommendation = "BUY" if tick_result.price_direction == "up" else "SELL"

            return {
                "success": True,
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_confidence": overall_confidence,
                "has_price_velocity": velocity_alert is not None,
                "has_tick_cluster": has_tick_cluster,
                "has_cross_asset_signal": has_cross_asset,
                "has_news_catalyst": bool(has_catalyst),
                "recommendation": recommendation,
                "alerts": firing_alerts,
                "cross_asset_correlations": cross_corr_summary,
            }

        except Exception as e:
            logger.error(f"detect_informed_flow failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_trump_posts(self, hours_back: int = 24) -> Dict[str, Any]:
        """Return recent market-relevant posts from TruthSocialMonitor.

        Args:
            hours_back: Look-back window in hours. Range: [0, ∞). Default 24.

        Returns:
            Dict with keys:
                posts (list of dicts), count (int), hours_back (int),
                enabled (bool — False when TRUTH_SOCIAL_ENABLED != 'true').
            Each post dict has: post_text, timestamp (ISO-8601), sentiment,
                keywords_found (list), confidence (float 0.0-1.0).
        """
        try:
            # Lazy import to avoid circular dependencies at module load time.
            from src.services.social.truth_social_monitor import TruthSocialMonitor  # noqa: PLC0415

            monitor = TruthSocialMonitor()
            posts = monitor.get_recent_posts(hours_back=hours_back)

            serialized = [
                {
                    "post_text": p.post_text,
                    "timestamp": p.timestamp.isoformat(),
                    "sentiment": p.sentiment,
                    "keywords_found": p.keywords_found,
                    "confidence": p.confidence,
                }
                for p in posts
            ]

            return {
                "success": True,
                "enabled": monitor.enabled,
                "hours_back": hours_back,
                "count": len(serialized),
                "posts": serialized,
            }

        except Exception as e:
            logger.error(f"get_trump_posts failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _check_news_catalyst(
        self,
        symbol: str,
        minutes_back: int = 30,
    ) -> Dict[str, Any]:
        """Check whether a recent news catalyst exists for the symbol.

        Args:
            symbol: MT4 symbol string (e.g. 'CrudeOIL').
            minutes_back: Look-back window in minutes. Range: [1, ∞). Default 30.

        Returns:
            Dict with keys:
                has_catalyst (bool), article_count (int), symbol (str),
                minutes_back (int), articles (list of dicts).
            Each article dict has: headline, source, published_at (ISO-8601),
                relevance_score (float), url (str).
            On error: {"success": False, "error": str}.
        """
        try:
            # Lazy import to avoid circular dependencies at module load time.
            from src.services.news.news_feed_service import NewsFeedService  # noqa: PLC0415

            service = NewsFeedService()
            articles = await service.get_recent_news(
                symbols=[symbol],
                lookback_minutes=minutes_back,
            )

            serialized = [
                {
                    "headline": a.headline,
                    "source": a.source,
                    "published_at": a.published_at.isoformat(),
                    "relevance_score": a.relevance_score,
                    "url": a.url,
                }
                for a in articles
            ]

            return {
                "success": True,
                "symbol": symbol,
                "minutes_back": minutes_back,
                "has_catalyst": len(articles) > 0,
                "article_count": len(articles),
                "articles": serialized,
            }

        except Exception as e:
            logger.error(f"check_news_catalyst failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def run(self):
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


async def main():
    """Main entry point."""
    import os
    
    # API URL for RiseTrader backend
    api_url = os.getenv("RISETRADER_API_URL", "http://host.docker.internal:8003")
    
    # MT4 ZMQ connection settings
    mt4_host = os.getenv("MT4_HOST", "host.docker.internal")
    mt4_port = int(os.getenv("MT4_PORT", "5555"))
    
    logger.info(f"Connecting to API at: {api_url}")
    logger.info(f"Connecting to MT4 at: {mt4_host}:{mt4_port}")
    
    server = RiseTraderMCP(
        api_base_url=api_url,
        mt4_host=mt4_host,
        mt4_port=mt4_port
    )
    await server.run()


def main_sync():
    """Synchronous entry point for CLI."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
