# Feature Specification: Intelligent Multi-Agent Trading System

**Feature Branch**: `005-intelligent-agent-trading`
**Created**: 2025-12-01
**Status**: Draft
**Input**: User description: "RiseTraderMVP: Intelligent Multi-Agent Trading System - Build an autonomous AI trading system where ALL decisions—including position sizing, stop-loss placement, and take-profit targets—are made by intelligent agents that learn and adapt from data. No hardcoded formulas. Every parameter is either learned through reinforcement learning or dynamically reasoned by agents with full context."

## Clarifications

### Session 2025-12-01

- **Q: Portfolio allocation architecture** → **A**: System must support portfolio-level capital allocation across multiple strategies (e.g., 20% CrudeOIL scraping, 20% CrudeOIL long term (not long vs. short, but 90+ days), 20% Crude Oil medium term (7 days - 90 days), 20% Gold or mixed, 20% Reserve). Position sizing agents work within their allocated capital, not total account balance. Supports both static (config-based) and dynamic (Portfolio Allocator Agent) allocation modes.

- **Q: ML model integration protocol** → **A**: ML forecasting models (TCN, TFT, FEDformer) and calculation tools (Kelly criterion, ATR, support/resistance) are exposed as MCP (Model Context Protocol) tools that agents call. This integrates with Feature 003 ML Forecasting Pipeline.

- **Q: Execution broker integration** → **A**: Order execution uses existing MT4/ZMQ bridge from Feature 001 for order placement, fill management, and position tracking. Generic "broker API" references in this spec refer to the MT4 integration layer.

- **Q: Multi-instrument support scope** → **A**: Initial deployment supports multiple instruments simultaneously (Gold, Crude Oil, Stocks, Forex strategies), not single instrument. BUT INITIALLY WE WILL TEST ONY WITH CRUDEOIL AS IT'S THE ONLY FULL HISTORICAL DATA WE HAVE. Each instrument has dedicated agent teams. Constraint updated from "single instrument initially" to "initially supports 2-3 instruments with plan for expansion."

- **Q: Dual-LLM cost optimization pattern** → **A**: Agent system uses two-tier LLM strategy: (1) Quick-think LLM (e.g., Qwen3-14B) for data gathering, summarization, routine analysis; (2) Deep-think LLM (e.g., DeepSeek-R1-14B) for complex reasoning, adversarial debate, critical decisions. This pattern generalizes beyond just bear researcher to all agent types.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adaptive Position Sizing Based on Market Context (Priority: P1)

As a trader, I want the system to automatically determine how much capital to risk on each trade based on current market conditions, my portfolio state, the current strategy allocated balance and trade conviction—rather than using a fixed percentage—so that I can maximize returns while protecting capital during different market regimes.

**Why this priority**: Position sizing is the most critical risk management decision. Fixed percentage approaches (e.g., always risk 2%) fail to adapt to changing market volatility, portfolio drawdown, correlation exposure, or trade confidence. This is the foundation for intelligent risk management.

**Independent Test**: Can be fully tested by executing trades across different market regimes (high volatility vs. low volatility, winning streak vs. drawdown, high confidence signals vs. low confidence) and verifying that position sizes vary appropriately rather than remaining constant.

**Acceptance Scenarios**:

1. **Given** the system is in a 10% drawdown with high market volatility, **When** a moderate-confidence trade signal is generated, **Then** the position size should be reduced compared to normal conditions (e.g., from 2% to 0.8% risk) with a rationale explaining drawdown adjustment and volatility regime.

2. **Given** the portfolio has high correlation exposure to USD pairs and a new USD-correlated trade is proposed, **When** the position sizing agent evaluates the trade, **Then** the position size should be reduced to account for existing correlation exposure with documented reasoning.

3. **Given** a high-conviction trade signal with mathematical edge (positive Kelly criterion output), **When** market conditions are favorable (low volatility, no drawdown), **Then** the position size should be larger than baseline with clear attribution to conviction level and Kelly fraction used.

