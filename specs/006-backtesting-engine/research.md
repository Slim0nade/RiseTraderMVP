# Research: Backtesting Engine

**Feature**: 006-backtesting-engine
**Date**: 2025-12-11
**Status**: Phase 0 Complete

## Overview

This document consolidates research findings for implementing the RiseTrader backtesting engine. Research focuses on: (1) efficient historical data replay strategies, (2) accurate trading performance metrics calculation, (3) Gymnasium environment interface design, (4) synthetic vs full mode architecture, and (5) deterministic replay mechanisms.

## Research Areas

### 1. Historical Data Replay Architecture

**Decision**: Streaming iterator pattern with chunked database queries

**Rationale**:
- **Memory efficiency**: 13.5M candles cannot fit in memory simultaneously. Streaming prevents OOM errors.
- **Performance**: Chunked queries (10k-100k candles) balance database round trips vs memory usage
- **Deterministic ordering**: `ORDER BY timestamp ASC` with indexed timestamp column ensures consistent replay
- **Compatibility**: Works seamlessly with async SQLAlchemy cursor iteration

**Implementation approach**:
```python
async def replay_historical_data(start_date, end_date, symbol, chunk_size=50000):
    """
    Async generator that streams historical candles in chronological order.
    Yields candles one at a time while fetching in chunks for efficiency.
    """
    offset = 0
    while True:
        chunk = await market_data_repo.get_candles_range(
            symbol, start_date, end_date,
            offset=offset, limit=chunk_size,
            order_by="timestamp ASC"
        )
        if not chunk:
            break
        for candle in chunk:
            yield candle
        offset += chunk_size
```

**Alternatives considered**:
- **Load all data upfront**: Rejected - would require 1GB+ memory for multi-year backtests
- **Page-by-page database queries**: Rejected - too many round trips (slow for millions of candles)
- **Pre-materialized views**: Rejected - inflexible for different date ranges/symbols

**Best practices**:
- Use database indexes on `(symbol, timestamp)` for fast range queries
- Implement progress tracking: log every N candles processed (e.g., every 10k)
- Add validation: detect missing candles (gaps) before backtest starts
- Support resumable backtests: checkpoint state every N candles for long-running tests

---

### 2. Trading Performance Metrics Calculation

**Decision**: pandas-based vectorized calculations with numba optimization for hot paths

**Rationale**:
- **Accuracy**: Financial metrics have standard formulas - use battle-tested implementations
- **Performance**: pandas vectorized operations are 10-100x faster than Python loops
- **Validation**: Easy to verify against known results (e.g., quantstats library benchmarks)
- **Maintainability**: Clear, readable code that matches academic/industry formulas

**Key metrics implementation**:

**Sharpe Ratio** (annualized risk-adjusted return):
```python
def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """
    Sharpe = (mean_return - risk_free_rate) / std_return * sqrt(periods_per_year)
    For daily returns: periods_per_year = 252 (trading days)
    """
    excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
    if excess_returns.std() == 0:
        return 0.0
    return (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
```

**Maximum Drawdown** (peak-to-trough decline):
```python
def calculate_max_drawdown(equity_curve: pd.Series) -> tuple[float, int]:
    """
    Returns: (max_drawdown_pct, drawdown_duration_days)
    """
    cumulative_max = equity_curve.cummax()
    drawdown = (equity_curve - cumulative_max) / cumulative_max
    max_dd = drawdown.min()  # Most negative value

    # Find drawdown duration
    dd_start = drawdown[drawdown == max_dd].index[0]
    recovery = equity_curve[dd_start:][equity_curve >= cumulative_max[dd_start]]
    duration = 0 if len(recovery) == 0 else (recovery.index[0] - dd_start).days

    return abs(max_dd), duration
```

**Win Rate**:
```python
def calculate_win_rate(trades: list[SimulatedTrade]) -> float:
    """
    Win rate = (number of profitable trades) / (total closed trades)
    """
    closed_trades = [t for t in trades if t.exit_timestamp is not None]
    if not closed_trades:
        return 0.0
    profitable = sum(1 for t in closed_trades if t.net_pnl > 0)
    return profitable / len(closed_trades)
```

**Profit Factor**:
```python
def calculate_profit_factor(trades: list[SimulatedTrade]) -> float:
    """
    Profit factor = gross_profit / gross_loss
    """
    gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    return 0.0 if gross_loss == 0 else gross_profit / gross_loss
```

