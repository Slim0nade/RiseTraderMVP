# User Story 4: Agent Configuration Comparison - COMPLETE

**Status**: ✅ **100% Complete** (14/14 tasks)
**Completion Date**: 2025-12-13
**Implementation Time**: Phase 6

---

## Executive Summary

User Story 4 delivers a production-ready **statistical A/B testing framework** for comparing different agent configurations with rigorous statistical significance testing. The implementation enables data-driven decision-making when choosing between trading strategies, risk parameters, or ML models.

### Key Achievements

- ✅ Statistical significance testing using Welch's t-test (p < 0.05 threshold)
- ✅ Trade overlap analysis (consensus vs divergent trades)
- ✅ Equity curve alignment for visual comparison
- ✅ Performance breakdown by time period (day/week/month)
- ✅ Comprehensive comparison reports with recommendations
- ✅ REST API endpoint for A/B testing (`POST /api/v1/backtesting/comparison`)
- ✅ Composite scoring algorithm for ranking configurations
- ✅ Confidence interval calculation for mean differences

---

## Task Completion Breakdown

### Phase 6 - User Story 4: A/B Testing (14/14 tasks - 100%)

#### Tests (3 tasks)
- ✅ **T100**: Unit test for statistical significance calculation (t-test) (`test_comparison.py`, ~200 lines)
- ✅ **T101**: Unit test for trade overlap analysis (consensus/divergent trades)
- ✅ **T102**: Integration test for end-to-end A/B comparison

#### Core Implementation (6 tasks)
- ✅ **T103**: `ComparisonService` class (statistical comparison engine, 670 lines)
- ✅ **T104**: `compare_runs` method for side-by-side metrics
- ✅ **T105**: Statistical significance testing with scipy.stats.ttest_ind (Welch's t-test)
- ✅ **T106**: Trade overlap analysis (time-window matching)
- ✅ **T107**: Equity curve alignment with pandas interpolation
- ✅ **T108**: Performance breakdown by time period

#### API Endpoint (1 task)
- ✅ **T109**: `POST /api/v1/backtesting/comparison` endpoint (165 lines)

#### Validation (4 tasks - covered in tests)
- ✅ **T110**: Test comparison with 2 configurations (conservative vs aggressive)
- ✅ **T111**: Verify statistical tests produce correct p-values
- ✅ **T112**: Test trade overlap with known overlapping trades
- ✅ **T113**: Verify comparison handles different numbers of trades

---

## Implementation Statistics

### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `tests/unit/backtesting/test_comparison.py` | ~450 | Unit tests for statistical tests and trade overlap (T100-T101) |
| `tests/integration/backtesting/test_comparison.py` | ~350 | End-to-end A/B comparison tests (T102) |
| `src/services/backtesting/comparison.py` | 670 | **Core comparison service** (T103-T108) |

### Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `src/api/models/backtesting_models.py` | +80 lines | Comparison request/response models (T109) |
| `src/api/routes/backtesting.py` | +165 lines | Comparison API endpoint (T109) |
| `src/services/backtesting/__init__.py` | +7 lines | Export comparison classes |
| `specs/006-backtesting-engine/tasks.md` | Marked T100-T113 | Task completion tracking |

### Total Code Volume
- **New code**: ~1,715 lines
- **Test coverage**: ~800 lines of tests (47% of total)
- **Core implementation**: 670 lines (ComparisonService)
- **API layer**: 245 lines (models + endpoint)

---

## Key Features Delivered

### 1. ComparisonService

```python
from src.services.backtesting import ComparisonService

# Initialize service
comparison_service = ComparisonService()

# Compare two runs
comparison = await comparison_service.compare_runs(
    run_a_id=uuid_a,
    run_b_id=uuid_b,
    async_session=db_session,
    time_window_minutes=5,  # For trade overlap matching
)

# Access results
print(comparison.recommendation)  # "run_a" | "run_b" | "no_significant_difference"
print(comparison.statistical_tests["returns_ttest"].p_value)  # 0.0234
print(comparison.trade_overlap.overlap_rate)  # 0.67 (67% consensus)
```

### 2. Statistical Significance Testing

**Method**: Welch's t-test (unequal variances)

```python
# Calculate statistical significance
test_result = comparison_service.calculate_statistical_significance(
    returns_a=[0.01, 0.02, -0.01, 0.03, ...],
    returns_b=[0.02, 0.03, 0.01, 0.04, ...],
    confidence_level=0.95,
)

# Result structure
StatisticalTest(
    t_statistic=2.45,
    p_value=0.0156,  # < 0.05 → statistically significant
    is_significant=True,
    degrees_of_freedom=198.34,
    mean_difference=0.0085,  # Run A outperforms by 0.85% avg
    confidence_interval=(0.0032, 0.0138),  # 95% CI
)
```

**Key Features**:
- Welch's t-test (doesn't assume equal variances)
- Welch-Satterthwaite degrees of freedom calculation
- 95% confidence intervals for mean difference
- Handles edge cases (zero variance, different sample sizes)

