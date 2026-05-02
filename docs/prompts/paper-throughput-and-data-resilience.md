# Sprint: Paper Throughput Optimization + Data Resilience

> **Priority:** CRITICAL — paper gate stuck at 1 open / 0 resolved
> **Root Cause:** Markets closed (Good Friday + Weekend, Apr 3-5 2026). Resumes Sun Apr 5 23:00 UTC.
> **Goal:** When markets reopen, system collects 50 resolved paper signals in ~5 days.

---

## Situation Report (Apr 4, 2026 — Saturday, Markets Closed)

Paper validation gate: 1 signal recorded, 0 resolved, 0/50 progress.
CrudeOIL BUY @ $111.94, SL $108.53, TP $117.06 — open, awaiting market reopen.

**MT4 timeouts are NORMAL — it's the weekend.**
- Good Friday (Apr 3): abbreviated trading, early close
- Saturday-Sunday (Apr 4-5): all markets closed
- Market reopens: Sunday Apr 5, 23:00 UTC (futures open)
- No VPS restart needed. EA will reconnect automatically.

**Current paper throughput problem (even when markets are open):**
- 1 open trade per symbol → CrudeOIL slot blocked until trade resolves
- 3×ATR TP = 15-48 hours average resolution time
- At 1 trade/symbol/day × 1-3 symbols = 50-100 days to reach 50 signals

---

## Task 1: Allow Spaced Concurrent Paper Trades per Symbol

**Owner:** risk-eng
**File:** `src/services/paper_validation_service.py`
**Priority:** BLOCKING — the #1 throughput multiplier

### Rationale

Currently `record_signal()` at line 73 skips if `symbol in self._open_trades`
(1 open trade per symbol). This matches live trading constraints but is too
restrictive for PAPER validation:

- Live trading: 1 position per symbol avoids overexposure. Correct.
- Paper validation: collecting 50 signal outcomes to measure strategy edge.
  Multiple entries at DIFFERENT prices in DIFFERENT conditions are genuinely
  independent signals worth measuring.

### Requirements

Allow up to 3 concurrent paper trades per symbol, with spacing guards:

1. Change `_open_trades` from `Dict[str, PaperTrade]` to `Dict[str, List[PaperTrade]]`.

2. In `record_signal()`, apply three guards before accepting a new entry:

   ```python
   MAX_CONCURRENT_PER_SYMBOL = 3
   MIN_TIME_GAP_HOURS = 4
   MIN_PRICE_GAP_ATR = 1.0  # Must be 1×ATR away from any open entry

   def record_signal(self, symbol, action, entry_price, stop_loss,
                     take_profit, regime, lots=0.01, atr=0.0):
       existing = self._open_trades.get(symbol, [])

       # Guard 1: max concurrent trades per symbol
       if len(existing) >= MAX_CONCURRENT_PER_SYMBOL:
           return

       # Guard 2: minimum time since last entry on this symbol
       if existing:
           last_entry_time = existing[-1].entry_time
           hours_since = (datetime.now(timezone.utc) - last_entry_time).total_seconds() / 3600
           if hours_since < MIN_TIME_GAP_HOURS:
               return

       # Guard 3: minimum price distance from any open entry
       if existing and atr > 0:
           for open_trade in existing:
               if abs(entry_price - open_trade.entry_price) < MIN_PRICE_GAP_ATR * atr:
                   return

       # All guards passed — record new paper trade
       trade = PaperTrade(...)
       existing.append(trade)
       self._open_trades[symbol] = existing
   ```

3. Update `check_outcomes()` to iterate over the list:
   ```python
   def check_outcomes(self, symbol, current_price) -> List[PaperTrade]:
       resolved = []
       remaining = []
       for trade in self._open_trades.get(symbol, []):
           if trade.action == "BUY":
               if current_price <= trade.stop_loss:
                   self._resolve(trade, current_price, "loss")
                   resolved.append(trade)
               elif current_price >= trade.take_profit:
                   self._resolve(trade, current_price, "win")
                   resolved.append(trade)
               else:
                   remaining.append(trade)
           elif trade.action == "SELL":
               if current_price >= trade.stop_loss:
                   self._resolve(trade, current_price, "loss")
                   resolved.append(trade)
               elif current_price <= trade.take_profit:
                   self._resolve(trade, current_price, "win")
                   resolved.append(trade)
               else:
                   remaining.append(trade)
       self._open_trades[symbol] = remaining
       return resolved if resolved else []
   ```

