"""
OpenAPI configuration and metadata for FastAPI documentation (T107).

Provides comprehensive API documentation with examples and schemas.
"""
from typing import Dict

# OpenAPI metadata
OPENAPI_TITLE = "RiseTrader MT4 Integration API"
OPENAPI_VERSION = "1.0.0"
OPENAPI_DESCRIPTION = """
# RiseTrader MT4 Integration API

Comprehensive REST API for managing MetaTrader 4 (MT4) integration, including:

## Features

- **EA Management**: Register, monitor, and control Expert Advisors
- **Account Queries**: Real-time account information and balance tracking
- **Position Monitoring**: Track open positions and P&L across all EAs
- **Order Management**: Query order history with advanced filtering
- **Portfolio Risk**: Aggregated portfolio-level risk metrics
- **Health Monitoring**: Service health checks and system status

## Authentication

🔒 **Note**: Authentication is not yet implemented. Before production deployment:
- JWT-based authentication required
- API key validation needed
- Rate limiting must be enabled

## User Stories

This API implements the following user stories:
- **US4**: Query Account Information
- **US5**: Manage Multiple Expert Advisors

## Rate Limits

⚠️ **Production Considerations**:
- Implement rate limiting (e.g., 100 requests/minute per client)
- Add request throttling for expensive operations
- Consider caching for frequently accessed endpoints

## Error Handling

All endpoints return standard error responses with:
- `error`: Error type/code
- `message`: Human-readable error description
- `details`: Additional context (optional)
- `timestamp`: Error occurrence time

## Support

For issues or questions:
- GitHub: [RiseTrader Repository](https://github.com/yourusername/risetrader)
- Documentation: `/docs` (Swagger UI) or `/redoc` (ReDoc)
"""

OPENAPI_TAGS_METADATA = [
    {
        "name": "MT4 Integration",
        "description": """
Operations for MT4 integration management.

All endpoints in this group provide functionality for:
- EA connection management
- Account information queries
- Position and order tracking
- Portfolio risk monitoring
- Service health checks
        """,
    },
]

# Example responses for documentation
EXAMPLE_RESPONSES: Dict[str, Dict] = {
    "account_info": {
        "balance": "10000.50",
        "equity": "10250.75",
        "margin": "500.00",
        "free_margin": "9750.75",
        "margin_level": "2050.15",
        "profit": "250.25",
        "account_number": 123456789,
        "leverage": 100,
        "currency": "USD",
        "server": "BrokerServer-Live",
        "company": "Broker Inc."
    },
    "position_info": {
        "ticket": 12345678,
        "symbol": "CrudeOIL",
        "type": "BUY",
        "volume": "0.10",
        "open_price": "75.50",
        "current_price": "75.75",
        "stop_loss": "75.00",
        "take_profit": "76.50",
        "profit": "25.00",
        "open_time": "2025-01-15T10:30:00Z",
        "magic_number": 100001
    },
    "ea_connection": {
        "ea_id": "momentum_strategy_1",
        "magic_number": 100001,
        "rep_port": 5555,
        "pub_port": 5556,
        "host": "localhost",
        "symbol": "CrudeOIL",
        "status": "ACTIVE",
        "last_heartbeat": "2025-01-15T12:45:30Z",
        "encryption_enabled": True
    },
    "portfolio_risk": {
        "total_equity": "10000.00",
        "total_margin_used": "500.00",
        "margin_level": "2000.00",
        "total_open_positions": 3,
        "exposure_by_symbol": {
            "CrudeOIL": "7550.00",
            "EURUSD": "2000.00"
        },
        "exposure_by_ea": {
            "100001": "5000.00",
            "100002": "4550.00"
        },
        "last_updated": "2025-01-15T12:45:00Z",
        "is_margin_critical": False,
        "available_margin_pct": "95.00"
    },
    "health_check": {
        "status": "healthy",
        "timestamp": "2025-01-15T12:45:00Z",
        "uptime_seconds": 86400.5,
        "active_connections": 3,
        "total_orders_today": 45,
        "total_positions_open": 5,
        "errors_last_hour": 0,
        "avg_order_latency_ms": 125.5,
        "database_healthy": True,
        "redis_healthy": True,
        "mt4_connections_healthy": 3,
        "issues": []
    },
    "error": {
        "error": "NOT_FOUND",
        "message": "EA with magic number 999999 not found",
        "details": {"magic_number": 999999},
        "timestamp": "2025-01-15T12:45:00Z"
    }
}


def get_openapi_config() -> Dict:
    """
    Get OpenAPI configuration for FastAPI app.
    
    Usage:
        app = FastAPI(**get_openapi_config())
    """
    return {
        "title": OPENAPI_TITLE,
        "version": OPENAPI_VERSION,
        "description": OPENAPI_DESCRIPTION,
        "openapi_tags": OPENAPI_TAGS_METADATA,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
