# RiseTrader Agent System

**Model Context Protocol (MCP) Server for Autonomous Trading Agents**

This module implements the event-driven agent coordination system for RiseTrader's 10 autonomous trading agents.

## Quick Start

### 1. Start Dependencies

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Verify services
docker-compose ps
```

### 2. Configure Agents

Edit `config/agents.yaml` to enable/disable agents and adjust parameters.

### 3. Run MCP Server

```bash
# From project root
python -m src.agents.mcp_server

# Or with custom configuration
AGENT_CONFIG_PATH=config/agents.yaml \
REDIS_URL=redis://localhost:6379 \
python -m src.agents.mcp_server
```

### 4. Check Status

```bash
# Health check
curl http://localhost:7000/health

# List agents
curl http://localhost:7000/agents

# View metrics
curl http://localhost:7000/metrics
```

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      MCP Server (Port 7000)                   │
│                    FastAPI + Event Coordination               │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────┐    ┌──────────────┐    ┌─────────────┐ │
│  │  EventBus      │◄──►│AgentRegistry │◄──►│BaseAgent(s) │ │
│  │  (Redis Pub/Sub)│    │(Health Check)│    │             │ │
│  └────────────────┘    └──────────────┘    └─────────────┘ │
│                                                               │
└──────────────────────────────────────────────────────────────┘
                           ▲
                           │ Events
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    10 Trading Agents                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  EXECUTION LAYER          DATA/ML LAYER      SUPERVISORY     │
│  ├─ SignalGenerator       ├─ MarketData     ├─ Performance  │
│  ├─ RiskManager           ├─ MLPrediction   ├─ RiskOverseer │
│  └─ Execution             └─ RegimeDetection└─ Optimizer    │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. EventBus (`event_bus.py`)

High-performance async event bus using Redis pub/sub.

**Features:**
- Priority-based event queuing (CRITICAL, HIGH, NORMAL, LOW)
- Automatic retry with exponential backoff
- Dead letter queue for failed events
- Backpressure handling
- Prometheus metrics

**Usage:**

```python
from src.agents.event_bus import EventBus, Event, EventPriority

event_bus = EventBus(redis_url="redis://localhost:6379")
await event_bus.start()

# Publish event
event = Event(
    event_type="new_tick",
    source_agent="market_data",
    data={"symbol": "CrudeOIL", "price": 75.50},
    priority=EventPriority.NORMAL
)
await event_bus.publish(event)

# Subscribe to events
event_bus.subscribe("new_tick", "my_agent", my_handler)
```

**Performance Targets:**
- <50ms event processing
- 100+ events/second sustained
- 500+ events/second burst

### 2. AgentRegistry (`agent_registry.py`)

Agent lifecycle and health management with circuit breaker.

**Features:**
- Agent registration with metadata
- Heartbeat-based health monitoring (30s interval)
- Circuit breaker for fault isolation
- Redis-backed distributed state

**Usage:**

```python
from src.agents.agent_registry import AgentRegistry, AgentStatus

registry = AgentRegistry(redis_url="redis://localhost:6379")
await registry.start()

# Register agent
metadata = await registry.register(
    agent_id="signal_generator",
    agent_class="src.agents.execution.signal_generator.SignalGeneratorAgent",
    priority=1,
    config={"strategies": [...]}
)

# Send heartbeat
await registry.heartbeat("signal_generator")

# Check circuit breaker
if registry.is_circuit_open("signal_generator"):
    print("Agent circuit is open!")
```

**Circuit Breaker:**
- Failure threshold: 5 errors
- Recovery timeout: 60 seconds
- States: CLOSED → OPEN → HALF_OPEN → CLOSED

### 3. BaseAgent (`base_agent.py`)

Abstract base class for all trading agents.

**Features:**
- Event subscription and publishing
- Lifecycle management (start/stop/pause/resume)
- Automatic heartbeat
- Shared context via Redis
- Error handling with metrics

**Usage:**

```python
from src.agents.base_agent import BaseAgent
from src.agents.event_bus import Event, EventPriority

class MyAgent(BaseAgent):
    async def initialize(self) -> None:
        """Set up agent subscriptions and resources"""
        self.subscribe_to_event("new_tick")
        self.model = await self.load_model()

    async def process_event(self, event: Event) -> None:
        """Handle incoming event"""
        if event.event_type == "new_tick":
            result = await self.analyze(event.data)

            # Publish result
            await self.publish_event(
                event_type="signal_generated",
                data={"signal": result},
                priority=EventPriority.HIGH
            )

    async def cleanup(self) -> None:
        """Clean up resources"""
        await self.model.close()