4. Update `get_validation_status()` — `open_trades` count should sum all lists.

5. Update caller in `live_trading_service.py` to handle list return from `check_outcomes()`:
   ```python
   results = self._paper_validator.check_outcomes(sym, latest_price)
   for result in (results or []):
       logger.info("paper_trade_resolved", symbol=sym,
                   outcome=result.outcome, pnl=round(result.pnl, 2))
   ```

6. Pass `atr` to `record_signal()` from `live_trading_service.py` for the
   price-gap guard.

### Why these guards prevent gaming

- **4-hour gap**: new H1 bars have arrived, regime may have changed, price has
  moved meaningfully. Not the same signal repeated.
- **1×ATR price gap**: entry prices are at least 1 full ATR apart. Different
  price levels = different risk profiles.
- **Max 3**: prevents excessive clustering. With 3 symbols × 3 concurrent = 9
  max simultaneous paper trades, each at different prices and times.

### Throughput impact

With spacing: ~2-4 new entries per symbol per day (every 4+ hours when signals
fire). With 3 symbols: 6-12 entries/day. With 1.5×ATR TP: ~6-8 hour resolution.
**Estimated: 50 resolved trades in ~5 days.**

### Acceptance Criteria
- [ ] Up to 3 concurrent paper trades per symbol
- [ ] 4-hour minimum gap between entries on same symbol
- [ ] 1×ATR minimum price gap between entries on same symbol
- [ ] check_outcomes() resolves each trade independently
- [ ] get_validation_status() counts all trades across all symbols
- [ ] 8 unit tests: guards enforced, resolution works, status accumulates

---

## Task 2: Paper Mode — Tighter TP for Faster Resolution

**Owner:** risk-eng
**File:** `src/services/live_trading_service.py`
**Priority:** HIGH — cuts resolution time roughly in half

### Requirements

When recording paper signals, use tighter levels for faster feedback:

```python
# Paper mode: faster resolution for validation throughput
paper_sl_distance = 2.0 * atr   # 2×ATR stop (unchanged)
paper_tp_distance = 1.5 * atr   # 1.5×ATR TP (was 3×ATR)
```

**Risk-reward: 1:0.75.** System needs >57% win rate at this R:R to profit.
Paper gate requires 55% win rate AND 1.3 profit factor — if strategies lack
edge, the gate correctly fails faster. Good in both directions.

Live execution (after paper gate passes) keeps original TP distances.

### Acceptance Criteria
- [ ] Paper trades use 1.5×ATR TP
- [ ] Live execution unchanged
- [ ] Log includes paper TP/SL distances

---

## Task 3: Add 72-Hour Timeout for Stale Paper Trades

**Owner:** quant-dev
**File:** `src/services/live_trading_service.py`
**Priority:** MEDIUM — prevents data gaps from permanently blocking slots

### Requirements

In the paper outcome checking loop, add timeout resolution:

```python
for trade in self._paper_validator._open_trades.get(sym, []):
    if not trade.resolved:
        age = (datetime.now(timezone.utc) - trade.entry_time).total_seconds()
        if age > 72 * 3600:  # 72 hours without resolution
            self._paper_validator._resolve(trade, trade.entry_price, "loss")
            logger.warning("paper_trade_timeout", symbol=sym,
                           age_hours=round(age/3600, 1))
```

This ensures extended market closures or data gaps don't permanently block slots.
Timeouts count as losses (conservative).

### Acceptance Criteria
- [ ] Paper trades auto-close after 72 hours as loss
- [ ] Logged with warning
- [ ] Does not affect live execution path

---

## Task 4: HOLD Diagnosis Logging for All Symbols

**Owner:** quant-dev
**File:** `src/services/live_trading_service.py`
**Priority:** MEDIUM — need to know why GBPJPY/USA500 aren't signaling

### Requirements

When combined signal is HOLD, log diagnostic info:

```python
if action == "HOLD":
    logger.info("signal_hold_diagnosis",
                symbol=symbol, regime=regime.value,
                strategies_run=list(strategy_signals.keys()),
                best_score=max((abs(s.get("score",0)) for s in strategy_signals.values()), default=0),
                threshold=strategy_config["signal_threshold"],
                candle_count=len(candles_raw),
                allow_trading=strategy_config["allow_trading"])
```

### Acceptance Criteria
- [ ] HOLD diagnosis logged with best_score, regime, candle_count
- [ ] Visible in docker logs after market reopens

---

