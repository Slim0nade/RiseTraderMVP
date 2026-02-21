# Feature Specification: Backtesting Engine

**Feature Branch**: `006-backtesting-engine`
**Created**: 2025-12-11
**Status**: Draft
**Input**: User description: "Backtesting Engine for validating multi-agent trading decisions against historical market data. Simulates trade execution, tracks P&L, and generates performance metrics (Sharpe, drawdown, win rate). Required for RL training (Gymnasium environment) and A/B testing agent configurations. Uses existing 13.5M candle PostgreSQL database. Supports two modes: full agent pipeline (LLM decisions) and synthetic fast mode (rule-based, 1000x faster for hyperparameter search)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Historical Performance Validation (Priority: P1)

A trader or system administrator needs to validate that the multi-agent trading system would have performed profitably on historical market data before deploying it to live trading. They configure the backtesting engine with a date range, initial capital, and agent configuration, then run a simulation that replays historical candles and executes the full agent decision pipeline (including LLM-powered agents). The system generates a comprehensive performance report showing P&L, Sharpe ratio, maximum drawdown, win rate, and trade-by-trade execution log.

**Why this priority**: This is the core value proposition of the backtesting engine. Without the ability to validate agent decisions against historical data, users cannot confidently deploy the trading system. This directly addresses risk management and system validation needs.

**Independent Test**: Can be fully tested by configuring a backtest run with specific date range and agent settings, executing the simulation, and verifying that realistic P&L metrics and trade logs are generated. Delivers immediate value by showing whether the agent configuration would have been profitable.

**Acceptance Scenarios**:

1. **Given** a configured agent system and selected date range with available historical data, **When** user initiates a backtest with initial capital of $10,000, **Then** system replays all candles in chronological order, executes agent decisions at each timepoint, simulates trade execution with realistic slippage and commissions, and produces a final performance report
2. **Given** a completed backtest run, **When** user views the performance report, **Then** report displays total P&L (dollar amount and percentage), Sharpe ratio, maximum drawdown (percentage and duration), win rate (percentage of profitable trades), total number of trades, and average trade duration
3. **Given** a backtest with multiple trades executed, **When** user examines the trade log, **Then** each trade entry shows timestamp, symbol, action (buy/sell), quantity, entry price, exit price, P&L, holding duration, and the agent decision rationale
4. **Given** a backtest running with the full agent pipeline, **When** market conditions trigger agent decisions, **Then** all agent interactions (signal generation, risk validation, position sizing, execution) are logged with timestamps and can be reviewed post-simulation

---

### User Story 2 - Rapid Strategy Optimization (Priority: P2)

A quant researcher needs to test hundreds of different agent parameter configurations to find optimal settings. They switch to synthetic fast mode (rule-based decisions instead of LLM calls) and run a hyperparameter search across multiple agent configurations simultaneously. The system processes years of historical data in minutes instead of hours, generates performance metrics for each configuration, and ranks them by Sharpe ratio or other selected criteria.

**Why this priority**: Enables rapid iteration and optimization without waiting hours for LLM-based backtests. Critical for parameter tuning and strategy development, but depends on P1 validation functionality being in place first.

**Independent Test**: Can be tested by defining a parameter grid (e.g., 50 different risk threshold combinations), running synthetic mode backtests in parallel, and verifying that results are generated 100x+ faster than full mode while maintaining statistical validity. Delivers value by accelerating the research cycle.

**Acceptance Scenarios**:

1. **Given** a parameter grid with 100 different agent configurations, **When** user runs batch backtest in synthetic fast mode, **Then** system processes all configurations using rule-based decision logic (no LLM calls), completes within 1/100th the time of full mode, and generates performance metrics for each configuration
2. **Given** completed synthetic mode backtests for multiple configurations, **When** user requests ranked results, **Then** system displays all configurations sorted by selected metric (Sharpe ratio, total return, or max drawdown), showing top performers and statistical significance of differences
3. **Given** a researcher identifying a promising configuration in synthetic mode, **When** they run the same configuration in full agent mode for validation, **Then** system executes with actual LLM agent decisions and results show reasonable correlation with synthetic mode predictions (within expected variance)

---

### User Story 3 - Reinforcement Learning Environment (Priority: P3)

An ML engineer building a reinforcement learning agent needs a training environment that simulates realistic trading conditions. They integrate the backtesting engine as a Gymnasium environment where the RL agent receives market state observations, takes actions (trade decisions), and receives rewards based on P&L. The environment handles episode management, state transitions, and reward calculation while using the backtesting engine's historical data replay and P&L tracking capabilities.

