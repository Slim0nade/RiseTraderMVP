# RiseTrader FastAPI Application

Complete REST API implementation for the RiseTrader autonomous algorithmic trading platform.

## Overview

The RiseTrader API provides comprehensive endpoints for:
- Agent management and monitoring
- Trading operations (positions, orders, history)
- Market data access and streaming
- ML forecast generation and retrieval
- Performance analytics and metrics
- Strategy management and optimization
- System health and monitoring

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│  Middleware Layer                                            │
│  ├─ CORS Middleware                                          │
│  ├─ Logging Middleware (Structured Logs)                    │
│  ├─ Metrics Middleware (Prometheus)                         │
│  └─ Error Handling Middleware                               │
├─────────────────────────────────────────────────────────────┤
│  API Routes (/api/v1)                                        │
│  ├─ /agents          - Agent management                     │
│  ├─ /trading         - Trading operations                   │
│  ├─ /market-data     - Market data access                   │
│  ├─ /forecasts       - ML predictions                       │
│  ├─ /performance     - Analytics & metrics                  │
│  ├─ /strategies      - Strategy management                  │
│  └─ /system          - Health & system ops                  │
├─────────────────────────────────────────────────────────────┤
│  Dependencies                                                │
│  ├─ Database Session (AsyncSession)                         │
│  ├─ Agent Coordinator                                        │
│  ├─ Authentication (JWT + API Key)                          │
│  └─ Rate Limiting                                            │
├─────────────────────────────────────────────────────────────┤
│  Backend Services                                            │
│  ├─ Agent Coordinator (10 Trading Agents)                   │
│  ├─ MCP Server (Event Bus)                                  │
│  ├─ PostgreSQL Database                                     │
│  └─ Redis Cache                                              │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements-api.txt
```

### 2. Configure Environment

Create a `.env` file:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader

# Redis
REDIS_URL=redis://localhost:6379

# API Configuration
HOST=0.0.0.0
PORT=8003
DEBUG=false
LOG_LEVEL=INFO

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Security (Optional - for production)
JWT_SECRET_KEY=your-secret-key-here
API_KEY=your-api-key-here

# Feature Flags
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false
ENABLE_FORECASTING=true

# MT4 Configuration
MT4_HOST=75.154.254.174
MT4_COMMAND_PORT=5555
MT4_STREAM_PORT=5556

# Agent Configuration
AGENT_CONFIG_PATH=/path/to/config/agents.yaml
```

### 3. Start the Server

```bash
# Development mode with auto-reload
python main.py

# Or using uvicorn directly
uvicorn src.api.main:app --host 0.0.0.0 --port 8003 --reload

# Production mode
uvicorn src.api.main:app --host 0.0.0.0 --port 8003 --workers 4
```

## API Endpoints

### Agent Management (`/api/v1/agents`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List all agents with status |
| GET | `/agents/{agent_id}` | Get agent details |
| POST | `/agents/{agent_id}/start` | Start an agent |
| POST | `/agents/{agent_id}/stop` | Stop an agent |
| POST | `/agents/{agent_id}/restart` | Restart an agent |
| GET | `/agents/{agent_id}/metrics` | Get agent metrics |
| GET | `/agents/{agent_id}/logs` | Get agent logs |
| POST | `/agents/{agent_id}/command` | Send command to agent |

**Example:**
```bash
# List all agents
curl http://localhost:8003/api/v1/agents

# Start signal generator agent
curl -X POST http://localhost:8003/api/v1/agents/signal_generator/start

# Send command to agent
curl -X POST http://localhost:8003/api/v1/agents/signal_generator/command \
  -H "Content-Type: application/json" \
  -d '{"action": "generate_signal", "parameters": {"symbol": "CrudeOIL"}}'
```

### Trading Operations (`/api/v1/trading`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/trading/positions` | Get open positions |
| GET | `/trading/positions/{position_id}` | Get position details |
| POST | `/trading/positions/{position_id}/close` | Close position |
| GET | `/trading/history` | Get trading history |
| GET | `/trading/history/{trade_id}` | Get trade details |
| POST | `/trading/orders` | Place new order |

**Example:**
```bash
# Get all open positions
curl http://localhost:8003/api/v1/trading/positions

# Get positions for specific symbol
curl "http://localhost:8003/api/v1/trading/positions?symbol=CrudeOIL"

# Place order (paper trading)
curl -X POST http://localhost:8003/api/v1/trading/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "CrudeOIL",
    "order_type": "MARKET",
    "position_type": "BUY",
    "size": 0.1,
    "stop_loss": 70.50,
    "take_profit": 75.00,
    "mode": "PAPER"
  }'
```

### Market Data (`/api/v1/market-data`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/market-data/{symbol}` | Get latest market data |
| GET | `/market-data/{symbol}/range` | Get data for time range |
| GET | `/market-data/symbols` | Get available symbols |
| POST | `/market-data/stream/start` | Start data streaming |
| POST | `/market-data/stream/stop` | Stop data streaming |

**Example:**
```bash
# Get latest data for CrudeOIL
curl http://localhost:8003/api/v1/market-data/CrudeOIL

# Get data for specific time range
curl "http://localhost:8003/api/v1/market-data/CrudeOIL/range?start_time=2024-01-01T00:00:00Z&end_time=2024-01-15T23:59:59Z"

# Get all available symbols
curl http://localhost:8003/api/v1/market-data/symbols
```

### ML Forecasts (`/api/v1/forecasts`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/forecasts/{symbol}` | Get latest forecasts |
| GET | `/forecasts/{symbol}/history` | Get historical forecasts |
| POST | `/forecasts/generate` | Trigger forecast generation |

