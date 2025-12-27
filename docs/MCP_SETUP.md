# RiseTrader MCP Server Setup Guide

## Overview

The RiseTrader MCP (Model Context Protocol) server exposes comprehensive trading platform capabilities to Claude and other LLMs. This enables natural language interaction with live trading, backtesting, market data, and ML forecasting.

## Quick Start

### 1. Install MCP Package (Already Done)

The MCP server is already installed in the RiseTrader API container with all dependencies resolved.

### 2. Configure Claude Desktop

Add the following configuration to your Claude Desktop MCP settings file:

**Location:** `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
  "mcpServers": {
    "risetrader": {
      "command": "/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/scripts/launch_mcp_server.sh",
      "args": []
    }
  }
}
```

**Note:** The MCP server uses a launcher script (`scripts/launch_mcp_server.sh`) that runs the server inside the Docker container. This ensures all dependencies (MCP package, RiseTrader code) are available.

### 3. Restart Claude Desktop

After adding the configuration, restart Claude Desktop for the MCP server to be recognized.

### 4. Verify Connection

In Claude Desktop, you should see the "risetrader" MCP server available. You can test it by asking Claude:

```
"Show me my current trading account balance"
```

Claude will use the `get_account_info` tool to fetch your MT4 account details.

## Available Tools

The RiseTrader MCP server provides 12 tools organized into 5 categories:

### Live Trading (5 tools)

1. **place_market_order**
   - Place market orders with optional stop loss and take profit
   - Parameters: symbol, side (buy/sell), quantity, stop_loss (optional), take_profit (optional)
   - Example: "Buy 0.01 lots of CrudeOIL with stop loss at 68.00"

2. **close_position**
   - Close a specific open position by ID
   - Parameters: position_id
   - Example: "Close position #1779"

3. **close_all_positions**
   - Emergency close all open positions (optionally filtered by symbol)
   - Parameters: symbol (optional)
   - Example: "Close all CrudeOIL positions"

4. **get_open_positions**
   - List all currently open trading positions
   - No parameters required
   - Example: "What positions do I have open?"

5. **get_account_info**
   - Get trading account information (balance, equity, margin, P&L)
   - No parameters required
   - Example: "Show my account balance"

### Market Data (2 tools)

6. **get_latest_candles**
   - Fetch recent OHLCV candle data for technical analysis
   - Parameters: symbol, timeframe (M1/M5/M15/H1/H4/D1), limit (default 100)
   - Example: "Get the last 50 H1 candles for CrudeOIL"

7. **get_symbols**
   - List all available trading symbols
   - No parameters required
   - Example: "What symbols can I trade?"

### Backtesting (3 tools)

8. **create_backtest**
   - Create and run a new backtest
   - Parameters: name, symbol, start_date, end_date, strategy, timeframe, initial_capital (default 10000)
   - Example: "Run a backtest on CrudeOIL using crude_oil_v3 strategy from 2024-01-01 to 2024-12-31 on H1 timeframe"

9. **get_backtest_results**
   - Retrieve backtest results and performance metrics
   - Parameters: backtest_id (run ID)
   - Example: "Show me results for backtest abc123"

10. **list_backtests**
    - List all backtests (sorted by most recent)
    - Parameters: limit (default 20)
    - Example: "Show my last 10 backtests"

### ML/Forecasting (1 tool)

11. **get_forecast**
    - Get ML price forecast for a symbol
    - Parameters: symbol, horizon (optional, e.g., '1H', '4H', '1D')
    - Example: "What's the forecast for CrudeOIL over the next 4 hours?"

### Strategy Management (1 tool)

12. **list_strategies**
    - List available trading strategies with their parameters
    - No parameters required
    - Example: "What trading strategies are available?"

## Architecture

```
Claude Desktop
    ↓ (stdio)
RiseTrader MCP Server (src/mcp/server.py)
    ↓ (HTTP/REST)
RiseTrader FastAPI Backend (localhost:8003)
    ↓ (ZMQ)
MetaTrader 4
```

## Configuration

### Network Location

The system supports two network locations:
- **Local**: Home network (192.168.0.123)
- **Remote**: Internet (75.154.254.186)

