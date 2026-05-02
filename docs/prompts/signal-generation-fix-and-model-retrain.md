# Sprint: Fix Signal Generation + XGBoost Retrain + Commit All

> **Priority:** EMERGENCY — system generates ZERO signals on a $15 CrudeOIL rally
> **Root Cause:** Strategy math produces sub-threshold scores during sustained trends
> **Constraint:** Paper validation mode stays ON. Do NOT disable it.

---

## Diagnosis (verified with live data Apr 3 2026)

CrudeOIL moved from $97 to $113 in 48 hours (Apr 1-2). This is one of the
strongest H1 momentum events of the year. The regime classifier correctly
identifies TRENDING (Hurst=1.0, MA50 consecutive=11 bars above). The strategy
router correctly routes to momentum + breakout + trend_following.

**But all three strategies return sub-threshold scores:**

| Strategy | Why It Fails | Score | Threshold |
|----------|-------------|-------|-----------|
| momentum | MA10/MA30 crossover happened 20+ bars ago. Continuation is dampened to 0.5×. Score × conf = 0.35 | 0.35 | 0.60 |
| breakout | Price at 111.94, 20-bar high is 112.89. Not "near" the high (>99.5%). Returns HOLD. | 0.00 | 0.60 |
| trend_following | **NOT IMPLEMENTED** — referenced in router but no method exists in live_trading_service.py | N/A | 0.60 |

**Result:** Combined weighted score ≈ 0.15-0.25. Threshold is 0.60. Every signal
is HOLD. Paper validation collects 0/50 signals indefinitely.

**Additional throughput bottleneck:** The system runs every 5 minutes but uses
H1 candles with fingerprint-based staleness check. This means it effectively
evaluates only once per hour (when a new H1 bar closes). At best, 24 evaluations
per day × 3 symbols = 72 potential signals. Most will be HOLD. Even with fixed
strategies, reaching 50 resolved paper trades will take 2-4 weeks.

---

## Task 1: Implement trend_following Strategy

**Owner:** quant-dev
**File:** `src/services/live_trading_service.py`
**Priority:** CRITICAL — the strategy router assigns 25% weight to a strategy
that doesn't exist

### Requirements

Add `_trend_following_strategy(self, prices: list) -> Optional[dict]` method.

This strategy should fire during SUSTAINED trends, not just at crossover points:

```python
def _trend_following_strategy(self, prices: list) -> Optional[dict]:
    """
    Trend-following using ADX + price position relative to EMAs.

    Fires when:
    - Price is above EMA20 AND EMA20 > EMA50 (uptrend) → BUY
    - Price is below EMA20 AND EMA20 < EMA50 (downtrend) → SELL

    Confidence scales with:
    - Distance from EMA20 (further = stronger confirmation)
    - Slope of EMA20 (steeper = more momentum)

    Unlike momentum (crossover-only), this fires continuously during trends.
    """
```

**Key design principles:**
- Must produce scores > 0.60 during a clear uptrend like the Apr 1-2 rally
- Uses EMA (not SMA) for faster response
- Confidence based on EMA slope + price-EMA distance, NOT hardcoded
- Score = directional strength (0 to 1), not binary
- Returns None if no clear trend (ADX < 20 or EMAs interleaved)

### Acceptance Criteria
- [ ] Method exists and is callable from `_generate_signal()`
- [ ] In TRENDING regime, trend_following produces score > 0.60 on current CrudeOIL data
- [ ] Backtested on last 300 H1 bars: produces at least 15+ non-HOLD signals
- [ ] Confidence is computed from data, not hardcoded
- [ ] 5 unit tests: clear uptrend → BUY, clear downtrend → SELL, flat → None, insufficient data → None, score > threshold on real-like data

---

## Task 2: Fix momentum Strategy Continuation Signals

**Owner:** quant-dev
**File:** `src/services/live_trading_service.py`
**Priority:** HIGH — currently dampens legitimate continuation to useless levels

### Problem

Current code dampens non-crossover signals by 0.5×:
```python
score = min(abs(diff) / 2.0, 1.0) * 0.5  # continuation, not crossover
```

On current data: MA10=111.08, MA30=105.39, diff=+5.69. This produces
score=0.50, combined=0.35. The strongest trend of the year gets a weaker
score than a random crossover in a ranging market.

### Fix

Replace the flat 0.5 dampening with a scaled continuation score:

```python
# Continuation signal — scale with trend strength
raw_score = min(abs(diff) / 2.0, 1.0)
if abs(diff) > 1.0:
    # Strong continuation: diff > 1.0 means well-separated MAs
    # Scale from 0.5 (diff=1) to 0.9 (diff>=5)
    continuation_factor = min(0.5 + (abs(diff) - 1.0) * 0.1, 0.9)
else:
    continuation_factor = 0.5
score = raw_score * continuation_factor
```

