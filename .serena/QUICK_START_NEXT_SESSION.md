# Quick Start Guide - Next Session

## Session Status: Feature 005 Foundation + Database COMPLETE ✅

**Last Session**: 2025-12-02 (Continued)
**Tasks Completed**: T001-T028 (foundation) + T015-T016 (database migration)
**Status**: Database ready, API running. Ready for AutoGen 0.4 research → agent implementation

---

## What's Been Completed

### ✅ Phase 1: Infrastructure (T001-T006)
- Agent directory structure created
- AutoGen 0.4 + RL dependencies installed in Docker
- Pre-commit hooks configured
- YAML configuration templates created
- MLflow + Ollama services added to docker-compose.yml

### ✅ Phase 2: Database & Schemas (T007-T021)
- **Migration 010**: 7 agent system tables
- **7 SQLAlchemy Models**: Agent, DecisionLog, RLTrainingRun, ModelConfiguration, PortfolioAllocation, StrategyTeam, MCPTool
- **20+ Pydantic Schemas**: Events, Decisions, Reports, AgentConfig

### ✅ Phase 2: Repository Layer (T022-T028)
- **7 Repositories**: Full async CRUD with specialized queries
- All repositories exported in `src/database/repositories/__init__.py`

### ✅ Docker Build Status
- API container built successfully
- All 100+ packages installed including:
  - autogen-agentchat-0.4.4
  - autogen-core-0.4.4
  - autogen-ext-0.4.4
  - stable-baselines3-2.4.1
  - gymnasium-1.0.0
  - mlflow-2.9.2

### ✅ API Fixes & Database Migration (This Session - 2025-12-02 Continued)

**Code Fixes Applied:**
1. Fixed CORS parsing in `src/api/config.py` - added `field_validator` for comma-separated env var
2. Added missing `load_config()` function to `src/ml/training/config.py`
3. Fixed missing imports in `src/api/routes/ml_forecasting.py` (List, Optional)
4. Fixed `agent_config_path` to use Docker container path `/app/config/agents.yaml`
5. Temporarily disabled agent coordinator initialization (pending BaseAgent implementation)

**Database Migration:**
- ✅ Applied migration 009 (exogenous_variables table)
- ✅ Applied migration 010 (7 agent system tables created)
- ✅ Verified all tables and 40+ composite indexes created successfully

**API Status:**
- Container running healthy on port 8003
- All routes accessible
- Ready for Alembic migrations and testing

---

## Immediate Next Steps

### ✅ COMPLETED: Database Migration (T015-T016)

**T015**: ✅ Applied Alembic migration
- Successfully created 7 agent system tables
- All composite indexes created for time-series queries
- Migration 009 (exogenous_variables) and 010 (agent_system) applied

**Verification**:
```bash
# All 7 tables created
docker-compose exec postgres psql -U postgres -d risetrader -c "\dt" | grep -E "(strategy_teams|agents|decision_log|rl_training_runs|model_configurations|portfolio_allocations|mcp_tools)"
```

**T016**: ⚠️ TimescaleDB Not Available
- Current PostgreSQL image (postgres:17-alpine) doesn't include TimescaleDB
- Decision_log table created with standard indexes (composite time-series indexes work well)
- **Future Enhancement**: Switch to `timescale/timescaledb:latest-pg17` image for hypertable + retention policy

**Note**: Standard PostgreSQL with composite indexes is sufficient for MVP. TimescaleDB can be added later for production scale.

### ✅ COMPLETED: Research AutoGen 0.4 + Ollama Network Configuration

**AutoGen 0.4 Research**: ✅ Complete
- Comprehensive research document created: `.serena/AUTOGEN_0.4_RESEARCH_SUMMARY.md`
- AssistantAgent API patterns documented
- OllamaChatCompletionClient integration understood
- Tool registration and message patterns learned

**Ollama Network Configuration**: ✅ Complete
- Connected to external Ollama at `192.168.0.123:11434`
- Models available: `qwen3:14b`, `deepseek-r1:14b`, `qwen3:30b-a3b`
- API container using `network_mode: host` for LAN access
- Connectivity verified from container

### ✅ COMPLETED: Implement BaseAgent (T029)

