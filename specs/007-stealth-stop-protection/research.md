# Phase 0: Research & Design Decisions

**Feature**: Enhanced Stealth Stop Manager with Multi-Layer Risk Protection
**Date**: 2026-01-14
**Status**: Complete

## Overview

This document captures research findings and design decisions for implementing multi-layer risk protection in the stealth stop manager. The research phase resolves technical unknowns from the specification and establishes implementation approaches based on existing codebase patterns.

## Research Tasks

### 1. ATR Calculation Best Practices

**Question**: What is the most reliable approach for calculating ATR in a real-time trading system?

**Research Findings**:
- **Standard Approach**: 14-period Average True Range (ATR) using Wilder's smoothing method
- **Formula**: ATR(n) = [(ATR(n-1) × 13) + TR(n)] / 14, where TR = max(H-L, |H-C_prev|, |L-C_prev|)
- **Data Requirements**: Minimum 14 OHLC candles on the position's timeframe
- **Caching Strategy**: Cache ATR values with 60-second TTL to avoid recalculation on every monitoring cycle
- **Fallback**: When insufficient data, use 2% of entry price as disaster stop distance (spec requirement FR-005)

**Decision**: Implement centralized `ATRCalculator` utility class in `src/utils/atr_calculator.py` with:
- Wilder's 14-period smoothing
- In-memory cache with TTL
- Graceful fallback to percentage-based calculation
- Support for multiple timeframes (M1, M5, M15, H1)

**Rationale**: Centralizing ATR logic enables:
- Consistent calculation across all protection mechanisms
- Easy testing and validation
- Future reuse by other services (signal generators, risk managers)
- Performance optimization via caching

**Alternatives Considered**:
- **Simple Moving Average**: Rejected - less accurate for volatility measurement, doesn't handle gaps well
- **Database-stored ATR**: Rejected - adds latency, unnecessary complexity for short-term caching
- **Real-time streaming ATR**: Rejected - overkill for 60-second monitoring cycle

### 2. Profit Highwater Mark Tracking Strategy

**Question**: How should we track profit highwater marks to detect erosion efficiently?

**Research Findings**:
- **In-Memory State**: Store highwater mark in `MonitoredPosition` dataclass
- **Update Frequency**: Every monitoring cycle (default 60 seconds)
- **Persistence**: Not required - positions re-sync from MT4 on service restart
- **Calculation**: Current profit = (entry_price - current_price) × lot_size × pip_value (adjusted for direction)

**Decision**: Add three new fields to `MonitoredPosition` dataclass:
```python
@dataclass
class MonitoredPosition:
    # ... existing fields
    profit_highwater: float = 0.0      # Peak unrealized profit in USD
    last_highwater_update: Optional[datetime] = None
    profit_erosion: float = 0.0        # Current erosion from highwater
```

**Tracking Algorithm**:
1. Calculate current profit on each monitoring cycle
2. If current_profit > profit_highwater: Update highwater, reset erosion
3. If current_profit < profit_highwater: Calculate erosion = highwater - current_profit
4. If erosion > (0.3 × ATR × lot_size): Log warning (FR-013)
5. If erosion > (0.5 × ATR × lot_size): Trigger protection tightening (FR-010)

**Rationale**:
- Simple in-memory tracking - no database overhead
- Graceful handling of service restarts (re-syncs from MT4)
- Efficient O(1) calculation per monitoring cycle
- Clear thresholds aligned with spec requirements

**Alternatives Considered**:
- **Database persistence**: Rejected - unnecessary latency and complexity for transient state
- **Sliding window of profits**: Rejected - highwater mark is simpler and meets requirements
- **Percentage-based erosion**: Rejected - ATR-based is volatility-adjusted, more robust

### 3. Stop Modification Queuing Strategy

**Question**: How should we queue stop modifications to handle MT4 rate limiting and disconnection?

**Research Findings**:
- **MT4 Rate Limit**: Minimum 1-second spacing between modifications to same position (observed behavior)
- **Disconnection Scenarios**: Network outages, MT4 EA crashes, broker server restarts
- **Existing Infrastructure**: Redis 7+ available for pub/sub, MT4Client has retry logic

