# Aggressive Recovery Strategy - Delegation Plan

## The Problem
- **Lost:** ~$8,800 (CrudeOIL short at $71.95 → $90.96)
- **Current:** $430 balance, 0.01 lot SHORT @ $93.635
- **ML Signal:** 99.7% confidence on MORE shorts (rejected by risk system)
- **Constraint:** 1 position per symbol max

## The Lamborghini on Bike Tires

| Engine (What We Have) | Tires (What Limits Us) |
|----------------------|------------------------|
| 99.7% ML confidence | $430 balance |
| 15.4x leverage | 0.01 lot minimum |
| 10 agent pipeline | 1 position/symbol rule |
| 13.5M candles history | $40.55 margin per 0.01 lot |

**Current utilization:** 0.01 lot = $40.55 margin = **9.4% of capital**
**Maximum possible:** 0.10 lot = $405.50 margin = **95% of capital**

---

## Recovery Math

### Conservative Path (Current)
- 0.01 lot = $1/pip
- Average win = 10 pips = $1
- To recover $8,800 → **8,800 trades needed**
- At 5 trades/day → **4.8 years**

### Aggressive Path (Proposed)
- 0.08 lot = $8/pip (using ~80% of capital)
- Average win = 10 pips = $80
- To recover $8,800 → **110 trades needed**
- At 5 trades/day → **22 days**

### Risk Reality
- At 0.08 lots, SL of 24 pips (2.5 ATR) = **$192 loss**
- That's **45% of account** per trade
- **One loss = disaster territory**

---

## PROPOSED STRATEGY: Controlled Aggression

### Phase 1: Gradual Scale-Up (Weeks 1-2)

#### 1.1 Enable Pyramiding for Same-Direction High-Confidence
```bash
/agent risk-eng Modify risk_controller.py to allow pyramiding when:
1. Direction matches existing position (both SELL or both BUY)
2. ML confidence > 95%
3. Total position doesn't exceed 0.05 lots
4. Account margin level stays > 200%

Current behavior: "position_already_exists" → REJECT
New behavior: "position_already_exists" + same_direction + high_confidence → ALLOW SCALE-IN
```

**File:** `src/risk/risk_controller.py`

**Acceptance Criteria:**
- [ ] Allow adding to winners, not flipping positions
- [ ] Cap total lots at 0.05 (using ~$200 margin, ~50% of account)
- [ ] Hard stop if margin level < 200%

#### 1.2 Implement Tiered Position Sizing
```bash
/agent risk-eng Create tiered_position_sizer.py that calculates lot size based on:

| ML Confidence | Account % | Max Lots |
|---------------|-----------|----------|
| 50-70% | 10% | 0.01 |
| 70-85% | 20% | 0.02 |
| 85-95% | 30% | 0.03 |
| 95%+ | 50% | 0.05 |

With current $430 balance and 99.7% confidence:
- Should use 50% = $215 margin
- That's 0.05 lots on CrudeOIL
```

---

### Phase 2: Multi-Symbol Diversification (Week 2)

#### 2.1 Add Correlated Instruments
```bash
/agent quant-dev Identify and backtest on these symbols:
1. CrudeOIL (current) - Primary
2. XAUUSD (Gold) - Flight to safety inverse
3. DXY (Dollar Index) - Oil inverse correlation
4. VIX (Volatility) - Crash indicator

When CrudeOIL SELL signal fires AND:
- DXY rising = confirm (dollar up = oil down)
- VIX stable = low fear, trend continuation
- Gold falling = risk-on sentiment

This is the regime-aware cross-asset strategy we designed.
```

#### 2.2 Allow 1 Position Per Symbol But 3 Symbols Active
```bash
/agent risk-eng Modify position limits:
- Keep: 1 position per symbol
- Change: Max 3 simultaneous symbols
- With $430 → $143 allocation per symbol max
- 0.03 lots CrudeOIL + 0.01 lot Gold + etc.
```

---

### Phase 3: Informed Flow Integration (Week 3-4)

Use the InformedFlowDetector we just designed:

```bash
/agent flow-detector Integrate price velocity detection with entry logic:

1. On HIGH/CRITICAL alert → increase position size by 1.5x
2. On "no news catalyst" → confirms informed flow, increase confidence
3. If Trump post detected with bearish_oil keywords → full size SHORT
```

---

## IMMEDIATE ACTIONS FOR CURRENT POSITION

### Right Now: Manage Existing 0.01 SHORT

