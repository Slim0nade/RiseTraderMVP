# Feature Specification: Enhanced Stealth Stop Manager with Multi-Layer Risk Protection

**Feature Branch**: `001-stealth-stop-protection`
**Created**: 2026-01-13
**Status**: Draft
**Input**: User description: "Enhanced Stealth Stop Manager with Multi-Layer Risk Protection - implementing 5 critical fixes to prevent catastrophic losses from unprotected positions"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Immediate Disaster Protection on Position Entry (Priority: P1)

When a trader opens a new position (manually or via automated strategy), the system must immediately set a protective stop loss without any manual intervention. This prevents the catastrophic scenario where a position moves against the trader before any protection is in place.

**Why this priority**: This is the most critical fix. Without initial protection, positions are exposed to unlimited downside risk. The Jan 12-13 failure demonstrated a $2,585 swing that could have been prevented with this single feature.

**Independent Test**: Can be fully tested by opening a position and verifying that a stop loss order is automatically placed within seconds. Delivers immediate value by ensuring no position is ever unprotected.

**Acceptance Scenarios**:

1. **Given** no open positions exist, **When** trader opens a new SHORT position at $59.43 with ATR=$0.75, **Then** system automatically sets disaster stop at $61.68 (entry + 3×ATR) within 10 seconds
2. **Given** no open positions exist, **When** trader opens a new LONG position at $100.00 with ATR=$2.00, **Then** system automatically sets disaster stop at $94.00 (entry - 3×ATR) within 10 seconds
3. **Given** existing position has no stop loss, **When** stealth stop manager detects the position for the first time, **Then** system immediately calculates and applies appropriate disaster stop based on current ATR
4. **Given** position is detected, **When** ATR cannot be calculated (insufficient data), **Then** system uses fallback of 2% of entry price as disaster stop distance

---

### User Story 2 - Profit Erosion Detection and Protection (Priority: P2)

When a position reaches profitable territory and then begins to reverse, the system must detect the profit erosion and automatically tighten the stop loss to protect remaining gains. This prevents the scenario where a position goes from significant profit (+$605) to significant loss (-$1,980).

**Why this priority**: This addresses the core failure mode - watching profits vanish during reversals. Once a trader has unrealized profit, the system should defend it aggressively rather than let it completely evaporate.

**Independent Test**: Can be tested by simulating a position that moves into profit then reverses. System should lock in profit protection before erosion exceeds thresholds. Delivers value by converting paper profits into protected gains.

**Acceptance Scenarios**:

1. **Given** SHORT position at $59.43 with profit highwater of $0.70 (at price $58.73), **When** price rises to $58.87 causing $0.14 profit erosion, **Then** system logs erosion warning and maintains existing stop
2. **Given** SHORT position with profit highwater of $0.70 and current profit of $0.30, **When** profit erosion exceeds 0.5×ATR ($0.375), **Then** system immediately tightens stop to lock in remaining profit
3. **Given** position showing profit erosion of 0.3×ATR, **When** erosion threshold is crossed, **Then** system logs warning alert with position details and current vs peak profit
4. **Given** position with locked profit protection stop, **When** price continues moving favorably, **Then** system updates highwater mark and loosens protection stop accordingly

---

### User Story 3 - Early Profit Locking with Reduced Thresholds (Priority: P2)

When a position moves into modest profit (0.5×ATR instead of 1.0×ATR), the system must begin trailing the stop loss to start locking in gains much earlier. This ensures that even small profitable moves are defended.

**Why this priority**: The original failure showed Position #24500414 reaching $0.70 profit but needing $0.75 to trigger trailing - missing by just 5 cents. Lowering thresholds ensures protection activates for most favorable moves.

**Independent Test**: Can be tested by opening a position and moving price to create 0.5×ATR profit. System should activate trailing immediately. Delivers value by protecting smaller wins that would otherwise be ignored.

**Acceptance Scenarios**:

1. **Given** SHORT position at $59.43 with ATR=$0.75, **When** price drops to $59.05 (profit=$0.38, which is 0.50×ATR), **Then** system activates trailing stop mechanism
2. **Given** position with 0.50×ATR profit, **When** trailing activates, **Then** stop is set to lock minimum profit of 0.25×ATR (half the trigger threshold)
3. **Given** position with 0.60×ATR profit, **When** price moves further in favor by 0.20×ATR, **Then** stop trails by same distance maintaining profit lock
4. **Given** position reaches 0.5×ATR profit for soft breakeven, **When** stop is moved to entry price, **Then** position becomes risk-free (maximum loss is zero minus commissions)

---

### User Story 4 - Comprehensive Alert and Monitoring System (Priority: P3)

The system must log all protection actions and alert the trader when important thresholds are crossed or stops are modified. This provides visibility into the automated risk management and builds trader confidence in the system.

