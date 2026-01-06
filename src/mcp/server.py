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
                timeout_ms=10000,
                enable_circuit_breaker=False
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
        """Place a market order."""
        payload = {
            "symbol": symbol,
            "order_type": "market",
            "side": side,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }

        return await self._api_call("POST", "/api/trading/orders", json=payload)

    async def _close_position(self, position_id: int) -> Dict[str, Any]:
        """Close a position."""
        return await self._api_call("POST", f"/api/trading/positions/{position_id}/close")

    async def _close_all_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Close all positions (optionally filtered by symbol)."""
        # Get all open positions (live only)
        positions = await self._get_open_positions(live_only=True, limit=100)

        closed = []
        errors = []

        for pos in positions.get("positions", []):
            if symbol and pos["symbol"] != symbol:
                continue

            try:
                result = await self._close_position(pos["id"])
                closed.append(result)
            except Exception as e:
                errors.append({"position_id": pos["id"], "error": str(e)})

        return {
            "closed_count": len(closed),
            "error_count": len(errors),
            "closed": closed,
            "errors": errors
        }

    async def _get_open_positions(
        self,
        symbol: Optional[str] = None,
        live_only: bool = True,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get open positions with filtering."""
        # Build query params
        params = {"page_size": limit}
        if symbol:
            params["symbol"] = symbol
        
        # Get positions from API
        result = await self._api_call("GET", "/api/trading/positions", params=params)
        
        positions = result.get("positions", [])
        
        # Filter out simulated positions if live_only
        if live_only:
            positions = [p for p in positions if not p.get("simulation", False)]
        
        # Apply limit after filtering
        positions = positions[:limit]
        
        return {
            "positions": positions,
            "total": len(positions),
            "live_only": live_only,
            "limit": limit
        }

    async def _get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        return await self._api_call("GET", "/api/trading/account")

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
        """Get available symbols (lightweight list only)."""
        # Return known symbols to avoid heavy API call
        # The API endpoint /api/market-data/symbols may return too much data
        return {
            "symbols": [
                {"symbol": "CrudeOIL", "description": "WTI Crude Oil"},
                {"symbol": "XAUUSD", "description": "Gold vs USD"},
                {"symbol": "EURUSD", "description": "Euro vs USD"},
                {"symbol": "GBPUSD", "description": "British Pound vs USD"},
                {"symbol": "USDJPY", "description": "USD vs Japanese Yen"},
            ],
            "note": "For full symbol list with metadata, use the dashboard or API directly"
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
        """List available strategies."""
        # This would ideally come from the API, but for now return hardcoded list
        return {
            "strategies": [
                {
                    "name": "crude_oil_v3",
                    "description": "Multi-indicator strategy with EMA, RSI, CCI, and ATR-based stops",
                    "parameters": {
                        "ema_fast": 8,
                        "ema_slow": 29,
                        "rsi_period": 10,
                        "rsi_overbought": 68,
                        "rsi_oversold": 32,
                        "cci_period": 20,
                        "atr_period": 10
                    }
                },
                {
                    "name": "ma_crossover",
                    "description": "Simple moving average crossover strategy",
                    "parameters": {
                        "fast_period": 10,
                        "slow_period": 20
                    }
                }
            ]
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
