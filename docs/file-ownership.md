# File Ownership Map

This document defines which agent owns which files and directories. Only the owning agent may edit files in their domain. Cross-cutting changes require `lead` approval + `reviewer` sign-off.

## Ownership Table

### quant-dev (Sonnet) — Strategies & Agent Logic
```
src/strategies/                         # All trading strategy implementations
src/strategies/spreads/                 # Spread strategies (shared with spread-builder in Phase 2)
src/strategies/agriculture/             # Agricultural strategies (shared with spread-builder in Phase 2)
src/strategies/carry/                   # Carry trade strategies (shared with spread-builder in Phase 2)
src/agents/                             # All agent logic
  src/agents/data_ml/                   # ML prediction, regime detection, market data agents
  src/agents/execution/                 # Signal generator, risk manager, execution agents
  src/agents/supervisory/               # Performance monitor, risk overseer, strategy optimizer
  src/agents/decision/                  # Fund manager, position sizing, stop loss, take profit agents
  src/agents/teams/                     # Trading pipeline, risk debate team
  src/agents/tools/                     # MCP tools (Kelly, forecast)
  src/agents/schemas/                   # Pydantic schemas for agent communication
  src/agents/utils/                     # Agent utilities (metrics, logging)
src/ml/                                 # ML model code
  src/ml/models/                        # Model architectures (XGBoost, LSTM, FEDformer)
  src/ml/data/                          # Data loaders and preprocessors
  src/ml/training/                      # Training infrastructure
src/services/backtesting/               # Backtest engine (SyntheticEngine, strategies)
  src/services/backtesting/synthetic_engine.py
  src/services/backtesting/value_area_strategy.py
  src/services/backtesting/crude_oil_v3_strategy.py
  src/services/backtesting/ma_crossover_strategy.py
  # etc.
```

### risk-eng (Sonnet) — Risk Infrastructure
```
src/services/stealth_stop_manager.py    # 1,320-line stealth stop 4-layer protection
src/utils/atr_calculator.py             # Wilder's ATR calculation
src/risk/                               # Risk models (VaR, correlation, position limits)
src/execution/                          # Order execution and MT4 interaction
config/stealth_stops.yaml               # Stealth stop configuration
config/stealth_stops.json               # Stealth stop JSON config
```

### mcp-verifier (Sonnet) — Tests & Validation Scripts
```
tests/                                  # ALL test files
  tests/unit/                           # Pure math validation tests
  tests/integration/                    # Real-data integration tests
  tests/e2e/                            # End-to-end pipeline tests
scripts/validate-no-fakes.sh            # PostToolUse quality gate
scripts/require-integration-test.sh     # TaskCompleted quality gate
scripts/                                # Other validation/deployment scripts
```

### lead (Opus) — Documentation & Configuration
```
docs/                                   # All documentation
  docs/file-ownership.md                # This file
  docs/phase-gates/                     # Phase gate reports
CLAUDE.md                               # Project rules (auto-loaded by all agents)
.claude/                                # Agent configurations
  .claude/settings.json                 # Project settings with hooks
  .claude/agents/                       # Agent definition files
```

### reviewer (Sonnet) — READ-ONLY
```
* (all directories)                     # Read-only access to everything
                                        # Reviews but never edits
```

### spread-builder (Phase 2 Only) — Spread Strategies
```
src/strategies/spreads/                 # Crack spread, WTI-Brent spread
src/strategies/agriculture/             # WHEAT, CORN seasonal strategies
src/strategies/carry/                   # GBPJPY carry trade
```
Note: These directories are shared with quant-dev. Coordinate via lead.

### ml-trainer (Phase 4 Only) — ML Models
```
src/ml/models/                          # Trained model artifacts
src/agents/data_ml/ml_prediction.py     # MLPredictionAgent (replacing fakes)
```
Note: Works in git worktree isolation. Merges require reviewer + mcp-verifier approval.

## Conflict Resolution

1. If two agents need to edit the same file, **lead** decides who owns the change.
2. If a change spans multiple ownership domains, split it into separate commits per domain.
3. **reviewer** can request changes to any file but must delegate the actual edit to the owning agent.
4. Emergency fixes (production outage) bypass ownership — but must be reviewed retroactively.

## Shared Resources (Any Agent Can Read)

These files are read by all agents but owned by specific agents:
- `CLAUDE.md` — owned by lead, read by all
- `config/stealth_stops.yaml` — owned by risk-eng, referenced by quant-dev strategies
- `.serena/memories/` — shared context, writeable by lead and mcp-verifier
- `requirements.txt` — owned by lead, PRs from any agent
