# RiseTrader Project Structure

**Created:** November 16, 2025
**Status:** ✅ Complete and ready for development

## Directory Overview

```
RiseTrader/
├── .claude/                  # Claude Code configuration
│   ├── agents/              # 8 specialist subagents
│   └── hooks/               # Automation hooks
├── .serena/                  # Serena memory system
├── backups/                  # Database backups
├── config/                   # Configuration files
│   ├── agents.yaml          # Agent system config
│   └── environments/        # Environment-specific configs
├── dashboard/                # React TypeScript frontend
├── docker/                   # Docker configurations
│   ├── api/
│   ├── dashboard/
│   ├── ml-service/
│   └── postgres/
├── docs/                     # Documentation
├── mt4/                      # MetaTrader 4 Expert Advisors
│   ├── experts/
│   └── libraries/
├── research/                 # ML research & experiments
│   ├── notebooks/
│   ├── experiments/
│   └── data/
├── scripts/                  # Automation scripts
│   ├── setup/
│   ├── maintenance/
│   └── deployment/
├── src/                      # Python source code
│   ├── agents/              # 10 trading agents
│   │   ├── execution/       # Signal, Risk, Execution
│   │   ├── data_ml/         # MarketData, ML, Regime
│   │   └── supervisory/     # Performance, RiskOverseer, Optimizer
│   ├── api/                 # FastAPI application
│   │   ├── routes/
│   │   └── middleware/
│   ├── database/            # Database layer
│   │   ├── models/
│   │   ├── repositories/
│   │   └── migrations/
│   ├── trading/             # Trading engine
│   │   ├── engine/
│   │   ├── strategies/
│   │   ├── risk/
│   │   └── execution/
│   ├── ml/                  # Machine learning
│   │   ├── data/
│   │   ├── models/
│   │   ├── training/
│   │   ├── inference/
│   │   └── evaluation/
│   ├── services/            # Business logic
│   ├── monitoring/          # Metrics & tracing
│   └── utils/               # Utilities
├── tests/                    # Test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .env                      # Environment variables
├── .gitignore                # Git ignore rules
├── docker-compose.yml        # Docker Compose config
├── pyproject.toml            # Python project config
├── requirements.txt          # Python dependencies
├── README.md                 # Project overview
└── CLAUDE.md                 # Claude Code guide

Total Python Packages: 26
Total Test Packages: 16
```

## Key Files Created

### Configuration
- `pyproject.toml` - Python project metadata
- `requirements.txt` - Dependency list
- `config/agents.yaml` - Agent system configuration
- `.env` - Environment variables
- `.gitignore` - Git ignore patterns

### Documentation  
- `README.md` - Project overview
- `CLAUDE.md` - Claude Code guide (updated)
- `docs/` - All planning documents

### Infrastructure
- `docker-compose.yml` - Container orchestration
- 26 `__init__.py` files for Python packages
- 16 test package files

## Next Steps

1. **Start Building Agents**
   - Use backend-architect to design MCP server
   - Use agent-developer to implement base agent class
   - Implement 10 trading agents

2. **Development Workflow**
   ```bash
   # Start services
   docker-compose up -d
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Run tests
   pytest
   ```

3. **Agent Build Order**
   - Week 1: MCP Server + Base Agent
   - Week 2: Execution Layer (3 agents)
   - Week 3: Data/ML Layer (3 agents)
   - Week 4: Supervisory Layer (3 agents)

## Infrastructure Status

✅ PostgreSQL 17 running (port 5433)
✅ Redis 7 configured
✅ 13.5M market data records
✅ Project structure complete
✅ Configuration files ready

## Ready to Code!

Everything is organized and ready for agent development.
See `.serena/QUICK_START.md` for detailed next steps.
