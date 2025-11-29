# Quickstart Guide: Dashboard API Service

**Feature**: 002-fastapi-dashboard-api
**Date**: 2025-11-24
**Target Audience**: Developers implementing and testing the Dashboard API

## Overview

This guide provides step-by-step instructions for setting up, running, and testing the Dashboard API Service locally.

**Prerequisites**:
- Python 3.11+
- PostgreSQL 15+ (with populated `market_data` and related tables)
- Redis 7+
- MT4 Integration Service running (feature 001-mt4-integration)
- Docker and Docker Compose (optional but recommended)

---

## Quick Start (5 minutes)

### 1. Environment Setup

Create `.env` file in project root (if not exists):

```bash
# Database
DATABASE_URL=postgresql+asyncpg://risetrader:password@localhost:5432/risetrader

# Redis
REDIS_URL=redis://localhost:6379/0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8003
API_RELOAD=true

# CORS (for dashboard access)
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
CORS_ENABLED=true

# Prometheus Metrics
PROMETHEUS_ENABLED=true

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 3. Run Database Migrations

```bash
# Apply all migrations
alembic upgrade head

# Verify current migration
alembic current
```

### 4. Start the API

```bash
# Development mode with auto-reload
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8003 --reload

# Or using the main entry point
python src/api/main.py
```

### 5. Verify API is Running

```bash
# Health check
curl http://localhost:8003/health

# Expected response:
# {"status":"healthy","version":"1.0.0","uptime_seconds":5.2}

# Interactive API docs
open http://localhost:8003/docs  # Swagger UI
open http://localhost:8003/redoc  # ReDoc
```

---

## Docker Quick Start (Recommended)

### 1. Start All Services

```bash
# Start PostgreSQL, Redis, and API
docker-compose up -d

# View logs
docker-compose logs -f api

# Check service status
docker-compose ps
```

### 2. Verify Services

```bash
# Check API health
curl http://localhost:8003/health

# Check database connection
docker-compose exec api alembic current

# Check Redis connection
docker-compose exec redis redis-cli ping
```

### 3. Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (CAUTION: deletes data)
docker-compose down -v
```

---

## Testing the API

### Market Data Endpoints

```bash
# Get available symbols
curl http://localhost:8003/api/market-data/symbols | jq

# Get latest market data for CrudeOIL (M5 timeframe)
curl "http://localhost:8003/api/market-data/CrudeOIL?timeframe=M5&limit=500" | jq

# Get market data for specific time range
curl "http://localhost:8003/api/market-data/CrudeOIL/range?start_time=2024-11-24T00:00:00Z&end_time=2024-11-24T23:59:59Z" | jq
```

### Trading Endpoints

```bash
# Get account information
curl http://localhost:8003/api/trading/account | jq

# Get open positions
curl http://localhost:8003/api/trading/positions | jq

# Get open positions for specific symbol
curl "http://localhost:8003/api/trading/positions?symbol=CrudeOIL" | jq

# Get trading history (last 50 trades)
curl "http://localhost:8003/api/trading/history?page=1&page_size=50" | jq

# Get trading history for specific date range
curl "http://localhost:8003/api/trading/history?start_date=2024-11-01T00:00:00Z&end_date=2024-11-24T23:59:59Z" | jq
```

### Forecast Endpoints

```bash
# Get latest forecasts for all symbols
curl http://localhost:8003/api/forecasts/latest | jq

# Get forecasts for specific symbol
curl http://localhost:8003/api/forecasts/CrudeOIL | jq

# Filter forecasts by horizon
curl "http://localhost:8003/api/forecasts/latest?horizon=1h" | jq
```

### Strategy Endpoints

```bash
# Get all strategies
curl http://localhost:8003/api/strategies | jq

# Get strategy allocations
curl http://localhost:8003/api/strategies/1/allocations | jq

# Get strategy performance
curl "http://localhost:8003/api/strategies/1/performance?period=monthly" | jq
```

### Real-Time Streaming (SSE)

```bash
# Stream market data for CrudeOIL and EURUSD
curl "http://localhost:8003/api/stream/market-data?symbols=CrudeOIL,EURUSD"

# Stream account updates
curl http://localhost:8003/api/stream/account

# Expected output format (SSE):
# event: market_data
# data: {"symbol":"CrudeOIL","price":75.45,"timestamp":"2024-11-24T10:30:00Z"}
#
# event: market_data
# data: {"symbol":"EURUSD","price":1.0945,"timestamp":"2024-11-24T10:30:01Z"}
```

### System Endpoints

```bash
# Comprehensive health check
curl http://localhost:8003/api/system/health | jq

# Prometheus metrics
curl http://localhost:8003/metrics
```

---

## Development Workflow

### 1. Create New Database Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add strategy tables"

# Review generated migration in migrations/versions/

# Apply migration
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

### 2. Add New Endpoint

**Step 1**: Define Pydantic request/response models in `src/api/models/`

```python
# src/api/models/new_feature.py
from pydantic import BaseModel

class NewFeatureResponse(BaseModel):
    id: int
    name: str
    ...
```

**Step 2**: Create route handler in `src/api/routes/`

```python
# src/api/routes/new_feature.py
from fastapi import APIRouter, Depends
from ..models import NewFeatureResponse

router = APIRouter(prefix="/new-feature", tags=["new-feature"])

@router.get("/", response_model=NewFeatureResponse)
async def get_new_feature():
    return {"id": 1, "name": "example"}
```

**Step 3**: Register router in `src/api/main.py`

```python
from .routes import new_feature

app.include_router(new_feature.router, prefix="/api")
```

**Step 4**: Write tests FIRST (TDD)

