# Phase 1: Data Model

**Feature**: Enhanced Stealth Stop Manager with Multi-Layer Risk Protection
**Date**: 2026-01-14
**Status**: Complete

## Overview

This document defines the data entities and their relationships for the enhanced stealth stop manager. The design extends existing `MonitoredPosition` and adds new entities for stop modification tracking, protection events, and configuration management.

## Core Entities

### 1. MonitoredPosition (Enhanced)

**Purpose**: Represents a trading position actively monitored for stop protection

**Location**: `src/services/stealth_stop_manager.py` (dataclass)

**Fields** (✨ = new/modified):

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `ticket` | int | Yes | - | MT4 position ticket number (unique ID) |
| `symbol` | str | Yes | - | Trading symbol (e.g., "CrudeOIL", "EURUSD") |
| `direction` | str | Yes | - | Position direction: "long" or "short" |
| `entry_price` | float | Yes | - | Position entry price |
| `current_stop` | float | Yes | - | Current stop loss price |
| `current_tp` | float | Yes | - | Current take profit price |
| `lots` | float | Yes | - | Position size in lots |
| `current_price` | float | No | 0.0 | Latest market price |
| `last_check` | datetime | No | None | Last monitoring cycle timestamp |
| `last_trail_price` | float | No | None | Price at which stop was last trailed |
| `breakeven_triggered` | bool | No | False | Whether breakeven protection activated |
| ✨ `profit_highwater` | float | No | 0.0 | Peak unrealized profit (USD) |
| ✨ `last_highwater_update` | datetime | No | None | Timestamp of last highwater update |
| ✨ `profit_erosion` | float | No | 0.0 | Current erosion from highwater (USD) |
| ✨ `disaster_stop_set` | bool | No | False | Whether initial disaster stop applied |
| ✨ `trailing_activated` | bool | No | False | Whether trailing stop mechanism active |

**Relationships**:
- **One-to-many** with `StopModificationRequest`: A position can have multiple pending/historical stop modifications
- **One-to-many** with `ProtectionEvent`: A position generates multiple protection events (logs)

**State Transitions**:

```
New Position Detected
  ↓
[disaster_stop_set = False]
  ↓
Calculate & Apply Disaster Stop (FR-002)
  ↓
[disaster_stop_set = True]
  ↓
Monitor for Profit (every cycle)
  ↓
[Current Profit >= 0.5× ATR] (FR-009)
  ↓
[trailing_activated = True]
  ↓
Monitor for Erosion (every cycle)
  ↓
[profit_erosion > 0.5× ATR] (FR-010)
  ↓
Tighten Stop (Protection)
  ↓
[Position Closed or Stopped Out]
  ↓
Remove from Monitoring (FR-020)
```

**Validation Rules**:
- `ticket` must be positive integer
- `symbol` must match known trading symbols
- `direction` must be "long" or "short"
- `lots` must be positive
- `profit_highwater` >= 0
- `profit_erosion` >= 0
- If `trailing_activated == True`, then `profit_highwater` > 0

**Example**:

```python
position = MonitoredPosition(
    ticket=24504142,
    symbol="CrudeOIL",
    direction="short",
    entry_price=60.87,
    current_stop=62.17,
    current_tp=57.37,
    lots=0.5,
    current_price=61.625,
    profit_highwater=0.70,  # Was at $0.70 profit
    profit_erosion=0.14,    # Now eroded by $0.14
    disaster_stop_set=True,
    trailing_activated=False  # Didn't reach 0.5× ATR yet
)
```

---

### 2. StopModificationRequest (New)

**Purpose**: Tracks a pending or completed stop loss modification attempt

**Location**: `src/services/stealth_stop_manager.py` (dataclass)

**Fields**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `request_id` | str | Yes | - | UUID for request tracking |
| `ticket` | int | Yes | - | Position ticket number |
| `timestamp` | datetime | Yes | - | Request creation timestamp |
| `old_stop` | float | Yes | - | Previous stop loss price |
| `new_stop` | float | Yes | - | New stop loss price |
| `reason` | str | Yes | - | Modification reason (enum) |
| `status` | str | Yes | "pending" | Request status (enum) |
| `attempt_count` | int | No | 0 | Number of modification attempts |
| `next_retry_time` | datetime | No | None | When to retry (for exponential backoff) |
| `error_message` | str | No | None | Last error message if failed |
| `completed_at` | datetime | No | None | When modification succeeded |
| `mt4_response` | dict | No | None | Raw MT4 response for audit |