**Implementation Complete**: ✅
- Created `src/agents/base/base_agent.py` - Abstract base class wrapping AutoGen 0.4
- Created `src/agents/examples/simple_test_agent.py` - Test implementation
- Features implemented:
  - Dual-LLM client creation (quick-think vs deep-think)
  - Decision logging to decision_log table
  - Error handling with retry logic and exponential backoff
  - Health monitoring and state management
  - Performance metrics tracking
  - Pause/resume/shutdown lifecycle management

**BaseAgent Architecture**:
```python
BaseAgent (Abstract)
├── _autogen_agent: AssistantAgent (AutoGen 0.4)
├── _model_client: OllamaChatCompletionClient
├── _session: AsyncSession (database)
├── _agent_repo: AgentRepository
├── _decision_log_repo: DecisionLogRepository
└── _state: AgentStateModel (runtime tracking)

Methods:
├── run(task, context, correlation_id) -> decision_data
├── health_check() -> health_status
├── get_state() -> AgentStateModel
├── pause() / resume() / shutdown()
└── Abstract: _get_system_message(), _extract_decision()
```

**Test Agent**: SimpleTestAgent created for testing infrastructure

### 🚀 CURRENT: Test BaseAgent with Ollama (T029 Verification)

**Status**: Rebuilding API container with new BaseAgent code

**Next Steps**:
1. Complete container rebuild
2. Run BaseAgent import test
3. Execute SimpleTestAgent with live Ollama connection
4. Verify decision logging to database
5. Document results

### Priority 2: First Production Agent - Technical Analyst (T030)

---

## File Locations Reference

### Configuration Files
```
config/agents/agents.yaml.template              # Main agent config
config/agents/rl_training_config.yaml.template  # RL hyperparameters
config/agents/portfolio_allocation.yaml.template # Portfolio allocation
.pre-commit-config.yaml                          # Code quality hooks
```

### Database Models
```
src/database/models/agent.py                     # Agent model
src/database/models/decision_log.py              # DecisionLog (TimescaleDB)
src/database/models/rl_training_run.py           # RL training tracking
src/database/models/model_configuration.py       # Config versioning
src/database/models/portfolio_allocation.py      # Capital allocation
src/database/models/strategy_team.py             # Team management
src/database/models/mcp_tool.py                  # Tool registry
```

### Pydantic Schemas
```
src/agents/schemas/events.py                     # BaseEvent, EventType
src/agents/schemas/decisions.py                  # 5 decision schemas
src/agents/schemas/reports.py                    # 4 report schemas
src/agents/base/agent_config.py                  # AgentConfig, AgentState
```

### Repositories
```
src/database/repositories/agent_repository.py
src/database/repositories/decision_log_repository.py
src/database/repositories/rl_training_run_repository.py
src/database/repositories/model_configuration_repository.py
src/database/repositories/portfolio_allocation_repository.py
src/database/repositories/strategy_team_repository.py
src/database/repositories/mcp_tool_repository.py
```

### Migration
```
src/database/migrations/versions/010_create_agent_system_tables.py
```

---

## Key Architecture Decisions Made

1. **Dual-LLM Strategy**
   - Quick-think: Qwen2.5:14b (temperature 0.1, 500 tokens)
   - Deep-think: DeepSeek-R1:14b (temperature 0.7, 2000 tokens)

2. **RL Validation Requirements**
   - Walk-forward: 252 train / 63 test / 21 step days
   - OOS Sharpe > 1.2 required for production promotion
   - Algorithms: PPO (discrete), SAC (continuous)

3. **TimescaleDB for Decision Log**
   - Partitioned by `decided_at` timestamp
   - 90-day retention policy
   - Composite indexes for time-series queries

4. **Event-Driven Architecture**
   - BaseEvent with correlation_id for multi-agent coordination
   - EventPriority: critical, high, normal, low
   - 20+ event types across 5 layers

5. **Portfolio Allocation**
   - Static mode: Config-based (e.g., 40% Gold, 40% Crude, 20% Reserve)
   - Dynamic mode: Portfolio Allocator Agent (future)
   - Rebalancing triggers: Sharpe, Drawdown, Correlation thresholds

---

