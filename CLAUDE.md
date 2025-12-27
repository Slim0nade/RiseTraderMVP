# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference for New Sessions

**IMPORTANT:** Before starting any work, check these files:
- `.serena/QUICK_START.md` - Infrastructure status & immediate next steps
- `.serena/SESSION_PROGRESS_2025-11-16.md` - Latest session progress & detailed notes
- `.claude/SETUP_COMPLETE.md` - Subagent system usage guide

 Key Learnings:

  1. ⚠️ Always search entire codebase before changing class names
  2. ⚠️ Always verify fixes work by checking logs and data
  3. ⚠️ Always provide context for anything
  4. ⚠️ Never assume a fix is complete without verification


## Project Overview

**RiseTrader** is an autonomous algorithmic trading platform that combines a FastAPI backend, React TypeScript dashboard, ML-powered forecasting, and a multi-agent coordination system for 24/7 automated trading on MetaTrader 4 (MT4).

**Current Status:** Infrastructure complete (PostgreSQL + Redis ready). Database restored with 13.5M market data records. Ready to begin agent system development - Phase 2.5.

## 🔴 CRITICAL: Service Network Configuration (READ THIS FIRST!)

**Current Mode: REMOTE** (connecting to external VPS server)

### Remote Mode (Current - VPS at 75.154.254.186)
- **Ollama Server**: `http://75.154.254.186:11434`
  - Available models: qwen3:14b, deepseek-r1:14b, mistral:7b-instruct, llama3.1:8b
  - ⚠️ **DO NOT** append `/v1` in configs - code automatically adds it for OpenAI-compatible endpoint
  - Test: `curl http://75.154.254.186:11434/api/tags`

- **MT4 Server**: `75.154.254.186`
  - REP Port: 5555 (commands)
  - PUB Port: 5556 (streaming data)
  - Test: `telnet 75.154.254.186 5555`

### Local Mode (192.168.0.123 - when on same network)
- **Ollama Server**: `http://192.168.0.123:11434`
- **MT4 Server**: `192.168.0.123:5555/5556`

**⚠️ IMPORTANT**: When switching between remote/local, update BOTH service IPs in:
- `.env` file: `OLLAMA_BASE_URL`, `MT4_HOST`
- Backtest configs: `ollama_base_url` in `config_params`

## Key Architecture Components

### 1. Multi-Agent System (Core Innovation)

The system uses **10 specialized autonomous agents** coordinated by an MCP (Model Context Protocol) server:

**Execution Layer:**
- `SignalGeneratorAgent` - Multi-strategy signal generation from multiple sources
- `RiskManagerAgent` - Pre-trade validation, position sizing, risk checks
- `ExecutionAgent` - Order execution on MT4 via encrypted ZMQ

**Data/ML Layer:**
- `MarketDataAgent` - Real-time market data streaming and validation
- `MLPredictionAgent` - ML-powered price forecasts (XGBoost, TFT, LSTM)
- `RegimeDetectionAgent` - Market regime classification for adaptive strategies

**Supervisory Layer:**
- `PerformanceMonitorAgent` - Real-time P&L tracking and reporting
- `RiskOverseerAgent` - System-wide risk monitoring and emergency stops
- `StrategyOptimizerAgent` - Continuous parameter tuning and A/B testing

**Coordination:**
- `MCP Server` - Event-driven agent communication hub with shared context

### 2. Technology Stack

**Backend:**
- Python 3.11+ with FastAPI for REST API
- PostgreSQL 15+ with time-series optimizations
- Redis 7+ for caching and pub/sub
- SQLAlchemy 2.0+ (async) with Alembic migrations
- ZMQ (PyZMQ) for MT4 communication with CurveZMQ encryption

**ML Stack:**
- PyTorch 2.0+, XGBoost, scikit-learn for models
- MLflow for experiment tracking and model registry
- Optuna for hyperparameter optimization
- pandas/numpy for data processing

**Frontend:**
- React 18+ with TypeScript
- TradingView Lightweight Charts for financial visualization
- TanStack Query for data fetching
- Zustand for state management
- TailwindCSS for styling

