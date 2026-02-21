# Session 2025-12-03 - LLM JSON Output Blocker

## Summary

Successfully fixed Ollama networking and database logging issues, but BLOCKED by LLM not producing JSON output.

## Progress ✅

### 1. Networking Fix - COMPLETE
- **Problem**: Ollama connection hardcoded to office IP `192.168.0.123`
- **Solution**:
  - Updated `src/agents/base/base_agent.py` to use environment variable
  - Updated `docker-compose.yml` OLLAMA_BASE_URL to public IP `75.154.254.174:11434`
- **Status**: ✅ LLM connection working - confirmed 22-91 second response times

### 2. Database Logging Fix - COMPLETE
- **Problem**: `execution_time_ms` parameter didn't match DecisionLog model
- **Solution**: Changed to `decision_latency_ms` and added required fields
- **File**: `src/agents/base/base_agent.py` line 324-334
- **Status**: ✅ Decisions logging successfully

### 3. Model Selection - ATTEMPTED
- **Initial Model**: deepseek-r1:14b - produces reasoning text, not JSON
- **Switched To**: qwen3:14b - better at structured output
- **File**: `src/agents/decision/position_sizing_agent.py` line 539
- **Status**: ⚠️ Still not producing JSON

## Current Blocker ❌

### LLM Not Producing JSON Output

**Symptoms**:
```
position_size_extraction_failed error=Expecting value: line 1 column 1 (char 0)
```

**What's Working**:
- Ollama connection successful (public IP)
- MCP tools executing correctly (Kelly, regime detection)
- LLM responding (22-91 second execution times)
- Database logging functioning

**What's NOT Working**:
- LLM output format is NOT JSON
- Both deepseek-r1:14b and qwen3:14b produce same issue
- Result shows LLM is echoing back the input task instead of responding

**Test Evidence** (4 scenarios, all failed):
```
Scenario 1: 22.1 seconds - 0.01 lots (fallback)
Scenario 2: 33.5 seconds - 0.01 lots (fallback)
Scenario 3: 20.1 seconds - 0.01 lots (fallback)
Scenario 4: 91.0 seconds - 0.01 lots (fallback)
```

All scenarios falling back to minimum safe size (0.01 lots) because JSON extraction fails.

## Root Cause Hypothesis

The AutoGen 0.4.4 `TaskResult` object is returning the USER message (the input task) instead of the ASSISTANT's response.

Evidence from logs:
```python
result=TaskResult(messages=[TextMessage(source='user', models_usage=None, content='\n**Position Sizing Request for Gold**\n\n...'
```

The `source='user'` indicates it's echoing the input, not the LLM's response.

## Next Steps to Unblock

### Option 1: Debug AutoGen Message Handling
Check if AutoGen 0.4.4 is properly extracting the assistant's response:
```python
# In _extract_decision method
if hasattr(result, 'messages') and result.messages:
    # Currently taking last message
    # May need to filter by source='assistant'
    assistant_messages = [m for m in result.messages if hasattr(m, 'source') and m.source == 'assistant']
```

### Option 2: Enable Response Format
Some models need explicit JSON mode:
```python
# In _create_model_client
OpenAIChatCompletionClient(
    ...,
    response_format={"type": "json_object"},  # Force JSON mode
)
```

### Option 3: Simplify System Prompt
Current prompt is 100+ lines. Try minimal JSON-focused prompt:
```python
return """Output ONLY a JSON object matching this schema:
{
    "lot_quantity": float,
    "dynamic_risk_percentage": float,
    ...
}

Do not include any other text. ONLY JSON."""
```

### Option 4: Use Different Model
Try mistral or llama3 which have proven JSON support with Ollama.

## Files Modified This Session

1. `docker-compose.yml` - Line 128: Changed Ollama URL to public IP
2. `src/agents/base/base_agent.py` - Line 116: Added `os.getenv()` for Ollama host
3. `src/agents/base/base_agent.py` - Line 324-334: Fixed DecisionLog parameters
4. `src/agents/decision/position_sizing_agent.py` - Line 539: Switched to qwen3:14b

## Test Execution Times

- Docker rebuild: ~2 minutes
- Container startup: ~15 seconds
- Integration test (4 scenarios): ~3 minutes total
  - Scenario 1: 22 seconds
  - Scenario 2: 34 seconds
  - Scenario 3: 20 seconds
  - Scenario 4: 91 seconds

## SC-001 Status

**Target**: 50%+ variance in position sizes across scenarios

**Current Result**: 0.0% variance (all scenarios returning 0.01 lots fallback)

**Why Failing**: LLM JSON extraction failure causes all scenarios to use safe minimum

**When Fixed**: Expect 80-90% variance based on mathematical calculations from previous session:
- Favorable scenario: ~1.38x baseline
- Adverse scenario: ~0.13x baseline
- Theoretical variance: 90.7%

## Environment Status

- **Docker**: All containers healthy
- **Database**: PostgreSQL 13.5M records
- **Ollama**: Accessible at public IP, both models available
- **Branch**: `005-intelligent-agent-trading`
- **Phase**: User Story 1 - 98% complete (blocked by JSON output)

## References

- Previous session: `.serena/SESSION_2025-12-03_US1_BLOCKER_OLLAMA.md`
- Integration test: `tests/integration/test_position_sizing_real.py`
- Position agent: `src/agents/decision/position_sizing_agent.py`