**Why this priority**: Enables advanced ML-based trading strategies, but requires P1 and P2 functionality as foundation. This is an extended use case that builds on core backtesting capabilities.

**Independent Test**: Can be tested by instantiating a Gymnasium environment, running a simple RL training loop for 1000 episodes, and verifying that the environment correctly provides observations, accepts actions, calculates rewards, and handles episode resets. Delivers value by enabling RL agent development.

**Acceptance Scenarios**:

1. **Given** a Gymnasium-compatible environment wrapper around the backtesting engine, **When** an RL agent calls `env.reset()`, **Then** environment initializes at a random starting point in historical data with defined initial capital and returns the initial market state observation
2. **Given** an active RL training episode, **When** agent calls `env.step(action)` with a trading action (buy/sell/hold and quantity), **Then** environment advances time by one candle, simulates trade execution, calculates reward based on P&L change, returns next observation and done flag if episode ends
3. **Given** an RL training run over 1000 episodes, **When** episodes complete, **Then** environment cycles through different historical periods to ensure diverse training data, tracks cumulative performance metrics, and provides episode statistics for monitoring training progress

---

### User Story 4 - Agent Configuration Comparison (Priority: P3)

A trading team needs to A/B test different agent configurations (e.g., conservative vs aggressive risk settings, different ML models, alternative signal generation strategies) to determine which performs best on historical data. They define two or more configurations, run parallel backtests on the same historical period with identical starting capital, and compare side-by-side performance reports with statistical significance tests.

**Why this priority**: Supports evidence-based decision making for system configuration, but requires core backtesting functionality (P1) to be in place first. This is a comparative analysis use case.

**Independent Test**: Can be tested by defining two agent configurations with different risk parameters, running both backtests on the same date range, and verifying that results are directly comparable with statistical tests showing whether performance differences are significant. Delivers value by enabling objective configuration decisions.

**Acceptance Scenarios**:

1. **Given** two agent configurations defined as "Config A" and "Config B", **When** user initiates parallel A/B test over the same historical period with same initial capital, **Then** system runs both backtests independently with identical market data replay and generates separate performance reports
2. **Given** completed A/B test results, **When** user views comparison report, **Then** report displays side-by-side metrics (P&L, Sharpe, drawdown, win rate) for both configurations, highlights statistically significant differences, and shows equity curves on the same chart for visual comparison
3. **Given** multiple trades executed by both configurations, **When** analyzing trade overlap, **Then** report identifies trades taken by both configs (consensus trades), trades unique to each config, and performance breakdown for consensus vs divergent decisions

---

### Edge Cases

- What happens when historical data has gaps (missing candles) during backtest replay?
- How does the system handle agent decisions that would require more capital than available (margin calls)?
- What if a backtest runs for extended periods (years of data) and exhausts memory?
- How are dividends, splits, and other corporate actions handled in historical data?
- What happens when synthetic fast mode and full agent mode produce significantly different results?
- How does the system handle time zone differences and market hours in historical data?
- What if an agent decision takes longer to compute than the candle interval duration?
- How are partial fills and order rejections simulated realistically?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST replay historical market data (OHLCV candles) from the existing PostgreSQL database in strict chronological order, advancing time step-by-step to simulate live market conditions
- **FR-002**: System MUST support two execution modes: full agent pipeline mode (where actual configured agents make LLM-powered decisions) and synthetic fast mode (where rule-based logic approximates agent decisions for speed)
- **FR-003**: System MUST simulate realistic trade execution including order slippage (estimated 0.1-0.5% from closing price), commission costs (per trade and/or percentage-based), and order fill logic based on candle high/low ranges
- **FR-004**: System MUST track simulated portfolio state throughout backtest including cash balance, open positions with entry prices and quantities, unrealized P&L on open positions, and realized P&L from closed positions
- **FR-005**: System MUST calculate and report standard trading performance metrics including total return (percentage and dollar amount), Sharpe ratio (annualized risk-adjusted return), maximum drawdown (peak-to-trough decline in percentage), win rate (percentage of profitable closed trades), total number of trades, average trade duration, and profit factor (gross profit / gross loss)
- **FR-006**: System MUST generate detailed trade logs showing every executed trade with timestamp, symbol, action (buy/sell/close), quantity, entry price, exit price (for closed positions), P&L, fees incurred, and the agent decision context (which agent triggered the trade and why)
- **FR-007**: System MUST allow users to configure backtest parameters including date range (start/end dates), initial capital amount, specific agent configuration to test (or reference to saved configuration), slippage assumptions, and commission structure
- **FR-008**: System MUST implement a Gymnasium-compatible environment interface that exposes `reset()`, `step(action)`, observation space, action space, and reward calculation for reinforcement learning integration
- **FR-009**: System MUST support batch execution of multiple backtest runs with different parameters and provide aggregated results ranked by user-selected performance metric (Sharpe, total return, or max drawdown)
- **FR-010**: System MUST validate that requested date ranges have complete historical data available and warn users if data gaps exist that could compromise backtest validity
- **FR-011**: System MUST implement proper episode management for RL environment mode including random starting points in historical data, episode length limits (maximum number of candles or time duration), and reset logic that preserves statistical validity
- **FR-012**: System MUST support comparison of multiple agent configurations by running them on identical historical periods and providing side-by-side performance metrics with statistical significance indicators
- **FR-013**: System MUST enforce realistic trading constraints including minimum position sizes, maximum leverage limits (configurable), prevention of short selling if not enabled, and capital preservation (cannot trade with negative balance)
- **FR-014**: System MUST log all agent interactions and decisions during full pipeline mode including signals generated, risk assessments, position sizing calculations, and execution confirmations for post-backtest analysis
- **FR-015**: System MUST handle market hours correctly by only processing candles during active trading hours for the relevant market and symbol, skipping weekends and holidays based on a configurable trading calendar per symbol/market (24/7 for crypto, standard market hours for traditional assets)

