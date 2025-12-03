# Quick Start Guide - Next Session

**Last Updated**: 2025-12-02
**Current Status**: 8 core agents implemented, service layer pending

---

## 🎯 What's Complete

### ✅ Core Agent Infrastructure (100%)
- BaseAgent with AutoGen 0.4
- LLM provider clients (Ollama, OpenAI, Anthropic, Google)
- LLMRouter with intelligent tier selection
- MCP tool wrappers (8 functions)
- Team orchestration (RoundRobin, Selector)
- AgentRegistry with health monitoring
- Prometheus metrics (27 metrics)
- Database migration 011 (TimescaleDB)

### ✅ Concrete Agents (100%)
- **Analysis Layer** (3): Technical, Fundamental, Sentiment
- **Decision Layer** (3): Position Sizing, Stop-Loss, Take-Profit
- **Execution Layer** (2): Trade Executor, Position Monitor

**Total**: 8 agents with comprehensive system prompts and structured outputs

---

## 🚧 What's Next (Priority Order)

### 1. Agent Service Layer (T044-T046) - ~1-2 hours
**Files to Create**:
- `src/services/agent_service.py` - High-level orchestration
- `src/services/__init__.py` - Service exports

**Requirements**:
- Agent lifecycle management (create, start, stop, health check)
- Pipeline orchestration (analysis → decision → execution)
- Error recovery and retry logic
- Integration with AgentRegistry

### 2. API Endpoints (T047-T050) - ~2 hours
**Files to Create**:
- `src/api/routes/agents.py` - Agent control endpoints
- Schemas in `src/api/schemas/agent_schemas.py`

**Endpoints Needed**:
```
POST /api/v1/agents/analysis/run
POST /api/v1/agents/decision/run
POST /api/v1/agents/execution/execute
GET  /api/v1/agents/health
GET  /api/v1/agents/registry/stats
GET  /api/v1/agents/positions/{position_id}
```

### 3. Integration Testing - ~2-3 hours
- Pull Ollama models (qwen3:14b, deepseek-r1:14b)
- Test full pipeline with real models
- Verify MCP tool integration
- Validate database persistence
- Check Prometheus metrics

---

## 🔧 Before Starting Next Session

### 1. Pull Ollama Models
```bash
ollama pull qwen3:14b        # Quick-think (1-2s)
ollama pull deepseek-r1:14b  # Deep-think (8-12s)
```

Verify:
```bash
curl http://192.168.0.123:11434/v1/models
```

### 2. Verify ML API is Running
```bash
docker-compose ps ml-forecasting-api
curl http://localhost:8004/health
```

If not running:
```bash
docker-compose up -d ml-forecasting-api
```

### 3. Check Database Migration
```bash
docker-compose exec api alembic current
# Should show: 011_convert_decision_log_to_timescaledb_hypertable
```

---

## 📁 Key Files Reference

### Agent Implementations
```
src/agents/
├── analysis/
│   ├── technical_analyst.py       [TechnicalAnalystAgent]
│   ├── fundamental_analyst.py     [FundamentalAnalystAgent]
│   └── sentiment_analyst.py       [SentimentAnalystAgent]
│
├── decision/
│   ├── position_sizing_agent.py   [PositionSizingAgent]
│   ├── stop_loss_agent.py         [StopLossAgent]
│   └── take_profit_agent.py       [TakeProfitAgent]
│
└── execution_layer/
    ├── trade_executor.py          [TradeExecutorAgent]
    └── position_monitor.py        [PositionMonitorAgent]
```

### Supporting Infrastructure
```
src/agents/
├── base/
│   ├── base_agent.py              [BaseAgent abstract class]
│   └── agent_config.py            [Config schemas]
│
├── providers/
│   └── model_router.py            [LLMRouter]
│
├── tools/
│   └── mcp_tools.py               [8 MCP tool functions]
│
├── teams/
│   ├── analysis_team.py           [RoundRobinGroupChat]
│   ├── debate_team.py             [SelectorGroupChat]
│   └── team_factory.py            [AgentTeamFactory]
│
└── coordination/
    └── agent_registry.py          [AgentRegistry]
```

### Documentation
```
.serena/
├── AGENT_IMPLEMENTATION_SESSION_SUMMARY.md  [Complete summary]
├── T036-T038_AGENT_IMPLEMENTATION_COMPLETE.md
└── QUICK_START_NEXT_SESSION.md (this file)

examples/
└── agent_usage_example.py         [Complete usage walkthrough]
```

---

## 🧪 Quick Test Commands

### Run Usage Example (No DB Required)
```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP
python examples/agent_usage_example.py
```

### Test Agent Import
```python
from src.agents.analysis import create_technical_analyst
from src.agents.decision import create_position_sizing_agent
from src.agents.execution_layer import create_trade_executor

print("✅ All agents imported successfully")
```

