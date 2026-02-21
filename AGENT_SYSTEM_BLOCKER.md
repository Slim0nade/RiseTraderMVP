# Agent System Implementation Blocker

**Date:** 2025-12-19
**Status:** ❌ Blocked - Configuration Mismatch
**Severity:** High

---

## Critical Issue Discovered

While attempting to enable the agent coordinator, I discovered a **fundamental mismatch** between the agent configuration file and the agent coordinator code. This prevents the agent system from starting.

### The Problem

**Agent Coordinator Code** expects:
```yaml
# What agent_coordinator.py looks for
agents:
  signal_generator:
    enabled: true
    config:
      # agent-specific settings
  risk_manager:
    enabled: true
    config:
      # agent-specific settings
```

**Current Config File** (`config/agents.yaml`) has:
```yaml
# What actually exists
strategy_teams:
  - team_id: "team-gold-001"
    symbol: "Gold"
    enabled_layers: [...]

agent_templates:
  analysis:
    technical_analyst:
      llm_tier: "quick_think"
```

### Error When Starting
```
KeyError: 'signal_generator'
File "/app/src/agents/agent_coordinator.py", line 239
config = {**agent_configs["signal_generator"]["config"], **shared_config}
```

---

## Root Cause Analysis

The agent system appears to have been refactored from:
1. **Old Design:** 10 individual agents (signal_generator, risk_manager, etc.)
2. **New Design:** Team-based system with agent templates per instrument

The `agent_coordinator.py` still expects the old design, but `agents.yaml` uses the new design.

---

## Impact

❌ **Cannot enable agent coordinator** - Crashes on startup
❌ **Cannot use agents in backtests** - Coordinator not running
❌ **Cannot view agent decisions** - No agents making decisions
✅ **Synthetic backtests still work** - Don't require agents
✅ **All other functionality works** - Trading, MT4 sync, etc.

---

## Solutions

### Option 1: Quick Fix - Stub Agent Coordinator (1-2 hours)

Create a simplified agent coordinator that:
- Returns stub agent status (fake data)
- Doesn't actually initialize agents
- Allows UI development to proceed
- Agent decisions come from database (from previous runs)

**Pros:**
- Unblocks UI development immediately
- Can build and test all UI components
- Backtest creation UI works (synthetic mode)

**Cons:**
- Agents don't actually run
- Can't test real agent decision-making
- Temporary workaround only

### Option 2: Fix Config Mismatch (4-6 hours)

Refactor agent coordinator to match new config structure:
- Rewrite `_create_agents()` to read `strategy_teams`
- Create agents per team/symbol
- Update initialization logic
- Test with Ollama

**Pros:**
- Agents actually work
- Can test real LLM decision-making
- Production-ready solution

**Cons:**
- Significant refactoring required
- May break other dependencies
- Need to understand full team architecture

### Option 3: Revert to Old Config (2-3 hours)

Create new config file matching old structure:
```yaml
agents:
  signal_generator:
    enabled: true
    config:
      llm_provider: "ollama"
      llm_model: "qwen2.5:14b"
      ollama_base_url: "http://75.154.254.174:11434/v1"
```

**Pros:**
- Works with existing coordinator code
- Agents run immediately
- Simpler than refactoring coordinator

**Cons:**
- Loses new team-based architecture
- May break other code expecting new structure
- Unclear if all agents are implemented

---

## Recommended Approach

Given the time constraints and goal to see UI working, I recommend:

### Phase 1: Proceed Without Live Agents (Today)
1. ✅ Keep agent coordinator disabled
2. ✅ Build all UI components:
   - Create Backtest Modal (works for synthetic mode)
   - Agent Chat Interface (shows decisions from DB)
   - Model switching (config only, not live)
3. ✅ Test with synthetic backtests
4. ✅ View agent decisions from previous runs in database

**Result:** Full UI working, can create backtests, view past decisions

### Phase 2: Fix Agent System (Next Session)
1. Investigate which config structure is correct
2. Choose Option 2 or 3 above
3. Test with live Ollama
4. Verify agents make decisions

