#!/bin/bash
# API Startup Script with Hot Reload Support

set -e

echo "🧹 Clearing __pycache__ to prevent stale imports..."
find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "🚀 Starting RiseTrader API..."

# Check if hot reload is enabled
if [ "${ENABLE_HOT_RELOAD}" = "true" ]; then
    echo "🔥 Hot reload ENABLED - Code changes will auto-reload"
    exec uvicorn src.api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        --reload-dir /app/src \
        --reload-dir /app/config \
        --log-level info
else
    echo "⚡ Hot reload DISABLED - Production mode"
    exec uvicorn src.api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --log-level info
fi
