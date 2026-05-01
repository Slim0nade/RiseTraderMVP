# 2026-04-29 — MT4 Broker Premium Analysis + Corrected Training/Execution Architecture

**SUPERSEDES the "Phase 2/5 = drop dirty data" verdict in `2026-04-28-data-quality-deep-audit-and-source-strategy.md`.** That earlier conclusion was wrong. The data shows broker premium dynamics, not corrupt data.

## Key context (NEW)

**Broker is ForTrade.** ForTrade is a CFD broker. Their MT4 prices:
- Move in the same direction as the underlying instrument (NYMEX/CME).
- **Adjust at least once a month** — broker resets/changes their pricing rule periodically.
- **Consistently carry a structural offset (premium)** vs the real market price.

This is normal CFD-broker behavior, not corruption.

## Statistical proof that Phase 2 / Phase 5 are STRUCTURAL PREMIUMS, not bad data

Five tests on `data/quality/mt4_daily.csv`:

| Test | Phase 2 (Apr-Jun 2025) | Phase 5 (Mar-Apr 2026) | Implication |
|---|---|---|---|
| Mean offset (BC − MT4) | **−$1.96** | **−$4.40** | MT4 systematically higher |
| Mean % offset | **+3.02%** | **+4.57%** | Scales as % of price → premium-like |
| Regression r² (offset vs price level) | **0.70** | **0.57** | Strong linear scaling = consistent rule |
| Lag-1 autocorrelation | **+0.79** | **+0.57** | Smooth day-to-day drift, not random noise |
| Per-minute std (intraday) | 0.17 | **0.51** | P5 had broker tick-lag during volatility |

Compared to "clean" phases:

| Phase | Mean % | Lag-1 autocorr | Intraday std | Verdict |
|---|---:|---:|---:|---|
| P1 initial demo (2024-08 → 2025-03) | 0.00% | −0.33 | 0.030 | Tight broker tracking |
| **P2 disputed (Apr-Jun 2025)** | **+3.02%** | **+0.79** | 0.165 | **Structural ~3% premium** |
| P4 live (Nov 2025 → Feb 2026) | +0.80% | +0.06 | 0.048 | Tight tracking, ~1% spread |
| **P5 disputed (Mar-Apr 2026)** | **+4.57%** | **+0.57** | **0.508** | **~5% premium + 10× normal intraday lag during Hormuz** |
| **P6 current (Apr 19, 2026 → ...)** | **−0.16%** | n/a | **0.087** | **Cleanest phase in dataset** |

### Diagnosis

- **P2** = broker shifted pricing rule for ~2 months (possibly switched WTI→Brent reference, or added carry layer). Smooth, structural ~3% premium. Data is clean and usable.
- **P5** = broker amplified premium AND tick-lagged during Hormuz crisis. Data is structurally consistent but execution-quality data is poor.
- **P6** = current state, premium ≈ 0%. MT4 is mid-quoting NYMEX within bid-ask spread. Cleanest tracking observed.

## Corrected ML training + execution architecture

### Two prices, two purposes

| Source | Use for | Why |
|---|---|---|
| **BC (NYMEX CL*0)** | **Training the model** | Clean canonical exchange price. 16 yr depth. No broker regime shifts. |
| **MT4 (ForTrade)** | **Backtesting + executing** | What the account actually fills at. Includes premium/lag/slippage. |

### Four corrected rules

**Rule 1 — Train on BC, never on MT4.**
Models learn "what crude oil does" from canonical exchange data. Broker regime shifts don't pollute training signal.

**Rule 2 — Predict returns/direction, not absolute prices.**
Direction-based targets (`forward log-return`, `prob of breakout`, `next-bar direction`) are price-level-invariant. ForTrade can be quoting WTI / Brent / unicorn-tears+3% — directional predictions still apply.

**Rule 3 — Backtest on MT4 with realistic slippage.**
After training, run strategy through MT4's actual historical prices to estimate live P&L. Use per-day `std_overlap_diff` as slippage input — P5 had 10× normal intraday std, slippage scales accordingly.

**Rule 4 (REWRITTEN — superseding the earlier "pause when spread widens" version):**
- **a. All stops and targets anchored to BC, not MT4.** When NYMEX hits the trigger, send orders to MT4 at the corresponding broker price. Premium changes during holding period can't reverse your P&L.
- **b. Position size scales inversely to *spread volatility*** (not spread level). Use rolling 7-day stdev of `BC.close − MT4.close` as the scaling factor.
- **c. High-conviction signals override** — when BC volatility is high AND model is confident, trade BIGGER. Volatility = alpha opportunity, not stay-out condition.
- **d. Avoid holding through scheduled regime-shift moments** (month ends, contract rolls, scheduled news). Close before, reopen after if signal persists.

### The math justifying Rule 4

Per-trade expected P&L = (NYMEX_move × win_rate) − (slippage × fill_count) − (premium_drift × holding_days)

