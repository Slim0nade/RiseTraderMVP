#!/bin/bash

# ============================================================================
# RiseTrader - Restore Script
# Restores database and configuration from backup
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
BACKUP_DIR="${PROJECT_ROOT}/backups"
BACKUP_ID="${1:-}"
ENVIRONMENT="${2:-production}"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.${ENVIRONMENT}"

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}RiseTrader - Restore from Backup${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# Change to project root
cd "${PROJECT_ROOT}"

# Validate backup ID
if [ -z "$BACKUP_ID" ]; then
    echo -e "${RED}✗ Backup ID required${NC}"
    echo ""
    echo "Usage: $0 <backup_id> [environment]"
    echo ""
    echo "Available backups:"
    ls -lh "${BACKUP_DIR}" | grep backup_ || echo "  No backups found"
    exit 1
fi

# Determine backup path
if [ -d "${BACKUP_DIR}/backup_${BACKUP_ID}" ]; then
    BACKUP_PATH="${BACKUP_DIR}/backup_${BACKUP_ID}"
elif [ -f "${BACKUP_DIR}/backup_${BACKUP_ID}.tar.gz" ]; then
    echo -e "${YELLOW}Extracting compressed backup...${NC}"
    tar -xzf "${BACKUP_DIR}/backup_${BACKUP_ID}.tar.gz" -C "${BACKUP_DIR}"
    BACKUP_PATH="${BACKUP_DIR}/backup_${BACKUP_ID}"
else
    echo -e "${RED}✗ Backup not found: ${BACKUP_ID}${NC}"
    exit 1
fi

echo "Backup Path: ${BACKUP_PATH}"
echo "Environment: ${ENVIRONMENT}"
echo ""

# Display backup metadata
if [ -f "${BACKUP_PATH}/metadata.txt" ]; then
    echo -e "${BLUE}Backup Information:${NC}"
    cat "${BACKUP_PATH}/metadata.txt"
    echo ""
fi

# Confirmation
echo -e "${YELLOW}⚠ WARNING: This will overwrite the current database!${NC}"
read -p "Continue with restore? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi
echo ""

# ============================================================================
# Restore PostgreSQL Database
# ============================================================================
echo -e "${YELLOW}Restoring PostgreSQL database...${NC}"

if [ ! -f "${BACKUP_PATH}/database.dump" ]; then
    echo -e "${RED}✗ Database dump not found in backup${NC}"
    exit 1
fi

# Ensure PostgreSQL is running
if ! docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps postgres | grep -q "Up"; then
    echo -e "${YELLOW}Starting PostgreSQL...${NC}"
    docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d postgres
    sleep 10
fi

# Get database credentials
source "${ENV_FILE}"

# Drop existing connections
echo -e "${YELLOW}Dropping existing database connections...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
    psql -U "${POSTGRES_USER:-postgres}" -d postgres -c \
    "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '${POSTGRES_DB:-risetrader}' AND pid <> pg_backend_pid();" \
    || true

# Drop and recreate database
echo -e "${YELLOW}Recreating database...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
    psql -U "${POSTGRES_USER:-postgres}" -d postgres -c \
    "DROP DATABASE IF EXISTS ${POSTGRES_DB:-risetrader};"

docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
    psql -U "${POSTGRES_USER:-postgres}" -d postgres -c \
    "CREATE DATABASE ${POSTGRES_DB:-risetrader};"

# Restore database from dump
echo -e "${YELLOW}Restoring database from dump...${NC}"
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
    pg_restore -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-risetrader}" \
    --clean --if-exists --no-owner --no-acl \
    < "${BACKUP_PATH}/database.dump"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database restored successfully${NC}"
else
    echo -e "${RED}✗ Database restore failed${NC}"
    exit 1
fi

echo ""

# ============================================================================
# Restore ML Models
# ============================================================================
echo -e "${YELLOW}Restoring ML models...${NC}"

if [ -d "${BACKUP_PATH}/models" ] && [ "$(ls -A ${BACKUP_PATH}/models 2>/dev/null)" ]; then
    mkdir -p "${PROJECT_ROOT}/models"
    cp -r "${BACKUP_PATH}/models/"* "${PROJECT_ROOT}/models/"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ ML models restored${NC}"
    else
        echo -e "${YELLOW}⚠ Failed to restore ML models${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No models found in backup${NC}"
fi

echo ""

# ============================================================================
# Verify Database
# ============================================================================
echo -e "${BLUE}Verifying database...${NC}"

# Test connection
docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
    psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-risetrader}" -c "SELECT version();" > /dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database connection verified${NC}"
else
    echo -e "${RED}✗ Database connection failed${NC}"
    exit 1
fi

# Count tables
TABLE_COUNT=$(docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
    psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-risetrader}" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')

echo -e "${GREEN}✓ Database contains ${TABLE_COUNT} tables${NC}"

echo ""

# ============================================================================
# Restart Services
# ============================================================================
echo -e "${YELLOW}Restarting services...${NC}"

docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" restart api ml-service

# Wait for services to be healthy
sleep 10

if docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps api | grep -q "Up (healthy)"; then
    echo -e "${GREEN}✓ Services restarted successfully${NC}"
else
    echo -e "${YELLOW}⚠ Services may not be fully healthy yet${NC}"
fi

echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Restore Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Database and models have been restored from backup: ${BACKUP_ID}"
echo ""
echo "Next steps:"
echo "  1. Verify API is responding: curl http://localhost/health"
echo "  2. Check application logs: docker-compose -f ${COMPOSE_FILE} logs -f api"
echo "  3. Test trading functionality"
echo ""
echo -e "${GREEN}Done!${NC}"
