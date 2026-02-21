# MCP Event Flow Guide

**RiseTrader Agent Communication Patterns**

This guide documents the event-driven communication patterns between RiseTrader's 10 autonomous trading agents coordinated by the MCP server.

## Table of Contents

1. [Event Types](#event-types)
2. [Trading Cycle Flows](#trading-cycle-flows)
3. [Event Schemas](#event-schemas)
4. [Subscription Matrix](#subscription-matrix)
5. [Error Handling](#error-handling)
6. [Performance Characteristics](#performance-characteristics)

---

## Event Types

### Priority Levels

Events are processed based on priority:

| Priority | Level | Use Cases | Target Latency |
|----------|-------|-----------|----------------|
| CRITICAL | 0 | Emergency stops, system failures | <10ms |
| HIGH | 1 | Trade execution, risk alerts | <25ms |
| NORMAL | 2 | Signals, data updates | <50ms |
| LOW | 3 | Performance reports, optimization | <100ms |

### Event Categories

**Market Data Events:**
- `new_tick` - New price tick received
- `new_bar` - New candlestick bar completed
- `market_data_error` - Data validation failure

**Analysis Events:**
- `regime_changed` - Market regime transition
- `forecast_generated` - ML prediction ready
- `indicator_updated` - Technical indicator calculated

**Trading Events:**
- `signal_generated` - Trading signal created
- `trade_validated` - Risk check passed
- `trade_rejected` - Risk check failed
- `trade_executed` - Order filled on MT4
- `trade_failed` - Execution error

**Risk Events:**
- `risk_alert` - Risk limit approached
- `emergency_stop` - Critical risk breach
- `position_closed` - Position liquidated

**Performance Events:**
- `pnl_updated` - P&L recalculated
- `performance_report` - Periodic summary
- `strategy_optimized` - Parameters updated

**System Events:**
- `agent_started` - Agent initialized
- `agent_stopped` - Agent shutdown
- `agent_failed` - Agent error
- `heartbeat` - Health check

---

## Trading Cycle Flows

### Flow 1: Normal Trade Execution

```
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Market Data Ingestion                                      │
└─────────────────────────────────────────────────────────────────────┘

MT4 (ZMQ) ──tick──> MarketDataAgent
                         │
                         ├─ Validate tick
                         ├─ Store to PostgreSQL
                         └─ Publish "new_tick" event (NORMAL)
                              │
                              └─> Event Bus

┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Analysis & Signal Generation                               │
└─────────────────────────────────────────────────────────────────────┘

Event Bus ──"new_tick"──> RegimeDetectionAgent
                               │
                               ├─ Classify market regime
                               ├─ Update context: "market_regime"
                               └─ Publish "regime_changed" (NORMAL)
                                    │
Event Bus ──"new_tick"──> MLPredictionAgent
                               │
                               ├─ Run ensemble models
                               ├─ Generate forecasts (5m, 15m, 60m)
                               └─ Publish "forecast_generated" (NORMAL)
                                    │
Event Bus ──"new_tick"──> SignalGeneratorAgent
      + context("market_regime")
      + context("forecast")
                               │
                               ├─ Run all strategies:
                               │    - Momentum (30%)
                               │    - Mean Reversion (25%)
                               │    - Breakout (25%)
                               │    - ML Forecast (20%)
                               ├─ Aggregate signals
                               ├─ Check confidence > 0.6
                               └─ Publish "signal_generated" (HIGH)
                                    │
                                    │ {
                                    │   "symbol": "CrudeOIL",
                                    │   "direction": "LONG",
                                    │   "confidence": 0.75,
                                    │   "entry_price": 75.50,
                                    │   "strategy": "momentum+ml"
                                    │ }

┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Risk Validation                                            │
└─────────────────────────────────────────────────────────────────────┘

Event Bus ──"signal_generated"──> RiskManagerAgent
                                       │
                                       ├─ Check pre-trade rules:
                                       │    ✓ Max open positions < 5
                                       │    ✓ Daily loss < $1,000
                                       │    ✓ Position correlation < 0.7
                                       ├─ Calculate position size (Kelly)
                                       ├─ Set stop loss & take profit
                                       │
                                       ├─ IF APPROVED:
                                       │    └─ Publish "trade_validated" (HIGH)
                                       │         {
                                       │           "signal_id": "...",
                                       │           "position_size": 2.5,
                                       │           "stop_loss": 74.00,
                                       │           "take_profit": 77.00
                                       │         }
                                       │
                                       └─ IF REJECTED:
                                            └─ Publish "trade_rejected" (HIGH)
                                                 {
                                                   "signal_id": "...",
                                                   "reason": "max_positions_reached"
                                                 }

┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Execution                                                  │
└─────────────────────────────────────────────────────────────────────┘

Event Bus ──"trade_validated"──> ExecutionAgent
                                      │
                                      ├─ Build MT4 order:
                                      │    {
                                      │      "symbol": "CrudeOIL",
                                      │      "type": "BUY",
                                      │      "volume": 2.5,
                                      │      "sl": 74.00,
                                      │      "tp": 77.00
                                      │    }
                                      ├─ Send via ZMQ to MT4
                                      ├─ Wait for confirmation (5s timeout)
                                      │
                                      ├─ IF SUCCESS:
                                      │    ├─ Store to open_positions table
                                      │    └─ Publish "trade_executed" (HIGH)
                                      │         {
                                      │           "order_id": "MT4-12345",
                                      │           "fill_price": 75.52,
                                      │           "slippage": 0.02
                                      │         }
                                      │
                                      └─ IF FAILED:
                                           └─ Publish "trade_failed" (HIGH)
                                                {
                                                  "error": "insufficient_margin",
                                                  "retry": false
                                                }

┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 5: Monitoring                                                 │
└─────────────────────────────────────────────────────────────────────┘

Event Bus ──"trade_executed"──> PerformanceMonitorAgent
                                      │
                                      ├─ Update P&L metrics
                                      ├─ Calculate win rate
                                      ├─ Update Sharpe ratio
                                      └─ Publish "pnl_updated" (LOW)

Event Bus ──"trade_executed"──> RiskOverseerAgent
                                      │
                                      ├─ Calculate portfolio VaR
                                      ├─ Check correlation matrix
                                      ├─ Monitor drawdown
                                      │
                                      └─ IF risk_threshold_exceeded:
                                           └─ Publish "risk_alert" (CRITICAL)
```

### Flow 2: Emergency Stop

```
┌─────────────────────────────────────────────────────────────────────┐
│ Risk Breach Detection                                               │
└─────────────────────────────────────────────────────────────────────┘

RiskOverseerAgent (monitoring loop)
    │
    ├─ Daily loss > $1,000 detected
    │
    └─ Publish "emergency_stop" (CRITICAL)
         {
           "reason": "max_daily_loss_exceeded",
           "current_loss": -1050.00,
           "limit": -1000.00,
           "action": "close_all_positions"
         }

┌─────────────────────────────────────────────────────────────────────┐
│ Immediate Response                                                  │
└─────────────────────────────────────────────────────────────────────┘

Event Bus ──"emergency_stop"──> ExecutionAgent
                                      │
                                      ├─ PRIORITY: Process immediately
                                      ├─ Close all open positions
                                      ├─ Cancel pending orders
                                      └─ Publish "positions_closed" (CRITICAL)

Event Bus ──"emergency_stop"──> SignalGeneratorAgent
                                      │
                                      └─ Pause signal generation

Event Bus ──"emergency_stop"──> RiskManagerAgent
                                      │
                                      └─ Reject all new trade validations
```

### Flow 3: Strategy Optimization (Daily)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Scheduled Optimization                                              │
└─────────────────────────────────────────────────────────────────────┘

StrategyOptimizerAgent (daily cron: 00:00 UTC)
    │
    ├─ Load last 1000 trades from PostgreSQL
    ├─ Evaluate current strategy parameters
    ├─ Run Bayesian optimization
    ├─ Test new parameters on validation set
    │
    └─ IF performance_improved:
         └─ Publish "strategy_optimized" (LOW)
              {
                "strategy": "momentum",
                "old_params": {
                  "threshold": 0.6,
                  "stop_loss_pct": 0.02
                },
                "new_params": {
                  "threshold": 0.65,
                  "stop_loss_pct": 0.018
                },
                "expected_sharpe_improvement": 0.15
              }

Event Bus ──"strategy_optimized"──> SignalGeneratorAgent
                                         │
                                         └─ Update strategy parameters
                                              (A/B test: 80% old, 20% new)
```

---

## Event Schemas

### Standard Event Structure

```python
{
    "event_id": "uuid-v4",
    "event_type": "signal_generated",
    "source_agent": "signal_generator",
    "data": {
        # Event-specific payload
    },
    "priority": 1,  # 0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW
    "timestamp": 1700000000.124,
    "correlation_id": "uuid-v4-optional",  # Links related events
    "metadata": {
        # Optional additional context
    }
}
```

### Event Schemas by Type

#### new_tick
```python
{
    "event_type": "new_tick",
    "data": {
        "symbol": "CrudeOIL",
        "bid": 75.50,
        "ask": 75.52,
        "timestamp": 1700000000.124,
        "volume": 1000
    },
    "priority": 2  # NORMAL
}
```

#### signal_generated
```python
{
    "event_type": "signal_generated",
    "data": {
        "signal_id": "uuid-v4",
        "symbol": "CrudeOIL",
        "direction": "LONG",  # LONG, SHORT
        "confidence": 0.75,
        "entry_price": 75.50,
        "strategy": "momentum+ml",
        "indicators": {
            "rsi": 65,
            "macd": 0.15,
            "ml_forecast_5m": 75.80
        }
    },
    "priority": 1  # HIGH
}
```

#### trade_validated
```python
{
    "event_type": "trade_validated",
    "data": {
        "signal_id": "uuid-v4",
        "position_size": 2.5,
        "stop_loss": 74.00,
        "take_profit": 77.00,
        "risk_reward_ratio": 3.0,
        "risk_pct": 0.02,
        "checks_passed": [
            "max_positions",
            "daily_loss",
            "correlation"
        ]
    },
    "priority": 1  # HIGH
}
```

#### trade_executed
```python
{
    "event_type": "trade_executed",
    "data": {
        "order_id": "MT4-12345",
        "signal_id": "uuid-v4",
        "symbol": "CrudeOIL",
        "direction": "LONG",
        "volume": 2.5,
        "fill_price": 75.52,
        "requested_price": 75.50,
        "slippage": 0.02,
        "stop_loss": 74.00,
        "take_profit": 77.00,
        "execution_time_ms": 250,
        "mt4_timestamp": 1700000000.124
    },
    "priority": 1  # HIGH
}
```

#### emergency_stop
```python
{
    "event_type": "emergency_stop",
    "data": {
        "reason": "max_daily_loss_exceeded",
        "current_loss": -1050.00,
        "limit": -1000.00,
        "action": "close_all_positions",
        "open_positions": [
            {"order_id": "MT4-12345", "symbol": "CrudeOIL", "pnl": -500.00},
            {"order_id": "MT4-12346", "symbol": "DXY", "pnl": -550.00}
        ]
    },
    "priority": 0  # CRITICAL
}
```

---

## Subscription Matrix

| Event Type | Priority | Publishers | Subscribers |
|------------|----------|-----------|-------------|
| new_tick | NORMAL | MarketDataAgent | SignalGenerator, MLPrediction, RegimeDetection |
| new_bar | NORMAL | MarketDataAgent | SignalGenerator, RegimeDetection |
| regime_changed | NORMAL | RegimeDetectionAgent | SignalGenerator, StrategyOptimizer |
| forecast_generated | NORMAL | MLPredictionAgent | SignalGenerator |
| signal_generated | HIGH | SignalGeneratorAgent | RiskManager |
| trade_validated | HIGH | RiskManagerAgent | ExecutionAgent |
| trade_rejected | HIGH | RiskManagerAgent | PerformanceMonitor |
| trade_executed | HIGH | ExecutionAgent | PerformanceMonitor, RiskOverseer |
| trade_failed | HIGH | ExecutionAgent | PerformanceMonitor, RiskManager |
| emergency_stop | CRITICAL | RiskOverseerAgent | ALL |
| risk_alert | HIGH | RiskOverseerAgent | RiskManager, SignalGenerator |
| pnl_updated | LOW | PerformanceMonitorAgent | RiskOverseer |
| strategy_optimized | LOW | StrategyOptimizerAgent | SignalGenerator |

---

## Error Handling

### Retry Logic

Events that fail processing are retried automatically:

```python
# Configuration in config/agents.yaml
events:
  retry_failed: true
  retry_max_attempts: 3
  retry_delay: 1.0  # seconds
  timeout: 30.0
```

**Retry Strategy:**
1. First attempt: Immediate
2. Second attempt: 1 second delay
3. Third attempt: 2 second delay
4. After 3 failures → Dead Letter Queue

### Dead Letter Queue

Failed events are stored for manual inspection:

```python
# Access dead letter events
dead_letter_events = await event_bus.dead_letter_queue.get()

# Structure:
{
    "event": {...},  # Original event
    "agent_id": "risk_manager",
    "error": "KeyError: 'position_size'",
    "timestamp": 1700000000.124,
    "attempts": 3
}
```

### Circuit Breaker States

When an agent fails repeatedly, its circuit breaker opens:

```
CLOSED (normal operation)
    │
    ├─ 5 failures detected
    │
    ▼
OPEN (reject all requests)
    │
    ├─ 60 seconds elapsed
    │
    ▼
HALF_OPEN (test recovery)
    │
    ├─ 3 successes → CLOSED
    └─ 1 failure → OPEN
```

**Impact on Events:**
- Events to agents with OPEN circuits are rejected immediately
- Error logged: `event_rejected_circuit_open`
- No retry attempts (circuit must recover first)

---

## Performance Characteristics

### Latency Targets

| Flow Stage | Target | Measurement |
|------------|--------|-------------|
| Event publish | <5ms | EventBus.publish() |
| Queue to handler | <10ms | EventBus internal routing |
| Handler execution | <35ms | Agent.process_event() |
| **Total event processing** | **<50ms** | End-to-end |

### Throughput Capacity

| Metric | Target | Notes |
|--------|--------|-------|
| Events/second | 100+ | Sustained load |
| Peak events/second | 500+ | Burst handling |
| Concurrent agents | 10 | All running |
| Queue capacity | 10,000 events | Per priority level |

### Monitoring

**Key Prometheus Metrics:**

```python
# Event metrics
mcp_events_published_total{event_type="new_tick"}
mcp_events_consumed_total{event_type="new_tick", agent_id="signal_generator"}
mcp_event_processing_seconds{event_type="new_tick"}  # Histogram

# Queue metrics
mcp_event_queue_size{priority="HIGH"}

# Agent metrics
agent_events_processed_total{agent_id="signal_generator", event_type="new_tick"}
agent_event_processing_seconds{agent_id="signal_generator", event_type="new_tick"}
agent_errors_total{agent_id="signal_generator", error_type="KeyError"}
```

**Alerts:**

```yaml
# Event processing latency
- alert: HighEventProcessingLatency
  expr: histogram_quantile(0.95, mcp_event_processing_seconds) > 0.1
  for: 5m
  annotations:
    summary: "Event processing latency >100ms (p95)"

# Queue capacity
- alert: EventQueueNearCapacity
  expr: mcp_event_queue_size / 10000 > 0.9
  for: 1m
  annotations:
    summary: "Event queue >90% capacity"

# Agent failures
- alert: AgentCircuitBreakerOpen
  expr: mcp_circuit_breaker_state{state="open"} == 1
  for: 1m
  annotations:
    summary: "Agent circuit breaker opened"
```

---

## Example Agent Implementation

Here's how to implement an agent that subscribes to events:

```python
from src.agents.base_agent import BaseAgent
from src.agents.event_bus import Event, EventPriority

class ExampleAgent(BaseAgent):
    async def initialize(self) -> None:
        """Set up subscriptions"""
        self.subscribe_to_event("new_tick")
        self.subscribe_to_event("signal_generated")

        # Load agent-specific resources
        self.model = load_ml_model()

        self.logger.info("agent_initialized")

    async def process_event(self, event: Event) -> None:
        """Handle incoming events"""
        if event.event_type == "new_tick":
            await self._handle_tick(event)
        elif event.event_type == "signal_generated":
            await self._handle_signal(event)

    async def _handle_tick(self, event: Event) -> None:
        """Process market tick"""
        tick_data = event.data

        # Do processing
        result = await self.model.predict(tick_data)

        # Publish new event
        await self.publish_event(
            event_type="forecast_generated",
            data={"forecast": result},
            priority=EventPriority.NORMAL,
            correlation_id=event.correlation_id
        )

    async def cleanup(self) -> None:
        """Cleanup resources"""
        await self.model.close()
        self.logger.info("agent_cleanup_complete")
```

---

**Next Steps:**

1. Implement specific agent classes inheriting from `BaseAgent`
2. Define event schemas in Pydantic models for validation
3. Set up monitoring dashboards in Grafana
4. Write integration tests for event flows
5. Load test with 1000+ events/second

**Related Documentation:**

- [ADR-001: MCP Server Architecture](ADR-001-MCP-Server-Architecture.md)
- [Agent Implementation Guide](Agent-Implementation-Guide.md) (to be created)
- [Testing Guide](Testing-Guide.md) (to be created)
