# RiseTrader Production Deployment Checklist

Complete checklist for deploying RiseTrader to production. Follow this step-by-step guide to ensure a successful deployment.

---

## Pre-Deployment

### Infrastructure Setup

- [ ] **Server provisioned** (8GB RAM minimum, 16GB recommended)
- [ ] **Operating system updated**
  ```bash
  sudo apt-get update && sudo apt-get upgrade -y
  ```
- [ ] **Docker installed** (v24.0+)
  ```bash
  docker --version
  ```
- [ ] **Docker Compose installed** (v2.20+)
  ```bash
  docker-compose --version
  ```
- [ ] **Git installed**
  ```bash
  git --version
  ```
- [ ] **Domain name configured** (if using)
  - DNS A record pointing to server IP
  - DNS propagation verified
- [ ] **Firewall configured**
  - SSH (22)
  - HTTP (80)
  - HTTPS (443)
  - Closed all other ports

### Repository Setup

- [ ] **Code repository cloned**
  ```bash
  cd /opt
  git clone https://github.com/yourusername/RiseTraderMVP.git
  cd RiseTraderMVP
  ```
- [ ] **Latest version checked out**
  ```bash
  git checkout main
  git pull origin main
  ```
- [ ] **Directory permissions set**
  ```bash
  sudo chown -R $USER:$USER /opt/RiseTraderMVP
  ```

---

## Configuration

### Environment Variables

- [ ] **Environment file created**
  ```bash
  cp docker/.env.example .env
  ```

- [ ] **Database credentials configured**
  ```bash
  POSTGRES_PASSWORD=<generate-secure-password>
  ```

- [ ] **JWT secret generated**
  ```bash
  JWT_SECRET_KEY=$(openssl rand -base64 32)
  ```

- [ ] **API key generated**
  ```bash
  API_KEY=$(openssl rand -hex 32)
  ```

- [ ] **Grafana password set**
  ```bash
  GRAFANA_ADMIN_PASSWORD=<secure-password>
  ```

- [ ] **MT4 connection configured**
  ```bash
  MT4_HOST=75.154.254.186
  MT4_COMMAND_PORT=5555
  MT4_STREAM_PORT=5556
  ```

- [ ] **ZMQ encryption keys generated**
  ```python
  # Run this Python script to generate keys
  import zmq.auth
  zmq.auth.create_certificates('.', 'client')
  zmq.auth.create_certificates('.', 'server')
  ```
  ```bash
  ZMQ_CLIENT_SECRET_KEY=<client-secret>
  ZMQ_CLIENT_PUBLIC_KEY=<client-public>
  ZMQ_SERVER_PUBLIC_KEY=<server-public>
  ```

- [ ] **CORS origins configured**
  ```bash
  CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
  ```

- [ ] **Frontend API URL configured**
  ```bash
  VITE_API_URL=https://yourdomain.com/api
  ```

- [ ] **Risk limits configured**
  ```bash
  MAX_POSITION_SIZE=10.0
  MAX_DAILY_LOSS=1000.0
  MAX_OPEN_POSITIONS=5
  ```

- [ ] **Feature flags set**
  ```bash
  ENABLE_PAPER_TRADING=true
  ENABLE_LIVE_TRADING=false  # Keep false until tested
  ENABLE_FORECASTING=true
  ```

### Security Configuration

- [ ] **All default passwords changed**
- [ ] **Secrets never committed to Git**
  ```bash
  # Verify .env is in .gitignore
  grep "^\.env$" .gitignore
  ```
- [ ] **SSL certificates obtained** (if using HTTPS)
  ```bash
  sudo certbot certonly --standalone -d yourdomain.com
  ```
- [ ] **SSL certificates copied to project**
  ```bash
  mkdir -p ssl
  sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/
  sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/
  ```

### Resource Configuration

- [ ] **Database resources tuned** (in .env)
  ```bash
  # For 8GB RAM server
  POSTGRES_SHARED_BUFFERS=2GB
  POSTGRES_EFFECTIVE_CACHE_SIZE=6GB
  POSTGRES_WORK_MEM=64MB
  ```

