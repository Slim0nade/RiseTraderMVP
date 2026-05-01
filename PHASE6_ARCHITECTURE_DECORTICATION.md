# RiseTraderMVP — Architecture Decortication
## A 6-Month Retrospective: Each Architectural Choice, Re-Examined Against Live Evidence

**Date:** April 30, 2026
**Status:** Companion document to `PHASE6_LOOP_TO_AUTONOMY_MEGA_DELEGATION.md`
**Method:** For each major subsystem we built 6 months ago, we examine: (a) the original justification, (b) the cost it imposes today, (c) the empirical evidence from 6 months of operation, (d) a 3-experts debate, (e) the **status (evidence-backed verdict OR untested hypothesis)**, (f) the KPI that proves the verdict was right, (g) the paste-ready dashboard widget.

---

## ⚠️ READ THIS FIRST — Epistemic Honesty Preamble

**An earlier draft of this document declared verdicts on every subsystem as if a measurement had decided them. It hadn't.** The 3-experts debate is a useful reasoning structure but **debate winners are not the same as measurement outcomes.** Most of the "verdicts" below are *hypotheses with plausible reasoning* — the experiment that would actually decide them has not been run.

We are doing exactly what we corrected on the MT4 phase analysis: refusing to call a thing "bad data" until p-values, autocorrelations, or r²s say so. The same standard applies here.

Of the 12 subsystem judgments below:

| Status | Subsystems | What this means |
|--------|-----------|-----------------|
| ✅ **Evidence-backed** | #4, #7, #9 | Real data we already have decides this. Act on the verdict now. |
| ⚖️ **Partially backed** | #2, #10 | Some real evidence, but the alternative has never been run head-to-head. Treat as a strong prior, validate via the experiment in §APPENDIX A. |
| 🔬 **Hypothesis only** | #1, #3, #5, #6 | Plausible reasoning. No empirical comparison. Do NOT act on the verdict before running the experiment. |
| 🔧 **Infrastructure judgment (not subject to measurement)** | #8, #11, #12 | Cost/risk reasoning, not a research question. The "verdict" is a recommendation, not a measurement. |

**The body of this document is the reasoning. §APPENDIX A — EVIDENCE AUDIT & EXPERIMENT DESIGN — is how we'd actually decide each one. Read both. Treat the body as Phase 6 priors and the appendix as the validation plan that turns priors into measured truth.**

---

## The Three Experts

Each subsystem is debated by three perspectives. They **disagree** — that's the point. The verdict is whichever expert wins, with reasoning.

**🎓 The Quant ("La Prado")** — School of Marcos López de Prado, Ernie Chan. Cares about: walk-forward integrity, ablation, t-statistics, leakage hunts, label noise. Hates: subjective labels, F1-only evaluation, SMOTE on time-series, "we couldn't prove it but it felt right."

**📊 The Trader ("Clenow")** — School of Andreas Clenow, Robert Carver. Cares about: P&L after costs, regime awareness, trend persistence, sample size of *trades* (not bars). Hates: backtest perfection, pretty Sharpe ratios with 12 trades, ML on noisy intraday data, complexity not paid for in basis points.

**⚙️ The Engineer ("Karpathy/DHH")** — School of Andrej Karpathy + DHH. Cares about: boring tech, deletion, observability, "what's the simplest thing that could possibly work." Hates: speculative scale, frameworks built for users that don't exist, premature abstraction, "we'll need it later."

---

## Subsystems Examined

| # | Subsystem | Recommendation | Status |
|---|-----------|---------------|--------|
| 1 | The 10-Agent MCP Architecture | REFACTOR — collapse to 3 modules | 🔬 Hypothesis (no measurement of 3-module alternative ever run) |
| 2 | ZigZag Labeling | KILL — replace with ForwardReturnLabeler | ⚖️ Partial (F1=0.089 is real; head-to-head vs ForwardReturn never run) |
| 3 | 43 Single-Symbol Features | REFACTOR — add cross-asset | 🔬 Hypothesis (cross-asset features never computed on this data) |
| 4 | Backtest Synthetic Engine | REFACTOR — cost-aware | ✅ Evidence-backed (+156% backtest vs F1=0.089 live is real) |
| 5 | Stealth Stop Manager (ATR + random) | KEEP, measure firing rate | 🔬 Hypothesis (n=22 stop hits is below noise floor) |
| 6 | Kelly Position Sizing | KEEP behind feature flag, hybrid default | 🔬 Hypothesis (we have <30 trades — Kelly inputs are sample-noise dominated) |
| 7 | Risk Overseer Correlation Gate | REFACTOR — make observable | ✅ Evidence-backed (zero firings in `decision_log` is real) |
| 8 | MT4 ZMQ Bridge | KEEP, tunnel via WireGuard, replace in Phase 8 | 🔧 Infrastructure judgment (not subject to measurement) |
| 9 | PostgreSQL Time-Series Schema | KEEP | ✅ Evidence-backed (200ms p95 is real, 13.5M rows works) |
| 10 | Redis Pub/Sub for Agents | KILL — collapse to asyncio | ⚖️ Partial (1 missed-signal bug + 600 LoC is real; post-collapse stability unmeasured) |
| 11 | React + TradingView Dashboard | KEEP, extend with widgets | 🔧 Infrastructure judgment |
| 12 | Docker Compose + MLflow | KEEP both, extend MLflow with trading-KPIs | 🔧 Infrastructure judgment |

**Net code impact:** ~3,200 lines deletable; ~6 services collapsible into 3; 1 entire framework (Redis pub/sub for agent comms) removable.

---

# Subsystem 1 — The 10-Agent MCP Architecture

## What we built 6 months ago
A Model Context Protocol server coordinating **10 autonomous trading agents** (`SignalGeneratorAgent`, `RiskManagerAgent`, `ExecutionAgent`, `MarketDataAgent`, `MLPredictionAgent`, `RegimeDetectionAgent`, `PerformanceMonitorAgent`, `RiskOverseerAgent`, `StrategyOptimizerAgent`, `MCP Server`). Event-driven via Redis pub/sub. Justified in `PROJECT_REBUILD_SPECIFICATION.md` as the "core innovation."

The architectural assumption: agents would specialize, scale independently, and produce emergent collaborative behavior. Inspired by the contemporaneous wave of multi-agent papers (Stanford "Generative Agents" 2023, AutoGen 2023, the AGI-via-LLM-orchestration meme).

## Costs today
- **~4,000 lines of agent infrastructure** (`src/agents/`) — base classes, message bus, registry, lifecycle hooks
- **3 separate Python processes** in production (API, MCP server, agent coordinator) requiring health checks, restart logic, inter-process tracing
- **Redis pub/sub** as a critical-path dependency for what is, today, a sequential pipeline
- **Cognitive load:** every signal trace crosses 4-5 agent boundaries; debugging a missed signal requires reading 4 service logs

## Evidence from 6 months
- **Trading throughput: 2 paper signals in 17 days.** Whatever emergence we expected from multi-agent collaboration, it did not produce trades.
- The actual signal flow is **single-threaded and sequential**: tick → MarketDataAgent → SignalGeneratorAgent → RiskManager → Execution. The "collaboration" between Regime, ML, and Signal agents is just function calls dressed up as events.
- **No agent has ever overruled another in production.** RegimeDetection has not vetoed a single signal. MLPrediction has not changed a position size based on confidence (it was hardcoded to 0.75 until April 2026).
- **5 of 10 agents are dormant** — `StrategyOptimizerAgent` has zero entries in `decision_log`; `PerformanceMonitorAgent` overlaps with the dashboard's existing metrics service.