4. **Given** a major economic event (e.g., FOMC announcement) is scheduled within the trade timeframe, **When** the position sizing agent evaluates the trade, **Then** the position size should be reduced to account for event risk with explicit documentation of the adjustment.

---

### User Story 2 - Intelligent Stop-Loss Placement Using Market Structure (Priority: P1)

As a trader, I want the system to place stop-losses based on actual market structure, volatility regimes, and probability analysis—rather than fixed ATR multiples—so that I avoid being stopped out unnecessarily while still protecting capital effectively.

**Why this priority**: Fixed ATR multiples (e.g., 1.5x ATR) ignore market context and often result in premature stop-outs at predictable levels. Intelligent stop placement considering support/resistance, liquidity zones, and regime-adjusted volatility significantly improves trade outcomes.

**Independent Test**: Can be fully tested by comparing stop-loss placements across different market conditions and verifying that stops are positioned beyond key market structure levels, adjusted for volatility regime, and avoid predictable liquidity zones.

**Acceptance Scenarios**:

1. **Given** a long trade entry with a clear support level 20 pips below entry and ATR of 15 pips, **When** the stop-loss agent determines placement, **Then** the stop should be positioned beyond the support level (e.g., 22 pips) rather than at the 1.5x ATR level (22.5 pips), with rationale citing market structure priority.

2. **Given** a high-volatility regime (VIX > 30), **When** the stop-loss agent calculates stop distance, **Then** the stop should use a wider ATR multiplier than in low-volatility regimes to avoid being stopped out by normal noise, with documented regime adjustment.

3. **Given** analysis shows a liquidity cluster (stop-loss concentration zone) at a common ATR multiple level, **When** the stop-loss agent places the stop, **Then** the stop should be positioned away from the cluster to avoid being targeted by liquidity hunters, with reasoning documented.

4. **Given** probability analysis from ML forecasts indicating 85% probability of reaching the target before stop, **When** the stop-loss agent evaluates placement, **Then** this probability estimate should influence the stop distance decision and be documented in the rationale.

---

### User Story 3 - Probabilistic Take-Profit Targeting (Priority: P1)

As a trader, I want the system to set take-profit targets based on probability distributions from ML models and key market levels—rather than fixed risk-reward ratios—so that I can capture realistic profit potential while managing expectations probabilistically.

**Why this priority**: Fixed risk-reward ratios (e.g., always 2:1) ignore the actual probability distribution of price movements. A 2:1 target with 20% probability of being reached is worse than a 1.5:1 target with 70% probability. Probabilistic targeting maximizes expected value.

**Independent Test**: Can be fully tested by verifying that take-profit levels align with probability density from ML forecasts, respect key resistance/support levels, and include partial profit opportunities when appropriate.

**Acceptance Scenarios**:

1. **Given** an ML forecast showing 70% probability mass concentrated within 30 pips and only 15% probability beyond 50 pips, **When** the take-profit agent sets targets, **Then** the primary target should be around the 70% probability zone (30 pips) rather than a fixed 2:1 ratio that might be 60 pips, with probability reasoning documented.

2. **Given** a strong resistance level at 50 pips with an ML forecast showing probability drops sharply beyond this level, **When** the take-profit agent determines targets, **Then** the target should be set just before the resistance level with documentation citing both technical structure and probability distribution.

3. **Given** an ML forecast showing multiple high-probability zones (40 pips with 60% probability, 70 pips with 30% additional probability), **When** the take-profit agent creates the profit plan, **Then** partial targets should be set at both zones (e.g., take 50% profit at 40 pips, 50% at 70 pips) with expected value calculations documented.

4. **Given** a trade with asymmetric risk-reward where the probability-weighted expected value is positive despite a sub-1:1 risk-reward ratio, **When** the take-profit agent evaluates the target, **Then** the agent should approve the trade if expected value is positive and document the probability-weighted rationale.

---