- [ ] **API workers configured**
  ```bash
  # Formula: (2 x CPU cores) + 1
  API_WORKERS=4  # For 2 CPU cores
  ```

- [ ] **Redis memory limit set**
  ```bash
  # In docker/redis/redis.conf
  maxmemory 512mb
  ```

---

## Build & Deployment

### Docker Images

- [ ] **Docker images built**
  ```bash
  ./scripts/deployment/build.sh
  ```

- [ ] **Build successful**
  - No errors in build output
  - All images created

- [ ] **Image versions tagged**
  ```bash
  VERSION=1.0.0 ./scripts/deployment/build.sh
  ```

### Initial Deployment

- [ ] **Deploy application**
  ```bash
  ./scripts/deployment/deploy.sh
  ```

- [ ] **All containers started**
  ```bash
  docker-compose -f docker-compose.prod.yml ps
  ```

- [ ] **Health checks passing**
  ```bash
  ./scripts/deployment/health_check.sh
  ```

### Database Setup

- [ ] **Database initialized**
  ```bash
  docker exec risetrader-postgres psql -U postgres -l
  ```

- [ ] **Extensions installed**
  ```bash
  docker exec risetrader-postgres psql -U postgres -d risetrader -c "\dx"
  ```

- [ ] **Migrations run**
  ```bash
  docker-compose -f docker-compose.prod.yml run --rm api alembic upgrade head
  ```

- [ ] **Sample data loaded** (optional, for testing)
  ```bash
  # If you have seed data
  docker exec -i risetrader-postgres psql -U postgres -d risetrader < data/seed.sql
  ```

---

## Verification

### Service Health

- [ ] **PostgreSQL responsive**
  ```bash
  docker exec risetrader-postgres pg_isready -U postgres
  ```

- [ ] **Redis responsive**
  ```bash
  docker exec risetrader-redis redis-cli ping
  ```

- [ ] **API responding**
  ```bash
  curl http://localhost:8003/health
  ```

- [ ] **API docs accessible**
  ```bash
  curl http://localhost:8003/docs
  ```

### Endpoint Testing

- [ ] **Health endpoint returns 200**
  ```bash
  curl -I http://localhost:8003/health
  ```

- [ ] **Metrics endpoint accessible**
  ```bash
  curl http://localhost:8003/metrics
  ```

- [ ] **Agent status endpoint working**
  ```bash
  curl http://localhost:8003/api/v1/agents/status
  ```

- [ ] **Market data endpoint working**
  ```bash
  curl http://localhost:8003/api/v1/market-data/latest
  ```

### Authentication

- [ ] **JWT authentication working**
  ```bash
  # Test login endpoint
  curl -X POST http://localhost:8003/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"test"}'
  ```

- [ ] **API key authentication working**
  ```bash
  curl -H "X-API-Key: $API_KEY" http://localhost:8003/api/v1/agents/status
  ```

### MT4 Connection

- [ ] **MT4 connection established**
  ```bash
  docker-compose -f docker-compose.prod.yml logs api | grep "MT4"
  ```

- [ ] **ZMQ encryption active**
  ```bash
  docker-compose -f docker-compose.prod.yml logs api | grep "ZMQ"
  ```

- [ ] **Test order execution** (paper trading)
  ```bash
  curl -X POST http://localhost:8003/api/v1/trading/orders \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{
      "symbol": "CrudeOIL",
      "order_type": "market",
      "side": "buy",
      "quantity": 0.1,
      "paper_trading": true
    }'
  ```

---

## Monitoring Setup

### Prometheus

- [ ] **Prometheus accessible**
  ```bash
  curl http://localhost:9090/-/healthy
  ```

- [ ] **Targets being scraped**
  - Visit: http://localhost:9090/targets
  - Verify all targets are "UP"

- [ ] **Metrics flowing**
  ```bash
  curl 'http://localhost:9090/api/v1/query?query=up'
  ```

### Grafana

- [ ] **Grafana accessible**
  ```bash
  curl http://localhost:3001/api/health
  ```

- [ ] **Login successful**
  - URL: http://localhost:3001
  - Username: admin
  - Password: From GRAFANA_ADMIN_PASSWORD