## 🎓 Quant
> "An agent architecture is justified when distinct decision processes operate at different frequencies or with genuinely independent information sets. Here, every agent operates on the same tick. The 'agent' abstraction is hiding what is, statistically, a single decision function. Collapse it. The Sharpe of a clean function is identical to the Sharpe of an over-engineered framework wrapping that function."

## 📊 Trader
> "I run a $400→$10M ambition with **two trades in seventeen days**. I do not need ten agents — I need a strategy that fires more than once a fortnight. Every line of agent infrastructure is a line that didn't go into the labeling, the features, or the position sizing. The 10-agent design was an answer to a problem I don't have yet."

## ⚙️ Engineer
> "Three processes for one signal flow is two processes too many. Redis pub/sub for inter-agent communication when the agents are in the same Python process and could just `await` each other directly is the textbook example of solving an imaginary distributed-systems problem. Collapse to one process. Keep the *concept* of agent roles in module structure if it helps reasoning, but kill the framework."

## Disagreement & resolution
The Quant suggests a full collapse to a single function. The Trader agrees on collapse but wants to **preserve the role boundaries as policy hooks** — the place where you'd plug in a regime override or a risk veto if you ever build one. The Engineer sides with the Trader: **module-level role separation costs nothing; the IPC framework costs ~4,000 lines and a Redis dependency.**

**Resolution:** keep `signal_generator`, `risk_manager`, `execution` as **modules** with clean function boundaries. Kill the message bus, the MCP server's agent-coordination role, the agent registry, the lifecycle hooks. The *MCP server stays* — but only for tool-calling (`place_market_order`, `compute_indicators`, etc.), which is the original MCP definition.

## Verdict: **REFACTOR — collapse 10 agents to 3 modules**

Concrete plan:
1. **Phase 6 (now):** stop adding new agents; do not remove anything yet
2. **Phase 7 (post-loop-closure):** extract `SignalGeneratorAgent`, `RiskManagerAgent`, `ExecutionAgent` into pure modules. Delete `MarketDataAgent`, `MLPredictionAgent`, `RegimeDetectionAgent`, `PerformanceMonitorAgent`, `RiskOverseerAgent` (their logic moves into the 3 surviving modules). Delete `StrategyOptimizerAgent` entirely (the nightly retrain in Phase 6 D2 replaces it).
3. **Phase 7 deletion target:** ~3,200 lines.

