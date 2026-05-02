# AGENT TEAM PROMPT: Regime-Aware Strategy System — Path to Profit

## MISSION
Replace the current "run all strategies blindly" approach with a regime-aware strategy selector that only deploys the right strategy for the current market condition. This is the single highest-value change remaining. The system must: (1) classify market regime in real-time, (2) route to the correct strategy, (3) add cross-asset confirmation, (4) validate on paper for 50 signals before live, (5) retrain XGBoost WITH regime features in parallel.

## CONTEXT: WHY THIS IS THE PRIORITY

**Account:** $293.39. Min lot 0.01. CrudeOIL contract size 1000. A 2×ATR stop ($3.00) = $30 loss = 10.2% of account. The 2% risk cap is structurally impossible at min lots. This means: fewer trades, higher selectivity, only trade when multiple factors align.

**What just happened:** CrudeOIL moved from $93→$106→$98→$104 in one week. BRENT spiked +6.6% in one hour. USA500 dropped -1.07% simultaneously. The system had no concept of regime, no cross-asset signal, no volatility halt. The 8-failure fix patched the bleeding but didn't add intelligence.

**Current data (all live and streaming):**
- CrudeOIL: 95K+ H1 candles, live MT4 stream
- USA500: 13K+ H1, live MT4 stream
- BRENT_OIL: 39K+ H1, live MT4 stream
- GBPJPY: 43K+ H1, live MT4 stream
- WHEAT/CORN/GASOLINE: ~275 H1 each (MT4 only, 1 month)
- TSLA/MSFT: 5K+ H1, live MT4 stream

**Existing strategies (registered in SyntheticEngine):**
- `crude_oil_v3` — Multi-indicator (EMA/RSI/CCI/ATR), time-filtered
- `ma_crossover` — 10/30 SMA crossover
- `rsi` — RSI mean reversion (30/70)
- `trend_following` — 20-period momentum
- `mean_reversion` — Bollinger Bands 2σ
- `value_area` — TPO/Volume Profile mean-reversion from VAH/VAL to POC

**Existing infrastructure we're building on:**
- `src/trading/filters/trend_filter.py` — ADX+MA trend guard (just built in 8-failure fix)
- `src/services/live_trading_service.py` — Hot-patched with cooldown, stale candle filter, model quality gate
- `src/trading/risk/tiered_position_sizer.py` — Conservative tiers (20%/15%/10%/5%)
- `src/ml/training/train_reversal_classifier.py` — XGBoost + LSTM training pipeline
- `src/ml/features/reversal_features.py` — 43 features including ROC, ATR, MACD, RSI, volume

## DELEGATION

### TASK 1 — REGIME CLASSIFIER (quant-dev, 45 min)
**Goal:** Create `src/trading/regime/regime_classifier.py` — a rule-based regime detector that runs on every cycle.

**No ML required.** This uses the indicators we already compute. Three regimes, each with clear entry criteria:

