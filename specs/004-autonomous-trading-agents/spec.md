# Feature Specification: Autonomous Trading Agents System

**Feature Branch**: `004-autonomous-trading-agents`
**Created**: 2025-11-29
**Status**: Draft
**Input**: User description: "Autonomous trading agents system with 10 specialized agents (SignalGeneratorAgent, RiskManagerAgent, ExecutionAgent, MarketDataAgent, MLPredictionAgent, RegimeDetectionAgent, PerformanceMonitorAgent, RiskOverseerAgent, StrategyOptimizerAgent) coordinated by MCP Server for event-driven autonomous trading decisions"

## Overview

The Autonomous Trading Agents System is the intelligent core of the RiseTrader platform, enabling 24/7 automated trading decisions through a coordinated network of 10 specialized agents. Each agent has a specific responsibility in the trading lifecycle, from market data validation and ML-powered forecasting to signal generation, risk management, order execution, and performance monitoring. Agents communicate through an event-driven Message Context Protocol (MCP) server that orchestrates their collaboration while maintaining system-wide context and decision history. This distributed intelligence architecture allows for autonomous operation, continuous learning, and adaptive strategy optimization without human intervention.

## Agent Architecture

The system consists of three layers of specialized agents:

**Execution Layer** (Core Trading Flow):
- **SignalGeneratorAgent**: Multi-strategy signal generation from price patterns, indicators, and ML forecasts
- **RiskManagerAgent**: Pre-trade validation, position sizing, and risk checks
- **ExecutionAgent**: Order execution on MT4 with smart order routing

**Data & Intelligence Layer** (Information Processing):
- **MarketDataAgent**: Real-time data validation, cleaning, and distribution
- **MLPredictionAgent**: ML-powered price forecasts and regime predictions
- **RegimeDetectionAgent**: Market regime classification for adaptive strategies

**Supervisory Layer** (Monitoring & Optimization):
- **PerformanceMonitorAgent**: Real-time P&L tracking and reporting
- **RiskOverseerAgent**: System-wide risk monitoring and emergency controls
- **StrategyOptimizerAgent**: Continuous parameter tuning and A/B testing

**Coordination**:
- **MCP Server**: Event-driven message broker with shared context and agent registry

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Autonomous Trading Decision Flow (Priority: P1)

The system autonomously executes the complete trading lifecycle: market data arrives → validated → forecast generated → signal created → risk checked → order executed → position monitored, with all agents coordinating through the MCP server without human intervention.

**Why this priority**: This is the core value proposition - autonomous end-to-end trading. Without this working, the entire agent system has no purpose.

**Independent Test**: Can be fully tested by simulating a market tick event, verifying each agent processes it in sequence, and confirming an order is executed when all validations pass.

**Acceptance Scenarios**:

1. **Given** the MCP server and all agents are running, **When** a new market tick arrives, **Then** MarketDataAgent validates it and emits a "tick_validated" event
2. **Given** a "tick_validated" event is emitted, **When** MLPredictionAgent receives it, **Then** it generates a forecast and emits a "forecast_generated" event
3. **Given** a "forecast_generated" event shows bullish signal, **When** SignalGeneratorAgent processes it, **Then** it creates a BUY signal and emits "signal_generated"
4. **Given** a "signal_generated" event, **When** RiskManagerAgent validates it, **Then** it calculates position size, checks limits, and emits "trade_approved" or "trade_rejected"
5. **Given** a "trade_approved" event, **When** ExecutionAgent receives it, **Then** it sends order to MT4 and emits "order_executed"
6. **Given** an "order_executed" event, **When** PerformanceMonitorAgent receives it, **Then** it updates P&L tracking and portfolio statistics

---

### User Story 2 - Agent Health Monitoring and Recovery (Priority: P1)

Operators need to monitor agent status, detect failures, and trigger automatic recovery when agents crash or become unresponsive.