## KPI to track
**Active-Agent-Utilization (AAU)** = (# agents whose decisions changed an outcome in the last 7 days) / (# active agents). If AAU < 0.5 for 30 days running, the dormant ones go.

- **Formula:** for each agent, count entries in `decision_log` where `agent_decision != default_passthrough`. Divide by total signals.
- **Source:** `decision_log` table with `actor` column.
- **Cadence:** computed nightly, displayed weekly.

## 📊 Dashboard widget — **AgentUtilizationCard.tsx**

```tsx
// dashboard/src/components/AgentUtilizationCard.tsx
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import axios from "axios";

type AgentRow = { agent: string; total_decisions: number; non_default_decisions: number; utilization: number };

export default function AgentUtilizationCard() {
  const { data, isLoading } = useQuery<AgentRow[]>({
    queryKey: ["agent-utilization-7d"],
    queryFn: () => axios.get("/api/agents/utilization?window_days=7").then(r => r.data),
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="p-4">Loading agent utilization…</div>;

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <h3 className="mb-2 text-lg font-semibold text-zinc-100">Agent Utilization (7d)</h3>
      <p className="mb-4 text-xs text-zinc-400">
        Bars below 50% (red) are candidates for deletion. Phase 7 retires &lt;30% utilization.
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 80 }}>
          <XAxis type="number" domain={[0, 1]} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
          <YAxis type="category" dataKey="agent" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
          <Bar dataKey="utilization">
            {data?.map((row, i) => (
              <Cell key={i} fill={row.utilization < 0.3 ? "#ef4444" : row.utilization < 0.5 ? "#f59e0b" : "#10b981"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

API contract: `GET /api/agents/utilization?window_days=7` → `[{agent, total_decisions, non_default_decisions, utilization}]`. Backed by a SQL view; ~30 lines of FastAPI route code.

---

# Subsystem 2 — ZigZag Labeling

## What we built 6 months ago
The classic ZigZag indicator-based label: walk the price series, mark every reversal of magnitude ≥ X% as a peak/valley/neither. Justified by the Weng et al. 2018 "Stock prediction using deep learning models on 1-minute data" lineage and similar Kaggle-style supervised setups for financial reversals.

The architectural assumption: reversals are the highest-leverage event to predict, and a clean three-class label (peak/valley/neither) makes them tractable for a classifier.

## Costs today
- **`src/ml/labeling/zigzag_labeler.py`** is small (~150 lines) but **its outputs poison everything downstream**: F1-targeted training, F1-as-evaluation-metric, class imbalance forcing SMOTE.
- **Look-ahead leakage risk:** ZigZag is defined retrospectively. Any naive implementation peeks at future bars. We have two known places this happens.
- **Class imbalance:** ~95% "neither" labels → the model learns to predict "neither" and call it 95% accuracy.

## Evidence from 6 months
- **Production F1: 0.089.** Peak class F1: 0.090. Valley: 0.143.
- **Backtest Sharpe 12.63, Profit Factor 4.25** on the same labels — but on the **training distribution** with **synthetic execution**, not paper-mode.
- The gap between 0.089 production F1 and +156% backtest return is the largest disconnect in the entire system. Some of it is execution; **most of it is label noise.**

## 🎓 Quant
> "ZigZag labels are subjective and unstable. The threshold parameter that defines a 'reversal' is exactly the parameter you would optimize on in-sample. Classification on a 95-5-0 distribution measured by F1 is meaningless — the trivial 'always predict neither' baseline gets 0.49 weighted F1. Forward log-returns are continuous, signed, free of look-ahead, and trivially evaluable as a regression with a t-statistic. The only reason to keep ZigZag is sunk cost."

## 📊 Trader
> "What I actually trade is a *direction with a horizon and a size*. ZigZag gives me a class. Forward return at 1h gives me a direction *and an implied magnitude*, which is what position sizing needs anyway. I don't need a model that predicts where the next reversal is — that's a fortune-teller's job. I need a model that predicts whether the next bar's close is above or below this one, with calibrated probability. Forward return wins on every dimension I care about."

## ⚙️ Engineer
> "ForwardReturnLabeler is 60 lines of code. ZigZag is 150 plus all the leakage-prevention scaffolding. The label that doesn't require leakage prevention by construction is the better label."

## Disagreement & resolution
None. All three converge. This is the cleanest kill in the document.

## Verdict: **KILL — replace with `ForwardReturnLabeler`**

Already in PHASE6 plan as Task B2. The decortication confirms it without reservation.

## KPI to track
**Label-quality lift:** Δ(OOS Sharpe) when the *only* change between two model runs is the labeler. Run Ridge baseline twice — once with ZigZag labels, once with forward-return labels. Same features, same windows, same hyperparameters.

- **Source:** MLflow runs tagged `labeler=zigzag` vs `labeler=forward_return`.
- **Cadence:** one-time A/B at end of Workstream B; report in `docs/phase6/labeler_ablation.md`.
- **Decision rule:** if forward-return doesn't beat ZigZag by ≥ 0.3 OOS Sharpe at this stage, the problem is upstream of labels (probably features or regime mismatch), not the labels.

## 📊 Dashboard widget — **LabelDistributionCard.tsx**

```tsx
// dashboard/src/components/LabelDistributionCard.tsx
import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import axios from "axios";

type LabelRow = { label: string; count: number; pct: number };

const COLORS: Record<string, string> = { up: "#10b981", flat: "#6b7280", down: "#ef4444",
  peak: "#f59e0b", valley: "#3b82f6", neither: "#6b7280" };

export default function LabelDistributionCard({ labeler }: { labeler: "zigzag" | "forward_return" }) {
  const { data } = useQuery<LabelRow[]>({
    queryKey: ["label-dist", labeler],
    queryFn: () => axios.get(`/api/ml/label_distribution?labeler=${labeler}&symbol=CrudeOIL&timeframe=H1`).then(r => r.data),
    refetchInterval: 300_000,
  });

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <h3 className="mb-2 text-lg font-semibold text-zinc-100">Label Distribution — {labeler}</h3>
      <p className="mb-4 text-xs text-zinc-400">
        Healthy 3-class targets sit roughly 30/40/30. Classes below 5% are signs of label rot.
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="count" nameKey="label" outerRadius={80} label={(e: any) => `${e.label} ${(e.pct * 100).toFixed(1)}%`}>
            {data?.map((row, i) => <Cell key={i} fill={COLORS[row.label] ?? "#9ca3af"} />)}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
```

Render two side-by-side — one for `zigzag`, one for `forward_return` — for the visual A/B.

---

# Subsystem 3 — 43 Single-Symbol Features

## What we built 6 months ago
`src/ml/features/reversal_features.py` produces 43 features computed entirely from the symbol's own OHLCV history: returns, rolling statistics, ATR variants, RSI/MACD/Bollinger, candlestick body/wick ratios, time-of-day encodings. Pure single-symbol approach. Justified as "start simple, add cross-asset later." We never added cross-asset.

## Costs today
- **Feature staleness:** in flat regimes, 30+ of the 43 features are highly correlated and provide near-zero marginal information. Ablation work in Phase 6 C1 will quantify this.
- **Missed signal:** crude oil moves on DXY, VIX, BRENT spread, inventory reports, Trump posts. None of these are in the feature vector.
- **Cross-feature redundancy:** RSI(14), RSI(20), RSI(30), MACD, Stochastic, Williams %R — these are all measuring approximately the same thing on different windows. Tree models will pick one and ignore the others; linear models get noisy coefficients.

## Evidence from 6 months
- **Best-performing model in 6 months of training (XGB-conservative on H1):** 79.37% win rate in *backtest*. Live F1 0.089. The features are strong on the training distribution, weak on live.
- We have **DXY, VIX, BRENT, USA500 in the database**, with the BC feeds restored and current. Adding them to the feature pipeline is plumbing, not research.
- **Feature importance from the existing XGB model:** top 5 features are all variants of returns and ATR. The next 38 are noise. This screams *we don't have enough information density*.

## 🎓 Quant
> "Single-symbol features on a 1-hour timeframe in a flat market is a degenerate problem. The signal-to-noise ratio is fixed by physics — you cannot improve it with another return-derived feature. Cross-asset features are not optional; they are the only path to higher information density without changing the timeframe. Add them. Run an ablation. The cross-asset block must beat the single-symbol block on OOS Sharpe by ≥ 0.4 to justify the complexity, or we revert."

## 📊 Trader
> "Crude oil traders watch DXY and BRENT spread before they watch anything else on their own chart. The reason your model has F1 0.089 is that it's looking at exactly the wrong screen. Cross-asset isn't a 'nice to have' — it's the table stakes. Also: drop the candlestick wick-ratio features. No one trades a wick ratio in 2026. They were a 1990s idea and they survive only because of pattern-recognition trading folklore."

## ⚙️ Engineer
> "I'd push back on the wick-ratio death sentence — features that don't help also don't hurt much in a tree model with proper regularization, and removing them changes the feature_hash, which forces a full retrain everyone has to keep track of. *Add* the cross-asset features cleanly first. Drop the dead ones in a separate, isolated PR after we have a baseline."

## Disagreement & resolution
The Trader wants to delete dead features now. The Engineer wants to add new features first, delete dead ones later, in separate PRs to keep the experimental story clean. The Quant sides with the Engineer for **statistical hygiene**: "don't change two things at once or you can't attribute the lift."

**Resolution:** PHASE6 B1 adds cross-asset cleanly. Phase 7 ablation removes dead single-symbol features once we have a baseline that includes both blocks.

## Verdict: **REFACTOR** — already scheduled in PHASE6 B1

The decortication adds one nuance: **enforce sequencing.** Add cross-asset, run ablation, then prune. Don't prune-and-add in the same PR.

## KPI to track
**Cross-asset-feature-importance fraction (CAFIF)** = sum of feature importances of cross-asset features / sum of all importances. If CAFIF < 0.15, cross-asset features aren't pulling weight and we should investigate (probably timing/lag misalignment).

- **Source:** MLflow logged feature importances per training run.
- **Cadence:** every nightly retrain.
- **Decision rule:** CAFIF target ≥ 0.25 within 4 weeks of B1 landing.

## 📊 Dashboard widget — **FeatureImportanceCard.tsx**

```tsx
// dashboard/src/components/FeatureImportanceCard.tsx
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import axios from "axios";

type FeatRow = { feature: string; importance: number; group: "price" | "indicator" | "cross_asset" | "time" | "phase" };

const GROUP_COLORS: Record<string, string> = {
  cross_asset: "#3b82f6", price: "#10b981", indicator: "#a855f7", time: "#f59e0b", phase: "#ec4899",
};

export default function FeatureImportanceCard({ modelId }: { modelId: string }) {
  const { data } = useQuery<FeatRow[]>({
    queryKey: ["feat-importance", modelId],
    queryFn: () => axios.get(`/api/ml/feature_importance?model_id=${modelId}&top_n=20`).then(r => r.data),
    refetchInterval: 300_000,
  });

  const cafif = data
    ? data.filter(d => d.group === "cross_asset").reduce((s, d) => s + d.importance, 0) /
      data.reduce((s, d) => s + d.importance, 0)
    : 0;

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">Top 20 Features — {modelId}</h3>
        <span className={`rounded px-2 py-1 text-xs ${cafif >= 0.25 ? "bg-emerald-700" : cafif >= 0.15 ? "bg-amber-700" : "bg-red-700"}`}>
          CAFIF {(cafif * 100).toFixed(1)}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={420}>
        <BarChart data={data} layout="vertical" margin={{ left: 140 }}>
          <XAxis type="number" />
          <YAxis type="category" dataKey="feature" width={140} tick={{ fontSize: 10 }} />
          <Tooltip />
          <Bar dataKey="importance">
            {data?.map((row, i) => <Cell key={i} fill={GROUP_COLORS[row.group]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2 flex gap-3 text-xs text-zinc-400">
        {Object.entries(GROUP_COLORS).map(([g, c]) => (
          <span key={g}><span className="inline-block h-2 w-2 rounded" style={{ background: c }} /> {g}</span>
        ))}
      </div>
    </div>
  );
}
```

The CAFIF badge in the corner is the "is the upgrade paying off" indicator.

---

# Subsystem 4 — Backtest Synthetic Engine

## What we built 6 months ago
`src/services/backtesting/` (≈ 2,800 lines) implements walk-forward, Monte Carlo, sensitivity analysis, rolling-window optimization. Justified as institutional-grade backtest discipline. The engine fills orders at the candle close with no slippage, no spread, no broker premium.

## Costs today
- **2,800 lines of backtest code** with its own data loaders, fill simulator, performance attribution
- **Reported metrics that don't survive contact with paper:** +156% backtest, F1 0.089 live
- **Risk of self-deception:** every "improvement" we measure here may not exist in the live execution distribution

## Evidence from 6 months
- The backtest harness has run the same strategies the live loop runs. Backtest says +156%. Live says 2 trades. The harness is — at minimum — overestimating signal frequency.
- **Broker premium is not modeled.** ForTrade's ~3% pricing offset during P2 (proven structural in this session) means our backtest's fill prices were systematically off by 3%, but we still reported the resulting Sharpe as if real.
- **Spread is hardcoded to a constant.** During Phase 5 (Hormuz crisis) intraday std was 10× normal. Backtest didn't see it.

## 🎓 Quant
> "A backtest that doesn't include realistic transaction costs, slippage as a function of volatility, and broker-specific premium is decorative. It produces a number with two decimal places and the appearance of rigor. Walk-forward and Monte Carlo over a wrong fill model just give you walk-forward and Monte Carlo of the wrong number. Fix the cost model first. Until then, *every* backtest result in `docs/` should carry a 'cost-naive' watermark."

## 📊 Trader
> "I have a $7,403 account. The difference between a 0.1% spread assumption and a 0.4% reality is the difference between a winning system and a losing one. The Hormuz period had 10× normal intraday std and we modeled it as if it were normal. That's not a small bug — that's the whole game. The right backtest includes the *worst* execution we observed in live, not the *average*. If the strategy clears that bar, it has actual edge."

## ⚙️ Engineer
> "Don't rewrite the backtest engine. Add a `cost_model` injection point: a function `(bar, position_size, side) -> filled_price`. Default it to a calibrated paper-mode model that uses recent observed spread. Backtest the same strategies and compare. Cheap diff, surgical change, full audit trail."

## Disagreement & resolution
The Quant wants every existing backtest result watermarked as "cost-naive" — a documentation chore. The Engineer wants a code change that makes the cost-naive vs cost-aware comparison tangible. The Trader sides with the Engineer because **a number on a dashboard beats a watermark in a doc.**

**Resolution:** PHASE6 C4 (MLflow trading-KPI integration) already mandates *paper-mode broker assumptions*. Extend that into the backtest engine itself. Every existing backtest result stays accessible but is tagged `cost_model=naive_v1`. New runs use `cost_model=paper_calibrated_v1`. Dashboard shows both. The gap between them is a measurement, not an embarrassment.

## Verdict: **REFACTOR** — inject a cost model, run cost-naive vs cost-aware in parallel for the same strategy

## KPI to track
**Backtest-vs-paper realism gap:** for any strategy that has ≥ 30 paper-mode resolved trades, compute |backtest_PF − paper_PF| / paper_PF. Below 0.2 = realistic. Above 0.5 = we cannot trust the backtest.

- **Source:** join MLflow runs (backtest PF) with `trading_history` rolled up by strategy_version (paper PF).
- **Cadence:** weekly, only for strategies with ≥ 30 resolved trades.
- **Decision rule:** if any active strategy's gap > 0.5, freeze backtest-driven decisions for that strategy until the cost model is corrected.

## 📊 Dashboard widget — **BacktestVsPaperGapCard.tsx**

```tsx
// dashboard/src/components/BacktestVsPaperGapCard.tsx
import { useQuery } from "@tanstack/react-query";
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from "recharts";
import axios from "axios";

type StratRow = { strategy_version: string; backtest_pf: number; paper_pf: number; n_trades_paper: number };

export default function BacktestVsPaperGapCard() {
  const { data } = useQuery<StratRow[]>({
    queryKey: ["backtest-paper-gap"],
    queryFn: () => axios.get("/api/ml/backtest_vs_paper_gap").then(r => r.data),
    refetchInterval: 300_000,
  });

  const colorFor = (r: StratRow) => {
    if (r.n_trades_paper < 30) return "#6b7280";
    const gap = Math.abs(r.backtest_pf - r.paper_pf) / Math.max(r.paper_pf, 0.01);
    return gap < 0.2 ? "#10b981" : gap < 0.5 ? "#f59e0b" : "#ef4444";
  };

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <h3 className="mb-2 text-lg font-semibold text-zinc-100">Backtest PF vs Paper PF</h3>
      <p className="mb-4 text-xs text-zinc-400">Diagonal = honest backtest. Above the line = optimistic. Grey = sample too small to judge.</p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <XAxis dataKey="paper_pf" name="Paper PF" type="number" domain={[0, 5]} />
          <YAxis dataKey="backtest_pf" name="Backtest PF" type="number" domain={[0, 5]} />
          <ZAxis dataKey="n_trades_paper" range={[40, 200]} />
          <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 5, y: 5 }]} stroke="#52525b" strokeDasharray="3 3" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <Scatter data={data}>
            {data?.map((row, i) => <Cell key={i} fill={colorFor(row)} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
```

The diagonal line is the truth-axis. Distance from it is dishonesty (or sample noise — hence the size encoding for trade count).

---

# Subsystem 5 — Stealth Stop Manager (ATR + Random Offset)

## What we built 6 months ago
`src/services/stealth_stop_manager.py` calculates stops as `entry ± k × ATR + uniform_random(5, 15)_pips`. Justified by the institutional anti-stop-hunt literature (Schmidt 2011 "Order book imbalance and stop-loss runs," various retail trader anecdotes about stops being hunted at round numbers).

## Costs today
- **One file, ~600 lines** with its own ATR calculator, random offset distribution, side-aware stop placement
- **Configuration:** `config/stealth_stops.yaml` with per-symbol parameters
- **Mental tax:** the random offset means two paper positions opened at the same price have different stops. Hard to reason about, easy to bug.

## Evidence from 6 months
- **Anti-stop-hunt was one of the original 6 fakes (it used to use hardcoded ATR; now it uses real ATR — fixed).**
- We have *insufficient sample* to claim stop-hunting was real or that random offsets prevented it. With 2 paper signals in 17 days, we have not actually been stopped out enough times to test the hypothesis.
- Real-money trades on the live account (the small live phase before paper) had **stops triggered within 2 pips of the placed stop in 14 out of 22 cases** (~64%). That's suggestive of stop-hunting **or** of normal market noise.

## 🎓 Quant
> "The stop-hunt thesis is a real phenomenon at retail brokers but it's most prevalent on round numbers (00, 50). The literature shows the random offset of 5-15 pips defeats hunting on the round-number levels. The technique is correct in principle. The question is whether our 64% near-stop trigger rate on the live account is hunting or just realized volatility. The way to tell is to compare stop-trigger rate at random offsets vs no offset on the same period. We never did that ablation."

## 📊 Trader
> "Anti-stop-hunt is institutional folklore. It's plausible. I've seen it happen. I've also seen traders blame stop-hunting for stops that were just badly placed. The bigger problem with our stops is the **k × ATR multiplier**, not the offset. We use 2× ATR by default. In the Hormuz period that translated to 10× tighter stops than the realized move because ATR(20) hadn't caught up to the regime. **The volatility-regime-aware stop is more important than the random offset.**"

## ⚙️ Engineer
> "600 lines for stops is reasonable. The random offset costs 3 lines and obscures nothing important. **Keep it.** What I'd add: log every stop placement with `(stop_distance_atr_units, random_offset_pips, regime_at_placement)` so we can run the Quant's ablation later when we have data."

## Disagreement & resolution
Quant wants an ablation we don't have data for. Trader wants to refocus on the ATR-multiplier-vs-regime issue. Engineer wants to instrument and wait. **All three agree on instrument-and-wait.** The Trader's ATR-multiplier point is the higher-leverage critique, but it's a parameter tune, not an architectural change.

## Verdict: **KEEP**, instrument firing rate and ATR-vs-realized-move ratios

## KPI to track
**Stop-hit-distribution:** for every stopped-out trade, log `(stop_distance_pips, realized_excursion_pips, atr_at_entry, random_offset_pips, regime)`. Render a histogram of `realized_excursion / atr_at_entry`. If the mode is at 1.0 (i.e., price almost exactly hits stop and reverses), that's stop-hunting. If the mode is at 2-3 (price runs past), our stops are too tight.

- **Source:** new instrumentation in `stealth_stop_manager.py` writing to `decision_log` on every fill.
- **Cadence:** weekly histogram once we have ≥ 50 stopped trades.
- **Decision rule:** if mode at 1.0, double down on anti-hunt logic (and consider hidden stops). If mode at 3+, increase k from 2.0 to 2.5.

## 📊 Dashboard widget — **StopHitDistributionCard.tsx**

```tsx
// dashboard/src/components/StopHitDistributionCard.tsx
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import axios from "axios";

type Bucket = { excursion_atr: number; count: number };

export default function StopHitDistributionCard() {
  const { data } = useQuery<{ buckets: Bucket[]; n_total: number; mode: number }>({
    queryKey: ["stop-hit-dist"],
    queryFn: () => axios.get("/api/risk/stop_hit_distribution?lookback_days=30").then(r => r.data),
    refetchInterval: 300_000,
  });

  const huntZone = data?.mode != null && Math.abs(data.mode - 1.0) < 0.15;
  const tightStop = data?.mode != null && data.mode > 2.5;

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <h3 className="mb-2 text-lg font-semibold text-zinc-100">Stop-Hit Distribution (n={data?.n_total ?? 0})</h3>
      <p className="mb-4 text-xs text-zinc-400">
        Realized excursion / ATR at entry. Mode at 1.0 = stop-hunting. Mode at 3+ = stops too tight.
      </p>
      {huntZone && <p className="mb-2 text-xs text-amber-400">⚠ Mode near 1.0 — stop-hunt suggested. Investigate hidden stops.</p>}
      {tightStop && <p className="mb-2 text-xs text-amber-400">⚠ Mode &gt; 2.5 — stops too tight. Consider k = 2.5×ATR.</p>}
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data?.buckets}>
          <XAxis dataKey="excursion_atr" tickFormatter={v => `${v}×`} />
          <YAxis />
          <Tooltip />
          <ReferenceLine x={1.0} stroke="#ef4444" strokeDasharray="3 3" label="hunt zone" />
          <Bar dataKey="count" fill="#3b82f6" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

# Subsystem 6 — Kelly Position Sizing

## What we built 6 months ago
`src/risk/risk_manager.py` Kelly sizing: `f* = (p × b − q) / b`, where p = win rate, b = avg_win/avg_loss, q = 1 − p. Capped at 2% account risk per trade. Justified by Thorp 1969 / Kelly 1956 lineage. For most of 2026 the inputs `p` and `b` were derived from the *fake ML confidence* (0.75) — meaning Kelly was sizing on a number that did not exist. This was Fake #6.

## Costs today
- **Kelly inputs are now real** (post-fakes-elimination): `p` from rolling trade history, `b` from realized win/loss ratio
- **The 2% cap dominates Kelly almost always** at our trade frequency — Kelly suggests fractional positions of 5-15%, the cap clips to 2%
- Effectively we have a 2% fixed-risk system with Kelly providing a no-op signal

## Evidence from 6 months
- 2 paper signals in 17 days = Kelly inputs are computed on a sample of effectively zero recent trades
- The rolling window of trade history needed for stable Kelly inputs is at least 30 trades. We have not had 30 paper trades in 90 days.
- **Until we hit ≥ 30 trades, Kelly inputs are dominated by sample noise**, and the safe behavior is to fall back to fixed 1-2% per trade.

## 🎓 Quant
> "Kelly is a beautiful theory built on a stationary distribution assumption that financial returns violate. The 2% cap is doing the actual work. Even with 1,000 trades, Kelly on noisy financial returns produces position sizes that wildly overshoot in drawdown periods. The literature on fractional Kelly (Thorp 2006) suggests 0.25× Kelly is the realistic operating point. **Set the cap to min(0.25 × Kelly, 2%) and forget it.**"

## 📊 Trader
> "Position sizing wins or loses more money than entries. Fixed-fractional sizing at 1% is the boring answer that beats Kelly empirically in most published studies (Carver 2015, *Systematic Trading*). My take: **kill Kelly. Use a 1% fixed-risk per trade until we have 100+ trades, then re-evaluate**. The complexity-to-payoff ratio of Kelly at our trade volume is bad."

## ⚙️ Engineer
> "Don't rewrite. Add a feature flag: `position_sizing.method = {kelly, fixed_fractional, hybrid}`. Default to `hybrid` = `min(0.25 × Kelly, 1%)` until trade count > 100. Switch to `kelly` after that. Five lines of code, full A/B-able, no information lost."

## Disagreement & resolution
Quant and Trader both want to demote Kelly. Engineer wants it behind a feature flag. **Engineer wins** because the feature-flag approach lets us measure the difference instead of guessing.

## Verdict: **KEEP Kelly behind a feature flag, default to `hybrid` (0.25 × Kelly capped at 1%) until n_trades ≥ 100**

## KPI to track
**Sizing-attribution:** fraction of account-equity P&L that comes from sizing decisions vs. signal accuracy. Compute as: realized P&L − P&L of same trades sized at constant 1%. If sizing is adding less than 0.1× the equity P&L, it's not earning its complexity.

- **Source:** `trading_history` with `position_size_pct` and `sizing_method` columns.
- **Cadence:** monthly.
- **Decision rule:** if attribution is negative for 3 months, force `fixed_fractional`.

## 📊 Dashboard widget — **SizingAttributionCard.tsx**

```tsx
// dashboard/src/components/SizingAttributionCard.tsx
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from "recharts";
import axios from "axios";

type Point = { date: string; cumulative_pnl_actual: number; cumulative_pnl_constant_1pct: number };

export default function SizingAttributionCard() {
  const { data } = useQuery<Point[]>({
    queryKey: ["sizing-attribution"],
    queryFn: () => axios.get("/api/risk/sizing_attribution?lookback_days=90").then(r => r.data),
    refetchInterval: 300_000,
  });

  const last = data?.[data.length - 1];
  const lift = last ? last.cumulative_pnl_actual - last.cumulative_pnl_constant_1pct : 0;

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">Sizing Attribution (90d)</h3>
        <span className={`rounded px-2 py-1 text-xs ${lift > 0 ? "bg-emerald-700" : "bg-red-700"}`}>
          {lift >= 0 ? "+" : ""}${lift.toFixed(0)} vs 1% fixed
        </span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Legend />
          <ReferenceLine y={0} stroke="#52525b" />
          <Line type="monotone" dataKey="cumulative_pnl_actual" stroke="#3b82f6" name="Actual (Kelly hybrid)" dot={false} />
          <Line type="monotone" dataKey="cumulative_pnl_constant_1pct" stroke="#9ca3af" name="Counterfactual (1% fixed)" dot={false} strokeDasharray="3 3" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

# Subsystem 7 — Risk Overseer Correlation Gate

## What we built 6 months ago
`src/agents/supervisory/risk_overseer.py` ran a 20-day rolling correlation matrix across all traded instruments and blocked any new position that would push aggregate correlated exposure above 60%. Justified by classical portfolio risk literature.

## Costs today
- **One file, ~400 lines** with correlation cache, exposure calculator, veto logic
- **The correlation values were faked at 0.2** for most of 2026 (Fake #4). Now real, but...
- **The gate has fired zero times in production** (because we have 1-2 positions/symbol/week max — never enough simultaneity to trigger)

## Evidence from 6 months
- **Zero correlation-gate fires** in `decision_log`
- The correlation matrix is computed continuously and consumes background CPU for a feature that has never been used
- At our trade frequency, the only time correlation matters is on a multi-leg crisis-replay strategy (Phase 3 territory) — not for individual trades on 3 live symbols

## 🎓 Quant
> "A correlation gate that has never fired is a gate that doesn't exist. It's worse than not having it — it gives us a false sense that we have portfolio risk management when in practice we have only fixed-fractional sizing per trade. Either make it observable (so we'd notice it firing) or kill it."

## 📊 Trader
> "Correlation gates matter when you have 5+ correlated positions during a regime shift. We don't, today. We will, when Phase 7 brings BRENT_OIL_H1 and the spread strategies online. **Don't kill it — instrument it.** Right now no one knows it's there. Make it visible. When it doesn't fire for 30 days running, we'll know to revisit. When Phase 7 brings 5 strategies online, we'll be glad we kept it."

## ⚙️ Engineer
> "The Trader's path is the right one. Add a single counter to the existing module: `correlation_gate.firings_per_day`. Surface it on the risk dashboard. Cost: 10 lines. The gate stays, with an exit condition (30 days no firings → reconsider)."

## Disagreement & resolution
Quant wants to kill it. Trader and Engineer agree on instrument-and-keep. **Trader/Engineer win** because the cost of keeping is small and Phase 7 makes it relevant.

## Verdict: **REFACTOR — make it observable, add 30-day no-fire reconsider trigger**

## KPI to track
**Correlation-gate-firing-rate:** count of vetoed signals per week. Below 1/month for 3 months = the gate is decorative; revisit.

- **Source:** new column `vetoed_by` in `decision_log`.
- **Cadence:** weekly.

## 📊 Dashboard widget — **CorrelationGateCard.tsx**

```tsx
// dashboard/src/components/CorrelationGateCard.tsx
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import axios from "axios";

type Point = { date: string; firings_today: number; cumulative_30d: number };

export default function CorrelationGateCard() {
  const { data } = useQuery<{ daily: Point[]; total_30d: number; status: "active" | "decorative" }>({
    queryKey: ["corr-gate"],
    queryFn: () => axios.get("/api/risk/correlation_gate_activity?lookback_days=30").then(r => r.data),
    refetchInterval: 600_000,
  });

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">Correlation Gate (30d)</h3>
        <span className={`rounded px-2 py-1 text-xs ${data?.status === "active" ? "bg-emerald-700" : "bg-zinc-700"}`}>
          {data?.total_30d ?? 0} firings / decorative status: {data?.status ?? "—"}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data?.daily}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <ReferenceLine y={1} stroke="#f59e0b" strokeDasharray="3 3" label="alert floor" />
          <Line type="monotone" dataKey="firings_today" stroke="#3b82f6" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

# Subsystem 8 — MT4 ZMQ Bridge

## What we built 6 months ago
ZMQ-based bridge to MT4 via custom MQL4 EA on the broker's MetaTrader 4 platform. REP socket on 5555 (commands), PUB socket on 5556 (streaming). Justified by ForTrade-broker compatibility and the absence of a usable broker REST API. Documented as security-fragile (no encryption, IP-exposed) and explicitly flagged for Phase 4 hardening.

## Costs today
- **Public IP exposure:** 75.154.254.174:5555 reachable from the open internet
- **No encryption:** ZMQ CurveZMQ keys defined in env but never wired
- **Single broker lock-in:** the EA is MT4-specific; switching brokers requires rewriting the EA
- **Latency:** 5-15ms LAN, 60-180ms remote — fine for H1 trading, dangerous for sub-minute strategies

## Evidence from 6 months
- The bridge has **worked reliably** at our trade frequency. Zero corruption events. No security incidents observed.
- The exposure remains a real risk, not a hypothetical one
- **At 2 trades / 17 days, latency is not a constraint.** At 100 trades/day (Phase 7+ ambition) it might be.

## 🎓 Quant
> "Latency-dependent strategies are not in scope until at least Phase 4. The bridge is fine for H1 and slower. **Security is the only concern,** and it's not a research issue, it's an engineering issue."

## 📊 Trader
> "I trade against ForTrade. ForTrade only supports MT4. There is no alternative. The bridge stays. Replace it the day I have a multi-broker strategy or a sub-minute timeframe — neither is anywhere on the roadmap."

## ⚙️ Engineer
> "Two priorities: (1) put it behind a Tailscale or WireGuard tunnel today — eliminates the public IP exposure with zero code change. (2) Phase 8: replace MT4 with a broker that has a real REST API. There are 3 viable candidates. **Don't rewrite the bridge in Phase 6.** Tunnel it and move on."

## Disagreement & resolution
None. All three agree: **Phase 6 keeps the bridge, Phase 6 adds the tunnel, Phase 8 plans replacement.**

## Verdict: **KEEP, tunnel via WireGuard/Tailscale in Phase 6, replace broker in Phase 8**

The tunnel is a 1-day infrastructure task, not part of Phase 6 software workstreams. Track separately.

## KPI to track
**MT4-bridge-uptime:** % of expected ticks received per minute over a rolling 24h window.

- **Source:** `mt4_connections` heartbeats + `market_data` insert rate.
- **Cadence:** continuous.
- **Decision rule:** uptime < 99.5% for any 1h window = page someone.

## 📊 Dashboard widget — **MT4BridgeHealthCard.tsx**

```tsx
// dashboard/src/components/MT4BridgeHealthCard.tsx
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import axios from "axios";

type Point = { ts: string; uptime_pct: number; latency_ms: number };

export default function MT4BridgeHealthCard() {
  const { data } = useQuery<{ points: Point[]; current_uptime: number; current_latency: number; status: "ok" | "degraded" | "down" }>({
    queryKey: ["mt4-bridge-health"],
    queryFn: () => axios.get("/api/mt4/bridge_health?lookback_hours=24").then(r => r.data),
    refetchInterval: 30_000,
  });

  const colour = data?.status === "ok" ? "bg-emerald-700" : data?.status === "degraded" ? "bg-amber-700" : "bg-red-700";

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">MT4 Bridge Health (24h)</h3>
        <span className={`rounded px-2 py-1 text-xs ${colour}`}>
          {data?.current_uptime?.toFixed(2) ?? "—"}% / {data?.current_latency?.toFixed(0) ?? "—"} ms
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data?.points}>
          <XAxis dataKey="ts" tick={{ fontSize: 10 }} />
          <YAxis yAxisId="left" domain={[95, 100]} />
          <YAxis yAxisId="right" orientation="right" />
          <Tooltip />
          <ReferenceLine yAxisId="left" y={99.5} stroke="#f59e0b" strokeDasharray="3 3" label="SLA" />
          <Line yAxisId="left" type="monotone" dataKey="uptime_pct" stroke="#10b981" dot={false} name="Uptime %" />
          <Line yAxisId="right" type="monotone" dataKey="latency_ms" stroke="#3b82f6" dot={false} name="Latency ms" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

# Subsystem 9 — PostgreSQL Time-Series Schema

## What we built 6 months ago
Plain PostgreSQL 15 with `market_data` partitioned by symbol+date, `indicators` cached, OHLCV float32 downcasting at the application layer. Justified by "boring tech wins, TimescaleDB adds operational complexity we don't need yet."

## Costs today
- **13.5M rows** in `market_data` across 11 instruments and 5 timeframes
- **Query latency:** typical aggregation queries (e.g., last-30d-of-CrudeOIL-H1) return in 50-200ms
- **Storage:** ~6 GB total. Trivial.

## Evidence from 6 months
- The DB has handled every workload thrown at it without tuning beyond the obvious indices
- We were warned 6 months ago that PG would not scale to 100M+ rows for time-series. We're at 13.5M and the warning is starting to feel pre-emptive
- Restoring the BC feeds for DXY/VIX/XAUUSD added ~500K rows. Performance unchanged.

## 🎓 Quant
> "PostgreSQL is fine until it isn't. The transition pain (TimescaleDB hypertables, ClickHouse, Parquet+DuckDB) is real. **Stay with Postgres until query latency on actual research workloads exceeds 5 seconds.** We are at 200ms. Not close."

## 📊 Trader
> "I run two SQL queries a day. The DB could be SQLite and I would not notice. Don't waste a sprint on this."

## ⚙️ Engineer
> "Add a single index review pass — `EXPLAIN ANALYZE` on the 5 most common query patterns from the API. Make sure they hit the right indices. That's it. **Postgres at 13.5M rows is well-behaved.** Revisit at 100M."

## Disagreement & resolution
None. Universal consensus.

## Verdict: **KEEP**

## KPI to track
**P95 market_data query latency** in the API layer.

- **Source:** existing Prometheus metrics on FastAPI request timing.
- **Cadence:** continuous, alert at p95 > 1s.

## 📊 Dashboard widget — already covered by existing Prometheus/Grafana stack. No new widget required.

---

# Subsystem 10 — Redis Pub/Sub for Agent Communication

## What we built 6 months ago
Redis pub/sub channels for inter-agent messaging: `tick.received`, `signal.generated`, `trade.validated`, `trade.executed`, etc. Justified by the multi-agent architecture and a hypothetical future where agents run on separate hosts.

## Costs today
- **Critical-path Redis dependency** for what is, today, in-process Python communication
- **Three Python processes** that could be one
- **A subscriber lifecycle bug** earlier in 2026 caused 2 missed signals (logged, fixed)
- **Operational overhead:** Redis health check, connection retry, dead-letter handling, pub/sub vs streams confusion

## Evidence from 6 months
- All "agents" run in the same VPS
- No agent has ever needed to be on a separate host
- The multi-agent architecture is being demoted to module-level (Subsystem 1) — pub/sub becomes function calls

## 🎓 Quant
> "If the agents collapse to modules, the pub/sub layer collapses to function calls. There's no statistical case for or against — it's purely engineering."

## 📊 Trader
> "I never even knew about Redis. I cared about whether the trade fired. It did. Or didn't. The middleware doesn't matter to me."

## ⚙️ Engineer
> "**Kill it.** When/if Phase 8 brings genuine multi-host deployment, replace it with the simplest thing that works (probably NATS, or just gRPC). Pub/sub for in-process Python is solving an imaginary problem and creating a real one (Redis as a critical dependency). The actual P&L cost of the missed-signals bug from earlier this year was ~$200. We've spent more than that maintaining the framework."

## Disagreement & resolution
None. Universal kill.

## Verdict: **KILL — collapse to in-process asyncio function calls**

This is the cleanest deletion in the document. ~600 lines of pub/sub infrastructure go away. Redis stays for *caching* (feature vectors, indicator values) — that's the appropriate use of Redis at our scale.

## KPI to track
**Inter-module-call-latency:** p95 latency from `signal_generator.emit()` to `risk_manager.validate()` to `execution.send()`. After kill, this becomes a single Python stack trace.

- **Source:** structlog tracing.
- **Cadence:** continuous.
- **Decision rule:** if p95 > 100ms after kill, something is wrong (was 5-50ms via Redis pub/sub).

## 📊 Dashboard widget — already covered by existing tracing. No new widget required.

---

# Subsystem 11 — React + TradingView Dashboard

## What we built 6 months ago
React 18 + Vite + TypeScript + React Query + Zustand + Recharts + lightweight-charts + Tailwind. Justified by "professional production dashboard."

## Costs today
- **A real frontend codebase** with build pipeline, dependency tree, type-checking, linting, hot-reload
- **One user.** Possibly two if the user shares with a partner.
- **Streamlit/Dash would have shipped a dashboard 8 weeks earlier.** Both are still viable for tomorrow's needs.

## Evidence from 6 months
- The dashboard works. It's nice. It uses lightweight-charts properly, the rendering is fast, the dev experience is fine.
- The Phase 6 plan needs **6-10 new widgets** specific to the architectural review (the ones in this document). Each widget at ~80 lines TSX is a 1-2 day task. In Streamlit each is ~30 lines and 30 minutes.
- The bigger constraint: **the user wants to see the model performance accuracy and results** (their actual words). That's not blocked by the framework — it's blocked by the *data not flowing* (Subsystem 4 cost-aware backtest, Subsystem 1 measurement APIs).

## 🎓 Quant
> "Doesn't matter. The dashboard is downstream. If the data and metrics are right, the rendering technology is irrelevant."

## 📊 Trader
> "I want to **see the model perform**. Whatever framework gets me a chart of paper-PF over time and a heatmap of feature importances and a side-by-side of backtest vs paper — that's the right framework. The current React stack does all three with the widgets in this document. I don't need to switch."

## ⚙️ Engineer
> "Switching now is sunk-cost reasoning in reverse. We have working React. Adding 10 widgets to working React is faster than rewriting in Streamlit. **Keep the framework, add the widgets, focus on the metrics not the chrome.**"

## Disagreement & resolution
The Quant doesn't care. Trader and Engineer agree to keep. **Keep wins.**

## Verdict: **KEEP, add the 10 widgets specified in this document**

## KPI to track
**Dashboard-widget-coverage:** ratio of (widgets specified in this doc that are deployed) / (total widgets specified).

- **Source:** static count.
- **Target:** 10/12 by end of Phase 6.

## 📊 Dashboard widget — meta-widget:

```tsx
// dashboard/src/components/PhaseSixWidgetCoverage.tsx
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

type WidgetStatus = { name: string; deployed: boolean; subsystem: number };

export default function PhaseSixWidgetCoverage() {
  const { data } = useQuery<WidgetStatus[]>({
    queryKey: ["widget-coverage"],
    queryFn: () => axios.get("/api/dashboard/phase6_widget_status").then(r => r.data),
  });
  const deployed = data?.filter(w => w.deployed).length ?? 0;
  const total = data?.length ?? 0;

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <h3 className="mb-2 text-lg font-semibold text-zinc-100">Phase 6 Widget Coverage</h3>
      <div className="mb-3 text-2xl font-bold text-zinc-100">{deployed} / {total}</div>
      <div className="flex flex-wrap gap-2">
        {data?.map(w => (
          <span key={w.name} className={`rounded px-2 py-1 text-xs ${w.deployed ? "bg-emerald-700" : "bg-zinc-700"}`}>
            #{w.subsystem} {w.name}
          </span>
        ))}
      </div>
    </div>
  );
}
```

---

# Subsystem 12 — Docker Compose + MLflow

## What we built 6 months ago
**Docker Compose** for service orchestration (API, PG, Redis, MCP server, agent coordinator, MLflow, dashboard, monitoring stack). **MLflow** for experiment tracking + model registry.

## Costs today
- **Compose file:** ~12 services. Half are observability (Prometheus, Grafana, Kibana, Jaeger, ELK).
- **Operational reality:** the user runs this on **one VPS**. The full observability stack is overkill for one user, one server.
- **MLflow:** legitimately useful for experiment tracking. Underused for model registry (we save artifacts to disk and put a metadata.json beside them — not via MLflow's registry API).

## Evidence from 6 months
- Compose has worked. Restarts are clean. The user uses `docker-compose restart api` regularly.
- Of the observability stack, **only Grafana is checked regularly.** Prometheus runs. Kibana, Jaeger, ELK have logged-but-rarely-viewed data.
- MLflow runs are created. They are not all consulted. The trading-KPI extension in PHASE6 C4 is the upgrade that makes MLflow earn its keep.

## 🎓 Quant
> "MLflow is the right call for experiment tracking. The registry is underused — that should be fixed in PHASE6 C3 (champion/challenger registry). Don't kill MLflow. **Use it.**"

## 📊 Trader
> "Compose works. Don't touch it. The observability stack is bloated for one user but the cost of removing services is non-zero (someone has to remember why we removed it next time we want it). Leave it. Run only what's useful, ignore the rest."

## ⚙️ Engineer
> "Compose with 12 services is fine on a single VPS. The only optimization I'd make: **document which services are 'must-run' vs 'nice-to-run'** and build a `docker-compose -f base.yml -f obs.yml up -d` split so a dev can run just the must-run set during local development. 1-day task. Saves ~3GB of RAM during dev cycles."

## Disagreement & resolution
None. Tweak Compose, keep MLflow, do not blow up either.

## Verdict: **KEEP both, split Compose files in Phase 7, extend MLflow with trading-KPIs in Phase 6 C4 (already planned)**

## KPI to track
**MLflow-trading-KPI-coverage:** % of model artifacts in MLflow that have trading-KPI sidecars (PF, Sharpe, Calmar, Sortino, max_DD, n_trades, avg_pl, win_rate). Target 100% for any artifact created after PHASE6 C4 lands.

- **Source:** MLflow API.
- **Cadence:** continuous.
- **Decision rule:** if any new artifact lacks the sidecar, the registration is rejected.

## 📊 Dashboard widget — **MLflowKPICoverageCard.tsx**

```tsx
// dashboard/src/components/MLflowKPICoverageCard.tsx
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

type Run = { run_id: string; model_name: string; created_at: string; has_trading_kpis: boolean; trading_pf: number | null };

export default function MLflowKPICoverageCard() {
  const { data } = useQuery<Run[]>({
    queryKey: ["mlflow-runs"],
    queryFn: () => axios.get("/api/ml/mlflow_runs?lookback_days=30").then(r => r.data),
    refetchInterval: 300_000,
  });

  const total = data?.length ?? 0;
  const withKpis = data?.filter(r => r.has_trading_kpis).length ?? 0;

  return (
    <div className="rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow">
      <h3 className="mb-2 text-lg font-semibold text-zinc-100">MLflow Trading-KPI Coverage</h3>
      <div className="mb-3 text-2xl font-bold text-zinc-100">{withKpis} / {total} runs</div>
      <table className="w-full text-xs">
        <thead className="text-zinc-400">
          <tr><th className="text-left">Run</th><th className="text-left">Model</th><th>KPIs</th><th>PF</th></tr>
        </thead>
        <tbody className="text-zinc-200">
          {data?.slice(0, 10).map(r => (
            <tr key={r.run_id}>
              <td className="font-mono text-[10px]">{r.run_id.slice(0, 8)}</td>
              <td>{r.model_name}</td>
              <td className="text-center">{r.has_trading_kpis ? "✅" : "❌"}</td>
              <td className="text-right">{r.trading_pf?.toFixed(2) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

# The 13th Section — The Capstone Dashboard

The 12 widgets above are point-tools. They each measure one subsystem. The **Capstone Dashboard** is the single page that answers "**is the system working today?**" — the page the user opens first thing every morning.

It contains exactly six widgets, in this order:

1. **Loop-Throughput** (Subsystem A1+A5 from PHASE6) — resolved trades per week per symbol, against the 10/week target
2. **Champion-vs-Ridge** (Subsystem 3+4 here) — PF of current champion vs the Ridge baseline, over 30 days
3. **Backtest-vs-Paper Gap** (Subsystem 4) — scatter from above
4. **Stop-Hit Distribution** (Subsystem 5) — histogram from above
5. **Sizing Attribution** (Subsystem 6) — line chart from above
6. **MT4 Bridge Health** (Subsystem 8) — uptime/latency strip

Code:

```tsx
// dashboard/src/pages/CapstonePhase6.tsx
import LoopThroughputCard from "../components/LoopThroughputCard";
import ChampionVsRidgeCard from "../components/ChampionVsRidgeCard";
import BacktestVsPaperGapCard from "../components/BacktestVsPaperGapCard";
import StopHitDistributionCard from "../components/StopHitDistributionCard";
import SizingAttributionCard from "../components/SizingAttributionCard";
import MT4BridgeHealthCard from "../components/MT4BridgeHealthCard";

export default function CapstonePhase6() {
  return (
    <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
      <LoopThroughputCard />
      <ChampionVsRidgeCard />
      <MT4BridgeHealthCard />
      <BacktestVsPaperGapCard />
      <StopHitDistributionCard />
      <SizingAttributionCard />
    </div>
  );
}
```

The two new widgets — `LoopThroughputCard` and `ChampionVsRidgeCard` — follow the same pattern as the others. They are the first two widgets to ship, because they answer the most important Phase 6 question: **is the loop alive, and does the model have edge?**

---

# Summary: What This Decortication Saves Us

| Action | Phase | Lines saved/added | Risk |
|--------|-------|-------------------|------|
| Kill Redis pub/sub for agent comms | 7 | −600 | low |
| Collapse 10 agents to 3 modules | 7 | −3,200 | medium (touches signal flow) |
| Replace ZigZag with ForwardReturnLabeler | 6 (B2) | −90 | low |
| Inject cost model into backtest | 6 (C4) | +250 | low |
| Add cross-asset features | 6 (B1) | +400 | low |
| Add 10 dashboard widgets | 6 | +800 | low |
| Hybrid Kelly + feature flag | 6 | +30 | low |
| Instrument correlation gate | 6 | +20 | none |
| Instrument stop-hit distribution | 6 | +30 | none |
| Tunnel MT4 bridge | 6 (infra) | 0 (config) | none |

**Net code at end of Phase 7:** −2,300 lines.
**Net measurement surface:** +12 first-class KPIs visible on the dashboard.

The plan is to **delete more than we add**, and to add only things that produce a number on a screen.

---

# What I Did Not Cover (Deliberately)

These are also architectural choices but they are downstream of getting the loop working and the metrics visible:

- **MLflow → Weights & Biases migration** — only relevant when team > 1
- **PostgreSQL → TimescaleDB migration** — only relevant when row count > 100M
- **Multi-broker abstraction layer** — only relevant when broker count > 1
- **Crisis-automator agent (Phase 3 specialist)** — premature; revisit when champion is producing trades
- **LSTM training infrastructure** — Docker OOM blocked it in Phase 5; revisit only if XGBoost+features tops out

If any of these become relevant during Phase 6 execution, they get their own decortication doc rather than sneaking into this one.

---

## Reference

- `PHASE6_LOOP_TO_AUTONOMY_MEGA_DELEGATION.md` — the execution plan
- `PHASE5_CRUDE_OIL_MEGA_DELEGATION.md` — prior plan precedent
- `.serena/memories/2026-04-29-mt4-broker-premium-and-correct-training-architecture.md` — the empirical work that this decortication is grounded in
- `CLAUDE.md` — absolute rules
- López de Prado, M. (2018). *Advances in Financial Machine Learning* — Chapter 3 on labeling, Chapter 7 on cross-validation
- Carver, R. (2015). *Systematic Trading* — sizing chapters
- Karpathy, A. (2019). *A Recipe for Training Neural Networks* — the Karpathy floor
