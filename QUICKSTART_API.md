# RiseTrader API - Quick Start Guide

Get the RiseTrader API running in 5 minutes!

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Running database and Redis instances

## Step 1: Install Dependencies

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP

# Install API dependencies
pip install -r requirements-api.txt
```

## Step 2: Configure Environment

Create `.env` file in project root:

```bash
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader

# Redis
REDIS_URL=redis://localhost:6379

# Server
HOST=0.0.0.0
PORT=8003
DEBUG=true
LOG_LEVEL=INFO

# CORS (for React dashboard)
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Features
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false
ENABLE_FORECASTING=true

# Agent Config
AGENT_CONFIG_PATH=/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/config/agents.yaml
EOF
```

## Step 3: Start the Server

```bash
# From project root
python main.py
```

You should see:

```
╔═══════════════════════════════════════════════════════════════╗
║                      RiseTrader API Server                    ║
║                  Autonomous Trading Platform                  ║
╠═══════════════════════════════════════════════════════════════╣
║  Version: 1.0.0                                               ║
║  Host:    0.0.0.0                                             ║
║  Port:    8003                                                ║
...
```

## Step 4: Test the API

Open your browser to:

### Interactive Documentation
http://localhost:8003/docs

### Test Endpoints

```bash
# Health check
curl http://localhost:8003/health

# List all agents
curl http://localhost:8003/api/v1/agents

# Get system status
curl http://localhost:8003/api/v1/system/status

# Get open positions
curl http://localhost:8003/api/v1/trading/positions

# Get market data
curl http://localhost:8003/api/v1/market-data/symbols
```

## Step 5: Explore the API

Visit these URLs in your browser:

1. **Swagger UI**: http://localhost:8003/docs
   - Interactive API documentation
   - Try endpoints directly from browser
   - See request/response schemas

2. **ReDoc**: http://localhost:8003/redoc
   - Beautiful API documentation
   - Easy to read and navigate

3. **Metrics**: http://localhost:8003/metrics
   - Prometheus metrics
   - Performance data

4. **Health**: http://localhost:8003/health
   - Quick health check
   - System uptime

## Common Commands

### Start/Stop Agents

```bash
# Start signal generator
curl -X POST http://localhost:8003/api/v1/agents/signal_generator/start

# Stop signal generator
curl -X POST http://localhost:8003/api/v1/agents/signal_generator/stop

# Restart agent
curl -X POST http://localhost:8003/api/v1/agents/signal_generator/restart

# Get agent status
curl http://localhost:8003/api/v1/agents/signal_generator

# List all agents
curl http://localhost:8003/api/v1/agents
```

### Trading Operations

```bash
# Get open positions
curl http://localhost:8003/api/v1/trading/positions

# Get trading history
curl http://localhost:8003/api/v1/trading/history

# Get position by ID
curl http://localhost:8003/api/v1/trading/positions/1
```

### Market Data

```bash
# Get available symbols
curl http://localhost:8003/api/v1/market-data/symbols

# Get latest data for CrudeOIL
curl http://localhost:8003/api/v1/market-data/CrudeOIL

# Get data with pagination
curl "http://localhost:8003/api/v1/market-data/CrudeOIL?page=1&page_size=50"
```

### Performance

```bash
# Get performance summary
curl http://localhost:8003/api/v1/performance/summary

# Get detailed metrics
curl http://localhost:8003/api/v1/performance/metrics

# Get by-strategy breakdown
curl http://localhost:8003/api/v1/performance/by-strategy
```

## Troubleshooting

### Issue: "Database connection failed"

**Check PostgreSQL is running:**
```bash
docker-compose ps postgres
# or
pg_isready -h localhost -p 5433
```

**Test connection:**
```bash
psql postgresql://postgres:risetrader2024@localhost:5433/risetrader -c "SELECT 1"
```

### Issue: "Redis connection failed"

**Check Redis is running:**
```bash
docker-compose ps redis
# or
redis-cli -h localhost -p 6379 ping
```

### Issue: "Agent coordinator not initialized"

**Check agent config exists:**
```bash
ls -la /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/config/agents.yaml
```

**View agent config:**
```bash
cat /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/config/agents.yaml
```

### Issue: "Import errors"

**Ensure all dependencies installed:**
```bash
pip install -r requirements-api.txt
```

**Check Python version:**
```bash
python --version  # Should be 3.11+
```

### View Logs

**Check application logs:**
```bash
# If running with docker-compose
docker-compose logs -f api

# If running directly, logs go to stdout
# Or check log file if configured
tail -f /path/to/log/file
```

## Development Mode

For development with auto-reload:

```bash
# Method 1: Using main.py
python main.py

# Method 2: Using uvicorn directly
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8003

# Method 3: With specific workers
uvicorn src.api.main:app --workers 4 --host 0.0.0.0 --port 8003
```

## Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=src/api --cov-report=html

# Run specific test file
pytest tests/integration/test_api_agents.py -v

# Run and watch
pytest-watch
```

## Next Steps

1. **Explore API Documentation**: Visit http://localhost:8003/docs
2. **Test Endpoints**: Use Swagger UI to test all endpoints
3. **Monitor Performance**: Check http://localhost:8003/metrics
4. **Integrate Dashboard**: Connect React dashboard to API
5. **Configure Agents**: Customize agent settings in `config/agents.yaml`

## Production Deployment

For production deployment, see `API_README.md` for:
- Docker deployment
- Systemd service setup
- Nginx reverse proxy configuration
- SSL/TLS setup
- Environment-specific configurations

## API Endpoints Summary

| Category | Base Path | Endpoints |
|----------|-----------|-----------|
| Agents | `/api/v1/agents` | 8 endpoints |
| Trading | `/api/v1/trading` | 6 endpoints |
| Market Data | `/api/v1/market-data` | 5 endpoints |
| Forecasts | `/api/v1/forecasts` | 3 endpoints |
| Performance | `/api/v1/performance` | 4 endpoints |
| Strategies | `/api/v1/strategies` | 6 endpoints |
| System | `/api/v1/system` | 4 endpoints |

**Total: 36+ endpoints**

## Key Files

- `main.py` - Entry point
- `src/api/main.py` - FastAPI application
- `src/api/config.py` - Configuration
- `src/api/routes/` - API route handlers
- `src/api/models/` - Pydantic models
- `src/api/middleware/` - Middleware components
- `requirements-api.txt` - Python dependencies

## Support

For detailed documentation, see:
- `API_README.md` - Complete API documentation
- `API_IMPLEMENTATION_SUMMARY.md` - Implementation details
- `/docs` endpoint - Interactive API docs

Happy Trading! 🚀
