#!/bin/bash

# ============================================================================
# RiseTrader - Aggregate Logs Script
# View and tail logs from all services
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
SERVICE="${2:-all}"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.${ENVIRONMENT}"

cd "${PROJECT_ROOT}"

# Function to display usage
usage() {
    echo "Usage: $0 [environment] [service]"
    echo ""
    echo "Environments: production, staging"
    echo "Services: all, api, postgres, redis, ml-service, nginx, prometheus, grafana"
    echo ""
    echo "Examples:"
    echo "  $0                          # View all logs (production)"
    echo "  $0 production api           # View API logs (production)"
    echo "  $0 staging                  # View all logs (staging)"
    exit 1
}

# Display header
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}RiseTrader - Service Logs${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Environment: ${ENVIRONMENT}"
echo "Service: ${SERVICE}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
echo ""

# Follow logs
if [ "$SERVICE" == "all" ]; then
    docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs -f --tail=100
else
    docker-compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs -f --tail=100 "${SERVICE}"
fi
