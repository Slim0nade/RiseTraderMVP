#!/bin/bash
#
# Start the Stealth Stop Manager Service
#
# This service monitors your positions 24/7 and automatically trails stops
# at predefined levels using institutional-grade pricing.
#
# Usage:
#   ./scripts/start_stealth_stops.sh              # Use defaults
#   MT4_HOST=192.168.0.123 ./scripts/start_stealth_stops.sh
#
# To run in background:
#   nohup ./scripts/start_stealth_stops.sh > logs/stealth_stops.log 2>&1 &
#

set -e

# Change to project directory
cd "$(dirname "$0")/.."

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set defaults
export MT4_HOST="${MT4_HOST:-192.168.0.123}"
export MT4_PORT="${MT4_PORT:-5555}"
export POLL_INTERVAL="${POLL_INTERVAL:-5}"

echo "=============================================="
echo "  🛡️  Stealth Stop Manager"
echo "=============================================="
echo "  MT4 Host: $MT4_HOST:$MT4_PORT"
echo "  Poll Interval: ${POLL_INTERVAL}s"
echo "  Config: config/stealth_stops.json"
echo "=============================================="
echo ""

# Run the service
python -m src.services.stealth_stop_manager
