# RiseTrader Quick Deployment Guide

Fast-track production deployment in under 30 minutes.

---

## Prerequisites

- Ubuntu 20.04+ server with 8GB RAM minimum
- Docker 24.0+ installed
- Domain name (optional, for SSL)

---

## Installation (5 minutes)

### 1. Install Docker
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Clone Repository
```bash
cd /opt
git clone https://github.com/yourusername/RiseTraderMVP.git
cd RiseTraderMVP
```

---

## Configuration (10 minutes)

### 3. Create Environment File
```bash
cp docker/.env.example .env
```

### 4. Generate Secrets
```bash
# Generate secure passwords and keys
cat > .env << EOF
# Database
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# Security
JWT_SECRET_KEY=$(openssl rand -base64 32)
API_KEY=$(openssl rand -hex 32)
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)

# MT4 Connection
MT4_HOST=75.154.254.186
MT4_COMMAND_PORT=5555
MT4_STREAM_PORT=5556

# Feature Flags
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false
ENABLE_FORECASTING=true

# Risk Limits
MAX_POSITION_SIZE=10.0
MAX_DAILY_LOSS=1000.0
MAX_OPEN_POSITIONS=5

# Resources (adjust for your server)
POSTGRES_SHARED_BUFFERS=2GB
POSTGRES_EFFECTIVE_CACHE_SIZE=6GB
API_WORKERS=4
EOF
```

### 5. Set Domain (Optional)
```bash
# If using a domain
echo "CORS_ORIGINS=https://yourdomain.com" >> .env
echo "VITE_API_URL=https://yourdomain.com/api" >> .env
```

---

## Deployment (10 minutes)

### 6. Build Images
```bash
./scripts/deployment/build.sh
```

### 7. Deploy
```bash
./scripts/deployment/deploy.sh
```

### 8. Verify
```bash
# Run health check
./scripts/deployment/health_check.sh

# Check services
docker-compose -f docker-compose.prod.yml ps
```

---

## Access Services (2 minutes)

### URLs
- **API**: http://your-server-ip:8003
- **API Docs**: http://your-server-ip:8003/docs
- **Grafana**: http://your-server-ip:3001 (admin / your-grafana-password)
- **Prometheus**: http://your-server-ip:9090
- **Kibana**: http://your-server-ip:5601
- **MLflow**: http://your-server-ip:5000

### Test API
```bash
# Health check
curl http://localhost:8003/health

# API docs
curl http://localhost:8003/docs

# Metrics
curl http://localhost:8003/metrics
```

---

## SSL Setup (Optional, 5 minutes)

### 9. Install Certbot
```bash
sudo apt-get update
sudo apt-get install certbot -y
```

### 10. Get Certificate
```bash
# Stop nginx temporarily
docker-compose -f docker-compose.prod.yml stop nginx

# Get certificate
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Copy to project
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./ssl/
sudo chown -R $USER:$USER ./ssl/

# Start nginx
docker-compose -f docker-compose.prod.yml start nginx
```

---

## Firewall (3 minutes)

### 11. Configure UFW
```bash
# Enable firewall
sudo ufw enable

# Allow SSH (IMPORTANT - do this first!)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Check status
sudo ufw status
```

---

## Monitoring Setup (5 minutes)

### 12. Access Grafana
1. Open: http://your-server-ip:3001
2. Login: admin / (your GRAFANA_ADMIN_PASSWORD)
3. Navigate to Dashboards
4. All dashboards are pre-configured!

### 13. Configure Alerts (Optional)
1. In Grafana: Settings → Notification channels
2. Add Slack/Email/PagerDuty
3. Alerts will use these channels

---

## Backup (2 minutes)

### 14. Create First Backup
```bash
./scripts/deployment/backup.sh
```

### 15. Schedule Automated Backups
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /opt/RiseTraderMVP/scripts/deployment/backup.sh
```

---

## Verification Checklist

Run through this quick checklist:

```bash
# All services running?
docker-compose -f docker-compose.prod.yml ps

# Database ready?
docker exec risetrader-postgres pg_isready -U postgres

# Redis ready?
docker exec risetrader-redis redis-cli ping

# API responding?
curl http://localhost:8003/health

# Grafana working?
curl http://localhost:3001/api/health
```

---

## Common Commands

### View Logs
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Just API
docker-compose -f docker-compose.prod.yml logs -f api

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100
```

### Restart Services
```bash
# Restart all
docker-compose -f docker-compose.prod.yml restart

# Restart API only
docker-compose -f docker-compose.prod.yml restart api
```

### Update
```bash
./scripts/deployment/update.sh
```

### Rollback
```bash
./scripts/deployment/rollback.sh --version 1.0.0
```

### Health Check
```bash
./scripts/deployment/health_check.sh
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs service-name

# Check status
docker ps -a

# Restart
docker-compose -f docker-compose.prod.yml restart service-name
```

### API Not Responding
```bash
# Check API logs
docker-compose -f docker-compose.prod.yml logs api

# Check health
curl -v http://localhost:8003/health

# Restart API
docker-compose -f docker-compose.prod.yml restart api
```

### Database Connection Error
```bash
# Check PostgreSQL
docker exec risetrader-postgres pg_isready -U postgres

# Check connection string in .env
cat .env | grep DATABASE_URL

# Restart database
docker-compose -f docker-compose.prod.yml restart postgres
```

### Out of Memory
```bash
# Check memory usage
docker stats

# Reduce resources in .env
POSTGRES_SHARED_BUFFERS=1GB  # Instead of 2GB
API_WORKERS=2  # Instead of 4

# Restart
docker-compose -f docker-compose.prod.yml restart
```

---

## Next Steps

1. **Monitor for 24 hours** - Watch Grafana dashboards
2. **Test paper trading** - Verify all strategies work
3. **Configure alerts** - Set up Slack/email notifications
4. **Review logs** - Check for any errors or warnings
5. **Test backup/restore** - Ensure data recovery works
6. **Read full documentation** - See DOCKER_DEPLOYMENT.md

---

## Security Reminders

- [ ] All default passwords changed
- [ ] SSL/TLS enabled (if using domain)
- [ ] Firewall configured
- [ ] Monitoring ports not publicly accessible
- [ ] Backups encrypted
- [ ] .env file never committed to git

---

## Emergency Stop

If anything goes wrong:

```bash
# Stop all services
docker-compose -f docker-compose.prod.yml down

# View logs
docker-compose -f docker-compose.prod.yml logs

# Contact support
```

---

## Support

- **Documentation**: DOCKER_DEPLOYMENT.md (comprehensive guide)
- **Checklist**: DEPLOYMENT_CHECKLIST.md (detailed verification)
- **Issues**: GitHub Issues
- **Email**: support@risetrader.com

---

**You're all set!** 🚀

RiseTrader is now running in production. Monitor closely for the first 24-48 hours.

**IMPORTANT**: Keep `ENABLE_LIVE_TRADING=false` until thoroughly tested in paper trading mode for at least 30 days.
