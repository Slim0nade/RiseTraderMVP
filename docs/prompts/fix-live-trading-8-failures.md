# AGENT TEAM PROMPT: Fix 8 Live Trading Failures (HOT-PATCH + REBUILD)

## MISSION
Fix all 8 compounding failures in `src/services/live_trading_service.py` and its dependencies that caused 3 consecutive SELL trades during a CrudeOIL rally ($93→$100), losing C$40.41. The live loop MUST NOT be stopped — existing stealth trailing stops must keep running. Instead, we hot-patch signal generation first, then rebuild each layer properly.

## CONTEXT: THE 8 FAILURES

| # | Failure | File(s) | Severity |
|---|---------|---------|----------|
| 1 | ML model has 8.9% peak F1 but outputs 92% confidence → confident liar | `models/reversal_classifier/CrudeOIL_H1/metadata.json` | CRITICAL |
| 2 | Signal weighting rigged: ML is 60× stronger than other strategies | `live_trading_service.py:368-405` | CRITICAL |
| 3 | Zero trend filter — reversal detector calls every new high a "peak" | Entire pipeline | CRITICAL |
| 4 | Stale H1 candles → identical prediction repeated 12×/hour | `live_trading_service.py:592,722-780` | HIGH |
| 5 | Pyramid loophole: re-enters same losing direction after stop-out with larger size | `live_trading_service.py:938-969` | HIGH |
| 6 | Tiered sizer rewards overconfident models (93% conf → 30% of account) | `src/trading/risk/tiered_position_sizer.py` | HIGH |
| 7 | Signal threshold lowered from 0.6→0.5 to "let ML signals through" | `live_trading_service.py:443-444` | MEDIUM |
| 8 | Zero feature drift monitoring — model trained March 5, no staleness check | `live_trading_service.py:216-304` | MEDIUM |

## DELEGATION

### TASK 0 — HOT-PATCH (risk-eng, IMMEDIATE, < 5 min)
**Goal:** Neuter new entries without killing the loop. Stealth stops keep trailing.

**File:** `src/services/live_trading_service.py`

Add a **signal cooldown + direction lock** at the TOP of `_process_symbol()` (line ~584), BEFORE any signal generation:

```python
# --- HOT-PATCH: Post-loss cooldown ---
# After a stop-loss, block same-direction entries for N cycles
_direction_cooldowns: Dict[str, Tuple[str, int]] = {}  # symbol → (blocked_direction, cycles_remaining)
COOLDOWN_CYCLES = 12  # 12 × 5min = 1 hour cooldown after a loss
```

In `_process_symbol`, after fetching candles but before `_generate_signal`:
```python
# Check cooldown
if symbol in self._direction_cooldowns:
    blocked_dir, remaining = self._direction_cooldowns[symbol]
    if remaining > 0:
        self._direction_cooldowns[symbol] = (blocked_dir, remaining - 1)
        # Still generate signal for logging, but block execution
    else:
        del self._direction_cooldowns[symbol]
```

After a trade is stopped out (detect via position disappearing from open_positions between cycles), set:
```python
self._direction_cooldowns[symbol] = (last_direction, COOLDOWN_CYCLES)
```

Also **immediately raise signal threshold back to 0.6**:
```python
self._signal_threshold: float = 0.6  # RESTORED — was lowered to 0.5, caused bad entries
self._min_confidence: float = 0.6    # RAISED — force higher consensus
```

**Commit:** `fix(live-trading): hot-patch cooldown + restore 0.6 threshold [integration-pass]`

---

### TASK 1 — TREND FILTER (quant-dev, ~30 min)
**Goal:** Create `src/trading/filters/trend_filter.py` — a trend guard that suppresses counter-trend signals.

**Specification:**
```python
class TrendFilter:
    """
    Suppresses reversal signals that oppose the dominant trend.

    Uses 3 confirmations:
    1. Price vs MA(50): price > MA50 = uptrend
    2. MA(20) vs MA(50): MA20 > MA50 = uptrend
    3. ADX(14) > 25: trending (vs ranging)

    If 2/3 confirm uptrend AND signal is SELL → suppress (return HOLD)
    If 2/3 confirm downtrend AND signal is BUY → suppress (return HOLD)
    If ADX < 20 → ranging, allow all signals (reversal detector appropriate)
    """

    def should_suppress(self, prices: List[Dict], proposed_action: str) -> Tuple[bool, str]:
        """
        Returns (should_suppress: bool, reason: str).

        prices: OHLCV dicts, oldest-first, minimum 50 entries.
        proposed_action: "BUY" or "SELL"
        """
```

