# RiseTraderMVP — Full Project State Review

**Report Date:** April 20, 2026
**Author:** Session context rebuild (Slim / claude-opus-4-7)
**Purpose:** Consolidate every prior memory (Nov 2025 → Apr 2026) into a single up-to-date reference. Read this first before any new work.
**Branch:** `008-async-optimization-sse` (heavy uncommitted changes from paper-throughput sprint Apr 4)
**Live Account (queried via risetrader-mcp):** Balance $293.39 USD, Equity $293.39, Free Margin $293.39, 0 open positions, 0 pending orders.

---

## 1. MISSION (unchanged since Feb 2026)

RiseTrader is a 24/7 autonomous algorithmic trading system targeting $10K → $1M growth via a multi-agent architecture trading MT4 CFDs on the Fortrade broker. The system is built around:

1. **10-agent pipeline** coordinated by an MCP server (signal → risk → execution → monitoring).
2. **No-fakes policy** (6 known fakes eliminated Mar 9, 2026): real ATR, real correlation, real VaR, real Kelly inputs, real ML scores/confidences. A `validate-no-fakes.sh` hook blocks regressions.
3. **Three-tier testing** (unit → integration → E2E with real MT4/candle data, no mocks).
4. **Phased roadmap** Phase 1–4 (all code-complete), with Phase 5 = live/paper deployment currently in flight.

North star is a Dalio-style multi-instrument diversified book (15 uncorrelated streams) rather than a single-market bet.

---

## 2. ACCOUNT + BROKER REALITY (Apr 20, 2026 snapshot)

- **Broker:** Fortrade Canada, account `#1423389` (Slim Rouissi), currency USD.
- **Server IP:** `75.154.254.174` (remote / public) or `192.168.0.123` (local home LAN). Ollama and MT4 share this host — ZMQ ports 5555/5556 for MT4, 11434 for Ollama. Always switch both together via `scripts/switch_network.py local|remote`.
- **Balance history:**
  - Jan 5, 2026: $11,053.51 (with 1.0 lot SHORT CrudeOIL floating +$450)
  - Feb 10, 2026: ~$9,474.91
  - Mar 3, 2026: ~$10,041 (0.5 lot SHORT CrudeOIL @ $62.80 plus 5 pending orders)
  - Mar 26, 2026 (live launch day): $396.97 — **implies a ~$8,600 drawdown Feb→Mar** from CrudeOIL short caught in $71.95 → $90.96 rally (see `.claude/AGGRESSIVE_RECOVERY_STRATEGY.md`).
  - Apr 4, 2026: $293.39 (no positions)
  - **Apr 20, 2026 (NOW): $293.39** — unchanged since Apr 4, markets have been inactive for this account since the last trade unwound.
- **CrudeOIL live spec (queried today):** bid 86.515 / ask 86.605, spread 90 points, contract 1000 bbl, margin_pct 16.53% (broker raised margin sharply from 6.5% on Mar 3 → 16.5% now), **leverage now only 6.1x (was 15.4x)**. Margin per 0.01 lot ≈ $143.
  - This matters: prior sizing math (margin $41 for 0.01 lot CrudeOIL) no longer holds. The broker effectively tightened ~2.7× since March.

### 2.1 Funding gap for proper testing

The Apr 4 signal-fix sprint documented this exact blocker and it is still in force today:

- CrudeOIL ATR(14) = $1.71 at that time.
- Max stop at 5% risk / 0.01 lots / contract 1000 = $1.467 budget → ratio 0.86× ATR, below the 0.9× ATR floor. Commit `b49ce1c` lowered the floor to 0.8× to unblock, but only barely.
- Minimum account for CrudeOIL at ATR 1.71 with 0.9× ATR floor: **$307.80.** Current: $293.39 → still ~$15 short of clean headroom even after the ATR-floor concession.
- With today's *higher margin requirement* ($143 vs prior $41 per 0.01 lot), the practical floor is even higher — **a single 0.01 lot CrudeOIL now eats ~49% of the account as margin**, leaving almost no room for 3 concurrent paper trades or any diversification.

**Funding recommendations to unblock proper testing:**