### User Story 4 - Multi-Perspective Analysis Through Agent Debate (Priority: P2)

As a trader, I want to receive trade recommendations that have been stress-tested through adversarial debate between bull and bear perspectives—consuming analysis from technical, fundamental, and sentiment agents—so that I avoid confirmation bias and understand both the case for and against each trade.

**Why this priority**: Single-perspective analysis leads to confirmation bias. Having specialized agents build the strongest bull case and the strongest bear case (including rebuttals) produces more robust trade decisions. This is critical for risk management but can operate independently of the execution system.

**Independent Test**: Can be fully tested by verifying that every trade recommendation includes both a bull thesis and a bear counterargument, with each perspective supported by specific evidence from technical, fundamental, and sentiment analysis.

**Acceptance Scenarios**:

1. **Given** technical analysis shows a strong bullish signal (multiple ML models agree), **When** the debate process runs, **Then** the bear researcher must identify potential risks (e.g., upcoming economic events, divergent sentiment data, overbought conditions) even if the technical case is strong, with specific evidence cited.

2. **Given** a trade recommendation from the debate layer, **When** presented to the user, **Then** the output must include: (a) bull thesis with supporting evidence, (b) bear counterarguments with rebuttals to bull points, (c) key factors from each perspective, (d) dissenting views that survived debate, with all claims traceable to specific analyst reports.

3. **Given** fundamental analysis shows deteriorating macro conditions while technical analysis shows bullish patterns, **When** the debate process runs, **Then** both perspectives must be represented with weighted importance, and the trade decision agent must explicitly address the conflict in its reasoning.

4. **Given** sentiment analysis shows extreme crowded positioning in one direction, **When** the bear researcher builds the contrarian case, **Then** this positioning data must be prominently featured in the bear argument with specific metrics (e.g., "90% of retail traders long, smart money reducing positions").

---

### User Story 5 - Continuous Agent Improvement Through Reinforcement Learning (Priority: P2)

As a system operator, I want decision-making agents (position sizing, stop-loss, take-profit, trade decision) to continuously learn from outcomes and improve their strategies through reinforcement learning—so that the system adapts to changing market conditions and improves performance over time without manual recalibration.

**Why this priority**: Static decision rules become outdated as markets evolve. RL-trained agents can discover optimal strategies through trial and error in backtesting environments and adapt to regime changes. This is essential for long-term system viability but requires the core decision infrastructure to be in place first.

**Independent Test**: Can be fully tested by running walk-forward backtests where agents are trained on historical data, validated on out-of-sample periods, and performance metrics (Sharpe ratio, drawdown, win rate) show measurable improvement compared to baseline strategies.

**Acceptance Scenarios**:

1. **Given** a position sizing agent trained on 2 years of historical data with reward signal based on Sharpe contribution minus drawdown penalty, **When** evaluated on an out-of-sample 6-month validation period, **Then** the agent's position sizing decisions should demonstrate better risk-adjusted returns than a fixed percentage baseline (e.g., Sharpe improvement of >0.3), with decision logs showing learned behaviors.

2. **Given** a stop-loss agent being trained with reward signal minimizing unnecessary stop-outs while protecting capital, **When** the training converges, **Then** the agent should demonstrate measurably lower stop-out rates on winning trades while maintaining capital protection on losing trades, with statistical significance across multiple validation windows.

3. **Given** a trade decision agent trained with reward signal based on realized PnL and direction accuracy, **When** market regime changes from trending to mean-reverting, **Then** the agent should adapt its decision criteria within the retraining cycle, demonstrable through decision log analysis showing different factor weightings.

4. **Given** multiple RL training runs across different regimes, **When** performing walk-forward validation with rolling train/validation/test windows, **Then** the system must detect and alert on out-of-sample performance degradation exceeding defined thresholds (e.g., >20% Sharpe decline), triggering retraining requirements.

---

### User Story 6 - Multi-Model Provider Cost-Effectiveness Testing (Priority: P3)