**Decision**: Implement two-tier queuing strategy:

**Tier 1 - In-Process Queue** (for normal operation):
- Python `asyncio.Queue` for pending stop modifications
- Worker coroutine processes queue with 1-second delays
- Immediate retry on transient ZMQ errors (3 attempts)
- Promotes to Tier 2 on persistent failures

**Tier 2 - Redis Persistence Queue** (for disconnection resilience):
- Redis list data structure: `stealth_stops:pending_modifications`
- Stores modifications that failed Tier 1
- Retried on reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s)
- TTL: 300 seconds (5 minutes) - expired modifications logged and discarded

**Processing Flow**:
```
1. Stop modification needed
2. Add to asyncio.Queue (Tier 1)
3. Worker processes with 1s delay
4. If ZMQ error:
   a. Retry immediately (max 3 attempts)
   b. If still failing → Push to Redis (Tier 2)
5. Background task polls Redis queue on reconnection
6. Process Tier 2 with exponential backoff
7. Log success/failure for all modifications
```

**Rationale**:
- Tier 1 handles 99%+ of cases (normal operation)
- Tier 2 provides resilience without performance overhead
- Graceful degradation during outages
- Auditable via structured logging (FR-014)

**Alternatives Considered**:
- **Redis-only queue**: Rejected - unnecessary latency for normal operations
- **Database queue**: Rejected - overkill, slower than Redis
- **No queuing**: Rejected - violates rate limiting, loses modifications on restart

### 4. Configuration Management Approach

**Question**: How should we structure configuration to support per-symbol customization while maintaining simplicity?

**Research Findings**:
- **Existing**: `config/stealth_stops.json` with hardcoded position tickets
- **Requirements**: Per-symbol configuration (FR-016), sensible defaults, hot-reload support
- **Best Practice**: YAML for configuration (more readable than JSON, supports comments)

**Decision**: Migrate to `config/stealth_stops.yaml` with three-tier structure:

```yaml
# Global defaults (apply to all symbols unless overridden)
defaults:
  disaster_stop_multiplier: 3.0      # 3× ATR
  trail_trigger_atr: 0.5              # Start trailing at 0.5× ATR profit
  breakeven_trigger_atr: 0.5          # Move to breakeven at 0.5× ATR profit
  erosion_threshold_atr: 0.5          # Tighten stop when erosion > 0.5× ATR
  monitoring_cycle_seconds: 60
  max_volatility_adjustment: 0.5      # Max 50% stop adjustment per cycle

# Per-symbol overrides
symbol_overrides:
  CrudeOIL:
    disaster_stop_multiplier: 2.5    # Tighter for oil (more volatile)
    trail_trigger_atr: 0.4            # More aggressive trailing
  EURUSD:
    disaster_stop_multiplier: 4.0    # Wider for forex (less volatile)
    trail_trigger_atr: 0.6            # Less aggressive trailing

# Feature flags
features:
  enable_disaster_stops: true
  enable_profit_erosion: true
  enable_early_breakeven: true
  enable_audit_trail: false          # Optional database logging
```

**Hot-Reload Support**:
- Watch `config/stealth_stops.yaml` for changes (using `watchdog` library)
- Reload configuration on file modification
- Validate schema before applying (using `pydantic` or `jsonschema`)
- Log configuration changes with old/new values
- Apply changes to new positions immediately, existing positions on next cycle

**Rationale**:
- YAML more maintainable than JSON (comments, readability)
- Three-tier structure (defaults → symbol → feature flags) covers all use cases
- Hot-reload enables parameter tuning without service restart (critical for 24/7 operation)
- Validation prevents configuration errors from causing failures

**Alternatives Considered**:
- **Environment variables**: Rejected - too many parameters, hard to manage overrides
- **Database configuration**: Rejected - overkill, adds latency and complexity
- **Python file (config.py)**: Rejected - requires code reload, less user-friendly

### 5. Testing Strategy for Risk Management Logic

**Question**: How can we achieve 85%+ test coverage while thoroughly validating risk scenarios?

