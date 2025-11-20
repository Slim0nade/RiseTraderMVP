# RiseTrader Testing Suite

Comprehensive testing suite for the RiseTrader algorithmic trading platform.

## Overview

This testing suite provides:
- **Unit tests** for individual components (agents, database, API)
- **Integration tests** for multi-component workflows
- **End-to-end tests** for complete trading cycles
- **Performance tests** for throughput and latency validation
- **85%+ code coverage** target

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── test_config.py                 # Test-specific settings
├── unit/                          # Unit tests (fast, isolated)
│   ├── agents/                    # Agent tests
│   │   ├── test_event_bus.py
│   │   ├── test_agent_registry.py
│   │   ├── test_signal_generator.py
│   │   ├── test_risk_manager.py
│   │   └── test_execution_agent.py
│   ├── api/                       # API route tests
│   │   ├── test_agent_routes.py
│   │   └── test_trading_routes.py
│   └── database/                  # Database tests
│       └── test_models.py
├── integration/                   # Integration tests (multi-component)
│   └── agents/
│       ├── test_mcp_server.py
│       └── test_agent_coordination.py
├── e2e/                          # End-to-end tests (full system)
│   ├── test_complete_trading_cycle.py
│   └── test_risk_scenarios.py
└── performance/                   # Performance tests
    └── test_throughput.py
```

## Running Tests

### All Tests
```bash
pytest
```

### By Category
```bash
# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# E2E tests
pytest tests/e2e/

# Performance tests
pytest tests/performance/
```

### By Marker
```bash
# Critical path tests only
pytest -m critical

# Agent tests
pytest -m agent

# API tests
pytest -m api

# Slow tests only
pytest -m slow

# Exclude slow tests
pytest -m "not slow"
```

### With Coverage
```bash
# Generate coverage report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

### Specific Test File
```bash
pytest tests/unit/agents/test_signal_generator.py

# Specific test class
pytest tests/unit/agents/test_signal_generator.py::TestSignalGeneration

# Specific test
pytest tests/unit/agents/test_signal_generator.py::TestSignalGeneration::test_generate_signal
```

### Verbose Output
```bash
# Show test names
pytest -v

# Show print statements
pytest -s

# Both
pytest -vs
```

### Fast Tests Only
```bash
# Run unit tests (fast)
pytest tests/unit/ --durations=10
```

## Test Markers

Tests are marked with pytest markers for selective execution:

| Marker | Description | Usage |
|--------|-------------|-------|
| `@pytest.mark.agent` | Agent system tests | `pytest -m agent` |
| `@pytest.mark.database` | Database tests | `pytest -m database` |
| `@pytest.mark.api` | API endpoint tests | `pytest -m api` |
| `@pytest.mark.integration` | Integration tests | `pytest -m integration` |
| `@pytest.mark.e2e` | End-to-end tests | `pytest -m e2e` |
| `@pytest.mark.slow` | Slow tests (>5s) | `pytest -m slow` |
| `@pytest.mark.critical` | Critical path tests | `pytest -m critical` |
| `@pytest.mark.performance` | Performance tests | `pytest -m performance` |
| `@pytest.mark.security` | Security tests | `pytest -m security` |

## Fixtures

### Database Fixtures
- `async_engine` - Async SQLite engine
- `db_session` - Async database session
- `sample_market_data` - Sample OHLCV data
- `sample_position` - Sample position object

### Agent Fixtures
- `event_bus` - Event bus for agent communication
- `agent_registry` - Agent registry for health monitoring
- `signal_generator_agent` - SignalGeneratorAgent instance
- `risk_manager_agent` - RiskManagerAgent instance
- `execution_agent` - ExecutionAgent instance

### Mock Fixtures
- `redis_client` - Mocked Redis client
- `mock_mt4_connection` - Mocked MT4 ZMQ connection
- `mock_mt4_order_response` - Mocked MT4 order response

### Data Fixtures
- `sample_signal` - Sample trading signal
- `sample_forecast` - Sample ML forecast
- `sample_regime` - Sample market regime
- `price_history_100` - 100 bars of price history

### API Fixtures
- `api_client` - FastAPI TestClient
- `auth_headers` - Authentication headers

## Writing New Tests