**ADX calculation:** Use Wilder's smoothed ADX(14). Implement from scratch in the filter — do NOT add a dependency. Formula:
- +DM, -DM from consecutive highs/lows
- Smoothed +DI, -DI over 14 periods (Wilder smoothing)
- DX = |+DI - -DI| / (+DI + -DI)
- ADX = Wilder smoothed DX over 14 periods

**Integration point:** In `live_trading_service.py._process_symbol()`, AFTER `_generate_signal()` returns action/score/confidence, BEFORE `_validate_signal()`:
```python
from src.trading.filters.trend_filter import TrendFilter
_trend_filter = TrendFilter()

# After signal generation
if action != "HOLD":
    suppress, reason = _trend_filter.should_suppress(candles_raw, action)
    if suppress:
        logger.info("trend_filter_suppressed", symbol=symbol, action=action, reason=reason)
        return  # Skip this signal
```

**Tests required:**
- Unit: `tests/unit/trading/filters/test_trend_filter.py`
  - Synthetic uptrend (50 ascending closes) + SELL → suppressed
  - Synthetic downtrend + BUY → suppressed
  - Synthetic range (ADX < 20) + SELL → allowed
  - Uptrend + BUY → allowed
- Integration: Feed real CrudeOIL H1 candles from DB, verify during March 2026 rally it would have suppressed SELL

**Commit:** `feat(trend-filter): ADX+MA trend guard for counter-trend suppression [integration-pass]`

---

### TASK 2 — REBALANCE SIGNAL WEIGHTS (quant-dev, ~20 min)
**Goal:** Fix signal combination so ML can't dominate when other strategies disagree.

**File:** `src/services/live_trading_service.py`, function `_combine_signals()`

**Current problem:** The formula `score * weight * confidence` means a high-confidence ML signal (0.926 × 0.35 × 0.926 = 0.300) drowns out everything else.

**Fix — use agreement-weighted voting:**
```python
def _combine_signals(strategy_signals: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Agreement-weighted voting. ML weight is capped and requires corroboration.

    Step 1: Count directional agreement (how many strategies agree on BUY vs SELL)
    Step 2: If ML disagrees with majority of non-ML strategies, halve ML weight
    Step 3: Cap ML effective contribution to 40% of total weighted score
    """
    weights = {
        "ml_reversal": 0.25,     # REDUCED from 0.35
        "value_area": 0.25,      # INCREASED from 0.30
        "momentum": 0.20,        # INCREASED from 0.15
        "mean_reversion": 0.15,  # INCREASED from 0.10
        "breakout": 0.15,        # INCREASED from 0.10
    }

    # Step 1: Determine non-ML consensus direction
    non_ml_scores = []
    for name, sig in strategy_signals.items():
        if name == "ml_reversal":
            continue
        s = sig.get("score", 0.0)
        if abs(s) > 0.01:  # Ignore near-zero
            non_ml_scores.append(s)

    non_ml_direction = np.sign(np.mean(non_ml_scores)) if non_ml_scores else 0

    # Step 2: Check if ML disagrees with non-ML consensus
    ml_sig = strategy_signals.get("ml_reversal", {})
    ml_direction = np.sign(ml_sig.get("score", 0.0))

    effective_weights = dict(weights)
    if ml_direction != 0 and non_ml_direction != 0 and ml_direction != non_ml_direction:
        # ML disagrees with majority — halve its weight
        effective_weights["ml_reversal"] *= 0.5
        # Redistribute to agreeing strategies
        redistrib = weights["ml_reversal"] * 0.5 / max(len(non_ml_scores), 1)
        for name in strategy_signals:
            if name != "ml_reversal" and name in effective_weights:
                effective_weights[name] += redistrib

    # Step 3: Standard weighted combination with effective weights
    weighted_sum = 0.0
    total_weight = 0.0
    confidence_sum = 0.0
    count = 0

    for name, signal in strategy_signals.items():
        w = effective_weights.get(name, 0.0)
        if w <= 0:
            continue
        score = signal.get("score", 0.0)
        conf = signal.get("confidence", 0.0)
        # Use sqrt(confidence) to dampen overconfident ML
        effective_conf = conf ** 0.5
        weighted_sum += score * w * effective_conf
        total_weight += w * effective_conf
        confidence_sum += conf
        count += 1

    if total_weight == 0.0 or count == 0:
        return {"score": 0.0, "confidence": 0.0}

    return {
        "score": weighted_sum / total_weight,
        "confidence": confidence_sum / count,
    }
```

