# Agent Team Configuration — February 22, 2026

## Setup Complete
All files created and verified on 2026-02-22.

## Files Created

### Agent Configs (.claude/agents/)
1. `lead.md` — Opus orchestrator, plan-only mode, roadmap guardian
2. `quant-dev.md` — Sonnet, strategies + agent logic, owns src/strategies/ src/agents/ src/ml/
3. `risk-eng.md` — Sonnet, risk infrastructure, owns stealth stops + ATR + execution
4. `mcp-verifier.md` — Sonnet, exclusive MCP access, no-mocks enforcer, owns tests/
5. `reviewer.md` — Sonnet, read-only, 5-lens review (security/perf/arch/regression/fakes)
6. `spread-builder.md` — Sonnet, Phase 2 specialist, spread + ag + carry strategies
7. `ml-trainer.md` — Opus, Phase 4 specialist, worktree isolation, real model training

### Archived Old Agents (.claude/agents/archived/)
- agent-developer.md, backend-architect.md, code-reviewer.md
- database-specialist.md, devops-engineer.md, frontend-developer.md
- memory-manager.md, ml-engineer.md

### Quality Gate Scripts (scripts/)
- `validate-no-fakes.sh` — PostToolUse hook, catches all 6 known fakes
- `require-integration-test.sh` — TaskCompleted hook, requires [integration-pass]
- Both executable (chmod +x)

### Configuration
- `.claude/settings.json` — Hooks configured, MCP servers enabled, team mode ON
- `docs/file-ownership.md` — Complete ownership table
- `docs/phase-gates/` — Directory created for phase gate reports
- `CLAUDE.md` — Updated with Absolute Rules, Agent Team Architecture, 6 Known Fakes table

## Hook Verification Results
- stealth_stop_manager.py: BLOCKED (atr_defaults detected) ✅
- ml_prediction.py: BLOCKED (confidence=0.75, score=0.5+features) ✅
- risk_overseer.py: BLOCKED (correlation=0.2, VaR=0.02*balance) ✅

## Spawn Prompt (for Claude Code)
Ready at: CLAUDE.md "Agent Team Architecture" section
Start with Phase 1 Week 1: ATR fix + position sizing cap + seasonality filter
