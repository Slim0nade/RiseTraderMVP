# Quickstart Guide: MT4 Integration

**Feature**: MT4 Integration
**Date**: 2025-11-20
**For**: Developers implementing or testing MT4 integration

## Overview

This guide will help you set up a local development environment for MT4 integration, run tests, and verify end-to-end functionality.

---

## Prerequisites

### Required Software

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15+ (or use Docker)
- Redis 7+ (or use Docker)
- MetaTrader 4 (for E2E testing)

### Python Dependencies

```bash
pip install -r requirements.txt
```

Key packages:
- `pyzmq` - ZeroMQ Python bindings
- `fastapi` - REST API framework
- `sqlalchemy[asyncio]` - Async database ORM
- `redis` - Redis client
- `pydantic` - Data validation
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support

---

## Quick Start (5 minutes)

### 1. Clone and Setup

```bash
# Navigate to project root
cd RiseTraderMVP

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
```

### 2. Start Infrastructure

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Run database migrations
alembic upgrade head
```

### 3. Generate Encryption Keys

```bash
# Generate CurveZMQ keypairs
python scripts/generate_zmq_keys.py

# Output will be:
# CLIENT_SECRET_KEY=<40-char-z85>
# CLIENT_PUBLIC_KEY=<40-char-z85>
# SERVER_PUBLIC_KEY=<40-char-z85> (for MT4 EA config)
```

Add keys to `.env`:
```env
ZMQ_CLIENT_SECRET_KEY=<client-secret>
ZMQ_CLIENT_PUBLIC_KEY=<client-public>
ZMQ_SERVER_PUBLIC_KEY=<server-public>
```

### 4. Run Tests

```bash
# Run all tests
pytest tests/unit/test_mt4_*.py -v

# Run with coverage
pytest tests/unit/test_mt4_*.py --cov=src/trading/execution --cov-report=html

# View coverage report
open htmlcov/index.html
```

### 5. Start MT4 Integration Service

```bash
# Start the service
uvicorn src.api.main:app --reload --port 8003

# Verify health
curl http://localhost:8003/health

# Check API docs
open http://localhost:8003/docs
```

---

## Development Workflow

### Running Unit Tests

```bash
# Test MT4 client
pytest tests/unit/test_mt4_client.py -v

# Test connection pool
pytest tests/unit/test_mt4_connection_pool.py -v

# Test encryption
pytest tests/unit/test_mt4_encryption.py -v

# Test integration service
pytest tests/unit/test_mt4_integration_service.py -v
```

### Running Integration Tests

Integration tests require a mock MT4 EA or real MT4 instance:

```bash
# Start mock MT4 EA (Python simulator)
python tests/integration/mock_mt4_ea.py &

# Run integration tests
pytest tests/integration/test_mt4_communication.py -v

# Test multi-EA coordination
pytest tests/integration/test_multi_ea_coordination.py -v

# Stop mock EA
pkill -f mock_mt4_ea.py
```

### Testing with Real MT4

1. **Configure MT4 EA**:
   - Copy `mt4/experts/HelloWorldServerEA.mq4` to MT4's Experts folder
   - Edit EA parameters:
     - `ZMQ_SERVER_PUBLIC_KEY` = your generated server key
     - `REP_PORT` = 5555
     - `PUB_PORT` = 5556
   - Compile EA in MetaEditor
   - Attach EA to a chart (e.g., CrudeOIL M1)

2. **Register EA Connection**:
```bash
curl -X POST http://localhost:8003/api/v1/mt4/connections \
  -H "Content-Type: application/json" \
  -d '{
    "ea_id": "crude_oil_ea_1",
    "symbol": "CrudeOIL",
    "mt4_server_host": "75.154.254.186"
  }'
```

3. **Test Connection**:
```bash
# Get connection status
curl http://localhost:8003/api/v1/mt4/connections/crude_oil_ea_1

# Should show status: ACTIVE if connection successful
```

---

## Configuration

### Environment Variables

Create `.env` file with:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/risetrader

# Redis
REDIS_URL=redis://localhost:6379/0

# MT4 Connection
MT4_DEFAULT_HOST=75.154.254.186
MT4_BASE_REP_PORT=5555
MT4_BASE_PUB_PORT=5556

# ZMQ Encryption
ZMQ_CLIENT_SECRET_KEY=your-client-secret-key-40-chars-z85
ZMQ_CLIENT_PUBLIC_KEY=your-client-public-key-40-chars-z85
ZMQ_SERVER_PUBLIC_KEY=your-server-public-key-40-chars-z85

# Feature Flags
ENABLE_LIVE_TRADING=false  # ALWAYS false until ready for production
ENABLE_PAPER_TRADING=true

# Risk Limits
MAX_PORTFOLIO_MARGIN_PCT=80  # 80% max margin usage
MAX_SYMBOL_EXPOSURE=100000   # $100k max per symbol
MAX_EA_COUNT=100             # Maximum EAs per instance

# Performance
ZMQ_COMMAND_TIMEOUT_MS=5000  # 5 seconds
ZMQ_QUERY_TIMEOUT_MS=10000   # 10 seconds
CONNECTION_HEALTH_CHECK_INTERVAL_SEC=30

# Observability
LOG_LEVEL=INFO
PROMETHEUS_PORT=9090
JAEGER_AGENT_HOST=localhost
JAEGER_AGENT_PORT=6831
```

### YAML Configuration

Edit `config/mt4_config.yaml`:

```yaml
mt4_integration:
  max_concurrent_eas: 100
  port_allocation:
    base_rep_port: 5555
    base_pub_port: 5556
    port_increment: 2

  encryption:
    enabled: true
    key_rotation_days: 90

  circuit_breaker:
    failure_threshold: 5
    timeout_seconds: 60
    success_threshold: 2

  reconnection:
    initial_backoff_seconds: 1
    max_backoff_seconds: 60
    max_retries: 10

  risk_limits:
    max_margin_usage_pct: 80.0
    max_symbol_exposure: 100000.0
    margin_warning_level_pct: 120.0

  health_monitoring:
    heartbeat_interval_seconds: 30
    heartbeat_timeout_seconds: 90
```

---

## Testing Scenarios

### Scenario 1: Basic Order Submission

```python
# tests/integration/test_basic_order.py
import pytest
from src.services.mt4_integration_service import MT4IntegrationService

@pytest.mark.asyncio
async def test_submit_market_order(mt4_service: MT4IntegrationService):
    # Submit BUY order
    order = await mt4_service.submit_market_order(
        ea_id="crude_oil_ea_1",
        symbol="CrudeOIL",
        direction="BUY",
        volume=0.1,
        stop_loss=75.50,
        take_profit=80.00
    )

    # Verify order confirmed
    assert order.status == "CONFIRMED"
    assert order.ticket_number is not None
    assert order.magic_number == 100001
```

### Scenario 2: Multi-EA Risk Aggregation

```python
# tests/integration/test_multi_ea_risk.py
import pytest

@pytest.mark.asyncio
async def test_portfolio_risk_aggregation(mt4_service):
    # Register 3 EAs
    ea1 = await mt4_service.register_ea("crude_oil_ea_1", "CrudeOIL")
    ea2 = await mt4_service.register_ea("eurusd_ea_1", "EURUSD")
    ea3 = await mt4_service.register_ea("gbpusd_ea_1", "GBPUSD")

    # Submit orders from each EA
    await mt4_service.submit_market_order(ea1.ea_id, "CrudeOIL", "BUY", 0.1)
    await mt4_service.submit_market_order(ea2.ea_id, "EURUSD", "SELL", 1.0)
    await mt4_service.submit_market_order(ea3.ea_id, "GBPUSD", "BUY", 0.5)

    # Get portfolio risk
    risk_state = await mt4_service.get_portfolio_risk()

    # Verify aggregation
    assert risk_state.total_open_positions == 3
    assert len(risk_state.exposure_by_ea) == 3
    assert risk_state.margin_level > 100.0
```

### Scenario 3: Circuit Breaker Activation

```python
# tests/integration/test_circuit_breaker.py
import pytest
from src.trading.execution.mt4_client import CircuitBreakerOpenError

@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(mt4_client):
    # Simulate 5 consecutive failures
    for i in range(5):
        with pytest.raises(Exception):
            await mt4_client.send_command({"command": "test_connection"})

    # Circuit should now be OPEN
    assert mt4_client.circuit_breaker.state == "OPEN"

    # Next call should fail immediately without attempting connection
    with pytest.raises(CircuitBreakerOpenError):
        await mt4_client.send_command({"command": "test_connection"})
```

---

## Troubleshooting

### Connection Failures

**Problem**: EA connection shows status `ERROR`

**Solutions**:
1. Verify MT4 EA is running and attached to chart
2. Check firewall allows connections on ports 5555-5556
3. Verify ZMQ keys match between service and EA
4. Check MT4 Expert log for error messages
5. Test basic ZMQ connectivity:
```python
import zmq
context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://75.154.254.186:5555")
socket.send_json({"command": "test_connection"})
response = socket.recv_json()
print(response)
```

### Order Rejections

**Problem**: Orders rejected with "Insufficient margin"

**Solutions**:
1. Check account balance in MT4
2. Verify margin requirements for symbol
3. Check portfolio risk state for cumulative margin usage
4. Reduce position size or close existing positions

### Slow Response Times

**Problem**: Orders taking >500ms to confirm

**Solutions**:
1. Check network latency to MT4 server:
```bash
ping 75.154.254.186
```
2. Monitor MT4 server load (MT4 terminal may be slow)
3. Check for pending messages in ZMQ queue
4. Verify broker server connectivity in MT4

### Encryption Errors

**Problem**: "Invalid server key" or authentication failures

**Solutions**:
1. Regenerate keys and update both service and EA config
2. Verify keys are Z85-encoded (40 characters)
3. Check no trailing whitespace in .env file
4. Test without encryption first (set `encryption_enabled=false`)

---

## Next Steps

After completing this quickstart:

1. **Review Architecture**: Read [plan.md](./plan.md) for detailed design
2. **Understand Data Model**: See [data-model.md](./data-model.md) for entities
3. **API Contracts**: Explore [contracts/](./contracts/) for message schemas
4. **Implement Tasks**: See [tasks.md](./tasks.md) for implementation checklist

---

## Useful Commands

```bash
# Database
alembic revision --autogenerate -m "Add MT4 tables"
alembic upgrade head
alembic downgrade -1

# Testing
pytest -v                              # All tests
pytest -k mt4                          # MT4-related tests only
pytest --cov --cov-report=html         # With coverage
pytest -x                              # Stop on first failure
pytest --pdb                           # Drop into debugger on failure

# Development
uvicorn src.api.main:app --reload     # API server with auto-reload
python -m src.trading.execution.mt4_client  # Test MT4 client standalone

# Monitoring
docker-compose logs -f mt4-integration
docker stats
redis-cli monitor                      # Watch Redis activity

# Production
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml logs -f
```

---

## Resources

- **MT4 Documentation**: https://docs.mql4.com/
- **ZeroMQ Guide**: https://zeromq.org/get-started/
- **PyZMQ Docs**: https://pyzmq.readthedocs.io/
- **CurveZMQ Security**: https://rfc.zeromq.org/spec:26/CURVEZMQ/
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

---

**Happy Coding!** If you encounter issues, check the troubleshooting section or reach out to the development team.
