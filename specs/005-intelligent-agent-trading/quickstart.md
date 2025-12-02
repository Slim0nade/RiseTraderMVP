# Quickstart Guide: Intelligent Multi-Agent Trading System

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Created**: 2025-12-01 | **Last Updated**: 2025-12-01

## Overview

This guide explains how to run the intelligent multi-agent trading system for RiseTrader. The system consists of 12 specialized agents organized in 5 layers, coordinated by an MCP server, with reinforcement learning training capabilities.

**Prerequisites**:
- Feature 001 (MT4 Integration) completed and running
- Feature 003 (ML Forecasting Pipeline) completed with trained models
- Docker and Docker Compose installed
- PostgreSQL 15+ and Redis 7+ running
- Python 3.11+ installed

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         MCP Server                               │
│                   (Event Routing & Coordination)                 │
└────────────┬───────────────────────────────────┬─────────────────┘
             │                                   │
    ┌────────▼─────────┐                ┌───────▼────────┐
    │  Analysis Layer  │                │  Debate Layer  │
    │  - Technical     │                │  - Bull        │
    │  - Fundamental   │───────────────▶│  - Bear        │
    │  - Sentiment     │                └───────┬────────┘
    └──────────────────┘                        │
                                         ┌──────▼───────┐
                                         │Decision Layer│
                                         │- Trade Intent│
                    ┌────────────────────│- Position    │
                    │                    │- Stop Loss   │
                    │                    │- Take Profit │
                    │                    └──────┬───────┘
                    │                           │
             ┌──────▼──────────┐       ┌───────▼────────┐
             │Execution Layer  │       │ Supervisory    │
             │- Execution      │◀──────│- Risk Overseer │
             │- Monitor        │       │                │
             └─────────────────┘       └────────────────┘
                    │
                    ▼
              ┌──────────┐
              │ MT4/ZMQ  │
              └──────────┘
```

## Quick Start (Development Mode)

### 1. Environment Setup

```bash
# Navigate to project root
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP

# Activate virtual environment
source venv/bin/activate

# Install agent system dependencies
pip install -r requirements.txt

# Verify additional dependencies for agents
pip install litellm stable-baselines3 gymnasium mlflow
```

### 2. Configuration

Create agent configuration file:

```bash
# Create agents config directory if not exists
mkdir -p config/agents

# Copy template (will be created in implementation)
cp config/agents/agents.yaml.template config/agents/agents.yaml

# Edit configuration
vim config/agents/agents.yaml
```

**Minimal `agents.yaml` configuration**:

```yaml
# config/agents/agents.yaml

# Portfolio Allocation
portfolio:
  total_capital_usd: 100000.0
  reserve_percentage: 20.0
  allocations:
    - symbol: "Gold"
      allocated_capital_usd: 40000.0
      allocated_percentage: 40.0
    - symbol: "CrudeOIL"
      allocated_capital_usd: 40000.0
      allocated_percentage: 40.0

# Strategy Teams (one per instrument)
strategy_teams:
  - team_id: "team-gold-001"
    team_name: "Gold Swing Strategy"
    symbol: "Gold"
    strategy_type: "SWING"
    is_active: true
    enabled_layers: ["analysis", "debate", "decision", "execution", "supervisory"]

  - team_id: "team-crude-001"
    team_name: "Crude Oil Swing Strategy"
    symbol: "CrudeOIL"
    strategy_type: "SWING"
    is_active: true
    enabled_layers: ["analysis", "debate", "decision", "execution", "supervisory"]

# LLM Configuration (Dual-LLM Strategy)
llm:
  quick_think:
    provider: "ollama"
    model: "qwen2.5:14b"
    api_base: "http://localhost:11434"
    temperature: 0.1
    max_tokens: 500

  deep_think:
    provider: "ollama"
    model: "deepseek-r1:14b"
    api_base: "http://localhost:11434"
    temperature: 0.7
    max_tokens: 2000