**Why this priority**: Critical for 24/7 operation - system must self-heal to maintain autonomous trading without manual intervention.

**Independent Test**: Can be fully tested by killing an agent process, verifying the MCP server detects the failure, and confirming the agent automatically restarts.

**Acceptance Scenarios**:

1. **Given** all agents are running, **When** viewing the agent status dashboard, **Then** all agents show "healthy" status with last heartbeat timestamps
2. **Given** an agent crashes, **When** the MCP server checks heartbeats, **Then** it detects the failure within 10 seconds and marks agent as "unhealthy"
3. **Given** an agent is marked unhealthy, **When** automatic recovery is enabled, **Then** the agent process restarts within 30 seconds
4. **Given** an agent fails to restart after 3 attempts, **When** manual intervention is required, **Then** operators receive critical alerts with failure details
5. **Given** agents are degraded (slow response times), **When** performance thresholds are exceeded, **Then** warnings are generated before complete failure

---

### User Story 3 - Risk Oversight and Emergency Stop (Priority: P1)

The RiskOverseerAgent continuously monitors system-wide risk metrics and can trigger emergency stop-loss actions or halt trading when portfolio risk exceeds defined thresholds.

**Why this priority**: Prevents catastrophic losses - this is the safety net for autonomous operation and must be operational from day one.

**Independent Test**: Can be fully tested by simulating portfolio losses exceeding daily limits and verifying all trading is halted automatically.

**Acceptance Scenarios**:

1. **Given** the portfolio is trading normally, **When** daily loss reaches 90% of maximum threshold, **Then** RiskOverseerAgent emits warning alerts
2. **Given** daily loss exceeds maximum threshold, **When** RiskOverseerAgent detects breach, **Then** it emits "emergency_stop" event and halts all new trades
3. **Given** emergency stop is triggered, **When** open positions exist, **Then** all positions are automatically closed at market prices
4. **Given** trading is halted, **When** attempting to place new orders, **Then** ExecutionAgent rejects orders with "system_halted" status
5. **Given** emergency conditions are resolved, **When** operators manually approve resumption, **Then** trading resumes with reduced position sizing for safety

---

### User Story 4 - Multi-Strategy Signal Generation (Priority: P2)

SignalGeneratorAgent combines signals from multiple strategies (trend following, mean reversion, ML forecasts) with configurable weights to produce ensemble trading signals.

**Why this priority**: Important for diversification and robustness, but system can operate with a single strategy initially.

**Independent Test**: Can be fully tested by configuring multiple strategies, generating signals from each, and verifying the ensemble output matches expected weighted average.

**Acceptance Scenarios**:

1. **Given** three strategies are configured (trend, mean reversion, ML), **When** all produce signals, **Then** ensemble signal is weighted average based on strategy allocations
2. **Given** strategies have different confidence levels, **When** combining signals, **Then** higher confidence signals receive proportionally more weight
3. **Given** strategies conflict (one BUY, one SELL), **When** ensemble is calculated, **Then** net signal reflects the dominant direction or neutral if balanced
4. **Given** a strategy is performing poorly, **When** its Sharpe ratio drops below threshold, **Then** its weight is automatically reduced

---

### User Story 5 - Continuous Strategy Optimization (Priority: P2)

StrategyOptimizerAgent runs A/B tests on strategy parameters, analyzes performance metrics, and recommends parameter adjustments to improve returns.

**Why this priority**: Valuable for long-term performance but not required for initial operation - manual tuning can suffice initially.

**Independent Test**: Can be fully tested by running two parameter sets in parallel, comparing performance metrics, and verifying the better-performing set is promoted.

**Acceptance Scenarios**:

1. **Given** a strategy is running with baseline parameters, **When** optimization is triggered, **Then** alternative parameter sets are tested in paper trading mode
2. **Given** A/B test results after 100 trades, **When** variant outperforms baseline by 15%, **Then** StrategyOptimizerAgent recommends promoting the variant
3. **Given** a parameter recommendation, **When** operators approve it, **Then** the new parameters are deployed to live trading gradually (10% allocation first)
4. **Given** optimized parameters are deployed, **When** performance degrades, **Then** automatic rollback to baseline parameters occurs

---

### User Story 6 - Real-time Performance Monitoring (Priority: P2)

PerformanceMonitorAgent tracks P&L, win rate, Sharpe ratio, and drawdown in real-time, providing dashboards and alerts when metrics deviate from targets.

**Why this priority**: Important for visibility but not blocking for autonomous trading - operators can monitor manually initially.

**Independent Test**: Can be fully tested by executing trades, verifying P&L updates immediately, and confirming metrics recalculation.

**Acceptance Scenarios**:

1. **Given** a trade is executed, **When** PerformanceMonitorAgent receives the event, **Then** P&L is updated within 1 second
2. **Given** trading activity over 24 hours, **When** viewing performance dashboard, **Then** daily P&L, win rate, average profit/loss per trade are displayed
3. **Given** Sharpe ratio drops below 1.0, **When** threshold is breached, **Then** alerts are sent to operators
4. **Given** drawdown exceeds 10%, **When** RiskOverseerAgent is notified, **Then** position sizing is reduced by 50%

---

### User Story 7 - Market Regime Adaptation (Priority: P3)

RegimeDetectionAgent classifies current market conditions (trending, ranging, high volatility) and adapts strategy selection and parameters accordingly.

**Why this priority**: Enhances performance but system can operate with fixed strategies initially - nice to have for maturity.

**Acceptance Scenarios**:

1. **Given** market volatility increases, **When** RegimeDetectionAgent detects regime shift to "high_volatility", **Then** stop-loss distances are widened
2. **Given** market enters ranging mode, **When** regime is detected, **Then** mean-reversion strategies receive higher allocation
3. **Given** trending market detected, **When** SignalGeneratorAgent receives regime update, **Then** trend-following strategies are prioritized

---

### Edge Cases

- What happens when the MCP server crashes while agents are processing events?
- How does the system handle conflicting signals from different agents (e.g., RiskManager rejects but SignalGenerator keeps generating)?
- What occurs when ExecutionAgent cannot connect to MT4 for order execution?
- How are events handled when an agent is temporarily offline but comes back (event replay)?
- What happens during rapid market movements when forecasts become stale before execution?
- How does system behave when multiple agents simultaneously request position closes?
- What occurs when agents disagree on risk assessment (RiskManager vs. RiskOverseer)?
- How are circular dependencies prevented (Agent A waits for Agent B waits for Agent A)?
- What happens when event queues overflow during high-frequency market data?
- How does system handle timezone issues for global markets (24/5 operation)?

## Requirements *(mandatory)*

### Functional Requirements

**MCP Server (Coordination Layer):**

- **FR-001**: System MUST provide an event broker that receives, routes, and delivers events between all agents
- **FR-002**: MCP Server MUST maintain a registry of all active agents with their capabilities, status, and communication endpoints
- **FR-003**: MCP Server MUST support pub/sub pattern where agents subscribe to specific event types
- **FR-004**: MCP Server MUST maintain shared context accessible to all agents (current positions, account state, market conditions)
- **FR-005**: MCP Server MUST implement event replay capability for agents that reconnect after downtime
- **FR-006**: MCP Server MUST detect agent failures through heartbeat monitoring (10-second intervals)
- **FR-007**: MCP Server MUST log all events with timestamps, source agent, destination agents, and payload for audit trails
- **FR-008**: MCP Server MUST prevent circular event loops by tracking event chains and breaking cycles

**MarketDataAgent (Data Validation):**

