# Quickstart: Enhanced Stealth Stop Manager

**Feature**: Multi-Layer Risk Protection System
**Audience**: Developers implementing or testing this feature
**Prerequisites**: Python 3.11+, Docker, basic understanding of async/await

## Overview

This guide helps you set up, test, and deploy the enhanced stealth stop manager with four critical protection mechanisms:

1. **Disaster Stop Protection** - Automatic initial stop loss on every position
2. **Early Profit Locking** - Trailing begins at 0.5× ATR (lowered from 1.0×)
3. **Profit Erosion Detection** - Tightens stops when profit erodes from highwater
4. **Comprehensive Alerting** - Logs all protection actions with structured logging

## Quick Setup (5 minutes)

### 1. Clone and Install Dependencies

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP

# Install Python dependencies (if not already installed)
pip install -r requirements.txt

# Additional dependencies for this feature
pip install pyyaml jsonschema watchdog hypothesis pytest-mock
```

### 2. Configure the Service

Create `/config/stealth_stops.yaml` from template:

```bash
cp specs/001-stealth-stop-protection/contracts/stealth_stops.yaml.example config/stealth_stops.yaml
```

**Minimal configuration** (for development):

```yaml
# config/stealth_stops.yaml
defaults:
  disaster_stop_multiplier: 3.0     # 3× ATR initial protection
  trail_trigger_atr: 0.5             # Lowered from 1.0
  breakeven_trigger_atr: 0.5         # Lowered from 1.5
  erosion_threshold_atr: 0.5         # New: profit erosion protection
  erosion_alert_threshold_atr: 0.3   # New: early warning
  monitoring_cycle_seconds: 60

symbol_overrides: {}  # Empty for now

features:
  enable_disaster_stops: true
  enable_profit_erosion: true
  enable_early_breakeven: true
  enable_audit_trail: false  # Optional database logging
  enable_institutional_pricing: true
```

### 3. Verify MT4 Connection

Ensure MT4 is running and accessible:

```bash
# Local network (at home)
export MT4_HOST=192.168.0.123
export MT4_PORT=5555

# Remote (anywhere)
export MT4_HOST=75.154.254.174
export MT4_PORT=5555

# Test connection
python3 -c "
from src.trading.execution.mt4_client import MT4Client
client = MT4Client(host='$MT4_HOST', rep_port=$MT4_PORT)
positions = client.get_open_positions()
print(f'Connected! Found {len(positions)} positions')
"
```

### 4. Run in Development Mode

```bash
# Start service directly (not in Docker)
export PYTHONPATH=$(pwd)
python3 -m src.services.stealth_stop_manager

# You should see:
# ============================================================
# 🚀 Stealth Stop Manager Started (DYNAMIC MODE)
#    MT4: 75.154.254.174:5555
#    Poll interval: 60s
#    Trail Trigger: 0.5x ATR profit  ← NEW (was 1.0x)
#    Breakeven Trigger: 0.5x ATR profit  ← NEW (was 1.5x)
#    Disaster Stops: ENABLED  ← NEW
#    Erosion Protection: ENABLED  ← NEW
# ============================================================
```

## Development Workflow

### TDD Approach (Test-Driven Development)

As per constitution, we write tests FIRST before implementing:

#### Step 1: Write Failing Test

Create `tests/unit/services/test_disaster_stops.py`:

```python
import pytest
from src.services.stealth_stop_manager import StealthStopManager, MonitoredPosition

@pytest.mark.asyncio
async def test_disaster_stop_applied_on_detection():
    """Test FR-002: Disaster stop applied within 10 seconds of position detection"""
    # Arrange
    manager = StealthStopManager(mt4_host="mock", config=DynamicTrailConfig(
        disaster_stop_multiplier=3.0
    ))

    position = MonitoredPosition(
        ticket=12345,
        symbol="CrudeOIL",
        direction="short",
        entry_price=60.00,
        current_stop=0.0,  # No stop set yet
        current_tp=55.00,
        lots=1.0,
        disaster_stop_set=False  # ← This is the key assertion target
    )

    # Mock ATR calculation
    mock_atr = 0.75

    # Act
    disaster_stop = await manager.calculate_disaster_stop(position, mock_atr)

    # Assert
    assert disaster_stop == 62.25  # 60.00 + (3.0 × 0.75) = 62.25
    assert disaster_stop > position.entry_price  # For SHORT, stop must be above entry
```

#### Step 2: Run Test (Should Fail)

```bash
pytest tests/unit/services/test_disaster_stops.py::test_disaster_stop_applied_on_detection -v

# Expected: FAILED (method not implemented yet)
```

#### Step 3: Implement to Make Test Pass

Add method to `StealthStopManager`:

```python
async def calculate_disaster_stop(
    self,
    position: MonitoredPosition,
    atr: float
) -> float:
    """Calculate disaster stop distance using ATR multiplier."""
    multiplier = self.config.disaster_stop_multiplier

    if position.direction == "short":
        # For SHORT: Stop ABOVE entry (price rises → loss)
        disaster_stop = position.entry_price + (multiplier * atr)
    else:
        # For LONG: Stop BELOW entry (price falls → loss)
        disaster_stop = position.entry_price - (multiplier * atr)

    return disaster_stop