**Enums**:

```python
class ModificationReason(str, Enum):
    DISASTER_STOP = "disaster_stop"          # Initial protection (FR-002)
    TRAILING_PROFIT = "trailing_profit"      # Normal trailing (FR-009)
    PROFIT_EROSION = "profit_erosion"        # Erosion protection (FR-010)
    BREAKEVEN_MOVE = "breakeven_move"        # Breakeven lock (FR-011)
    MANUAL_OVERRIDE = "manual_override"      # Trader manual adjustment

class ModificationStatus(str, Enum):
    PENDING = "pending"              # In asyncio queue
    IN_PROGRESS = "in_progress"      # Sent to MT4, awaiting response
    COMPLETED = "completed"          # Successfully applied
    FAILED = "failed"                # Failed after max retries
    RETRYING = "retrying"            # In Redis queue, retrying
```

**Lifecycle**:

```
Created → PENDING → IN_PROGRESS → COMPLETED (success)
                              ↓
                          RETRYING → FAILED (after max retries)
```

**Validation Rules**:
- `new_stop` must be different from `old_stop`
- For SHORT positions: `new_stop` > `old_stop` (tightening) OR `new_stop` < `old_stop` (widening during erosion)
- For LONG positions: `new_stop` < `old_stop` (tightening) OR `new_stop` > `old_stop` (widening during erosion)
- `attempt_count` <= 10 (max retries)
- `status` transitions must follow lifecycle rules

**Example**:

```python
request = StopModificationRequest(
    request_id="fab1c0c9-a741-474f-b426-d08941952c1f",
    ticket=24504142,
    timestamp=datetime.now(),
    old_stop=62.17,
    new_stop=61.68,  # Disaster stop (3× ATR below entry)
    reason=ModificationReason.DISASTER_STOP,
    status=ModificationStatus.COMPLETED,
    attempt_count=1,
    completed_at=datetime.now(),
    mt4_response={"status": "OK", "message": "Stop modified"}
)
```

---

### 3. ProtectionEvent (New, Optional)

**Purpose**: Auditable log of all protection actions for compliance and analysis

**Location**:
- Model: `src/database/models/protection_events.py` (SQLAlchemy model)
- Repository: `src/database/repositories/protection_repository.py`

**Note**: This is OPTIONAL. Can be implemented as pure logging (structlog) without database persistence. Database audit trail provides queryable history for analysis but adds complexity.

**Fields** (if implemented):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | int | Yes | Auto-increment primary key |
| `event_id` | str | Yes | UUID for event correlation |
| `ticket` | int | Yes | Position ticket number (indexed) |
| `timestamp` | datetime | Yes | Event occurrence time (indexed) |
| `event_type` | str | Yes | Event category (enum) |
| `severity` | str | Yes | Log level: INFO/WARNING/ERROR |
| `description` | str | Yes | Human-readable event description |
| `position_context` | JSON | Yes | Position state at event time |
| `metrics` | JSON | No | Event-specific metrics (profit, ATR, stop prices) |
| `alert_generated` | bool | No | Whether alert sent to trader |
| `user_acknowledged` | bool | No | Whether trader acknowledged alert |

**Event Types**:

```python
class ProtectionEventType(str, Enum):
    DISASTER_STOP_SET = "disaster_stop_set"
    TRAILING_ACTIVATED = "trailing_activated"
    STOP_TRAILED = "stop_trailed"
    EROSION_WARNING = "erosion_warning"
    EROSION_PROTECTION_APPLIED = "erosion_protection_applied"
    BREAKEVEN_LOCKED = "breakeven_locked"
    MODIFICATION_FAILED = "modification_failed"
    POSITION_DETECTED = "position_detected"
    POSITION_REMOVED = "position_removed"
```

**Database Schema** (PostgreSQL):