**Example:**
```bash
# Get latest forecasts
curl http://localhost:8003/api/v1/forecasts/CrudeOIL

# Generate new forecasts
curl -X POST http://localhost:8003/api/v1/forecasts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "CrudeOIL",
    "model_types": ["XGBoost", "LSTM"],
    "horizons": ["1h", "4h"]
  }'
```

### Performance Analytics (`/api/v1/performance`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/performance/summary` | Overall P&L summary |
| GET | `/performance/metrics` | Detailed metrics |
| GET | `/performance/by-strategy` | Per-strategy breakdown |
| GET | `/performance/chart` | Equity curve data |

### Strategy Management (`/api/v1/strategies`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/strategies` | List all strategies |
| GET | `/strategies/{strategy_id}` | Get strategy details |
| PUT | `/strategies/{strategy_id}` | Update strategy config |
| POST | `/strategies/{strategy_id}/enable` | Enable strategy |
| POST | `/strategies/{strategy_id}/disable` | Disable strategy |
| GET | `/strategies/{strategy_id}/performance` | Strategy performance |

### System Operations (`/api/v1/system`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/system/health` | Health check |
| GET | `/system/status` | Detailed system status |
| POST | `/system/emergency-stop` | Emergency stop all trading |
| POST | `/system/restart` | Restart system |

## API Documentation

### Interactive API Docs

Once the server is running, visit:
- **Swagger UI**: http://localhost:8003/docs
- **ReDoc**: http://localhost:8003/redoc
- **OpenAPI JSON**: http://localhost:8003/openapi.json

### Prometheus Metrics

Metrics are exposed at: http://localhost:8003/metrics

Available metrics:
- `api_requests_total` - Total API requests by method/endpoint/status
- `api_request_duration_seconds` - Request duration histogram
- `api_active_requests` - Current active requests
- `api_errors_total` - Total errors by type
- `trading_operations_total` - Trading operations by type/status
- `agent_operations_total` - Agent operations by agent/type/status
- `ml_predictions_total` - ML predictions by model/symbol

## Authentication

### API Key Authentication (Optional)

Add API key to requests:

```bash
curl http://localhost:8003/api/v1/agents \
  -H "X-API-Key: your-api-key-here"
```

Configure API keys in `.env`:
```env
API_KEY=primary-key
VALID_API_KEYS=key1,key2,key3
```

### JWT Authentication (Optional)

For production environments, JWT authentication is recommended.

## Rate Limiting

Default rate limits:
- 60 requests per minute
- 1000 requests per hour

Rate limit headers included in responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## Error Handling

All errors return consistent JSON format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "status_code": 400,
    "details": {},
    "request_id": "uuid"
  }
}
```

HTTP Status Codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `422` - Validation Error
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
- `503` - Service Unavailable

## Logging

Structured JSON logging with correlation IDs:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "event": "request_completed",
  "request_id": "uuid",
  "method": "GET",
  "url": "/api/v1/agents",
  "status_code": 200,
  "duration_ms": 45.2
}
```

## Performance

Target performance metrics:
- API endpoints: <200ms (p95)
- Health check: <10ms
- Database queries: <100ms
- Concurrent requests: 100+

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# With coverage
pytest --cov=src/api --cov-report=html

# Specific test file
pytest tests/integration/test_api_agents.py
```

### Adding New Endpoints

1. Create Pydantic models in `src/api/models/`
2. Create route handlers in `src/api/routes/`
3. Include router in `src/api/main.py`
4. Add tests in `tests/integration/`

### Code Structure

```
src/api/
├── __init__.py
├── main.py              # FastAPI application
├── config.py            # Configuration settings
├── dependencies.py      # Dependency injection
├── middleware/          # Custom middleware
│   ├── logging.py
│   ├── error_handler.py
│   └── metrics.py
├── models/              # Pydantic models
│   ├── agent_models.py
│   ├── trading_models.py
│   ├── market_data_models.py
│   ├── forecast_models.py
│   ├── performance_models.py
│   ├── strategy_models.py
│   └── system_models.py
└── routes/              # API route handlers
    ├── agents.py
    ├── trading.py
    ├── market_data.py
    ├── forecasts.py
    ├── performance.py
    ├── strategies.py
    └── system.py
```

## Production Deployment

### Docker

```bash
# Build image
docker build -t risetrader-api .

# Run container
docker run -d \
  --name risetrader-api \
  -p 8003:8003 \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e REDIS_URL=redis://... \
  risetrader-api
```

### Using Docker Compose

```bash
docker-compose up -d
```

### Systemd Service

Create `/etc/systemd/system/risetrader-api.service`:

```ini
[Unit]
Description=RiseTrader API Server
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=risetrader
WorkingDirectory=/opt/risetrader
Environment="PATH=/opt/risetrader/venv/bin"
ExecStart=/opt/risetrader/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable risetrader-api
sudo systemctl start risetrader-api
```

## Troubleshooting

### Common Issues

**Database Connection Failed**
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
psql postgresql://postgres:risetrader2024@localhost:5433/risetrader
```

**Redis Connection Failed**
```bash
# Check Redis is running
docker-compose ps redis

# Test connection
redis-cli -h localhost -p 6379 ping
```

**Agent Coordinator Not Starting**
```bash
# Check agent configuration
cat config/agents.yaml

# View logs
docker-compose logs -f api
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit pull request

## License

Copyright 2024 RiseTrader. All rights reserved.

## Support

For issues and questions:
- GitHub Issues: [Link to repo]
- Documentation: [Link to docs]
- Email: support@risetrader.com
