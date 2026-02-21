# Agent System - Current Status & Next Steps

**Date:** 2025-12-19
**Status:** Agents exist but disabled
**Complexity:** High (9-14 hours of work)

---

## Summary

Your RiseTrader agent system is **fully implemented** but currently **disabled** in the API. Enabling it and adding the requested UIs requires significant development across multiple areas:

1. ✅ **Agent code exists** - Coordinat, base classes, decision agents, debate teams all implemented
2. ❌ **Agent coordinator disabled** - Commented out in `/src/api/main.py` line 54
3. ❌ **No backtest creation UI** - Can only create via terminal/API
4. ❌ **No agent chat interface** - Decision logs exist in DB but no viewer
5. ❌ **No model switching UI** - Config file only

---

## What EXISTS (Already Implemented)

### Backend ✅
- **Agent Coordinator:** `/src/agents/agent_coordinator.py` (14KB, production-ready)
- **Agent Registry:** `/src/agents/agent_registry.py` (18KB)
- **Decision Agents:**
  - Fund Manager Agent (implemented)
  - Position Sizing Agent (implemented)
  - Debate Layer (bull/bear researchers)
- **Database Tables:**
  - `agent_decision_logs` (stores all agent decisions with reasoning)
  - `backtest_runs`, `backtest_configurations`
- **API Endpoints:**
  - `GET /api/agents/status` (exists, returns 503 because coordinator disabled)
  - `GET /api/backtesting/runs/{run_id}/decisions` (returns agent decisions)
  - `POST /api/backtesting/configurations` (create backtest)
  - `POST /api/backtesting/runs` (execute backtest)
- **Configuration:**
  - `/config/agents.yaml` (complete config with Ollama models)

### Frontend ✅
- **Backtesting Page:** `/dashboard/src/pages/Backtesting.tsx` (displays results)
- **API Client:** `/dashboard/src/api/endpoints.ts` (all backtest endpoints)

---

## What NEEDS to be Built

### 1. Enable Agent System (30 minutes)

**File:** `/src/api/main.py`
```python
# Line 52-56, change from:
# await init_agent_coordinator()

# To:
await init_agent_coordinator()
logger.info("agent_coordinator_initialized")
```

**Test:**
```bash
curl http://localhost:8003/api/agents/status
# Should return list of agents instead of 503 error
```

**Potential Issues:**
- Ollama connection might fail if URL wrong
- Config file might have errors
- Redis connection required

---

### 2. Create Backtest UI (3-4 hours)

**New Files Needed:**
1. `/dashboard/src/components/backtesting/CreateBacktestModal.tsx`
2. `/dashboard/src/components/backtesting/BacktestForm.tsx`

**UI Components:**
```typescript
interface BacktestFormData {
  name: string;
  symbol: 'CrudeOIL' | 'Gold' | 'EURUSD';
  startDate: Date;
  endDate: Date;
  initialCapital: number;
  executionMode: 'full_pipeline' | 'synthetic_fast';
  model?: 'qwen2.5:14b' | 'deepseek-r1:14b';
  timeframe: 'M5' | 'M15' | 'H1';
}
```

**Features:**
- Modal dialog with form
- Symbol dropdown
- Date range picker (react-datepicker)
- Execution mode toggle
- Model selector (only show if agent mode)
- Validation
- Submit & auto-navigate to results

**Integration:**
```typescript
const handleSubmit = async (data: BacktestFormData) => {
  // 1. Create configuration
  const config = await backtestApi.createConfiguration({
    name: data.name,
    symbol: data.symbol,
    start_date: data.startDate.toISOString(),
    end_date: data.endDate.toISOString(),
    initial_capital: data.initialCapital.toString(),
    execution_mode: data.executionMode,
    config_params: {
      agent_config: {
        model: data.model,
        ollama_base_url: "http://192.168.0.123:11434/v1"
      }
    }
  });

  // 2. Start backtest run
  const run = await backtestApi.runBacktest({
    config_id: config.id,
    timeframe: data.timeframe
  });

  // 3. Navigate to results
  navigate(`/backtesting/${run.run_id}`);
};
```