# Create and start agent
agent = MyAgent(
    agent_id="my_agent",
    event_bus=event_bus,
    agent_registry=registry,
    config={...}
)
await agent.start()
```

### 4. MCPServer (`mcp_server.py`)

Central coordination hub with HTTP API.

**Features:**
- Dynamic agent loading from YAML config
- FastAPI endpoints for control/monitoring
- Graceful shutdown handling
- Prometheus metrics endpoint

**API Endpoints:**

```bash
# Server info
GET /

# Health check
GET /health

# List all agents
GET /agents

# Agent details
GET /agents/{agent_id}

# Pause agent
POST /agents/{agent_id}/pause

# Resume agent
POST /agents/{agent_id}/resume

# Send command
POST /agents/{agent_id}/command
{
  "action": "generate_signal",
  "parameters": {"symbol": "CrudeOIL"}
}

# Event bus statistics
GET /events/stats

# Registry statistics
GET /registry/stats

# Prometheus metrics
GET /metrics
```

## The 10 Trading Agents

### Execution Layer (Priority 1-3)

**1. SignalGeneratorAgent**
- Aggregates signals from multiple strategies
- Integrates ML forecasts and regime detection
- Publishes `signal_generated` events

**2. RiskManagerAgent**
- Validates signals against risk limits
- Calculates position sizing (Kelly criterion)
- Publishes `trade_validated` or `trade_rejected`

**3. ExecutionAgent**
- Executes orders on MT4 via ZMQ
- Handles retries and error recovery
- Publishes `trade_executed` or `trade_failed`

### Data/ML Layer (Priority 4-6)

**4. MarketDataAgent**
- Streams real-time ticks from MT4
- Validates data quality
- Publishes `new_tick` and `new_bar` events

**5. MLPredictionAgent**
- Runs ensemble ML models (XGBoost, Transformer, LSTM)
- Generates forecasts for multiple horizons
- Publishes `forecast_generated` events

**6. RegimeDetectionAgent**
- Classifies market regime (trending/ranging/volatile)
- Adapts strategy parameters to regime
- Publishes `regime_changed` events

### Supervisory Layer (Priority 7-9)

**7. PerformanceMonitorAgent**
- Tracks real-time P&L and metrics
- Calculates Sharpe ratio, win rate, etc.
- Publishes `pnl_updated` events

**8. RiskOverseerAgent**
- Monitors system-wide risk metrics
- Triggers emergency stops if needed
- Publishes `risk_alert` and `emergency_stop`

**9. StrategyOptimizerAgent**
- Continuously optimizes strategy parameters
- A/B tests new configurations
- Publishes `strategy_optimized` events

## Event Flow Example

```
1. MarketDataAgent receives tick from MT4
   ↓
   Publishes "new_tick" event (NORMAL priority)

2. Multiple agents process tick:
   - RegimeDetectionAgent updates market regime
   - MLPredictionAgent generates forecast
   - SignalGeneratorAgent creates trading signal
   ↓
   SignalGeneratorAgent publishes "signal_generated" (HIGH priority)

3. RiskManagerAgent validates signal
   ↓
   Publishes "trade_validated" (HIGH priority)

4. ExecutionAgent sends order to MT4
   ↓
   Publishes "trade_executed" (HIGH priority)

5. Monitoring agents update metrics:
   - PerformanceMonitorAgent updates P&L
   - RiskOverseerAgent checks portfolio risk
```

See [docs/MCP-Event-Flow-Guide.md](../../docs/MCP-Event-Flow-Guide.md) for detailed event flows.

## Configuration

### agents.yaml Structure

```yaml
mcp_server:
  host: "0.0.0.0"
  port: 7000
  heartbeat_interval: 30

agents:
  signal_generator:
    enabled: true
    class: "src.agents.execution.signal_generator.SignalGeneratorAgent"
    priority: 1
    config:
      strategies:
        - name: "momentum"
          enabled: true
          weight: 0.3

events:
  retry_failed: true
  retry_max_attempts: 3
  retry_delay: 1.0
  timeout: 30.0

circuit_breaker:
  enabled: true
  failure_threshold: 5
  recovery_timeout: 60.0

logging:
  level: "INFO"
  format: "json"
```

### Environment Variables

```bash
# Required
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/risetrader

# Optional
AGENT_CONFIG_PATH=config/agents.yaml
LOG_LEVEL=INFO
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=7000
```

## Monitoring

### Prometheus Metrics

**Event Metrics:**
- `mcp_events_published_total` - Total events published by type
- `mcp_events_consumed_total` - Total events consumed by agent
- `mcp_event_processing_seconds` - Event processing latency histogram
- `mcp_event_queue_size` - Current queue size

**Agent Metrics:**
- `mcp_agents_total` - Total agents by status
- `mcp_agent_health_checks_total` - Health check results
- `mcp_circuit_breaker_state` - Circuit breaker state by agent
- `agent_events_processed_total` - Events processed per agent
- `agent_errors_total` - Errors per agent by type

### Logging

Structured JSON logging with correlation IDs:

```json
{
  "timestamp": "2025-11-16T12:00:00.000Z",
  "level": "info",
  "logger_name": "src.agents.base_agent",
  "event": "event_processed",
  "agent_id": "signal_generator",
  "agent_class": "SignalGeneratorAgent",
  "event_id": "uuid-here",
  "event_type": "new_tick",
  "processing_time": 0.035
}
```

## Testing

### Unit Tests

```bash
# Test EventBus
pytest tests/unit/agents/test_event_bus.py