- Term 1 dominates when conviction is high → trade big.
- Term 2 always small if execution is sized correctly.
- **Term 3 is the trap:** if you anchor stops/targets to MT4 prices, premium drift during holding can amplify gains AND losses non-linearly relative to NYMEX, decoupling P&L from direction call.
- **NYMEX-anchored stops convert term 3 from "random walk" into "rounding error"** — you exit when the real market hits the level, premium dynamics fade out as fill-time slippage only.

### Worked example (the trap)

You buy ForTrade during P5: NYMEX $96, premium +$12, ForTrade $108.

| Day | NYMEX | Premium | ForTrade | Anchor exit @ NYMEX$99? |
|---|---:|---:|---:|---|
| 5 | $117 | +$12 | $129 | NYMEX target hit → close at $129 (+$21) |
| 14 | $117 | +$1 | $118 | (already closed at day 5) |
| 21 | $108 | $0 | $108 | (already closed) |

**Without** NYMEX anchoring, holding to day 21 = flat P&L on a correctly-predicted +$3 NYMEX move. **With** NYMEX anchoring, exits at the right moment.

## Forensic note on P2 cause

P2 offset has the **highest correlation with price level** (r²=0.70) and a **smooth +3% drift** for ~2 months. Signature matches a broker who switched their reference from WTI-cash to WTI-with-carry, or to Brent-priced. Brent traded $3-6 above WTI through Apr-Jun 2025 with the spread widening over the period — fits P2's drift pattern. Could be confirmed by comparing P2 dates against historical Brent-WTI spread, but not required for the architecture.

## Implications for project priorities (UPDATED)

### Don't drop Phase 2 or Phase 5 data

Earlier memory said "drop dirty phases". That's wrong. They're valuable training samples covering different volatility regimes and broker pricing behaviors. Robust models benefit from seeing them.

### What to do with MT4 phases instead

**Option A (preferred):** Add `account_phase` as **categorical metadata**, not a quality flag. Backtests can:
- Filter to specific phases for sanity tests
- Or use phase as a categorical feature
- Or use phase-specific premium correction (subtract the known offset)

**Option B:** Train models entirely on BC and use MT4 only for execution simulation. MT4 phase awareness then matters only for the execution/slippage model.

### What unlocks Rule 4 in production

**Live BC ingestion** is now a critical-path dependency. To anchor stops/targets to BC during live trading, BC must be available in near-real-time:
- Continuous (every 5-15 min) scrape of last 60 min of CL*0 / DXY / VIX / etc.
- Live computation of `BC.close − MT4.close` with rolling 7-day stdev
- Both exposed via API for the strategy layer

This becomes Priority #1 for live deployment. Without it, you can train models but can't execute them with proper anchoring.

## Concrete next-step ordering (REVISED from yesterday)

1. **Live BC ingestion service** — scrape last 60 min every 5-15 min for top symbols. ~1 hr. Unlocks Rule 4a/b.
2. **Live spread monitor** — compute and cache `BC − MT4` with rolling stdev. ~30 min. Powers Rule 4b conviction sizing.
3. **Chunked M1→M5/M15 aggregator** — still important for multi-TF backtests. ~2-3 hr.
4. **Staleness watchdog** — daily check that no feed has gone silent. ~30 min.
5. **First model: CrudeOIL 60-min directional, trained on BC, features = returns/z-scores/cross-asset spreads (DXY/VIX/BRENT/XAUUSD).**
6. **Dual backtest framework** — same strategy on BC and MT4, compare P&L. Validates that broker friction doesn't kill edge.
7. **Phase tagging metadata** (NOT deletion) — sidecar table or column.

Yesterday's memory had the gap-fill, current state, and the wrong "drop dirty MT4" conclusion. This memory corrects that and lays out the actual production architecture.

## Current state (post-backfill)

| Symbol | M1 latest | M1 bars | Status |
|---|---|---:|---|
| CrudeOIL | 2026-04-29 | 5,729,773 | ✓ deep + current, BC + MT4 |
| DXY | 2026-04-29 | 5,967,180 | ✓ restored from 393d stale |
| VIX | 2026-04-29 | 2,144,396 | ✓ restored from 392d stale |
| XAUUSD | 2026-04-29 | 2,555,565 | ✓ restored from 60d stale |
| BRENT_OIL | 2026-04-29 | 2,332,234 | ✓ |
| GBPJPY | 2026-04-29 | 2,573,387 | ✓ |
| USA500 | 2026-04-29 | 739,093 | ✓ ~2 yr |
| TSLA D1 | 2026-04-28 | 3,994 | ✓ since IPO |
| MSFT D1 | 2026-04-29 | 10,140 | ✓ since 1986 |
| GASOLINE/WHEAT/CORN | 2026-04-29 | ~10-20k | ⚠ only 2 months — backfill running unattended |

**MT4 Phase 6 quality (Apr 19 → today):**
- Mean MT4 − BC: −0.16% (essentially flat)
- Median |diff|: $0.18
- Mean intraday std: 0.087
- Best tracking ever observed in the dataset

→ Live paper trading can start as soon as the directional model is built. No data-side blocker. Just add live BC ingestion before going live so Rule 4 anchoring is operational.