---

### 3. Agent Chat Interface (4-5 hours)

**New Files Needed:**
1. `/dashboard/src/pages/AgentChat.tsx` (main page)
2. `/dashboard/src/components/agents/AgentConversation.tsx` (chat layout)
3. `/dashboard/src/components/agents/AgentMessage.tsx` (single message)
4. `/dashboard/src/components/agents/DecisionTimeline.tsx` (timeline view)

**Data Source:**
```sql
-- Query agent_decision_logs table
SELECT
  id,
  agent_name,
  decision_type,
  reasoning,
  market_context,
  timestamp,
  backtest_run_id
FROM agent_decision_logs
WHERE backtest_run_id = ?
ORDER BY timestamp ASC;
```

**UI Layout:**
```
┌────────────────────────────────────────────────┐
│  Agent Interactions - CrudeOIL Backtest        │
│  Run: b02dc98d... | 2025-01-31 to 2025-02-01  │
├────────────────────────────────────────────────┤
│  Filters:                                       │
│  [Agent: All ▼] [Decision Type: All ▼]        │
├────────────────────────────────────────────────┤
│                                                 │
│  ┌─ 14:23:15 - Technical Analyst ──────────┐  │
│  │ 📊 Analysis                              │  │
│  │ "RSI showing bearish divergence at 72.5" │  │
│  │ Conviction: 0.65                         │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌─ 14:23:18 - Bull Researcher ────────────┐  │
│  │ 🐂 Bullish Argument                      │  │
│  │ "Strong support level at $72.00..."     │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌─ 14:23:20 - Bear Researcher ────────────┐  │
│  │ 🐻 Bearish Argument                      │  │
│  │ "Resistance at $75.00 likely to hold..." │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌─ 14:23:25 - Trade Decision Agent ───────┐  │
│  │ ✅ Final Decision: SELL                  │  │
│  │ Conviction: 0.75                         │  │
│  │ Size: 0.02 lots ($720 risk)             │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

**API Integration:**
```typescript
const { data: decisions } = useQuery({
  queryKey: ['agent-decisions', runId],
  queryFn: () => backtestApi.getRunDecisions(runId, { limit: 1000 }),
  enabled: !!runId
});

// Group decisions by timestamp/sequence
const conversationThreads = groupDecisionsByThread(decisions.items);
```

---

### 4. Model Switching (2 hours)

**UI Locations:**
1. **In CreateBacktestModal:** Dropdown to select model before starting
2. **In Settings Page:** Change default model for new backtests

**Backend Support:**
- Already supported via `config_params.agent_config.model`
- Agent coordinator reads model from config

**Example:**
```typescript
<Select
  label="LLM Model"
  value={selectedModel}
  onChange={setSelectedModel}
  options={[
    { value: 'qwen2.5:14b', label: 'Qwen 2.5 14B (Fast, Efficient)' },
    { value: 'deepseek-r1:14b', label: 'DeepSeek R1 14B (Better Reasoning)' },
    { value: 'llama3.1:70b', label: 'Llama 3.1 70B (Most Capable)' },
  ]}
/>
```

---

### 5. Better Results Display (2-3 hours)

**Enhancements Needed:**

1. **Equity Curve Chart:**
```typescript
<EquityCurveChart
  data={createEquityCurveData()}
  initialCapital={10000}
  finalCapital={runData.final_capital}
/>
```

2. **Trade List Table:**
```typescript
<TradeListTable
  trades={tradesData.items}
  columns={['Entry Time', 'Exit Time', 'Symbol', 'Type', 'P&L']}