### Check Prometheus Metrics
```python
from src.monitoring.agent_metrics import record_agent_decision

record_agent_decision(
    agent_type="technical_analyst",
    symbol="Gold",
    decision_type="technical_report",
    duration_seconds=1.5,
    success=True
)
print("✅ Metrics recorded")
```

---

## 💡 Implementation Tips

### Agent Service Layer Design
```python
class AgentService:
    """High-level agent orchestration service."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.registry = AgentRegistry()
        self.llm_router = LLMRouter()

    async def run_analysis_pipeline(self, symbol: str) -> Dict[str, Any]:
        """Run all analysis agents for a symbol."""
        # Create agents
        technical = create_technical_analyst(...)
        fundamental = create_fundamental_analyst(...)
        sentiment = create_sentiment_analyst(...)

        # Run in parallel
        results = await asyncio.gather(
            technical.run(...),
            fundamental.run(...),
            sentiment.run(...),
        )

        return {"technical": results[0], ...}

    async def run_decision_pipeline(
        self,
        analysis: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run decision agents sequentially."""
        # Position sizing
        position = await position_sizer.run(...)

        # Stop-loss
        stop = await stop_agent.run(...)

        # Take-profit
        tp = await tp_agent.run(...)

        return {"position": position, "stop": stop, "target": tp}
```

### API Endpoint Pattern
```python
@router.post("/agents/analysis/run")
async def run_analysis(
    request: AnalysisRequest,
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    """Run analysis agents for a symbol."""

    service = AgentService(session)
    result = await service.run_analysis_pipeline(request.symbol)

    return AnalysisResponse(**result)
```

---

## 📊 Feature 005 Progress Tracker

### Phase 1: Setup (100% ✅)
- Directory structure
- Dependencies
- Config templates

### Phase 2: Foundational (100% ✅)
- Database models/repos
- Core agent infrastructure
- LLM providers
- MCP tools
- Team orchestration

### Phase 3: Implementation (50% 🚧)
- ✅ Concrete agents (8/8)
- ⏳ Service layer (0/1)
- ⏳ API endpoints (0/6)
- ⏳ Integration tests (0/1)

### Phase 4: Advanced (0% ⏳)
- RL training
- A/B testing
- Production deployment

**Overall Progress**: ~45% complete

---

## 🎯 Success Criteria for Next Session

### Must Complete
- [ ] AgentService class with lifecycle management
- [ ] All 6 API endpoints functional
- [ ] Basic integration test passing
- [ ] Ollama models pulled and tested

### Nice to Have
- [ ] Comprehensive test suite
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Grafana dashboard for metrics
- [ ] Error recovery examples

---

## 🚨 Known Issues / TODOs

### Configuration
- [ ] API keys not configured (optional, for <5% of decisions)
- [ ] Ollama models need to be pulled

### Dependencies
- [ ] Feature 003 ML API must be running for MCP tools
- [ ] TimescaleDB extension not installed (optional optimization)

### Testing
- [ ] Need real market data for integration testing
- [ ] Need MT4 connection for execution testing (can mock initially)

---

## 📞 Key Integration Points

### With Feature 003 (ML Forecasting)
- MCP tools call ML API at `http://localhost:8004`
- 8 tool endpoints expected:
  - `/forecast/tcn`
  - `/forecast/xgboost`
  - `/forecast/lstm`
  - `/regime/classify`
  - `/indicators`
  - `/market-data/{symbol}`
  - `/forecast/accuracy`
  - Kelly criterion (local calculation)

### With Feature 001 (MT4 Integration)
- TradeExecutorAgent calls MT4/ZMQ bridge
- Order placement, fill confirmation, slippage tracking
- Position updates flow back to PositionMonitorAgent

### With Feature 002 (Dashboard API)
- Agent metrics exposed via Prometheus
- Health endpoints for monitoring
- Decision logs queryable via API

---

## 🔗 Useful Commands

### Start All Services
```bash
docker-compose up -d postgres redis ml-forecasting-api
```

### Check Agent Registry Stats
```python
from src.agents.coordination import get_global_registry

registry = get_global_registry()
stats = registry.get_statistics()
print(stats)
```

### View Decision Logs
```sql
SELECT
    decided_at,
    agent_type,
    confidence,
    decision_latency_ms,
    was_executed
FROM decision_log
ORDER BY decided_at DESC
LIMIT 10;
```

---

**Ready for Next Session**: Create AgentService, API endpoints, and integration testing

**Estimated Time**: 6 hours to complete T044-T050 + testing

**Current Branch**: `005-intelligent-agent-trading`

---

*Last Updated: 2025-12-02 by Claude Code*