# Agent Assignments (per strategy team)
agent_templates:
  analysis:
    technical_analyst:
      llm_tier: "quick_think"
      max_position_size_pct: 3.0

    fundamental_analyst:
      llm_tier: "quick_think"
      max_position_size_pct: 3.0

    sentiment_analyst:
      llm_tier: "quick_think"
      max_position_size_pct: 3.0

  debate:
    bull_researcher:
      llm_tier: "deep_think"

    bear_researcher:
      llm_tier: "deep_think"

  decision:
    trade_decision:
      llm_tier: "deep_think"
      min_conviction: 0.6

    position_sizing:
      llm_tier: "deep_think"
      max_position_size_pct: 3.0
      rl_enabled: false  # Enable after training

    stop_loss:
      llm_tier: "quick_think"
      max_stop_distance_pct: 5.0
      rl_enabled: false

    take_profit:
      llm_tier: "quick_think"
      min_risk_reward_ratio: 1.5
      rl_enabled: false

  execution:
    execution:
      llm_tier: "quick_think"

    position_monitor:
      llm_tier: "quick_think"

    risk_overseer:
      llm_tier: "deep_think"
      max_daily_loss: 5000.0
      max_open_positions: 3
      circuit_breaker_enabled: true

# MCP Server Configuration
mcp_server:
  host: "localhost"
  port: 7000
  redis_url: "redis://localhost:6379/0"
  circuit_breaker_threshold: 100  # events/sec

# Performance Targets
performance:
  decision_latency_target_ms:
    INTRADAY: 5000
    SWING: 30000
    POSITION: 300000
  mcp_tool_latency_target_ms: 100
  event_propagation_target_ms: 50
```

### 3. Database Migrations

Run Alembic migrations to create agent system tables:

```bash
# Generate migration for agent system tables
alembic revision --autogenerate -m "Add agent system tables (Feature 005)"

# Apply migration
alembic upgrade head

# Verify tables created
psql $DATABASE_URL -c "\dt" | grep -E "agents|decision_log|rl_training|portfolio"
```

**Expected tables**:
- `agents` - Agent configuration
- `decision_log` - TimescaleDB hypertable for decision audit trail
- `rl_training_runs` - RL training metadata
- `model_configurations` - A/B testing configurations
- `portfolio_allocations` - Capital allocation
- `strategy_teams` - Agent team assignments
- `mcp_tools` - MCP tool registry

### 4. Start Agent System

**Option A: Start All Services with Docker Compose**

```bash
# Start all services (API + MCP server + agents)
docker-compose up -d

# Check service health
docker-compose ps

# View MCP server logs
docker-compose logs -f mcp-server

# View agent logs (example: technical analyst for Gold)
docker-compose logs -f agent-technical-gold
```

**Option B: Start Manually (Development)**

```bash
# Terminal 1: Start MCP Server
python -m src.agents.coordination.mcp_server

# Terminal 2: Start Strategy Team for Gold
python scripts/agents/start_agent_system.py --symbol Gold --team-id team-gold-001

# Terminal 3: Start Strategy Team for Crude Oil
python scripts/agents/start_agent_system.py --symbol CrudeOIL --team-id team-crude-001

# Terminal 4: Monitor agent health
python scripts/agents/monitor_agents.py
```

### 5. Verify Agent System is Running

```bash
# Check agent health via API
curl http://localhost:8003/api/v1/agents/health

# Expected response:
{
  "status": "healthy",
  "total_agents": 24,  # 12 agents × 2 instruments
  "active_agents": 24,
  "strategy_teams": [
    {
      "team_id": "team-gold-001",
      "symbol": "Gold",
      "status": "active",
      "agent_count": 12
    },
    {
      "team_id": "team-crude-001",
      "symbol": "CrudeOIL",
      "status": "active",
      "agent_count": 12
    }
  ]
}

# Check MCP server status
curl http://localhost:7000/mcp/status

# Check decision log
psql $DATABASE_URL -c "SELECT COUNT(*) FROM decision_log WHERE timestamp > NOW() - INTERVAL '1 hour';"
```

## Paper Trading Mode

**IMPORTANT**: Always start in paper trading mode before live trading.

### Enable Paper Trading

```yaml
# config/agents/agents.yaml

# Add to root level
trading_mode: "PAPER"  # Options: PAPER, LIVE

# Paper trading configuration
paper_trading:
  initial_balance: 100000.0
  use_live_prices: true  # Use real market prices but simulate execution
  slippage_model: "realistic"  # Simulate realistic slippage
  commission_per_lot: 7.0  # Simulate broker commissions
```

### Start in Paper Mode

```bash
# Start agent system in paper trading mode
python scripts/agents/start_agent_system.py \
  --symbol Gold \
  --team-id team-gold-001 \
  --mode PAPER

