# RiseTrader Docker Configuration

This directory contains all Docker-related configuration files for RiseTrader deployment.

---

## Directory Structure

```
docker/
├── api/                        # FastAPI backend container
│   └── Dockerfile              # Multi-stage Python build
├── postgres/                   # PostgreSQL 17 database
│   ├── Dockerfile              # PostgreSQL with extensions
│   ├── init.sql                # Database initialization
│   ├── extensions.sql          # Extensions (TimescaleDB, etc.)
│   └── postgresql.conf         # Performance tuning
├── redis/                      # Redis 7 cache
│   ├── Dockerfile              # Redis with custom config
│   └── redis.conf              # Redis configuration
├── ml-service/                 # ML inference service
│   └── Dockerfile              # PyTorch + XGBoost
├── dashboard/                  # React frontend
│   └── Dockerfile              # Nginx + React build
├── nginx/                      # Reverse proxy
│   ├── Dockerfile              # Nginx + SSL
│   ├── nginx.conf              # Main configuration
│   └── conf.d/                 # Site configurations
├── prometheus/                 # Metrics collection
│   ├── prometheus.yml          # Scrape configuration
│   └── alerts.yml              # Alert rules
├── grafana/                    # Visualization
│   ├── dashboards/             # Pre-built dashboards
│   └── datasources/            # Data sources
├── logstash/                   # Log processing
│   └── pipeline/               # Logstash pipelines
└── .env.example                # Environment template
```

---

## Container Images

### API Service
- **Base Image:** python:3.11-slim
- **Build Type:** Multi-stage
- **Size:** ~800MB (optimized)
- **User:** Non-root (risetrader)
- **Exposed Ports:** 8000

**Features:**
- TA-Lib compiled from source
- All Python dependencies pre-installed
- Health check endpoint
- Production-ready uvicorn

### PostgreSQL
- **Base Image:** postgres:17-alpine
- **Extensions:** TimescaleDB, pg_stat_statements, pgcrypto
- **User:** postgres
- **Exposed Ports:** 5432

**Features:**
- Time-series optimizations
- Performance tuning for trading data
- Automatic initialization scripts
- Health checks

### Redis
- **Base Image:** redis:7-alpine
- **Persistence:** AOF (appendonly)
- **User:** redis
- **Exposed Ports:** 6379

**Features:**
- LRU eviction policy
- 512MB memory limit
- Optimized for agent state

### ML Service
- **Base Image:** python:3.11
- **ML Libraries:** PyTorch, XGBoost, scikit-learn
- **User:** Non-root
- **Exposed Ports:** None (internal)

**Features:**
- GPU support (optional)
- Model caching
- MLflow integration

### Dashboard
- **Base Image:** node:18-alpine (build), nginx:alpine (runtime)
- **Build Type:** Multi-stage
- **Size:** ~50MB
- **User:** nginx
- **Exposed Ports:** 80

**Features:**
- React production build
- Nginx serving static files
- Gzip compression

### Nginx
- **Base Image:** nginx:1.25-alpine
- **SSL:** Self-signed (dev) + Let's Encrypt support
- **User:** nginx
- **Exposed Ports:** 80, 443

**Features:**
- Reverse proxy for all services
- SSL/TLS termination
- Rate limiting
- Gzip compression

---

## Configuration Files

### PostgreSQL Configuration

**`postgresql.conf`** - Performance tuning:
```ini
shared_buffers = 2GB              # 25% of RAM
effective_cache_size = 6GB        # 75% of RAM
work_mem = 64MB                   # Per operation
maintenance_work_mem = 512MB      # For VACUUM, etc.
max_connections = 200             # Connection limit
```

Adjust based on server specs.

### Redis Configuration

**`redis.conf`** - Cache optimizations:
```ini
maxmemory 512mb                   # Memory limit
maxmemory-policy allkeys-lru      # Eviction policy
appendonly yes                    # Persistence
appendfsync everysec              # Fsync frequency
```

### Nginx Configuration

**`nginx.conf`** - Main configuration:
- Worker processes: auto
- Worker connections: 1024
- Gzip compression: enabled
- Client max body size: 10MB

**`conf.d/default.conf`** - Site configuration:
- Reverse proxy for API
- Static file serving for dashboard
- WebSocket support for MCP
- SSL/TLS configuration