| Goal | Minimum deposit | Comfortable deposit |
|------|-----------------|---------------------|
| Single CrudeOIL 0.01 lot live, sane margin (<30%) | top up to **$500** | **$1,000** |
| Full Apr-4 paper-throughput plan (3 concurrent × 3 symbols incl. CrudeOIL, USA500, GBPJPY.) | **$1,000** | **$2,000** |
| Dalio-style 8-position diversified book (see §6 portfolio table) | **$2,000** | **$5,000** |
| Original "aggressive recovery" tiered-sizer targeting 0.05 lot CrudeOIL on 95%+ confidence | **$3,000** | **$5,000+** |
| Crash-portfolio strategy (Feb 2026 plan, 0.3–0.5 lot CrudeOIL legs, 0.05 lot GOLD., multi-leg pendings) | Needs reset to $10,000 baseline |

**Bottom line: we cannot meaningfully validate the system below ~$1,000 given current broker margin. A deposit to $1,000–$2,000 unlocks paper throughput and the 3-symbol set (CrudeOIL, USA500, GBPJPY.) that the live service is wired for.**

---

## 3. WHERE WE ARE ON THE ROADMAP

### Phase status (from `session-2026-03-09-status-and-pending.md`, still current)
- **Phase 1:** COMPLETE. All 4 in-scope fakes eliminated (ATR, correlation, VaR, Kelly).
- **Phase 2:** COMPLETE. 4 new strategies (crack spread, WTI-Brent, seasonal MA ag, GBPJPY carry), 5+ instruments, correlation blocking live.
- **Phase 3:** CONDITIONAL PASS. Crisis code (VIX regime switching, crash portfolio, contrarian filter, crisis stops) all in place — real crisis replay confirmed COVID best = value_area +2.64%, Energy best = ma_crossover +21.82%. USA500 coverage still patchy for full replay targets.
- **Phase 4:** COMPLETE on the code side. All 6 fakes eliminated, `ReversalPredictor` wired with XGBoost, ML Reversal strategy registered in both synthetic and vectorized engines, backtested profitably. *Only CrudeOIL_H1 model actually persisted to disk.*
- **Phase 5 (current):** Live paper trading + throughput sprint, driven by `LiveTradingService` (Mar 26 launch) and the Apr 4 concurrent-paper-trades upgrade.

### Fakes elimination (all 6 done — do not reintroduce)
| # | Fake | File | Replacement |
|---|------|------|-------------|
| 1 | ATR defaults `{"CrudeOIL": 0.75}` | stealth_stop_manager.py | real Wilder ATR via `atr_calculator.py` |
| 2 | `score = 0.5 + features[0]*0.3` | ml_prediction.py | `ReversalPredictor` booster output |
| 3 | `confidence = 0.75` | ml_prediction.py | real reversal probabilities |
| 4 | `return 0.2` correlation | risk_overseer.py | rolling 20-day Pearson of D1 log returns |
| 5 | `0.02 * balance` VaR | risk_overseer.py | realized daily vol from D1 candles |
| 6 | Kelly inputs w/ fake confidence | risk_manager.py | real win_rate + avg_win/avg_loss from TradingHistoryRepository |

---

## 4. STRATEGIES INVENTORY

### SyntheticEngine (tick-by-tick, 12 strategies)
Phase 1: `crude_oil_v3`, `ma_crossover`, `rsi`, `mean_reversion`, `trend_following`, `value_area`
Phase 2: `crack_spread`, `wti_brent_spread`, `seasonal_ma_corn`, `seasonal_ma_wheat`, `gbpjpy_carry`
Phase 4: `ml_reversal` (XGBoost reversal classifier, 43 features)

### VectorizedEngine (batch, 100× faster, 6 strategies)
`ma_crossover`, `rsi`, `crude_oil_v3`, `mean_reversion`, `value_area`, `ml_reversal`

### MCP tool surface (currently live, from `list_strategies`)
The MCP server *only* advertises 6 synthetic strategies today: `crude_oil_v3`, `ma_crossover`, `rsi`, `trend_following`, `mean_reversion`, `value_area`. Phase 2 spread/carry/ag strategies and Phase 4 `ml_reversal` exist in code and are registered in the engines, but are not exposed by `list_strategies` — worth confirming next session whether that is a registration gap or intentional (likely the MCP list endpoint reads a stale registry).