**Key changes:**
1. ML weight reduced 0.35 → 0.25, others increased proportionally
2. If ML disagrees with non-ML consensus, its weight is halved
3. `conf ** 0.5` instead of raw `conf` — dampens overconfident models (0.926 → 0.962 vs 0.70 → 0.837, much closer)

**Tests:** Add `tests/unit/services/test_combine_signals.py`:
- All agree SELL → SELL with high confidence
- ML says SELL, 3 others say BUY → final should be BUY or weak HOLD
- ML says SELL with 0.95 conf, others say BUY with 0.3 conf → NOT SELL

**Commit:** `fix(signal-weights): agreement-weighted voting, ML can't override consensus [integration-pass]`

---

### TASK 3 — MODEL QUALITY GATE (risk-eng, ~20 min)
**Goal:** Block models with F1 below threshold from influencing live trades.

**File:** `src/services/live_trading_service.py`, function `_ml_reversal_strategy()`

**Add after loading the model (line ~270), before prediction:**
```python
# Model quality gate — block models with poor reversal F1
metadata_file = model_dir / "metadata.json"
if metadata_file.exists():
    import json
    with open(metadata_file) as f:
        meta = json.load(f)
    reversal_f1 = meta.get("reversal_f1", 0.0)
    peak_f1 = meta.get("peak_f1", 0.0)
    valley_f1 = meta.get("valley_f1", 0.0)

    MIN_REVERSAL_F1 = 0.30  # Minimum acceptable reversal F1
    if reversal_f1 < MIN_REVERSAL_F1:
        logger.warning(
            "ml_model_quality_gate_blocked",
            symbol=symbol,
            reversal_f1=reversal_f1,
            peak_f1=peak_f1,
            valley_f1=valley_f1,
            min_required=MIN_REVERSAL_F1,
        )
        return None  # Model too poor — skip ML signal entirely
```

**This alone would have prevented all 3 bad trades.** The CrudeOIL model has `reversal_f1=0.116`, far below the 0.30 gate.

**Also add model staleness check:**
```python
    # Model staleness check — block models older than 14 days
    training_date_str = meta.get("training_date", "")
    if training_date_str:
        from datetime import datetime, timezone
        try:
            training_date = datetime.fromisoformat(training_date_str)
            age_days = (datetime.now(timezone.utc) - training_date.replace(tzinfo=timezone.utc)).days
            MAX_MODEL_AGE_DAYS = 14
            if age_days > MAX_MODEL_AGE_DAYS:
                logger.warning(
                    "ml_model_stale",
                    symbol=symbol,
                    training_date=training_date_str,
                    age_days=age_days,
                    max_age=MAX_MODEL_AGE_DAYS,
                )
                return None
        except (ValueError, TypeError):
            pass  # Can't parse date, skip staleness check
```

**Commit:** `feat(model-gate): block ML models with F1<0.30 or age>14d from live trading [integration-pass]`

---

### TASK 4 — FIX STALE CANDLE PROBLEM (quant-dev, ~15 min)
**Goal:** Prevent identical predictions from repeating every 5 minutes on unchanged H1 data.

**File:** `src/services/live_trading_service.py`

**Add candle fingerprint cache to the class:**
```python
# In __init__:
self._last_candle_fingerprint: Dict[str, str] = {}  # symbol → hash of last 5 closes
self._signal_cache: Dict[str, Tuple[str, float, float, float]] = {}  # symbol → last signal
```

**In `_process_symbol`, after fetching candles:**
```python
# Stale candle detection — skip if H1 data hasn't changed
fingerprint = "|".join(f"{c['close']:.5f}" for c in candles_raw[-5:])
if fingerprint == self._last_candle_fingerprint.get(symbol):
    logger.debug("stale_candles_skipping", symbol=symbol, fingerprint=fingerprint[:40])
    return  # Same H1 candles as last cycle — no new information
self._last_candle_fingerprint[symbol] = fingerprint
```

This ensures the system only acts on genuinely new information. When a new H1 candle closes, the fingerprint changes and signal generation proceeds.

**Commit:** `fix(stale-candles): fingerprint cache prevents identical H1 predictions repeating [integration-pass]`

---

### TASK 5 — FIX PYRAMID LOOPHOLE (risk-eng, ~20 min)
**Goal:** Prevent re-entering the same losing direction after a stop-out.

**File:** `src/services/live_trading_service.py`

**Add loss memory to the class:**
```python
# In __init__:
self._recent_losses: Dict[str, List[Tuple[str, float, datetime]]] = {}
# symbol → [(direction, loss_amount, timestamp), ...]
```

