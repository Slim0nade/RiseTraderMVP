# ADR-001: MCP Server Architecture for Agent Coordination

## Status
**ACCEPTED** - November 16, 2025

## Context

RiseTrader requires coordination of 10 autonomous trading agents that must communicate in real-time to execute trading strategies. The system needs:

1. **Sub-second latency** for trading decisions (target: <50ms event processing)
2. **High throughput** to handle market data and agent communication (100+ events/second)
3. **Fault tolerance** to prevent cascading failures
4. **Observability** for monitoring agent behavior and system health
5. **Scalability** to add new agents or strategies without major refactoring

### Constraints

- PostgreSQL database at port 5433 with 13.5M market data records
- Redis pub/sub for inter-agent messaging
- MT4 connection at 75.154.254.186 via ZMQ
- Async/await architecture throughout (FastAPI + asyncio)
- Must support both paper trading and live trading modes

### Agent Types

**Execution Layer (Priority 1-3):**
- SignalGeneratorAgent - Multi-strategy signal generation
- RiskManagerAgent - Pre-trade validation
- ExecutionAgent - MT4 order execution

**Data/ML Layer (Priority 4-6):**
- MarketDataAgent - Real-time streaming
- MLPredictionAgent - Forecasts
- RegimeDetectionAgent - Market state

**Supervisory Layer (Priority 7-9):**
- PerformanceMonitorAgent - P&L tracking
- RiskOverseerAgent - Risk monitoring
- StrategyOptimizerAgent - Parameter tuning

## Decision

We will implement an **Event-Driven MCP (Model Context Protocol) Server** with the following architecture:

### Core Components

#### 1. EventBus (event_bus.py)
**Purpose:** High-performance message distribution using Redis pub/sub

**Key Features:**
- Priority-based event queuing (CRITICAL, HIGH, NORMAL, LOW)
- Async event processing with <50ms target
- Backpressure handling via queue size monitoring
- Dead letter queue for failed events
- Automatic retry with exponential backoff
- Prometheus metrics for observability

**Event Flow:**
```
Agent A → EventBus.publish(event) → Redis Pub/Sub → EventBus queues → Agent B handler
```

**Performance Optimizations:**
- Separate asyncio.Queue per priority level
- Parallel event dispatching to subscribers
- Timeout protection (30s default)
- Queue size monitoring (warn at 90% capacity)

#### 2. AgentRegistry (agent_registry.py)
**Purpose:** Agent lifecycle and health management with circuit breaker

**Key Features:**
- Agent registration with metadata (class, priority, config)
- Heartbeat-based health monitoring (30s interval, 90s timeout)
- Circuit breaker pattern for fault isolation
  - States: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)
  - Failure threshold: 5 errors
  - Recovery timeout: 60 seconds
- Redis-backed distributed state
- Status tracking: STARTING → RUNNING → PAUSED/STOPPED/FAILED

**Circuit Breaker Logic:**
```
Success → (HALF_OPEN → 3 successes) → CLOSED
Failure → (count > 5) → OPEN → (60s timeout) → HALF_OPEN
```

#### 3. BaseAgent (base_agent.py)
**Purpose:** Abstract base class for all agents

**Key Features:**
- Event subscription and publishing
- Lifecycle management (start/stop/pause/resume)
- Automatic heartbeat sending
- Shared context via Redis (get_context/set_context)
- Error handling with metrics
- Integration with registry and event bus

**Agent Lifecycle:**
```
STOPPED → start() → STARTING → initialize() → RUNNING → stop() → STOPPED
                                   ↓
                              process_event()
```

#### 4. MCPServer (mcp_server.py)
**Purpose:** Central coordination hub and HTTP API

**Key Features:**
- Dynamic agent loading from YAML config
- Priority-ordered agent startup/shutdown
- FastAPI endpoints for control and monitoring
- Signal handlers for graceful shutdown
- Configuration management
- Prometheus metrics endpoint

**API Endpoints:**
```
GET  /                          - Server info
GET  /health                    - Health check
GET  /agents                    - List all agents
GET  /agents/{id}              - Agent details
POST /agents/{id}/pause        - Pause agent
POST /agents/{id}/resume       - Resume agent
POST /agents/{id}/command      - Send command
GET  /events/stats             - Event bus statistics
GET  /registry/stats           - Registry statistics
GET  /metrics                  - Prometheus metrics
```

### Event Types and Flow

#### Typical Trading Cycle

```
1. Market Tick Event
   MarketDataAgent receives tick
   ↓
   Publishes "new_tick" event (NORMAL priority)

2. Analysis Phase
   RegimeDetectionAgent → Updates market regime
   MLPredictionAgent → Generates forecast
   SignalGeneratorAgent → Processes all inputs
   ↓
   Publishes "signal_generated" event (HIGH priority)

3. Risk Validation
   RiskManagerAgent → Validates signal
   ↓
   Publishes "trade_validated" or "trade_rejected" event (HIGH priority)

4. Execution
   ExecutionAgent → Sends order to MT4
   ↓
   Publishes "trade_executed" event (HIGH priority)

5. Monitoring
   PerformanceMonitorAgent → Updates P&L
   RiskOverseerAgent → Checks portfolio risk
```

### Configuration Management

All agent configuration in `config/agents.yaml`:

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
      strategies: [...]