As a system operator, I want to run A/B tests comparing different AI model providers (proprietary like GPT-4o, Claude, Gemini vs. open-source local models like Qwen3, DeepSeek-R1) across the same trading scenarios—so that I can identify the most cost-effective model configuration that balances performance with inference costs.

**Why this priority**: LLM inference costs vary dramatically (proprietary models can cost 100x more than local open-source models). If local models can achieve 85% of the performance at 1% of the cost, the ROI is significantly better. This optimization is valuable but not critical for initial system operation.

**Independent Test**: Can be fully tested by running parallel paper trading sessions with different model configurations and comparing: (a) trading performance (returns, Sharpe, max drawdown), (b) per-trade LLM costs, (c) cost-effectiveness metric (return per dollar spent on LLM inference).

**Acceptance Scenarios**:

1. **Given** two agent configurations (Config A: GPT-4o for all agents, Config B: Qwen3-14B for analysts + DeepSeek-R1 for bear researcher), **When** both run in paper trading mode for 30 days on the same market data, **Then** the system must track and report: total LLM cost per config, total return per config, return-per-dollar-spent metric, with statistical significance testing.

2. **Given** an A/B test showing that a local model configuration achieves 80% of the Sharpe ratio of a proprietary configuration at 5% of the cost, **When** evaluating cost-effectiveness, **Then** the system should calculate that the local config delivers 16x better return-per-dollar-spent and flag this as a recommended configuration switch.

3. **Given** different model providers with varying latency characteristics, **When** running A/B tests, **Then** the system must also track and report decision latency (time from signal to execution decision) to identify if cheaper models create unacceptable execution delays.

4. **Given** A/B test results across multiple market regimes (trending, ranging, high volatility), **When** analyzing model effectiveness, **Then** the system should identify if certain model configurations perform better in specific regimes and recommend context-aware model routing strategies.

---

### User Story 7 - Dynamic Portfolio Rebalancing (Priority: P3)
As a trader, I want the system to automatically adjust capital allocation 
across strategies based on their recent performance and current market regime...

---

### Edge Cases

- **What happens when multiple agents disagree on critical parameters?** (e.g., position sizing agent recommends 2% but risk overseer forces reduction to 0.5% due to portfolio limits) - System must log the conflict, apply the most conservative limit, and flag for review.

- **How does the system handle extreme market conditions where all ML models show high uncertainty?** - Agents should output low conviction scores, position sizing should reduce to minimum, and trade decision agent may recommend NO_TRADE if uncertainty exceeds thresholds.

- **What happens when an agent's decision violates hard risk limits?** (e.g., position sizing agent recommends 5% risk but max allowed is 3%) - Risk overseer agent must override with hard limits, log the violation attempt, and potentially pause the violating agent for review.

- **How does the system handle concurrent position changes?** (e.g., stop-loss agent wants to trail stop while position monitor agent wants to scale out) - Must implement decision precedence rules and transaction isolation to prevent race conditions.

- **What happens during RL training if an agent learns to exploit backtesting artifacts?** (e.g., overfitting to specific historical patterns, look-ahead bias) - Walk-forward validation must detect out-of-sample degradation, and training pipeline must enforce point-in-time data constraints.

- **How does the system handle partial fills or slippage that invalidate the original risk parameters?** - Execution agent must recalculate actual risk realized and adjust remaining order sizing or cancel if actual risk exceeds intended parameters.

- **What happens when market structure changes after stop placement?** (e.g., new strong support forms above current stop) - Position monitor agent should detect structure changes and recommend stop adjustments with clear rationale.

## Requirements *(mandatory)*

### Functional Requirements

#### Analysis Layer

- **FR-001**: System MUST provide technical analysis through an agent that consumes ML forecasts (TCN, TFT, FEDformer), regime detection, and support/resistance detection to produce structured technical reports with directional bias, confidence levels, key price levels, and model agreement metrics.