### 3. Trade Overlap Analysis

Identifies **consensus trades** (both runs) vs **divergent trades** (only one run).

```python
# Analyze trade overlap
overlap = comparison_service.analyze_trade_overlap(
    trades_a=[...],  # Run A trades
    trades_b=[...],  # Run B trades
    time_window_minutes=5,  # Match trades within 5 min
)

# Result
TradeOverlap(
    consensus_trades=23,       # Both runs entered same position
    divergent_trades_a=7,      # Only run A took these trades
    divergent_trades_b=5,      # Only run B took these trades
    overlap_rate=0.66,         # 23 / (23 + 7 + 5) = 65.7%
    consensus_trade_details=[  # Details of consensus trades
        {
            "entry_time_a": datetime(...),
            "entry_time_b": datetime(...),
            "direction": "BUY",
            "profit_a": 120.50,
            "profit_b": 135.75,  # Run B executed better
            "profit_diff": 15.25,
        },
        ...
    ],
)
```

**Matching Logic**:
- Same direction (BUY/SELL) required
- Within time window (default 5 minutes)
- Profit comparison for consensus trades

### 4. Equity Curve Alignment

Aligns equity curves to common timeline for visual comparison.

```python
# Align equity curves
aligned = comparison_service.align_equity_curves(
    equity_a=[
        {"timestamp": datetime(2024, 1, 1, 10, 0), "equity": 10000},
        {"timestamp": datetime(2024, 1, 1, 10, 30), "equity": 10100},
        ...
    ],
    equity_b=[...],
    normalize=True,  # Normalize to start at 1.0 for % comparison
)

# Result (normalized)
{
    "timestamps": [datetime(...), datetime(...), ...],
    "equity_a": [1.0, 1.01, 1.015, ...],  # All start at 1.0
    "equity_b": [1.0, 1.008, 1.012, ...],
}
```

**Features**:
- Pandas-based timestamp merging (outer join)
- Forward-fill interpolation for missing values
- Optional normalization to 1.0 start (for % comparison)
- Handles different sampling rates

### 5. Performance Breakdown by Time Period

```python
# Break down by month
breakdown = comparison_service.breakdown_by_period(
    trades=[...],
    period="month",  # "day" | "week" | "month"
)

# Result
{
    "2024-01": {
        "total_profit": 1250.50,
        "num_trades": 45,
        "win_rate": 0.62,
        "avg_profit": 27.79,
    },
    "2024-02": {
        "total_profit": -230.75,
        "num_trades": 38,
        "win_rate": 0.45,
        "avg_profit": -6.07,
    },
    ...
}
```

### 6. Composite Scoring Algorithm

Used when statistical significance is not detected:

```python
composite_score = (
    0.30 * sharpe_ratio_normalized +
    0.25 * total_return_normalized +
    0.20 * profit_factor_normalized +
    0.15 * win_rate +
    -0.10 * max_drawdown_penalty
)
```

**Weighting**:
- Sharpe ratio: 30% (risk-adjusted returns)
- Total return: 25% (absolute performance)
- Profit factor: 20% (win/loss ratio)
- Win rate: 15% (consistency)
- Drawdown penalty: -10% (risk control)

### 7. REST API Endpoint

```python
# POST /api/v1/backtesting/comparison
{
    "run_a_id": "uuid-for-run-a",
    "run_b_id": "uuid-for-run-b",
    "time_window_minutes": 5,
    "generate_report": true
}

# Response
{
    "run_a_id": "...",
    "run_b_id": "...",
    "recommendation": "run_a",  # Winner
    "metrics_comparison": {
        "run_a": {
            "total_return": 0.125,
            "sharpe_ratio": 1.85,
            "win_rate": 0.62,
            ...
        },
        "run_b": {...},
        "differences": {
            "total_return_diff": 0.045,
            "sharpe_diff": 0.32,
            ...
        }
    },
    "statistical_tests": {
        "returns_ttest": {
            "t_statistic": 2.45,
            "p_value": 0.0156,
            "is_significant": true,
            "mean_difference": 0.0085,
            ...
        }
    },
    "trade_overlap": {
        "consensus_trades": 23,
        "divergent_trades_a": 7,
        "divergent_trades_b": 5,
        "overlap_rate": 0.66
    },
    "equity_curves": {...},
    "performance_breakdown": {...},
    "report": {
        "summary": {...},
        "recommendation": "run_a",
        "detailed_metrics": {...},
        "statistical_analysis": {...},
        "trade_analysis": {...}
    }
}
```

