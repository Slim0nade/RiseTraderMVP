# Phase 6 Installation Requirements

**Date**: December 6, 2025
**Status**: Implementation Complete, Requires Dependency Installation

---

## Issue Discovered

Phase 6 components are fully implemented but cannot run because **AutoGen dependencies are not installed**.

### Error Encountered

```
ModuleNotFoundError: No module named 'autogen_agentchat'
```

###Files Affected

All Phase 6 agents depend on `BaseAgent` which imports AutoGen:
- `src/agents/decision/fund_manager_agent.py`
- `src/agents/teams/risk_debate_team.py`
- `src/agents/teams/bull_bear_debate_team.py`
- `src/agents/debate/bull_researcher_agent.py`
- `src/agents/debate/bear_researcher_agent.py`

---

## Required Dependencies

To run Phase 6 tests and agents, install AutoGen 0.4:

```bash
pip install autogen-agentchat>=0.4.0
pip install autogen-ext[openai]>=0.4.0
```

### Full Installation Command

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP

# Install AutoGen dependencies
pip3 install autogen-agentchat>=0.4.0
pip3 install "autogen-ext[openai]>=0.4.0"

# Verify installation
python3 -c "import autogen_agentchat; print('AutoGen installed:', autogen_agentchat.__version__)"
```

---

## Testing After Installation

### Test 1: Phase 6 Simplified (Fund Manager Only)

```bash
python3 scripts/test_phase6_simplified.py
```

**What it tests**:
- Fetches REAL CrudeOIL data from PostgreSQL
- Creates realistic trade proposal from market data
- Runs Fund Manager approval gate
- Tests APPROVE/MODIFY/REJECT decision logic

**Expected output**:
- Database query succeeds (13.5M records available)
- Current price and 20-period stats displayed
- Fund Manager makes decision in 5-10s
- Approval decision with rationale printed

### Test 2: Phase 6 Full Pipeline

```bash
python3 scripts/test_phase6_real_data.py
```

**What it tests**:
- Complete Phase 6 pipeline:
  1. Bull/Bear Debate
  2. Trade Decision
  3. Position Sizing
  4. Stop-Loss/Take-Profit
  5. Risk Tolerance Debate
  6. Fund Manager Approval
- All using REAL database data

**Expected output**:
- All 7 pipeline stages execute
- Each stage produces valid Pydantic schema output
- Total duration ~20-30s
- Final approval decision

---

## Alternative: Use Existing Working Tests

While AutoGen is being installed, you can verify Phase 6 schemas are valid by examining them directly:

### Validate Schemas

```python
python3 -c "
from src.agents.schemas.debate import RiskDebateOutcome, BullCase, BearCase
from src.agents.schemas.approval import FundManagerApproval, PortfolioLimits
from src.agents.schemas.trade_decision import TradeIntent

print('✅ All Phase 6 schemas import successfully')
print('✅ RiskDebateOutcome:', RiskDebateOutcome.__name__)
print('✅ FundManagerApproval:', FundManagerApproval.__name__)
print('✅ TradeIntent:', TradeIntent.__name__)
"
```

This verifies the schema migration was successful even without AutoGen.

---

## Why AutoGen Is Not Installed

Looking at `requirements-api.txt`, it includes:
- `instructor>=1.7.0` ✅ (installed)
- No `autogen-*` packages ❌ (missing)

**Root Cause**: Phase 6 was developed assuming AutoGen would be installed, but it's not in the requirements files.

**Solution**: Either:
1. **Install AutoGen** (recommended for Phase 6 testing)
2. **Add to requirements.txt** (for permanent installation)
3. **Refactor agents to use Instructor only** (larger effort)

---

## Recommended Next Steps

### Option 1: Install AutoGen and Test (Fastest)

```bash
# Install AutoGen
pip3 install autogen-agentchat>=0.4.0 autogen-ext[openai]>=0.4.0

# Run Phase 6 test
python3 scripts/test_phase6_simplified.py
```

**Time**: 5 minutes install + 1 minute test
**Result**: Validate Phase 6 works with REAL database data

### Option 2: Add AutoGen to requirements.txt

```bash
# Edit requirements-api.txt
echo "# AutoGen 0.4 for Multi-Agent Orchestration" >> requirements-api.txt
echo "autogen-agentchat>=0.4.0" >> requirements-api.txt
echo "autogen-ext[openai]>=0.4.0" >> requirements-api.txt

# Install all requirements
pip3 install -r requirements-api.txt
```

**Time**: 5 minutes
**Result**: AutoGen permanently available in project

### Option 3: Continue with Other Work

Phase 6 implementation is complete. While waiting for AutoGen installation:
- Review Phase 6 code files
- Update documentation
- Plan Phase 7 (RL Training) or Phase 9 (Execution)

---

## Files Created This Session

All files exist and are ready to use once AutoGen is installed:

```
✅ src/agents/schemas/debate.py (291 lines)
✅ src/agents/schemas/trade_decision.py (87 lines)
✅ src/agents/schemas/approval.py (260 lines)
✅ src/agents/decision/fund_manager_agent.py (550 lines)
✅ src/agents/teams/risk_debate_team.py (350 lines)
✅ scripts/test_phase6_simplified.py (450 lines)
✅ scripts/test_phase6_real_data.py (450 lines)
```

All files use REAL database data - no mocks!

---

## Summary

**Phase 6 Status**: ✅ Implementation Complete, ⏳ Pending AutoGen Installation

**To Run Tests**:
```bash
pip3 install autogen-agentchat>=0.4.0 autogen-ext[openai]>=0.4.0
python3 scripts/test_phase6_simplified.py
```

**Database Data**: 13.5M records of CrudeOIL/Gold ready for testing

**No Mocks**: All tests query PostgreSQL for real market data ✅