**Why this priority**: While not preventing losses directly, alerts enable informed decision-making and allow manual intervention when needed. They also provide audit trails for post-trade analysis.

**Independent Test**: Can be tested by triggering various protection scenarios and verifying appropriate logs/alerts are generated. Delivers value by keeping trader informed of all automated risk management actions.

**Acceptance Scenarios**:

1. **Given** new position detected, **When** initial disaster stop is set, **Then** system logs "Initial protection set: Ticket #123 stop at $X.XX (3×ATR=$Y.YY)"
2. **Given** position showing profit erosion of 0.3×ATR, **When** threshold is crossed, **Then** system generates warning alert: "⚠️ PROFIT EROSION ALERT: Ticket #123 Peak: $X.XX, Current: $Y.YY"
3. **Given** trailing stop is modified, **When** modification is successful, **Then** system logs "Stop trailed: Ticket #123 from $X.XX to $Y.YY (locked profit: $Z.ZZ)"
4. **Given** stop modification fails (MT4 error), **When** error occurs, **Then** system logs critical error with ticket details and retries modification with exponential backoff

---

### Edge Cases

- **What happens when ATR cannot be calculated?** (e.g., newly listed instrument with insufficient price history)
  - System uses fallback of 2% of entry price as disaster stop distance
  - Logs warning that ATR-based protection unavailable, using fixed percentage

- **What happens when MT4 is disconnected during stop modification?**
  - System queues stop modification requests in local cache
  - Retries with exponential backoff when connection restored
  - Logs all failed attempts and eventual success/failure

- **What happens when position is already very close to disaster stop?**
  - If current price is within 0.5×ATR of calculated disaster stop, system uses current price + 0.5×ATR as stop
  - Prevents setting stops that would trigger immediately due to spread/slippage

- **What happens when multiple positions exist on the same symbol?**
  - Each position tracked independently with its own profit highwater and protection stops
  - System manages stop modification queue to avoid MT4 rate limiting

- **What happens during extreme volatility when ATR spikes suddenly?**
  - System recalculates stops using new ATR but applies maximum adjustment limit of 50% per update cycle
  - Prevents stops from moving too far too fast during volatility spikes

- **What happens when a position is manually closed while stop modification is pending?**
  - System detects closed position on next sync cycle and removes from monitoring
  - Cancels any pending stop modification requests for that ticket

- **What happens when trader manually modifies a stop that system is managing?**
  - System detects manual change and respects it for 1 monitoring cycle (default 60 seconds)
  - After grace period, system evaluates whether manual stop meets protection criteria
  - If manual stop is better (more protective), system adopts it as new baseline
  - If manual stop is worse, system logs warning and may override based on configuration

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect new positions within 10 seconds of opening and add them to monitoring queue
- **FR-002**: System MUST calculate and apply initial disaster stop within 10 seconds of detecting a new unprotected position
- **FR-003**: System MUST use 3×ATR multiplier as default for disaster stop distance (configurable per symbol)
- **FR-004**: System MUST calculate ATR using 14-period Average True Range on the position's timeframe
- **FR-005**: System MUST provide fallback disaster stop of 2% of entry price when ATR cannot be calculated
- **FR-006**: System MUST track profit highwater mark (peak unrealized profit) for each monitored position
- **FR-007**: System MUST update profit highwater mark whenever current profit exceeds previous peak
- **FR-008**: System MUST calculate profit erosion as difference between highwater mark and current profit
- **FR-009**: System MUST activate trailing stops when position profit reaches 0.5×ATR threshold (reduced from 1.0×ATR)
- **FR-010**: System MUST tighten stop loss when profit erosion exceeds 0.5×ATR from highwater mark
- **FR-011**: System MUST move stop to entry price (soft breakeven) when profit reaches 0.5×ATR
- **FR-012**: System MUST trail stop loss to lock minimum profit of 0.25×ATR once trailing is activated
- **FR-013**: System MUST log warning alert when profit erosion exceeds 0.3×ATR from highwater mark
- **FR-014**: System MUST log all stop loss modifications with timestamp, ticket number, old price, new price, and reason
- **FR-015**: System MUST retry failed stop modifications with exponential backoff (1s, 2s, 4s, 8s, max 30s between retries)
- **FR-016**: System MUST support configuration per symbol for: disaster stop multiplier, trail trigger multiplier, erosion threshold, soft breakeven trigger
- **FR-017**: System MUST prevent setting stops that would trigger immediately (minimum 0.5×ATR distance from current price)
- **FR-018**: System MUST handle MT4 disconnection by queuing stop modifications and retrying on reconnection
- **FR-019**: System MUST respect trader's manual stop modifications for 60-second grace period before re-evaluating
- **FR-020**: System MUST remove closed positions from monitoring on next sync cycle and cancel pending operations

### Key Entities