## Docker Services Available

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# Services:
# - postgres:5432    (PostgreSQL 17)
# - redis:6379       (Redis 7)
# - mlflow:5000      (MLflow tracking)
# - ollama:11434     (Local LLM inference)
# - api:8003         (FastAPI)
```

### Pull Ollama Models
```bash
# After starting ollama service
docker exec -it risetrader-ollama ollama pull qwen2.5:14b
docker exec -it risetrader-ollama ollama pull deepseek-r1:14b
```

---

## Testing the Foundation

### Verify Database Models
```python
# Test imports
from src.database.models import (
    Agent, DecisionLog, RLTrainingRun,
    ModelConfiguration, PortfolioAllocation,
    StrategyTeam, MCPTool
)

# Test repositories
from src.database.repositories import (
    AgentRepository, DecisionLogRepository,
    RLTrainingRunRepository, ModelConfigurationRepository,
    PortfolioAllocationRepository, StrategyTeamRepository,
    MCPToolRepository
)
```

### Verify Pydantic Schemas
```python
# Test imports
from src.agents.schemas import (
    BaseEvent, EventType, MarketTickEvent,
    TradeIntent, PositionSize, StopLoss, TakeProfit,
    TechnicalReport, FundamentalReport, DebateOutcome
)

from src.agents.base import (
    AgentConfig, AgentStateModel, AgentType, AgentLayer
)
```

### Run Pre-Commit Hooks
```bash
# Install hooks
pre-commit install

# Run on all files
pre-commit run --all-files

# Should pass:
# - trailing-whitespace
# - end-of-file-fixer
# - check-yaml
# - black, isort, flake8, mypy
# - validate-pydantic-schemas
```

---

## Common Commands

### Database
```bash
# Apply migrations
docker-compose exec api alembic upgrade head

# Rollback
docker-compose exec api alembic downgrade -1

# Create new migration
docker-compose exec api alembic revision --autogenerate -m "description"

# Access PostgreSQL
docker-compose exec postgres psql -U postgres -d risetrader
```

### MLflow
```bash
# Access MLflow UI
open http://localhost:5000

# List experiments
docker-compose exec api python -c "
import mlflow
mlflow.set_tracking_uri('http://mlflow:5000')
print(mlflow.list_experiments())
"
```

### Ollama
```bash
# Test LLM
docker exec -it risetrader-ollama ollama run qwen2.5:14b "Hello, I'm a trading agent"

# List models
docker exec -it risetrader-ollama ollama list
```

---

## Known Issues / TODOs

### Must Complete Before Agent Implementation
- [ ] T015: Apply Alembic migration
- [ ] T016: Setup TimescaleDB hypertable
- [ ] Research AutoGen 0.4 API

### Nice to Have
- [ ] Create example agent config YAML (copy from templates)
- [ ] Test database connection in Docker
- [ ] Verify MLflow tracking works
- [ ] Test Ollama LLM inference

---

## Session Progress Tracking

**Completed**: 26/174 tasks (15%)
**Phase 1**: 6/6 tasks ✅
**Phase 2 Foundation**: 20/47 tasks (43%)
**Phase 2 Remaining**: Skipped T015-T016 (migration), T029+ (agents)

**Next Milestone**: Complete T029-T038 (Core Agent Infrastructure with AutoGen 0.4)

---

## Resources

**Documentation**:
- AutoGen 0.4: https://microsoft.github.io/autogen/
- Stable-Baselines3: https://stable-baselines3.readthedocs.io/
- MLflow: https://mlflow.org/docs/latest/
- TimescaleDB: https://docs.timescale.com/

**Project Docs**:
- Feature Spec: `specs/005-intelligent-agent-trading/spec.md`
- Tasks: `specs/005-intelligent-agent-trading/tasks.md`
- Session Progress: `.serena/SESSION_PROGRESS_2025-12-02.md`

**Key Files to Review**:
- `CLAUDE.md` - Project overview
- `docker-compose.yml` - Service configuration
- `requirements.txt` - Dependencies

---

## Quick Wins for Next Session

1. **Apply migration** (5 min)
2. **Research AutoGen 0.4** (30-60 min)
3. **Create first agent** (Technical Analyst - simplest)
4. **Test end-to-end flow** (Event → Decision → Log)

---

**Status**: Ready for AutoGen 0.4 implementation! 🚀
**Last Updated**: 2025-12-02
