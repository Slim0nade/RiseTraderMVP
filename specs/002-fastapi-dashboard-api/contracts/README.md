# API Contracts

This directory contains the API contract specifications for the RiseTrader Dashboard API.

## Files

- **openapi-spec.yaml**: Complete OpenAPI 3.0 specification for all API endpoints
  - Market Data endpoints
  - Trading endpoints (account, positions, history)
  - Forecasts endpoints
  - Strategies endpoints
  - Real-time streaming (SSE) endpoints
  - System/health endpoints

## Using the Spec

### View Documentation
The OpenAPI spec is automatically served by FastAPI at:
- **Swagger UI**: http://localhost:8003/docs
- **ReDoc**: http://localhost:8003/redoc
- **OpenAPI JSON**: http://localhost:8003/openapi.json

### Generate Client Code
Use OpenAPI Generator to create client libraries for the dashboard:

```bash
# Install OpenAPI Generator
npm install @openapitools/openapi-generator-cli -g

# Generate TypeScript client for React dashboard
openapi-generator-cli generate \
  -i specs/002-fastapi-dashboard-api/contracts/openapi-spec.yaml \
  -g typescript-axios \
  -o dashboard/src/generated/api \
  --additional-properties=supportsES6=true
```

### Validate Spec
```bash
# Install validator
npm install -g @apidevtools/swagger-cli

# Validate OpenAPI spec
swagger-cli validate specs/002-fastapi-dashboard-api/contracts/openapi-spec.yaml
```

## Contract Testing

Contract tests verify that the API implementation matches the OpenAPI specification:
- Located at: `tests/contract/test_*_schemas.py`
- Run with: `pytest tests/contract/`
- Coverage: All endpoints and response schemas

## Changelog

### v1.0.0 (2025-11-24)
- Initial API specification
- Market Data endpoints with SSE streaming
- Trading endpoints (account, positions, history)
- Forecasts endpoints
- Strategies endpoints
- System/health endpoints
- Keyset pagination support
- SSE streaming for real-time updates

## Notes

- **Authentication**: NOT YET IMPLEMENTED - Planned for Phase 8-9
- **Real-time**: SSE preferred over WebSocket for unidirectional streaming
- **Pagination**: Keyset (cursor-based) pagination for consistent performance
- **Caching**: Redis caching with configurable TTL per data type
- **Performance**: <200ms p95 latency target, <2s for chart data