- **FR-002**: System MUST provide fundamental analysis through an agent that consumes economic calendar data, correlation matrices, and macro indicators to produce structured fundamental reports with macro context, upcoming event risks, and cross-asset correlation insights.

- **FR-003**: System MUST provide sentiment analysis through an agent that consumes sentiment scores, positioning data, and order flow information to produce structured sentiment reports with crowd positioning metrics and smart money flow indicators.

#### Decision Layer

- **FR-004**: System MUST determine trade direction (LONG, SHORT, NO_TRADE) through an agent that evaluates debate outcomes, conviction levels, and invalidation conditions—producing a structured trade intent with action, conviction score (0.0-1.0), time horizon (INTRADAY, SWING, POSITION), and invalidation triggers.

- **FR-005**: System MUST determine position size dynamically (NOT fixed percentage) through an agent that considers: mathematical edge (Kelly criterion output), current portfolio drawdown state, market volatility regime, trade conviction level, correlation with existing positions, and upcoming scheduled events—producing a structured position size with lot quantity, dynamic risk percentage, Kelly fraction applied, and documented adjustments.

- **FR-006**: System MUST determine stop-loss placement intelligently (NOT fixed ATR multiple) through an agent that considers: ATR-based distance with adaptive multiplier, market structure (support/resistance levels), liquidity concentration zones, volatility regime adjustments, and probability of stop vs. target being hit—producing a structured stop-loss with price level, ATR distance, placement rationale (STRUCTURE, ATR, or HYBRID), and estimated hit probability.

- **FR-007**: System MUST determine take-profit targets probabilistically (NOT fixed risk-reward ratio) through an agent that considers: ML forecast probability distributions, key resistance/support levels, risk-reward vs. probability trade-offs, and partial profit opportunities—producing a structured take-profit with primary target price, optional partial targets with percentages, dynamically calculated risk-reward ratio, and estimated reach probabilities.

#### Debate Layer

- **FR-008**: System MUST generate adversarial perspectives through bull and bear researcher agents that consume all analyst reports, build the strongest case for and against each trade, and produce structured arguments with thesis, supporting evidence, scenarios (upside/downside), and explicit rebuttals to the opposing view—ensuring decisions are stress-tested rather than confirmation-biased.

#### Execution & Monitoring Layer

- **FR-009**: System MUST execute approved trades through an execution agent that handles order placement, fill management, slippage tracking, partial execution scenarios, and order lifecycle management—producing execution confirmations with actual fill prices and realized slippage.

- **FR-010**: System MUST monitor open positions through a position monitor agent that trails stops when positions move favorably, adjusts targets based on new information, detects regime changes requiring position closure, and manages scaling out at partial targets—producing position adjustment recommendations with clear rationale.

- **FR-011**: System MUST enforce portfolio-level risk limits through a risk overseer agent that monitors correlation exposure across positions, enforces daily loss limits, implements circuit breakers when thresholds are breached, and can halt all trading if risk limits are violated—producing override decisions and alert notifications.

#### Training & Validation

- **FR-012**: System MUST support backtesting of all decision agents in a deterministic environment with point-in-time data (no look-ahead bias), full decision logging with context preservation, and outcome tracking with attribution to specific agent decisions.

- **FR-013**: System MUST support reinforcement learning training for each decision-making agent (trade decision, position sizing, stop-loss, take-profit) with agent-specific reward signals: trade decision (realized PnL × direction accuracy), position sizing (Sharpe contribution - drawdown penalty), stop-loss (minimize unnecessary stop-outs + protect capital), take-profit (maximize expected value captured).

- **FR-014**: System MUST perform walk-forward validation with rolling train/validation/test windows across multiple time periods to prevent overfitting to specific market regimes, track out-of-sample performance degradation, and alert when degradation exceeds acceptable thresholds.

#### Multi-Model Support

