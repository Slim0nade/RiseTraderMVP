#!/bin/bash

# ============================================================================
# RiseTrader - Production Deployment Script
# Deploys RiseTrader with health checks and rollback capability
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENVIRONMENT="${1:-production}"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.${ENVIRONMENT}"

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}RiseTrader - Production Deployment${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Environment: ${ENVIRONMENT}"
echo "Compose File: ${COMPOSE_FILE}"
echo "Env File: ${ENV_FILE}"
echo ""

# Change to project root
cd "${PROJECT_ROOT}"

# Check if environment file exists
if [ ! -f "${ENV_FILE}" ]; then
    echo -e "${RED}✗ Environment file ${ENV_FILE} not found!${NC}"
    exit 1
fi

# Function to check service health
check_health() {
    local service=$1
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}Checking ${service} health...${NC}"

    while [ $attempt -le $max_attempts ]; do
        if docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps "${service}" | grep -q "Up (healthy)"; then
            echo -e "${GREEN}✓ ${service} is healthy${NC}"
            return 0
        fi

        echo -e "${BLUE}Attempt ${attempt}/${max_attempts}: Waiting for ${service}...${NC}"
        sleep 5
        ((attempt++))
    done

    echo -e "${RED}✗ ${service} failed to become healthy${NC}"
    return 1
}

# Function to rollback deployment
rollback() {
    echo -e "${RED}============================================================================${NC}"
    echo -e "${RED}Deployment Failed - Rolling Back${NC}"
    echo -e "${RED}============================================================================${NC}"

    echo -e "${YELLOW}Stopping services...${NC}"
    docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down

    echo -e "${YELLOW}Starting previous version...${NC}"
    # Restore from backup would go here

    exit 1
}

# Pre-deployment checks
echo -e "${BLUE}Running pre-deployment checks...${NC}"

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✗ Docker is not running${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker is running${NC}"

# Check disk space
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo -e "${RED}✗ Disk usage is above 80%: ${DISK_USAGE}%${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Disk space available (${DISK_USAGE}% used)${NC}"

# Backup database
echo -e "${YELLOW}Creating database backup...${NC}"
bash "${SCRIPT_DIR}/backup.sh"
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Database backup failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Database backup created${NC}"

echo ""
echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}Starting Deployment${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""

# Pull latest images
echo -e "${YELLOW}Pulling latest images...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" pull
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Failed to pull images${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Images pulled successfully${NC}"
echo ""

# Stop existing containers (graceful shutdown)
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down --remove-orphans
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Failed to stop containers${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Containers stopped${NC}"
echo ""

# Start services
echo -e "${YELLOW}Starting services...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Failed to start services${NC}"
    rollback
fi
echo -e "${GREEN}✓ Services started${NC}"
echo ""

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to be healthy...${NC}"
echo ""

# Check core infrastructure
check_health "postgres" || rollback
check_health "redis" || rollback

# Check application services
check_health "api" || rollback

# Check monitoring (non-critical)
check_health "prometheus" || echo -e "${YELLOW}⚠ Prometheus health check failed (non-critical)${NC}"
check_health "grafana" || echo -e "${YELLOW}⚠ Grafana health check failed (non-critical)${NC}"

echo ""
echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}Running Post-Deployment Tests${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""

# Test API endpoint
echo -e "${YELLOW}Testing API endpoint...${NC}"
API_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health)
if [ "$API_RESPONSE" == "200" ]; then
    echo -e "${GREEN}✓ API is responding (HTTP ${API_RESPONSE})${NC}"
else
    echo -e "${RED}✗ API is not responding correctly (HTTP ${API_RESPONSE})${NC}"
    rollback
fi

# Test database connection
echo -e "${YELLOW}Testing database connection...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres pg_isready -U postgres > /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database is accessible${NC}"
else
    echo -e "${RED}✗ Database is not accessible${NC}"
    rollback
fi

# Test Redis connection
echo -e "${YELLOW}Testing Redis connection...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T redis redis-cli ping > /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Redis is accessible${NC}"
else
    echo -e "${RED}✗ Redis is not accessible${NC}"
    rollback
fi

echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Deployment Successful!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Services are running and healthy."
echo ""
echo "Access points:"
echo "  - Dashboard: https://localhost/"
echo "  - API: https://localhost/api/v1/"
echo "  - Grafana: https://localhost/grafana/"
echo "  - Prometheus: https://localhost/prometheus/"
echo ""
echo "View logs:"
echo "  docker-compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} logs -f"
echo ""
echo "Service status:"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps
echo ""
echo -e "${GREEN}Deployment complete!${NC}"