- **MonitoredPosition**: Represents a trading position under active stealth stop management
  - Position identification (ticket number, symbol, direction, entry price)
  - Current protection state (disaster stop level, trail stop level, current stop)
  - Profit tracking (current profit, profit highwater mark, profit erosion amount)
  - ATR context (current ATR value, timeframe, calculation timestamp)
  - Status flags (is_trailing_active, is_breakeven_locked, last_stop_modification_time)
  - Configuration overrides (custom disaster multiplier, trail trigger, erosion threshold)

- **StopModificationRequest**: Represents a pending or completed stop loss modification
  - Request identification (request ID, ticket number, timestamp)
  - Stop loss details (old stop price, new stop price, modification reason)
  - Execution status (pending, in_progress, completed, failed, retrying)
  - Retry tracking (attempt count, next retry time, last error message)
  - MT4 response (modification ticket number, execution timestamp, error code if failed)

- **ProtectionEvent**: Represents a logged protection action or alert
  - Event identification (event ID, ticket number, timestamp, event type)
  - Event details (description, severity level, position context at time of event)
  - Metrics (profit at event time, ATR at event time, stop price at event time)
  - Alert status (logged_only, alert_generated, user_acknowledged)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: No position remains unprotected for more than 10 seconds after opening
- **SC-002**: System detects and responds to profit erosion exceeding 0.5×ATR within one monitoring cycle (≤60 seconds)
- **SC-003**: Positions reaching 0.5×ATR profit automatically activate trailing stops within one monitoring cycle
- **SC-004**: Stop loss modifications are successfully applied to MT4 within 5 seconds under normal conditions (MT4 connected, sufficient margin)
- **SC-005**: Failed stop modifications are retried successfully within 60 seconds when MT4 connection is restored
- **SC-006**: System generates alerts for 100% of profit erosion events exceeding 0.3×ATR threshold
- **SC-007**: Trader receives clear, actionable log entries for all automated stop modifications including reason and profit impact
- **SC-008**: Positions that reach +$600 profit do not result in losses exceeding -$100 under normal market conditions (no gaps, flash crashes)
- **SC-009**: System maintains accurate profit highwater tracking with less than 1% deviation from actual peak profit
- **SC-010**: Soft breakeven protection activates for 95%+ of positions that reach 0.5×ATR profit

### Risk Mitigation Validation

To validate that the enhanced system prevents the original failure scenario:

- **Scenario Replay**: Position SHORT at $59.43 reaching $58.73 (+$605 profit peak), then reversing to $61.23
  - **Expected Outcome**: System locks profit protection when erosion exceeds 0.5×ATR, position closes at worst -$50 instead of -$1,980

- **Near-Miss Scenario**: Position reaches 0.70×ATR profit (5 cents short of old 1.0×ATR trigger)
  - **Expected Outcome**: New 0.5×ATR trigger activates trailing, prevents missed protection opportunity

- **Rapid Reversal**: Position reaches 0.6×ATR profit then reverses quickly losing 0.4×ATR in 10 minutes
  - **Expected Outcome**: Profit erosion protection tightens stop, locks remaining 0.2×ATR profit minimum

## Assumptions

- **MT4 Connectivity**: MT4 platform is running and ZMQ connection is available at least 95% of the time
- **Market Data Availability**: Real-time price data is available with less than 5-second latency for monitored symbols
- **ATR Calculation**: Historical price data for ATR calculation (14 periods minimum) is available for all traded symbols
- **Stop Loss Acceptance**: Broker accepts stop loss orders for all position types being traded (standard CFDs, not exotic derivatives)
- **Slippage Tolerance**: Stop losses execute within 0.1×ATR of requested price under normal market conditions
- **Position Synchronization**: MT4 position state is accurately synchronized to Python backend within 5 seconds of changes
- **Configuration Persistence**: Symbol-specific configuration (disaster multipliers, thresholds) persists across system restarts
- **Single-Instance Operation**: Only one instance of stealth stop manager runs at a time per MT4 account (no race conditions)
- **Monitoring Cycle**: Default monitoring cycle is 60 seconds but configurable down to 10 seconds minimum
- **No Gap Risk**: System assumes positions can be closed at calculated stop prices (no overnight/weekend gap risk factored into stop distances)

## Out of Scope

- **Order Entry Integration**: This feature manages stops for existing positions only, does not control initial position entry/sizing
- **Multi-Account Management**: Manages positions for single MT4 account, not portfolio-level risk across multiple accounts
- **Machine Learning Stop Optimization**: Uses rule-based ATR multipliers, not ML-predicted optimal stop distances
- **Correlation-Based Risk**: Does not consider correlation between multiple positions when setting individual stops
- **Fundamental Event Protection**: Does not adjust stops based on economic calendar events or news releases
- **Partial Position Management**: Manages single stop per position, does not support scaling out with multiple stops
- **Strategy-Specific Logic**: Generic stop management, does not customize behavior based on which trading strategy opened the position
- **Backtesting Integration**: Initially focused on live/paper trading, historical backtest integration deferred to future phase
- **Manual Override UI**: Command-line/config-file based management only, no GUI for manual stop adjustments in this phase
- **Performance Analytics Dashboard**: Logs protection actions but does not provide visual analytics/reporting interface