### April 4 signal-generation upgrades (commit-ready, not yet merged)
- **trend_following** rewritten (EMA20/EMA50 alignment + slope confidence). Live score 0.97, conf 0.90.
- **momentum continuation** fix: dampening replaced by `min(0.5 + abs(diff)/long_ma*20, 0.9)`. Live score 0.90, conf 0.70 (was 0.35).
- **breakout** switched from 99.5%-of-20bar-high to percentile position (trigger at ≥0.85 or ≤0.15). Live score 0.90, conf 0.65 (was 0.00).
- Diagnostic logging added (`strategy_raw_output`, `signal_combine_result`).
- Cross-asset confirmation on CrudeOIL passes even with BRENT + USA500 neutral.
- **Result:** signals now pass all filters for CrudeOIL (combined 0.92, conf 0.75, threshold 0.60). Only blocker is position sizing on the $293 account.

---

## 5. MODELS

| Model | Status | File / Notes |
|-------|--------|--------------|
| XGB reversal classifier — CrudeOIL H1 | **PERSISTED** | `models/reversal_classifier/CrudeOIL_H1/` — XGB-conservative (max_depth=4, lr=0.2, 100 trees), 43 features, training_date 2026-03-06, reversal_f1 0.1165, peak_f1 0.0899, valley_f1 0.1431, macro_f1 0.4002. Quality gate threshold is F1 ≥ 0.30 → current model **blocked by gate**, `ml_reversal` returns None each cycle. |
| XGB — BRENT_OIL H1 | **trained, NOT saved** | Best F1 0.142 (XGB-aggressive) |
| XGB — USA500 H1 | **trained, NOT saved** | F1 0.122 |
| XGB — GBPJPY H1 | **trained, NOT saved** | F1 0.094 (weakest) |
| XGB — XAUUSD H1 | **failed** | 99.9% zero tick volume → feature NaNs |
| LSTM all symbols | **blocked** | Docker OOM, needs host training or bigger container |
| Reversal features pipeline | **working** | `src/ml/features/reversal_features.py::compute_features_from_ohlcv()` = single source of truth for 43 features used in both training and inference |
| ZigZag labeler | **working** | depth=12, deviation=5, backstep=3; reversal rate ≈6% across all symbols (consistent with expectations) |
| Indicator compute service | **working** | 231,754 indicator rows computed across 5 symbols on H1 |

### Critical ML notes
- Load XGBoost via `xgb.Booster().load_model()` + `DMatrix`, never `XGBClassifier().load_model()` (loses `n_classes_`, crashes `predict_proba`).
- Class mapping: 0=valley→BUY, 1=neutral→HOLD, 2=peak→SELL.
- F1 scores look low because only ~6% of candles are reversals — but backtest P&L is where it's proven (see §6).
- Signal-generator ML weighting by regime: high_vol=0.15, trending=0.25, ranging=0.20, low_vol=0.10. Kelly sizing is decoupled from ML confidence (uses real trade stats) — graceful degradation if a model is missing.

---

## 6. BACKTEST RESULTS (latest, CrudeOIL H1, Jan 2024 – Mar 2025, $10K)

| Strategy | Return | Sharpe | Win Rate | PF | Max DD | Avg P&L | Trades |
|----------|--------|--------|----------|-----|--------|---------|--------|
| **Value Area** | **+208.94%** | 16.94 | 83.95% | 3.42 | -7.16% | $50.88 | 162 |
| **ML Reversal (XGB)** | **+156.62%** | 12.63 | 79.37% | **4.25** | -16.01% | **$103.11** | 63 |
| Crude Oil v3 | +3.48% | 1.13 | 31.34% | 1.16 | -8.13% | $4.67 | — |
| RSI | -8.89% | -1.08 | 63.83% | 0.81 | -22.62% | -$10.07 | — |
| MA Crossover | -17.47% | -2.61 | 33.06% | 0.74 | -24.77% | -$13.75 | — |

Key read: **Value Area wins on absolute return, ML Reversal wins on profit factor and per-trade expectancy.** Ensemble (ML-Reversal + Value-Area) was scoped in the Phase 5 "Crude Oil mega delegation" but not yet built.

### Historical crisis replay (real, from audit fix sprint)
| Period | Best strategy | Return | Sharpe |
|--------|---------------|--------|--------|
| COVID crash (Feb–Apr 2020) | CrudeOIL MA f15/s20 | +154.7% | 10.0 |
| 2022 Energy crisis | CrudeOIL MA f8/s40 | +60.5% | 9.0 |
| COVID recovery (May–Dec 2020) | CrudeOIL MA f12/s25 | +37.2% | 5.4 |

Rolling-window OOS MSFT Mean Reversion (0.88 robustness) and MSFT MA Crossover (0.75) are the two strategies that pass the Monte-Carlo/walk-forward smell test on equities.