Network location is automatically persisted and survives API restarts. You can check or change it via:

```bash
# Check current location
curl http://localhost:8003/api/system/network-location

# Change to local
curl -X PUT http://localhost:8003/api/system/network-location \
  -H "Content-Type: application/json" \
  -d '{"location": "local"}'
```

### Environment Variables

The MCP server uses these environment variables:

- `RISETRADER_API_URL`: Base URL for the FastAPI backend (default: `http://localhost:8003`)
- `PYTHONPATH`: Path to RiseTrader root directory

## Usage Examples

### Live Trading Workflow

```
User: "What's my current account balance?"
Claude: [Calls get_account_info]
Result: Balance: $12,866.80, Equity: $12,833.70, Margin: $84.16

User: "Buy 0.01 lots of CrudeOIL"
Claude: [Calls place_market_order with symbol=CrudeOIL, side=buy, quantity=0.01]
Result: Order placed successfully, position ID: 1780

User: "Close that position"
Claude: [Calls close_position with position_id=1780]
Result: Position closed successfully
```

### Backtesting Workflow

```
User: "Run a backtest on CrudeOIL using the V3 strategy from 2024-01-01 to 2024-06-30"
Claude: [Calls create_backtest with appropriate parameters]
Result: Backtest created with run ID: abc123-def456

User: "Show me the results"
Claude: [Calls get_backtest_results with backtest_id=abc123-def456]
Result: Total trades: 42, Win rate: 58.3%, Sharpe ratio: 1.45, ...
```

### Market Analysis Workflow

```
User: "Get the last 100 H1 candles for CrudeOIL and analyze the trend"
Claude: [Calls get_latest_candles with symbol=CrudeOIL, timeframe=H1, limit=100]
Claude: [Analyzes OHLCV data and provides technical analysis]

User: "What does the ML model forecast for the next 4 hours?"
Claude: [Calls get_forecast with symbol=CrudeOIL, horizon=4H]
Result: Predicted price movement: +0.35 (bullish)
```

## Troubleshooting

### MCP Server Not Showing Up in Claude Desktop

1. Check that `claude_desktop_config.json` is in the correct location
2. Verify JSON syntax is valid (no trailing commas)
3. Restart Claude Desktop completely
4. Check Claude Desktop logs: `~/Library/Logs/Claude/mcp*.log`

### API Connection Errors

1. Verify RiseTrader API is running: `curl http://localhost:8003/health`
2. Check network location is correct: `curl http://localhost:8003/api/system/network-location`
3. Verify MT4 connection: `curl http://localhost:8003/api/trading/account`

### Tool Call Failures

1. Check API logs: `docker logs risetrader-api --tail 50`
2. Verify MT4 is connected and accepting commands
3. Check that account has sufficient margin for trades
4. Ensure symbol is valid and market is open

## Security Notes

**IMPORTANT:** The MCP server provides full trading access, including:
- Placing live orders
- Closing positions
- Managing account

**Recommendations:**
1. Only use on trusted machines
2. Never share your MCP configuration
3. Implement position size limits in your account settings
4. Use the paper trading mode for testing new strategies
5. Always verify trades before execution

## Current Status (as of Dec 21, 2025)

- ✅ MCP server implemented with 12 comprehensive tools
- ✅ All dependencies installed and conflicts resolved
- ✅ API container restarted and verified healthy
- ✅ MT4 connection tested and working
- ✅ Network location persistence verified
- ⏳ Pending: Claude Desktop configuration and testing

## Next Steps

1. Configure Claude Desktop with the MCP server
2. Test all 12 tools through natural language commands
3. Implement portfolio management tools (planned)
4. Add real-time event streaming for market updates
5. Integrate with agent system for autonomous trading

## Support

For issues or questions:
- Check API health: `curl http://localhost:8003/health`
- View logs: `docker logs risetrader-api --tail 100`
- Restart API: `docker-compose restart api`
- Check MCP server: `docker exec risetrader-api python -m src.mcp.server --help`

## Reference

- MCP Specification: https://spec.modelcontextprotocol.io/
- RiseTrader API Docs: http://localhost:8003/docs
- Claude Desktop: https://claude.ai/download