**Alternatives considered**:
- **Custom implementations**: Rejected - high risk of calculation errors
- **quantstats library**: Considered - excellent but heavy dependency (matplotlib, seaborn). May use for validation only.
- **QuantLib**: Rejected - C++ binding overhead not justified for simple metrics

**Best practices**:
- Verify calculations against sample datasets with known results
- Use property-based testing (hypothesis) to catch edge cases (empty trades, all losses, etc.)
- Log intermediate values for debugging (mean return, std, number of trades)
- Handle division by zero gracefully (return 0.0 or None with clear semantics)

---

### 3. Gymnasium Environment Interface Design

**Decision**: Stateful environment wrapper implementing standard Gymnasium API

**Rationale**:
- **Standard interface**: Gymnasium (formerly OpenAI Gym) is the de facto RL standard
- **Wide compatibility**: Works with Stable-Baselines3, RLlib, custom RL algorithms
- **Clear semantics**: `reset()`, `step(action)`, `render()` methods have well-defined contracts
- **Episode management**: Gymnasium handles episode boundaries, seeding, rendering

**Interface specification**:
```python
class BacktestTradingEnv(gymnasium.Env):
    """
    Gymnasium environment for RL training on historical trading data.

    Observation space: Box (continuous)
        - Recent N candles (OHLCV): shape (N, 5)
        - Technical indicators: shape (M,) configurable
        - Portfolio state: [cash, position_qty, unrealized_pnl]

    Action space: Discrete (3) or Box (continuous)
        - Discrete: {0: hold, 1: buy, 2: sell} with fixed quantity
        - Box: continuous [-1, 1] where value = position size fraction

    Reward: P&L change since last step (normalized by account value)
    """

    def reset(self, seed=None, options=None) -> tuple[np.ndarray, dict]:
        """
        Reset to random starting point in historical data.
        Returns: (initial_observation, info_dict)
        """

    def step(self, action) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        Execute action, advance one candle, return (obs, reward, terminated, truncated, info)
        """

    @property
    def observation_space(self) -> gymnasium.spaces.Box:
        """Define observation dimensions and bounds"""

    @property
    def action_space(self) -> gymnasium.spaces.Discrete | gymnasium.spaces.Box:
        """Define action dimensions and bounds"""
```

**Episode termination conditions**:
- **Terminated** (natural end): Reached end of historical data OR account balance <= 0 (bankruptcy)
- **Truncated** (timeout): Exceeded max_steps limit (e.g., 1000 candles)

**Reward shaping options**:
1. **Simple P&L**: `reward = (current_value - previous_value) / initial_capital`
2. **Risk-adjusted**: `reward = pnl / volatility` (penalize volatile strategies)
3. **Sparse**: `reward = 0` during episode, final reward = total P&L (encourages long-term thinking)

**Alternatives considered**:
- **Custom RL interface**: Rejected - reinventing the wheel, limited compatibility
- **TensorTrade library**: Considered - specialized for trading but less flexible than raw Gymnasium
- **FinRL library**: Considered - good example code but heavyweight (includes everything)

**Best practices**:
- Normalize observations to [0, 1] or [-1, 1] range (improves RL convergence)
- Use seed parameter for reproducible training runs
- Include `info` dict with diagnostic data (trade count, Sharpe ratio, drawdown)
- Support both discrete and continuous action spaces (different RL algorithms prefer different)

---

### 4. Synthetic Fast Mode Architecture

**Decision**: Rule-based decision tree bypassing agent LLM calls

**Rationale**:
- **Speed**: Eliminating LLM API calls provides 100-1000x speedup (from seconds to milliseconds per decision)
- **Determinism**: Pure rule-based logic ensures reproducible results
- **Hyperparameter search**: Enables grid search over 100+ configurations in hours instead of weeks
- **Correlation**: Simple rules (RSI, moving average crossovers) correlate well with LLM decisions for parameter tuning

**Synthetic decision logic** (example for signal generation):
```python
class SyntheticSignalGenerator:
    """
    Fast rule-based signal generation approximating agent decisions.
    Uses technical indicators instead of LLM reasoning.
    """

    def generate_signal(self, candles: list, config: dict) -> Signal:
        # Calculate indicators
        rsi = calculate_rsi(candles, period=14)
        ma_short = calculate_sma(candles, period=config['ma_short'])
        ma_long = calculate_sma(candles, period=config['ma_long'])

        # Rule-based decision
        if rsi < config['rsi_oversold'] and ma_short > ma_long:
            return Signal(action='BUY', confidence=0.8)
        elif rsi > config['rsi_overbought'] and ma_short < ma_long:
            return Signal(action='SELL', confidence=0.8)
        else:
            return Signal(action='HOLD', confidence=0.5)
```