```

#### Step 4: Run Test (Should Pass)

```bash
pytest tests/unit/services/test_disaster_stops.py::test_disaster_stop_applied_on_detection -v

# Expected: PASSED
```

#### Step 5: Repeat for All Features

Write tests for:
- Profit highwater tracking
- Erosion detection (0.3× ATR warning, 0.5× ATR protection)
- Early trailing (0.5× ATR trigger)
- Early breakeven (0.5× ATR trigger)
- Stop modification queuing
- Configuration validation

### Running Test Suite

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run all tests with coverage
pytest --cov=src/services/stealth_stop_manager \
       --cov=src/utils/atr_calculator \
       --cov-report=html

# Open coverage report
open htmlcov/index.html

# Run only fast tests (skip integration)
pytest tests/unit/ -m "not slow"

# Run scenario replay tests
pytest tests/integration/test_protection_scenarios.py::test_jan_12_13_failure_prevention -v
```

### Manual Testing

#### Test Scenario 1: Disaster Stop Applied

1. Start service: `python3 -m src.services.stealth_stop_manager`
2. Open a position manually in MT4
3. Within 10 seconds, check logs for:
   ```
   [INFO] Initial protection set: Ticket #123456 stop at $62.25 (3×ATR=$2.25)
   ```
4. Verify in MT4 that stop loss was set

#### Test Scenario 2: Profit Erosion Protection

1. Open SHORT position at $60.00
2. Price drops to $59.25 (profit: $0.75)
3. Wait for monitoring cycle (60s)
4. Check logs: Highwater mark set to $0.75
5. Price rises back to $59.60 (profit: $0.40, erosion: $0.35)
6. If ATR = $0.75, erosion = 0.47× ATR (< 0.5×)
7. Check logs: Warning logged but no stop tightening yet
8. Price rises to $59.65 (erosion = 0.50× ATR)
9. Check logs: Stop tightened to protect remaining profit

#### Test Scenario 3: Early Trailing Activation

1. Open SHORT position at $61.00, ATR = $0.75
2. Price drops to $60.60 (profit: $0.40 = 0.53× ATR)
3. Wait for monitoring cycle
4. Check logs: `Trailing activated at 0.53× ATR profit` (NEW behavior)
5. OLD system would have required $0.75 profit (1.0× ATR)

### Debugging Tips

#### Enable Debug Logging

```python
# In stealth_stop_manager.py
import logging
logging.getLogger("stealth-stop-manager").setLevel(logging.DEBUG)
```

#### Check Redis Queue

```bash
# Connect to Redis
docker exec -it risetrader-redis redis-cli

# Check pending modifications
LLEN stealth_stops:pending_modifications

# View pending requests
LRANGE stealth_stops:pending_modifications 0 -1

# Clear queue (if needed)
DEL stealth_stops:pending_modifications
```

#### Inspect Live Positions

```python
# Python REPL
from src.services.stealth_stop_manager import StealthStopManager

manager = StealthStopManager()
positions = manager._monitored_positions

for ticket, pos in positions.items():
    print(f"Ticket: {ticket}")
    print(f"  Profit Highwater: ${pos.profit_highwater:.2f}")
    print(f"  Profit Erosion: ${pos.profit_erosion:.2f}")
    print(f"  Trailing Active: {pos.trailing_activated}")
    print(f"  Disaster Stop Set: {pos.disaster_stop_set}")
```

## Configuration Reference

### Global Defaults

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `disaster_stop_multiplier` | 3.0 | 1.0-10.0 | Initial stop distance (× ATR) |
| `trail_trigger_atr` | 0.5 | 0.1-5.0 | Start trailing at N× ATR profit |
| `breakeven_trigger_atr` | 0.5 | 0.1-5.0 | Move to breakeven at N× ATR |
| `erosion_threshold_atr` | 0.5 | 0.1-5.0 | Tighten when erosion > N× ATR |
| `erosion_alert_threshold_atr` | 0.3 | 0.1-5.0 | Warn when erosion > N× ATR |
| `monitoring_cycle_seconds` | 60 | 10-300 | Position check interval |
| `max_volatility_adjustment` | 0.5 | 0.1-1.0 | Max stop change per cycle (50%) |

### Per-Symbol Overrides

Example for high-volatility crude oil:

```yaml
symbol_overrides:
  CrudeOIL:
    disaster_stop_multiplier: 2.5  # Tighter (oil moves fast)
    trail_trigger_atr: 0.4          # More aggressive trailing
    erosion_threshold_atr: 0.4      # Protect profit sooner
```

Example for low-volatility forex:

```yaml
symbol_overrides:
  EURUSD:
    disaster_stop_multiplier: 4.0  # Wider (forex moves slowly)
    trail_trigger_atr: 0.6          # Less aggressive trailing
```

### Feature Flags

```yaml
features:
  enable_disaster_stops: true       # FR-002: Initial protection
  enable_profit_erosion: true       # FR-010: Erosion detection
  enable_early_breakeven: true      # FR-011: Soft breakeven
  enable_audit_trail: false         # Optional: Database logging
  enable_institutional_pricing: true # Anti-stop-hunting randomization
```

