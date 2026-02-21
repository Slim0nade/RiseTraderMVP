# Agent System Implementation Plan

**Date:** 2025-12-19
**Status:** Planning
**Priority:** High

---

## Current State

### What's Working ✅
- Agent configuration file exists (`config/agents.yaml`)
- Ollama server running at `75.154.254.174:11434`
- Models available: `qwen2.5:14b`, `deepseek-r1:14b`
- Agent coordinator code exists but is disabled
- Backtest engine functional (can run synthetic backtests)

### What's Broken ❌
- Agent coordinator not initialized (commented out in `main.py`)
- No UI to create new backtests
- No agent chat/interaction viewer
- No model switching UI
- Agent decision logs exist in DB but no way to view them

---

## User Requirements

### 1. Working Agents with Local Ollama
- Use local Ollama instance for testing
- Configure agents to use `qwen2.5:14b` or `deepseek-r1:14b`
- Agents should make trading decisions during backtests

### 2. Model/Type Switching
- Switch between different LLM models (qwen, deepseek, etc.)
- Switch between agent types/configurations
- Update configuration without restarting

### 3. Agent Chat Interface
- View agent interactions in conversation format
- See decision-making process (bull vs bear debate, final decision)
- Timeline view of agent activities
- Filter by agent type, symbol, timeframe

### 4. Backtest Creation UI
- Select execution mode (full_pipeline with agents vs synthetic_fast)
- Pick instrument/symbol (CrudeOIL, Gold, etc.)
- Set date range, initial capital, parameters
- Start backtest and monitor progress
- View results with proper metrics display

---

## Implementation Plan

### Phase 1: Enable Agent System (Priority 1)

**Files to Modify:**
1. `/src/api/main.py` - Uncomment agent coordinator initialization
2. `/src/api/dependencies.py` - Check agent coordinator dependencies
3. `/config/agents.yaml` - Verify Ollama configuration

**Steps:**
1. Check if agent coordinator implementation is complete
2. Enable initialization in main.py
3. Test agent status endpoint: `GET /api/agents/status`
4. Verify agents can connect to Ollama

**Expected Result:**
- `GET /api/agents/status` returns list of active agents
- No "Agent coordinator not initialized" error

---

### Phase 2: Backtest Creation UI (Priority 1)

**New Components:**
1. `/dashboard/src/components/backtesting/CreateBacktestModal.tsx`
2. `/dashboard/src/components/backtesting/BacktestForm.tsx`

**Features:**
- Form fields:
  - Name (auto-generated or custom)
  - Symbol dropdown (CrudeOIL, Gold, EURUSD, etc.)
  - Date range picker
  - Initial capital input
  - Execution mode toggle (Agent Pipeline vs Synthetic)
  - Agent config selector (if Agent Pipeline mode)
  - Model selector (qwen2.5:14b, deepseek-r1:14b)
- Validation
- Submit to `POST /api/backtesting/configurations` then `POST /api/backtesting/runs`
- Auto-redirect to run status page

**API Integration:**
- Use existing `backtestApi.createConfiguration()`
- Use existing `backtestApi.runBacktest()`
- Poll `backtestApi.getRunStatus()` for progress

---

### Phase 3: Agent Chat Interface (Priority 2)

**New Components:**
1. `/dashboard/src/pages/AgentChat.tsx`
2. `/dashboard/src/components/agents/AgentConversation.tsx`
3. `/dashboard/src/components/agents/DecisionThread.tsx`
4. `/dashboard/src/components/agents/AgentMessage.tsx`

**Data Source:**
- `agent_decision_logs` table (already exists)
- Fields: `agent_name`, `decision_type`, `reasoning`, `market_context`, `timestamp`

**UI Layout:**
```
┌─────────────────────────────────────────────┐
│  Agent Interactions                          │
├─────────────────────────────────────────────┤
│ Filters:                                     │
│ [Symbol: CrudeOIL ▼] [Agent: All ▼] [...]  │
├─────────────────────────────────────────────┤
│                                              │
│ 🟢 Technical Analyst Agent                  │
│    "Bearish divergence on RSI..."           │
│    2025-01-15 14:23:15                       │
│                                              │
│ 🟡 Bull Researcher                           │
│    "Strong support at $72.50..."            │
│    2025-01-15 14:23:18                       │
│                                              │
│ 🔴 Bear Researcher                           │
│    "Resistance at $75.00 likely to hold..." │
│    2025-01-15 14:23:20                       │
│                                              │
│ ✅ Trade Decision Agent                      │
│    "Decision: SELL, Conviction: 0.75"       │
│    2025-01-15 14:23:25                       │
│                                              │
└─────────────────────────────────────────────┘
```

**API Endpoints:**
- `GET /api/backtesting/runs/{run_id}/decisions` (already exists)
- Need to add: `GET /api/agents/interactions?symbol=X&start=...&end=...`