```python
"""
Regime Classifier

Classifies the current market into one of three regimes using
only price action and standard indicators. No ML — rules are
transparent and debuggable.

Regimes:
  TRENDING  — Strong directional move. Only trend-following strategies.
  RANGING   — Oscillating around a mean. Mean-reversion strategies.
  VOLATILE  — Extreme moves, news-driven. HALT all trading.
"""
from enum import Enum
from typing import Dict, List, Tuple, Optional
import numpy as np

class MarketRegime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"

class RegimeClassifier:
    """
    Multi-factor regime detection using ADX, ATR ratio, and Hurst exponent.

    Classification rules (2-of-3 confirmation required):

    TRENDING (all must be true):
      1. ADX(14) > 25
      2. Price above/below MA(50) for 10+ consecutive bars
      3. Hurst exponent > 0.55 (persistent trend)

    RANGING (all must be true):
      1. ADX(14) < 20
      2. Price crossed MA(20) at least 3 times in last 20 bars
      3. Hurst exponent between 0.35 and 0.55

    VOLATILE (any one triggers halt):
      1. Current ATR(14) > 2.5× its 50-period SMA (extreme volatility)
      2. Single bar range > 3× ATR(14) (news candle)
      3. Hourly return > 3× standard deviation of 50-period returns

    UNKNOWN: None of the above conditions are met clearly — reduce position size.
    """

    def classify(self, prices: List[Dict], candle_count_min: int = 60) -> Tuple[MarketRegime, Dict]:
        """
        Classify current regime from OHLCV data.

        Args:
            prices: Chronological OHLCV dicts (oldest first), minimum 60 bars.

        Returns:
            Tuple of (regime, metadata_dict) where metadata contains:
              - adx: float
              - atr_ratio: float (current ATR / 50-period ATR SMA)
              - hurst: float
              - ma50_consecutive: int (bars above/below MA50)
              - ma20_crosses: int (in last 20 bars)
              - regime_confidence: float (0-1, how clearly the regime is identified)
        """

    def _compute_adx(self, highs, lows, closes, period=14) -> float:
        """Wilder's ADX — reuse logic from trend_filter.py if possible."""

    def _compute_hurst(self, closes, max_lag=20) -> float:
        """
        Rescaled range (R/S) Hurst exponent estimation.

        H > 0.5: trending (persistent)
        H = 0.5: random walk
        H < 0.5: mean-reverting (anti-persistent)

        Uses lags from 2 to max_lag. Linear regression of log(R/S) vs log(lag).
        """
        # Standard R/S analysis implementation
        # For each lag n:
        #   1. Split series into non-overlapping blocks of size n
        #   2. For each block: compute range R and std S
        #   3. R/S_n = mean(R/S across blocks)
        # Hurst = slope of log(R/S_n) vs log(n)

    def _compute_atr_ratio(self, highs, lows, closes, period=14, sma_period=50) -> float:
        """Current ATR(14) divided by 50-period SMA of ATR(14)."""
```

**Hurst exponent is critical.** This is the SOTA differentiator — academic literature (Mandelbrot, Peters) shows H distinguishes trending from mean-reverting better than ADX alone. CrudeOIL during the rally would have H > 0.6 (trending), while CrudeOIL during the $100-104 consolidation would have H ≈ 0.45 (ranging).

**Tests:**
- Unit: Synthetic trending series (y = 0.1*x + noise) → TRENDING, H > 0.55
- Unit: Synthetic ranging series (sine wave + noise) → RANGING, H < 0.50
- Unit: Synthetic volatile series (normal + 5σ spike) → VOLATILE
- Integration: Run on real CrudeOIL H1 March 25-31 2026 — should show TRENDING→VOLATILE transition

**Commit:** `feat(regime): rule-based regime classifier with ADX+Hurst+ATR [integration-pass]`

---

### TASK 2 — STRATEGY ROUTER (quant-dev, 30 min)
**Goal:** Create `src/trading/regime/strategy_router.py` — maps regime to allowed strategies.

```python
"""
Strategy Router

Given a regime classification, returns which strategies should run
and with what weight adjustments. This replaces the hardcoded
"run all 5 strategies and combine" logic in live_trading_service.py.
"""

class StrategyRouter:
    """
    Routes regime to strategy selection.

    Routing table:
      TRENDING:
        - momentum (weight: 0.40) — MA crossover captures trend
        - breakout (weight: 0.35) — breakout confirms trend strength
        - trend_following (weight: 0.25) — crude_oil_v3 multi-indicator
        - BLOCKED: value_area, mean_reversion, ml_reversal (counter-trend)

      RANGING:
        - value_area (weight: 0.45) — TPO profile is king in ranges
        - mean_reversion (weight: 0.35) — Bollinger mean reversion
        - ml_reversal (weight: 0.20) — IF model passes quality gate
        - BLOCKED: momentum, breakout (whipsaw in ranges)

      VOLATILE:
        - ALL BLOCKED — no trading during extreme volatility
        - Return HOLD with reason "volatile_regime_halt"

      UNKNOWN:
        - All strategies with equal weight (0.20 each)
        - BUT raise signal threshold to 0.75 (extra selectivity)
    """

    # Strategy pools per regime
    REGIME_STRATEGIES = {
        MarketRegime.TRENDING: {
            "momentum": 0.40,
            "breakout": 0.35,
            "trend_following": 0.25,
        },
        MarketRegime.RANGING: {
            "value_area": 0.45,
            "mean_reversion": 0.35,
            "ml_reversal": 0.20,
        },
        MarketRegime.VOLATILE: {},  # Empty = no trading
        MarketRegime.UNKNOWN: {
            "momentum": 0.20,
            "value_area": 0.20,
            "mean_reversion": 0.20,
            "breakout": 0.20,
            "ml_reversal": 0.20,
        },
    }

    def get_strategy_config(self, regime: MarketRegime) -> Dict:
        """
        Returns:
          {
            "strategies": {"name": weight, ...},
            "signal_threshold": float,
            "allow_trading": bool,
            "reason": str
          }
        """
```