---

## Usage Examples

### Example 1: A/B Test Conservative vs Aggressive

```python
from src.services.backtesting import BacktestService, ComparisonService

# Run backtest A: Conservative (1% position size)
config_a = {
    "symbol": "EURUSD",
    "timeframe": "M5",
    "strategy_params": {
        "ema_fast": 8,
        "ema_slow": 21,
        "position_size": 0.01,  # Conservative
    },
}

# Run backtest B: Aggressive (5% position size)
config_b = {
    **config_a,
    "strategy_params": {
        **config_a["strategy_params"],
        "position_size": 0.05,  # Aggressive
    },
}

# Execute backtests
service = BacktestService(db_session)
result_a = await service.run_backtest(config_a)
result_b = await service.run_backtest(config_b)

# Compare results
comparison_service = ComparisonService()
comparison = await comparison_service.compare_runs(
    run_a_id=result_a.run_id,
    run_b_id=result_b.run_id,
    async_session=db_session,
)

# Analyze results
print(f"Recommendation: {comparison.recommendation}")
print(f"P-value: {comparison.statistical_tests['returns_ttest'].p_value:.4f}")

if comparison.recommendation == "run_a":
    print("✅ Conservative configuration is statistically better")
elif comparison.recommendation == "run_b":
    print("✅ Aggressive configuration is statistically better")
else:
    print("⚠️ No statistically significant difference - use risk preferences")
```

### Example 2: REST API Usage

```bash
# Run comparison via API
curl -X POST "http://localhost:8003/api/v1/backtesting/comparison" \
  -H "Content-Type: application/json" \
  -d '{
    "run_a_id": "123e4567-e89b-12d3-a456-426614174000",
    "run_b_id": "987fcdeb-51a2-43f7-b89c-123456789abc",
    "time_window_minutes": 5,
    "generate_report": true
  }'
```

### Example 3: Trade Overlap Analysis

```python
# Find out which trades both runs agreed on
comparison = await comparison_service.compare_runs(...)

print(f"Consensus trades: {comparison.trade_overlap.consensus_trades}")
print(f"Overlap rate: {comparison.trade_overlap.overlap_rate:.2%}")

# Analyze consensus trade profitability
for trade in comparison.trade_overlap.consensus_trade_details:
    if trade["profit_diff"] > 0:
        print(f"Run B executed {trade['direction']} better by ${trade['profit_diff']}")
    else:
        print(f"Run A executed {trade['direction']} better by ${-trade['profit_diff']}")
```

### Example 4: Monthly Performance Comparison

```python
# Compare month-by-month performance
comparison = await comparison_service.compare_runs(...)

breakdown_a = comparison.performance_breakdown["run_a_by_month"]
breakdown_b = comparison.performance_breakdown["run_b_by_month"]

print("Monthly Performance Comparison:")
print(f"{'Month':<10} {'Run A Profit':<15} {'Run B Profit':<15} {'Winner':<10}")
print("-" * 50)

for month in sorted(breakdown_a.keys()):
    profit_a = breakdown_a[month]["total_profit"]
    profit_b = breakdown_b[month]["total_profit"]
    winner = "Run A" if profit_a > profit_b else "Run B"
    print(f"{month:<10} ${profit_a:<14.2f} ${profit_b:<14.2f} {winner:<10}")
```

---

## Test Results Summary

### Unit Tests (T100-T101)

**Statistical Significance Tests**:
```python
✅ test_ttest_detects_significant_difference()
   - Correctly identifies p < 0.05 for different means

✅ test_ttest_no_significant_difference()
   - Correctly identifies p >= 0.05 for similar means

✅ test_ttest_with_identical_returns()
   - Handles edge case: p = 1.0, t = 0.0

✅ test_ttest_with_different_sample_sizes()
   - Uses Welch's t-test (unequal variances)

✅ test_confidence_interval_calculation()
   - 95% CI correctly calculated
```

**Trade Overlap Tests**:
```python
✅ test_identify_consensus_trades()
   - Correctly matches trades within time window

✅ test_divergent_trades_identification()
   - Correctly identifies unique trades

✅ test_trade_overlap_with_opposite_directions()
   - BUY vs SELL at same time = NOT consensus

✅ test_consensus_trade_performance_comparison()
   - Compares profitability of consensus trades
```

### Integration Tests (T102)

```python
✅ test_compare_two_configurations_end_to_end()
   - Full A/B comparison workflow
   - Conservative vs Aggressive configurations
   - Verifies all comparison components

✅ test_compare_with_statistical_significance_detected()
   - Detects significant performance difference

✅ test_compare_with_no_statistical_significance()
   - Correctly identifies no significant difference

✅ test_equity_curve_alignment_integration()
   - Aligned curves have same timestamps

✅ test_performance_breakdown_by_month()
   - Monthly breakdown correctly aggregated
```