## Dependencies

- **Existing MT4 ZMQ Integration**: Requires functional ZMQ connection for reading positions and modifying stops (`src/trading/execution/mt4_client.py`)
- **Market Data Service**: Needs access to OHLCV data for ATR calculation (either from MT4 directly or existing `market_data` database)
- **Position Synchronization Service**: Depends on `mt4_sync_service.py` for detecting new/modified/closed positions
- **Configuration Management**: Uses existing YAML configuration system (`config/stealth_stops.yaml` or similar)
- **Logging Infrastructure**: Integrates with existing structured logging system (`structlog` configured in `src/utils/logging.py`)
- **Redis Pub/Sub**: May use Redis for alert distribution if real-time notifications required beyond logging

## Technical Constraints

- **MT4 Modification Rate Limits**: MT4 may throttle rapid stop modifications, system must respect minimum 1-second spacing between modifications to same position
- **ZMQ Latency**: Network latency between Python service and MT4 EA typically 10-500ms, must account for round-trip time in timing requirements
- **ATR Calculation Performance**: ATR calculation for multiple positions/symbols must complete within monitoring cycle (default 60s)
- **Database Write Load**: Frequent logging of protection events must not overwhelm database connection pool (consider buffering/batching)
- **Memory Footprint**: Must efficiently track hundreds of monitored positions without excessive memory usage (estimated max 1000 concurrent positions)
- **Async Operation**: All MT4 communication and stop modifications must be non-blocking async operations to prevent service lockup
- **Error Recovery**: Must gracefully handle MT4 errors (insufficient margin, market closed, invalid stops) without crashing service
- **Configuration Reload**: Should support hot-reload of configuration without restarting service or losing position monitoring state

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Stop modifications fail during high volatility | Positions lose protection during critical moments | Medium | Implement aggressive retry logic with sub-second intervals; maintain last-known-good stop in case of total failure |
| ATR calculation lags during fast markets | Stop distances based on stale volatility | Medium | Cache recent ATR values; use most recent available; add staleness warnings to logs |
| False profit erosion triggers on spread widening | Unnecessary stop tightening reduces profit potential | Low | Filter profit erosion based on bid/ask average rather than single quote; require erosion to persist for 2+ monitoring cycles |
| System sets stop too tight on mean-reverting moves | Premature exit from positions that would recover | Medium | Make soft breakeven configurable; allow traders to disable erosion protection per symbol for ranging markets |
| MT4 disconnection during critical price move | Missed protection opportunity during disconnect window | Low | Immediate alert on disconnect; queue all modifications; execute burst of updates on reconnection |
| Configuration errors cause incorrect stop distances | Positions under/over protected due to wrong multipliers | Low | Validate all configuration on load; require multipliers within sensible ranges (1-10×ATR); log warnings for unusual values |
| Multiple instances of service running simultaneously | Race conditions causing conflicting stop modifications | Very Low | Implement distributed lock using Redis; add instance ID to all logs; detect and alert on multi-instance operation |
| Broker rejects stop modifications (too close to price) | Protection cannot be applied despite system attempt | Medium | Pre-validate stop distance against broker minimum (typically 10-50 pips); use fallback distance if calculated stop too close |

## Notes

**Design Philosophy**: This specification treats the stealth stop manager as a defensive safety net, not an offensive profit maximizer. The goal is to prevent catastrophic losses and lock in reasonable gains, not to perfectly time exits for maximum profit. Conservative thresholds and aggressive protection are intentional trade-offs.

**Configuration Flexibility**: While the specification defines sensible defaults (3×ATR disaster, 0.5×ATR trailing trigger), every threshold should be symbol-configurable. Crude oil may need different parameters than EUR/USD due to different volatility characteristics.

**Observability First**: Comprehensive logging and alerting are critical for trader confidence. Every automated action must be transparent and auditable. Traders should never be surprised by a stop modification.

**Graceful Degradation**: If ATR cannot be calculated, fall back to percentage-based stops. If MT4 is disconnected, queue operations. The system should never fail to protect positions due to missing data or connectivity issues - it should use best available information and alert the trader to limitations.

**Future Enhancements** (deferred but documented for reference):
- Time-based stop tightening (e.g., tighten stops in final hour before market close)
- Volatility regime detection to adjust multipliers dynamically
- Correlation-aware stop management for hedged positions
- Integration with economic calendar for pre-event protection tightening
- Machine learning to learn optimal stop distances from historical trade outcomes