**Integration into live_trading_service.py:**

Replace the current `_generate_signal` method. Instead of running all 5 strategies blindly:

```python
# In _process_symbol, BEFORE signal generation:
regime, regime_meta = self._regime_classifier.classify(candles_raw)

logger.info("regime_classified", symbol=symbol, regime=regime.value,
            adx=regime_meta.get("adx"), hurst=regime_meta.get("hurst"),
            atr_ratio=regime_meta.get("atr_ratio"))

# Get strategy config for this regime
config = self._strategy_router.get_strategy_config(regime)

if not config["allow_trading"]:
    logger.info("regime_halt", symbol=symbol, regime=regime.value, reason=config["reason"])
    return

# Run ONLY the strategies allowed for this regime, with regime-specific weights
signals = {}
for strategy_name, weight in config["strategies"].items():
    signal = self._run_strategy(strategy_name, candles_raw, symbol)
    if signal is not None:
        signals[strategy_name] = signal

# Combine with regime-specific weights (replaces _combine_signals)
combined = self._combine_signals_weighted(signals, config["strategies"])

# Use regime-specific threshold
threshold = config["signal_threshold"]
if abs(combined["score"]) < threshold or combined["confidence"] < threshold:
    return
```

**Also remove the old `_combine_signals` function** and replace with `_combine_signals_weighted` that takes the weight dict from the router. Keep the agreement-weighted logic from the 8-failure fix (sqrt(conf) dampening, ML disagreement check) but apply it to whichever strategies the router selected.

**Tests:**
- Unit: TRENDING regime → only momentum/breakout/trend_following returned
- Unit: RANGING regime → only value_area/mean_reversion/ml_reversal returned
- Unit: VOLATILE regime → allow_trading=False
- Integration: Feed real CrudeOIL rally candles → TRENDING → verify Value Area NOT called

**Commit:** `feat(strategy-router): regime-aware strategy selection replaces blind combination [integration-pass]`

---

### TASK 3 — CROSS-ASSET CONFIRMATION (risk-eng, 30 min)
**Goal:** Create `src/trading/filters/cross_asset_filter.py` — uses correlation between related instruments to confirm or reject signals.