**Result:** Agents actually running and making live decisions

---

## What We Can Build Today

Even without live agents, we can build **complete UI** that will work when agents are fixed:

### 1. ✅ Create Backtest Modal
- Form with all fields
- Symbol selection
- Date range picker
- Mode selection (synthetic for now)
- Model dropdown (config only)
- **Works:** Creates synthetic backtests successfully

### 2. ✅ Agent Chat Interface
- Displays agent_decision_logs from database
- Shows decisions from previous backtest runs
- Conversation-style layout
- Filtering by agent, symbol, time
- **Works:** Database has existing decisions to display

### 3. ✅ Results Display Improvements
- Equity curve chart
- Trade list table
- Metrics cards
- **Works:** Uses backtest_runs data

### 4. ✅ Model Switching UI
- Dropdown to select model
- Saves to config_params
- **Works:** Stores preference, will work when agents enabled

---

## Database Verification

Let me check if there are existing agent decisions to display:

```sql
SELECT COUNT(*) FROM agent_decision_logs;
-- If > 0, we have data to show in UI
```

```bash
docker exec risetrader-postgres psql -U postgres -d risetrader \
  -c "SELECT COUNT(*) as decision_count FROM agent_decision_logs;"
```

If we have existing decisions, the Agent Chat UI will be immediately useful!

---

## Next Steps

### Immediate (This Session):
1. ✅ Document the blocker (this file)
2. ⏭️ Build Create Backtest Modal (synthetic mode)
3. ⏭️ Build Agent Chat Interface (shows DB data)
4. ⏭️ Add Results Display improvements
5. ⏭️ Test complete flow

### Future (Next Session):
1. Analyze agent coordinator vs config mismatch
2. Choose fix strategy (Option 2 or 3)
3. Implement fix
4. Test with live Ollama
5. Verify end-to-end with real agent decisions

---

## Technical Details

### Files Involved

**Agent Coordinator:**
- `/src/agents/agent_coordinator.py` (expects old config structure)
- `/src/api/dependencies.py` (initialization logic)

**Configuration:**
- `/config/agents.yaml` (new team-based structure)
- Need to create `/config/agents_simple.yaml` (old structure)

**Agent Implementations:**
- `/src/agents/execution/` (SignalGeneratorAgent, etc.)
- `/src/agents/decision/` (Fund Manager, Position Sizing)
- `/src/agents/teams/` (Team-based architecture)

### Config Structure Needed

```yaml
agents:
  signal_generator:
    enabled: true
    config:
      llm_provider: "ollama"
      llm_model: "qwen2.5:14b"
      llm_base_url: "http://75.154.254.174:11434/v1"
      temperature: 0.7
      max_tokens: 500

  risk_manager:
    enabled: true
    config:
      max_position_size: 0.03
      max_daily_loss: 1000.0

  execution:
    enabled: true
    config:
      mt4_host: "75.154.254.174"
      mt4_port: 5555

  market_data:
    enabled: true
    config: {}

  ml_prediction:
    enabled: true
    config:
      llm_provider: "ollama"
      llm_model: "deepseek-r1:14b"
      llm_base_url: "http://75.154.254.174:11434/v1"

  regime_detection:
    enabled: true
    config: {}

  performance_monitor:
    enabled: true
    config: {}

  data_quality:
    enabled: true
    config: {}

  risk_overseer:
    enabled: true
    config:
      circuit_breaker_threshold: 5000.0

  strategy_optimizer:
    enabled: true
    config: {}
```

---

## Decision Point

**Do you want me to:**

**A)** Build all the UI components now (create backtest modal, agent chat, etc.) knowing agents won't run live but UI will be ready when fixed?

**B)** Stop and fix the agent system first (config refactor), then build UI?

**C)** Create a stub agent coordinator that returns fake data, allowing both UI and fake agent testing?

**My Recommendation:** **Option A** - Build UI now, fix agents next session. This gives you visible progress today and a complete interface, even if backend needs work.

Would you like me to proceed with building the UI components?