```

### Error Handling Strategy

**Three-Layer Protection:**

1. **Event Level**
   - Try/catch in event handlers
   - Retry logic (3 attempts with exponential backoff)
   - Dead letter queue for max retries

2. **Agent Level**
   - Circuit breaker prevents cascading failures
   - Automatic status updates (RUNNING → FAILED)
   - Error counting and metrics

3. **System Level**
   - Health check monitoring
   - Graceful degradation (pause agent instead of crash)
   - Alert on critical failures

### Performance Optimizations

1. **Async Throughout**
   - All I/O operations use async/await
   - Parallel event dispatching
   - Non-blocking Redis operations

2. **Queueing Strategy**
   - Priority queues prevent low-priority events blocking high-priority
   - Backpressure detection (warn at 90% capacity)
   - Separate processing tasks per priority

3. **Redis Usage**
   - Pub/sub for event distribution
   - Key-value for shared context
   - Expiring keys with TTL for cleanup

4. **Metrics Collection**
   - Prometheus counters/gauges/histograms
   - No blocking in metric collection
   - Pre-allocated label sets

## Consequences

### Positive

1. **Low Latency**
   - Event processing <50ms target achievable
   - Priority queues ensure critical events processed first
   - Async design prevents blocking

2. **High Reliability**
   - Circuit breaker prevents cascading failures
   - Dead letter queue ensures no event loss
   - Heartbeat monitoring detects failures quickly

3. **Observability**
   - Prometheus metrics throughout
   - Structured logging with correlation IDs
   - Real-time status via HTTP API

4. **Flexibility**
   - Easy to add new agents (inherit BaseAgent)
   - Configuration-driven agent loading
   - Event-driven allows loose coupling

5. **Scalability**
   - Redis pub/sub supports distributed deployment
   - Priority-based processing handles load spikes
   - Circuit breaker protects under stress

### Negative

1. **Complexity**
   - Multiple layers (EventBus, Registry, BaseAgent, MCPServer)
   - Requires understanding of async patterns
   - Debugging event flows can be challenging

2. **Redis Dependency**
   - Single point of failure if Redis unavailable
   - Adds operational complexity
   - Network latency for Redis operations

3. **Memory Usage**
   - Multiple event queues (4 priority levels)
   - Dead letter queue storage
   - Agent metadata in memory

4. **Learning Curve**
   - Developers must understand event-driven architecture
   - Circuit breaker states and transitions
   - Async/await patterns throughout

### Mitigation Strategies

**For Complexity:**
- Comprehensive documentation and examples
- Base agent class handles common patterns
- Structured logging for debugging

**For Redis Dependency:**
- Connection retry with exponential backoff
- Circuit breaker on Redis failures
- Consider Redis Sentinel/Cluster for production

**For Memory Usage:**
- Queue size limits with backpressure
- Dead letter queue max size (1000 events)
- Periodic cleanup of expired context keys

**For Learning Curve:**
- Example agent implementations
- Integration tests demonstrating flows
- Developer documentation with diagrams

## Implementation Notes

### File Structure
```
src/agents/
├── __init__.py
├── event_bus.py           # EventBus implementation
├── agent_registry.py      # AgentRegistry + CircuitBreaker
├── base_agent.py          # BaseAgent abstract class
├── mcp_server.py          # MCPServer + FastAPI app
├── execution/             # Execution layer agents
│   ├── signal_generator.py
│   ├── risk_manager.py
│   └── execution.py
├── data_ml/               # Data/ML layer agents
│   ├── market_data.py
│   ├── ml_prediction.py
│   └── regime_detection.py
└── supervisory/           # Supervisory layer agents
    ├── performance_monitor.py
    ├── risk_overseer.py
    └── strategy_optimizer.py
```

### Dependencies
```python
# Core
redis==5.0.1           # Pub/sub and key-value store
pydantic==2.5.2        # Data validation
structlog==23.2.0      # Structured logging
prometheus-client==0.19.0  # Metrics

# Server
fastapi==0.104.1       # HTTP API
uvicorn==0.24.0        # ASGI server
pyyaml==6.0.1          # Configuration
```

### Running MCP Server
```bash
# Start Redis
docker-compose up -d redis

# Run MCP server
python -m src.agents.mcp_server

# Or with custom config
AGENT_CONFIG_PATH=config/agents.yaml REDIS_URL=redis://localhost:6379 python -m src.agents.mcp_server
```

### Testing Strategy
1. **Unit Tests:** Each component isolated
2. **Integration Tests:** Event flow between agents
3. **Load Tests:** 1000+ events/second stress testing
4. **Fault Injection:** Circuit breaker behavior

### Monitoring

**Key Metrics:**
- `mcp_events_published_total` - Events by type
- `mcp_event_processing_seconds` - Processing latency
- `mcp_agent_health_checks_total` - Health check results
- `mcp_circuit_breaker_state` - Circuit states by agent
- `agent_events_processed_total` - Per-agent event counts
- `agent_errors_total` - Per-agent error counts

**Alerts:**
- Event queue >90% capacity
- Agent heartbeat timeout
- Circuit breaker opened
- Event processing >100ms (p95)

## Related Decisions

- **ADR-002:** Agent Implementation Patterns (to be created)
- **ADR-003:** Event Schema Standards (to be created)
- **ADR-004:** MT4 Integration via ZMQ (to be created)
- **ADR-005:** ML Model Integration (to be created)

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Redis Pub/Sub Guide](https://redis.io/docs/manual/pubsub/)
- [Python asyncio Best Practices](https://docs.python.org/3/library/asyncio-task.html)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)

---

**Author:** Claude (Backend Architect)
**Date:** November 16, 2025
**Review Status:** Approved for implementation
