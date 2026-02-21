# Backtest Accuracy Fix Plan

**Date:** 2026-01-01
**Status:** IN PROGRESS

## Problem Summary

The backtesting engine is **significantly overstating profits** due to incorrect cost modeling.

### Accuracy Analysis (Run 7ed75629, 11 trades)

| Metric | Current (Buggy) | Accurate (Fortrade) | Error |
|--------|-----------------|---------------------|-------|
| Contract Size | 100 | **1000** | 10x wrong |
| Spread Cost/Lot | ~$3 | **$40** | 13x underestimated |
| Total Fees | $7.86 | **$22.99** | $15.13 missing |
| Net P&L | -$62.30 | **-$77.44** | **$15.14 overstated** |

## Root Causes

### 1. Wrong Contract Size
- **Bug:** Using 100 barrels/lot
- **Actual:** 1000 barrels/lot (from MT4 specification)
- **Impact:** Position sizing calculations 10x off

### 2. Wrong Cost Model
- **Bug:** Using % slippage (0.1%) as spread proxy
- **Actual:** Fixed spread of 40 points = $40/lot
- **Impact:** Spread costs underestimated by ~13x

### 3. Missing Swap/Overnight Fees
- **Bug:** No overnight fees calculated
- **Actual:** ~$3.50/lot/night for longs (TBD - need exact rate)
- **Impact:** Multi-day trades show inflated profits

### 4. No Triple Swap Wednesday
- **Bug:** Not implemented
- **Actual:** 3x swap charged on Wednesday for weekend settlement

## Fortrade CrudeOIL Specifications (from MT4)

```
Contract Size:     1000 barrels
Digits:            3 (price format: 57.505)
Spread:            40 points ($0.040/barrel)
Tick Size:         0.001
Tick Value:        $1.00 per tick per lot
Margin:            7.3% (~13.7:1 leverage)
Commission:        $0 (spread only)
Swap Long:         TBD - need from MT4
Swap Short:        TBD - need from MT4
Rollover Time:     22:00 UTC (server time)
Triple Swap Day:   Wednesday
```

## Files Changed

### Created
1. `/src/services/backtesting/cfd_specifications.py` - CFD instrument specs
2. `/src/services/backtesting/cfd_trade_simulator.py` - Enhanced simulator
3. `/src/services/backtesting/validate_accuracy.py` - Validation script

### To Update
1. `/src/services/backtesting/backtest_service.py` - Use CFD simulator
2. `/src/services/backtesting/trade_simulator.py` - Deprecate or update
3. Database models - Add swap tracking fields

## Action Items

- [x] Create CFD specifications module with Fortrade values
- [x] Create CFD trade simulator with proper spread model
- [x] Create accuracy validation script
- [ ] **Get swap rates from MT4** (user needs to scroll in specification)
- [ ] Update backtest service to use CFD simulator
- [ ] Add database migration for swap tracking
- [ ] Re-run backtests with accurate cost model
- [ ] Create unit tests for CFD calculations

## How to Get Swap Rates

In MT4:
1. Right-click "CrudeOIL" in Market Watch
2. Select "Specification" or "Properties"
3. Look for:
   - Swap long
   - Swap short
   - Swap type (points or currency)

Or hold a position overnight and check the swap charged in the Trade tab.

## Expected Impact

After fixes, backtests will show:
- **More realistic (lower) profits** or higher losses
- **Proper spread cost** of ~$40 per lot round trip
- **Overnight holding costs** for positions held past 22:00 UTC
- **Triple swap** on Wednesdays

This will prevent false confidence in strategies that only appear profitable
due to underestimated trading costs.
