#!/bin/bash
# =============================================================================
# validate-no-fakes.sh — PostToolUse hook for Edit|Write
# Blocks ANY edit that introduces or preserves hardcoded trading values.
# Called automatically after every file edit by any agent.
# =============================================================================

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Skip if no file or file doesn't exist
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  exit 0
fi

# Skip non-Python files (configs, markdown, etc.)
case "$FILE" in
  *.py) ;; # Check Python files
  *) exit 0 ;; # Skip everything else
esac

# Skip test fixture files and config examples
case "$FILE" in
  */fixtures/*|*/.env*|*/config/example*|*/CLAUDE.md|*/agents/*.md)
    exit 0 ;;
esac

VIOLATIONS=""

# =============================================================================
# CHECK 1: Hardcoded ATR defaults
# The StealthStopManager had: atr_defaults = {"CrudeOIL": 0.75, "XAUUSD": 15.0}
# All ATR must come from atr_calculator.py with real candle data.
# =============================================================================
if grep -qn 'atr_defaults\s*=' "$FILE" 2>/dev/null; then
  VIOLATIONS+="BLOCKED: Hardcoded atr_defaults dict detected in $FILE.\n"
  VIOLATIONS+="  Fix: Use atr_calculator.py with real candle data from MCP.\n\n"
fi

if grep -qn '"CrudeOIL":\s*0\.75\|"XAUUSD":\s*15\.0' "$FILE" 2>/dev/null; then
  VIOLATIONS+="BLOCKED: Known hardcoded ATR values (0.75 or 15.0) detected in $FILE.\n"
  VIOLATIONS+="  Fix: Calculate ATR dynamically from candle data.\n\n"
fi

# =============================================================================
# CHECK 2: Fake ML confidence / scores
# MLPredictionAgent had: confidence = 0.75, score = 0.5 + (features[0] * 0.3)
# Until real models exist, ML signals must be flagged and skipped.
# =============================================================================
if grep -qn 'confidence\s*=\s*0\.75' "$FILE" 2>/dev/null; then
  # Exclude comments and docstrings
  REAL_HITS=$(grep -n 'confidence\s*=\s*0\.75' "$FILE" | grep -v '#' | grep -v '"""' | grep -v "'''" | wc -l)
  if [ "$REAL_HITS" -gt 0 ]; then
    VIOLATIONS+="BLOCKED: Hardcoded ML confidence = 0.75 detected in $FILE.\n"
    VIOLATIONS+="  Fix: Use calibrated model output or skip ML signals entirely.\n\n"
  fi
fi

if grep -qn 'score\s*=\s*0\.5\s*+\s*(features' "$FILE" 2>/dev/null; then
  VIOLATIONS+="BLOCKED: Fake ML score formula (0.5 + features * weight) detected in $FILE.\n"
  VIOLATIONS+="  Fix: Use real trained model prediction or skip.\n\n"
fi

# =============================================================================
# CHECK 3: Fake correlation
# RiskOverseerAgent had: return 0.2 with comment "assume low correlation"
# Must use rolling 20-day correlation from real returns.
# =============================================================================
if grep -qn 'return\s*0\.2.*#.*correl\|assume.*low.*correlation' "$FILE" 2>/dev/null; then
  VIOLATIONS+="BLOCKED: Fake correlation value (0.2) detected in $FILE.\n"
  VIOLATIONS+="  Fix: Use rolling 20-day correlation from real price returns.\n\n"
fi

# =============================================================================
# CHECK 4: Fake VaR (hardcoded 2% daily volatility)
# RiskOverseerAgent had: portfolio_volatility = 0.02 * self.current_balance
# Must use realized rolling volatility from actual candle history.
# =============================================================================
if grep -qn '0\.02\s*\*\s*self\.current_balance' "$FILE" 2>/dev/null; then
  VIOLATIONS+="BLOCKED: Hardcoded VaR (2% * balance) detected in $FILE.\n"
  VIOLATIONS+="  Fix: Use realized rolling 20-day volatility from candle data.\n\n"
fi

if grep -qn 'assume.*2%.*daily\|# assume.*daily.*vol' "$FILE" 2>/dev/null; then
  VIOLATIONS+="BLOCKED: Hardcoded daily volatility assumption detected in $FILE.\n"
  VIOLATIONS+="  Fix: Calculate from actual historical returns.\n\n"
fi

# =============================================================================
# CHECK 5: Mock usage in test files
# NO MOCKS ALLOWED for MT4/MCP/market data interactions.
# All tests must hit real data via MCP server.
# =============================================================================
if grep -qn 'from unittest.mock import\|from unittest import mock\|MagicMock\|@patch(' "$FILE" 2>/dev/null; then
  # Only flag in test files — library code might legitimately import for type hints
  case "$FILE" in
    */test_*|*tests/*)
      VIOLATIONS+="BLOCKED: Mock usage detected in test file $FILE.\n"
      VIOLATIONS+="  Fix: Use real MCP/MT4 data for all integration tests.\n"
      VIOLATIONS+="  If unit-testing pure math, use static inputs (not mocks).\n\n"
      ;;
  esac
fi

# =============================================================================
# CHECK 6: Position sizing > 2% risk
# No function should allow risk exceeding 2% of account balance.
# =============================================================================
if grep -qn 'max_risk.*=.*0\.\(0[3-9]\|[1-9]\)' "$FILE" 2>/dev/null; then
  VIOLATIONS+="WARNING: max_risk appears to exceed 2% in $FILE.\n"
  VIOLATIONS+="  Review: Ensure position sizing caps at 2% account risk.\n\n"
fi

# =============================================================================
# OUTPUT RESULTS
# =============================================================================
if [ -n "$VIOLATIONS" ]; then
  echo "================================================================" >&2
  echo "  FAKE DETECTION HOOK — VIOLATIONS FOUND" >&2
  echo "================================================================" >&2
  echo -e "$VIOLATIONS" >&2
  echo "All trading calculations must use real market data." >&2
  echo "See CLAUDE.md 'ABSOLUTE RULES' section for details." >&2
  echo "================================================================" >&2
  exit 2
fi

exit 0