```python
"""
Cross-Asset Confirmation Filter

Before placing a trade on CrudeOIL, checks whether related assets
(BRENT_OIL, USA500) confirm the signal.

Logic:
  - CrudeOIL and BRENT_OIL should move in the same direction (0.85+ correlation)
    → If CrudeOIL says BUY but BRENT is falling: REJECT
  - CrudeOIL and USA500 have complex relationship:
    → Both falling = demand destruction (stronger SELL signal)
    → Oil up + Equity down = supply shock (strong OIL BUY)
    → Both rising = risk-on (moderate BUY)
    → Oil down + Equity up = deflationary (moderate OIL SELL)

For GBPJPY:
  - Check against USA500 (risk sentiment proxy)
  - GBPJPY rises with risk-on, falls with risk-off

Confirmation score: -1.0 (strong reject) to +1.0 (strong confirm)
Signal passes if confirmation > -0.3 (mild disagreement allowed)
"""

class CrossAssetFilter:
    def __init__(self):
        self._asset_groups = {
            "CrudeOIL": {
                "confirm": ["BRENT_OIL"],      # Must agree
                "context": ["USA500"],           # Provides context
            },
            "BRENT_OIL": {
                "confirm": ["CrudeOIL"],
                "context": ["USA500"],
            },
            "USA500": {
                "confirm": [],
                "context": ["CrudeOIL", "BRENT_OIL"],
            },
            "GBPJPY": {
                "confirm": [],
                "context": ["USA500"],
            },
        }

    async def check_confirmation(
        self,
        symbol: str,
        action: str,
        lookback_bars: int = 10,
    ) -> Tuple[float, str]:
        """
        Check cross-asset confirmation for a proposed trade.

        Fetches latest H1 candles for related symbols from DB.
        Computes short-term returns and checks directional agreement.

        Returns:
            (confirmation_score, reason_string)
            Score > 0: confirming. Score < 0: rejecting.
            Trade passes if score > -0.3
        """

    def _short_term_direction(self, prices: List[Dict], bars: int = 10) -> float:
        """
        Returns directional signal from -1 to +1 based on last N bars.
        Uses ROC + MA alignment, not just close-to-close.
        """
```

**Integration into `live_trading_service.py`:**
After regime classification and signal generation, BEFORE risk validation:

```python
# Cross-asset confirmation
if action != "HOLD":
    confirmation, reason = await self._cross_asset_filter.check_confirmation(symbol, action)
    logger.info("cross_asset_check", symbol=symbol, action=action,
                confirmation=round(confirmation, 3), reason=reason)
    if confirmation < -0.3:
        logger.info("cross_asset_rejected", symbol=symbol, action=action, reason=reason)
        return
```

**Tests:**
- Unit: CrudeOIL BUY + BRENT rising → confirmation > 0
- Unit: CrudeOIL BUY + BRENT falling → confirmation < -0.3 → rejected
- Unit: CrudeOIL SELL + USA500 also falling → stronger confirmation (demand destruction)
- Integration: Feed real candle data from April 1 06:00 UTC (oil crash + equity drop) → verify SELL would be confirmed

**Commit:** `feat(cross-asset): BRENT/USA500 confirmation filter for CrudeOIL signals [integration-pass]`

---

### TASK 4 — VOLATILITY-ADJUSTED POSITION SIZING (risk-eng, 20 min)
**Goal:** Fix the structural over-leverage problem at $293.

**File:** `src/trading/risk/tiered_position_sizer.py`

The current sizer computes lots as `risk_amount / (2 * ATR * contract_size)`. At $293 with 5% tier, that's $14.67 / ($3.00 * 1000) = 0.0049 lots → rounds to 0.01. But the actual risk at 0.01 lots with $3 stop is $30 (10.2% of account).

**Fix: Add honest risk disclosure and adaptive stop distance.**

```python
def calculate_lot_size(self, confidence, account_balance, symbol, atr,
                       existing_lots=0.0, recent_loss_count=0):
    """Enhanced position sizing with honest risk assessment."""

    # ... existing tier logic ...

    # Calculate ACTUAL risk at minimum lot
    contract_size = CONTRACT_SIZES.get(symbol, 1000)
    stop_distance = 2.0 * atr
    min_lot_risk = stop_distance * contract_size * MIN_LOTS
    actual_risk_pct = min_lot_risk / account_balance if account_balance > 0 else 1.0

    # If min lot exceeds 5% account risk, tighten the stop
    if actual_risk_pct > 0.05:
        # Option 1: Reduce stop distance to cap risk at 5%
        max_stop = (0.05 * account_balance) / (contract_size * MIN_LOTS)
        # But don't go below 1.0 × ATR (too tight = stop hunted)
        if max_stop >= 1.0 * atr:
            adjusted_stop = max_stop
            logger.info("stop_tightened_for_risk", symbol=symbol,
                       original_stop=round(stop_distance, 4),
                       adjusted_stop=round(adjusted_stop, 4),
                       risk_pct=round(adjusted_stop * contract_size * MIN_LOTS / account_balance, 4))
            # Store for caller to use
            self._last_adjusted_stop = adjusted_stop
            return MIN_LOTS
        else:
            # Option 2: Stop would be too tight — skip this trade entirely
            logger.warning("account_too_small_for_symbol", symbol=symbol,
                          min_risk_pct=round(actual_risk_pct, 4),
                          account_balance=round(account_balance, 2))
            return 0.0  # Can't trade this symbol safely

    # ... rest of existing logic ...
```