**Configuration parameters** (exposed for optimization):
```yaml
synthetic_config:
  ma_short: 10        # Short moving average period
  ma_long: 50         # Long moving average period
  rsi_oversold: 30    # RSI buy threshold
  rsi_overbought: 70  # RSI sell threshold
  risk_limit: 0.02    # Max position size (2% of capital)
```

**Correlation validation**:
- Run identical backtest in both modes (full and synthetic)
- Compare final metrics: correlation should be 0.7+ for total return and Sharpe ratio
- If correlation is low, adjust synthetic rules to better approximate agent behavior

**Alternatives considered**:
- **LLM caching**: Cache LLM responses for identical inputs - still 10-100x slower than rules
- **Smaller LLM model**: Faster but less accurate, defeats purpose of validation
- **No synthetic mode**: Rejected - hyperparameter search becomes impractically slow

**Best practices**:
- Document synthetic rule assumptions clearly (not meant to replace agents, just approximate)
- Validate synthetic mode against full mode periodically (correlation check)
- Use synthetic mode for parameter screening, then validate finalists in full mode
- Expose all decision thresholds as configurable parameters

---

### 5. Deterministic Replay Mechanisms

**Decision**: Fixed random seed + chronological ordering + idempotent operations

**Rationale**:
- **Reproducibility**: Critical for debugging (same config + data = same result every time)
- **Validation**: Required for verifying optimizations don't change behavior
- **Regulatory compliance**: Auditors need reproducible results for trading system validation
- **Testing**: Unit tests can assert exact output for given input

**Implementation strategies**:

**1. Database query determinism**:
```python
# ALWAYS include ORDER BY for consistent ordering
query = (
    select(MarketData)
    .where(MarketData.symbol == symbol)
    .where(MarketData.timestamp >= start_date)
    .where(MarketData.timestamp <= end_date)
    .order_by(MarketData.timestamp.asc())  # CRITICAL for determinism
)
```

**2. Random seed control** (for RL environment):
```python
class BacktestTradingEnv(gymnasium.Env):
    def reset(self, seed=None, options=None):
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)
            self._rng = np.random.default_rng(seed)

        # Use self._rng for all random operations
        start_idx = self._rng.integers(0, len(self.data) - self.episode_length)
        ...
```

**3. Floating point determinism**:
- Avoid operations with undefined order (dict iteration in Python <3.7)
- Use fixed precision for money calculations: `Decimal` type or integer cents
- Document any non-deterministic operations (e.g., parallel execution order)

**4. Agent integration determinism** (full mode):
```python
# Force synchronous event processing (no race conditions)
async def process_market_tick(candle):
    # Events must be processed in strict order
    await mcp_server.emit_event('new_tick', candle)

    # Wait for agent decisions before proceeding
    signal = await mcp_server.wait_for_event('signal_generated', timeout=10.0)
    validated = await mcp_server.wait_for_event('trade_validated', timeout=5.0)

    # Only advance time after all agents have responded
    return validated
```

**Validation approach**:
```python
def test_deterministic_replay():
    """
    Property: Running same backtest twice produces identical results.
    """
    config = BacktestConfig(
        start_date='2023-01-01',
        end_date='2023-06-30',
        initial_capital=10000,
        seed=42
    )

    run1 = await backtest_service.run_backtest(config)
    run2 = await backtest_service.run_backtest(config)

    # Assert byte-for-byte identical results
    assert run1.total_return == run2.total_return
    assert run1.sharpe_ratio == run2.sharpe_ratio
    assert len(run1.trades) == len(run2.trades)
    for t1, t2 in zip(run1.trades, run2.trades):
        assert t1.entry_price == t2.entry_price
        assert t1.quantity == t2.quantity
```

**Alternatives considered**:
- **Approximate reproducibility**: Within 0.1% variance - rejected, too lenient for financial calculations
- **Snapshot-based testing**: Store results, compare new runs - rejected, hides non-determinism bugs
- **Ignore reproducibility**: Rejected - makes debugging impossible

**Best practices**:
- Always set random seed in tests and production runs (log seed value)
- Use datetime with timezone (UTC) - never naive datetime
- Test determinism explicitly: run twice, assert identical
- Document any sources of intentional non-determinism (e.g., wall-clock timestamps in logs)

---

## Technology Decisions

### Dependencies to Add