**DevOps:**
- Docker and Docker Compose for containerization
- Prometheus + Grafana for metrics and visualization
- ELK Stack (Elasticsearch, Logstash, Kibana) for centralized logging
- Jaeger for distributed tracing
- GitHub Actions for CI/CD

### 3. Planned Directory Structure

```
RiseTrader/
├── src/                          # Python source code
│   ├── api/                      # FastAPI REST API endpoints
│   ├── database/                 # Models, repositories, migrations
│   ├── trading/                  # Trading engine core
│   │   ├── engine/              # Strategy execution orchestration
│   │   ├── strategies/          # Trading strategy implementations
│   │   ├── risk/                # Risk management logic
│   │   └── execution/           # MT4 order execution
│   ├── ml/                       # Machine learning pipeline
│   │   ├── data/                # Data loaders and preprocessors
│   │   ├── models/              # Model implementations
│   │   ├── training/            # Training infrastructure
│   │   ├── inference/           # Real-time prediction service
│   │   └── evaluation/          # Model evaluation metrics
│   ├── agents/                   # Intelligent agent system
│   │   ├── base_agent.py        # Base agent class
│   │   ├── mcp_server.py        # Agent coordination server
│   │   ├── execution/           # Signal, risk, execution agents
│   │   ├── data_ml/             # Data and ML agents
│   │   └── supervisory/         # Monitoring and optimization agents
│   ├── services/                 # Business logic services
│   ├── monitoring/               # Metrics and tracing
│   └── utils/                    # Shared utilities
├── dashboard/                    # React TypeScript frontend
├── research/                     # Jupyter notebooks & experiments
│   ├── notebooks/               # Organized by research phase
│   ├── experiments/             # MLflow tracked experiments
│   └── data/                    # Training datasets
├── mt4/                          # MetaTrader 4 Expert Advisors
│   ├── experts/                 # Trading EAs (MQL4)
│   └── libraries/               # ZMQ integration libraries
├── tests/                        # Comprehensive test suite
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── e2e/                     # End-to-end tests
├── docker/                       # Docker configurations
├── config/                       # Configuration files
│   ├── agents.yaml              # Agent system configuration
│   └── environments/            # Environment-specific configs
├── scripts/                      # Deployment and maintenance scripts
└── docs/                         # Documentation
```

## Development Commands (Planned)

Once implementation begins, these will be the standard commands:

### Docker Operations
```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f api
docker-compose logs -f agent-coordinator

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d --force-recreate

# Check service health
docker-compose ps
./scripts/monitoring/check_service_health.sh
```

### Database Operations
```bash
# Run migrations
docker-compose exec api alembic upgrade head

# Rollback migration
docker-compose exec api alembic downgrade -1

# Create new migration
docker-compose exec api alembic revision --autogenerate -m "description"

# Backup database
./scripts/maintenance/backup_database.sh

# Restore database
./scripts/setup/restore_database.sh backup.dump
```

### Testing
```bash
# Run all tests
docker-compose exec api pytest

# Run with coverage
docker-compose exec api pytest --cov=src --cov-report=html

# Run specific test file
docker-compose exec api pytest tests/unit/test_trading_engine.py

# Run integration tests only
docker-compose exec api pytest tests/integration/

# Load testing
docker-compose exec api locust -f tests/load/locustfile.py
```

### Agent System
```bash
# Check agent status
curl http://localhost:8003/agents/status

# Trigger signal generation
curl -X POST http://localhost:8003/agents/signal_generator/command \
  -H "Content-Type: application/json" \
  -d '{"action": "generate_signal", "symbol": "CrudeOIL"}'

# View MCP server logs
docker-compose logs -f agent-coordinator
```

### ML Operations
```bash
# Start MLflow UI
docker-compose up mlflow

# Train model
docker-compose exec ml-service python -m src.ml.training.train_model

# Run inference
docker-compose exec ml-service python -m src.ml.inference.predict

# Start Jupyter for research
docker-compose up jupyter
```

## Critical Security Requirements