**Track closed positions each cycle.** In `_run_loop`, BEFORE the symbol processing loop, compare current open positions to previous cycle's snapshot:
```python
# In __init__:
self._prev_open_tickets: Dict[int, Dict] = {}  # ticket → position info

# In _run_loop, before symbol loop:
current_positions = await self._get_all_open_positions()
current_tickets = {p.get("ticket"): p for p in current_positions}

# Detect closed positions (were open last cycle, gone now)
for ticket, prev_pos in self._prev_open_tickets.items():
    if ticket not in current_tickets:
        sym = prev_pos.get("symbol", "").rstrip(".")
        direction = prev_pos.get("type", "")
        profit = float(prev_pos.get("profit", 0))
        if profit < 0:  # Was a loss
            if sym not in self._recent_losses:
                self._recent_losses[sym] = []
            self._recent_losses[sym].append((direction, profit, datetime.now(timezone.utc)))
            logger.info("loss_detected", symbol=sym, direction=direction, profit=profit, ticket=ticket)
self._prev_open_tickets = current_tickets
```

**In `_validate_signal`, add loss-direction check BEFORE the existing position check (around line 938):**
```python
# Block same-direction re-entry within 1 hour of a loss
db_symbol = symbol.rstrip(".")
if db_symbol in self._recent_losses:
    recent = self._recent_losses[db_symbol]
    # Clean entries older than 1 hour
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = [(d, p, t) for d, p, t in recent if t > cutoff]
    self._recent_losses[db_symbol] = recent

    for loss_dir, loss_amt, loss_time in recent:
        if loss_dir.upper() == action:
            return False, f"post_loss_cooldown ({loss_dir} lost ${abs(loss_amt):.2f} at {loss_time.strftime('%H:%M')})", 0.0
```

**Also fix the lot size escalation after loss:** In the tiered sizer, add a "loss streak" penalty. After consecutive losses on same symbol, REDUCE tier by one level:
```python
# In TieredPositionSizer.calculate_lot_size, add parameter:
def calculate_lot_size(self, confidence, account_balance, symbol, atr,
                       existing_lots=0.0, recent_loss_count=0):
    # Penalize confidence for recent losses
    loss_penalty = min(recent_loss_count * 0.10, 0.30)  # Max 30% reduction
    effective_confidence = confidence - loss_penalty
```

**Commit:** `fix(pyramid-loophole): block same-direction re-entry after stop-out, loss-streak penalty [integration-pass]`

---

### TASK 6 — FIX TIERED SIZER OVERCONFIDENCE (risk-eng, ~15 min)
**Goal:** The sizer must not treat model probability as accuracy.

**File:** `src/trading/risk/tiered_position_sizer.py`

**Change the tier table to be more conservative:**
```python
TIERS = [
    (0.95, 0.20),  # Was 50% → now 20%. 95%+ conf still gets most, but not half the account
    (0.85, 0.15),  # Was 30% → now 15%
    (0.70, 0.10),  # Was 20% → now 10%
    (0.50, 0.05),  # Was 10% → now 5%
]
```

**Also cap ML-sourced confidence in live_trading_service.py:**
In `_validate_signal`, line 976:
```python
# Cap ML confidence for sizing — model probability != model accuracy
# Until model F1 > 0.50, cap sizing confidence at 0.70
sizing_conf = ml_confidence if ml_confidence > 0 else confidence
sizing_conf = min(sizing_conf, 0.70)  # Hard cap prevents top tier abuse
```

**Commit:** `fix(position-sizing): conservative tiers, cap ML confidence for sizing [integration-pass]`

---

### TASK 7 — FEATURE DRIFT MONITOR (quant-dev, ~20 min)
**Goal:** Detect when live features are outside the training distribution.

**File:** Create `src/ml/monitoring/feature_drift.py`

```python
class FeatureDriftMonitor:
    """
    Detects when live feature values are outside training distribution.

    Uses simple z-score method: if >30% of features have |z| > 3.0
    relative to training stats, the model is operating out-of-distribution.
    """

    def __init__(self, training_stats_file: Path):
        """Load feature means and stds from training run."""
        # training_stats.json: {"feature_name": {"mean": x, "std": y}, ...}

    def check_drift(self, features: np.ndarray, feature_names: List[str]) -> Tuple[bool, float, Dict]:
        """
        Returns (is_drifted, drift_pct, per_feature_zscores).
        is_drifted = True if > 30% of features have |z| > 3.0
        """
```