### Prometheus Configuration

**`prometheus.yml`** - Scrape targets:
```yaml
scrape_configs:
  - job_name: 'risetrader-api'
    static_configs:
      - targets: ['api:8000']
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

**`alerts.yml`** - Alert rules:
- API down for >1 minute
- High error rate (>5%)
- Database connections >90%
- Memory usage >90%
- Disk space <10%

### Grafana Dashboards

Pre-built dashboards in `grafana/dashboards/`:
1. **risetrader-overview.json** - System health, API metrics
2. **trading-performance.json** - P&L, trades, positions
3. **agent-monitoring.json** - Agent activity
4. **database-performance.json** - Query times, connections
5. **infrastructure.json** - CPU, memory, disk, network

---

## Environment Variables

### Required Variables

**Database:**
```bash
POSTGRES_DB=risetrader
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secure-password>
```

**Security:**
```bash
JWT_SECRET_KEY=<32-byte-base64>
API_KEY=<api-key>
```

**MT4 Connection:**
```bash
MT4_HOST=75.154.254.174
MT4_COMMAND_PORT=5555
MT4_STREAM_PORT=5556
ZMQ_CLIENT_SECRET_KEY=<zmq-secret>
ZMQ_CLIENT_PUBLIC_KEY=<zmq-public>
ZMQ_SERVER_PUBLIC_KEY=<zmq-server-public>
```

**Risk Management:**
```bash
MAX_POSITION_SIZE=10.0
MAX_DAILY_LOSS=1000.0
MAX_OPEN_POSITIONS=5
```

**Feature Flags:**
```bash
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false
ENABLE_FORECASTING=true
```

See `.env.example` for complete list.

---

## Building Images

### Build All Images
```bash
cd /opt/RiseTraderMVP
./scripts/deployment/build.sh
```

### Build Specific Image
```bash
# API
docker build -f docker/api/Dockerfile -t risetrader/api:latest .

# PostgreSQL
docker build -f docker/postgres/Dockerfile -t risetrader/postgres:latest .

# Redis
docker build -f docker/redis/Dockerfile -t risetrader/redis:latest .
```

### Multi-Platform Build (Optional)
```bash
# For ARM64 and AMD64
docker buildx build --platform linux/amd64,linux/arm64 \
  -f docker/api/Dockerfile \
  -t risetrader/api:latest \
  --push .
```

---

## Docker Compose Usage

### Development
```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production
```bash
# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f api

# Stop services
docker-compose -f docker-compose.prod.yml down
```

### Useful Commands
```bash
# Restart specific service
docker-compose restart api

# Scale API workers
docker-compose up -d --scale api=4

# View resource usage
docker stats

# View container details
docker inspect risetrader-api

# Execute command in container
docker exec -it risetrader-api bash

# View container logs
docker logs -f risetrader-api

# Remove all volumes (CAUTION: deletes data)
docker-compose down -v
```

---

## Networking

### Networks

**Frontend Network:**
- Public-facing services
- Nginx, Dashboard, API (external endpoints)

**Backend Network:**
- Internal services only
- PostgreSQL, Redis, ML Service

**Monitoring Network:**
- Isolated monitoring stack
- Prometheus, Grafana, ELK

### Network Isolation

- Backend network has `internal: true` (no external access)
- Services communicate via Docker DNS
- Only Nginx is publicly accessible

---

## Volume Management

### Persistent Volumes

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect risetrader_postgres_data

# Backup volume
docker run --rm -v risetrader_postgres_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_data.tar.gz /data

# Restore volume
docker run --rm -v risetrader_postgres_data:/data -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/postgres_data.tar.gz -C /
```

### Volume Locations

- **PostgreSQL Data:** `risetrader_postgres_data`
- **Redis Data:** `risetrader_redis_data`
- **Prometheus Data:** `risetrader_prometheus_data`
- **Grafana Data:** `risetrader_grafana_data`
- **Elasticsearch Data:** `risetrader_elasticsearch_data`
- **MLflow Data:** `risetrader_mlflow_data`
- **Model Cache:** `risetrader_model_cache`

---

## Health Checks

### Container Health Checks

All production containers have health checks:

**API:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

**PostgreSQL:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD pg_isready -U postgres -d risetrader || exit 1
```