**MUST be implemented before production:**

1. **MT4 Connection Security (Week 3-4)**
   - Current: Exposed at IP 75.154.254.186 with no encryption
   - Required: Implement ZMQ CurveZMQ encryption OR VPN tunnel
   - Configuration: `ZMQ_CLIENT_SECRET_KEY`, `ZMQ_CLIENT_PUBLIC_KEY`, `ZMQ_SERVER_PUBLIC_KEY`

2. **API Authentication (Week 3-4)**
   - Required: JWT + API key authentication on all endpoints
   - Configuration: `JWT_SECRET_KEY`, `API_KEY`, `VALID_API_KEYS`

3. **Rate Limiting (Week 8-9)**
   - Implement slowapi middleware for API protection

4. **Circuit Breakers (Week 4-5)**
   - Protect against cascading failures from MT4 disconnection

## Key Architectural Patterns

### Repository Pattern
- Database operations abstracted through repository classes at `src/database/repositories/`
- Base repository with common CRUD operations
- Specialized repositories for domain entities

### Service Layer Pattern
- Business logic in `src/services/` separate from API routes
- Services orchestrate between repositories, agents, and external systems
- Clear separation of concerns

### Event-Driven Architecture
- Agents communicate via events through MCP server
- Redis pub/sub for asynchronous messaging
- Event handlers registered per agent

### Strategy Pattern
- Multiple trading strategies with common interface in `src/trading/strategies/`
- Pluggable strategy implementations
- Live, paper, and backtest execution modes

### Circuit Breaker Pattern
- Protection for MT4 connection resilience
- Automatic recovery with exponential backoff

## Configuration Management

Environment variables organized by category:

**Database:**
- `DATABASE_URL` - PostgreSQL connection string with asyncpg
- `REDIS_URL` - Redis connection string

**MT4 Connection:**
- `MT4_HOST`, `MT4_COMMAND_PORT`, `MT4_STREAM_PORT`
- `ZMQ_CLIENT_SECRET_KEY`, `ZMQ_CLIENT_PUBLIC_KEY`, `ZMQ_SERVER_PUBLIC_KEY`

**Security:**
- `JWT_SECRET_KEY`, `API_KEY`, `VALID_API_KEYS`

**Risk Limits:**
- `MAX_POSITION_SIZE`, `MAX_DAILY_LOSS`, `MAX_OPEN_POSITIONS`

**Feature Flags:**
- `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_FORECASTING`

**Monitoring:**
- `MLFLOW_TRACKING_URI`, `SENTRY_DSN`, `JAEGER_AGENT_HOST`

Configuration files at `config/environments/*.yaml` for environment-specific settings.

## Database Schema

10 core tables:
1. `market_data` - OHLCV time-series data with partitioning by date
2. `indicators` - Technical indicator values
3. `strategies` - Strategy configurations and allocations
4. `open_positions` - Currently active positions
5. `trading_history` - Complete trade history
6. `forecasts` - ML model predictions with ensemble blending
7. `strategy_performance` - Performance metrics per strategy
8. `trading_simulation` - Backtest results
9. `optimal_trades` - Optimal entry/exit points from analysis
10. `news_events` - Economic calendar events

All tables use SQLAlchemy ORM models at `src/database/models/`.

## Implementation Timeline

**Phase 1 (Week 1-2):** Foundation - Docker, database, basic API
**Phase 2 (Week 3-4):** Core services + MT4 integration + Security
**Phase 2.5 (Week 4-5):** Agent system implementation (all 10 agents + MCP)
**Phase 3 (Week 6-7):** ML pipeline and model registry
**Phase 4 (Week 8-9):** Security hardening and monitoring stack
**Phase 5 (Week 10):** Testing and documentation
**Phase 6 (Week 11):** Production deployment

**Total: 11 weeks**

## Testing Strategy

- Unit tests: 85%+ coverage target using pytest
- Integration tests: Test agent communication, database operations, MT4 connection
- E2E tests: Full trading flow from signal to execution
- Load tests: Using Locust for API and agent system
- Security tests: Input validation, authentication, authorization

