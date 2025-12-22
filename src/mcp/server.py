"""
RiseTrader MCP Server

Exposes comprehensive trading platform capabilities to Claude and other LLMs
via the Model Context Protocol (MCP).

This server provides tools for:
- Live trading (place/close orders)
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
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("risetrader-mcp")


class RiseTraderMCP:
    """MCP Server for RiseTrader platform."""

    def __init__(self, api_base_url: str = "http://localhost:8003"):
        """
        Initialize MCP server.

        Args:
            api_base_url: Base URL for RiseTrader API
        """
        self.api_base_url = api_base_url
        self.server = Server("risetrader")

        # Register all tool handlers
        self._register_tools()

        logger.info(f"RiseTrader MCP Server initialized (API: {api_base_url})")

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
                    description="Get all open trading positions",
                    inputSchema={
                        "type": "object",
                        "properties": {}
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
                    description="Create and run a new backtest",
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
                    name="list_backtests",
                    description="List all backtests",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of backtests to return (default 20)",
                                "default": 20
                            }
                        }
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
                    result = await self._get_open_positions()
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
                elif name == "list_backtests":
                    result = await self._list_backtests(**arguments)
                elif name == "get_forecast":
                    result = await self._get_forecast(**arguments)
                elif name == "list_strategies":
                    result = await self._list_strategies()
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

    async def _api_call(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API call to RiseTrader backend."""
        import aiohttp

        url = f"{self.api_base_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
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
        # Get all open positions
        positions = await self._get_open_positions()

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

    async def _get_open_positions(self) -> Dict[str, Any]:
        """Get all open positions."""
        return await self._api_call("GET", "/api/trading/positions")

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
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit
        }
        return await self._api_call("GET", "/api/market-data/candles", params=params)

    async def _get_symbols(self) -> Dict[str, Any]:
        """Get available symbols."""
        return await self._api_call("GET", "/api/market-data/symbols")

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
        """Create and run a backtest."""
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

        # Run backtest
        run_payload = {
            "config_id": config["id"],
            "timeframe": timeframe
        }

        run = await self._api_call("POST", "/api/backtesting/runs", json=run_payload)

        return {
            "config_id": config["id"],
            "run_id": run["run_id"],
            "status": "running",
            "message": "Backtest started successfully"
        }

    async def _get_backtest_results(self, backtest_id: str) -> Dict[str, Any]:
        """Get backtest results."""
        return await self._api_call("GET", f"/api/backtesting/runs/{backtest_id}/status")

    async def _list_backtests(self, limit: int = 20) -> Dict[str, Any]:
        """List backtests."""
        params = {"limit": limit}
        return await self._api_call("GET", "/api/backtesting/runs", params=params)

    async def _get_forecast(
        self,
        symbol: str,
        horizon: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get price forecast."""
        params = {"symbol": symbol}
        if horizon:
            params["horizon"] = horizon
        return await self._api_call("GET", "/api/forecasts/latest", params=params)

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
    # Use host.docker.internal to reach the host machine from inside Docker
    import os
    api_url = os.getenv("RISETRADER_API_URL", "http://host.docker.internal:8003")
    logger.info(f"Connecting to API at: {api_url}")
    server = RiseTraderMCP(api_base_url=api_url)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
