# RiseTrader Project Rebuild Specification

## Executive Summary

This document provides a comprehensive specification for rebuilding the RiseTrader algorithmic trading system with improved organization, containerization, and production-readiness. The new structure follows best practices from ML research projects and production trading systems.

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Improved Project Structure](#improved-project-structure)
3. [Technology Stack](#technology-stack)
4. [Containerization Strategy](#containerization-strategy)
5. [Database Migration Strategy](#database-migration-strategy)
6. [MT4 Integration](#mt4-integration)
7. [Deployment Architecture](#deployment-architecture)
8. [Comprehensive Build Prompt](#comprehensive-build-prompt)

---

## Current State Analysis

### Existing Components

**Backend Services:**
- FastAPI REST API (port 8003)
- PostgreSQL database
- ZMQ-based MT4 connection (ports 5555/5556)
- Position monitoring service
- Real-time forecasting service

**Frontend:**
- React TypeScript admin dashboard (port 3000)
- TradingView charts integration
- Real-time data visualization

**ML Pipeline:**
- Multiple ML models (XGBoost, TFT, LSTM)
- Jupyter notebooks for research
- Feature engineering pipeline
- Forecast blending system

**Trading Infrastructure:**
- MT4 Expert Advisors (MQL4)
- Multi-strategy execution engine
- Risk management system
- Position sizing algorithms

**Database Schema:**
- `market_data` - OHLCV data
- `indicators` - Technical indicators
- `open_positions` - Active positions
- `trading_history` - Closed positions
- `strategies` - Strategy configurations
- `strategy_performance` - Performance metrics
- `forecasts` - ML predictions
- `trading_simulation` - Backtest results
- `optimal_trades` - Optimal entry/exit points
- `news_events` - Economic calendar

### Current Issues

1. **Organization**: Scattered Python files, multiple versions (V0, V1, V2)
2. **Deployment**: No containerization or orchestration
3. **Configuration**: Limited config management
4. **Testing**: Minimal test coverage
5. **Monitoring**: No centralized logging/metrics
6. **Documentation**: Inconsistent documentation
7. **CI/CD**: No automated pipelines
8. **Experiment Tracking**: No MLflow/W&B integration

---

## Improved Project Structure

```
RiseTrader/
│
├── .github/
│   └── workflows/
│       ├── ci.yml                    # CI/CD pipeline
│       ├── docker-build.yml          # Docker image builds
│       └── tests.yml                 # Automated testing
│
├── docker/
│   ├── api/
│   │   └── Dockerfile                # FastAPI service
│   ├── dashboard/
│   │   └── Dockerfile                # React dashboard
│   ├── ml-services/
│   │   └── Dockerfile                # ML inference services
│   ├── notebooks/
│   │   └── Dockerfile                # Jupyter environment
│   └── postgres/
│       ├── Dockerfile                # PostgreSQL with extensions
│       └── init.sql                  # Database initialization
│
├── docker-compose.yml                # Local development
├── docker-compose.prod.yml           # Production deployment
├── .dockerignore
│
├── config/
│   ├── __init__.py
│   ├── settings.py                   # Application settings
│   ├── database.py                   # Database configuration
│   ├── trading.py                    # Trading parameters
│   ├── ml_models.py                  # Model configurations
│   ├── logging.yaml                  # Logging configuration
│   └── environments/
│       ├── development.yaml
│       ├── staging.yaml
│       └── production.yaml
│
├── src/
│   ├── __init__.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI application
│   │   ├── dependencies.py           # DI containers
│   │   ├── middleware.py             # Custom middleware
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── market_data.py        # Market data endpoints
│   │       ├── indicators.py         # Technical indicators
│   │       ├── positions.py          # Position management
│   │       ├── strategies.py         # Strategy management
│   │       ├── forecasts.py          # ML forecasts
│   │       ├── backtests.py          # Backtesting
│   │       └── health.py             # Health checks
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py                   # SQLAlchemy base
│   │   ├── session.py                # Database sessions
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── market_data.py
│   │   │   ├── indicators.py
│   │   │   ├── positions.py
│   │   │   ├── strategies.py
│   │   │   ├── forecasts.py
│   │   │   ├── trades.py
│   │   │   └── performance.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # Base repository
│   │   │   ├── market_data_repo.py
│   │   │   ├── strategy_repo.py
│   │   │   └── forecast_repo.py
│   │   └── migrations/
│   │       ├── env.py                # Alembic environment
│   │       ├── script.py.mako
│   │       └── versions/             # Migration scripts
│   │
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── strategy_registry.py  # Strategy management
│   │   │   ├── tick_dispatcher.py    # Price distribution
│   │   │   ├── order_manager.py      # Order execution
│   │   │   └── runners/
│   │   │       ├── __init__.py
│   │   │       ├── base_runner.py    # Abstract base
│   │   │       ├── live_runner.py    # Live trading
│   │   │       ├── paper_runner.py   # Paper trading
│   │   │       └── backtest_runner.py
│   │   ├── strategies/
│   │   │   ├── __init__.py
│   │   │   ├── base_strategy.py      # Strategy interface
│   │   │   ├── ml_strategy.py        # ML-based strategies
│   │   │   ├── technical_strategy.py # Technical strategies
│   │   │   └── ensemble_strategy.py  # Multi-signal
│   │   ├── risk/
│   │   │   ├── __init__.py
│   │   │   ├── position_sizing.py    # Kelly criterion
│   │   │   ├── stop_loss.py          # Stop management
│   │   │   ├── portfolio_risk.py     # Portfolio VaR
│   │   │   └── risk_limits.py        # Risk constraints
│   │   └── execution/
│   │       ├── __init__.py
│   │       ├── mt4_connector.py      # MT4 ZMQ connection
│   │       ├── order_router.py       # Order routing
│   │       └── position_monitor.py   # Position tracking
│   │
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── loaders.py            # Data loading
│   │   │   ├── preprocessors.py      # Data preprocessing
│   │   │   ├── feature_engineering.py
│   │   │   └── datasets.py           # PyTorch datasets
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base_model.py         # Model interface
│   │   │   ├── xgboost_model.py
│   │   │   ├── tft_model.py          # Temporal Fusion
│   │   │   ├── lstm_model.py
│   │   │   └── ensemble_model.py
│   │   ├── training/
│   │   │   ├── __init__.py
│   │   │   ├── trainer.py            # Training loop
│   │   │   ├── validators.py         # Cross-validation
│   │   │   └── hyperparameter_tuning.py
│   │   ├── inference/
│   │   │   ├── __init__.py
│   │   │   ├── predictor.py          # Inference engine
│   │   │   ├── forecast_blender.py   # Ensemble blending
│   │   │   └── realtime_forecaster.py
│   │   └── evaluation/
│   │       ├── __init__.py
│   │       ├── metrics.py            # Performance metrics
│   │       └── backtester.py         # Model backtesting
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── technical.py              # Technical analysis
│   │   ├── fundamental.py            # Fundamental analysis
│   │   └── market_regime.py          # Regime detection
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── market_data_service.py    # Data fetching
│   │   ├── indicator_service.py      # Indicator calculation
│   │   ├── forecast_service.py       # Forecast management
│   │   └── notification_service.py   # Alerts/notifications
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py                # Logging utilities
│       ├── decorators.py             # Custom decorators
│       ├── validators.py             # Input validation
│       └── helpers.py                # Helper functions
│
├── dashboard/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── common/               # Reusable components
│   │   │   ├── charts/               # Chart components
│   │   │   ├── layout/               # Layout components
│   │   │   └── trading/              # Trading-specific
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx         # Main dashboard
│   │   │   ├── Strategies.tsx        # Strategy management
│   │   │   ├── Positions.tsx         # Position monitoring
│   │   │   ├── Backtests.tsx         # Backtest results
│   │   │   └── Analytics.tsx         # Performance analytics
│   │   ├── hooks/                    # Custom React hooks
│   │   ├── services/                 # API clients
│   │   ├── store/                    # State management
│   │   ├── types/                    # TypeScript types
│   │   ├── utils/                    # Utility functions
│   │   ├── App.tsx
│   │   └── index.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
│
├── research/
│   ├── notebooks/
│   │   ├── 01_data_exploration/
│   │   │   ├── 01_crude_oil_analysis.ipynb
│   │   │   ├── 02_correlation_analysis.ipynb
│   │   │   └── 03_feature_distributions.ipynb
│   │   ├── 02_feature_engineering/
│   │   │   ├── 01_technical_indicators.ipynb
│   │   │   ├── 02_derived_features.ipynb
│   │   │   └── 03_feature_importance.ipynb
│   │   ├── 03_model_development/
│   │   │   ├── 01_baseline_models.ipynb
│   │   │   ├── 02_xgboost_experiments.ipynb
│   │   │   ├── 03_tft_experiments.ipynb
│   │   │   └── 04_ensemble_methods.ipynb
│   │   ├── 04_backtesting/
│   │   │   ├── 01_strategy_backtests.ipynb
│   │   │   └── 02_portfolio_simulation.ipynb
│   │   └── 05_analysis/
│   │       ├── 01_performance_analysis.ipynb
│   │       └── 02_market_regime_analysis.ipynb
│   ├── experiments/
│   │   ├── configs/                  # Experiment configs
│   │   ├── results/                  # Experiment results
│   │   └── mlruns/                   # MLflow tracking
│   ├── scripts/
│   │   ├── train_model.py
│   │   ├── evaluate_model.py
│   │   ├── hyperparameter_search.py
│   │   └── export_model.py
│   └── data/
│       ├── raw/                      # Raw data
│       ├── processed/                # Processed data
│       ├── features/                 # Feature sets
│       └── models/                   # Trained models
│
├── mt4/
│   ├── experts/
│   │   ├── CrudeOILTraderV3.mq4
│   │   ├── ZigZagTrader.mq4
│   │   └── MLSignalReceiver.mq4      # Python signal receiver
│   ├── indicators/
│   ├── libraries/
│   │   └── ZMQLibrary.mq4            # ZMQ integration
│   └── scripts/
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Pytest fixtures
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_strategies.py
│   │   ├── test_risk.py
│   │   └── test_utils.py
│   ├── integration/
│   │   ├── test_api.py
│   │   ├── test_database.py
│   │   ├── test_mt4_connection.py
│   │   └── test_forecasting.py
│   └── e2e/
│       ├── test_trading_flow.py
│       └── test_backtest_flow.py
│
├── scripts/
│   ├── setup/
│   │   ├── init_database.sh
│   │   ├── load_sample_data.sh
│   │   └── create_admin_user.sh
│   ├── deployment/
│   │   ├── deploy_staging.sh
│   │   ├── deploy_production.sh
│   │   └── rollback.sh
│   └── maintenance/
│       ├── backup_database.sh
│       ├── cleanup_old_data.sh
│       └── health_check.sh
│
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── API.md                        # API documentation
│   ├── DATABASE.md                   # Database schema
│   ├── DEPLOYMENT.md                 # Deployment guide
│   ├── DEVELOPMENT.md                # Development guide
│   ├── ML_PIPELINE.md                # ML pipeline docs
│   └── TRADING_STRATEGIES.md         # Strategy documentation
│
├── .env.example                      # Environment variables
├── .gitignore
├── .dockerignore
├── requirements.txt                  # Python dependencies
├── requirements-dev.txt              # Dev dependencies
├── pyproject.toml                    # Python project config
├── setup.py                          # Package setup
├── pytest.ini                        # Pytest configuration
├── alembic.ini                       # Alembic configuration
├── Makefile                          # Common commands
└── README.md                         # Project README
```

---

## Technology Stack

### Backend
- **Python 3.11+** - Primary language
- **FastAPI** - REST API framework
- **SQLAlchemy 2.0+** - ORM
- **Alembic** - Database migrations
- **PostgreSQL 15+** - Primary database
- **Redis** - Caching and pub/sub
- **ZMQ (PyZMQ)** - MT4 communication

### ML/AI
- **PyTorch 2.0+** - Deep learning
- **XGBoost** - Gradient boosting
- **scikit-learn** - ML utilities
- **pandas** - Data manipulation
- **numpy** - Numerical computing
- **MLflow** - Experiment tracking
- **Optuna** - Hyperparameter tuning

### Frontend
- **React 18+** - UI framework
- **TypeScript** - Type safety
- **TradingView Lightweight Charts** - Charting
- **TanStack Query** - Data fetching
- **Zustand** - State management
- **TailwindCSS** - Styling

### DevOps
- **Docker** - Containerization
- **Docker Compose** - Local orchestration
- **Kubernetes** (optional) - Production orchestration
- **GitHub Actions** - CI/CD
- **Prometheus** - Metrics
- **Grafana** - Visualization
- **ELK Stack** - Logging

### Testing
- **pytest** - Python testing
- **pytest-asyncio** - Async tests
- **pytest-cov** - Coverage
- **locust** - Load testing
- **Jest** - Frontend testing

---

## Containerization Strategy

### Services Architecture

```yaml
services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    environment:
      POSTGRES_DB: risetrader
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  # Redis Cache
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data

  # FastAPI Backend
  api:
    build:
      context: .
      dockerfile: docker/api/Dockerfile
    ports: ["8003:8003"]
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@postgres:5432/risetrader
      REDIS_URL: redis://redis:6379
      MT4_HOST: ${MT4_HOST:-75.154.254.186}
      MT4_PORT: ${MT4_PORT:-5555}
    volumes:
      - ./src:/app/src
      - ./config:/app/config
      - model_storage:/app/models

  # ML Inference Service
  ml-service:
    build:
      context: .
      dockerfile: docker/ml-services/Dockerfile
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@postgres:5432/risetrader
      REDIS_URL: redis://redis:6379
    volumes:
      - model_storage:/app/models
      - ./research/data:/app/data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  # React Dashboard
  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    ports: ["3000:3000"]
    depends_on:
      - api
    environment:
      REACT_APP_API_URL: http://api:8003

  # Jupyter Notebooks (Development only)
  jupyter:
    build:
      context: .
      dockerfile: docker/notebooks/Dockerfile
    ports: ["8888:8888"]
    depends_on:
      - postgres
    volumes:
      - ./research/notebooks:/app/notebooks
      - ./research/data:/app/data
      - ./src:/app/src
    environment:
      JUPYTER_ENABLE_LAB: "yes"

  # MLflow Tracking Server
  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    ports: ["5000:5000"]
    depends_on:
      - postgres
    command: >
      mlflow server
      --backend-store-uri postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/mlflow
      --default-artifact-root /mlflow/artifacts
      --host 0.0.0.0
    volumes:
      - mlflow_data:/mlflow/artifacts

  # Prometheus (Monitoring)
  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes:
      - ./docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  # Grafana (Visualization)
  grafana:
    image: grafana/grafana:latest
    ports: ["3001:3000"]
    depends_on:
      - prometheus
      - postgres
    volumes:
      - grafana_data:/var/lib/grafana
      - ./docker/grafana/dashboards:/etc/grafana/provisioning/dashboards
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}

volumes:
  postgres_data:
  redis_data:
  model_storage:
  mlflow_data:
  prometheus_data:
  grafana_data:
```

### Multi-Stage Docker Builds

**FastAPI Service (docker/api/Dockerfile):**
```dockerfile
# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8003/health')"

# Run application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

**ML Service (docker/ml-services/Dockerfile):**
```dockerfile
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create directories for models and data
RUN mkdir -p /app/models /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

# Run ML service
CMD ["python", "-m", "src.ml.inference.realtime_forecaster"]
```

---

## Database Migration Strategy

### Backup Existing Database

```bash
# On source machine
pg_dump -h localhost -U postgres -d risetrader \
  --format=custom \
  --file=risetrader_backup_$(date +%Y%m%d_%H%M%S).dump

# Compress backup
gzip risetrader_backup_*.dump
```

### Restore to Docker Container

```bash
# Copy backup to Docker volume
# The file is located at  /Volumes/MSI/MSI-HX-Core/Desktop/rise_pg17.sql
docker cp risetrader_backup.dump.gz risetrader-postgres-1:/tmp/

# Restore database
docker exec -it risetrader-postgres-1 bash
gunzip /tmp/risetrader_backup.dump.gz
pg_restore -U postgres -d risetrader -v /tmp/risetrader_backup.dump

# Verify data
psql -U postgres -d risetrader -c "SELECT COUNT(*) FROM market_data;"
```

### Alembic Migration Setup

```python
# alembic/env.py
from src.database.base import Base
from src.database.models import *  # Import all models

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()
```

---

## MT4 Integration

### MT4 Server Configuration

```
MT4 Server IP: 75.154.254.186
ZMQ Ports: 5555 (commands), 5556 (data stream)
Protocol: JSON over ZMQ REQ/REP and PUB/SUB
```

### Connection Configuration

```yaml
# config/environments/production.yaml
mt4:
  host: "75.154.254.186"
  command_port: 5555
  stream_port: 5556
  timeout_ms: 5000
  reconnect_attempts: 3
  reconnect_delay_ms: 1000

  # Magic numbers for strategies
  magic_numbers:
    CrudeOILTraderV3: 1001
    ZigZagTrader: 1002
    MLStrategy: 1003
```

### Network Security

```yaml
# docker-compose.prod.yml
services:
  api:
    network_mode: "host"  # Or use bridge with explicit ports
    environment:
      MT4_HOST: "75.154.254.186"
      MT4_COMMAND_PORT: "5555"
      MT4_STREAM_PORT: "5556"
```

---

## Deployment Architecture

### Development Environment

```bash
# Clone repository
git clone <repository_url>
cd RiseTrader

# Copy environment variables
cp .env.example .env

# Edit .env with your credentials
vim .env

# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f api

# Access services:
# - API: http://localhost:8003
# - Dashboard: http://localhost:3000
# - Jupyter: http://localhost:8888
# - MLflow: http://localhost:5000
# - Grafana: http://localhost:3001
```

### Production Deployment

```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Restore database backup
./scripts/setup/restore_database.sh risetrader_backup.dump

# Run database migrations
docker-compose -f docker-compose.prod.yml run --rm api \
  alembic upgrade head

# Start production services
docker-compose -f docker-compose.prod.yml up -d

# Enable monitoring
./scripts/setup/init_monitoring.sh
```

---

## Comprehensive Build Prompt

**The following prompt can be provided to Claude/Codex to build the entire system:**

---

# COMPREHENSIVE BUILD PROMPT FOR RISETRADER SYSTEM

## Project Overview

Build a production-ready containerized algorithmic trading system called **RiseTrader** for crude oil markets. The system integrates Python-based ML forecasting, FastAPI backend, React dashboard, PostgreSQL database, and MetaTrader 4 via ZMQ communication.

## Core Requirements

### 1. Technology Stack

**Backend:**
- Python 3.11+ with FastAPI for REST API
- SQLAlchemy 2.0+ with async PostgreSQL driver (asyncpg)
- Alembic for database migrations
- Redis for caching and pub/sub
- PyZMQ for MT4 communication
- Pydantic v2 for data validation

**ML/AI:**
- PyTorch 2.0+ for deep learning models
- XGBoost for gradient boosting
- scikit-learn for utilities
- pandas, numpy for data processing
- MLflow for experiment tracking
- Optuna for hyperparameter optimization

**Frontend:**
- React 18+ with TypeScript
- TradingView Lightweight Charts
- TanStack Query (React Query) for data fetching
- Zustand for state management
- TailwindCSS for styling
- Vite for bundling

**Infrastructure:**
- Docker for containerization
- Docker Compose for orchestration
- PostgreSQL 15+ as primary database
- Redis 7+ for caching
- Prometheus + Grafana for monitoring
- GitHub Actions for CI/CD

### 2. Project Structure

Implement the following directory structure:

```
RiseTrader/
├── src/                          # Python source code
│   ├── api/                      # FastAPI application
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   └── routers/
│   ├── database/                 # Database layer
│   │   ├── models/
│   │   ├── repositories/
│   │   └── migrations/
│   ├── trading/                  # Trading engine
│   │   ├── engine/
│   │   ├── strategies/
│   │   ├── risk/
│   │   └── execution/
│   ├── ml/                       # ML pipeline
│   │   ├── data/
│   │   ├── models/
│   │   ├── training/
│   │   ├── inference/
│   │   └── evaluation/
│   ├── services/                 # Business services
│   └── utils/                    # Utilities
├── dashboard/                    # React frontend
├── research/                     # Jupyter notebooks
├── mt4/                          # MT4 Expert Advisors
├── tests/                        # Test suite
├── docker/                       # Docker files
├── config/                       # Configuration
├── scripts/                      # Deployment scripts
└── docs/                         # Documentation
```

### 3. Database Schema

Implement the following PostgreSQL tables:

**market_data:**
- Columns: id, time, symbol, import_symbol, timeframe, source, open, high, low, last, change, change_percent, volume
- Indexes: time, symbol, source
- Time-zone aware timestamps

**indicators:**
- Columns: id, market_data_id (FK), ma_20, ma_50, ma_200, rsi, macd, macd_signal, atr, sar, vwap, bb_upper, bb_middle, bb_lower, fib levels
- One-to-one with market_data
- Cascade delete

**strategies:**
- Columns: id, name, type (ENUM: python/mt4_ea), mode (ENUM: live/paper/backtest), real_capital_pct, virtual_capital_pct, risk_pct, enabled, mt4_ea_name, magic_number, config (JSON)
- Constraints: capital percentages 0-100, risk 0-10

**open_positions:**
- Columns: id, number (unique), type (ENUM: BUY/SELL), size, symbol, price, stop_loss, take_profit, commission, last_profit, last_update, last_strategy, simulation, strategy_id (FK)
- Track both real and simulated positions

**trading_history:**
- Columns: id, time, symbol, order_type, volume, price, sl, tp, commission, swap, profit, action, position_id, order_number, days_in_trade, simulation, strategy_id (FK)
- Complete audit trail

**forecasts:**
- Columns: id, model_type, model_version, symbol, forecast_horizon, predicted_price, model_confidence, prediction_timestamp, target_timestamp, actual_price, prediction_error, is_validated, model_metadata (JSON)
- Store ML predictions

**strategy_performance:**
- Columns: id, strategy_id (FK), date, pnl, trades_count, win_rate, max_drawdown, sharpe_ratio, total_volume, average_trade_duration, best_trade, worst_trade
- Performance tracking

**trading_simulation:**
- Columns: simulation_id, start_date, end_date, starting_capital, ending_capital, result, return_percent, max_drawdown, total_trades, win_rate
- Backtest results

**optimal_trades:**
- Columns: id, simulation_id (FK), entry_time, exit_time, symbol, trade_type, position_type, entry_market_data_id (FK), exit_market_data_id (FK), entry_price, exit_price, trade_duration, return_amount, return_percent, volume
- Optimal trade points

**news_events:**
- Columns: id, time, event_name, country, impact, actual, forecast, previous
- Economic calendar

**account_info:**
- Columns: id, timestamp, balance, equity, margin, free_margin, margin_level, profit
- Account snapshots

### 4. Docker Containerization

**Services to containerize:**

1. **postgres** - PostgreSQL 15 with init scripts
2. **redis** - Redis 7 for caching
3. **api** - FastAPI backend service
4. **ml-service** - ML inference service (with GPU support)
5. **dashboard** - React frontend (Nginx served)
6. **jupyter** - Jupyter Lab for research
7. **mlflow** - MLflow tracking server
8. **prometheus** - Metrics collection
9. **grafana** - Metrics visualization

**Multi-stage Dockerfile for API:**
```dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y gcc g++
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY src/ ./src/
COPY config/ ./config/
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
HEALTHCHECK CMD python -c "import requests; requests.get('http://localhost:8003/health')"
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

**docker-compose.yml:**
- Define all services with proper networking
- Mount volumes for data persistence
- Set environment variables
- Configure service dependencies
- Enable health checks

### 5. FastAPI Backend

**Application Structure:**

```python
# src/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize services
    await init_database()
    await start_forecasting_service()
    await start_position_monitor()
    yield
    # Shutdown: Cleanup
    await shutdown_services()

app = FastAPI(title="RiseTrader API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Include routers
app.include_router(market_data.router, prefix="/market-data")
app.include_router(indicators.router, prefix="/indicators")
app.include_router(positions.router, prefix="/positions")
app.include_router(strategies.router, prefix="/strategies")
app.include_router(forecasts.router, prefix="/forecasts")
app.include_router(backtests.router, prefix="/backtests")
```

**API Endpoints:**

**Market Data:**
- `GET /market-data/{symbol}` - Historical OHLCV
- `GET /market-data/{symbol}/latest` - Latest price
- `GET /market-data/symbols` - Available symbols

**Technical Indicators:**
- `GET /indicators/{symbol}` - Historical indicators
- `GET /indicators/{symbol}/latest` - Latest indicators
- `POST /indicators/calculate` - Calculate indicators

**Positions:**
- `GET /positions` - All open positions
- `GET /positions/{id}` - Position details
- `POST /positions/close/{id}` - Close position
- `POST /positions/close-all` - Emergency close all
- `PUT /positions/{id}/modify` - Modify SL/TP

**Strategies:**
- `GET /strategies` - All strategies
- `GET /strategies/{id}` - Strategy details
- `POST /strategies` - Create strategy
- `PUT /strategies/{id}` - Update strategy
- `DELETE /strategies/{id}` - Delete strategy
- `PUT /strategies/{id}/allocation` - Update allocation
- `POST /strategies/{id}/enable` - Enable strategy
- `POST /strategies/{id}/disable` - Disable strategy

**Forecasts:**
- `GET /forecasts/{symbol}` - Recent forecasts
- `GET /forecasts/{symbol}/latest` - Latest forecast
- `GET /forecasts/blend/{symbol}` - Blended forecast
- `GET /forecasts/leaderboard/{symbol}` - Model performance
- `POST /forecasts/create` - Create forecast

**Backtests:**
- `GET /backtests` - All backtest results
- `GET /backtests/{id}` - Backtest details
- `POST /backtests/run` - Run backtest
- `GET /backtests/{id}/trades` - Optimal trades

**Health:**
- `GET /health` - Service health
- `GET /health/services` - All services status

### 6. Trading Engine

**Strategy Registry:**
```python
class StrategyRegistry:
    def __init__(self, db_session, mt4_connection):
        self.strategies = {}
        self.runners = {}

    async def initialize(self):
        await self.load_strategies()
        await self.validate_allocations()
        await self.create_runners()

    async def validate_allocations(self):
        # Ensure total live capital <= 100%
        pass
```

**Base Runner:**
```python
class BaseRunner(ABC):
    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def on_tick(self, tick: Tick):
        pass
```

**Live Runner:**
- Connects to MT4
- Executes real orders
- Uses real capital allocation
- Sends to MT4 via ZMQ

**Paper Runner:**
- Simulates execution
- Uses virtual capital
- Stores in database with simulation=True
- No MT4 communication

**Backtest Runner:**
- Iterates historical data
- Simulates orders
- Calculates P&L
- Stores results

**Risk Management:**
```python
class PositionSizer:
    def calculate_position_size(
        self,
        strategy_allocation: float,
        account_balance: float,
        risk_pct: float,
        stop_loss_pips: float,
        pip_value: float
    ) -> float:
        # Kelly Criterion with risk constraints
        allocated_capital = account_balance * (strategy_allocation / 100)
        risk_amount = allocated_capital * (risk_pct / 100)
        position_size = risk_amount / (stop_loss_pips * pip_value)
        return position_size
```

### 7. ML Pipeline

**Model Interface:**
```python
class BaseModel(ABC):
    @abstractmethod
    def train(self, X_train, y_train, X_val, y_val):
        pass

    @abstractmethod
    def predict(self, X) -> np.ndarray:
        pass

    @abstractmethod
    def save(self, path: str):
        pass

    @abstractmethod
    def load(self, path: str):
        pass
```

**Forecast Blender:**
```python
class ForecastBlender:
    async def create_blended_forecast(
        self,
        symbol: str,
        forecast_horizon: str,
        strategy: BlendingStrategy
    ) -> dict:
        # Get recent forecasts
        forecasts = await self.get_recent_forecasts(symbol, forecast_horizon)

        # Apply blending strategy
        if strategy == BlendingStrategy.WEIGHTED_PERFORMANCE:
            weights = self.calculate_performance_weights(forecasts)
        elif strategy == BlendingStrategy.EQUAL_WEIGHT:
            weights = [1/len(forecasts)] * len(forecasts)

        # Blend predictions
        blended_price = sum(f.price * w for f, w in zip(forecasts, weights))

        # Store blend
        await self.store_blend(...)

        return result
```

**Real-time Forecaster:**
```python
class RealtimeForecaster:
    async def start_background_service(self):
        # Run forecasting loop
        while self.is_running:
            for model_config in self.models.values():
                if model_config.enabled:
                    await self.run_forecast(model_config)
            await asyncio.sleep(60)
```

### 8. MT4 Integration

**MT4 Connection:**
```python
class MT4Connection:
    def __init__(self, host: str, command_port: int, stream_port: int):
        self.context = zmq.asyncio.Context()
        self.command_socket = self.context.socket(zmq.REQ)
        self.command_socket.connect(f"tcp://{host}:{command_port}")

        self.stream_socket = self.context.socket(zmq.SUB)
        self.stream_socket.connect(f"tcp://{host}:{stream_port}")
        self.stream_socket.subscribe("")

    async def send_command(self, command: str, params: dict) -> dict:
        request = {"command": command, "params": params}
        await self.command_socket.send_json(request)
        response = await self.command_socket.recv_json()
        return response

    async def place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float,
        tp: float,
        magic_number: int
    ) -> dict:
        return await self.send_command("place_market_order", {
            "symbol": symbol,
            "type": order_type,
            "volume": volume,
            "stopLoss": sl,
            "takeProfit": tp,
            "magic": magic_number
        })
```

**MT4 Configuration:**
- Host: 75.154.254.186
- Command Port: 5555
- Stream Port: 5556
- Timeout: 5000ms
- Protocol: JSON over ZMQ

### 9. React Dashboard

**Pages:**
1. **Dashboard** - Overview, account info, P&L charts
2. **Strategies** - Strategy management, allocations, performance
3. **Positions** - Open positions, modify/close
4. **Backtests** - Run backtests, view results
5. **Analytics** - Performance analytics, model leaderboard
6. **Market Data** - Real-time charts, indicators

**Key Components:**
```tsx
// TradingView Chart
export const PriceChart: React.FC<Props> = ({ symbol, timeframe }) => {
  const chartRef = useRef<IChartApi>();
  const { data } = useMarketData(symbol, timeframe);

  useEffect(() => {
    if (chartRef.current && data) {
      chartRef.current.setData(data);
    }
  }, [data]);

  return <div ref={chartRef} />;
};

// Position Table
export const PositionTable: React.FC = () => {
  const { positions, closePosition } = usePositions();

  return (
    <table>
      {positions.map(pos => (
        <tr key={pos.id}>
          <td>{pos.symbol}</td>
          <td>{pos.type}</td>
          <td>{pos.size}</td>
          <td>{pos.price}</td>
          <td>{pos.profit}</td>
          <td>
            <button onClick={() => closePosition(pos.id)}>
              Close
            </button>
          </td>
        </tr>
      ))}
    </table>
  );
};
```

### 10. Configuration Management

**Environment Variables (.env):**
```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/risetrader
REDIS_URL=redis://redis:6379

# MT4
MT4_HOST=75.154.254.186
MT4_COMMAND_PORT=5555
MT4_STREAM_PORT=5556

# API
API_HOST=0.0.0.0
API_PORT=8003
SECRET_KEY=your-secret-key

# ML
MLFLOW_TRACKING_URI=http://mlflow:5000

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
```

**Configuration Files (config/):**
```python
# config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    mt4_host: str
    mt4_command_port: int
    mt4_stream_port: int

    class Config:
        env_file = ".env"

settings = Settings()
```

### 11. Testing Strategy

**Unit Tests:**
- Test individual functions and classes
- Mock external dependencies
- 80%+ code coverage

**Integration Tests:**
- Test API endpoints
- Test database operations
- Test MT4 connection

**E2E Tests:**
- Test complete trading flow
- Test backtest execution
- Test forecast generation

**Test Configuration:**
```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --verbose
    --cov=src
    --cov-report=html
    --cov-report=term-missing
```

### 12. Database Migration

**Restore from Backup:**
```bash
# scripts/setup/restore_database.sh
#!/bin/bash

BACKUP_FILE=$1

# Copy backup to container
docker cp $BACKUP_FILE risetrader-postgres-1:/tmp/backup.dump

# Restore
docker exec -it risetrader-postgres-1 \
  pg_restore -U postgres -d risetrader -v /tmp/backup.dump

# Verify
docker exec -it risetrader-postgres-1 \
  psql -U postgres -d risetrader -c "SELECT COUNT(*) FROM market_data;"
```

**Alembic Migrations:**
```python
# Generate migration
alembic revision --autogenerate -m "Add new feature"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### 13. Monitoring and Logging

**Structured Logging:**
```python
import structlog

logger = structlog.get_logger()

logger.info(
    "order_placed",
    symbol="CrudeOIL",
    type="BUY",
    volume=0.5,
    price=73.45,
    strategy="MLStrategy"
)
```

**Prometheus Metrics:**
```python
from prometheus_client import Counter, Gauge, Histogram

# Metrics
orders_total = Counter('orders_total', 'Total orders placed')
positions_open = Gauge('positions_open', 'Number of open positions')
order_latency = Histogram('order_latency_seconds', 'Order execution latency')
```

**Grafana Dashboards:**
- Trading performance
- System metrics
- ML model performance
- API metrics

### 14. Deployment Instructions

**Initial Setup:**
```bash
# 1. Clone repository
git clone <repo_url>
cd RiseTrader

# 2. Configure environment
cp .env.example .env
vim .env  # Edit with your credentials

# 3. Build containers
docker-compose build

# 4. Restore database
./scripts/setup/restore_database.sh backup.dump

# 5. Run migrations
docker-compose run --rm api alembic upgrade head

# 6. Start services
docker-compose up -d

# 7. Verify health
curl http://localhost:8003/health
```

**Production Deployment:**
```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d

# Enable SSL/TLS
certbot certonly --webroot -w /var/www/html -d api.risetrader.com

# Setup monitoring
./scripts/setup/init_monitoring.sh

# Configure backups
crontab -e
# 0 2 * * * /path/to/scripts/backup_database.sh
```

### 15. Documentation

Create comprehensive documentation:

**README.md:**
- Project overview
- Quick start guide
- Development setup
- Deployment instructions

**ARCHITECTURE.md:**
- System architecture
- Component descriptions
- Data flow diagrams

**API.md:**
- Complete API reference
- Request/response examples
- Authentication

**DATABASE.md:**
- Schema documentation
- Relationship diagrams
- Query examples

**DEVELOPMENT.md:**
- Coding standards
- Git workflow
- Testing guidelines

**DEPLOYMENT.md:**
- Infrastructure requirements
- Deployment steps
- Troubleshooting

### 16. Code Quality

**Linting and Formatting:**
```toml
# pyproject.toml
[tool.black]
line-length = 100
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

**Pre-commit Hooks:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
```

### 17. CI/CD Pipeline

**.github/workflows/ci.yml:**
```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run linters
        run: |
          black --check src/
          isort --check src/
          mypy src/

      - name: Run tests
        run: pytest

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build:
    runs-on: ubuntu-latest
    needs: test

    steps:
      - uses: actions/checkout@v3

      - name: Build Docker images
        run: docker-compose build

      - name: Push to registry
        if: github.ref == 'refs/heads/main'
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
          docker-compose push
```

### 18. Security Considerations

**API Security:**
- API key authentication
- Rate limiting
- Input validation
- SQL injection prevention

**Network Security:**
- TLS/SSL for all connections
- Firewall rules
- VPN for MT4 connection (production)

**Data Security:**
- Encrypted database backups
- Secure credential storage
- No hardcoded secrets

### 19. Performance Optimization

**Database:**
- Connection pooling
- Query optimization
- Proper indexing
- Materialized views for analytics

**API:**
- Async operations
- Response caching
- Database query optimization
- Connection reuse

**ML Inference:**
- Model quantization
- Batch predictions
- GPU acceleration
- Model caching

### 20. Deliverables

**Code:**
- Complete source code following the structure above
- All Docker configurations
- Database migrations
- Test suite

**Documentation:**
- README with quick start
- Architecture documentation
- API reference
- Deployment guide
- Development guide

**Configuration:**
- Environment variable templates
- Docker Compose files
- CI/CD pipelines
- Monitoring dashboards

**Scripts:**
- Database backup/restore
- Deployment automation
- Health checks
- Maintenance tasks

---

## Implementation Checklist

- [ ] Project structure setup
- [ ] Database models and migrations
- [ ] FastAPI backend with all endpoints
- [ ] Trading engine with strategy registry
- [ ] Risk management system
- [ ] ML pipeline with models
- [ ] MT4 connection implementation
- [ ] React dashboard
- [ ] Docker containerization
- [ ] Database backup/restore scripts
- [ ] Monitoring setup (Prometheus/Grafana)
- [ ] Testing suite
- [ ] CI/CD pipeline
- [ ] Documentation
- [ ] Deployment scripts

---

## Success Criteria

1. **Functionality:**
   - All API endpoints working
   - Trading engine executing strategies
   - ML forecasts generating
   - Dashboard displaying data
   - MT4 connection established

2. **Performance:**
   - API response time < 200ms
   - ML inference < 50ms
   - Database queries optimized
   - Real-time updates working

3. **Reliability:**
   - 99% uptime
   - Graceful error handling
   - Automatic reconnection
   - Data integrity maintained

4. **Maintainability:**
   - Clean, documented code
   - Comprehensive tests
   - Easy deployment
   - Clear documentation

5. **Security:**
   - Authenticated API
   - Encrypted connections
   - Secure credential storage
   - Input validation

---

## Notes for Claude/Codex

1. **Database**: Use the existing RiseTrader PostgreSQL backup for initial data
2. **MT4 Server**: External server at 75.154.254.186:5555/5556
3. **Code Quality**: Follow PEP 8, use type hints, write docstrings
4. **Testing**: Write tests for all critical components
5. **Documentation**: Document all major functions and classes
6. **Error Handling**: Implement comprehensive error handling
7. **Logging**: Use structured logging throughout
8. **Performance**: Optimize for low latency where needed
9. **Scalability**: Design for future horizontal scaling
10. **Maintainability**: Keep code clean, modular, and well-organized

---

# END OF BUILD PROMPT

