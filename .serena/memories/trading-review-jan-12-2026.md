# Trading Position Review & Anti-Stop-Hunt Strategy - January 12, 2026

## Current Open Positions

### Position 1: Ticket #24500414
- Type: SELL (Short), Size: 0.50 lots
- Entry: $59.43, SL: $0.00 ⚠️, TP: $0.00
- Float: +$315.00

### Position 2: Ticket #24500413
- Type: SELL (Short), Size: 0.50 lots
- Entry: $59.07, SL: $0.00 ⚠️, TP: $0.00
- Float: +$135.00

### Combined: 1.0 lots SHORT @ avg $59.25, +$450 floating

## Account Status
- Balance: $11,053.51, Equity: $11,501.37
- Margin Level: 267.75% ✅
- Weekly Target: $2,500

## Critical Issues

1. **NO STOPS SET** - Both positions unprotected over weekend
   - Recommended: #24500414 SL $61.78, #24500413 SL $61.45 (3x ATR + offset)

2. **Stealth Config Stale** - config/stealth_stops.json has old tickets
   - Config: 24494956, 24496370 (OLD)
   - Live: 24500414, 24500413 (CURRENT)

3. **Trail Not Triggered** - Needs 1x ATR ($0.75) profit
   - Current max profit: $0.63 (below trigger)
   - Activates at ~$58.32

## Anti-Stop-Hunt Rules (LOCKED)

1. **LIQUIDITY**: Use LIMIT only, never STOP entries
2. **PLACEMENT**: Weird prices ($56.37 not $56.50), 2-3x ATR + 5-15 pip offset
3. **SWEEP**: Wait for sweep + reversal candle before entry
4. **EXECUTION**: London/NY overlap only, avoid session opens, 30min news blackout
5. **CONFIRMATION**: Candle CLOSE + 150% avg volume on breakouts

## Key Technical Levels

### Resistance
- $60.03-60.27: Major fade zone
- $59.23: Pivot point

### Support/Targets
- $56.41: TP1 (+$1,420)
- $55.75: Double bottom (critical)
- $55.00: Weekly target (+$2,125) ✅
- $54.87: TP2 (+$2,190)

## Risk Calendar
- Wed Jan 14, 10:30 AM ET: EIA Inventory (HIGH impact)
- Geopolitical: Iran protests, Venezuela, Russia sanctions

## Stealth Stop Manager Settings
```
atr_multiplier_trail: 1.5
trail_trigger_atr: 1.0
breakeven_trigger_atr: 1.5
min_offset_pips: 5
max_offset_pips: 15
pip_value: 0.01
```

## Pending Orders for $60 Fade
- SELL LIMIT $59.87, 0.50 lots, SL $61.23
- SELL LIMIT $60.47, 0.30 lots, SL $62.17

## TODO: True Stealth Improvements
1. Ghost stops mode (never send to MT4, EA monitors internally)
2. Decoy stops (visible far away, exit at real level)
3. Multi-broker splitting