This way: diff=5.69 → raw=1.0, factor=0.9, score=0.90, combined=0.63 → **PASSES**.

### Acceptance Criteria
- [ ] Continuation signals in strong trends produce score > 0.60 combined
- [ ] Weak continuations (diff < 1.0) still dampened to avoid noise
- [ ] Crossover signals unchanged (still get full score)
- [ ] 3 unit tests: strong continuation, weak continuation, crossover

---

## Task 3: Fix breakout Strategy Threshold

**Owner:** quant-dev
**File:** `src/services/live_trading_service.py`
**Priority:** HIGH — too restrictive, misses valid breakouts

### Problem

Current breakout requires `price >= high_20 * 0.995` (within 0.5% of 20-bar
high). On CrudeOIL at $111.94 with a 20-bar high of $112.89, this fails because
$111.94 < $112.89 * 0.995 = $112.33.

The strategy should fire when price is in the upper zone of the range, not
only at the extreme.

### Fix

Use a percentile approach instead of proximity to extreme:

```python
range_20 = high_20 - low_20
if range_20 <= 0:
    return None

# Position within the 20-bar range (0 = at low, 1 = at high)
position = (current_price - low_20) / range_20

if position >= 0.85:  # Upper 15% of range
    score = position  # 0.85 to 1.0
    return {"action": "BUY", "score": score, "confidence": 0.65}
elif position <= 0.15:  # Lower 15% of range
    score = 1.0 - position  # 0.85 to 1.0
    return {"action": "SELL", "score": score, "confidence": 0.65}
else:
    return None  # No breakout signal
```

On current data: position = (111.94 - 103.80) / (112.89 - 103.80) = 0.896
→ score=0.896, combined=0.583. Close but still needs trend_following to push
above threshold via weighted combination.

### Acceptance Criteria
- [ ] Breakout fires when price is in upper/lower 15% of 20-bar range
- [ ] Score scales with proximity to extreme (not binary)
- [ ] 4 unit tests: near high → BUY, near low → SELL, mid-range → None, flat range → None

---

## Task 4: Retrain XGBoost with Regime Features (Docker)

**Owner:** quant-dev (inside Docker container)
**Priority:** HIGH — ml_reversal is dead weight at 8.9% F1

### Context

`reversal_features.py` already computes `regime_adx`, `regime_hurst`,
`regime_atr_ratio` (3 new features). But the deployed model was trained
March 6 with only 43 features. The training job was never run.

### Requirements

1. Run inside the Docker container (has DB access):
   ```bash
   docker exec -it risetrader-api python3 -m src.ml.training.train_reversal_classifier \
     --symbol CrudeOIL --timeframe H1 \
     --start-date 2024-01-01 --end-date 2026-03-31
   ```

2. If the training script doesn't accept those args, check its CLI interface
   and adapt. The key parameters:
   - Symbol: CrudeOIL
   - Timeframe: H1
   - Data range: 2024-01-01 to 2026-03-31
   - ZigZag: depth=12, deviation=5, backstep=3
   - Must use all 46 features (43 original + 3 regime)

3. Check metadata.json after training:
   - If peak_f1 >= 0.30: deploy as new model
   - If peak_f1 < 0.30: try class-weight balancing, reduced max_depth(4),
     SMOTE oversampling. Document results.
   - If still < 0.30: leave model gated, document in metadata.json

4. Update feature_names.json to include new features.

### Acceptance Criteria
- [ ] Training job runs successfully inside Docker
- [ ] metadata.json shows feature_count=46 and updated training_date
- [ ] If F1 passes gate: ml_reversal strategy fires in RANGING regime
- [ ] If F1 still fails: documented, model stays gated, no fake scores

---

## Task 5: Add Verbose Diagnostic Logging

**Owner:** risk-eng
**File:** `src/services/live_trading_service.py`
**Priority:** MEDIUM — needed to monitor signal health going forward

### Requirements

In `_generate_signal()`, add per-strategy logging BEFORE combining:

```python
for name, result in strategy_results.items():
    logger.info("strategy_raw_output",
                symbol=symbol, strategy=name,
                action=result.get("action"), score=round(result.get("score", 0), 4),
                confidence=round(result.get("confidence", 0), 4),
                regime=regime.value if hasattr(regime, 'value') else str(regime))
```

After combining, log the combined score vs threshold:

```python
logger.info("signal_combine_result",
            symbol=symbol, combined_score=round(score, 4),
            combined_confidence=round(confidence, 4),
            threshold=threshold,
            action=action,
            passed=abs(score) >= threshold and confidence >= self._min_confidence)
```

This makes it possible to diagnose from logs alone which strategy is
underperforming without needing to reproduce the math manually.

### Acceptance Criteria
- [ ] Every cycle logs raw output per strategy
- [ ] Every cycle logs combined score vs threshold
- [ ] Logs visible in `docker logs risetrader-api`