/>
```

3. **Agent Decision Summary:**
```typescript
<AgentDecisionSummary
  totalDecisions={runData.agent_decisions_count}
  decisionsBreakdown={{
    buy: 15,
    sell: 12,
    hold: 35
  }}
/>
```

---

## Recommended Implementation Order

### Phase 1: Enable & Test Agents (Day 1, 2-3 hours)
1. Uncomment agent coordinator in main.py
2. Restart API and test `/api/agents/status`
3. Fix any Ollama connection issues
4. Test with simple backtest to verify agents work

### Phase 2: Backtest Creation UI (Day 1-2, 3-4 hours)
1. Create CreateBacktestModal component
2. Add form with validation
3. Wire up to API
4. Test creating and running backtest

### Phase 3: Agent Chat Interface (Day 2-3, 4-5 hours)
1. Create AgentChat page
2. Fetch decision logs from API
3. Display in conversation format
4. Add filtering and search

### Phase 4: Polish & Model Switching (Day 3, 2-3 hours)
1. Add model selector to create form
2. Improve results display
3. Add equity curve chart
4. Testing and bug fixes

**Total: 11-15 hours over 3 days**

---

## Quick Start (Minimal Viable Solution)

If you want the **absolute minimum** to get started:

### Step 1: Enable Agents (5 min)
```bash
# Edit /src/api/main.py line 54
# Change from: # await init_agent_coordinator()
# To: await init_agent_coordinator()

docker-compose restart api
curl http://localhost:8003/api/agents/status
```

### Step 2: Create Backtest via API (Terminal)
```bash
# Create configuration
curl -X POST http://localhost:8003/api/backtesting/configurations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Agent Backtest",
    "symbol": "CrudeOIL",
    "start_date": "2024-01-31T00:00:00Z",
    "end_date": "2024-02-01T00:00:00Z",
    "initial_capital": "10000",
    "execution_mode": "full_pipeline",
    "config_params": {
      "agent_config": {
        "model": "qwen2.5:14b",
        "ollama_base_url": "http://192.168.0.123:11434/v1"
      }
    }
  }'

# Run backtest (use config_id from response)
curl -X POST http://localhost:8003/api/backtesting/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "YOUR_CONFIG_ID",
    "timeframe": "M5"
  }'
```

### Step 3: View Decisions in Existing Backtest Page
```bash
# Navigate to http://localhost:3003/backtesting
# Click the backtest
# Look at "Agent Decisions" tab (if it exists)
```

---

## Files to Modify/Create

### Must Modify:
- [ ] `/src/api/main.py` (enable agent coordinator)

### Nice to Create:
- [ ] `/dashboard/src/components/backtesting/CreateBacktestModal.tsx`
- [ ] `/dashboard/src/components/backtesting/BacktestForm.tsx`
- [ ] `/dashboard/src/pages/AgentChat.tsx`
- [ ] `/dashboard/src/components/agents/AgentConversation.tsx`
- [ ] `/dashboard/src/components/agents/AgentMessage.tsx`

---

## Decision Point

You have two options:

### Option A: Quick Enable (30 min)
- Enable agent coordinator
- Create backtests via API/terminal
- View results in existing UI
- **Pros:** Fast, can test agents immediately
- **Cons:** No UI, manual process

### Option B: Full Implementation (11-15 hours)
- Everything in Option A
- Create backtest UI modal
- Agent chat interface
- Model switching
- Polished results display
- **Pros:** Complete feature set, great UX
- **Cons:** Significant development time

---

## My Recommendation

Start with **Option A** to verify agents work, then build the UI incrementally:

1. **Now:** Enable agents, test with API (30 min)
2. **Today:** Add "Create Backtest" button that opens a simple form (2 hours)
3. **Tomorrow:** Build agent chat interface (4 hours)
4. **Later:** Add model switching and polish (2 hours)

This gets you working agents TODAY and complete UI by end of week.

Would you like me to proceed with Option A (enable agents now) or jump straight to Option B (full implementation)?
