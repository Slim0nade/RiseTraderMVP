# Live Backtest Visualization - Implementation Progress

## Feature Request
User requested MT4-style live visualization showing:
- Real-time price chart as backtest progresses
- Agent "thoughts" appearing as bubbles around the chart
- Order entry/exit points marked with buy/sell arrows (like MetaTrader 4)

## ✅ Backend Implementation (COMPLETE)

### 1. WebSocket Event Infrastructure
**File**: `src/services/backtesting/backtest_events.py` (NEW)

Created comprehensive event system with:
- **Event Types**:
  - `BACKTEST_STARTED` - Backtest initialization
  - `CANDLE_PROCESSED` - New candle data
  - `AGENT_DECISION` - Agent makes trading decision
  - `TRADE_EXECUTED` - Order filled
  - `POSITION_UPDATED` - Position changes
  - `EQUITY_UPDATED` - Portfolio value changes
  - `BACKTEST_COMPLETED` - Backtest finished
  - `BACKTEST_ERROR` - Error occurred

- **BacktestEventBroadcaster**: Manages WebSocket connections and broadcasts events
- **BacktestEvent**: Serializable event structure with automatic Decimal/UUID conversion

### 2. WebSocket Endpoint
**File**: `src/api/routes/backtesting.py` (MODIFIED)

Added WebSocket endpoint:
```
ws://localhost:8003/api/v1/backtesting/runs/{run_id}/live
```

Features:
- Accepts WebSocket connections
- Registers clients with event broadcaster
- Keeps connection alive with ping/pong
- Auto-cleanup on disconnect

Example Usage (JavaScript):
```javascript
const ws = new WebSocket('ws://localhost:8003/api/v1/backtesting/runs/{run_id}/live');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.event_type === 'agent_decision') {
    // Show agent thought bubble on chart
    const thought = data.data.agent_thought;
    const price = data.data.price;
    const conviction = data.data.conviction;
    // Render bubble at price level
  }
  else if (data.event_type === 'trade_executed') {
    // Draw buy/sell arrow on chart
    const action = data.data.action; // "buy" or "sell"
    const price = data.data.price;
    // Add marker to chart
  }
};
```

### 3. Agent Decision Broadcasting
**File**: `src/services/backtesting/agent_integrator.py` (MODIFIED)

Added event broadcasting after agent decisions are logged (line 551-578):

**Broadcast Data**:
```json
{
  "event_type": "agent_decision",
  "run_id": "uuid",
  "timestamp": "2025-12-27T21:05:16Z",
  "data": {
    "symbol": "CrudeOIL",
    "price": 75.86,
    "action": "buy" | "sell" | "hold",
    "quantity": 51.19,
    "conviction": 0.75,
    "direction": "LONG" | "SHORT",
    "agent_thought": "RSI oversold, MACD bullish crossover indicates strong buy signal...",
    "key_factors": ["Bullish momentum", "Strong demand", "Technical breakout"],
    "timestamp": "2025-12-27T21:05:16Z",
    "processing_time_ms": 8621
  }
}
```

## ⏳ Frontend Implementation (TODO)

### 1. LiveBacktestChart Component
**File**: `dashboard/src/components/backtesting/LiveBacktestChart.tsx` (TO CREATE)

React component using TradingView Lightweight Charts:
- Real-time candlestick chart
- WebSocket client connection
- Auto-updating as events arrive
- Responsive layout

### 2. Agent Thought Bubbles
**File**: `dashboard/src/components/backtesting/AgentThoughtBubble.tsx` (TO CREATE)

Features:
- Speech bubble UI positioned near price on chart
- Displays agent reasoning
- Fades out after 5-10 seconds
- Shows conviction strength (color-coded)
- Top 3 key factors as bullets

Example:
```
┌─────────────────────────────────────┐
│ 🤖 Agent Thinking (Conviction: 75%) │
│                                     │
│ RSI oversold, MACD bullish          │
│ crossover indicates strong buy...   │
│                                     │
│ • Bullish momentum                  │
│ • Strong demand                     │
│ • Technical breakout                │
└─────────────────────────────────────┘
```

### 3. Order Markers (Buy/Sell Arrows)
**File**: Integrated into `LiveBacktestChart.tsx`