---

## 7. DATA STATE

| Symbol | Timeframes | Rows | Range | Note |
|--------|-----------|------|-------|------|
| CrudeOIL | M1 / M5 / H1 | 5.5M / 442K / 95K | 2009→2026 | primary dataset |
| GBPJPY | H1 | 42.7K | 2019→2025 | Dukascopy |
| XAUUSD | H1 | 42K | 2019→2025 | 99.9% zero volume — unusable for volume features |
| BRENT_OIL | H1 | 38.7K | 2019→2025 | 98.6% zero volume |
| USA500 | H1 | 13.1K | 2023→2025 | 79.3% zero volume |
| TSLA, MSFT | M5/M30/H1/D1 | up to 10K each | varies | CSV + MT4 live |
| DXY, VIX | M1 mostly | 5.7M / 1.9M | 2008→2025 | zero volume throughout |

Dukascopy is the backfill feed (HistData is defunct since Mar 2026). CORN / WHEAT / GASOLINE are MT4-live-only — no historical backfill available on the free feed.

### Candle aggregator tracked symbols (live)
`CrudeOIL, USA500, BRENT_OIL, CORN, WHEAT, GBPJPY, TSLA, MSFT, GASOLINE, XAUUSD`

### EA symbol list (`RiseTraderMT4Server.mq4`)
`CrudeOIL, USA500, BRENT_OIL, CORN, WHEAT, GBPJPY., #TSLA, #MICROSOFT, GASOLINE, GOLD.`

---

## 8. INFRASTRUCTURE — what actually runs

- **LiveTradingService** (`src/services/live_trading_service.py`) — Mar 26 launch. Autonomous 5-minute loop: signal → risk → execute. Current symbol set `CrudeOIL, USA500, GBPJPY.`. Paper-TP is 1.5× ATR (Apr 4 change), Paper-SL 2× ATR. Live (post-paper-gate) uses original wider distances. 72-hour timeout on stale paper trades. Concurrent paper-trade limit 3/symbol with 4h time gap + 1× ATR price gap. Singleton; wired into `api/main.py` lifespan.
- **Stealth stop manager** — Feature 007 complete (Jan 17, 2026). Four layers: disaster stop (3× ATR within 10s), profit-erosion detection (0.3× ATR alert / 0.5× ATR protect), early trailing (trigger 0.5× ATR, breakeven 0.5× ATR, trail 1.5× ATR), alerts. Feature flags all default ON. Anti-stop-hunt: random 5–15 pip offset on every stop.
- **Agent coordinator** — still commented out (bypassed by LiveTradingService since Mar 26). Reviving it is not on the critical path.
- **MCP server** — live, reachable from this session. Exposed 40+ tools (trading, backtesting, optimization, ML, market data, news/Trump posts). Phase-2 strategies not listed by `list_strategies` (registry gap).
- **Docker stack** — 12 services (Postgres 17, Redis 7, API, MCP, Dashboard, Grafana, Prometheus, Kibana, Jaeger, Elasticsearch, Logstash, Nginx, MLflow on its own DB). MLflow healthcheck fixed Mar 26. Docker compose command override in place for mounted script losing `+x` on macOS.
- **ZMQ MT4 client** — `asyncio.Lock()` on `send_command()` eliminates EFSM errors; socket auto-reset on timeout. Data-only reconnect loop fixed for TSLA insufficient-data errors.
- **EDA / data quality** — `/api/eda/*` endpoints live; quality score 0–100 with price-consistency the heaviest weight (-25).
- **Network switching** — `python3 scripts/switch_network.py local|remote` updates both MT4 and Ollama IPs atomically.

### Git state
- Current branch: `008-async-optimization-sse` (main is `001-mt4-integration`).
- Latest commits (head first): `b49ce1c` lower ATR floor 0.9→0.8x, `b42001a` concurrent paper trades + tighter TP `[integration-pass]`, `0f35d53` TieredPositionSizer, `17955b1` ML inference / social / news / regime services, `a8814d8` CandleAggregator + Decimal SL/TP handling, `1345e96` SeasonalMA deque + contrarian filter + Kelly from history.
- **~30+ files still uncommitted** spanning the Apr 4 paper-throughput sprint and the Mar 5–9 ML refactor. Needs a batched commit pass with `[integration-pass]` tags.

---

## 9. KNOWN BLOCKERS & OPEN ITEMS