**Also update `_process_symbol` in live_trading_service.py to use adjusted stop:**
```python
# After _validate_signal returns approved:
if hasattr(sizer, '_last_adjusted_stop') and sizer._last_adjusted_stop:
    stop_distance = sizer._last_adjusted_stop
    tp_distance = stop_distance * 1.5  # Tighter R:R when stop is adjusted
    sizer._last_adjusted_stop = None
else:
    stop_distance = 2.0 * atr
    tp_distance = 3.0 * atr
```

This means:
- At $293, CrudeOIL with ATR=$1.50: max stop = $14.67/($1000*0.01) = $1.467 ≈ 1×ATR → trades allowed with tight stops
- At $293, if ATR spikes to $3.00: max stop = $14.67/($1000*0.01) = $1.467 < 1×ATR → trade BLOCKED (too volatile for account size)
- At $500: max stop = $25/($1000*0.01) = $2.50 = 1.67×ATR → comfortable

**Commit:** `fix(sizing): volatility-adjusted stops, block when account too small for symbol [integration-pass]`

---

### TASK 5 — RETRAIN XGBOOST WITH REGIME FEATURES (quant-dev, 45 min, PARALLEL)
**Goal:** Retrain the reversal model with 3 critical additions: regime label, cross-asset features, and recent price data.

**Run this in a worktree — it's parallel to Tasks 1-4.**

**Step 1: Add regime feature to training data.**
In `src/ml/features/reversal_features.py`, add to `compute_features_from_ohlcv`:
```python
# Regime features (new)
# Hurst exponent (rolling 50-bar window)
hurst_values = []
for i in range(len(df)):
    if i < 50:
        hurst_values.append(0.5)  # Default
    else:
        window = closes[i-50:i]
        hurst_values.append(_compute_hurst(window))
df['hurst_exponent'] = hurst_values

# ADX (already have code from trend_filter.py — reuse)
df['adx_14'] = _compute_adx_series(highs, lows, closes, period=14)

# ATR ratio (current ATR / 50-bar SMA of ATR)
atr_sma = df['atr'].rolling(50).mean()
df['atr_ratio'] = df['atr'] / atr_sma.replace(0, np.nan)
```

**Step 2: Retrain on extended data range.**
Training data: All CrudeOIL H1 candles from Jan 2024 → Apr 2026 (includes the $65-85 AND $93-106 ranges).

```bash
# Inside Docker:
docker exec -it risetrader-api python3 -m src.ml.training.train_reversal_classifier \
    --symbol CrudeOIL \
    --timeframe H1 \
    --start-date 2024-01-01 \
    --model-type xgboost \
    --config conservative
```

**Step 3: Save training stats for drift monitor.**
After training, dump feature means/stds to `models/reversal_classifier/CrudeOIL_H1/training_stats.json`.

**Step 4: Evaluate and gate.**
After training, check `metadata.json`:
- `reversal_f1 >= 0.30` → proceed to paper testing
- `peak_f1 >= 0.20` AND `valley_f1 >= 0.20` → balanced model
- If either fails → model stays gated, do NOT deploy