## Deployment

### Production Checklist

- [ ] Configuration validated with schema
- [ ] All tests passing (unit + integration + scenario replay)
- [ ] Test coverage ≥ 85%
- [ ] Paper trading validation complete (1 week minimum)
- [ ] Jan 12-13 scenario replay passes (SC-008)
- [ ] Configuration hot-reload tested
- [ ] MT4 connection resilience tested (disconnect/reconnect)
- [ ] Redis queue persistence tested
- [ ] Monitoring/alerting configured (Prometheus, logs)

### Deploy to Production

```bash
# 1. Build Docker image
docker-compose build api

# 2. Update configuration
cp config/stealth_stops.yaml.production config/stealth_stops.yaml

# 3. Validate configuration
python3 -c "
import yaml
import jsonschema

with open('config/stealth_stops.yaml') as f:
    config = yaml.safe_load(f)

with open('specs/001-stealth-stop-protection/contracts/stealth_stops.yaml.schema') as f:
    schema = yaml.safe_load(f)

jsonschema.validate(config, schema)
print('✓ Configuration valid')
"

# 4. Deploy with rolling restart
docker-compose up -d api

# 5. Monitor logs
docker logs -f risetrader-api | grep "stealth-stop-manager"

# 6. Verify protection active
docker exec risetrader-api python3 -c "
from src.services.stealth_stop_manager import StealthStopManager
manager = StealthStopManager()
print(f'Monitoring {len(manager._monitored_positions)} positions')
"
```

### Gradual Rollout Strategy

**Week 1: Disaster Stops Only**

```yaml
features:
  enable_disaster_stops: true
  enable_profit_erosion: false  # Disabled
  enable_early_breakeven: false  # Disabled
```

**Week 2: Add Profit Erosion**

```yaml
features:
  enable_disaster_stops: true
  enable_profit_erosion: true  # Enabled
  enable_early_breakeven: false
```

**Week 3: Full Feature Set**

```yaml
features:
  enable_disaster_stops: true
  enable_profit_erosion: true
  enable_early_breakeven: true  # Enabled
```

## Monitoring

### Key Metrics (Prometheus)

```python
# Instrument these metrics:
stealth_stops_positions_monitored         # Current count
stealth_stops_disaster_stops_set_total    # Counter
stealth_stops_trailing_activated_total    # Counter
stealth_stops_erosion_warnings_total      # Counter
stealth_stops_erosion_protection_applied_total  # Counter
stealth_stops_stop_modifications_total{status="success|failed"}  # Counter
stealth_stops_modification_latency_seconds  # Histogram
```

### Log Queries (Grep/ELK)

```bash
# Check disaster stops applied
grep "Initial protection set" logs/stealth_stops.log

# Check profit erosion warnings
grep "PROFIT EROSION ALERT" logs/stealth_stops.log

# Check stop modifications
grep "Stop trailed" logs/stealth_stops.log

# Check failures
grep "ERROR" logs/stealth_stops.log
```

## Troubleshooting

### Issue: Disaster Stops Not Being Set

**Symptoms**: New positions have no stop loss after 10+ seconds

**Diagnostics**:
```bash
# Check if service is running
ps aux | grep stealth_stop_manager

# Check if feature enabled
grep "enable_disaster_stops" config/stealth_stops.yaml

# Check MT4 connection
grep "Connected to MT4" logs/stealth_stops.log

# Check for errors
grep "Error getting positions" logs/stealth_stops.log
```

**Solutions**:
1. Verify `enable_disaster_stops: true` in config
2. Check MT4 connection (host/port correct?)
3. Verify ATR calculation working (check logs for ATR values)
4. Check ZMQ not timing out (increase timeout if remote)

### Issue: Trailing Not Activating

**Symptoms**: Position in profit but stop not moving

**Diagnostics**:
```bash
# Check trailing trigger
grep "trail_trigger_atr" config/stealth_stops.yaml

# Check position profit
grep "Profit:" logs/stealth_stops.log

# Check ATR value
grep "ATR:" logs/stealth_stops.log
```

**Solutions**:
1. Lower `trail_trigger_atr` if profit < threshold
2. Verify ATR calculation (may be higher than expected)
3. Check if position actually in profit (direction correct?)

### Issue: Profit Erosion Not Detected

**Symptoms**: Profit eroding but no protection applied

**Diagnostics**:
```bash
# Check if feature enabled
grep "enable_profit_erosion" config/stealth_stops.yaml

# Check highwater tracking
grep "profit_highwater" logs/stealth_stops.log

# Check erosion calculations
grep "profit_erosion" logs/stealth_stops.log
```

**Solutions**:
1. Verify `enable_profit_erosion: true`
2. Check `erosion_threshold_atr` (may be set too high)
3. Verify profit actually reached highwater first

## Next Steps

After quickstart:
1. Review [data-model.md](./data-model.md) for entity details
2. Review [research.md](./research.md) for design decisions
3. Start implementation with TDD workflow
4. Run `/speckit.tasks` to generate implementation task breakdown