Current position analysis:
- Entry: 93.635
- Current: 93.735 (in the red by ~$1)
- SL: 96.063 (24 pip loss = $24 risk)
- TP: 91.006 (26 pip profit = $26 reward)
- R:R = 1.08:1 (barely positive)

**Recommendation: Improve the R:R**

```bash
/agent risk-eng Modify the current position:

Option A - Tighter stop, wider target:
- Move SL to 94.80 (11.5 pips from current)
- Keep TP at 91.00 (27 pips to target)
- New R:R = 2.3:1

Option B - Add to position on confirmation:
- If price drops to 93.00 (signal confirmation)
- Add 0.02 lots with SL at 94.50
- Combined avg entry: 93.21, risk: $55, reward: $66
```

---

## DELEGATION COMMANDS

### Sprint 1: Position Sizing (Days 1-3)

```bash
/agent risk-eng Create src/risk/tiered_position_sizer.py

Requirements:
1. TieredPositionSizer class with confidence-based sizing
2. Integrate with PositionSizingAgent
3. Respect margin level minimum (200%)
4. Log all sizing decisions with rationale
5. Unit tests with various account/confidence scenarios

This replaces the conservative 0.01 lot default with dynamic sizing.
```

### Sprint 2: Pyramiding Logic (Days 4-6)

```bash
/agent risk-eng Modify src/risk/risk_controller.py

Add check_pyramid_eligibility() method:
- Same direction as existing position
- Combined lots don't exceed max_position_size
- ML confidence exceeds pyramid_threshold (95%)
- Time since last entry > min_pyramid_interval (5 min)
- Margin level remains > 200% after add

Replace "position_already_exists" → REJECT with conditional logic.
```

### Sprint 3: Cross-Asset Signals (Days 7-10)

```bash
/agent quant-dev Create src/strategies/cross_asset_confirmation.py

CrossAssetConfirmationFilter class:
- Check DXY direction (rising = bearish oil)
- Check VIX level (low = trend continuation)
- Check Gold direction (falling = risk-on)
- Return confirmation_score: 0-1
- Use score to boost/reduce position size

Wire into existing signal generation pipeline.
```

### Sprint 4: Integrate All Pieces (Days 11-14)

```bash
/agent lead Coordinate full integration:
1. TieredPositionSizer → PositionSizingAgent
2. Pyramiding → RiskController
3. CrossAssetConfirmation → SignalGeneratorAgent
4. InformedFlowDetector → Event Bus
5. Run full backtest on 2024 data with new logic
6. Paper trade for 1 week before live
```

---

## RISK MANAGEMENT RULES (NON-NEGOTIABLE)

Even aggressive recovery must respect these:

1. **Daily loss limit:** 5% of account ($21.50) → stop trading for day
2. **Weekly loss limit:** 15% of account ($64.50) → review strategy
3. **Margin level floor:** Never below 200%
4. **Max position size:** 0.10 lots total (all symbols combined)
5. **No overnight positions** unless SL is in profit

---

## SUCCESS METRICS

| Metric | Conservative | Aggressive Target |
|--------|--------------|-------------------|
| Trades to recover | 8,800 | 110 |
| Time to recover | 4.8 years | 22 days |
| Risk per trade | $2.40 (0.5%) | $24 (5%) |
| Win rate needed | 55% | 65% |
| Max drawdown | 10% | 40% |

---

## QUICK START

```bash
# 1. Check current situation
/agent lead Review account status and current positions

# 2. Start with position sizing
/agent risk-eng Implement tiered position sizing based on ML confidence

# 3. Enable pyramiding
/agent risk-eng Allow same-direction pyramiding for 95%+ confidence signals

# 4. Test on paper
/agent mcp-verifier Run integration tests with new position sizing logic
```

---

## THE HONEST TRUTH

With $430 and needing to recover $8,800:
- **20.5x return needed** just to break even
- Even at 0.08 lots, that's 110 winning 10-pip trades
- **One bad trade at full size = 45% drawdown**

The math says: Either accept 4.8 years of conservative recovery, OR take the aggressive path knowing you could lose the remaining $430 in a few bad trades.

**My recommendation:** Phase in the aggression gradually. Start with 0.03 lots (tiered sizing), enable pyramiding to 0.05 max, and only go to 0.08+ when the account has recovered to $800+. This gives you a middle path: faster recovery than 0.01 lot, but not betting the farm on each trade.