```sql
CREATE TABLE protection_events (
    id SERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    ticket BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    position_context JSONB NOT NULL,
    metrics JSONB,
    alert_generated BOOLEAN DEFAULT FALSE,
    user_acknowledged BOOLEAN DEFAULT FALSE,

    INDEX idx_protection_events_ticket (ticket),
    INDEX idx_protection_events_timestamp (timestamp DESC),
    INDEX idx_protection_events_type (event_type)
);
```

**Indexes**:
- `ticket`: Fast lookup of all events for a position
- `timestamp`: Chronological queries (recent events)
- `event_type`: Filter by event category

**Retention Policy**: 90 days (configurable), then archive to cold storage or delete

**Example**:

```python
event = ProtectionEvent(
    event_id="3c9782f6-0f53-47de-93d0-889a1924cdee",
    ticket=24504142,
    timestamp=datetime.now(),
    event_type=ProtectionEventType.EROSION_WARNING,
    severity="WARNING",
    description="Profit erosion detected: $0.14 from highwater $0.70",
    position_context={
        "symbol": "CrudeOIL",
        "entry": 60.87,
        "current": 61.625,
        "stop": 62.17,
        "lots": 0.5
    },
    metrics={
        "profit_highwater": 0.70,
        "current_profit": 0.56,
        "profit_erosion": 0.14,
        "atr": 0.75,
        "erosion_threshold": 0.375
    },
    alert_generated=True
)
```

---

### 4. DynamicTrailConfig (Enhanced)

**Purpose**: Configuration for protection behavior (per-symbol customizable)

**Location**: `src/services/stealth_stop_manager.py` (dataclass), loaded from `config/stealth_stops.yaml`

**Fields** (✨ = new/modified):

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ✨ `disaster_stop_multiplier` | float | No | 3.0 | Initial stop distance (× ATR) |
| `atr_multiplier_initial` | float | No | 2.0 | Legacy field (deprecated, use disaster_stop_multiplier) |
| `atr_multiplier_trail` | float | No | 1.5 | Trailing stop distance (× ATR) |
| ✨ `trail_trigger_atr` | float | No | 0.5 | Start trailing at N× ATR profit (lowered from 1.0) |
| `trail_step_atr` | float | No | 0.5 | Trail every N× ATR additional profit |
| ✨ `breakeven_trigger_atr` | float | No | 0.5 | Move to breakeven at N× ATR profit (lowered from 1.5) |
| ✨ `erosion_threshold_atr` | float | No | 0.5 | Tighten stop when erosion > N× ATR |
| ✨ `erosion_alert_threshold_atr` | float | No | 0.3 | Log warning when erosion > N× ATR |
| `breakeven_offset_pips` | float | No | 10 | Lock N pips profit at breakeven |
| `min_offset_pips` | float | No | 5 | Min random offset (institutional pricing) |
| `max_offset_pips` | float | No | 15 | Max random offset (institutional pricing) |
| `pip_value` | float | No | 0.01 | Pip size for symbol (0.01 for oil, 0.0001 for forex) |
| ✨ `monitoring_cycle_seconds` | int | No | 60 | Position check interval |
| ✨ `max_volatility_adjustment` | float | No | 0.5 | Max stop adjustment per cycle (50%) |
| ✨ `atr_fallback_percentage` | float | No | 0.02 | Use 2% when ATR unavailable |
| ✨ `manual_override_grace_period` | int | No | 60 | Respect manual stops for N seconds |

