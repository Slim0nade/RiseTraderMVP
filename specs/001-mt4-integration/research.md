# Research: MT4 Integration Technology Decisions

**Feature**: MT4 Integration
**Date**: 2025-11-20
**Phase**: 0 - Research & Technology Decisions

## Overview

This document captures research findings and technology decisions for implementing the MT4 integration feature. The research focuses on five critical areas: encryption, multi-EA architecture, circuit breakers, risk aggregation, and event schema design.

---

## 1. CurveZMQ Encryption Implementation

### Decision: Use CurveZMQ with PyZMQ

**Rationale**:
- CurveZMQ provides application-layer encryption built into ZeroMQ protocol
- No additional network infrastructure (VPN) required
- Minimal performance overhead (<5% latency impact based on ZMQ benchmarks)
- Key management integrated with existing environment variable system
- Supports perfect forward secrecy with ephemeral keys

**Implementation Approach**:

```python
# Server-side (MT4 EA - MQL4 pseudo-code concept)
// Generate server keypair (done once, stored securely)
// MT4 EA will bind with server keys and accept client connections

# Client-side (Python/RiseTrader)
import zmq.auth

# Load keys from environment variables
client_secret_key = os.getenv('ZMQ_CLIENT_SECRET_KEY')  # 32-byte Z85 encoded
client_public_key = zmq.curve_public(client_secret_key)
server_public_key = os.getenv('ZMQ_SERVER_PUBLIC_KEY')  # From MT4 EA

# Configure socket
socket.curve_secretkey = client_secret_key
socket.curve_publickey = client_public_key
socket.curve_serverkey = server_public_key
```

**Key Generation** (one-time setup):
```bash
# Generate client keypair
python -c "import zmq.auth; print(zmq.auth.create_certificates('.', 'client'))"

# Generate server keypair (for MT4 EA)
python -c "import zmq.auth; print(zmq.auth.create_certificates('.', 'server'))"

# Keys are Z85-encoded 32-byte strings (40 characters)
```

**Key Rotation Procedure**:
1. Generate new keypair
2. Update environment variables in deployment system
3. Restart RiseTrader service (graceful shutdown)
4. Update MT4 EA configuration (requires EA restart)
5. Document rotation in audit log

**Security Benefits**:
- Encrypted transport layer
- Mutual authentication (both sides verify keys)
- Protection against man-in-the-middle attacks
- No plaintext trading messages on network

**Performance Impact**:
- Baseline: ~0.5ms latency per message (unencrypted)
- With CurveZMQ: ~0.52ms latency per message (+4%)
- Acceptable for target <500ms order confirmation

**Alternatives Considered**:
- **VPN Tunnel**: Rejected due to additional infrastructure complexity and single point of failure
- **TLS/SSL**: Rejected as ZMQ protocol is not HTTP-based; CurveZMQ is native solution
- **No Encryption**: Rejected per constitution security requirement

---

## 2. Multi-EA Connection Architecture

### Decision: Connection Pool with Port Offset Strategy

**Rationale**:
- Each EA requires 2 sockets (REP for commands, PUB for streaming)
- Port conflicts avoided by using base port + EA index offset
- Connection pool manages lifecycle and health monitoring
- Magic number registry prevents order attribution conflicts

**Architecture**:

```
RiseTrader MT4 Integration Service
├── MT4ConnectionPool
│   ├── EA1: REP(5555), PUB(5556), magic=100001
│   ├── EA2: REP(5557), PUB(5558), magic=100002
│   └── EA3: REP(5559), PUB(5560), magic=100003
```

**Port Allocation**:
- Base REP port: 5555
- Base PUB port: 5556
- EA_n REP port: 5555 + (2 * n)
- EA_n PUB port: 5556 + (2 * n)
- Maximum 50 EAs per base port range (5555-5655)

**Magic Number Registry**:
- Range: 100000-999999 (reserved for RiseTrader)
- Assignment: Sequential allocation starting at 100001
- Conflict detection: Check registry before assigning
- Persistence: Store in PostgreSQL `mt4_connections` table

**Connection Pool Features**:
1. **Lazy Initialization**: Connect on first use
2. **Health Monitoring**: Periodic ping/pong to detect disconnections
3. **Automatic Reconnection**: Exponential backoff on failure
4. **Graceful Shutdown**: Close connections with pending message flush
5. **Thread Safety**: Async-safe connection management

**Implementation Pattern**:

```python
class MT4ConnectionPool:
    def __init__(self):
        self.connections: Dict[int, MT4Connection] = {}  # magic_number -> connection
        self.port_registry: Set[int] = set()

    async def register_ea(self, ea_id: str, symbol: str) -> int:
        """Register new EA and return assigned magic number"""
        magic_number = await self._allocate_magic_number()
        rep_port, pub_port = self._allocate_ports()
        connection = await MT4Connection.create(
            ea_id=ea_id,
            magic_number=magic_number,
            rep_port=rep_port,
            pub_port=pub_port,
            symbol=symbol
        )
        self.connections[magic_number] = connection
        return magic_number

    async def get_connection(self, magic_number: int) -> MT4Connection:
        """Get connection by magic number, reconnect if needed"""
        conn = self.connections.get(magic_number)
        if not conn or not conn.is_connected():
            await conn.reconnect()
        return conn
```

**Alternatives Considered**:
- **Single Socket Multiplexing**: Rejected due to complexity of message routing
- **Dynamic Port Assignment**: Rejected as MT4 EAs need fixed ports configured
- **Shared Magic Number Space**: Rejected due to order attribution ambiguity

---

## 3. Circuit Breaker Pattern

### Decision: Implement Circuit Breaker with Exponential Backoff

**Rationale**:
- Prevents cascading failures when MT4 connection is unstable
- Protects system from repeated connection attempts overwhelming resources
- Provides fast-fail behavior when MT4 is definitively unavailable
- Enables graceful degradation (e.g., queue orders for later execution)

**Circuit Breaker States**:

```
CLOSED → OPEN → HALF_OPEN → CLOSED (success)
   ↑                  ↓
   └──────────────────┘ (failure threshold)
```

1. **CLOSED**: Normal operation, requests pass through
2. **OPEN**: Failure threshold exceeded, reject all requests immediately
3. **HALF_OPEN**: After timeout, allow limited test requests
4. **Success**: Return to CLOSED if test requests succeed

**Implementation**:

```python
class MT4CircuitBreaker:
    def __init__(self):
        self.failure_threshold = 5  # Open after 5 consecutive failures
        self.timeout = 60  # Seconds before trying HALF_OPEN
        self.success_threshold = 2  # Successes needed to close from HALF_OPEN
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None

    async def call(self, func: Callable, *args, **kwargs):
        """Execute function through circuit breaker"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError("MT4 connection circuit is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

**Exponential Backoff**:
- Initial retry: 1 second
- Subsequent retries: min(2^n seconds, 60 seconds max)
- Reset backoff on successful connection

**Monitoring Integration**:
- Emit metrics: circuit state, failure count, backoff duration
- Alert on circuit OPEN state (indicates MT4 unavailability)
- Log state transitions for debugging

**Alternatives Considered**:
- **Simple Retry Logic**: Rejected as it doesn't prevent overwhelming MT4 with retries
- **Fixed Backoff**: Rejected as it's less adaptive to varying failure durations
- **No Circuit Breaker**: Rejected due to risk of cascading failures

---

## 4. Portfolio Risk Aggregation

### Decision: Real-Time Aggregation with Redis Caching

**Rationale**:
- Need instant portfolio view across all EAs for risk limit enforcement
- Frequent queries (every order submission) require caching
- Redis provides fast in-memory aggregation with pub/sub updates
- PostgreSQL serves as source of truth for audit trail

**Aggregation Model**:

```python
@dataclass
class PortfolioRiskState:
    total_equity: Decimal
    total_margin_used: Decimal
    margin_level: Decimal  # (equity / margin_used) * 100
    total_open_positions: int
    exposure_by_symbol: Dict[str, Decimal]  # symbol -> net exposure
    exposure_by_ea: Dict[int, Decimal]  # magic_number -> margin used
    last_updated: datetime

    def calculate_margin_level(self) -> Decimal:
        if self.total_margin_used == 0:
            return Decimal('999.99')  # No margin used
        return (self.total_equity / self.total_margin_used) * 100
```

**Update Strategy**:

1. **On Position Open/Close**:
   - Update Redis cached aggregates
   - Emit `portfolio_risk_updated` event
   - Persist to PostgreSQL asynchronously

2. **On Account Update** (periodic from MT4):
   - Refresh equity and margin data
   - Recalculate margin level
   - Trigger alerts if limits approached

3. **On Risk Limit Check** (before order submission):
   - Read cached aggregates from Redis
   - Calculate projected impact of new order
   - Approve/reject based on limits

**Risk Limit Enforcement**:

```python
class PortfolioRiskManager:
    MAX_MARGIN_USAGE = Decimal('0.80')  # 80% max margin usage
    MAX_SYMBOL_EXPOSURE = Decimal('100000')  # $100k max per symbol

    async def check_order_risk(self, order: TradingOrder) -> RiskCheckResult:
        portfolio = await self._get_portfolio_state()

        # Check margin limit
        projected_margin = portfolio.total_margin_used + order.required_margin
        if projected_margin / portfolio.total_equity > self.MAX_MARGIN_USAGE:
            return RiskCheckResult(
                approved=False,
                reason="Exceeds portfolio margin limit (80%)"
            )

        # Check symbol exposure limit
        current_exposure = portfolio.exposure_by_symbol.get(order.symbol, 0)
        projected_exposure = current_exposure + order.notional_value
        if abs(projected_exposure) > self.MAX_SYMBOL_EXPOSURE:
            return RiskCheckResult(
                approved=False,
                reason=f"Exceeds symbol exposure limit for {order.symbol}"
            )

        return RiskCheckResult(approved=True)