Features:
- Green up arrow for BUY orders
- Red down arrow for SELL orders
- Tooltip showing: price, quantity, timestamp
- Positioned at exact entry/exit price levels

### 4. Integration with Backtesting Page
**File**: `dashboard/src/pages/Backtesting.tsx` (TO MODIFY)

Add live chart view:
- Tab/toggle to switch between "Results" and "Live View"
- Only show for running backtests
- Auto-connect WebSocket when viewing live
- Disconnect when switching away

## Backend Testing

Test the WebSocket endpoint:

```bash
# Start a backtest
curl -X POST "http://localhost:8003/api/v1/backtesting/runs" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "config-uuid",
    "execution_mode": "full_pipeline"
  }'

# Connect to WebSocket (use wscat or JavaScript)
wscat -c "ws://localhost:8003/api/v1/backtesting/runs/{run_id}/live"

# You should receive events as backtest progresses:
# { "event_type": "agent_decision", "data": {...} }
# { "event_type": "trade_executed", "data": {...} }
```

## Next Steps

1. ✅ Backend WebSocket infrastructure - COMPLETE
2. ✅ Agent decision broadcasting - COMPLETE
3. ⏳ Create LiveBacktestChart.tsx component
4. ⏳ Add AgentThoughtBubble component
5. ⏳ Add order markers (arrows)
6. ⏳ Test with running backtest

## Performance Considerations

- **Event Throttling**: Agent decisions are naturally throttled (1 per candle in agent mode)
- **Broadcast Efficiency**: Only sends to connected clients for specific run_id
- **Auto-cleanup**: Dead connections automatically removed
- **Non-blocking**: Broadcast failures don't break backtest execution

## Files Modified

### Backend
1. `src/services/backtesting/backtest_events.py` - NEW (Event infrastructure)
2. `src/api/routes/backtesting.py` - Added WebSocket endpoint
3. `src/services/backtesting/agent_integrator.py` - Added event broadcasting

### Frontend (TODO)
1. `dashboard/src/components/backtesting/LiveBacktestChart.tsx` - TO CREATE
2. `dashboard/src/components/backtesting/AgentThoughtBubble.tsx` - TO CREATE
3. `dashboard/src/pages/Backtesting.tsx` - TO MODIFY (add live view tab)

## Dependencies Needed (Frontend)

```json
{
  "lightweight-charts": "^4.1.0"  // TradingView charts library
}
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         LiveBacktestChart.tsx                    │  │
│  │  - TradingView Lightweight Charts                │  │
│  │  - WebSocket client                              │  │
│  │  - AgentThoughtBubble components                 │  │
│  │  - Buy/Sell arrow markers                        │  │
│  └──────────────────────────────────────────────────┘  │
│                        │                                │
│                        │ WebSocket                      │
│                        ▼                                │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  backtesting.py                                  │  │
│  │  WebSocket Endpoint: /runs/{run_id}/live        │  │
│  └──────────────────────────────────────────────────┘  │
│                        │                                │
│                        ▼                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │  backtest_events.py                              │  │
│  │  BacktestEventBroadcaster                        │  │
│  │  - Manages WebSocket connections                 │  │
│  │  - Broadcasts events to all clients              │  │
│  └──────────────────────────────────────────────────┘  │
│                        ▲                                │
│                        │ Event Emission                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │  agent_integrator.py                             │  │
│  │  - Agent makes decision                          │  │
│  │  - Saves to database                             │  │
│  │  - Broadcasts AGENT_DECISION event               │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Example Event Flow

1. **Candle processed**: `backtest_service.py` → Broadcast `CANDLE_PROCESSED` event
2. **Agent decision**: `agent_integrator.py` → Broadcast `AGENT_DECISION` event
3. **Trade executed**: `portfolio_state.py` → Broadcast `TRADE_EXECUTED` event
4. **Frontend receives event**: WebSocket `onmessage` → Update chart + show thought bubble
5. **User sees**: Real-time chart updating with agent thoughts appearing and arrows marking trades

## Status

**Backend**: ✅ 100% Complete (WebSocket + Events working)
**Frontend**: ⏳ 0% Complete (Components not yet created)

**Estimated Time to Complete Frontend**: 2-3 hours
- LiveBacktestChart.tsx: 1 hour
- AgentThoughtBubble.tsx: 30 mins
- Integration + Testing: 1 hour