- **FR-015**: System MUST support swapping between multiple AI model providers for agent reasoning, including proprietary services (OpenAI GPT-4o/o1/o3, Anthropic Claude Sonnet/Opus, Google Gemini) and open-source local models (Qwen3-14B, DeepSeek-R1-Distill-14B, Qwen3-30B, GPT-OSS-20B) with consistent agent behavior regardless of underlying model.

- **FR-016**: System MUST support A/B testing of different model configurations by running variants in parallel (paper trading mode), tracking performance metrics (returns, Sharpe ratio, max drawdown), tracking cost metrics (LLM inference cost per trade), and calculating cost-effectiveness (return per dollar spent on LLM inference) with statistical significance testing.

#### Structured Communication

- **FR-017**: System MUST enforce typed schemas for all inter-agent communication (no free-form text) with defined structures for: TradeIntent (action, conviction, time_horizon, invalidation_conditions), PositionSize (lots, risk_percent, kelly_fraction_used, adjustments_applied), StopLoss (price, distance_atr, placement_type, estimated_hit_probability), TakeProfit (primary_target, partial_targets, risk_reward, estimated_reach_probability), and all analyst reports.

#### Portfolio Allocation & Integration

- **FR-018**: System MUST support portfolio-level capital allocation across multiple trading strategies through either static configuration (percentage-based allocations defined in config) or dynamic allocation (Portfolio Allocator Agent that adjusts allocations based on strategy performance, market regime, and risk metrics). Position sizing agents MUST operate within their allocated capital envelope, not total account balance. Each strategy allocation includes: instrument(s) traded, capital percentage, max drawdown limit, and rebalancing rules.

- **FR-019**: System MUST integrate with ML forecasting models and calculation utilities via MCP (Model Context Protocol) tools. Required MCP tools include: ML forecasts (get_tcn_forecast, get_tft_prediction, get_fedformer_regime), technical calculations (calculate_kelly, calculate_atr, get_support_resistance, detect_liquidity_clusters), and market data queries. Tool responses use structured schemas enabling deterministic agent reasoning and backtesting replay.

- **FR-020**: System MUST execute orders through the existing MT4/ZMQ integration bridge (from Feature 001) which handles: order placement (market/limit/stop orders), order modification and cancellation, fill confirmations with actual execution prices, slippage tracking, partial fill handling, and position status queries. Execution agent abstracts MT4-specific details behind a broker-agnostic interface for future multi-broker support.

- **FR-021**: System MUST support two-tier LLM allocation strategy to optimize inference costs: (1) Quick-think LLM tier for high-frequency, low-complexity operations (data gathering, summarization, routine analysis, report formatting), (2) Deep-think LLM tier for low-frequency, high-complexity operations (adversarial reasoning, critical trade decisions, complex debate resolution, edge case handling). Agent configuration specifies which tier each agent uses for each operation type, enabling cost-performance trade-offs.

### Key Entities

- **Agent**: An autonomous decision-making component with a specific role (e.g., technical analyst, position sizing agent, risk overseer). Each agent consumes inputs (data or other agent outputs), applies reasoning (potentially using an AI model), and produces structured outputs according to its domain responsibility. Agents can be RL-trained to improve their decision strategies.

- **Trade Intent**: A structured decision output from the trade decision agent containing: action (LONG/SHORT/NO_TRADE), conviction level (0.0-1.0), time horizon category (INTRADAY/SWING/POSITION), and conditions that would invalidate the trade thesis.

- **Position Size**: A structured decision output from the position sizing agent containing: lot quantity to trade, dynamic risk percentage determined for this specific trade, Kelly fraction utilized, and documented adjustments applied (e.g., drawdown reduction, regime adjustment, correlation adjustment, event risk reduction).

- **Stop Loss**: A structured decision output from the stop-loss agent containing: stop price level, distance measured in ATR multiples, placement type classification (STRUCTURE-based, ATR-based, or HYBRID), and estimated probability of the stop being hit before target.