# Monitor paper trading results
python scripts/agents/evaluate_agent_performance.py \
  --mode PAPER \
  --start-date 2025-12-01 \
  --symbol Gold
```

### Paper Trading Validation Checklist

Before switching to live trading, verify:

- [ ] At least 100 trades executed in paper mode
- [ ] Sharpe ratio > 1.5 (target from Success Criteria SC-004)
- [ ] Win rate > 55%
- [ ] No risk limit violations
- [ ] Decision latency < targets (5s INTRADAY, 30s SWING)
- [ ] No agent crashes or errors
- [ ] Position sizing within allocated capital
- [ ] Stop-loss placement > 70% structural (target from SC-005)
- [ ] Risk/reward ratio > 1.5 for all trades

## Reinforcement Learning Training

### Prerequisites for RL Training

Before training RL agents, ensure:
1. Historical market data available (2+ years)
2. ML forecasting models trained (Feature 003)
3. Backtesting environment configured
4. MLflow tracking server running

### Start RL Training

```bash
# Train Position Sizing Agent for Crude Oil
python scripts/agents/run_rl_training.py \
  --agent-type position_sizing \
  --symbol CrudeOIL \
  --algorithm sac \
  --train-start 2023-01-01 \
  --train-end 2024-12-31 \
  --validation walk_forward \
  --train-days 252 \
  --test-days 63 \
  --step-days 21

# Monitor training progress
mlflow ui --port 5000

# View training runs
open http://localhost:5000
```

**RL Training Configuration**:

```yaml
# config/agents/rl_training_config.yaml

rl_training:
  # Position Sizing Agent (SAC - continuous action)
  position_sizing:
    algorithm: "sac"
    hyperparameters:
      learning_rate: 0.0003
      gamma: 0.99
      batch_size: 256
      buffer_size: 1000000
      tau: 0.005
      train_freq: 1
      gradient_steps: 1

    reward_function:
      sharpe_weight: 0.6
      drawdown_weight: 0.3
      transaction_cost_penalty: 0.1

    validation:
      strategy: "walk_forward"
      train_days: 252
      test_days: 63
      step_days: 21
      min_sharpe_oos: 1.2  # Minimum out-of-sample Sharpe
      max_overfitting_score: 1.3  # train_sharpe / oos_sharpe

  # Stop Loss Agent (SAC - continuous action)
  stop_loss:
    algorithm: "sac"
    hyperparameters:
      learning_rate: 0.0003
      gamma: 0.95
      batch_size: 128

    reward_function:
      avoid_premature_stops_weight: 0.7
      minimize_loss_weight: 0.3

  # Take Profit Agent (SAC - continuous action)
  take_profit:
    algorithm: "sac"
    hyperparameters:
      learning_rate: 0.0003
      gamma: 0.95
      batch_size: 128

    reward_function:
      maximize_profit_weight: 0.6
      capture_moves_weight: 0.4

  # Trade Decision Agent (PPO - discrete action)
  trade_decision:
    algorithm: "ppo"
    hyperparameters:
      learning_rate: 0.0003
      gamma: 0.99
      n_steps: 2048
      batch_size: 64
      n_epochs: 10

    reward_function:
      pnl_weight: 0.5
      sharpe_weight: 0.3
      win_rate_weight: 0.2
```

### Deploy Trained Model

After training completes successfully:

```bash
# View training results
python scripts/agents/evaluate_rl_training.py \
  --run-id <mlflow_run_id> \
  --show-metrics

# If validation metrics pass, deploy to staging
python scripts/agents/deploy_rl_model.py \
  --run-id <mlflow_run_id> \
  --stage Staging \
  --agent-type position_sizing \
  --symbol CrudeOIL

# Test in paper trading with RL model
python scripts/agents/start_agent_system.py \
  --symbol CrudeOIL \
  --team-id team-crude-001 \
  --mode PAPER \
  --rl-enabled

# Monitor for 100+ trades, then promote to production
python scripts/agents/deploy_rl_model.py \
  --run-id <mlflow_run_id> \
  --stage Production \
  --agent-type position_sizing \
  --symbol CrudeOIL
```

## A/B Testing

### Setup A/B Test

To compare RL-trained model vs rule-based baseline:

```bash
# Create A/B test experiment
python scripts/agents/create_ab_test.py \
  --experiment-name "position_sizing_sac_vs_kelly_crude" \
  --agent-type position_sizing \
  --symbol CrudeOIL \
  --variant-a rl_trained \
  --variant-a-model-id <mlflow_run_id> \
  --variant-b rule_based \
  --traffic-split 50/50 \
  --min-sample-size 200
