#!/bin/bash

# ============================================================================
# RiseTrader - Backup Script
# Creates backups of database, configuration, and models
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ENVIRONMENT="${1:-production}"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.${ENVIRONMENT}"

# Backup retention (days)
RETENTION_DAYS=7

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}RiseTrader - Backup${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Timestamp: ${TIMESTAMP}"
echo "Environment: ${ENVIRONMENT}"
echo "Backup Directory: ${BACKUP_DIR}"
echo ""

# Change to project root
cd "${PROJECT_ROOT}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Function to cleanup old backups
cleanup_old_backups() {
    echo -e "${YELLOW}Cleaning up backups older than ${RETENTION_DAYS} days...${NC}"
    find "${BACKUP_DIR}" -name "backup_*" -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}✓ Old backups cleaned${NC}"
}

# Create timestamped backup directory
BACKUP_PATH="${BACKUP_DIR}/backup_${TIMESTAMP}"
mkdir -p "${BACKUP_PATH}"

echo -e "${YELLOW}Creating backup at ${BACKUP_PATH}${NC}"
echo ""

# ============================================================================
# Backup PostgreSQL Database
# ============================================================================
echo -e "${YELLOW}Backing up PostgreSQL database...${NC}"

if docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps postgres | grep -q "Up"; then
    # Get database credentials from env file
    source "${ENV_FILE}"

    # Create database dump
    docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T postgres \
        pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-risetrader}" \
        --format=custom --compress=9 \
        > "${BACKUP_PATH}/database.dump"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Database backed up: database.dump${NC}"

        # Get backup size
        BACKUP_SIZE=$(du -h "${BACKUP_PATH}/database.dump" | cut -f1)
        echo -e "${GREEN}  Size: ${BACKUP_SIZE}${NC}"
    else
        echo -e "${RED}✗ Database backup failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ PostgreSQL container is not running${NC}"
fi

echo ""

# ============================================================================
# Backup Configuration Files
# ============================================================================
echo -e "${YELLOW}Backing up configuration files...${NC}"

mkdir -p "${BACKUP_PATH}/config"

# Backup environment files
cp .env.* "${BACKUP_PATH}/config/" 2>/dev/null || true

# Backup docker configurations
cp -r docker "${BACKUP_PATH}/config/" 2>/dev/null || true

# Backup docker-compose files
cp docker-compose*.yml "${BACKUP_PATH}/config/" 2>/dev/null || true

echo -e "${GREEN}✓ Configuration files backed up${NC}"
echo ""

# ============================================================================
# Backup ML Models
# ============================================================================
echo -e "${YELLOW}Backing up ML models...${NC}"

if [ -d "${PROJECT_ROOT}/models" ]; then
    mkdir -p "${BACKUP_PATH}/models"
    cp -r "${PROJECT_ROOT}/models/"* "${BACKUP_PATH}/models/" 2>/dev/null || true

    if [ "$(ls -A ${BACKUP_PATH}/models 2>/dev/null)" ]; then
        echo -e "${GREEN}✓ ML models backed up${NC}"
    else
        echo -e "${YELLOW}⚠ No models found to backup${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Models directory not found${NC}"
fi

echo ""

# ============================================================================
# Backup Application Logs (last 7 days)
# ============================================================================
echo -e "${YELLOW}Backing up recent application logs...${NC}"

if [ -d "${PROJECT_ROOT}/logs" ]; then
    mkdir -p "${BACKUP_PATH}/logs"

    # Copy logs from last 7 days
    find "${PROJECT_ROOT}/logs" -name "*.log" -mtime -7 -exec cp {} "${BACKUP_PATH}/logs/" \; 2>/dev/null || true

    if [ "$(ls -A ${BACKUP_PATH}/logs 2>/dev/null)" ]; then
        echo -e "${GREEN}✓ Application logs backed up${NC}"
    else
        echo -e "${YELLOW}⚠ No recent logs found${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Logs directory not found${NC}"
fi

echo ""

# ============================================================================
# Create backup metadata
# ============================================================================
echo -e "${YELLOW}Creating backup metadata...${NC}"

cat > "${BACKUP_PATH}/metadata.txt" <<EOF
RiseTrader Backup
=================

Timestamp: ${TIMESTAMP}
Date: $(date)
Environment: ${ENVIRONMENT}
Hostname: $(hostname)
User: $(whoami)

Contents:
- PostgreSQL database dump
- Configuration files
- ML models
- Application logs (last 7 days)

Restore Instructions:
1. Restore database: ./scripts/deployment/restore.sh ${TIMESTAMP}
2. Verify database connection
3. Restart services

EOF

echo -e "${GREEN}✓ Metadata created${NC}"
echo ""

# ============================================================================
# Create compressed archive (optional)
# ============================================================================
read -p "Create compressed archive? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Creating compressed archive...${NC}"

    tar -czf "${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz" -C "${BACKUP_DIR}" "backup_${TIMESTAMP}"

    if [ $? -eq 0 ]; then
        ARCHIVE_SIZE=$(du -h "${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz" | cut -f1)
        echo -e "${GREEN}✓ Archive created: backup_${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})${NC}"

        # Remove uncompressed backup
        read -p "Remove uncompressed backup? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "${BACKUP_PATH}"
            echo -e "${GREEN}✓ Uncompressed backup removed${NC}"
        fi
    else
        echo -e "${RED}✗ Failed to create archive${NC}"
    fi
fi

echo ""

# Cleanup old backups
cleanup_old_backups

echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Backup Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Backup location: ${BACKUP_PATH}"
echo ""
echo "To restore this backup:"
echo "  ./scripts/deployment/restore.sh ${TIMESTAMP}"
echo ""
echo -e "${GREEN}Done!${NC}"
