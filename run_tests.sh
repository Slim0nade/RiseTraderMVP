#!/bin/bash

# RiseTrader Test Runner Script
# Provides convenient commands for running different test suites

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RiseTrader Test Suite${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Parse command line arguments
COMMAND=${1:-all}

case $COMMAND in
    all)
        echo -e "${YELLOW}Running all tests...${NC}"
        pytest --cov=src --cov-report=term-missing --cov-report=html
        ;;
    
    unit)
        echo -e "${YELLOW}Running unit tests...${NC}"
        pytest tests/unit/ -v
        ;;
    
    integration)
        echo -e "${YELLOW}Running integration tests...${NC}"
        pytest tests/integration/ -v
        ;;
    
    e2e)
        echo -e "${YELLOW}Running end-to-end tests...${NC}"
        pytest tests/e2e/ -v
        ;;
    
    performance)
        echo -e "${YELLOW}Running performance tests...${NC}"
        pytest tests/performance/ -v --durations=10
        ;;
    
    critical)
        echo -e "${YELLOW}Running critical path tests...${NC}"
        pytest -m critical -v
        ;;
    
    fast)
        echo -e "${YELLOW}Running fast tests only...${NC}"
        pytest -m "not slow" -v
        ;;
    
    coverage)
        echo -e "${YELLOW}Generating coverage report...${NC}"
        pytest --cov=src --cov-report=html --cov-fail-under=85
        echo -e "${GREEN}Coverage report generated at htmlcov/index.html${NC}"
        ;;
    
    agent)
        echo -e "${YELLOW}Running agent tests...${NC}"
        pytest -m agent -v
        ;;
    
    api)
        echo -e "${YELLOW}Running API tests...${NC}"
        pytest -m api -v
        ;;
    
    database)
        echo -e "${YELLOW}Running database tests...${NC}"
        pytest -m database -v
        ;;
    
    watch)
        echo -e "${YELLOW}Running tests in watch mode...${NC}"
        pytest-watch -- -v
        ;;
    
    debug)
        echo -e "${YELLOW}Running tests with debugger...${NC}"
        pytest -v -s --pdb
        ;;
    
    clean)
        echo -e "${YELLOW}Cleaning test artifacts...${NC}"
        rm -rf .pytest_cache htmlcov .coverage
        echo -e "${GREEN}Clean complete${NC}"
        ;;
    
    help|*)
        echo "Usage: ./run_tests.sh [command]"
        echo ""
        echo "Commands:"
        echo "  all          Run all tests with coverage (default)"
        echo "  unit         Run unit tests only"
        echo "  integration  Run integration tests only"
        echo "  e2e          Run end-to-end tests only"
        echo "  performance  Run performance tests only"
        echo "  critical     Run critical path tests only"
        echo "  fast         Run fast tests (exclude slow)"
        echo "  coverage     Generate coverage report"
        echo "  agent        Run agent tests only"
        echo "  api          Run API tests only"
        echo "  database     Run database tests only"
        echo "  watch        Run tests in watch mode"
        echo "  debug        Run tests with debugger"
        echo "  clean        Clean test artifacts"
        echo "  help         Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./run_tests.sh all"
        echo "  ./run_tests.sh unit"
        echo "  ./run_tests.sh critical"
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test run complete!${NC}"
echo -e "${GREEN}========================================${NC}"
