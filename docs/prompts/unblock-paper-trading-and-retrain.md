# Sprint: Unblock Paper Trading + Retrain XGBoost + Commit

> **Priority:** CRITICAL — strategies produce score 0.92 but sizer blocks every trade
> **Root Cause:** $293 account + CrudeOIL ATR $1.71 = stop at 0.86×ATR < 0.90× floor
> **Goal:** Start collecting paper signals NOW. 50-signal gate can't pass at 0/50.

---

## Situation Report (Apr 4, 2026)

Strategy fixes CONFIRMED WORKING on live CrudeOIL data:
- trend_following: 0.97 score, 0.90 confidence (NEW — didn't exist before)
- momentum: 0.90 score, 0.70 confidence (FIXED — was 0.35 with flat dampening)
- breakout: 0.90 score, 0.65 confidence (FIXED — was 0.00 with 99.5% proximity)
- Combined: 0.92 score → PASSES 0.60 threshold
- Cross-asset filter: PASSES (BRENT neutral, USA500 neutral)
- Trend filter: PASSES (regime=TRENDING, signal=BUY, aligned)

**Blocked at sizer:** ATR=$1.71, max_stop=$1.467, ratio=0.86×ATR < 0.90× floor.

**Other symbols:**
- GBPJPY: max_stop/ATR ≈ 29× → easily tradeable at $293
- USA500: max_stop/ATR ≈ 1.96× → easily tradeable at $293
- Only CrudeOIL is blocked (high ATR + 1000 contract size)

**XGBoost model:** DEAD. Training date 2026-03-06, peak_f1=0.089, blocked by 0.30 gate.
Feature code ready (46 features) but training never ran.

**MT4:** Timing out on account_info and positions queries. EA may need restart.
H1 candle data was flowing through Apr 2 but may have stopped.

---

## Task 1: Lower ATR Floor from 0.9× to 0.8× for Paper Mode Only

**Owner:** risk-eng
**File:** `src/trading/risk/tiered_position_sizer.py`
**Priority:** BLOCKING — zero paper signals without this

### Rationale

The 0.9× ATR floor exists to prevent stop-hunting. Valid concern for LIVE trading.
But in PAPER mode, the purpose is to validate signal quality — not to protect money.
A stop at 0.86× ATR is mathematically legitimate: risk is capped at 5% of account
($14.67), the stop is only 4% tighter than "ideal" 0.9× ATR placement.

### Requirements

1. Accept an optional `paper_mode: bool = False` parameter in `calculate_lot_size()`.

2. When `paper_mode=True`:
   - Lower ATR floor from 0.9 to 0.75 (allows stops down to 0.75× ATR)
   - This is for PAPER SIGNAL COLLECTION ONLY — not for live execution
   - Log: `"paper_mode_relaxed_atr_floor"` when this path is taken

3. When `paper_mode=False`:
   - Keep existing 0.9× floor unchanged (protects real money)

4. In `live_trading_service.py`, pass `paper_mode=self._paper_mode` to
   `calculate_lot_size()` so the sizer knows the context.

5. **ALTERNATIVE (simpler):** Instead of modifying the sizer, have the paper
   validation service record signals BEFORE the sizer gate. The paper service
   tracks theoretical outcomes — it doesn't need real lot sizes. This is
   actually the cleaner approach:

   In `_process_symbol()`, move the paper signal recording to BEFORE the sizer
   call. The signal has already passed regime + trend + cross-asset + cooldown
   filters at this point. Record it with a theoretical 0.01 lot size:

   ```python
   # BEFORE position sizing — record paper signal with theoretical lots
   if self._paper_validator and not self._paper_validator.get_validation_status()["criteria_met"]:
       # Use 2×ATR stop, 3×ATR TP for paper tracking (standard distances)
       paper_stop = current_price - (2 * atr) if action == "BUY" else current_price + (2 * atr)
       paper_tp = current_price + (3 * atr) if action == "BUY" else current_price - (3 * atr)
       self._paper_validator.record_signal(
           symbol=symbol, action=action,
           entry_price=current_price,
           stop_loss=paper_stop, take_profit=paper_tp,
           regime=regime.value, lots=0.01,
       )
       logger.info("paper_signal_recorded", symbol=symbol, action=action,
                    price=round(current_price, 5), regime=str(regime),
                    atr=round(atr, 5), stop_distance=round(2*atr, 5))
       return  # Skip real execution
   ```

   This way paper signals are collected based on SIGNAL QUALITY (regime +
   strategy + filters), not POSITION SIZING (which is account-dependent).
   The paper gate validates strategy edge, not account size.

### Acceptance Criteria
- [ ] Paper signals recorded when signal passes regime + strategy + filter checks
- [ ] Sizer is NOT the bottleneck for paper signal collection
- [ ] CrudeOIL BUY signal at current ATR=$1.71 produces a paper trade
- [ ] GBPJPY and USA500 signals also recorded when strategies fire
- [ ] Paper validation status shows total > 0 within one H1 bar cycle
- [ ] Live execution path (when paper gate passes) still uses full sizer with 0.9× floor

---

## Task 2: Retrain XGBoost Inside Docker

**Owner:** quant-dev
**Priority:** HIGH — ml_reversal dead at 0.089 F1 for a month

### Context

`src/ml/features/reversal_features.py` already computes 3 new regime features:
- `regime_adx` — ADX(14) continuous
- `regime_hurst` — Hurst via R/S, rolling 50-bar
- `regime_atr_ratio` — ATR(14) / SMA(ATR, 50)

The training script at `src/ml/training/train_reversal_classifier.py` should
pick these up automatically from `compute_features_from_ohlcv()`.

### Requirements

1. Check if the MCP tool `train_reversal_models` exists and can be called:
   ```
   Use risetrader-mcp train_reversal_models tool
   ```
   If the MCP tool works, use it. If not, fall back to Docker exec.

2. Training parameters:
   - Symbol: CrudeOIL
   - Timeframe: H1
   - Data range: 2024-01-01 to 2026-03-31
   - ZigZag labeling: depth=12, deviation=5, backstep=3

3. After training, read `models/reversal_classifier/CrudeOIL_H1/metadata.json`:
   - Verify feature_count = 46 (43 + 3 regime)
   - Verify training_date is today
   - Report peak_f1 — does it clear 0.30 gate?

4. If peak_f1 < 0.30:
   - Try with `scale_pos_weight` adjusted for class imbalance
   - Try max_depth=4 (reduce overfitting)
   - Document all attempts and results
   - Do NOT fake the F1 score

### Acceptance Criteria
- [ ] Training job executed with 46 features
- [ ] metadata.json updated with new training_date and metrics
- [ ] Feature_names.json includes regime_adx, regime_hurst, regime_atr_ratio
- [ ] If F1 >= 0.30: ml_reversal fires in RANGING regime → test with paper signal
- [ ] If F1 < 0.30: documented, model stays gated, no fakes

---

## Task 3: Verify MT4 Connectivity and Fix if Needed

**Owner:** mcp-verifier
**Priority:** HIGH — account_info and positions timing out

### Problem

`get_account_info` returns: "MT4 command timeout after 10000ms"
`get_open_positions` returns: "MT4 command timeout after 10000ms"

This suggests the MT4 EA (Expert Advisor) is not running or the ZMQ connection
is broken. H1 candle data was flowing through Apr 2 but may have stopped.

### Requirements

1. Check if new H1 candles are arriving:
   ```
   Use risetrader-mcp get_latest_candles for CrudeOIL H1, limit 3
   ```
   If latest candle time is > 2 hours old during market hours, MT4 stream is dead.

2. Check MT4 connection via the network:
   ```bash
   # From inside Docker container
   docker exec risetrader-api python3 -c "
   import zmq
   ctx = zmq.Context()
   sock = ctx.socket(zmq.REQ)
   sock.setsockopt(zmq.RCVTIMEO, 5000)
   sock.connect('tcp://192.168.0.123:5555')
   sock.send_json({'action': 'ACCOUNT'})
   print(sock.recv_json())
   "
   ```

3. If MT4 is down:
   - Check if it's a weekend/holiday (markets closed = expected timeout)
   - Check if the VPS at 192.168.0.123 is reachable
   - Document findings — do NOT try to restart MT4 without Slim's approval

4. If MT4 is up but EA is stuck:
   - The candle aggregator or sync service may need restart
   - Document the exact error for Slim to fix on the Windows VPS

### Acceptance Criteria
- [ ] MT4 connectivity status determined (up/down/weekend)
- [ ] If down: root cause identified, documented
- [ ] If up: account balance confirmed, paper trading can proceed
- [ ] Candle data flow status confirmed

---

## Task 4: Add Multi-Symbol Strategy Awareness

**Owner:** quant-dev
**File:** `src/services/live_trading_service.py`
**Priority:** MEDIUM — GBPJPY and USA500 may be producing HOLD signals too

### Problem

The three strategies (momentum, trend_following, breakout) were designed and
tested on CrudeOIL price patterns. GBPJPY (forex) and USA500 (index) have
different price structures:

- GBPJPY: moves in pips (190.50, 190.75), much tighter ranges relative to price
- USA500: moves in points (6600, 6610), very different volatility profile

The breakout `position >= 0.85` threshold and momentum continuation scaling
may need different parameters per asset class. But first: check if they're
actually generating signals or also returning HOLD.

### Requirements

1. Add logging to track signal generation per symbol across multiple cycles:
   ```python
   logger.info("symbol_signal_summary",
               symbol=symbol, regime=regime.value,
               signal_action=action, signal_score=round(score, 4),
               strategies_active=list(strategy_signals.keys()),
               any_nonzero=any(abs(s.get("score",0)) > 0.01 for s in strategy_signals.values()))
   ```

2. After 3-5 cycles with MT4 live, review logs:
   - Which symbols produce non-HOLD signals?
   - What regime is each symbol classified as?
   - Are GBPJPY/USA500 strategies actually running?

3. If GBPJPY/USA500 also stuck at HOLD:
   - Check if 300 H1 candles exist for these symbols
   - Check if regime classification works (may lack data for Hurst/ADX)
   - Report findings — do NOT change thresholds without evidence

### Acceptance Criteria
- [ ] Per-symbol signal summary logged
- [ ] After 5+ cycles: documented which symbols generate signals
- [ ] If symbols stuck at HOLD: root cause identified per symbol

---

## Task 5: Commit All Uncommitted Changes

**Owner:** lead
**Priority:** CRITICAL — 30+ files at risk

### Requirements

Commit everything in a single, well-documented commit:

```bash
git add src/ tests/ config/ docs/prompts/ .serena/memories/
git commit -m "feat(signals+paper): strategy fixes + paper gate + regime system [integration-pass]

- NEW: trend_following strategy (EMA20/EMA50 alignment, fires during sustained trends)
- FIX: momentum continuation scaling (was flat 0.5×, now scales with MA separation)
- FIX: breakout percentile approach (was 99.5% proximity, now 85th percentile position)
- WIRE: PaperValidationService into live loop (50-signal gate before live execution)
- ADD: per-strategy diagnostic logging (strategy_raw_output, signal_combine_result)
- ADD: config/regime.yaml externalized thresholds
- ADD: 1100-line integration test suite
- RegimeClassifier, StrategyRouter, CrossAssetFilter all production-ready

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

Do NOT include .env or any files with credentials.

### Acceptance Criteria
- [ ] All code committed
- [ ] Commit message describes all changes
- [ ] No credentials in commit
- [ ] `git status` shows clean working tree

---

## Task 6: Paper Signal Throughput Analysis

**Owner:** reviewer
**Priority:** MEDIUM — need to estimate time to 50 signals

### Requirements

After Task 1 deploys and paper signals start flowing:

1. Wait 24 hours and count paper_signal_recorded entries in logs
2. Calculate:
   - Signals per day per symbol
   - Estimated days to reach 50 resolved signals
   - Signal distribution across regimes (TRENDING vs RANGING vs UNKNOWN)
3. If throughput < 5 signals/day:
   - The H1 timeframe + staleness check means max 24 evaluations/day
   - Consider: should paper mode also evaluate on M15 for faster signal collection?
   - Or: should the paper signal threshold be lower than live threshold?
   - Document recommendation but do NOT change without lead approval

### Acceptance Criteria
- [ ] 24-hour signal throughput measured
- [ ] Time-to-50 estimated
- [ ] Recommendation documented if throughput too low

---

## Execution Order

```
Task 1 (risk-eng) ←── BLOCKING, do first. Unblocks paper signal collection.
  ↓
Task 3 (mcp-verifier) ←── PARALLEL with Task 1. Check MT4 connectivity.
  ↓
Deploy to Docker (rebuild container with Tasks 1 changes)
  ↓
Task 2 (quant-dev) ←── Inside Docker after deploy. Retrain XGBoost.
  ↓
Task 4 (quant-dev) ←── After first few cycles with paper signals flowing
  ↓
Task 5 (lead) ←── After all code changes confirmed working
  ↓
Task 6 (reviewer) ←── 24 hours after Task 1 deploy
```

## Launch Command

```
@lead Execute `docs/prompts/unblock-paper-trading-and-retrain.md` — Unblock
Paper Trading sprint. The system generates score 0.92 BUY signals on CrudeOIL
but the sizer blocks because $293 account can't afford 0.9×ATR stop at current
volatility.

Task 1 (risk-eng) is BLOCKING: move paper signal recording BEFORE the sizer
gate — paper mode validates signal quality, not account size. Use 2×ATR stop
and 3×ATR TP for paper tracking. mcp-verifier takes Task 3 IN PARALLEL: check
why MT4 is timing out on account_info. After deploy, quant-dev runs Task 2
(XGBoost retrain via MCP tool or Docker exec). quant-dev then does Task 4
(multi-symbol signal diagnostics). lead commits in Task 5. reviewer measures
paper signal throughput in Task 6 after 24 hours.

PAPER_VALIDATION_MODE stays TRUE. We need paper signals flowing NOW. Go.
```

## Success Criteria

The sprint is DONE when:
1. Paper signals are being recorded (total > 0, rising)
2. CrudeOIL BUY signals at current conditions produce paper trades
3. XGBoost retrained (or documented as sub-gate)
4. MT4 connectivity verified or issue documented
5. All changes committed
6. 24-hour signal throughput measured and time-to-50 estimated

## Non-Negotiable Rules

- **PAPER_VALIDATION_MODE stays TRUE.** No live trades until 50-signal gate passes.
- **Live execution sizer keeps 0.9× ATR floor.** Only paper signal collection is relaxed.
- **No fake scores, no fake F1, no hardcoded values.**
- **validate-no-fakes.sh must pass** on every edit.
- **Every commit tagged `[integration-pass]`** after mcp-verifier confirms.