## Monitoring and Observability

**Access URLs (when running):**
- Dashboard: http://localhost:3000
- API: http://localhost:8003
- MCP Server: http://localhost:7000
- Grafana: http://localhost:3001
- Prometheus: http://localhost:9090
- Kibana: http://localhost:5601
- Jaeger: http://localhost:16686
- MLflow: http://localhost:5000

**Key Metrics to Monitor:**
- API latency (target: <200ms p95)
- ML inference time (target: <50ms)
- Order execution time (target: <500ms)
- Agent response time (target: <100ms)
- System uptime (target: >99.5%)

## Reference Documents

This repository contains 5 comprehensive planning documents:

1. `PROJECT_REBUILD_SPECIFICATION.md` - Complete technical specification
2. `RiseTrader_Executive_Summary.md` - Quick reference and checklists
3. `RiseTrader_FINAL_BUILD_PLAN.md` - Implementation timeline with agent architecture
4. `RiseTrader_Plan_Validation.md` - Architecture validation and risk assessment
5. `RiseTrader_DevUI_Integration.md` - Microsoft Agent Framework DevUI integration

**Always consult these documents** when implementing features to ensure alignment with the overall architecture.

## Critical Warnings

1. **Never commit secrets** - Use environment variables for all sensitive data
2. **Test agents thoroughly** - Agents make autonomous trading decisions; extensive testing required
3. **Start with paper trading** - Always validate in paper mode before live trading
4. **Enable one strategy at a time** - Gradual rollout for production
5. **Monitor agent decisions** - Regular audits of agent decision-making logs
6. **Implement security first** - MT4 encryption and API auth are blocking requirements for production
7. **Backup before changes** - Always backup database before migrations or major changes

## Development Workflow

1. **Planning:** Review reference documents and create implementation plan
2. **Implementation:** Follow the phased approach in FINAL_BUILD_PLAN.md
3. **Testing:** Write tests before or alongside implementation
4. **Documentation:** Update docs as features are implemented
5. **Security:** Validate security requirements at each phase
6. **Monitoring:** Ensure observability for all new features
7. **Review:** Code review focusing on agent decision logic and risk management

## Agent Decision Flow

Understanding the agent workflow is critical:

```
Market Tick → MarketDataAgent validates
  → Emits "new_tick" event (MCP)
  → SignalGeneratorAgent processes
    → Calls MLPredictionAgent for forecasts
    → Calls RegimeDetectionAgent for context
    → Generates trading signal
  → Emits "signal_generated" event
  → RiskManagerAgent validates
    → Checks position limits
    → Calculates position size
    → Approves or rejects
  → If approved → Emits "trade_validated" event
  → ExecutionAgent executes
    → Sends order to MT4 via ZMQ
    → Verifies execution
    → Emits "trade_executed" event
  → PerformanceMonitorAgent updates P&L
  → RiskOverseerAgent checks portfolio risk
```

This autonomous flow requires careful testing and monitoring at each stage.

## Active Technologies
- PostgreSQL 15+ with async operations (positions, orders, account state, EA registry) (001-mt4-integration)
- Python 3.11+ + FastAPI 0.104.1, SQLAlchemy 2.0.23 (async), Pydantic 2.5.2, asyncpg 0.29.0, Redis 5.0.1, PyZMQ 25.1.2, Structlog 23.2.0, Prometheus-client 0.19.0 (002-fastapi-dashboard-api)
- PostgreSQL 15+ (async with asyncpg driver), Redis 7+ (pub/sub for real-time updates) (002-fastapi-dashboard-api)
- Python 3.11+ + Existing RiseTrader stack (SQLAlchemy 2.0+ async, asyncpg, pandas/numpy for metrics), Gymnasium (for RL environment interface), scipy (for statistical tests in A/B comparison) (006-backtesting-engine)
- PostgreSQL 15+ (existing 13.5M candle database from 001-mt4-integration) (006-backtesting-engine)

## Recent Changes
- 001-mt4-integration: Added Python 3.11+
