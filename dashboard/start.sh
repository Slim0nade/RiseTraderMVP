#!/bin/bash

# RiseTrader Dashboard - Quick Start Script

set -e

echo "=========================================="
echo "RiseTrader Dashboard - Quick Start"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is not installed${NC}"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}Error: Node.js 18+ required (current: $(node -v))${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Node.js $(node -v) detected${NC}"
echo ""

# Check if in correct directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}Error: Must be run from dashboard directory${NC}"
    echo "cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/dashboard"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env created${NC}"
    echo ""
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}Installing dependencies...${NC}"
    npm install
    echo -e "${GREEN}✓ Dependencies installed${NC}"
    echo ""
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}"
    echo ""
fi

# Display configuration
echo -e "${BLUE}Configuration:${NC}"
echo "  API URL: $(grep VITE_API_BASE_URL .env | cut -d'=' -f2)"
echo "  WS URL:  $(grep VITE_WS_URL .env | cut -d'=' -f2)"
echo ""

# Check if API is running
API_URL=$(grep VITE_API_BASE_URL .env | cut -d'=' -f2)
if [ -n "$API_URL" ]; then
    echo -e "${BLUE}Checking API connection...${NC}"
    if curl -s --max-time 3 "${API_URL}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is running${NC}"
    else
        echo -e "${YELLOW}⚠ Warning: Cannot connect to API at ${API_URL}${NC}"
        echo "  Make sure the RiseTrader API is running"
    fi
    echo ""
fi

# Start development server
echo -e "${BLUE}Starting development server...${NC}"
echo -e "${GREEN}Dashboard will be available at: http://localhost:3000${NC}"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

npm run dev