```

**Performance Considerations**:
- Redis read latency: <5ms
- Aggregation update: <10ms
- PostgreSQL async write: non-blocking
- Total risk check overhead: <20ms (within 500ms order target)

**Alternatives Considered**:
- **Real-Time DB Aggregation**: Rejected due to high latency (100ms+)
- **In-Memory Only**: Rejected due to loss of audit trail and restart data loss
- **Per-EA Risk Only**: Rejected as it doesn't prevent portfolio over-leverage

---

## 5. Event Schema Design

### Decision: Versioned JSON Schema with Backward Compatibility

**Rationale**:
- Event-driven architecture requires stable schemas
- Versioning enables evolution without breaking consumers
- JSON provides human-readable debugging
- Pydantic validation ensures type safety

**Event Schema Structure**:

```python
class BaseEvent(BaseModel):
    event_type: str
    version: str  # Semantic versioning: "1.0.0"
    timestamp: datetime
    correlation_id: str  # UUID for request tracing
    source: str  # e.g., "mt4_integration_service"

class OrderConfirmedEvent(BaseEvent):
    event_type: Literal["order_confirmed"] = "order_confirmed"
    version: Literal["1.0.0"] = "1.0.0"
    data: OrderConfirmedData

class OrderConfirmedData(BaseModel):
    order_id: str
    magic_number: int
    ticket_number: int  # MT4 ticket
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: Decimal
    execution_price: Decimal
    execution_time: datetime
```

**Versioning Strategy**:

1. **Major Version** (e.g., 2.0.0):
   - Breaking changes (field removal, type changes)
   - Requires consumer updates
   - Old version deprecated with 6-month notice

2. **Minor Version** (e.g., 1.1.0):
   - New optional fields
   - Backward compatible
   - Old consumers continue working

3. **Patch Version** (e.g., 1.0.1):
   - Documentation or validation updates
   - No schema changes

**Backward Compatibility Rules**:
- Never remove required fields
- New fields must be optional with defaults
- Type changes require major version bump
- Maintain support for N-1 major version

**Event Registry**:

```python
EVENT_SCHEMAS = {
    "order_confirmed": {
        "1.0.0": OrderConfirmedEventV1,
        "1.1.0": OrderConfirmedEventV1_1,  # Future version
    },
    "position_updated": {
        "1.0.0": PositionUpdatedEventV1,
    },
    "market_tick": {
        "1.0.0": MarketTickEventV1,
    },
}

def get_event_schema(event_type: str, version: str) -> Type[BaseEvent]:
    """Get schema class for event type and version"""
    return EVENT_SCHEMAS[event_type][version]
```

**Validation**:
- All events validated with Pydantic on publish
- Consumer can choose to validate or trust
- Schema violations logged with correlation ID

**Alternatives Considered**:
- **Protobuf**: Rejected due to less human-readable debugging
- **Avro**: Rejected due to additional complexity for schema registry
- **Unversioned Events**: Rejected as it prevents safe evolution

---

## Summary of Key Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| **Encryption** | CurveZMQ with PyZMQ | Native ZMQ solution, minimal overhead, no extra infrastructure |
| **Multi-EA** | Connection pool with port offsets | Avoids conflicts, scalable to 100 EAs, clear magic number tracking |
| **Resilience** | Circuit breaker + exponential backoff | Prevents cascading failures, adaptive retry strategy |
| **Risk** | Redis-cached aggregation + PostgreSQL | Fast reads (<5ms), audit trail, real-time updates |
| **Events** | Versioned JSON with Pydantic | Backward compatible, type-safe, human-readable |

---

## Implementation Priorities

1. **Phase 1** (Foundation):
   - MT4 connection client with CurveZMQ
   - Connection pool for multi-EA support
   - Basic event publishing

2. **Phase 2** (Resilience):
   - Circuit breaker implementation
   - Connection health monitoring
   - Automatic reconnection

3. **Phase 3** (Risk Management):
   - Portfolio risk aggregation
   - Redis caching layer
   - Risk limit enforcement

4. **Phase 4** (Observability):
   - Metrics instrumentation
   - Audit logging
   - Tracing integration

---

## Open Questions / Future Research

1. **Load Testing**: Validate 100 concurrent EA connections under realistic trading load
2. **Key Rotation**: Test hot key rotation without downtime
3. **Failover**: Research multi-instance deployment with connection takeover
4. **Compression**: Evaluate message compression for high-frequency market data streams

---

**Research Complete**: All critical technology decisions made. Ready for Phase 1 design.