---

## Task 6: Commit All Uncommitted Changes

**Owner:** lead
**Priority:** CRITICAL — 30+ files at risk of accidental loss

### Context

All regime-aware system code, paper validation, integration tests, config YAML,
and this sprint's fixes are uncommitted. `git status` shows 30+ modified files.
Last committed state is `a8814d8`.

### Requirements

1. Stage all relevant files (NOT .env or credentials):
   ```bash
   git add src/ tests/ config/regime.yaml docs/prompts/ models/
   ```

2. Commit with proper format:
   ```
   feat(regime+paper): regime-aware trading + paper validation gate + signal fixes [integration-pass]

   - RegimeClassifier (ADX + Hurst R/S + ATR ratio, 4 regimes)
   - StrategyRouter (regime → strategy mapping with weights)
   - CrossAssetFilter (BRENT/USA500 confirmation)
   - PaperValidationService wired into live loop (50-signal gate)
   - Volatility-adjusted position sizing for small accounts
   - trend_following strategy implementation
   - momentum continuation scaling fix
   - breakout percentile approach fix
   - Diagnostic logging per strategy per cycle
   - config/regime.yaml externalized thresholds
   - 1100-line integration test suite
   ```

3. Verify: `git log --oneline -1` shows the commit.

### Acceptance Criteria
- [ ] All sprint files committed
- [ ] No credentials or .env in commit
- [ ] Tagged with [integration-pass]

---

## Task 7: Signal Generation Validation

**Owner:** mcp-verifier
**Priority:** BLOCKING — must confirm fixes produce signals

### Requirements

After Tasks 1-3 are deployed to Docker:

1. Wait for next H1 bar close (check `docker logs` for `regime_classified`)
2. Verify logs show:
   - `strategy_raw_output` for momentum, breakout, trend_following
   - At least ONE strategy produces score > 0.30
   - `signal_combine_result` shows combined score
   - If combined > 0.60: `paper_signal_recorded` appears
3. If still no signals after 3 H1 bars, investigate:
   - Is regime VOLATILE (all trading halted)?
   - Are all strategies returning None?
   - Is cross-asset filter rejecting everything?
4. Report: which strategies fire, what scores, what the paper gate status is

### Acceptance Criteria
- [ ] At least 1 paper signal recorded within 24 hours of deployment
- [ ] Diagnostic logs confirm strategy-level scores
- [ ] Paper validation status logging shows total > 0

---

## Execution Order

```
Tasks 1+2+3 (quant-dev) ←── PARALLEL, all in live_trading_service.py
  ↓
Task 5 (risk-eng) ←── PARALLEL with above, different section of same file
  ↓
Deploy to Docker (rebuild container)
  ↓
Task 4 (quant-dev) ←── Inside Docker, after deploy
  ↓
Task 7 (mcp-verifier) ←── After deploy, wait for next H1 bar
  ↓
Task 6 (lead) ←── After all fixes confirmed working
```

## Launch Command

```
@lead Execute `docs/prompts/signal-generation-fix-and-model-retrain.md` — Signal
Generation Fix sprint. This is EMERGENCY priority: the system generates ZERO
signals on the strongest CrudeOIL rally of the year ($97→$113). Root cause:
trend_following strategy doesn't exist (router references it, no method),
momentum dampens continuations to 0.35 (below 0.60 threshold), breakout too
restrictive (needs 99.5% of 20-bar high).

quant-dev takes Tasks 1+2+3 IN PARALLEL — all three are in
live_trading_service.py signal generation section. risk-eng takes Task 5
(diagnostic logging) simultaneously. After deploying to Docker, quant-dev
runs Task 4 (XGBoost retrain inside container). mcp-verifier monitors Task 7
(verify paper signals appear in logs). lead commits everything in Task 6
after confirmation. DO NOT disable PAPER_VALIDATION_MODE. Go.
```

## Success Criteria

The sprint is DONE when:
1. trend_following strategy exists and produces BUY on current CrudeOIL uptrend
2. momentum continuation produces score > 0.60 when MA diff > 2.0
3. breakout fires in upper/lower 15% of 20-bar range
4. Diagnostic logging shows per-strategy scores every cycle
5. Paper validation status shows total_signals > 0 within 24 hours
6. All changes committed with [integration-pass] tag
7. XGBoost retrained (or documented as still sub-gate)

## Non-Negotiable Rules

- **PAPER_VALIDATION_MODE stays TRUE.** We fix strategies, we do NOT bypass the gate.
- **No fake scores.** All scores computed from real price data.
- **No hardcoded confidence.** Confidence derived from indicator strength.
- **validate-no-fakes.sh must pass** on every edit.
- **Every commit tagged `[integration-pass]`** after mcp-verifier confirms.