**Also train BRENT_OIL and USA500 models** if CrudeOIL succeeds:
```bash
for SYM in BRENT_OIL USA500 GBPJPY; do
    docker exec risetrader-api python3 -m src.ml.training.train_reversal_classifier \
        --symbol $SYM --timeframe H1 --start-date 2024-01-01 --model-type xgboost --config conservative
done
```

**Commit:** `feat(ml): retrain XGBoost with Hurst+ADX regime features on 2024-2026 data [integration-pass]`

---

### TASK 6 — PAPER TRADING VALIDATION MODE (risk-eng, 30 min)
**Goal:** Create a validation mode that runs the full pipeline but tracks paper results, requiring 50 profitable signals before live activation.

**File:** `src/services/paper_validation_service.py`

```python
"""
Paper Trading Validation Service

Runs alongside the live service but with dry_run=True.
Tracks all signals, their outcomes, and accumulates statistics.

When the system generates a signal:
  1. Log the signal with entry price, stop, TP
  2. On each subsequent cycle, check if stop or TP was hit
  3. Track win rate, average R:R, profit factor

Activation criteria (ALL must be met):
  - Minimum 50 resolved signals (hit TP or SL)
  - Win rate >= 55%
  - Profit factor >= 1.3 (gross profit / gross loss)
  - Max consecutive losses <= 5
  - Regime classifier shows at least 3 different regime transitions
    (proves it's not just working in one market condition)

When criteria met:
  - Log "PAPER_VALIDATION_PASSED" with full statistics
  - Set flag in Redis/DB that live trading can activate
  - Notify via structured log (future: webhook/email)
"""

class PaperValidationService:
    def __init__(self):
        self._open_paper_trades: Dict[str, Dict] = {}  # symbol → trade info
        self._resolved_trades: List[Dict] = []
        self._regime_transitions: int = 0
        self._last_regime: Optional[MarketRegime] = None

    async def record_signal(self, symbol, action, entry_price, stop_loss, take_profit, regime):
        """Record a new paper signal to track."""

    async def check_outcomes(self, symbol, current_price):
        """Check if any open paper trades hit TP or SL."""

    def get_validation_status(self) -> Dict:
        """Returns current validation statistics + whether criteria are met."""
```

**Integration:** In `live_trading_service.py`, when `self.dry_run` is True (or a new `PAPER_VALIDATION_MODE` env var), feed all signals to this service instead of the real execution path. The validation service passively monitors outcomes using real price data.

**Tests:**
- Unit: 50 trades with 60% win rate, PF=1.5 → PASSED
- Unit: 50 trades with 50% win rate → FAILED (win rate < 55%)
- Unit: 30 trades with 80% win rate → FAILED (< 50 signals)

**Commit:** `feat(paper-validation): 50-signal validation gate before live trading activation [integration-pass]`

---

### TASK 7 — WIRE IT ALL TOGETHER + E2E TEST (mcp-verifier, 30 min)

**After Tasks 1-6 complete, verify the full pipeline:**

1. **Regime classification E2E:**
```python
# Fetch CrudeOIL H1 from March 25-April 1 2026
# Run regime_classifier.classify() on sliding 60-bar windows
# Expected: TRENDING (Mar 25-27), VOLATILE (Mar 31 16:00 crash candle), RANGING (Apr 1)
# Log full transition timeline
```

2. **Strategy routing E2E:**
```python
# During TRENDING regime: verify only momentum/breakout run
# During RANGING regime: verify only value_area/mean_reversion run
# During VOLATILE: verify HALT — zero signals emitted
```

3. **Cross-asset E2E:**
```python
# At April 1 06:00 UTC (CrudeOIL -4.21%, BRENT -4.15%, USA500 +0.41%)
# CrudeOIL SELL signal should get STRONG confirmation (both oils crashing)
# CrudeOIL BUY signal should get STRONG rejection (BRENT disagrees)
```

4. **Position sizing E2E:**
```python
# With $293 balance and ATR=$2.00:
# verify sizer returns 0.01 lots with tightened stop (not 2×ATR)
# With $293 balance and ATR=$3.50:
# verify sizer returns 0.0 lots (can't trade safely)
```