---

### Phase 4: Model Switching (Priority 2)

**UI Components:**
1. Settings panel in AgentChat page
2. Model dropdown in CreateBacktestModal

**Backend Changes:**
- Support `config_params.agent_config.model` in backtest creation
- Agent coordinator should respect model config per run

**Example Request:**
```json
POST /api/backtesting/runs
{
  "config_id": "...",
  "timeframe": "M5",
  "synthetic_params": {
    "agent_config": {
      "model": "deepseek-r1:14b",
      "ollama_base_url": "http://192.168.0.123:11434/v1",
      "temperature": 0.7
    }
  }
}
```

---

### Phase 5: Results Display Improvements (Priority 3)

**Current Issues:**
- Backtesting page shows metrics but could be clearer
- No equity curve visualization
- No trade-by-trade breakdown

**Enhancements:**
1. Equity curve chart (already has placeholder code)
2. Trade list table with entry/exit details
3. Agent decision timeline
4. Performance metrics cards with charts

---

## Quick Wins (Can Do Now)

### 1. Enable Agent Coordinator (15 min)
```python
# /src/api/main.py
- # await init_agent_coordinator()
+ await init_agent_coordinator()
```

### 2. Add Create Backtest Button (30 min)
- Add button to Backtesting page
- Create modal with form
- Wire up to existing API

### 3. Show Agent Decisions (30 min)
- Use existing `/api/backtesting/runs/{run_id}/decisions` endpoint
- Add tab/section in backtest results
- Display in table or chat format

---

## Technical Challenges

### Challenge 1: Agent Coordinator Dependencies
**Issue:** May need to implement missing agent classes
**Solution:** Check which agents are actually implemented, stub out missing ones

### Challenge 2: Ollama Connection
**Issue:** Agent coordinator might not connect to Ollama correctly
**Solution:** Test connection separately, add error handling

### Challenge 3: Real-time Updates
**Issue:** Chat interface needs live updates during backtest
**Solution:** Poll API every 2-3 seconds, or use WebSockets (future)

---

## File Structure

```
src/
├── agents/
│   ├── agent_coordinator.py (exists - check implementation)
│   ├── decision/
│   │   ├── __init__.py
│   │   ├── fund_manager_agent.py (implemented)
│   │   └── position_sizing_agent.py (implemented)
│   └── schemas/
│       └── trade_decision.py
├── api/
│   └── routes/
│       ├── agents.py (exists - add interactions endpoint)
│       └── backtesting.py (exists - all endpoints ready)
└── database/
    └── models/
        ├── backtest.py
        └── simulated_trade.py (has AgentDecisionLog)

dashboard/src/
├── pages/
│   ├── Backtesting.tsx (exists - add create button)
│   └── AgentChat.tsx (NEW)
├── components/
│   ├── backtesting/
│   │   ├── CreateBacktestModal.tsx (NEW)
│   │   └── BacktestForm.tsx (NEW)
│   └── agents/
│       ├── AgentConversation.tsx (NEW)
│       └── AgentMessage.tsx (NEW)
└── api/
    └── endpoints.ts (add agent interaction endpoints)
```

---

## Next Steps

1. **Investigate agent coordinator** - Check if implementation is complete
2. **Enable agent system** - Uncomment initialization
3. **Test Ollama connection** - Verify agents can make API calls
4. **Build Create Backtest UI** - Modal with form
5. **Add Agent Chat View** - Display decision logs
6. **Test end-to-end** - Create backtest, run with agents, view decisions

---

## Estimated Timeline

- **Phase 1 (Enable Agents):** 1-2 hours
- **Phase 2 (Backtest UI):** 2-3 hours
- **Phase 3 (Agent Chat):** 3-4 hours
- **Phase 4 (Model Switching):** 1-2 hours
- **Phase 5 (Results Polish):** 2-3 hours

**Total:** 9-14 hours of development

---

## Risk Mitigation

### Risk: Agent Coordinator Not Fully Implemented
**Mitigation:** Check implementation status first, stub out missing parts

### Risk: Ollama Connection Issues
**Mitigation:** Test connection independently, add retry logic

### Risk: UI Complexity
**Mitigation:** Start with simple MVP, iterate

### Risk: Performance Issues
**Mitigation:** Add pagination, lazy loading for agent logs

---

## Success Criteria

✅ Agent status API returns active agents
✅ Can create new backtest from UI with agent mode
✅ Backtest runs successfully with agent decisions
✅ Can view agent decision logs in chat format
✅ Can switch between Ollama models
✅ Results display properly with metrics

---

## Open Questions

1. Are all agent classes implemented or just stubs?
2. Does agent coordinator actually work with Ollama?
3. What's the format of agent_decision_logs.reasoning field?
4. Should we add WebSocket support for real-time updates?
5. Do we need agent performance metrics (decision accuracy, P&L attribution)?