- **FR-009**: MarketDataAgent MUST validate incoming market data for completeness (OHLCV fields present)
- **FR-010**: MarketDataAgent MUST detect and flag anomalous data (price spikes, gaps, negative values)
- **FR-011**: MarketDataAgent MUST emit "tick_validated" events for clean data and "data_anomaly" events for issues
- **FR-012**: MarketDataAgent MUST forward validated data to all subscribers within 10ms of receipt
- **FR-013**: MarketDataAgent MUST maintain data quality metrics (validation pass rate, anomaly frequency)

**MLPredictionAgent (Forecasting):**

- **FR-014**: MLPredictionAgent MUST generate price forecasts for configured horizons (1h, 4h, 24h) upon receiving validated market data
- **FR-015**: MLPredictionAgent MUST load production models from the model registry on startup
- **FR-016**: MLPredictionAgent MUST include confidence intervals with all forecasts
- **FR-017**: MLPredictionAgent MUST emit "forecast_generated" events containing predictions for all configured horizons
- **FR-018**: MLPredictionAgent MUST cache recent forecasts to avoid redundant predictions for duplicate tick events
- **FR-019**: MLPredictionAgent MUST handle model loading failures gracefully and emit "model_unavailable" events

**RegimeDetectionAgent (Market Classification):**

- **FR-020**: RegimeDetectionAgent MUST classify current market conditions as trending, ranging, or volatile based on statistical indicators
- **FR-021**: RegimeDetectionAgent MUST emit "regime_changed" events when market conditions shift between classifications
- **FR-022**: RegimeDetectionAgent MUST calculate volatility metrics (ATR, historical volatility) continuously
- **FR-023**: RegimeDetectionAgent MUST maintain regime history for performance analysis

**SignalGeneratorAgent (Trading Signals):**

- **FR-024**: SignalGeneratorAgent MUST process forecasts and generate BUY, SELL, or NEUTRAL signals based on configured strategies
- **FR-025**: SignalGeneratorAgent MUST support multiple strategy types (trend following, mean reversion, ML-based)
- **FR-026**: SignalGeneratorAgent MUST combine signals from multiple strategies using weighted ensemble
- **FR-027**: SignalGeneratorAgent MUST include signal strength (0-100) and confidence level with all signals
- **FR-028**: SignalGeneratorAgent MUST emit "signal_generated" events with symbol, direction, strength, and recommended entry price
- **FR-029**: SignalGeneratorAgent MUST respect trading hours and market status (do not generate signals when markets are closed)

**RiskManagerAgent (Pre-Trade Risk Checks):**

- **FR-030**: RiskManagerAgent MUST validate all trading signals against position limits (max open positions, max position size)
- **FR-031**: RiskManagerAgent MUST calculate position sizing based on account balance and risk percentage (default 2% per trade)
- **FR-032**: RiskManagerAgent MUST calculate stop-loss and take-profit levels based on ATR and risk/reward ratio
- **FR-033**: RiskManagerAgent MUST check portfolio exposure limits (max exposure per symbol, total market exposure)
- **FR-034**: RiskManagerAgent MUST emit "trade_approved" events with position size, SL, TP when checks pass
- **FR-035**: RiskManagerAgent MUST emit "trade_rejected" events with rejection reasons when checks fail
- **FR-036**: RiskManagerAgent MUST apply stricter limits during high volatility periods

**ExecutionAgent (Order Placement):**

- **FR-037**: ExecutionAgent MUST send approved trades to MT4 for execution via the trading API
- **FR-038**: ExecutionAgent MUST retry failed orders with exponential backoff (3 attempts maximum)
- **FR-039**: ExecutionAgent MUST emit "order_executed" events with fill price, execution time, and order ID upon successful execution
- **FR-040**: ExecutionAgent MUST emit "order_failed" events with failure reasons for unsuccessful orders
- **FR-041**: ExecutionAgent MUST validate MT4 connectivity before sending orders
- **FR-042**: ExecutionAgent MUST support paper trading mode for testing without real money
- **FR-043**: ExecutionAgent MUST log all order attempts with full details for compliance