1. **Account too small for live execution at current broker margin.** Primary blocker. See §2.1.
2. **XGBoost quality gate blocks `ml_reversal`.** F1 0.089 < 0.30 threshold → strategy silently returns None every cycle. Options: (a) retrain with Phase 5 mega-delegation grid, (b) relax gate to a P&L-based threshold, (c) temporarily gate by macro_f1 (0.40, which passes).
3. **Only CrudeOIL_H1 model persisted** — BRENT_OIL, GBPJPY, USA500 trained but never saved.
4. **LSTM OOM in Docker** — move to host training or raise container memory.
5. **XAUUSD volume = 0** — features blow up. Fix by skipping volume features or imputing 1 for XAUUSD path.
6. **MCP `list_strategies` underreports** — only 6 of 12 registered strategies surface. Registry inspection needed.
7. **Decoy/ghost stops (truly hidden)** — documented as a TODO Jan 12; never built. Currently EA still sees the stop.
8. **Dashboard** — built but not actively used in the paper-throughput loop; last major polish Dec 2025 session.
9. **Agent coordinator** — dormant. Decide: revive or retire.
10. **Phase 3→4 gate "crisis replay reproduces +150% COVID / +60% energy"** — partially validated (COVID confirmed only +2.64% on value_area), USA500 data coverage insufficient to close gate officially.

---

## 10. OPPORTUNITY PIPELINE (Feb 2026 strategic assessment — still relevant)

Ranked by expected impact, none of these are yet earning P&L:

1. **Crack spread** (CrudeOIL + HEATING_OIL + GASOLINE) — academic 60–65% win, 1.8–2.2x PF. Coded Phase 2, not yet deployed live.
2. **Seasonality overlay** (month-of-year filter on commodity strategies) — 68–72% reliability in research docs; trivial to add; could flip `crude_oil_v3` from negative to positive OOS.
3. **Volatility-regime switching** (20-day ATR percentile rank → trend vs MR branch). Simple filter that coordinates all 6 Phase 1 strategies coherently.
4. **Agriculture seasonal** — CORN/WHEAT done, SOYBEAN still untouched. Strong leverage (16.6–27x) and capital efficiency ($19–$42 margin per 0.01 lot).
5. **Position sizing fix** — ALREADY LANDED via `TieredPositionSizer` (commit 0f35d53). Still under-validated because account too small to scale above the minimum lot.
6. **WTI–Brent spread** — coded, not live.
7. **GBPJPY. carry** — coded, +8 point positive swap long for long trend-aligned holds. Strategy exists, needs live enablement.
8. **Bond duration** — 10Y_T-NOTES at 100x, 7¢ spread. Untouched.
9. **Cross-asset hedging** — DOLLAR_INDX inverse, COPPER as macro read — nothing implemented.

### Proposed $10K Dalio-style portfolio (from MT4 symbol map)

| Instrument | Margin | Role |
|-----------|--------|------|
| 10Y_T-NOTES | $11 | rate cycle / safe haven |
| CORN / COTTON / WHEAT | $19 / $26 / $33 | seasonal ag |
| COPPER | $40 | macro growth |
| CrudeOIL | $41 (old; ~$143 now) | primary energy |
| GBPJPY. | $81 | carry + FX |
| GASOLINE + HEATING_OIL | $108 + $133 | crack spread legs |
| **Total** | **~$492** | <5% of account |

Today's raised CrudeOIL margin changes this math but not the shape — still far easier to run diversified at $1–2K than a single-symbol CrudeOIL bet.

---

## 11. AGENT TEAM (CLAUDE.md governance — do not violate)

- **Permanent core:** `lead` (Opus, orchestrator), `quant-dev` (Sonnet, strategies/agents/ML), `risk-eng` (Sonnet, stops/sizing/ATR), `mcp-verifier` (Sonnet, exclusive MCP access, no-mocks enforcer), `reviewer` (Sonnet, read-only 5-lens review).
- **Phase specialists:** `spread-builder` (Phase 2), `crisis-automator` (Phase 3), `ml-trainer` (Phase 4, worktree isolation), `flow-detector` (informed-flow delegation, Apr 2026).
- **Hooks:** `validate-no-fakes.sh` (PostToolUse Edit/Write), `require-integration-test.sh` (TaskCompleted). Commits must carry `[integration-pass]` from mcp-verifier.
- **File ownership enforced** — see `docs/file-ownership.md`. Cross-cutting changes need lead + reviewer sign-off.

---

