# RiseTrader Testing - Quick Reference Card

## Running Tests

```bash
# All tests
./run_tests.sh all
pytest

# Specific category
./run_tests.sh unit
./run_tests.sh integration
./run_tests.sh e2e
./run_tests.sh performance

# By marker
pytest -m critical
pytest -m agent
pytest -m api

# With coverage
./run_tests.sh coverage
pytest --cov=src --cov-report=html

# Fast tests only
pytest -m "not slow"

# Watch mode
pytest-watch
```

## Test Markers

```python
@pytest.mark.agent          # Agent tests
@pytest.mark.api            # API tests
@pytest.mark.database       # Database tests
@pytest.mark.integration    # Integration tests
@pytest.mark.e2e            # End-to-end tests
@pytest.mark.critical       # Critical path
@pytest.mark.slow           # Slow tests
@pytest.mark.performance    # Performance tests
```

## Common Fixtures

```python
# Database
async def test_db(db_session):
    # Use db_session

# Agents
async def test_agent(signal_generator_agent):
    # Use agent

# Mock data
def test_data(sample_signal, sample_market_data):
    # Use sample data

# API
def test_api(api_client):
    response = api_client.get("/api/v1/agents")
```

## Writing Tests

```python
import pytest

class TestMyFeature:
    """Test MyFeature functionality"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_my_async_feature(self, fixture):
        """Test description"""
        result = await fixture.do_something()
        assert result == expected
    
    @pytest.mark.api
    def test_my_sync_feature(self, api_client):
        """Test API endpoint"""
        response = api_client.get("/endpoint")
        assert response.status_code == 200
```

## Debugging

```bash
# Verbose output
pytest -vv -s

# Drop to debugger on failure
pytest --pdb

# Show slowest tests
pytest --durations=10

# Run specific test
pytest tests/unit/agents/test_signal_generator.py::TestSignalGeneration::test_generate_signal
```

## Coverage

```bash
# Generate report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html

# Fail if below threshold
pytest --cov=src --cov-fail-under=85
```

## Performance Targets

| Component | Target | Test |
|-----------|--------|------|
| Event Processing | <50ms | test_event_bus.py |
| Signal Generation | <50ms | test_signal_generator.py |
| Risk Validation | <30ms | test_risk_manager.py |
| Order Execution | <500ms | test_execution_agent.py |
| API Response | <200ms | test_agent_routes.py |
| Event Throughput | 100+/sec | test_throughput.py |

## File Locations

```
tests/
├── conftest.py           # Fixtures
├── unit/                 # Unit tests
│   ├── agents/          # Agent tests
│   ├── api/             # API tests
│   └── database/        # Database tests
├── integration/          # Integration tests
├── e2e/                 # End-to-end tests
└── performance/         # Performance tests
```

## Quick Checks

```bash
# Before commit
pytest -m critical --maxfail=1

# Full validation
pytest --cov=src --cov-fail-under=85

# Fast feedback
pytest tests/unit/ --maxfail=3

# Clean artifacts
./run_tests.sh clean
```

## Common Issues

1. **Import errors**: Check PYTHONPATH includes `src/`
2. **Async warnings**: Use `@pytest.mark.asyncio`
3. **Fixtures not found**: Check `conftest.py` loaded
4. **Slow tests**: Use `-m "not slow"` to exclude
5. **Coverage missing**: Ensure running from project root

## Documentation

- **Full Guide**: tests/README.md
- **Implementation**: TESTING_COMPLETE_SUMMARY.md
- **File List**: TEST_FILES_SUMMARY.md
- **Final Report**: TESTING_SUITE_FINAL_REPORT.md

## Help

```bash
# Show all markers
pytest --markers

# Show fixtures
pytest --fixtures

# Show help
./run_tests.sh help
pytest --help
```

---

**Quick Start**: `./run_tests.sh all`  
**Documentation**: `tests/README.md`  
**Coverage Target**: 85%+