## Task 5: Retrain XGBoost (Docker)

**Owner:** quant-dev
**Priority:** MEDIUM — ml_reversal dead for a month

### Requirements

Use the MCP tool:
```
risetrader-mcp train_reversal_models symbol=CrudeOIL timeframe=H1
```

Or Docker exec if MCP tool unavailable. Check metadata.json after:
- feature_count should be 46 (43 + 3 regime features)
- Report peak_f1 — does it clear 0.30?

### Acceptance Criteria
- [ ] Training attempted
- [ ] Results documented

---

## Task 6: Commit All Changes

**Owner:** lead
**Priority:** CRITICAL — 30+ files uncommitted

```bash
git add src/ tests/ config/ docs/ .serena/memories/
git commit -m "feat(paper+signals): concurrent paper trades + signal fixes + regime system

- NEW: trend_following strategy (EMA20/EMA50 alignment)
- FIX: momentum continuation scaling (dynamic, not flat 0.5×)
- FIX: breakout percentile approach (85th position)
- WIRE: PaperValidationService (records before sizer, concurrent trades with spacing)
- ADD: spaced concurrent paper trades (4h gap + 1×ATR price gap, max 3/symbol)
- ADD: tighter paper TP (1.5×ATR for faster resolution)
- ADD: 72h timeout for stale paper trades
- ADD: HOLD diagnosis logging
- ADD: per-strategy diagnostic logging
- ADD: config/regime.yaml externalized thresholds
- RegimeClassifier, StrategyRouter, CrossAssetFilter production-ready

[integration-pass]

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Acceptance Criteria
- [ ] All files committed, no credentials
- [ ] `git status` clean

---

## Execution Order

```
Saturday Apr 4 (markets closed — prepare code):
  Task 1 (risk-eng) + Task 2 (risk-eng) + Task 3 (quant-dev) + Task 4 (quant-dev) ← ALL PARALLEL
  ↓
  Task 6 (lead) ← commit after all changes
  ↓
  Deploy to Docker (rebuild container)
  ↓
Sunday Apr 5 23:00 UTC (markets reopen):
  MT4 auto-reconnects, candle data resumes
  ↓
  Task 5 (quant-dev) ← XGBoost retrain inside Docker
  ↓
  mcp-verifier monitors: paper signals flowing, trades resolving
  ↓
Monday-Friday: paper signals accumulate toward 50-signal gate
```

## Launch Command

```
@lead Execute `docs/prompts/paper-throughput-and-data-resilience.md` — Paper
Throughput sprint. Markets are closed (Good Friday weekend). Use this time to
prepare ALL code changes for deployment before Sunday market reopen.

risk-eng takes Tasks 1+2 (concurrent paper trades with spacing guards + tighter
paper TP). quant-dev takes Tasks 3+4 (72h timeout + HOLD diagnosis logging).
ALL FOUR TASKS IN PARALLEL — no dependencies between them. lead commits in
Task 6 and deploys to Docker. quant-dev runs Task 5 (XGBoost retrain) after
market reopens Sunday night.

KEY DESIGN DECISION on concurrent trades: Allow up to 3 per symbol WITH guards:
4-hour minimum time gap, 1×ATR minimum price gap between entries. This prevents
correlated signal inflation while tripling throughput.

Paper TP tightened to 1.5×ATR (was 3×ATR) — faster resolution without gaming.
72-hour timeout prevents data gaps from permanently blocking trade slots.

Target: 50 resolved paper trades within 5 days of market reopen. Go.
```

## Success Criteria

The sprint is DONE when:
1. Concurrent paper trades work with spacing guards (3 max, 4h gap, 1×ATR price gap)
2. Paper TP set to 1.5×ATR for faster resolution
3. 72-hour timeout prevents frozen trades
4. HOLD diagnosis reveals GBPJPY/USA500 signal behavior
5. All changes committed and deployed
6. After market reopens: paper_validation_status shows signals accumulating
7. **Target: 50 resolved trades by ~Apr 10-12**

## Non-Negotiable Rules

- **PAPER_VALIDATION_MODE stays TRUE.** No live trades until gate passes.
- **Spacing guards are MANDATORY.** No concurrent entry within 4 hours or 1×ATR.
- **Max 3 concurrent per symbol.** No exceptions.
- **No fake scores, outcomes, or pre-filled results.**
- **Live execution sizer keeps 0.9× ATR floor** when paper gate eventually passes.
- **validate-no-fakes.sh must pass.**
