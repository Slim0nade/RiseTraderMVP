# Signal Generation Fix Sprint — Evaluation (Apr 4, 2026)

## Sprint Outcome: Strategy Fixes WORKING, Blocked by Account Size

### What Was Built

**1. trend_following strategy (NEW, lines 233-289)**
- EMA20/EMA50 alignment: BUY when price > EMA20 > EMA50, SELL when inverse
- Score = `min(separation * 20 + distance * 10, 1.0)` — scales with EMA gap and price distance
- Confidence = `min(0.5 + abs(ema20_slope) * 50, 0.90)` — 5-bar EMA20 slope, capped 0.90
- Live result: score=0.97, confidence=0.90. WORKING.

**2. momentum continuation fix (lines 132-166)**
- Old: flat 0.5× dampening on ALL non-crossover signals
- New: `continuation_factor = min(0.5 + abs(diff) / long_ma * 20, 0.9)` when MAs separated > 1%
- Live result: score=0.90, confidence=0.70. FIXED (was 0.35).

**3. breakout percentile approach (lines 199-230)**
- Old: required price >= 99.5% of 20-bar high
- New: position within 20-bar range; triggers at 0.85 (upper 15%) or 0.15 (lower 15%)
- Live result: score=0.90, confidence=0.65. FIXED (was 0.00).

**4. Diagnostic logging (lines 1254-1270)**
- `strategy_raw_output`: per-strategy raw scores every cycle
- `signal_combine_result`: combined score vs threshold with pass/fail

**5. Dead imports** — Decimal, ValueAreaStrategy, MarketTick now all actively used (cleaned up).

### Combined Signal on Live Data
CrudeOIL TRENDING regime (ADX=33.85, Hurst=1.0, trending_score=3/3):
- Combined score=0.92, confidence=0.75, threshold=0.60 → PASSED
- Cross-asset: confirmation=0.0 (BRENT neutral, USA500 neutral) → PASSED (above -0.3)

### The Blocker: Account Too Small for CrudeOIL ATR

Signal passes ALL filters but blocked at position sizing:
- ATR(14) = $1.71
- Max stop at 5% risk, 0.01 lots, contract_size=1000: $1.467
- Ratio: $1.467 / $1.71 = 0.86× ATR
- ATR floor: 0.9× ATR
- 0.86 < 0.90 → BLOCKED (lot_size_zero_after_caps)

### The Math
- Minimum account for CrudeOIL at ATR=$1.71: $307.80
- Current account: $293.39 (short by $14.41)
- If ATR floor lowered to 0.8×: trade PASSES (stop at 0.86× ATR is still legitimate)
- GBPJPY ratio ≈ 29× ATR → easily tradeable
- USA500 ratio ≈ 1.96× ATR → easily tradeable
- Only CrudeOIL blocked (high ATR + large contract size)

### XGBoost: STILL NOT RETRAINED
- metadata.json: training_date=2026-03-06, feature_count=43, peak_f1=0.089
- Quality gate blocks it (F1 < 0.30), ml_reversal returns None every cycle
- Regime features added to reversal_features.py but training never executed

### MT4 Status
- get_account_info timeout (EA may not be running)
- Last known: $293.39, 0 positions
- H1 candle data flowing to DB (last: Apr 2 20:00 UTC)

### Paper Validation Gate
- PAPER_VALIDATION_MODE=true, paper signals: 0/50
- CrudeOIL signals pass all filters but sizer blocks
- GBPJPY/USA500 may produce paper signals when their strategies fire
- All changes uncommitted (30+ files)
