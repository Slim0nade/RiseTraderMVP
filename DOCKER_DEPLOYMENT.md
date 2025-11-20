# RiseTrader Docker Deployment Guide

Complete guide for deploying RiseTrader using Docker in production environments (Digital Ocean, AWS, GCP, etc.).

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Production Deployment](#production-deployment)
4. [Configuration](#configuration)
5. [Monitoring](#monitoring)
6. [Backup & Recovery](#backup--recovery)
7. [Troubleshooting](#troubleshooting)
8. [Security](#security)

---

## Prerequisites

### System Requirements

**Minimum Requirements:**
- 4 CPU cores
- 8GB RAM
- 50GB SSD storage
- Ubuntu 20.04+ / Debian 11+ / CentOS 8+

**Recommended for Production:**
- 8 CPU cores
- 16GB RAM
- 200GB SSD storage
- Ubuntu 22.04 LTS

### Software Requirements

1. **Docker Engine 24.0+**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

2. **Docker Compose 2.20+**
```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

3. **Git**
```bash
sudo apt-get update
sudo apt-get install git -y
```

---

## Quick Start

### Development Environment

1. **Clone Repository**
```bash
git clone https://github.com/yourusername/RiseTraderMVP.git
cd RiseTraderMVP
```

2. **Start Development Stack**
```bash
# Start PostgreSQL and Redis only
docker-compose up -d

# Check status
docker-compose ps
```

3. **Access Services**
- PostgreSQL: `localhost:5433`
- Redis: `localhost:6379`

---

## Production Deployment

### Step 1: Server Setup

#### Digital Ocean Droplet Setup

1. **Create Droplet**
```bash
# Using doctl (Digital Ocean CLI)
doctl compute droplet create risetrader-prod \
  --size s-4vcpu-8gb \
  --image ubuntu-22-04-x64 \
  --region nyc3 \
  --ssh-keys YOUR_SSH_KEY_ID
```

2. **SSH into Server**
```bash
ssh root@your-droplet-ip
```

3. **Install Docker**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

### Step 2: Deploy Application

1. **Clone Repository**
```bash
cd /opt
git clone https://github.com/yourusername/RiseTraderMVP.git
cd RiseTraderMVP
```

2. **Configure Environment**
```bash
# Copy environment template
cp docker/.env.example .env

# Edit with your production values
nano .env
```

**Required Configuration:**
```bash
# Security - MUST CHANGE
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD
JWT_SECRET_KEY=$(openssl rand -base64 32)
API_KEY=$(openssl rand -hex 32)
GRAFANA_ADMIN_PASSWORD=YOUR_GRAFANA_PASSWORD

# MT4 Connection
MT4_HOST=75.154.254.186
ZMQ_CLIENT_SECRET_KEY=YOUR_ZMQ_SECRET
ZMQ_CLIENT_PUBLIC_KEY=YOUR_ZMQ_PUBLIC
ZMQ_SERVER_PUBLIC_KEY=YOUR_ZMQ_SERVER_PUBLIC

# Domain (if using SSL)
CORS_ORIGINS=https://yourdomain.com
VITE_API_URL=https://yourdomain.com/api
```

3. **Build and Deploy**
```bash
# Build Docker images
./scripts/deployment/build.sh

# Deploy with production config
./scripts/deployment/deploy.sh
```

4. **Verify Deployment**
```bash
# Run health checks
./scripts/deployment/health_check.sh

# Check logs
docker-compose -f docker-compose.prod.yml logs -f api
```

### Step 3: SSL Certificate Setup

#### Option 1: Let's Encrypt (Recommended)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx -y

# Obtain certificate
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Copy certificates to project
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./ssl/

# Update nginx config to use SSL
# Edit docker/nginx/conf.d/default.conf

# Restart nginx
docker-compose -f docker-compose.prod.yml restart nginx
```

#### Option 2: Self-Signed (Development Only)

```bash
# Already generated in nginx container
# Located at: /etc/nginx/ssl/nginx-selfsigned.crt
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `docker/.env.example` for complete list.

#### Critical Settings

**Database:**
```bash
POSTGRES_DB=risetrader
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secure-password>
POSTGRES_SHARED_BUFFERS=2GB  # Adjust based on RAM
```

**API:**
```bash
API_WORKERS=4  # CPU cores
LOG_LEVEL=info
ENABLE_LIVE_TRADING=false  # Set true only when ready
```

**Security:**
```bash
JWT_SECRET_KEY=<32-byte-base64>
API_KEY=<api-key>
CORS_ORIGINS=https://yourdomain.com
```

**Risk Management:**
```bash
MAX_POSITION_SIZE=10.0
MAX_DAILY_LOSS=1000.0
MAX_OPEN_POSITIONS=5
```

### Resource Limits

Resource limits are configured in `docker-compose.prod.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

Adjust based on your server specifications.

---

## Monitoring

### Access Monitoring Tools

- **Grafana**: `http://your-domain:3001`
  - Username: admin
  - Password: Set in GRAFANA_ADMIN_PASSWORD

- **Prometheus**: `http://your-domain:9090`
- **Kibana**: `http://your-domain:5601`
- **MLflow**: `http://your-domain:5000`

### Pre-Built Dashboards

Grafana dashboards are automatically provisioned:

1. **RiseTrader Overview** - System health, API metrics
2. **Trading Performance** - P&L, trades, positions
3. **Agent Monitoring** - Agent activity, processing times
4. **Database Performance** - Query times, connections
5. **Infrastructure** - CPU, memory, disk, network

### Metrics Collection

Prometheus scrapes metrics from:
- FastAPI application (`/metrics`)
- PostgreSQL exporter
- Redis exporter
- Nginx
- Node exporter (system metrics)

### Alerts

Alerts are configured in `docker/prometheus/alerts.yml`:

- API down for >1 minute
- Database connections >90%
- High error rate (>5% of requests)
- Memory usage >90%
- Disk space <10%

Configure notification channels in Grafana:
1. Settings → Notification channels
2. Add Slack, Email, PagerDuty, etc.

---

## Backup & Recovery

### Automated Backups

Backups are created daily at 2 AM UTC (configurable):

```bash
# Enable automated backups
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # Cron format
BACKUP_RETENTION_DAYS=30
```

Backups are stored in `./backups/` directory.

### Manual Backup

```bash
# Create full backup
./scripts/deployment/backup.sh

# Quick backup (database only)
./scripts/deployment/backup.sh --quick

# Backup to remote (S3)
./scripts/deployment/backup.sh --remote s3://your-bucket/backups/
```

### Restore

```bash
# List available backups
ls -lh backups/

# Restore from backup
./scripts/deployment/restore.sh --file backups/risetrader_2025-11-16.dump

# Restore with confirmation prompt
./scripts/deployment/restore.sh
```

### Disaster Recovery

1. **Database Corruption**
```bash
# Stop services
docker-compose -f docker-compose.prod.yml down

# Restore database
./scripts/deployment/restore.sh --file backups/latest.dump

# Start services
./scripts/deployment/deploy.sh
```

2. **Complete System Failure**
```bash
# On new server, clone repo
git clone https://github.com/yourusername/RiseTraderMVP.git
cd RiseTraderMVP

# Copy environment config
scp old-server:/opt/RiseTraderMVP/.env .env

# Copy backups
scp old-server:/opt/RiseTraderMVP/backups/latest.dump backups/

# Deploy
./scripts/deployment/deploy.sh

# Restore data
./scripts/deployment/restore.sh --file backups/latest.dump
```

---

## Troubleshooting

### Common Issues

#### 1. Services Won't Start

**Check logs:**
```bash
docker-compose -f docker-compose.prod.yml logs api
docker-compose -f docker-compose.prod.yml logs postgres
```

**Check container status:**
```bash
docker ps -a
docker inspect risetrader-api
```

#### 2. Database Connection Issues

**Check PostgreSQL:**
```bash
docker exec risetrader-postgres pg_isready -U postgres
docker exec risetrader-postgres psql -U postgres -c "SELECT version();"
```

**Check connectivity from API:**
```bash
docker exec risetrader-api ping postgres
```

#### 3. API Not Responding

**Check health endpoint:**
```bash
curl http://localhost:8003/health
```

**Check worker processes:**
```bash
docker exec risetrader-api ps aux
```

**Restart API:**
```bash
docker-compose -f docker-compose.prod.yml restart api
```

#### 4. High Memory Usage

**Check container stats:**
```bash
docker stats
```

**Adjust resource limits in `docker-compose.prod.yml`**

**Optimize PostgreSQL:**
```bash
# Edit docker/postgres/postgresql.conf
shared_buffers = 1GB  # Reduce if needed
work_mem = 32MB
```

#### 5. Slow Performance

**Check database queries:**
```bash
docker exec risetrader-postgres psql -U postgres -d risetrader -c "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Check Redis performance:**
```bash
docker exec risetrader-redis redis-cli INFO stats
docker exec risetrader-redis redis-cli SLOWLOG GET 10
```

### Logs

**View all logs:**
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

**View specific service:**
```bash
docker-compose -f docker-compose.prod.yml logs -f api
```

**Export logs:**
```bash
docker-compose -f docker-compose.prod.yml logs --no-color > logs/export.log
```

### Debug Mode

Enable debug logging:
```bash
# In .env file
LOG_LEVEL=debug

# Restart services
docker-compose -f docker-compose.prod.yml restart api
```

---

## Security

### Security Checklist

- [ ] Change all default passwords
- [ ] Generate secure JWT_SECRET_KEY
- [ ] Configure CORS origins properly
- [ ] Enable SSL/TLS certificates
- [ ] Use encrypted ZMQ connection to MT4
- [ ] Set up firewall rules
- [ ] Enable fail2ban for SSH
- [ ] Regular security updates
- [ ] Backup encryption
- [ ] Monitor access logs

### Firewall Configuration

**Ubuntu UFW:**
```bash
# Enable firewall
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow only from specific IP (optional)
sudo ufw allow from YOUR_IP to any port 22

# Check status
sudo ufw status
```

**Restrict Port Access:**
```bash
# Only allow monitoring ports from internal network
sudo ufw allow from 10.0.0.0/8 to any port 9090  # Prometheus
sudo ufw allow from 10.0.0.0/8 to any port 3001  # Grafana
```

### SSL/TLS

**Force HTTPS:**

Edit `docker/nginx/conf.d/default.conf`:
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # ... rest of config
}
```

### Secrets Management

**Option 1: Docker Secrets (Swarm)**
```bash
echo "my_secure_password" | docker secret create postgres_password -
```

**Option 2: HashiCorp Vault**
```bash
# Store secrets in Vault
vault kv put secret/risetrader/db password="..."

# Retrieve in startup script
export POSTGRES_PASSWORD=$(vault kv get -field=password secret/risetrader/db)
```

**Option 3: AWS Secrets Manager**
```bash
# Store secret
aws secretsmanager create-secret --name risetrader/db-password --secret-string "..."

# Retrieve in startup
export POSTGRES_PASSWORD=$(aws secretsmanager get-secret-value --secret-id risetrader/db-password --query SecretString --output text)
```

---

## Maintenance

### Updates

**Update to latest version:**
```bash
./scripts/deployment/update.sh
```

**Update to specific version:**
```bash
./scripts/deployment/update.sh --version 1.1.0
```

**Update without backup (not recommended):**
```bash
./scripts/deployment/update.sh --no-backup
```

### Rollback

**Rollback to previous version:**
```bash
./scripts/deployment/rollback.sh --version 1.0.0
```

**Rollback with database restore:**
```bash
./scripts/deployment/rollback.sh --version 1.0.0 --backup backups/risetrader_2025-11-16.dump
```

### Health Checks

**Run health check:**
```bash
./scripts/deployment/health_check.sh
```

**Automated monitoring:**
```bash
# Add to crontab
*/5 * * * * /opt/RiseTraderMVP/scripts/deployment/health_check.sh >> /var/log/risetrader-health.log 2>&1
```

### Log Rotation

**Configure log rotation:**

Create `/etc/logrotate.d/risetrader`:
```
/opt/RiseTraderMVP/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 root root
    sharedscripts
    postrotate
        docker-compose -f /opt/RiseTraderMVP/docker-compose.prod.yml kill -s USR1 api
    endscript
}
```

---

## Performance Tuning

### Database Optimization

**For 8GB RAM server:**
```bash
POSTGRES_SHARED_BUFFERS=2GB
POSTGRES_EFFECTIVE_CACHE_SIZE=6GB
POSTGRES_WORK_MEM=64MB
POSTGRES_MAINTENANCE_WORK_MEM=512MB
```

**For 16GB RAM server:**
```bash
POSTGRES_SHARED_BUFFERS=4GB
POSTGRES_EFFECTIVE_CACHE_SIZE=12GB
POSTGRES_WORK_MEM=128MB
POSTGRES_MAINTENANCE_WORK_MEM=1GB
```

### API Performance

**Adjust workers:**
```bash
# Formula: (2 x CPU cores) + 1
API_WORKERS=9  # For 4 CPU cores
```

**Connection pooling:**
```python
# In src/api/config.py
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

### Redis Optimization

```bash
# Adjust maxmemory based on usage
docker exec risetrader-redis redis-cli CONFIG SET maxmemory 1gb
docker exec risetrader-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

---

## Support

- **Documentation**: `/docs/`
- **Issues**: GitHub Issues
- **Email**: support@risetrader.com
- **Discord**: [Join Community](https://discord.gg/risetrader)

---

## License

Copyright © 2025 RiseTrader Team. All rights reserved.
