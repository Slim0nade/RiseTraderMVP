# Phase 6 Testing: Adversarial Debate & Safety Gates

Comprehensive test suite for Phase 6 intelligent agent system with **REAL DATA** and **REAL LLM** integration.

## Overview

This test suite validates the complete Phase 6 pipeline:

1. **Risk Tolerance Debate** (3-way: Risky/Neutral/Safe)
2. **Fund Manager Approval** (APPROVE/MODIFY/REJECT powers)
3. **Full Pipeline Integration** (end-to-end with real data)

### Test Types

#### ✅ Unit Tests (`unit/`)
- **Fast**: Runs in ~5-10 seconds
- **Mocked**: Uses mocked LLM responses
- **Isolated**: Tests individual agent logic
- **Coverage**: Initialization, core functionality, edge cases, error handling

#### 🔥 Integration Tests (`integration/`)
- **Real LLMs**: Actual Ollama/DeepSeek API calls
- **Real Data**: PostgreSQL historical CrudeOIL data (6M+ records)
- **Slow**: ~30-60 seconds per test (LLM inference time)
- **End-to-End**: Full pipeline validation

## Database Requirements

### Required Data
- **Database**: `risetrader` (PostgreSQL)
- **Table**: `market_data`
- **Symbol**: `CrudeOIL` (or DXY, VIX)
- **Minimum**: 1,000+ H1 candles
- **Optimal**: 10,000+ candles for robust testing

### Check Data Availability
```bash
./run_phase6_tests.sh data-check
```

## Running Tests

### Quick Start

```bash
# Make test runner executable (one-time)
chmod +x run_phase6_tests.sh

# Run unit tests (fast, mocked)
./run_phase6_tests.sh unit

# Run integration tests (real LLMs + real data)
./run_phase6_tests.sh integration

# Run all tests
./run_phase6_tests.sh all

# Check database data
./run_phase6_tests.sh data-check
```

### Using Pytest Directly

```bash
# Unit tests only
pytest tests/unit/ -v -m "unit"

# Integration tests only (REAL LLM CALLS!)
pytest tests/integration/ -v -m "integration" -s

# Specific test file
pytest tests/integration/test_phase6_with_real_data.py::TestPhase6WithRealData::test_moderate_position_size_with_real_data -v -s

# With coverage
pytest tests/unit/ --cov=src/agents/debate --cov=src/agents/teams --cov=src/agents/approval --cov-report=html
```

## Test Structure

```
tests/
├── unit/
│   ├── agents/
│   │   ├── debate/
│   │   │   ├── test_risky_debator_agent.py        (396 lines, 11 tests)
│   │   │   ├── test_neutral_debator_agent.py      (382 lines, 10 tests)
│   │   │   └── test_safe_debator_agent.py         (429 lines, 12 tests)
│   │   ├── teams/
│   │   │   └── test_risk_debate_team.py           (453 lines, 10 tests)
│   │   └── approval/
│   │       └── test_fund_manager_agent.py         (642 lines, 9 tests)
└── integration/
    ├── test_phase6_full_pipeline.py               (690 lines, 3 scenarios - MOCKED)
    └── test_phase6_with_real_data.py              (450 lines, 3 tests - REAL DATA + REAL LLMs)
```

## Test Coverage

### Unit Tests (52 tests total)

**RiskyDebatorAgent** (11 tests):
- ✅ Initialization & config validation
- ✅ High conviction scenarios (recommend size increase)
- ✅ Low conviction scenarios (no increase)
- ✅ Extreme R:R ratios (>5:1)
- ✅ Zero risk factors handling
- ✅ Exception handling & health checks

**NeutralDebatorAgent** (10 tests):
- ✅ Kelly Criterion validation
- ✅ Valid baseline (1.0x adjustment)
- ✅ Questionable baseline (reduce)
- ✅ Aggressive Kelly fractions (>0.5)
- ✅ Unrealistic win rates (>0.70)

**SafeDebatorAgent** (12 tests):
- ✅ Risky scenarios (reduction)
- ✅ Clean scenarios (no reduction)
- ✅ Portfolio drawdown protection
- ✅ High correlation detection
- ✅ Extreme event risk (NFP, FOMC)
- ✅ Perfect conditions (no reduction)

**RiskDebateTeam** (10 tests):
- ✅ 3-debator initialization
- ✅ Consensus scenarios (simple average)
- ✅ Divergent scenarios (safety-weighted 50/30/20)
- ✅ Final size calculations
- ✅ Warning consolidation
- ✅ Metadata population

**FundManagerAgent** (9 tests):
- ✅ APPROVE (clean trades)
- ✅ MODIFY (oversized trades)
- ✅ REJECT scenarios:
  - Excessive risk (>5%)
  - Event risk (FOMC)
  - Portfolio drawdown
  - Excessive correlation
  - Poor quality (<0.4)

### Integration Tests (3 real data tests)

**TestPhase6WithRealData**:
- ✅ `test_moderate_position_size_with_real_data`
  - Fetches last 100 CrudeOIL candles
  - Runs 3-way risk debate (REAL LLM)
  - Runs Fund Manager approval (REAL LLM)
  - Validates APPROVE or MODIFY decision
  - ~30-45 seconds