---

## Success Criteria Validation

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| **Statistical Testing** | t-test for returns | ✅ Welch's t-test | ✅ |
| **Trade Overlap** | Consensus/divergent | ✅ Time-window matching | ✅ |
| **Equity Alignment** | Common timeline | ✅ Pandas interpolation | ✅ |
| **Time Breakdown** | Day/week/month | ✅ All 3 periods | ✅ |
| **API Endpoint** | REST endpoint | ✅ POST /comparison | ✅ |
| **Recommendation** | Auto-select winner | ✅ Composite scoring | ✅ |
| **Confidence Intervals** | 95% CI | ✅ Implemented | ✅ |
| **Edge Case Handling** | Zero variance, etc. | ✅ All handled | ✅ |

---

## Integration Guide

### For Trading Strategists

**Prerequisites**:
- Two completed backtest runs (same symbol, overlapping date ranges)

**Quick Start**:
1. Run two backtests with different configurations
2. Call `ComparisonService.compare_runs()` or use REST API
3. Check `recommendation` field for winner
4. Verify `is_significant` to ensure statistical rigor

**Decision Framework**:
- If `is_significant = True` → Trust the winner
- If `is_significant = False` → No clear winner, use:
  - Composite score (auto-calculated)
  - Risk preferences (conservative vs aggressive)
  - Trade overlap rate (consensus = robust)

### For ML Engineers

**A/B Testing ML Models**:
```python
# Compare XGBoost vs LSTM forecasts
config_xgboost = {..., "ml_model": "xgboost"}
config_lstm = {..., "ml_model": "lstm"}

# Run backtests
result_xgb = await backtest_service.run_backtest(config_xgboost)
result_lstm = await backtest_service.run_backtest(config_lstm)

# Compare with statistical tests
comparison = await comparison_service.compare_runs(
    run_a_id=result_xgb.run_id,
    run_b_id=result_lstm.run_id,
    async_session=db,
)

# Log to MLflow
mlflow.log_metric("comparison_p_value", comparison.statistical_tests["returns_ttest"].p_value)
mlflow.log_param("winner_model", comparison.recommendation)
```

### For DevOps/Dashboard

**Visualization Data**:
```python
comparison = await comparison_service.compare_runs(...)

# Get aligned equity curves for charts
equity_data = comparison.equity_curves
timestamps = equity_data["timestamps"]
equity_a = equity_data["equity_a"]
equity_b = equity_data["equity_b"]

# Plot with TradingView Lightweight Charts
chart_data_a = [{"time": ts.timestamp(), "value": eq} for ts, eq in zip(timestamps, equity_a)]
chart_data_b = [{"time": ts.timestamp(), "value": eq} for ts, eq in zip(timestamps, equity_b)]
```

---

## Known Limitations & Future Work

### Current Limitations
1. **Pairwise comparison only** - Can only compare 2 runs at a time
2. **Same symbol required** - Cannot compare EURUSD vs GBPUSD
3. **T-test only** - No non-parametric alternatives (Mann-Whitney U)
4. **No Bayesian methods** - Frequentist statistics only

### Planned Enhancements (Phase 7)
- Multi-way comparison (3+ configurations simultaneously)
- Bayesian A/B testing with credible intervals
- Non-parametric tests (Mann-Whitney U, Wilcoxon)
- Cross-symbol comparison (normalized metrics)
- Sequential testing (early stopping for conclusive results)
- Monte Carlo simulation for robustness testing

---

## References

- **Statistical Testing**: Welch, B.L. (1947). "The generalization of 'Student's' problem when several different population variances are involved."
- **Scipy Documentation**: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html
- **A/B Testing Best Practices**: "Trustworthy Online Controlled Experiments" (Kohavi et al.)

---

## Conclusion

User Story 4 successfully delivers a production-ready A/B testing framework with rigorous statistical methodology. The implementation enables data-driven decision-making when selecting between trading configurations, providing statistical confidence in performance differences.

**Next Steps**:
1. Integrate with User Story 2 (Batch Optimization) for automatic ranking
2. Add Bayesian A/B testing (Phase 7)
3. Implement multi-way comparison (3+ runs)
4. Create dashboard visualizations for comparison reports

**Total Implementation**: 14/14 tasks complete (100%) ✅

**Overall Backtesting Engine Progress**: 105/136 tasks (77.2%) ✅

---

**Document Version**: 1.0
**Last Updated**: 2025-12-13
**Author**: RiseTrader Development Team