**PerformanceMonitorAgent (P&L Tracking):**

- **FR-044**: PerformanceMonitorAgent MUST update profit/loss calculations within 1 second of trade execution
- **FR-045**: PerformanceMonitorAgent MUST calculate cumulative P&L, daily P&L, and P&L by strategy
- **FR-046**: PerformanceMonitorAgent MUST track win rate, average profit per trade, average loss per trade
- **FR-047**: PerformanceMonitorAgent MUST calculate Sharpe ratio, maximum drawdown, and recovery factor
- **FR-048**: PerformanceMonitorAgent MUST emit "performance_alert" events when metrics deviate from targets
- **FR-049**: PerformanceMonitorAgent MUST maintain performance history for backtesting and analysis

**RiskOverseerAgent (Portfolio Risk Management):**

- **FR-050**: RiskOverseerAgent MUST monitor daily loss and trigger emergency stop when loss exceeds maximum threshold
- **FR-051**: RiskOverseerAgent MUST track portfolio-wide metrics (total exposure, margin usage, VaR)
- **FR-052**: RiskOverseerAgent MUST emit "emergency_stop" event when critical risk thresholds are breached
- **FR-053**: RiskOverseerAgent MUST automatically close all positions when emergency stop is triggered
- **FR-054**: RiskOverseerAgent MUST prevent new trades during emergency stop status
- **FR-055**: RiskOverseerAgent MUST require manual operator approval to resume trading after emergency stop
- **FR-056**: RiskOverseerAgent MUST implement gradual risk scaling after emergency stop recovery

**StrategyOptimizerAgent (Continuous Improvement):**

- **FR-057**: StrategyOptimizerAgent MUST run A/B tests on strategy parameters using paper trading
- **FR-058**: StrategyOptimizerAgent MUST compare performance metrics between baseline and variant parameter sets
- **FR-059**: StrategyOptimizerAgent MUST emit "optimization_recommendation" events when variants outperform baseline by configurable threshold
- **FR-060**: StrategyOptimizerAgent MUST support gradual rollout of optimized parameters (10% allocation initially)
- **FR-061**: StrategyOptimizerAgent MUST automatically rollback parameters if performance degrades after deployment
- **FR-062**: StrategyOptimizerAgent MUST maintain optimization history with parameter sets and outcomes

**Agent Health & Monitoring:**

- **FR-063**: All agents MUST send heartbeat events to MCP Server every 5 seconds
- **FR-064**: All agents MUST implement graceful shutdown with event cleanup
- **FR-065**: All agents MUST support hot restart without losing in-flight event processing
- **FR-066**: All agents MUST expose health check endpoints reporting status, uptime, and resource usage
- **FR-067**: All agents MUST log errors, warnings, and critical events with structured logging
- **FR-068**: System MUST provide unified dashboard showing status of all agents in real-time

### Key Entities

