# Phase 6.5: Backtesting Infrastructure - Summary

**Status**: NEW PHASE ADDED
**Priority**: P1 - CRITICAL BLOCKER
**Created**: 2025-12-10
**Blocks**: Phase 7 (RL Training), Phase 8 (A/B Testing)

## Overview

Phase 6.5 (Backtesting Infrastructure) is a **critical blocking phase** that must be completed before Phase 7 (RL Training) and Phase 8 (A/B Testing) can proceed. This phase was added to the specification because:

1. **RL Training Dependency**: Phase 7 requires a Gymnasium environment for training agents, which must be built on top of a backtesting engine
2. **A/B Testing Dependency**: Phase 8 requires historical performance comparison, which depends on backtesting capabilities
3. **Real Data Validation**: Before deploying RL-trained agents to live trading, we need to validate their performance on historical data

## User Story 5.0: Backtesting Infrastructure

As a trader and system operator, I want to simulate agent trading decisions against historical market data to validate strategy performance, calculate realistic metrics, and provide a training environment for reinforcement learning—so that I can confidently deploy strategies that have been thoroughly tested on real market conditions before risking capital.

## Key Features

### 1. Core Backtesting Engine (6 tasks: T140-T145)

**BacktestEngine** - Simulates trading on historical data from PostgreSQL
- Loads 13.5M historical candles from `market_data` table (NO MOCK DATA)
- Bar-by-bar or tick-by-tick price replay
- Tracks simulated account state (balance, positions, orders)
- Supports multiple symbols and timeframes

**Order Simulation** - Realistic fill logic
- Market orders: fill at next bar open + slippage
- Limit orders: fill when price touches limit
- Stop orders: fill when price breaches stop
- Spread simulation for realistic costs
- Optional partial fills

**Position & P&L Tracking** - Accurate accounting
- Open/close position logic
- Realized and unrealized P&L
- Commission and swap costs
- Margin requirements
- Equity curve generation

**Trade Lifecycle Management** - Complete trade flow
- Entry signal → Order → Fill → Open position
- Stop-loss/Take-profit monitoring
- Position close → P&L recorded → Trade logged
- Support for partial exits

**Multi-Symbol Portfolio** - Portfolio-level backtesting
- Run backtests across Gold + CrudeOIL simultaneously
- Portfolio-level metrics aggregation
- Correlation-aware limits
- Aggregate equity curve

**BacktestConfig Schema** - Configuration management
- Pydantic model for backtest parameters
- Symbol, date range, capital, costs
- Agent configuration (which agents, LLM provider)
- Risk limits

### 2. Performance Metrics (4 tasks: T146-T149)

**Trade-Level Metrics**:
- Win rate, loss rate
- Average win/loss size
- Profit factor
- Trade duration
- Consecutive wins/losses

**Portfolio-Level Metrics**:
- Total return, annualized return
- Sharpe ratio (industry standard calculation)
- Sortino ratio
- Calmar ratio
- Maximum drawdown

**Risk Metrics**:
- Value at Risk (VaR)
- Expected Shortfall (CVaR)
- Volatility metrics
- Beta to benchmark

**BacktestResult Schema**:
- Complete results in Pydantic model
- Equity curve data
- Trade log export
- JSON serialization

### 3. Agent Integration (4 tasks: T150-T153)

**Agent Decision Interface**:
- Abstract interface for agent decisions
- Adapter for existing agents
- Batch decision mode for speed

**MarketState Representation**:
- Current OHLCV bar
- Recent price history
- Technical indicators
- Account state

**Full Pipeline Mode**:
- Run complete trading pipeline: Analysis → Debate → Decision → Risk Debate → Fund Manager → Execute
- Decision caching to avoid redundant LLM calls
- Configurable depth (full pipeline vs simplified)

**Synthetic Fast Mode**:
- Rule-based heuristics (NO LLM calls)
- 1000x faster than LLM mode
- For hyperparameter optimization
- Validates against LLM mode

### 4. Gymnasium Environment for RL (4 tasks: T154-T157)

**TradingGymEnv Base Class**:
- Inherits `gymnasium.Env`
- Observation space: market state + account state
- Action space: position sizing, stops, targets
- `step()` and `reset()` methods
- **CRITICAL FOR PHASE 7**

**Reward Functions**:
- Sharpe-based rewards
- P&L with drawdown penalty
- Transaction cost penalties
- Configurable reward shaping

**Episode Configuration**:
- Episode length (bars or days)
- Random start date sampling
- Train/validation/test splits
- Walk-forward generation

**Vectorized Environment**:
- Multiple parallel environments
- Compatible with Stable-Baselines3
- GPU acceleration support

### 5. Testing & Validation (4 tasks: T158-T161)

**Unit Tests**:
- Order fill logic
- P&L accuracy
- Edge cases

**Integration Tests with Real Data**:
- Backtest on Gold 2024 data from PostgreSQL
- Verify metrics accuracy
- Full agent pipeline testing

**Benchmark Tests**:
- Throughput targets:
  - Synthetic mode: >10,000 bars/second
  - LLM mode: >100 bars/second (with caching)