```

**A/B Test Configuration**:

```yaml
# config/agents/ab_tests.yaml

ab_tests:
  - experiment_name: "position_sizing_sac_vs_kelly_crude"
    agent_type: "position_sizing"
    symbol: "CrudeOIL"

    variants:
      - variant_name: "A"
        model_source: "rl_trained"
        rl_training_run_id: "<mlflow_run_id>"
        traffic_percentage: 50.0
        is_active: true

      - variant_name: "control"
        model_source: "rule_based"
        rule_based_config:
          method: "kelly_criterion"
          max_kelly_fraction: 0.25
        traffic_percentage: 50.0
        is_active: true

    experiment_start_date: "2025-12-01T00:00:00Z"
    min_sample_size: 200
    statistical_significance_threshold: 0.05
```

### Monitor A/B Test

```bash
# View A/B test results
python scripts/agents/view_ab_test_results.py \
  --experiment-name "position_sizing_sac_vs_kelly_crude"

# Expected output:
# Experiment: position_sizing_sac_vs_kelly_crude
# Status: RUNNING
#
# Variant A (RL Trained):
#   Trades: 245
#   Sharpe: 1.68
#   Win Rate: 67%
#   Avg P&L: $142.80
#   Max DD: 14%
#
# Control (Kelly):
#   Trades: 238
#   Sharpe: 1.45
#   Win Rate: 62%
#   Avg P&L: $125.30
#   Max DD: 18%
#
# Statistical Test:
#   p-value: 0.018 ✓ (< 0.05)
#   t-statistic: 2.62
#   Conclusion: Variant A significantly better
#
# Recommendation: PROMOTE VARIANT A

# Promote winner
python scripts/agents/promote_ab_test_winner.py \
  --experiment-name "position_sizing_sac_vs_kelly_crude" \
  --winner A
```

## Monitoring & Debugging

### View Decision Logs

```bash
# Query recent decisions for Gold
psql $DATABASE_URL -c "
  SELECT
    timestamp,
    agent_type,
    decision_type,
    decision,
    confidence,
    decision_latency_ms,
    outcome,
    pnl
  FROM decision_log
  WHERE symbol = 'Gold'
    AND timestamp > NOW() - INTERVAL '1 hour'
  ORDER BY timestamp DESC
  LIMIT 20;
"

# View full decision pipeline for a correlation_id
psql $DATABASE_URL -c "
  SELECT
    timestamp,
    agent_type,
    decision_type,
    decision,
    rationale
  FROM decision_log
  WHERE correlation_id = '<correlation_id>'
  ORDER BY timestamp;
"
```

### Agent Performance Analytics

```bash
# Agent performance summary (last 7 days)
psql $DATABASE_URL -c "
  SELECT
    agent_type,
    symbol,
    COUNT(*) AS total_decisions,
    AVG(decision_latency_ms) AS avg_latency_ms,
    COUNT(CASE WHEN outcome = 'success' THEN 1 END)::float / COUNT(*) AS success_rate,
    SUM(pnl) AS total_pnl,
    SUM(llm_cost_usd) AS total_llm_cost
  FROM decision_log
  WHERE timestamp > NOW() - INTERVAL '7 days'
    AND decision_type IN ('trade_intent', 'position_size', 'stop_loss', 'take_profit')
  GROUP BY agent_type, symbol
  ORDER BY total_pnl DESC;
"
```

### LLM Cost Tracking

```bash
# LLM cost analysis
psql $DATABASE_URL -c "
  SELECT
    agent_type,
    symbol,
    SUM(llm_cost_usd) AS total_cost,
    AVG(llm_calls) AS avg_llm_calls,
    COUNT(*) AS decisions,
    SUM(llm_cost_usd) / COUNT(*) AS cost_per_decision
  FROM decision_log
  WHERE timestamp > NOW() - INTERVAL '7 days'
  GROUP BY agent_type, symbol
  ORDER BY total_cost DESC;
"
```

### Prometheus Metrics

Key metrics exposed at `http://localhost:8003/metrics`:

```prometheus
# Agent decision metrics
agent_decision_total{agent_type="position_sizing", symbol="CrudeOIL", decision="calculated"}
agent_decision_duration_seconds{agent_type="position_sizing", symbol="CrudeOIL"}
agent_decision_success_total{agent_type="position_sizing", symbol="CrudeOIL"}

# MCP tool metrics
mcp_tool_call_duration_seconds{tool_name="get_tcn_forecast", symbol="CrudeOIL"}
mcp_tool_cache_hit_total{tool_name="get_tcn_forecast"}
mcp_tool_error_total{tool_name="get_tcn_forecast"}

# Event bus metrics
agent_event_published_total{event_type="trade_intent_generated", symbol="CrudeOIL"}
agent_event_consumed_total{event_type="trade_intent_generated", symbol="CrudeOIL"}
agent_event_processing_duration_seconds{event_type="trade_intent_generated"}

# RL training metrics
rl_training_duration_seconds{agent_type="position_sizing", algorithm="sac"}
rl_training_reward{agent_type="position_sizing", symbol="CrudeOIL"}
```

### Grafana Dashboards

Import pre-configured dashboards:

```bash
# Import agent system dashboards
curl -X POST http://admin:admin@localhost:3001/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @config/monitoring/grafana/agent_system_dashboard.json
```

Dashboard URLs:
- Agent Performance: http://localhost:3001/d/agent-performance
- Decision Pipeline: http://localhost:3001/d/decision-pipeline
- RL Training: http://localhost:3001/d/rl-training
- Cost Analysis: http://localhost:3001/d/llm-cost-analysis

## Common Issues & Troubleshooting

### Agent Not Starting

```bash
# Check agent logs
docker-compose logs agent-<agent_type>-<symbol>

# Common issues:
# 1. Missing LLM model
ollama pull qwen2.5:14b
ollama pull deepseek-r1:14b

# 2. Database migration not applied
alembic upgrade head

# 3. MCP server not running
docker-compose ps mcp-server
```

### High Decision Latency

```bash
# Check agent decision latency
psql $DATABASE_URL -c "
  SELECT
    agent_type,
    symbol,
    AVG(decision_latency_ms) AS avg_latency,
    MAX(decision_latency_ms) AS max_latency,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY decision_latency_ms) AS p95_latency
  FROM decision_log
  WHERE timestamp > NOW() - INTERVAL '1 hour'
  GROUP BY agent_type, symbol
  HAVING AVG(decision_latency_ms) > 5000;  -- Flag agents over 5s target
"

# Optimize:
# 1. Enable MCP tool caching
# 2. Reduce LLM max_tokens
# 3. Switch slow agents to quick_think tier
```

### MCP Tool Timeout

```bash
# Check MCP tool performance
curl http://localhost:7000/mcp/tools/stats

# Increase timeout for specific tool
# In config/ml/mcp_tools.yaml:
tools:
  get_tcn_forecast:
    timeout_ms: 200  # Increase from 100ms default
```

### RL Training Failure

```bash
# Check MLflow experiment logs
mlflow ui --port 5000
open http://localhost:5000

# Common issues:
# 1. Insufficient training data
# 2. Hyperparameters causing instability
# 3. Reward function numerical issues

# Retry with adjusted hyperparameters
python scripts/agents/run_rl_training.py \
  --agent-type position_sizing \
  --symbol CrudeOIL \
  --learning-rate 0.0001 \  # Reduce learning rate
  --batch-size 128  # Reduce batch size
```

## Next Steps

1. **Run in Paper Mode**: Validate system with 100+ trades
2. **Train RL Agents**: Start with position sizing agent
3. **A/B Testing**: Compare RL vs rule-based
4. **Deploy to Production**: Enable one instrument at a time (Gold first)
5. **Monitor & Iterate**: Use decision logs and metrics to improve

## Resources

- [Full Specification](./spec.md) - Complete feature requirements
- [Implementation Plan](./plan.md) - Development roadmap
- [Data Model](./data-model.md) - Entity schemas and relationships
- [MCP Tool Contracts](./contracts/mcp-tools.yaml) - MCP tool interfaces
- [Agent Event Schemas](./contracts/agent-events.yaml) - Inter-agent communication
- [Research Findings](./research.md) - Technical decisions and patterns

## Support

For issues or questions:
1. Check agent logs: `docker-compose logs -f <service>`
2. Query decision logs: `psql $DATABASE_URL`
3. Review Prometheus metrics: http://localhost:9090
4. View Grafana dashboards: http://localhost:3001

**Remember**: Always start in paper trading mode and validate thoroughly before live trading!
