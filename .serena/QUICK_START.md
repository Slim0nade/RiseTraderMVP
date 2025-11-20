# RiseTraderMVP - Quick Start Guide

## For Next Claude Code Session

### 1. Check Infrastructure Status

```bash
# Verify Docker containers are running
docker ps

# If not running, start them:
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP
docker-compose up -d

# Verify database connection
docker exec -it risetrader-postgres psql -U postgres -d risetrader -c "SELECT COUNT(*) FROM market_data;"
# Should return: 13558303
```

### 2. Available Subagents

Located in: `/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/.claude/agents/`

- **backend-architect** - System architecture and API design
- **agent-developer** - Agent implementation (use this first!)
- **ml-engineer** - PPO-LSTM model development
- **database-specialist** - Database optimization
- **frontend-developer** - React/WebSocket UI
- **devops-engineer** - Docker/deployment
- **code-reviewer** - Code quality checks
- **memory-manager** - Session tracking

**To use a subagent:** Reference the .md file in your prompt to Claude Code

### 3. Database Connection

```python
# Connection string
DATABASE_URL = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"

# Ports
PostgreSQL: 5433
Redis: 6379 (not started yet)
```

### 4. First Development Task

**Start with:** Building the MCP server and agent system

```bash
# Recommended workflow:
1. Review backend-architect.md for MCP server design
2. Use agent-developer.md to implement BaseAgent class
3. Build SignalGeneratorAgent as first working agent
4. Implement ZMQ bridge to MT4 (IP: 75.154.254.186)
```

### 5. Key Files to Reference

- `CLAUDE.md` - Complete project overview
- `.claude/SETUP_COMPLETE.md` - Subagent usage guide
- `.serena/SESSION_PROGRESS_2025-11-16.md` - Detailed session notes
- `docker-compose.yml` - Infrastructure config
- `.env` - Environment variables

### 6. Data Available

**Ready for ML Training:**
- 5.5M CrudeOIL M1 records (2009-2025, 16 years!)
- 441K CrudeOIL M5 records
- 5.7M DXY M1 records
- 1.9M VIX M1 records
- 70K pre-calculated technical indicators
- 8K optimal trade examples

### 7. Critical Security Reminders

**BEFORE connecting to MT4 in production:**
- [ ] Implement ZMQ CurveZMQ encryption
- [ ] Add JWT authentication
- [ ] Configure rate limiting
- [ ] Implement circuit breakers
- [ ] Test with demo account first

### 8. Project Structure (To Be Created)

```
RiseTraderMVP/
├── agents/               # Agent implementations (TO CREATE)
│   ├── base/            # BaseAgent class
│   ├── execution/       # SignalGenerator, RiskManager, Execution
│   ├── data_ml/         # DataCollector, FeatureEngineer, ModelTrainer
│   └── supervisory/     # StrategyCoordinator, PerformanceMonitor, Compliance
├── mcp_server/          # MCP server implementation (TO CREATE)
├── models/              # Database models
├── bridges/             # ZMQ MT4 bridge (TO CREATE)
├── tests/               # Test suite
└── docker-compose.yml   # ✅ EXISTS
```

### 9. Environment Setup Check

```bash
# Python version (should be 3.11+)
python --version

# Install dependencies (when requirements.txt is created)
pip install -r requirements.txt

# Verify Serena is registered
cat ~/.serena/serena_config.yml | grep RiseTraderMVP
# Should show: - /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP
```

### 10. Immediate Next Steps

**Week 1 Tasks:**
1. Design MCP server architecture (use backend-architect)
2. Implement BaseAgent class (use agent-developer)
3. Build SignalGeneratorAgent
4. Create ZMQ bridge for MT4 connection
5. Write unit tests

**Ready to start coding!**

---

**Last Updated:** November 16, 2025
**Status:** Infrastructure complete, ready for development
**Phase:** 2.5 - Multi-Agent Trading System