- **Take Profit**: A structured decision output from the take-profit agent containing: primary target price, optional array of partial profit targets (each with price and percentage of position), dynamically calculated risk-reward ratio, and estimated probability of reaching each target level.

- **Analyst Report**: Structured outputs from analysis layer agents (TechnicalReport, FundamentalReport, SentimentReport) containing domain-specific insights, confidence metrics, key data points, and actionable signals that feed into debate and decision layers.

- **Debate Outcome**: Structured output from the debate layer containing: bull thesis with supporting evidence and upside scenarios, bear thesis with risk factors and rebuttals to bull case, key factors from each perspective, and dissenting views that survived adversarial analysis.

- **Backtesting Environment**: A replay system that provides point-in-time market data to agents, logs all decisions with full context, tracks outcomes, and attributes performance to specific agent decisions—used for both performance validation and RL training.

- **RL Training Run**: A training session for a specific agent with defined reward signals, training/validation/test windows, hyperparameters, and performance metrics—tracked to monitor agent learning progress and prevent overfitting.

- **Model Configuration**: A specification of which AI model provider and model variant is assigned to each agent role, used for A/B testing to compare cost-effectiveness of different model combinations.

- **Portfolio Allocation**: A capital distribution specification defining how total account balance is divided across trading strategies. Contains: strategy identifier, allocated capital percentage, instrument(s) traded, max drawdown threshold, rebalancing frequency, and allocation mode (static config-based or dynamic agent-based). Position sizing agents query their allocated capital, not total balance.

- **MCP Tool**: A callable function exposed via Model Context Protocol that agents use to access ML forecasts, calculations, or data queries. Each tool has: tool name (e.g., "get_tcn_forecast"), input schema (structured parameters), output schema (typed response), and deterministic behavior for backtesting replay. Tools abstract implementation details from agent reasoning layer.

- **Strategy Team**: A dedicated set of agents (technical analyst, fundamental analyst, sentiment analyst, bull researcher, bear researcher, trade decision, position sizing, stop-loss, take-profit) assigned to a specific trading strategy/instrument. Each team operates independently with its own allocated capital envelope and decision pipeline. Multiple strategy teams can run in parallel for different instruments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Position sizes demonstrate measurable variance across different market conditions—position risk percentages must vary by at least 50% between high-volatility/high-drawdown scenarios and low-volatility/favorable scenarios (e.g., ranging from 0.5% to 2.0% rather than fixed 2.0%), with variance traceable to specific contextual factors in decision logs.

- **SC-002**: Stop-loss placements demonstrate structural intelligence—at least 70% of stops must be positioned relative to market structure levels (support/resistance, liquidity zones) rather than purely ATR-based distances, with documented rationale for structure-based decisions.

- **SC-003**: Take-profit targets demonstrate probabilistic optimization—expected value calculations for profit targets must show at least 15% improvement compared to fixed 2:1 risk-reward baselines, measured across a statistically significant sample of trades (minimum 100 trades).

- **SC-004**: Debate process produces balanced perspectives—every trade recommendation must include both bull and bear arguments with at least 3 supporting evidence points each, and bear arguments must successfully identify risks that materialize in at least 20% of trades (proving non-trivial adversarial analysis).

- **SC-005**: RL-trained agents demonstrate measurable improvement—agents trained via reinforcement learning must show statistically significant performance gains (p < 0.05) compared to baseline strategies across walk-forward validation windows, with at least one key metric improved (e.g., Sharpe ratio increase of >0.3, drawdown reduction of >20%, or win rate increase of >5 percentage points).

- **SC-006**: Walk-forward validation prevents overfitting—out-of-sample performance degradation for RL-trained agents must remain below 25% of in-sample performance across at least 80% of validation windows, demonstrating generalization rather than memorization.

- **SC-007**: Model cost-effectiveness is measurable—A/B testing framework must demonstrate ability to calculate return-per-dollar-spent for each model configuration with at least 95% accuracy in cost attribution, enabling data-driven model selection decisions.