**Validation Tests**:
- Simple MA crossover strategy
- Known outcome verification

## Acceptance Criteria

✅ **Memory Efficiency**: BacktestEngine processes 13.5M candles without memory issues
✅ **Metrics Accuracy**: Sharpe ratio calculation matches industry standard (annualized)
✅ **RL Compatibility**: Gymnasium environment compatible with Stable-Baselines3 PPO/SAC
✅ **Performance - Full Pipeline**: 1 year of 4H data in <10 minutes
✅ **Performance - Synthetic**: 1 year of 4H data in <10 seconds

## Task Breakdown

**Total Tasks**: 22 tasks (T140-T161)

**By Group**:
- Core Engine: 6 tasks
- Performance Metrics: 4 tasks
- Agent Integration: 4 tasks
- Gymnasium Environment: 4 tasks
- Testing & Validation: 4 tasks

**Estimated Effort**: 2-3 weeks (Medium complexity)

## Dependency Chain

```
Phase 6 (Complete) ✅
    ↓
Phase 6.5 (Backtesting) ⏳ ← YOU ARE HERE
    ↓
    ├─→ Phase 7 (RL Training)
    └─→ Phase 8 (A/B Testing)
```

**Phase 7 (RL Training) Dependencies**:
- Requires `TradingGymEnv` (T154)
- Requires reward functions (T155)
- Requires episode configuration (T156)
- Requires vectorized environment (T157)

**Phase 8 (A/B Testing) Dependencies**:
- Requires `BacktestEngine` (T140)
- Requires performance metrics (T146-T149)
- Requires agent adapters (T150)

## Data Source

**Uses REAL PostgreSQL Data - NO MOCKS**

- Database: `risetrader` at `localhost:5433`
- Table: `market_data`
- Records: 13.5 million historical candles
- Symbols: CrudeOIL, Gold
- Timeframes: 4H, 1D
- Date Range: 2020-2024

## Technical Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  BacktestEngine                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  PostgreSQL market_data (13.5M candles)          │  │
│  └───────────────────┬──────────────────────────────┘  │
│                      ↓                                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Bar-by-Bar Price Replay                         │  │
│  └───────────────────┬──────────────────────────────┘  │
│                      ↓                                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Agent Decision Pipeline (optional)              │  │
│  │  Analysis → Debate → Decision → Risk → Approval  │  │
│  └───────────────────┬──────────────────────────────┘  │
│                      ↓                                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Order Simulation & Fill Logic                   │  │
│  └───────────────────┬──────────────────────────────┘  │
│                      ↓                                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Position & P&L Tracking                         │  │
│  └───────────────────┬──────────────────────────────┘  │
│                      ↓                                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Performance Metrics Calculation                 │  │
│  │  Sharpe, Drawdown, Win Rate, etc.               │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              TradingGymEnv (for RL)                     │
│  Wraps BacktestEngine as Gymnasium Environment          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  observation_space: Market + Account State       │  │
│  │  action_space: Position Size, Stops, Targets     │  │
│  │  step(): Execute action, calculate reward        │  │
│  │  reset(): New random episode                     │  │
│  └──────────────────────────────────────────────────┘  │
│                      ↓                                   │
│            Used by Phase 7 (RL Training)                │
└─────────────────────────────────────────────────────────┘
```

## Implementation Notes

### Speed Optimization

**Two Modes**:
1. **LLM Mode**: Full agent pipeline with real LLM calls
   - Target: 100+ bars/second
   - Decision caching to avoid redundant calls
   - Use for final validation

2. **Synthetic Mode**: Rule-based heuristics, NO LLMs
   - Target: 10,000+ bars/second
   - Use for hyperparameter search
   - Use for RL training (fast iterations)

### Realistic Fill Simulation

**Fills are NOT perfect**:
- Market orders: slippage based on spread + volatility
- Limit orders: only fill if price actually touches limit
- Stop orders: slippage on volatile moves
- Partial fills possible for large positions

### Metric Calculations

**Industry-Standard Formulas**:
- Sharpe Ratio: annualized, using daily returns
- Maximum Drawdown: peak-to-trough in equity curve
- Win Rate: % of profitable trades (not % of profitable bars)
- Profit Factor: Gross profit / Gross loss

## Next Steps

1. **Review**: Review this phase specification with team
2. **Plan**: Create detailed implementation plan
3. **Implement**: Execute tasks T140-T161 in order
4. **Test**: Run validation tests on CrudeOIL 2023-2024 data
5. **Document**: Document API and usage examples
6. **Proceed**: Unblock Phase 7 (RL Training) and Phase 8 (A/B Testing)

## Related Documents

- **Spec**: `spec.md` - User Story 5.0 added
- **Tasks**: `tasks.md` - Phase 6.5 tasks T140-T161 added
- **Plan**: `plan.md` - No changes needed (plan is generated from tasks)

---

**Updated**: 2025-12-10
**Phase Status**: Specification Complete, Implementation Pending
**Next Action**: Begin implementation with T140 (BacktestEngine core)
