#!/bin/bash
#
# Start RiseTrader MCP Server
#
# This script starts the MCP server with all dependencies (PostgreSQL, Redis)
# and provides helpful status information.
#
# Usage:
#   ./scripts/start_mcp_server.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

print_message "$BLUE" "================================================"
print_message "$BLUE" "  RiseTrader MCP Server Startup"
print_message "$BLUE" "================================================"
echo ""

# Check dependencies
print_message "$YELLOW" "Checking dependencies..."

if ! command_exists docker-compose; then
    print_message "$RED" "Error: docker-compose is not installed"
    exit 1
fi

if ! command_exists python; then
    print_message "$RED" "Error: python is not installed"
    exit 1
fi

print_message "$GREEN" "✓ Dependencies found"
echo ""

# Start Docker services
print_message "$YELLOW" "Starting Docker services (PostgreSQL, Redis)..."

docker-compose up -d postgres redis

# Wait for services to be healthy
print_message "$YELLOW" "Waiting for services to be ready..."

max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker-compose ps | grep -q "postgres.*healthy" && docker-compose ps | grep -q "redis.*healthy"; then
        print_message "$GREEN" "✓ All services are healthy"
        break
    fi

    attempt=$((attempt + 1))
    echo -n "."
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    print_message "$RED" "Error: Services failed to start within 30 seconds"
    docker-compose logs postgres redis
    exit 1
fi

echo ""

# Check configuration
print_message "$YELLOW" "Checking configuration..."

if [ ! -f "config/agents.yaml" ]; then
    print_message "$RED" "Error: config/agents.yaml not found"
    exit 1
fi

if [ ! -f ".env" ]; then
    print_message "$RED" "Error: .env file not found"
    exit 1
fi

print_message "$GREEN" "✓ Configuration files found"
echo ""

# Display service status
print_message "$BLUE" "Service Status:"
echo ""
docker-compose ps postgres redis
echo ""

# Get service URLs
POSTGRES_PORT=$(grep POSTGRES_PORT .env | cut -d '=' -f2)
REDIS_PORT=$(grep REDIS_PORT .env | cut -d '=' -f2)
MCP_PORT=7000

print_message "$BLUE" "Service Endpoints:"
echo "  PostgreSQL: localhost:${POSTGRES_PORT}"
echo "  Redis:      localhost:${REDIS_PORT}"
echo "  MCP Server: localhost:${MCP_PORT}"
echo ""

# Check if Python dependencies are installed
print_message "$YELLOW" "Checking Python dependencies..."

if ! python -c "import fastapi, redis, structlog, prometheus_client" 2>/dev/null; then
    print_message "$YELLOW" "Installing Python dependencies..."
    pip install -r requirements.txt
fi

print_message "$GREEN" "✓ Python dependencies ready"
echo ""

# Start MCP Server
print_message "$GREEN" "================================================"
print_message "$GREEN" "  Starting MCP Server"
print_message "$GREEN" "================================================"
echo ""

print_message "$BLUE" "MCP Server will start on http://localhost:${MCP_PORT}"
print_message "$BLUE" "Press Ctrl+C to stop"
echo ""
print_message "$YELLOW" "Available endpoints:"
echo "  GET  http://localhost:${MCP_PORT}/            - Server info"
echo "  GET  http://localhost:${MCP_PORT}/health      - Health check"
echo "  GET  http://localhost:${MCP_PORT}/agents      - List agents"
echo "  GET  http://localhost:${MCP_PORT}/metrics     - Prometheus metrics"
echo ""
print_message "$YELLOW" "Logs will appear below..."
echo ""
echo "----------------------------------------"
echo ""

# Set environment variables
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export AGENT_CONFIG_PATH="config/agents.yaml"

# Start MCP server
python -m src.agents.mcp_server

# Cleanup on exit
trap "print_message '$YELLOW' 'Stopping services...'; docker-compose stop postgres redis" EXIT