**Research Findings**:
- **Constitution Requirement**: 85%+ test coverage, TDD workflow (tests first)
- **Critical Scenarios**: Jan 12-13 failure replay, extreme volatility, MT4 disconnection
- **Existing Infrastructure**: pytest, pytest-asyncio, pytest-mock

**Decision**: Four-layer testing strategy:

**Layer 1 - Unit Tests** (60% of coverage):
- Test each method in isolation with mocked dependencies
- Files:
  - `tests/unit/services/test_stealth_stop_manager.py`
  - `tests/unit/utils/test_atr_calculator.py`
- Coverage targets:
  - ATR calculation: 95%+
  - Profit highwater tracking: 90%+
  - Disaster stop calculation: 95%+
  - Erosion detection: 90%+

**Layer 2 - Integration Tests** (25% of coverage):
- Test service with mock MT4 EA (existing `tests/integration/mock_mt4_ea.py`)
- Files:
  - `tests/integration/test_stealth_stop_mt4_integration.py`
  - `tests/integration/test_protection_scenarios.py`
- Scenarios:
  - Position opens → disaster stop set within 10s
  - Position reaches profit → trailing activates
  - Profit erodes → stop tightens
  - MT4 disconnects → modifications queued → reconnect → modifications applied

**Layer 3 - Scenario Replay Tests** (10% of coverage):
- Replay historical failure (Jan 12-13) with actual price data
- File: `tests/integration/test_protection_scenarios.py::test_jan_12_13_failure_prevention`
- Test data: `tests/fixtures/historical_positions_jan_12_13.json`
- Expected outcome: Position closes at -$50 instead of -$1,980 (SC-008)

**Layer 4 - Property-Based Tests** (5% of coverage):
- Use `hypothesis` library to generate random market scenarios
- Invariant testing: "No position should ever lose more than disaster_stop distance"
- Fuzz testing: Random ATR values, price movements, timing variations

**TDD Workflow**:
1. **Red**: Write failing test for new feature (e.g., `test_disaster_stop_applied_on_detection`)
2. **Green**: Implement minimum code to make test pass
3. **Refactor**: Clean up implementation while keeping tests passing
4. **Repeat**: For each user story acceptance scenario

**Test Execution**:
```bash
# Run all tests with coverage
pytest --cov=src/services/stealth_stop_manager --cov=src/utils/atr_calculator --cov-report=html

# Run only unit tests (fast feedback loop)
pytest tests/unit/

# Run scenario replay tests
pytest tests/integration/test_protection_scenarios.py -k jan_12_13

# Run with hypothesis property testing
pytest tests/unit/ --hypothesis-show-statistics
```

**Rationale**:
- Four layers provide comprehensive coverage: unit → integration → historical → property-based
- Scenario replay tests directly validate spec success criteria (SC-008)
- Property-based testing discovers edge cases human testers miss
- Achieves 85%+ coverage target while maintaining fast test execution (<2 minutes total)

**Alternatives Considered**:
- **Manual testing only**: Rejected - not repeatable, doesn't meet TDD requirement
- **Integration tests only**: Rejected - slow, hard to isolate failures
- **Contract testing**: Rejected - not applicable (single service, no external API contracts)

## Summary of Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| **ATR Calculation** | Centralized utility with 14-period Wilder's smoothing, 60s cache TTL | Consistent calculation, testable, performant |
| **Highwater Tracking** | In-memory dataclass fields, no persistence | Simple, efficient, meets requirements |
| **Stop Modification Queue** | Two-tier: asyncio.Queue + Redis fallback | Balances performance and resilience |
| **Configuration** | YAML with defaults/overrides/flags, hot-reload | Maintainable, flexible, user-friendly |
| **Testing** | Four layers: unit/integration/scenario/property | Comprehensive coverage, validates spec success criteria |

## Open Questions (Resolved)

All research tasks completed. No blocking unknowns remain.

## Next Steps

Proceed to Phase 1: Design & Contracts
- Generate `data-model.md` with entity definitions
- Generate `contracts/stealth_stops.yaml.schema` for configuration validation
- Generate `quickstart.md` with developer setup instructions