```python
# tests/integration/test_new_feature_api.py
async def test_get_new_feature(client):
    response = await client.get("/api/new-feature/")
    assert response.status_code == 200
    assert response.json()["id"] == 1
```

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/integration/test_market_data_api.py

# Run tests matching pattern
pytest -k "test_market_data"

# Run with verbose output
pytest -v

# Run contract tests only
pytest tests/contract/
```

### 4. Code Quality Checks

```bash
# Format code with black
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking with mypy
mypy src/

# Linting with flake8
flake8 src/ tests/
```

---

## Troubleshooting

### API Won't Start

**Problem**: `ModuleNotFoundError: No module named 'src'`

**Solution**:
```bash
# Ensure PYTHONPATH includes project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or install package in development mode
pip install -e .
```

### Database Connection Error

**Problem**: `asyncpg.exceptions.InvalidCatalogNameError: database "risetrader" does not exist`

**Solution**:
```bash
# Create database
docker-compose exec postgres createdb -U risetrader risetrader

# Or using psql
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE risetrader;"
```

### Redis Connection Error

**Problem**: `redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379`

**Solution**:
```bash
# Start Redis with Docker Compose
docker-compose up -d redis

# Or start Redis manually
redis-server

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

### CORS Error in Dashboard

**Problem**: `Access to fetch at 'http://localhost:8003/api/market-data/symbols' from origin 'http://localhost:3000' has been blocked by CORS policy`

**Solution**:
```bash
# Add dashboard origin to .env
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
CORS_ENABLED=true

# Restart API
```

### SSE Stream Not Updating

**Problem**: Server-Sent Events stream connects but no data arrives

**Solution**:
```bash
# 1. Verify MT4 Integration Service is running
docker-compose ps mt4-service

# 2. Check Redis pub/sub channels have data
docker-compose exec redis redis-cli
> PSUBSCRIBE *
# Should see messages being published

# 3. Check API logs for subscription errors
docker-compose logs -f api | grep -i "redis\|subscribe"

# 4. Verify symbols parameter is correct
curl "http://localhost:8003/api/stream/market-data?symbols=CrudeOIL"
```

### Slow Query Performance

**Problem**: Chart data queries taking >2 seconds

**Solution**:
```bash
# 1. Verify indexes exist
docker-compose exec postgres psql -U risetrader -c "\d market_data"
# Should show composite index on (symbol, timeframe, time)

# 2. Analyze query performance
docker-compose exec postgres psql -U risetrader -c "EXPLAIN ANALYZE SELECT * FROM market_data WHERE symbol='CrudeOIL' AND timeframe='M5' ORDER BY time DESC LIMIT 500;"

# 3. Check if autovacuum is running
docker-compose exec postgres psql -U risetrader -c "SELECT * FROM pg_stat_user_tables WHERE relname='market_data';"

# 4. Manually vacuum if needed
docker-compose exec postgres psql -U risetrader -c "VACUUM ANALYZE market_data;"
```

---

## Performance Testing

### Load Testing with Locust

```bash
# Create locustfile.py
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class DashboardUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def get_market_data(self):
        self.client.get("/api/market-data/CrudeOIL?timeframe=M5&limit=500")

    @task(2)
    def get_account(self):
        self.client.get("/api/trading/account")

    @task(1)
    def get_positions(self):
        self.client.get("/api/trading/positions")
EOF

# Run load test with 50 concurrent users
locust -f locustfile.py --host=http://localhost:8003 --users 50 --spawn-rate 10

# Open web UI
open http://localhost:8089
```

### Benchmark Specific Endpoint

```bash
# Install Apache Bench
sudo apt-get install apache2-utils  # Ubuntu
brew install ab  # macOS

# Benchmark market data endpoint
ab -n 1000 -c 50 http://localhost:8003/api/market-data/CrudeOIL?timeframe=M5&limit=500

# Expected results (success criteria):
# Time per request: <200ms (p95)
# Failed requests: <5%
```

---

## Monitoring

### View Prometheus Metrics

```bash
# Access metrics endpoint
curl http://localhost:8003/metrics

# Key metrics to monitor:
# - api_request_duration_seconds_bucket (latency)
# - api_request_total (request count)
# - api_request_errors_total (error count)
# - database_connection_pool_size (connection pool usage)
```

### View Structured Logs

```bash
# Tail API logs (JSON format)
docker-compose logs -f api | jq

# Filter errors only
docker-compose logs -f api | grep ERROR | jq

# Filter specific operation
docker-compose logs -f api | grep "get_market_data" | jq
```

---

## Next Steps

1. **Implement Real-Time Streaming**: Complete SSE endpoint implementation with Redis pub/sub integration
2. **Add Caching Layer**: Implement Redis caching with cache-aside pattern
3. **Enhance Error Handling**: Add comprehensive error responses and validation
4. **Write Tests**: Achieve 85%+ test coverage following TDD approach
5. **Performance Optimization**: Add database query optimization and connection pooling tuning
6. **API Documentation**: Enhance OpenAPI spec with more examples and descriptions

---

## Resources

- **API Documentation**: http://localhost:8003/docs (Swagger UI)
- **OpenAPI Spec**: `specs/002-fastapi-dashboard-api/contracts/openapi-spec.yaml`
- **Data Models**: `specs/002-fastapi-dashboard-api/data-model.md`
- **Research Decisions**: `specs/002-fastapi-dashboard-api/research.md`
- **Implementation Plan**: `specs/002-fastapi-dashboard-api/plan.md`
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Pydantic V2**: https://docs.pydantic.dev/latest/
- **Redis Pub/Sub**: https://redis.io/docs/interact/pubsub/

---

**Last Updated**: 2025-11-24
**Maintained By**: RiseTrader Development Team