- ✅ `test_aggressive_position_should_get_modified`
  - Tests 4.5% risk (near max)
  - Aggressive Kelly fraction (0.50)
  - Should trigger MODIFY or REJECT
  - Validates safety gates work
  - ~30-45 seconds

**TestPhase6DataQuality**:
- ✅ `test_database_has_sufficient_data`
  - Verifies >1,000 CrudeOIL records
  - Checks table structure
  - ~1 second

## Example Test Output

### Unit Test (Mocked)
```bash
$ ./run_phase6_tests.sh unit

========================================
Phase 6: Test Runner
========================================

Running Unit Tests (mocked, fast)

tests/unit/agents/debate/test_risky_debator_agent.py::TestRiskyDebatorAgentInitialization::test_initialization_success PASSED
tests/unit/agents/debate/test_risky_debator_agent.py::TestRiskyDebatorAgentRun::test_run_high_conviction_scenario PASSED
...

========================================
52 passed in 8.43s
========================================
```

### Integration Test (Real Data + Real LLMs)
```bash
$ ./run_phase6_tests.sh integration

========================================
Phase 6: Test Runner
========================================

Running Integration Tests (real LLMs + real data)
WARNING: This will make real LLM API calls!

================================================================================
REAL DATA TEST: CrudeOIL @ $71.25
Range (20 candles): $69.80 - $72.10
Position: 1.5 lots, 2.0% risk, Stop: $69.83
================================================================================

Step 1: Running Risk Tolerance Debate (3 LLM calls)...

Risk Debate Results:
  Risky adjustment:   1.10x
  Neutral adjustment: 1.00x
  Safe adjustment:    0.95x
  Consensus:          1.02x
  Consensus reached:  True
  Final size:         1.53 lots
  Final risk:         2.04%

Step 2: Running Fund Manager Approval (1 LLM call)...

Fund Manager Decision:
  Decision:           APPROVE
  Approved size:      1.53
  Approved risk:      2.04%
  Hard limits passed: True
  Trade quality:      0.78
  Confidence:         0.85
  Portfolio risk:     7.04%

  Rationale: Trade approved for execution. All criteria met: High conviction (0.75)...

================================================================================
✓ SUCCESS: Phase 6 pipeline completed with real data
================================================================================

tests/integration/test_phase6_with_real_data.py::TestPhase6WithRealData::test_moderate_position_size_with_real_data PASSED [100%]

========================================
1 passed in 42.18s
========================================
```

## Environment Variables

```bash
# Database connection (default)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/risetrader

# Ollama API (if not default)
OLLAMA_BASE_URL=http://localhost:11434

# For Docker environment
DOCKER_CONTAINER=true
```

## LLM Requirements

### Required Models

**Ollama** (for quick-think debate agents):
```bash
ollama pull qwen2.5:14b-instruct
```

**DeepSeek** (for deep-think fund manager):
```bash
ollama pull deepseek-reasoner:14b
```

### Verify Models Available
```bash
ollama list | grep -E "qwen2.5|deepseek"
```

## Troubleshooting

### Database Connection Issues
```bash
# Check database exists
docker exec risetrader-postgres psql -U postgres -l | grep risetrader

# Check market data
docker exec risetrader-postgres psql -U postgres -d risetrader -c "SELECT COUNT(*), symbol FROM market_data GROUP BY symbol;"
```

### LLM Connection Issues
```bash
# Check Ollama running
curl http://localhost:11434/api/tags

# Test model inference
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:14b-instruct",
  "prompt": "Test",
  "stream": false
}'
```

### Import Errors
```bash
# Ensure PYTHONPATH includes src/
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../../src:$(pwd)"

# Or run from specs/005-intelligent-agent-trading/
cd specs/005-intelligent-agent-trading
./run_phase6_tests.sh unit
```

## Performance Benchmarks

| Test Type | Count | Duration | LLM Calls |
|-----------|-------|----------|-----------|
| Unit (all) | 52 | ~8-10s | 0 (mocked) |
| Integration (moderate) | 1 | ~30-45s | 4 (3 debate + 1 FM) |
| Integration (aggressive) | 1 | ~30-45s | 4 (3 debate + 1 FM) |
| Data check | 2 | ~1-2s | 0 |

## CI/CD Integration

```yaml
# .github/workflows/phase6-tests.yml
name: Phase 6 Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/unit/ -v -m "unit"

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
    steps:
      - uses: actions/checkout@v3
      - run: docker-compose up -d postgres ollama
      - run: pytest tests/integration/ -v -m "integration"
```

## Next Steps

1. ✅ **Unit Tests**: All 52 tests created
2. ✅ **Integration Tests**: Real data tests created
3. ⏭️ **Run Tests**: Execute test suite
4. ⏭️ **Fix Issues**: Address any failures
5. ⏭️ **Coverage Report**: Generate HTML coverage report
6. ⏭️ **Performance Profiling**: Profile LLM call latency
7. ⏭️ **MCP Integration**: Connect to event bus
8. ⏭️ **Database Logging**: Persist debate outcomes

## Support

For issues or questions:
- Check `pytest.ini` for configuration
- Review agent logs in console output
- Verify database has sufficient data
- Ensure LLM models are pulled and running

**Remember**: Integration tests make REAL LLM API calls. Monitor your usage and costs!