### Key Entities

- **Backtest Configuration**: Defines the parameters for a backtest run including date range, initial capital, agent configuration reference, slippage assumptions, commission structure, execution mode (full/synthetic), and optional constraints (max leverage, allowed symbols)
- **Backtest Run**: Represents a completed or in-progress backtest execution with unique identifier, configuration reference, start/end timestamps, current status (running/completed/failed), and link to generated results
- **Simulated Portfolio State**: Snapshot of portfolio at any point during backtest including timestamp, cash balance, list of open positions (symbol, quantity, entry price, current price, unrealized P&L), total portfolio value, and available buying power
- **Simulated Trade**: Record of a single executed trade during backtest including entry timestamp, exit timestamp (if closed), symbol, action (buy/sell), quantity, entry price, exit price, gross P&L, fees paid, net P&L, holding duration, and agent decision context
- **Performance Metrics**: Aggregated statistics for a backtest run including total return (%), Sharpe ratio, maximum drawdown (%), drawdown duration, win rate (%), total trades, average trade duration, profit factor, average win size, average loss size, and equity curve data points
- **Agent Decision Log**: Detailed record of agent interactions during full pipeline mode including timestamp, agent identifier, decision type (signal/risk/execution), input data received, output decision made, and execution outcome
- **Parameter Grid**: Collection of parameter combinations for batch optimization including parameter names, value ranges or discrete options, and total number of configurations to test
- **Gymnasium Environment State**: RL environment state including current market observation (recent candles, indicators, portfolio state), available actions (buy/sell/hold with quantity ranges), reward calculation method, episode configuration (length, starting capital), and episode statistics

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can configure and execute a backtest covering 6 months of historical data with full agent pipeline mode and receive comprehensive performance results within 30 minutes for a single symbol
- **SC-002**: Synthetic fast mode processes the same 6-month backtest at least 100 times faster than full agent mode while maintaining correlation of 0.7+ in key metrics (total return, Sharpe ratio)
- **SC-003**: Generated performance reports include all standard trading metrics (P&L, Sharpe, drawdown, win rate) with accuracy verified against manual calculations for sample trades (within 0.1% variance)
- **SC-004**: Trade logs capture every simulated trade with complete details (prices, timestamps, P&L, fees) enabling full reconstruction of portfolio state at any point in time
- **SC-005**: Gymnasium environment supports stable RL training runs of 10,000+ episodes without memory leaks or performance degradation
- **SC-006**: Users can run parallel batch optimizations of 100+ parameter configurations and identify top-performing configurations ranked by selected metric within 2 hours
- **SC-007**: A/B comparison tests between two agent configurations provide statistically significant results (p-value < 0.05) when performance differences exceed 10% in key metrics
- **SC-008**: System validates data completeness before backtest execution and reports any gaps in historical data with specific date ranges affected
- **SC-009**: 95% of backtest runs complete successfully without errors when using valid configurations and complete historical data
- **SC-010**: Backtest results are reproducible - running the same configuration on the same date range produces identical results across multiple executions (deterministic replay)