- [ ] **Datasources configured**
  - Navigate to: Configuration → Data Sources
  - Verify Prometheus is connected

- [ ] **Dashboards loaded**
  - Navigate to: Dashboards
  - Verify all pre-built dashboards present

### ELK Stack

- [ ] **Elasticsearch healthy**
  ```bash
  curl http://localhost:9200/_cluster/health
  ```

- [ ] **Kibana accessible**
  ```bash
  curl http://localhost:5601/api/status
  ```

- [ ] **Logstash receiving logs**
  ```bash
  docker-compose -f docker-compose.prod.yml logs logstash | tail -20
  ```

- [ ] **Logs visible in Kibana**
  - URL: http://localhost:5601
  - Create index pattern: `risetrader-*`
  - Verify logs appearing

### MLflow

- [ ] **MLflow accessible**
  ```bash
  curl http://localhost:5000/health
  ```

- [ ] **MLflow UI loads**
  - URL: http://localhost:5000
  - Verify experiments page loads

---

## Backup Configuration

### Automated Backups

- [ ] **Backup script executable**
  ```bash
  chmod +x scripts/deployment/backup.sh
  ```

- [ ] **Backup directory exists**
  ```bash
  mkdir -p backups
  ```

- [ ] **Test manual backup**
  ```bash
  ./scripts/deployment/backup.sh --quick
  ```

- [ ] **Verify backup created**
  ```bash
  ls -lh backups/
  ```

- [ ] **Configure automated backups**
  ```bash
  # Add to crontab
  crontab -e
  # Add line:
  0 2 * * * /opt/RiseTraderMVP/scripts/deployment/backup.sh
  ```

### Backup Restoration

- [ ] **Test backup restoration**
  ```bash
  ./scripts/deployment/restore.sh --file backups/latest.dump --no-confirm
  ```

- [ ] **Verify data restored**
  ```bash
  docker exec risetrader-postgres psql -U postgres -d risetrader -c "SELECT COUNT(*) FROM market_data;"
  ```

---

## Security Hardening

### Firewall

- [ ] **UFW enabled**
  ```bash
  sudo ufw enable
  ```

- [ ] **SSH allowed**
  ```bash
  sudo ufw allow 22/tcp
  ```

- [ ] **HTTP/HTTPS allowed**
  ```bash
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  ```

- [ ] **Monitoring ports restricted**
  ```bash
  # Only allow from internal network
  sudo ufw deny 9090/tcp  # Prometheus
  sudo ufw deny 3001/tcp  # Grafana
  sudo ufw deny 5601/tcp  # Kibana
  ```

- [ ] **Firewall status verified**
  ```bash
  sudo ufw status verbose
  ```

### SSH Hardening

- [ ] **SSH key-only authentication**
  ```bash
  # Edit /etc/ssh/sshd_config
  PasswordAuthentication no
  PubkeyAuthentication yes
  ```

- [ ] **Fail2ban installed**
  ```bash
  sudo apt-get install fail2ban -y
  sudo systemctl enable fail2ban
  sudo systemctl start fail2ban
  ```

### SSL/TLS

- [ ] **HTTPS enforced** (if using SSL)
  - Nginx redirects HTTP to HTTPS
  - HSTS header configured

- [ ] **SSL certificate auto-renewal**
  ```bash
  # Certbot auto-renewal
  sudo certbot renew --dry-run
  ```

### Container Security

- [ ] **Containers run as non-root**
  ```bash
  docker exec risetrader-api whoami
  # Should output: risetrader
  ```

- [ ] **Read-only root filesystems** (where applicable)
  - Check docker-compose.prod.yml

- [ ] **No sensitive data in images**
  ```bash
  docker history risetrader/api:latest | grep -i password
  # Should return nothing
  ```

---

## Performance Testing

### Load Testing

- [ ] **API load test**
  ```bash
  # Install hey (HTTP load generator)
  go install github.com/rakyll/hey@latest

  # Test API
  hey -n 1000 -c 10 http://localhost:8003/health
  ```

