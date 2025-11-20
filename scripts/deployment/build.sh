#!/bin/bash

# ============================================================================
# RiseTrader - Build Docker Images Script
# Builds all Docker images with proper versioning
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
VERSION="${VERSION:-latest}"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}RiseTrader - Building Docker Images${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Version: ${VERSION}"
echo "Build Date: ${BUILD_DATE}"
echo "VCS Ref: ${VCS_REF}"
echo ""

# Change to project root
cd "${PROJECT_ROOT}"

# Function to build an image
build_image() {
    local service=$1
    local dockerfile=$2
    local image_name="risetrader/${service}:${VERSION}"

    echo -e "${YELLOW}Building ${service}...${NC}"

    docker build \
        --file "${dockerfile}" \
        --tag "${image_name}" \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        --build-arg VCS_REF="${VCS_REF}" \
        --build-arg VERSION="${VERSION}" \
        .

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully built ${image_name}${NC}"

        # Also tag as latest
        docker tag "${image_name}" "risetrader/${service}:latest"
        echo -e "${GREEN}✓ Tagged as risetrader/${service}:latest${NC}"
    else
        echo -e "${RED}✗ Failed to build ${service}${NC}"
        exit 1
    fi

    echo ""
}

# Build images
echo -e "${YELLOW}Starting build process...${NC}"
echo ""

# Build API service
build_image "api" "docker/api/Dockerfile"

# Build ML service
build_image "ml-service" "docker/ml-service/Dockerfile"

# Build Dashboard
build_image "dashboard" "docker/dashboard/Dockerfile"

# Build Nginx gateway
build_image "nginx" "docker/nginx/Dockerfile"

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Build Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Built images:"
docker images | grep risetrader | grep -E "${VERSION}|latest"
echo ""

# Optional: Push to registry
read -p "Push images to registry? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Pushing images to registry...${NC}"

    for service in api ml-service dashboard nginx; do
        echo -e "${YELLOW}Pushing risetrader/${service}:${VERSION}...${NC}"
        docker push "risetrader/${service}:${VERSION}"
        docker push "risetrader/${service}:latest"
    done

    echo -e "${GREEN}✓ All images pushed successfully${NC}"
fi

echo ""
echo -e "${GREEN}Done!${NC}"