- **SC-008**: System demonstrates regime adaptability—agent decisions (particularly position sizing and stop-loss) must show measurably different behaviors across distinct market regimes (trending vs. ranging, low-vol vs. high-vol), with statistical tests confirming regime-dependent strategies.

- **SC-009**: Decision latency remains acceptable—end-to-end decision pipeline (from signal to execution decision) must complete within acceptable timeframes that do not materially impact trade execution quality: <5 seconds for INTRADAY trades, <30 seconds for SWING trades, <5 minutes for POSITION trades.

- **SC-010**: Risk limits are enforceable—risk overseer agent must successfully prevent 100% of attempted trades that would violate hard portfolio limits (max position size, correlation exposure, daily loss limits) with zero false negatives in enforcement.

## Assumptions

### Reasonable Defaults

- **Agent Communication Protocol**: Agents communicate via structured message passing with typed schemas. The specific implementation (message queues, direct calls, event bus) is not specified but must support asynchronous processing and message persistence for audit trails.

- **RL Training Infrastructure**: Reinforcement learning training occurs offline in a backtesting environment with historical data. Real-time online learning is explicitly out of scope for initial implementation due to safety concerns. Agents are trained, validated, and then deployed with static policies until the next training cycle.

- **Model Provider Integration**: All AI model providers expose a common interface for agent reasoning (e.g., chat completion with structured outputs). Provider-specific API differences are abstracted at an integration layer not detailed in this specification.

- **Data Availability**: The system has access to required input data: OHLCV market data, ML forecast outputs (from Feature 003), economic calendar, sentiment indicators, and correlation matrices. Data freshness and quality requirements are assumed to be handled by upstream data pipelines.

- **Paper Trading Mode**: A/B testing and initial validation occur in paper trading mode (simulated execution without real capital) before any live trading deployment. Live trading requires explicit operator approval after paper trading validation.

- **Statistical Significance Standards**: Performance comparisons (RL vs. baseline, A/B tests) use standard statistical significance thresholds (p < 0.05 for hypothesis tests, minimum 100 samples for proportion tests) unless domain-specific trading statistics require adjustments.

- **Event Risk Calendar**: Economic event data includes at minimum: event name, scheduled time, expected impact level (high/medium/low), and affected instruments. More detailed event data (forecasts, historical values) enhances functionality but is not strictly required.

- **Partial Profit Execution**: Broker API supports partial position closures at specified price levels. If not supported, take-profit agent will fall back to single target with documented limitation.

- **Agent Roles Are Fixed**: The specific set of agents (technical analyst, fundamental analyst, sentiment analyst, bull researcher, bear researcher, trade decision, position sizing, stop-loss, take-profit, execution, position monitor, risk overseer) is defined in this specification. Adding new agent types requires specification updates and is out of scope for initial implementation.

- **Performance Metrics Standard**: Trading performance is measured using industry-standard metrics: total return, Sharpe ratio, maximum drawdown, win rate, average win/loss ratio, profit factor. Custom metrics can be added but these form the baseline.

### Known Constraints

- **No Real-Time Online Learning**: RL agents are trained offline and deployed with fixed policies. Online learning (updating agent behavior from live trades) is explicitly deferred to future phases due to safety and regulatory concerns.

- **English Language Only**: All agent reasoning, reports, and rationales are in English. Multi-language support is out of scope.

- **Limited Multi-Instrument Scope Initially**: While the architecture supports multi-instrument trading, initial deployment supports 2-3 instruments (e.g., Gold and Crude Oil) with dedicated agent teams per instrument. Cross-instrument correlation analysis and dynamic instrument expansion comes in later phases. Portfolio allocation across instruments is supported from day one (FR-018).

- **Synchronous Decision Pipeline**: For a given signal, the decision pipeline runs sequentially (analysis → debate → decision → execution). Parallel evaluation of multiple signals is supported, but each signal's pipeline is synchronous to maintain decision causality and audit trail clarity.
