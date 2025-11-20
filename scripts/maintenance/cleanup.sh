#!/bin/bash

# ============================================================================
# RiseTrader - Docker Cleanup Script
# Clean up unused Docker resources
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}RiseTrader - Docker Cleanup${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# Function to display disk usage
show_disk_usage() {
    echo -e "${BLUE}Docker Disk Usage:${NC}"
    docker system df
    echo ""
}

# Show initial disk usage
echo -e "${YELLOW}Before cleanup:${NC}"
show_disk_usage

# Confirmation
echo -e "${YELLOW}⚠ This will remove:${NC}"
echo "  - Stopped containers"
echo "  - Unused networks"
echo "  - Dangling images"
echo "  - Build cache"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 0
fi
echo ""

# ============================================================================
# Cleanup Operations
# ============================================================================

echo -e "${YELLOW}Removing stopped containers...${NC}"
docker container prune -f
echo -e "${GREEN}✓ Stopped containers removed${NC}"
echo ""

echo -e "${YELLOW}Removing unused networks...${NC}"
docker network prune -f
echo -e "${GREEN}✓ Unused networks removed${NC}"
echo ""

echo -e "${YELLOW}Removing dangling images...${NC}"
docker image prune -f
echo -e "${GREEN}✓ Dangling images removed${NC}"
echo ""

echo -e "${YELLOW}Removing build cache...${NC}"
docker builder prune -f
echo -e "${GREEN}✓ Build cache removed${NC}"
echo ""

# Optional: Remove unused volumes (be careful!)
read -p "Remove unused volumes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}⚠ WARNING: This will delete data!${NC}"
    read -p "Are you sure? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${YELLOW}Removing unused volumes...${NC}"
        docker volume prune -f
        echo -e "${GREEN}✓ Unused volumes removed${NC}"
    fi
fi
echo ""

# Optional: Remove old RiseTrader images
read -p "Remove old RiseTrader images? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Removing old RiseTrader images...${NC}"
    docker images | grep risetrader | grep -v latest | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
    echo -e "${GREEN}✓ Old images removed${NC}"
fi
echo ""

# Show final disk usage
echo -e "${YELLOW}After cleanup:${NC}"
show_disk_usage

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo -e "${GREEN}Done!${NC}"