# Test AgentRegistry
pytest tests/unit/agents/test_agent_registry.py

# Test BaseAgent
pytest tests/unit/agents/test_base_agent.py
```

### Integration Tests

```bash
# Test agent communication
pytest tests/integration/agents/test_agent_communication.py

# Test full trading cycle
pytest tests/integration/agents/test_trading_cycle.py
```

### Load Tests

```bash
# Stress test event bus with 1000+ events/second
pytest tests/load/test_event_bus_load.py -v
```

## Troubleshooting

### Agent Not Starting

**Check logs:**
```bash
# View MCP server logs
docker-compose logs -f mcp-server

# Check specific agent
curl http://localhost:7000/agents/signal_generator
```

**Common issues:**
- Redis not running: `docker-compose up -d redis`
- Configuration error: Check `config/agents.yaml` syntax
- Import error: Verify agent class path

### Circuit Breaker Open

**Check agent status:**
```bash
curl http://localhost:7000/agents/{agent_id}
# Look for "circuit_breaker_open": true
```

**Recovery:**
1. Wait 60 seconds for automatic recovery attempt
2. Check agent logs for root cause
3. Fix underlying issue
4. Agent will automatically retry when circuit closes

### High Event Latency

**Check queue sizes:**
```bash
curl http://localhost:7000/events/stats
# Look for large queue_sizes
```

**Solutions:**
- Reduce event publishing rate
- Increase number of agent workers
- Optimize slow event handlers
- Check Redis connection latency

### Dead Letter Queue Growing

**Inspect failed events:**
```python
# Access dead letter queue programmatically
dead_letters = await event_bus.dead_letter_queue.get()
print(dead_letters["error"])
```

**Common causes:**
- Schema validation errors
- Agent configuration issues
- Database connection failures

## Performance Tuning

### EventBus Configuration

```python
# Increase queue capacity for high throughput
EventBus(
    max_queue_size=50000,  # Default: 10000
    retry_attempts=5,      # Default: 3
    event_timeout=60.0     # Default: 30.0
)
```

### Redis Optimization

```bash
# Increase Redis memory limit
redis-cli config set maxmemory 2gb

# Enable AOF persistence for durability
redis-cli config set appendonly yes
```

### Agent Tuning

```yaml
# In agents.yaml, adjust heartbeat frequency
mcp_server:
  heartbeat_interval: 10  # More frequent health checks

# Reduce circuit breaker sensitivity
circuit_breaker:
  failure_threshold: 10  # Allow more failures
  recovery_timeout: 30   # Faster recovery testing
```

## Development

### Adding a New Agent

1. **Create agent class:**

```python
# src/agents/my_layer/my_agent.py
from src.agents.base_agent import BaseAgent
from src.agents.event_bus import Event

class MyAgent(BaseAgent):
    async def initialize(self) -> None:
        self.subscribe_to_event("some_event")

    async def process_event(self, event: Event) -> None:
        # Your logic here
        pass

    async def cleanup(self) -> None:
        pass
```

2. **Add to configuration:**

```yaml
# config/agents.yaml
agents:
  my_agent:
    enabled: true
    class: "src.agents.my_layer.my_agent.MyAgent"
    priority: 5
    config:
      # Agent-specific config
```

3. **Test:**

```python
# tests/unit/agents/test_my_agent.py
import pytest
from src.agents.my_layer.my_agent import MyAgent

@pytest.mark.asyncio
async def test_my_agent_processes_event():
    # Test implementation
    pass
```

4. **Restart MCP server:**

```bash
# Agent will be automatically loaded
python -m src.agents.mcp_server
```

## Documentation

- [ADR-001: MCP Server Architecture](../../docs/ADR-001-MCP-Server-Architecture.md)
- [MCP Event Flow Guide](../../docs/MCP-Event-Flow-Guide.md)
- [Agent Implementation Examples](../../docs/Agent-Implementation-Guide.md) (to be created)

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f mcp-server`
2. Review metrics: `http://localhost:7000/metrics`
3. Inspect agent status: `http://localhost:7000/agents`
4. Consult documentation in `/docs`

---

**Built with:** Python 3.11+, FastAPI, Redis, asyncio, Prometheus
**License:** MIT
**Version:** 1.0.0