**Training stats generation:** Add to `train_reversal_classifier.py` — after training, save feature means and stds:
```python
stats = {}
for col in X_train.columns:
    stats[col] = {"mean": float(X_train[col].mean()), "std": float(X_train[col].std())}
with open(model_dir / "training_stats.json", "w") as f:
    json.dump(stats, f)
```

**Integration:** In `_ml_reversal_strategy`, after computing features but before prediction:
```python
stats_file = model_dir / "training_stats.json"
if stats_file.exists():
    from src.ml.monitoring.feature_drift import FeatureDriftMonitor
    monitor = FeatureDriftMonitor(stats_file)
    is_drifted, drift_pct, _ = monitor.check_drift(last_row, available)
    if is_drifted:
        logger.warning("feature_drift_detected", symbol=symbol, drift_pct=round(drift_pct, 2))
        return None  # Don't trust out-of-distribution predictions
```

**For the CURRENT model (no training_stats.json exists yet):** The model quality gate from Task 3 already blocks it (F1=0.116 < 0.30). This task is forward-looking for retrained models.

**Commit:** `feat(drift-monitor): z-score feature drift detection blocks OOD predictions [integration-pass]`

---

### TASK 8 — INTEGRATION TESTS (mcp-verifier, ~30 min)

**After all code changes are committed, verify:**

1. **Trend filter test with real data:**
```python
# Fetch CrudeOIL H1 candles from March 15-25 2026 (the rally period)
# Run trend_filter.should_suppress(candles, "SELL") → must return True
# Run trend_filter.should_suppress(candles, "BUY") → must return False
```

2. **Model quality gate test:**
```python
# Call _ml_reversal_strategy(real_candles, "CrudeOIL")
# → must return None (blocked by F1 < 0.30)
```

3. **Signal combination test:**
```python
# Simulate: ML says SELL (score=-0.92, conf=0.92), momentum says BUY (score=0.08, conf=0.70)
# → combined score must NOT be SELL
```

4. **Stale candle test:**
```python
# Call _process_symbol twice with same candles → second call must skip
```

5. **Post-loss cooldown test:**
```python
# Simulate: SELL loss on CrudeOIL → next SELL signal within 1hr must be rejected
# BUY signal should still be allowed
```

6. **Full pipeline E2E (dry-run mode):**
```python
# Set dry_run=True
# Run 3 cycles with real CrudeOIL H1 candles
# Verify: zero SELL signals emitted during the current rally
```

**Commit:** `test(live-trading): 6 integration tests for 8-failure fix [integration-pass]`

---

## EXECUTION ORDER

```
PARALLEL GROUP 1 (immediate):
  risk-eng  → Task 0 (hot-patch, 5 min) ← DEPLOY FIRST, restart API
  quant-dev → Task 1 (trend filter, 30 min)

PARALLEL GROUP 2 (after Task 0 deployed):
  risk-eng  → Task 3 (model quality gate)
  quant-dev → Task 2 (signal weights)

PARALLEL GROUP 3:
  risk-eng  → Task 5 (pyramid fix) + Task 6 (sizer fix)
  quant-dev → Task 4 (stale candles) + Task 7 (drift monitor)

SERIAL (after all above):
  mcp-verifier → Task 8 (integration tests)
  reviewer → Final review of all changes
```

## ABSOLUTE RULES (from CLAUDE.md — still enforced)
- No hardcoded ATR, ML confidence, correlation, VaR, or Kelly inputs
- All ATR from `atr_calculator.py` with real candle data
- 2% account risk cap per position — verify the new tiers don't violate this
- Anti-stop-hunt offsets on all stops (already present, don't remove)
- 3-tier testing: unit → integration → e2e
- Every commit tagged `[integration-pass]`
- File ownership enforced: risk-eng owns `live_trading_service.py` risk sections + `tiered_position_sizer.py`, quant-dev owns filters + signal logic

## SUCCESS CRITERIA
After all 8 tasks complete:
1. `_ml_reversal_strategy("CrudeOIL")` returns `None` (blocked by F1 gate)
2. Trend filter suppresses SELL during uptrend with ADX > 25
3. Signal weights: ML alone cannot produce score > 0.5 (threshold)
4. Stale candle cache: same H1 data → skip (no repeated prediction)
5. Post-loss cooldown: no same-direction re-entry within 1 hour
6. Tiered sizer: max tier is now 20% (was 50%), ML conf capped at 0.70
7. Signal threshold restored to 0.6
8. All 6 integration tests pass
9. Live loop never stopped — stealth trailing continues throughout
