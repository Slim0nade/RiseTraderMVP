#!/bin/bash
# Test script for agent pipeline endpoints
# Usage: ./scripts/test_agent_pipelines.sh

set -e

API_URL="${API_URL:-http://localhost:8003}"
BASE_PATH="/api/agent-pipelines"

echo "🧪 Testing Agent Pipeline Endpoints"
echo "API URL: $API_URL"
echo "-----------------------------------"

# Test 1: Health Check
echo ""
echo "1️⃣  Testing Health Endpoint..."
curl -s -X GET "$API_URL$BASE_PATH/health" \
  -H "Content-Type: application/json" | jq '.' || echo "❌ Health check failed"

# Test 2: Registry Stats
echo ""
echo "2️⃣  Testing Registry Stats Endpoint..."
curl -s -X GET "$API_URL$BASE_PATH/stats" \
  -H "Content-Type: application/json" | jq '.' || echo "❌ Stats endpoint failed"

# Test 3: Analysis Pipeline
echo ""
echo "3️⃣  Testing Analysis Pipeline..."
curl -s -X POST "$API_URL$BASE_PATH/analysis" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "Gold",
    "timeframe": "4H"
  }' | jq '.' || echo "❌ Analysis pipeline failed"

# Test 4: Decision Pipeline (requires analysis output)
echo ""
echo "4️⃣  Testing Decision Pipeline..."
curl -s -X POST "$API_URL$BASE_PATH/decision" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "Gold",
    "analysis": {
      "technical": {"current_price": 2050.00, "direction": "bullish"},
      "fundamental": {"macro_score": 0.65},
      "sentiment": {"positioning_score": 0.55}
    },
    "trade_context": {
      "account_balance": 50000.0,
      "current_drawdown": 0.03,
      "trade_conviction": 0.75,
      "win_rate": 0.60,
      "avg_win": 125,
      "avg_loss": 50,
      "correlation_with_existing": 0.0,
      "major_event_within_24h": false,
      "major_event_within_48h": true
    }
  }' | jq '.' || echo "❌ Decision pipeline failed"

# Test 5: Full Pipeline
echo ""
echo "5️⃣  Testing Full Trading Pipeline..."
curl -s -X POST "$API_URL$BASE_PATH/full" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "Gold",
    "timeframe": "4H",
    "trade_context": {
      "account_balance": 50000.0,
      "current_drawdown": 0.03,
      "trade_conviction": 0.75,
      "win_rate": 0.60,
      "avg_win": 125,
      "avg_loss": 50,
      "correlation_with_existing": 0.0,
      "major_event_within_24h": false,
      "major_event_within_48h": true
    }
  }' | jq '.' || echo "❌ Full pipeline failed"

echo ""
echo "-----------------------------------"
echo "✅ All endpoint tests complete!"