**Redis:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD redis-cli ping || exit 1
```

### Check Health Status
```bash
# All containers
docker ps

# Specific container
docker inspect --format='{{.State.Health.Status}}' risetrader-api

# Health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' risetrader-api
```

---

## Resource Limits

### Default Limits (Production)

**API:**
- CPU: 2 cores (limit), 1 core (reservation)
- Memory: 2GB (limit), 1GB (reservation)

**PostgreSQL:**
- CPU: 2 cores (limit), 1 core (reservation)
- Memory: 2GB (limit), 1GB (reservation)

**Redis:**
- CPU: 1 core (limit), 0.5 cores (reservation)
- Memory: 512MB (limit), 256MB (reservation)

**ML Service:**
- CPU: 4 cores (limit), 2 cores (reservation)
- Memory: 4GB (limit), 2GB (reservation)

### Adjust Limits

Edit `docker-compose.prod.yml`:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '4'      # Increase CPU
          memory: 4G     # Increase memory
        reservations:
          cpus: '2'
          memory: 2G
```

---

## Security Best Practices

### Container Security

- [x] Non-root users in all containers
- [x] Read-only root filesystems (where possible)
- [x] No secrets in images
- [x] Minimal base images (Alpine)
- [x] Multi-stage builds
- [x] Health checks enabled
- [x] Resource limits set

### Network Security

- [x] Backend network internal-only
- [x] Network isolation between layers
- [x] Only necessary ports exposed
- [x] TLS/SSL for external traffic

### Image Security

```bash
# Scan images for vulnerabilities
docker scan risetrader/api:latest

# Use trusted base images only
FROM python:3.11-slim  # Official Python image
FROM postgres:17-alpine  # Official PostgreSQL
FROM redis:7-alpine  # Official Redis
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs risetrader-api

# Check status
docker ps -a

# Check events
docker events --since 30m

# Restart container
docker restart risetrader-api
```

### Out of Disk Space

```bash
# Check disk usage
df -h

# Clean up Docker
docker system prune -a
docker volume prune

# Remove unused images
docker image prune -a
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Reduce resource limits
# Edit docker-compose.prod.yml

# Restart services
docker-compose -f docker-compose.prod.yml restart
```

### Network Issues

```bash
# Check networks
docker network ls

# Inspect network
docker network inspect risetrader_backend

# Test connectivity
docker exec risetrader-api ping postgres
docker exec risetrader-api nc -zv postgres 5432
```

---

## Maintenance

### Update Images

```bash
# Pull latest images
docker-compose -f docker-compose.prod.yml pull

# Restart with new images
docker-compose -f docker-compose.prod.yml up -d
```

### Cleanup

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused volumes (CAUTION)
docker volume prune

# Remove unused networks
docker network prune

# Complete cleanup
docker system prune -a --volumes
```

### Logs

```bash
# View logs
docker-compose logs -f

# Logs for specific service
docker-compose logs -f api

# Last 100 lines
docker-compose logs --tail=100

# Since timestamp
docker-compose logs --since 2025-11-17T10:00:00
```

---

## Development vs Production

| Feature | Development | Production |
|---------|-------------|------------|
| Compose File | docker-compose.yml | docker-compose.prod.yml |
| Services | 2 (postgres, redis) | 12 (full stack) |
| Volume Mounts | Yes (hot reload) | No (copied at build) |
| Resource Limits | No | Yes |
| Health Checks | Basic | Comprehensive |
| Logging | Console | JSON files |
| Restart Policy | No | unless-stopped |
| Network Isolation | No | Yes (3 networks) |
| Monitoring | No | Yes (Prometheus, Grafana) |
| SSL/TLS | No | Yes |

---

## Contributing

When adding new services:

1. Create Dockerfile in appropriate directory
2. Add service to docker-compose.prod.yml
3. Configure health checks
4. Set resource limits
5. Add to monitoring (Prometheus)
6. Update documentation
7. Test in isolation
8. Test with full stack

---

## Support

- **Main Documentation:** `../DOCKER_DEPLOYMENT.md`
- **Quick Start:** `../QUICK_DEPLOY.md`
- **Checklist:** `../DEPLOYMENT_CHECKLIST.md`
- **Summary:** `../DOCKER_SUMMARY.md`

---

**Last Updated:** 2025-11-17
**Version:** 1.0.0