- **Agent**: Autonomous component with unique ID, type (execution/data/supervisory), status (running/stopped/degraded), capabilities list, and communication channel
- **Event**: Message passed between agents containing event_type, timestamp, source_agent_id, payload (data specific to event type), correlation_id (for tracking event chains)
- **TradingSignal**: Generated by SignalGeneratorAgent containing symbol, direction (BUY/SELL/NEUTRAL), strength (0-100), confidence (0-1), recommended_entry_price, timestamp
- **TradeApproval**: Validated trade from RiskManagerAgent containing signal_id, approved (boolean), position_size, stop_loss_price, take_profit_price, rejection_reasons (if rejected)
- **OrderExecution**: Result from ExecutionAgent containing order_id, fill_price, execution_time, status (filled/partial/failed), failure_reason (if failed)
- **PerformanceMetrics**: Tracked by PerformanceMonitorAgent containing cumulative_pnl, daily_pnl, win_rate, sharpe_ratio, max_drawdown, trades_count
- **RiskLimits**: Configuration defining max_daily_loss, max_position_size, max_open_positions, max_exposure_per_symbol, used by RiskManagerAgent and RiskOverseerAgent
- **AgentRegistry**: Maintained by MCP Server with agent_id, agent_type, status, last_heartbeat, subscribed_events, capabilities
- **SharedContext**: Global state accessible to all agents including current_positions, account_balance, market_regime, system_status (trading/halted)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System autonomously executes complete trading cycles (data → forecast → signal → risk check → execution → monitoring) within 500ms end-to-end
- **SC-002**: All 10 agents maintain 99.5% uptime during market hours (24/5 operation) with automatic recovery from failures within 30 seconds
- **SC-003**: Agent communication latency remains under 100ms (p95) for event delivery through MCP Server under normal load
- **SC-004**: RiskOverseerAgent successfully triggers emergency stop within 5 seconds of daily loss threshold breach, with 100% success rate
- **SC-005**: Agent failure detection and recovery occurs within 30 seconds for 95% of agent crashes without loss of in-flight events
- **SC-006**: StrategyOptimizerAgent identifies performance-improving parameter sets with 70% accuracy in A/B tests over 100 trades
- **SC-007**: System operates autonomously for 7 consecutive days without requiring manual intervention or experiencing critical failures
- **SC-008**: Event logs capture 100% of agent communications with complete audit trail for compliance and debugging
- **SC-009**: Agent dashboard provides real-time visibility into all 10 agents with status updates within 1 second of state changes
- **SC-010**: Performance metrics (P&L, win rate, Sharpe ratio) are calculated and updated within 1 second of trade execution

## Assumptions & Dependencies

### Assumptions

- Agents will run as separate processes or containers with independent lifecycles
- MCP Server will be the single source of truth for system state and agent coordination
- Initial deployment will focus on CrudeOIL trading but architecture supports multiple symbols
- Operators will monitor the system during initial deployment phases before full autonomy
- Risk limits and thresholds will be configurable per trading environment (paper/live)
- Agents can tolerate brief network partitions and will reconnect automatically
- Event ordering is not strictly guaranteed but eventual consistency is acceptable

### Dependencies

- **MT4 Integration**: ExecutionAgent requires MT4 trading API for order placement (001-mt4-integration)
- **ML Forecasting**: MLPredictionAgent requires trained models from model registry (003-ml-forecasting-pipeline)
- **Market Data**: MarketDataAgent requires real-time tick data from MT4 connection (001-mt4-integration)
- **Database**: All agents require PostgreSQL for state persistence and historical data
- **Message Broker**: MCP Server requires event queue system (Redis pub/sub or similar)
- **Monitoring Stack**: Agent health monitoring requires observability infrastructure (Prometheus, Grafana)
- **Agent Framework**: Base agent classes and MCP communication protocol must be defined

## Out of Scope

- Natural language interaction with agents (voice/chat commands) - future enhancement
- Multi-broker support beyond MT4 - future enhancement
- Distributed agent deployment across geographic regions - future enhancement
- Machine learning-powered agent coordination (meta-learning) - future enhancement
- Integration with external signal providers - future enhancement
- Social trading / copy trading features - future enhancement
- Mobile app for agent monitoring - future enhancement (web dashboard sufficient initially)

## Related Documentation

- [001-mt4-integration spec](../001-mt4-integration/spec.md) - Market data source and order execution
- [003-ml-forecasting-pipeline spec](../003-ml-forecasting-pipeline/spec.md) - ML models for MLPredictionAgent
- [002-fastapi-dashboard-api spec](../002-fastapi-dashboard-api/spec.md) - Database and API infrastructure
- CLAUDE.md - Agent architecture and coordination patterns
- PROJECT_REBUILD_SPECIFICATION.md - Phase 2.5: Agent system implementation details
- RiseTrader_FINAL_BUILD_PLAN.md - Agent development timeline and integration approach
