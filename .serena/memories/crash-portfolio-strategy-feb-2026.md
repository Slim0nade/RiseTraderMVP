# Crash Portfolio Strategy - February 2026

## Target: $10,000 → $1,000,000 (100x)

## Key Decisions Made

### 1. Instrument Selection (by Leverage)
- GOLD.: 20x leverage (best) - LONG for safe haven
- CrudeOIL: 13.5x leverage - SHORT for demand destruction
- USA500/USA100/USA30: 10x leverage - SHORT for crash
- 30Y_T-BOND: 10x leverage - LONG for flight to safety
- DOLLAR_INDX: 6.7x leverage - LONG for risk-off USD strength

### 2. Dalio Portfolio Allocation
- 15 uncorrelated streams
- 60% crash-SHORT (indices, oil)
- 40% safe-haven-LONG (gold, bonds, USD)

### 3. Bug Fix Applied
- File: `src/services/backtesting/trade_simulator.py`
- Issue: `execute_exit()` missing `position_id` parameter
- Fix: Added `position_id: Optional[UUID] = None` parameter
- Status: Fix written, needs container restart

### 4. Anti-Stop-Hunt Rules
- Never use round numbers for stops
- ATR 2.5x + random 5-15 pip offset
- Enter during London/NY overlap only
- Wait for sweep + reversal confirmation

### 5. Position Sizing for 100x
- Aggressive compounding approach
- Maximum leverage on high-conviction trades
- Trail stops with 2x ATR during crash
- Let winners run, don't take profits early

## Pending Orders to Deploy

### CrudeOIL (SHORT)
- SELL LIMIT $65.47, SL $67.23, TP $58.00, 0.3 lots
- SELL LIMIT $66.87, SL $69.03, TP $57.00, 0.2 lots
- SELL STOP $62.00, SL $64.17, TP $54.00, 0.5 lots

### USA500 (SHORT)
- SELL LIMIT $7,050, SL $7,175, TP $6,500, 0.1 lots
- SELL STOP $6,900, SL $7,050, TP $6,200, 0.2 lots

### GOLD (LONG)
- BUY LIMIT $5,000, SL $4,875, TP $5,500, 0.05 lots
- BUY STOP $5,150, SL $5,025, TP $5,800, 0.05 lots

## Next Steps
1. Restart API container for bug fix
2. Run optimization on all strategies
3. Deploy pending orders
4. Monitor for crash signals (VIX > 25, 200 DMA break)

Session: 2026-02-10