**Validation Rules**:
- All multipliers must be in range [0.1, 10.0]
- `trail_trigger_atr` <= `breakeven_trigger_atr` (can't trigger breakeven before trailing)
- `erosion_alert_threshold_atr` < `erosion_threshold_atr` (warn before acting)
- `monitoring_cycle_seconds` >= 10 (minimum 10-second cycle)
- `max_volatility_adjustment` in range [0.1, 1.0]
- `atr_fallback_percentage` in range [0.01, 0.10]

**YAML Configuration Format**:

```yaml
defaults:
  disaster_stop_multiplier: 3.0
  trail_trigger_atr: 0.5
  breakeven_trigger_atr: 0.5
  erosion_threshold_atr: 0.5
  erosion_alert_threshold_atr: 0.3
  monitoring_cycle_seconds: 60
  max_volatility_adjustment: 0.5

symbol_overrides:
  CrudeOIL:
    disaster_stop_multiplier: 2.5
    trail_trigger_atr: 0.4
  EURUSD:
    disaster_stop_multiplier: 4.0
    trail_trigger_atr: 0.6
```

---

## Entity Relationships

```
MonitoredPosition (1) ──── (N) StopModificationRequest
     │                              │
     │                              │
     │                              │
  (1) │                          (1) │
     │                              │
     └──────────── (N) ProtectionEvent ──────────┘
                       (optional)

DynamicTrailConfig ───(loaded by)─── StealthStopManager
                                             │
                                             │ manages
                                             │
                                        MonitoredPosition(s)
```

**Relationships**:
1. **MonitoredPosition** has many **StopModificationRequest**s (one per stop change)
2. **MonitoredPosition** generates many **ProtectionEvent**s (audit trail)
3. **StopModificationRequest** can trigger **ProtectionEvent**s (on failure/success)
4. **DynamicTrailConfig** applies to all **MonitoredPosition**s (or per-symbol overrides)

---

## Data Flow

### 1. Position Detection Flow

```
MT4 EA publishes position
  ↓
StealthStopManager.sync_positions()
  ↓
Create MonitoredPosition (disaster_stop_set=False)
  ↓
Calculate disaster_stop = entry ± (3× ATR)
  ↓
Create StopModificationRequest (reason=DISASTER_STOP)
  ↓
Add to asyncio.Queue (Tier 1)
  ↓
Worker sends to MT4 via MT4Client
  ↓
MT4 responds → Update MonitoredPosition (disaster_stop_set=True)
  ↓
Log ProtectionEvent (event_type=DISASTER_STOP_SET)
```

### 2. Profit Erosion Detection Flow

```
Monitoring cycle triggers
  ↓
Calculate current_profit for each position
  ↓
If current_profit > profit_highwater:
  → Update profit_highwater
  → Reset profit_erosion = 0
  ↓
If current_profit < profit_highwater:
  → Calculate profit_erosion = highwater - current_profit
  ↓
If profit_erosion > (0.3× ATR):
  → Log ProtectionEvent (event_type=EROSION_WARNING, severity=WARNING)
  ↓
If profit_erosion > (0.5× ATR):
  → Calculate protection_stop = tighten based on remaining profit
  → Create StopModificationRequest (reason=PROFIT_EROSION)
  → Log ProtectionEvent (event_type=EROSION_PROTECTION_APPLIED)
```

### 3. Stop Modification Queue Flow

```
StopModificationRequest created
  ↓
Add to asyncio.Queue (Tier 1)
  ↓
Worker coroutine processes with 1s delay
  ↓
Send to MT4Client.modify_order()
  ↓
MT4 responds:
  ├─ Success → status=COMPLETED, log event
  ├─ ZMQ error → Retry (max 3 attempts)
  │              ├─ Still failing → Push to Redis (Tier 2)
  │              └─ Eventually succeeds → status=COMPLETED
  └─ Invalid params → status=FAILED, log error
```

---

## Performance Considerations

| Entity | Storage | Size | Cardinality |
|--------|---------|------|-------------|
| `MonitoredPosition` | In-memory (Python dict) | ~500 bytes | 10-100 concurrent |
| `StopModificationRequest` | In-memory + Redis (transient) | ~1 KB | 10-50 pending |
| `ProtectionEvent` | PostgreSQL (optional) | ~2 KB | Millions (historical) |
| `DynamicTrailConfig` | In-memory (loaded from YAML) | ~2 KB | 1 instance |

**Memory Footprint**:
- 100 positions × 500 bytes = 50 KB
- 50 pending requests × 1 KB = 50 KB
- Config: ~2 KB
- **Total: ~100 KB** (well under target)

**Database Load** (if ProtectionEvent enabled):
- Writes: ~10 events/minute (5 positions × 2 events/cycle)
- Reads: Minimal (query only for analysis/debugging)
- Index size: ~10 MB per 100K events
- Storage: ~200 MB per million events

---

## Next Steps

Proceed to:
1. Generate `contracts/stealth_stops.yaml.schema` (YAML schema validation)
2. Generate `quickstart.md` (developer setup guide)
3. Update agent context (if applicable)