### Unit Test Example
```python
import pytest

class TestMyComponent:
    """Test MyComponent functionality"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_my_feature(self, my_fixture):
        """Test specific feature"""
        result = await my_fixture.do_something()
        
        assert result is not None
        assert result.status == "success"
```

### Integration Test Example
```python
import pytest
import asyncio

class TestWorkflow:
    """Test multi-component workflow"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.critical
    async def test_complete_flow(self, agent1, agent2, event_bus):
        """Test component A → component B flow"""
        # Setup
        events_received = []
        
        async def handler(event):
            events_received.append(event)
        
        event_bus.subscribe("result_event", "test", handler)
        
        # Execute
        await agent1.trigger_action()
        await asyncio.sleep(0.5)
        
        # Verify
        assert len(events_received) > 0
```

### E2E Test Example
```python
import pytest

class TestCompleteSystem:
    """Test complete system functionality"""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.critical
    async def test_full_trading_cycle(
        self,
        all_agents,
        event_bus,
        db_session,
    ):
        """Test tick → signal → risk → execution → monitoring"""
        # Send market tick
        # Wait for signal generation
        # Verify risk validation
        # Confirm execution
        # Check monitoring updated
```

## Performance Requirements

Tests validate these performance targets:

| Component | Target | Test |
|-----------|--------|------|
| Event Processing | <50ms | `test_event_bus.py::test_event_processing_latency` |
| Signal Generation | <50ms | `test_signal_generator.py::test_signal_generation_performance` |
| Risk Validation | <30ms | `test_risk_manager.py::test_validation_performance` |
| Order Execution | <500ms | `test_execution_agent.py::test_execution_performance` |
| API Response | <200ms | `test_agent_routes.py::test_api_latency` |
| Event Throughput | 100+/sec | `test_throughput.py::test_event_bus_throughput` |

## Coverage Targets

Minimum coverage requirements:

- **Overall**: 85%+
- **Critical paths**: 95%+
- **Agents**: 90%+
- **Database**: 85%+
- **API**: 80%+

### Check Coverage
```bash
# Generate report
pytest --cov=src --cov-report=term-missing

# Detailed HTML report
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Fail if below threshold
pytest --cov=src --cov-fail-under=85
```

## Continuous Integration

### Pre-Commit Checks
```bash
# Run critical tests before commit
pytest -m critical --maxfail=1

# Fast tests only
pytest tests/unit/ --maxfail=1
```

### CI Pipeline
```bash
# Full test suite
pytest --cov=src --cov-report=xml --cov-fail-under=85

# Performance validation
pytest -m performance --durations=10

# Security tests
pytest -m security
```

## Troubleshooting

### Tests Failing

1. **Database connection errors**
   - Tests use in-memory SQLite by default
   - Check `conftest.py` database setup

2. **Redis connection errors**
   - Tests use mocked Redis by default
   - Check `redis_client` fixture in `conftest.py`

3. **MT4 connection errors**
   - Tests use mocked MT4 by default
   - Check `mock_mt4_connection` fixture

4. **Async test warnings**
   - Ensure `@pytest.mark.asyncio` decorator is used
   - Check `pytest-asyncio` is installed

### Slow Tests

```bash
# Find slow tests
pytest --durations=10

# Run fast tests only
pytest -m "not slow"

# Parallel execution
pytest -n auto  # Requires pytest-xdist
```

### Debug Tests

```bash
# Show print statements
pytest -s

# Drop into debugger on failure
pytest --pdb

# Verbose output
pytest -vv

# Show local variables on failure
pytest -l
```

## Best Practices

1. **Test Independence**: Each test should be independent
2. **Use Fixtures**: Reuse setup code via fixtures
3. **Mock External Services**: Don't call real MT4, Redis in unit tests
4. **Test Edge Cases**: Include error paths and boundary conditions
5. **Performance Tests**: Validate latency and throughput requirements
6. **Clear Names**: Test names should describe what's being tested
7. **Documentation**: Add docstrings explaining test purpose
8. **Markers**: Use appropriate markers for test categorization

## Adding New Tests

When adding new features:

1. **Write tests first** (TDD approach)
2. **Unit tests** for individual components
3. **Integration tests** for component interactions
4. **E2E tests** if trading flow is affected
5. **Performance tests** for critical paths
6. **Update fixtures** if new test data needed
7. **Update documentation** if new patterns introduced

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [Testing best practices](https://docs.pytest.org/en/latest/goodpractices.html)