## 12. WHAT I WOULD DO NEXT (suggested prioritization)

**If the goal is "get the system trading again reliably":**

1. **Fund the account to at least $1,000** (ideally $2,000) so paper-trade throughput, ATR floors, and margin can all breathe. At $293 we are dancing on every guard rail.
2. **Commit the 30+ uncommitted files** in batched `[integration-pass]` groups (paper-throughput sprint; signal-generation fixes; ML pipeline refactor). Otherwise all of Feb–Apr work is one Docker rebuild away from disappearing.
3. **Decide the ML-reversal gate** — either retrain (Phase 5 mega-delegation grid) or soften the F1 gate so the model is actually firing in the live loop.
4. **Persist BRENT_OIL / GBPJPY / USA500 models** (one script run). Without this the multi-symbol ML story is fiction.
5. **Reconcile `list_strategies` MCP output** with the 12 strategies actually registered — either fix the endpoint or document that the API surface is a subset.
6. **Re-run `monte_carlo_validate` + `rolling_window_optimize`** on `ml_reversal` and `value_area` across the four symbols with persisted models before any fresh live risk.
7. **Run the 72-hour autonomous paper-trading session** implied by the Phase 4→Production gate. The Apr 4 plan targets 50 resolved paper trades by ~Apr 10–12 — we are past that window with 0/50 documented, so the clock needs to restart.

**If the goal is "explain the project to a new collaborator":**

Point them here, then at `CLAUDE.md`, then at the latest three session memories: `2026-04-04-paper-throughput-sprint`, `2026-04-04-signal-fix-sprint-evaluation`, `session-2026-03-26-live-trading-launch`. Those three cover the live trading, the signal fixes, and the paper-throughput sprint — 90% of the current delta.

---

## 13. REFERENCE INDEX — source memories consulted

Most recent → oldest:
- `2026-04-04-paper-throughput-sprint.md` — concurrent paper trades, tighter TP, 72h timeout
- `2026-04-04-signal-fix-sprint-evaluation.md` — trend_following / momentum / breakout fixes, CrudeOIL account-size blocker
- `session-2026-03-26-live-trading-launch.md` — LiveTradingService, MLflow, ZMQ lock, first trade executed
- `session-2026-03-09-ml-pipeline-refactor-complete.md` + `session-2026-03-09-status-and-pending.md` — 4-part refactor (services, Docker, ML strategy, MCP tools)
- `ml-pipeline-training-results-mar2026.md` + `backtest_results_feb2026.md` — training results table, backtest P&L
- `zigzag-ml-labeling-implementation.md` — labeling scheme
- `MT4_SYMBOL_UNIVERSE_AND_LEVERAGE_MAP.md` — 174-symbol universe, leverage tiers, proposed portfolio
- `STRATEGIC_ASSESSMENT_FEB2026.md` — 9-item opportunity pipeline
- `AGENT_TEAM_CONFIG_FEB2026.md` — 5-agent core + phase specialists
- `crash-portfolio-strategy-feb-2026.md` — Dalio crash allocation, pending orders blueprint
- `session-2026-02-10-data-audit-backtest-evaluation.md` — Dukascopy import, rolling-window OOS results
- `session-2026-01-05-backtesting-system-fixes.md` — trade-limit bug (1000→10M), exit rules, max-candles timeout
- `stealth-stop-protection-complete.md` — Feature 007 four-layer protection
- `trading-review-jan-12-2026.md` + `session-2026-01-11-crude-oil-weekly-strategy.md` — weekly trading notes
- `eda-data-quality-implementation.md` — EDA service + dashboard page
- `SESSION_PROGRESS_2025-11-17.md` / `MEMORY_INDEX.md` / `QUICK_START.md` / `NEXT_STEPS_ROADMAP.md` — original Nov 2025 build-completion baseline
- `.claude/AGGRESSIVE_RECOVERY_STRATEGY.md` (uncommitted) — tiered sizer + pyramiding plan
- `.claude/INFORMED_FLOW_DELEGATION_PLAN.md` (uncommitted) — price velocity / tick clustering / cross-asset monitor plan
- `PHASE5_CRUDE_OIL_MEGA_DELEGATION.md` (uncommitted) — Mar 21 10× profit target delegation
- `RiseBackendMVP/comprehensive-audit.md` — unrelated RiseBackendMVP repo audit (security findings, not this project)

---

*End of Apr 20, 2026 state review. Read this first next session, then jump into the prioritized next-steps in §12.*
