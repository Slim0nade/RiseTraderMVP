#!/bin/bash
#
# Test runner for Phase 6: Adversarial Debate & Safety Gates
#
# Usage:
#   ./run_phase6_tests.sh [test-type]
#
# Test types:
#   unit          - Run unit tests only (fast, with mocks)
#   integration   - Run integration tests (real LLMs, real data)
#   all           - Run all tests
#   data-check    - Check database has sufficient data
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default test type
TEST_TYPE="${1:-unit}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Phase 6: Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Set PYTHONPATH to include src directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../../src:$(pwd)"

# Check if running in Docker or locally
if [ -n "$DOCKER_CONTAINER" ]; then
    echo -e "${GREEN}Running inside Docker container${NC}"
else
    echo -e "${YELLOW}Running locally (not in Docker)${NC}"
fi

case "$TEST_TYPE" in
    unit)
        echo -e "${GREEN}Running Unit Tests (mocked, fast)${NC}"
        echo ""
        pytest tests/unit/agents/debate/ \
               tests/unit/agents/teams/ \
               tests/unit/agents/approval/ \
               -v \
               -m "unit and not integration" \
               --tb=short
        ;;

    integration)
        echo -e "${GREEN}Running Integration Tests (real LLMs + real data)${NC}"
        echo -e "${YELLOW}WARNING: This will make real LLM API calls!${NC}"
        echo ""
        sleep 2
        pytest tests/integration/test_phase6_with_real_data.py \
               -v \
               -m "integration" \
               --tb=short \
               -s  # Show print statements
        ;;

    data-check)
        echo -e "${GREEN}Checking database data availability${NC}"
        echo ""
        pytest tests/integration/test_phase6_with_real_data.py::TestPhase6DataQuality \
               -v \
               --tb=short \
               -s
        ;;

    all)
        echo -e "${GREEN}Running ALL Tests${NC}"
        echo ""
        echo -e "${BLUE}=== Unit Tests ===${NC}"
        pytest tests/unit/agents/debate/ \
               tests/unit/agents/teams/ \
               tests/unit/agents/approval/ \
               -v \
               -m "unit" \
               --tb=short

        echo ""
        echo -e "${BLUE}=== Integration Tests ===${NC}"
        echo -e "${YELLOW}WARNING: Real LLM calls ahead!${NC}"
        sleep 2
        pytest tests/integration/test_phase6_with_real_data.py \
               -v \
               -m "integration" \
               --tb=short \
               -s
        ;;

    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo ""
        echo "Usage: $0 [test-type]"
        echo ""
        echo "Test types:"
        echo "  unit          - Run unit tests only (fast, with mocks)"
        echo "  integration   - Run integration tests (real LLMs, real data)"
        echo "  all           - Run all tests"
        echo "  data-check    - Check database has sufficient data"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Tests Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