- [ ] **Database query performance**
  ```bash
  docker exec risetrader-postgres psql -U postgres -d risetrader -c "
    SELECT query, calls, mean_exec_time, max_exec_time
    FROM pg_stat_statements
    ORDER BY mean_exec_time DESC
    LIMIT 10;
  "
  ```

- [ ] **Redis performance**
  ```bash
  docker exec risetrader-redis redis-cli --latency
  ```

### Resource Monitoring

- [ ] **Container resource usage normal**
  ```bash
  docker stats
  ```

- [ ] **No memory leaks detected**
  - Monitor over 24 hours
  - Check memory usage trend in Grafana

- [ ] **CPU usage acceptable**
  - < 70% average
  - No constant 100% spikes

---

## Documentation

### Team Documentation

- [ ] **Deployment runbook created**
- [ ] **Troubleshooting guide updated**
- [ ] **Architecture diagram current**
- [ ] **API documentation published**
- [ ] **Monitoring dashboards documented**

### Operations Manual

- [ ] **Backup/restore procedures documented**
- [ ] **Rollback procedures documented**
- [ ] **Emergency contacts listed**
- [ ] **Escalation path defined**

---

## Go-Live

### Final Checks

- [ ] **All tests passing**
  ```bash
  docker-compose -f docker-compose.prod.yml run --rm api pytest
  ```

- [ ] **No errors in logs**
  ```bash
  docker-compose -f docker-compose.prod.yml logs --tail=100 | grep -i error
  ```

- [ ] **Monitoring alerts configured**
  - Slack/Email notifications set up
  - On-call rotation defined

- [ ] **Backup verified within last 24 hours**

- [ ] **Rollback plan prepared**

### Communication

- [ ] **Team notified of deployment**
- [ ] **Maintenance window communicated** (if applicable)
- [ ] **Status page updated** (if applicable)

### Post-Deployment

- [ ] **Monitor for 1 hour**
  - Watch Grafana dashboards
  - Check error rates
  - Verify trading activity (paper mode)

- [ ] **Verify automated backups running**
  ```bash
  # Check next day
  ls -lh backups/
  ```

- [ ] **Document any issues encountered**

- [ ] **Team retrospective scheduled**

---

## Live Trading Activation (CRITICAL)

**DO NOT enable live trading until ALL of the following are verified:**

- [ ] **Extensive paper trading completed** (minimum 30 days)
- [ ] **All strategies profitable in paper trading**
- [ ] **Risk limits tested and working**
- [ ] **Emergency stop mechanism tested**
- [ ] **Manual override procedures documented**
- [ ] **Position limits configured correctly**
- [ ] **Loss limits enforced**
- [ ] **24/7 monitoring in place**
- [ ] **Trading approved by stakeholders**
- [ ] **Legal/compliance review completed**

**To enable live trading:**
```bash
# Edit .env
ENABLE_LIVE_TRADING=true

# Restart API
docker-compose -f docker-compose.prod.yml restart api

# Monitor CLOSELY
docker-compose -f docker-compose.prod.yml logs -f api
```

---

## Emergency Procedures

### Emergency Stop

```bash
# Immediately stop all trading
curl -X POST http://localhost:8003/api/v1/trading/emergency-stop \
  -H "X-API-Key: $API_KEY"

# Or stop entire system
docker-compose -f docker-compose.prod.yml stop api
```

### Emergency Contacts

- **Primary On-Call**: [Name] [Phone] [Email]
- **Secondary On-Call**: [Name] [Phone] [Email]
- **Management**: [Name] [Phone] [Email]
- **Broker Support**: [Phone] [Email]

### Rollback Command

```bash
./scripts/deployment/rollback.sh --version <previous-version> --backup backups/<latest-backup>
```

---

## Sign-Off

- [ ] **Deployment Engineer**: _________________ Date: _______
- [ ] **Senior Developer**: _________________ Date: _______
- [ ] **DevOps Lead**: _________________ Date: _______
- [ ] **Project Manager**: _________________ Date: _______

---

**Deployment completed successfully!** 🚀

Monitor closely for the first 24-48 hours and document any issues encountered.