```toml
[tool.poetry.dependencies]
gymnasium = "^0.29.1"        # RL environment interface
scipy = "^1.11.4"            # Statistical tests (t-test for A/B comparison)
hypothesis = "^6.92.0"       # Property-based testing for metrics
numba = "^0.58.1"           # Optional: JIT for performance-critical metrics
```

### Database Indexes

```sql
-- Ensure efficient historical data queries
CREATE INDEX idx_market_data_symbol_timestamp
ON market_data (symbol, timestamp ASC);

-- For backtest run queries
CREATE INDEX idx_backtest_runs_created_at
ON backtest_runs (created_at DESC);
```

### Configuration Schema

```yaml
# config/backtesting.yaml
backtesting:
  default_slippage_pct: 0.001      # 0.1% slippage per trade
  default_commission_pct: 0.0005   # 0.05% commission per trade
  chunk_size: 50000                # Candles per database query
  max_memory_mb: 1000              # Memory limit per backtest
  timeout_minutes: 60              # Max backtest duration

  synthetic_mode:
    ma_short: 10
    ma_long: 50
    rsi_period: 14
    rsi_oversold: 30
    rsi_overbought: 70
```

---

## Risk Assessment

### Performance Risks

| Risk | Mitigation |
|------|-----------|
| 6-month backtest exceeds 30min target | Profile bottlenecks (likely agent LLM calls). Implement caching for identical market states. |
| Memory usage grows unbounded | Implement streaming with generator pattern. Add memory monitoring and circuit breaker. |
| Synthetic mode <100x speedup | Benchmark current implementation. Use numba JIT for hot paths. Consider Rust extension. |

### Correctness Risks

| Risk | Mitigation |
|------|-----------|
| Metrics calculation errors | Validate against quantstats library. Use property-based tests. |
| Look-ahead bias in indicators | Ensure indicators only use past data. Add explicit validation. |
| Non-deterministic replay | Force chronological ordering, seed control, synchronous event processing. Test explicitly. |
| Edge cases in P&L tracking | Test: partial fills, dividends, splits, negative balance, max leverage. |

### Integration Risks

| Risk | Mitigation |
|------|-----------|
| Agent events out of order | Use synchronous MCP event processing in full mode. Log all event sequences. |
| Database query performance | Index (symbol, timestamp). Monitor slow query log. |
| Gymnasium interface breaks RL libraries | Write contract tests against Stable-Baselines3, RLlib. Follow Gymnasium spec strictly. |

---

## Open Questions (Resolved)

1. **Q: How to handle dividends/splits in historical data?**
   - A: Initial version assumes no corporate actions (crypto/forex focus). Future: adjust prices retroactively or track split events.

2. **Q: Should synthetic mode use same indicators as agents?**
   - A: No - synthetic mode uses simple technical indicators for speed. Purpose is parameter screening, not agent replication.

3. **Q: RL environment action space: discrete or continuous?**
   - A: Support both via config flag. Discrete for DQN/A2C, continuous for PPO/SAC.

4. **Q: How to handle gaps in historical data?**
   - A: Pre-validate before backtest starts. Warn user of gaps. Option to skip gaps or fail backtest.

---

## Implementation Priorities

**Phase 1 (MVP - P1 user story)**:
1. Historical data replay engine
2. Portfolio state tracking + P&L calculation
3. Trade simulator (slippage, commissions, fills)
4. Metrics calculator (Sharpe, drawdown, win rate, profit factor)
5. Basic backtest service orchestration
6. Full agent pipeline integration (MCP events)

**Phase 2 (Optimization - P2 user story)**:
7. Synthetic fast mode implementation
8. Batch optimizer for parameter grids
9. Parallel backtest execution
10. Results ranking and comparison

**Phase 3 (RL Integration - P3 user story)**:
11. Gymnasium environment wrapper
12. Episode management
13. Observation/action space configuration
14. RL training integration tests

**Phase 4 (Polish - P3 user story)**:
15. A/B testing framework
16. Statistical significance tests
17. Trade overlap analysis
18. Performance optimizations (numba, caching)

---

## References

- Gymnasium Documentation: https://gymnasium.farama.org/
- Quantstats Library (metrics reference): https://github.com/ranaroussi/quantstats
- Backtrader Documentation (architecture inspiration): https://www.backtrader.com/
- "Evidence-Based Technical Analysis" (Aronson) - metrics methodology
- "Advances in Financial Machine Learning" (López de Prado) - backtesting pitfalls

---

**Status**: Research complete. All technical unknowns resolved. Ready for Phase 1 design (data models and contracts).