5. **Full pipeline dry run:**
```python
# Enable PAPER_VALIDATION_MODE
# Run 10 cycles on CrudeOIL
# Verify: regime → strategy selection → signal → cross-asset → sizing → paper trade logged
# Verify: zero live orders placed
```

6. **ML model quality check (if Task 5 completed):**
```python
# Load retrained CrudeOIL model
# Check metadata.json: reversal_f1 >= 0.30?
# If yes: model passes quality gate in RANGING regime
# If no: model stays gated, Value Area handles RANGING alone
```

**Commit:** `test(regime-system): E2E validation of regime-aware trading pipeline [integration-pass]`

---

### TASK 8 — DOCUMENTATION: REGIME SYSTEM ARCHITECTURE (reviewer, 15 min)

**File:** `docs/regime-aware-architecture.md`

Document:
- Regime classification rules (ADX/Hurst/ATR thresholds)
- Strategy routing table
- Cross-asset confirmation logic
- Position sizing adjustments for small accounts
- Paper validation criteria
- How to add new strategies to a regime
- How to tune regime thresholds

This is critical for the reviewer role — they need to understand the system to audit it.

**Commit:** `docs(regime): architecture documentation for regime-aware strategy system [integration-pass]`

---

## EXECUTION ORDER

```
SERIAL (must be first):
  quant-dev → Task 1 (regime classifier, 45 min) — everything depends on this

PARALLEL GROUP 1 (after Task 1):
  quant-dev → Task 2 (strategy router, 30 min)
  risk-eng  → Task 3 (cross-asset filter, 30 min)
  risk-eng  → Task 4 (volatility-adjusted sizing, 20 min)
  quant-dev → Task 5 (XGBoost retrain, 45 min) — IN WORKTREE, parallel to all

SERIAL (after Tasks 2-4):
  risk-eng  → Task 6 (paper validation service, 30 min)

VERIFICATION (after all code tasks):
  mcp-verifier → Task 7 (E2E tests, 30 min)
  reviewer     → Task 8 (documentation, 15 min)

POST-DEPLOYMENT:
  Enable PAPER_VALIDATION_MODE=true in .env
  Monitor logs for 50 signals
  When validation passes → switch to live
```

## ABSOLUTE RULES (from CLAUDE.md)
- No hardcoded ATR, ML confidence, correlation, VaR, or Kelly inputs
- All ATR from `atr_calculator.py` with real candle data
- ML models gated at F1 >= 0.30 (from 8-failure fix, still enforced)
- Anti-stop-hunt offsets on all stops (preserved)
- 3-tier testing: unit → integration → e2e
- Every commit tagged `[integration-pass]`
- File ownership: quant-dev owns strategies/regime/features, risk-eng owns sizing/filters/validation, mcp-verifier owns tests

## SUCCESS CRITERIA
After all 8 tasks complete:
1. `regime_classifier.classify()` correctly identifies TRENDING/RANGING/VOLATILE on real data
2. Strategy router blocks counter-trend strategies in TRENDING regime
3. Cross-asset filter rejects CrudeOIL trades when BRENT disagrees
4. Position sizer blocks trades when account is too small for current volatility
5. Paper validation service tracks all signals and enforces 50-signal gate
6. Zero live trades placed until paper validation passes
7. Hurst exponent correctly distinguishes trending from ranging series
8. Full pipeline runs in paper mode without errors for 10 cycles
9. If XGBoost retrained: reversal_f1 >= 0.30 (or model stays gated)

## WHAT THIS UNLOCKS
- **Week 1-2:** Paper validation collects 50+ signals across regime transitions
- **Week 2-3:** If validation passes, live trading activates with regime-aware routing
- **Week 3-4:** ML model deployed only in RANGING regime (where reversals make sense)
- **Month 2+:** Account grows past $500, position sizing becomes sustainable
- **Phase 3 gate:** Once USA500 2020 data is backfilled, crisis replay runs with regime context
