#!/bin/bash
# =============================================================================
# require-integration-test.sh — TaskCompleted hook
# No task completes without a passing integration test tagged [integration-pass].
# Called automatically when any agent attempts to mark a task as done.
# =============================================================================

INPUT=$(cat)
TASK=$(echo "$INPUT" | jq -r '.task.title // "unknown task"')

# Check recent commits for [integration-pass] tag
if git log --oneline -10 2>/dev/null | grep -q "\[integration-pass\]"; then
  echo "Integration test confirmed for task: $TASK"
  exit 0
fi

# No integration pass found
echo "================================================================" >&2
echo "  INTEGRATION TEST REQUIRED — TASK BLOCKED" >&2
echo "================================================================" >&2
echo "Task: $TASK" >&2
echo "" >&2
echo "No [integration-pass] tag found in recent commits." >&2
echo "" >&2
echo "Required steps before completing this task:" >&2
echo "  1. mcp-verifier must run integration tests against real MT4 data" >&2
echo "  2. Tests must verify output is DYNAMIC (not hardcoded)" >&2
echo "  3. Commit with tag: [integration-pass]" >&2
echo "  4. Format: git commit -m 'feat(scope): description [integration-pass]'" >&2
echo "" >&2
echo "Ask mcp-verifier to validate before marking complete." >&2
echo "================================================================" >&2
exit 2
