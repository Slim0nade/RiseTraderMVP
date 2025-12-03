"""Create agent system tables for Feature 005.

Creates 7 tables for the multi-agent trading system:
1. strategy_teams - Strategy team management (11 agents per symbol)
2. agents - Agent configuration and state
3. model_configurations - Versioned LLM/RL configs
4. rl_training_runs - RL training experiment tracking
5. portfolio_allocations - Capital allocation management
6. mcp_tools - MCP tool registry
7. decision_log - Agent decision tracking (TimescaleDB hypertable)

Revision ID: 010
Revises: 009
Create Date: 2025-12-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create strategy_teams table
    op.create_table(
        'strategy_teams',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique strategy team identifier'),
        sa.Column('team_name', sa.String(100), nullable=False, unique=True,
                  comment="Unique team name (e.g., 'team-gold-001')"),
        sa.Column('display_name', sa.String(200), nullable=False,
                  comment="Human-readable display name"),
        sa.Column('symbol', sa.String(20), nullable=False,
                  comment="Trading symbol (e.g., 'Gold', 'CrudeOIL')"),
        sa.Column('asset_class', sa.String(50), nullable=False,
                  comment="Asset class (e.g., 'commodity', 'forex')"),
        sa.Column('strategy_type', sa.String(50), nullable=False,
                  server_default='multi_agent_autonomous',
                  comment='Strategy type'),
        sa.Column('trading_sessions', JSON, nullable=False,
                  comment='Active trading sessions'),
        sa.Column('allowed_timeframes', JSON, nullable=False,
                  comment="Timeframes (e.g., ['H1', 'H4', 'D1'])"),
        sa.Column('max_position_size_lots', sa.Float, nullable=False,
                  server_default='1.0',
                  comment='Maximum position size in lots'),
        sa.Column('max_daily_trades', sa.Integer, nullable=False,
                  server_default='5',
                  comment='Maximum trades per day'),
        sa.Column('max_open_positions', sa.Integer, nullable=False,
                  server_default='3',
                  comment='Maximum concurrent open positions'),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='true',
                  comment='Whether team is actively trading'),
        sa.Column('is_paper_trading', sa.Boolean, nullable=False,
                  server_default='true',
                  comment='Whether team is in paper trading mode'),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp when team was activated'),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp when team was deactivated'),
        sa.Column('agent_count', sa.Integer, nullable=False,
                  server_default='11',
                  comment='Number of agents in this team'),
        sa.Column('agent_composition', JSON, nullable=False,
                  comment='Agent composition metadata'),
        sa.Column('total_trades', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Total trades executed by this team'),
        sa.Column('win_rate', sa.Float, nullable=True,
                  comment='Win rate (0.0-1.0)'),
        sa.Column('current_sharpe_ratio', sa.Float, nullable=True,
                  comment='Current Sharpe ratio'),
        sa.Column('current_drawdown_pct', sa.Float, nullable=True,
                  comment='Current drawdown percentage'),
        sa.Column('created_by', sa.String(100), nullable=False,
                  server_default='system',
                  comment='User or system that created this team'),
        sa.Column('notes', sa.Text, nullable=True,
                  comment='Team notes and configuration details'),
        sa.Column('tags', JSON, nullable=True,
                  comment='Custom tags'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        comment='Strategy teams with 11 agents per symbol'
    )

    # Indexes for strategy_teams
    op.create_index('ix_strategy_teams_team_name', 'strategy_teams', ['team_name'])
    op.create_index('ix_strategy_teams_symbol', 'strategy_teams', ['symbol'])
    op.create_index('ix_strategy_teams_is_active', 'strategy_teams', ['is_active'])

    # 2. Create agents table
    op.create_table(
        'agents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique agent identifier'),
        sa.Column('name', sa.String(100), nullable=False,
                  comment="Human-readable agent name"),
        sa.Column('agent_type', sa.String(50), nullable=False,
                  comment="Agent type (e.g., 'technical_analyst', 'position_sizing')"),
        sa.Column('layer', sa.String(20), nullable=False,
                  comment='Agent layer: analysis, debate, decision, execution, supervisory'),
        sa.Column('strategy_team_id', UUID(as_uuid=True), nullable=True,
                  comment='FK to strategy_teams table'),
        sa.Column('llm_provider', sa.String(50), nullable=False,
                  server_default='ollama',
                  comment='LLM provider: ollama, openai, anthropic'),
        sa.Column('llm_model', sa.String(100), nullable=False,
                  comment="Model name (e.g., 'qwen2.5:14b')"),
        sa.Column('llm_tier', sa.String(20), nullable=False,
                  server_default='quick_think',
                  comment='LLM tier: quick_think, deep_think'),
        sa.Column('temperature', sa.Float, nullable=False,
                  server_default='0.1',
                  comment='LLM temperature (0.0-1.0)'),
        sa.Column('max_tokens', sa.Integer, nullable=False,
                  server_default='500',
                  comment='Maximum tokens per LLM response'),
        sa.Column('rl_enabled', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether this agent uses RL'),
        sa.Column('rl_algorithm', sa.String(20), nullable=True,
                  comment='RL algorithm: ppo, sac'),
        sa.Column('rl_model_registry_uri', sa.String(500), nullable=True,
                  comment='MLflow model URI'),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='true',
                  comment='Whether agent is actively processing'),
        sa.Column('state', sa.String(20), nullable=False,
                  server_default='idle',
                  comment='Current state: idle, processing, error, paused'),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp of last activity'),
        sa.Column('config_overrides', JSON, nullable=True,
                  comment='Agent-specific config overrides'),
        sa.Column('total_decisions', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Total decisions made by this agent'),
        sa.Column('avg_decision_time_ms', sa.Float, nullable=True,
                  comment='Average decision latency in milliseconds'),
        sa.Column('error_count', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Total errors encountered'),
        sa.Column('last_error_message', sa.Text, nullable=True,
                  comment='Most recent error message'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        comment='Agent configuration and state for multi-agent system'
    )

    # Indexes for agents
    op.create_index('ix_agents_agent_type', 'agents', ['agent_type'])
    op.create_index('ix_agents_layer', 'agents', ['layer'])
    op.create_index('ix_agents_strategy_team_id', 'agents', ['strategy_team_id'])
    op.create_index('ix_agents_is_active', 'agents', ['is_active'])

    # 3. Create model_configurations table
    op.create_table(
        'model_configurations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique configuration identifier'),
        sa.Column('config_name', sa.String(100), nullable=False,
                  comment='Human-readable config name'),
        sa.Column('config_type', sa.String(20), nullable=False,
                  comment='Configuration type: llm, rl'),
        sa.Column('agent_type', sa.String(50), nullable=False,
                  comment='Agent type this config applies to'),
        sa.Column('version', sa.String(20), nullable=False,
                  comment='Semantic version'),
        sa.Column('llm_system_prompt', sa.Text, nullable=True,
                  comment='System prompt template for LLM agent'),
        sa.Column('llm_user_prompt_template', sa.Text, nullable=True,
                  comment='User prompt template'),
        sa.Column('llm_tools', JSON, nullable=True,
                  comment='MCP tool definitions'),
        sa.Column('llm_parameters', JSON, nullable=True,
                  comment='LLM parameters'),
        sa.Column('rl_reward_function', JSON, nullable=True,
                  comment='Reward function config'),
        sa.Column('rl_action_space', JSON, nullable=True,
                  comment='Action space definition'),
        sa.Column('rl_observation_space', JSON, nullable=True,
                  comment='Observation space definition'),
        sa.Column('rl_environment_params', JSON, nullable=True,
                  comment='Environment parameters'),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether this config is currently active'),
        sa.Column('is_default', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether this is the default config'),
        sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp when config was deployed'),
        sa.Column('ab_test_group', sa.String(50), nullable=True,
                  comment='A/B test group identifier'),
        sa.Column('ab_test_allocation_pct', sa.Integer, nullable=True,
                  comment='Traffic allocation percentage for A/B test'),
        sa.Column('performance_metrics', JSON, nullable=True,
                  comment='Performance metrics for this config'),
        sa.Column('created_by', sa.String(100), nullable=False,
                  server_default='system',
                  comment='User or system that created this config'),
        sa.Column('notes', sa.Text, nullable=True,
                  comment='Configuration notes and change log'),
        sa.Column('tags', JSON, nullable=True,
                  comment='Custom tags for organization'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        comment='Versioned agent model configurations (LLM and RL)'
    )

    # Indexes for model_configurations
    op.create_index('ix_model_configurations_config_name', 'model_configurations', ['config_name'])
    op.create_index('ix_model_configurations_config_type', 'model_configurations', ['config_type'])
    op.create_index('ix_model_configurations_agent_type', 'model_configurations', ['agent_type'])
    op.create_index('ix_model_configurations_is_active', 'model_configurations', ['is_active'])

    # 4. Create rl_training_runs table
    op.create_table(
        'rl_training_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique training run identifier'),
        sa.Column('agent_id', UUID(as_uuid=True), nullable=False,
                  comment='FK to agents table'),
        sa.Column('agent_type', sa.String(50), nullable=False,
                  comment='Agent type (denormalized)'),
        sa.Column('strategy_team_id', UUID(as_uuid=True), nullable=True,
                  comment='FK to strategy_teams table'),
        sa.Column('mlflow_run_id', sa.String(100), nullable=False, unique=True,
                  comment='MLflow run ID'),
        sa.Column('mlflow_experiment_id', sa.String(100), nullable=False,
                  comment='MLflow experiment ID'),
        sa.Column('algorithm', sa.String(20), nullable=False,
                  comment='RL algorithm: ppo, sac'),
        sa.Column('hyperparameters', JSON, nullable=False,
                  comment='Training hyperparameters'),
        sa.Column('train_start_date', sa.DateTime(timezone=True), nullable=False,
                  comment='Training data start date'),
        sa.Column('train_end_date', sa.DateTime(timezone=True), nullable=False,
                  comment='Training data end date'),
        sa.Column('test_start_date', sa.DateTime(timezone=True), nullable=False,
                  comment='Out-of-sample test data start date'),
        sa.Column('test_end_date', sa.DateTime(timezone=True), nullable=False,
                  comment='Out-of-sample test data end date'),
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='running',
                  comment='Status: running, completed, failed, cancelled'),
        sa.Column('total_timesteps', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Total training timesteps'),
        sa.Column('current_timestep', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Current training timestep'),
        sa.Column('training_duration_seconds', sa.Integer, nullable=True,
                  comment='Total training duration in seconds'),
        sa.Column('train_mean_reward', sa.Float, nullable=True,
                  comment='Mean episodic reward on training data'),
        sa.Column('train_sharpe_ratio', sa.Float, nullable=True,
                  comment='Sharpe ratio on training data'),
        sa.Column('train_max_drawdown', sa.Float, nullable=True,
                  comment='Maximum drawdown on training data'),
        sa.Column('test_mean_reward', sa.Float, nullable=True,
                  comment='Mean episodic reward on OOS test data'),
        sa.Column('test_sharpe_ratio', sa.Float, nullable=True,
                  comment='Sharpe ratio on OOS test data (MUST be >1.2)'),
        sa.Column('test_max_drawdown', sa.Float, nullable=True,
                  comment='Maximum drawdown on OOS test data'),
        sa.Column('test_win_rate', sa.Float, nullable=True,
                  comment='Win rate on OOS test data'),
        sa.Column('passed_validation', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether model passed OOS Sharpe >1.2 threshold'),
        sa.Column('model_registry_uri', sa.String(500), nullable=True,
                  comment='MLflow model registry URI if promoted'),
        sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp when model was deployed'),
        sa.Column('error_message', sa.Text, nullable=True,
                  comment='Error message if training failed'),
        sa.Column('triggered_by', sa.String(100), nullable=False,
                  server_default='manual',
                  comment='Who/what triggered training'),
        sa.Column('notes', sa.Text, nullable=True,
                  comment='Training notes and observations'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        comment='RL training experiment tracking with MLflow integration'
    )

    # Indexes for rl_training_runs
    op.create_index('ix_rl_training_runs_agent_id', 'rl_training_runs', ['agent_id'])
    op.create_index('ix_rl_training_runs_agent_type', 'rl_training_runs', ['agent_type'])
    op.create_index('ix_rl_training_runs_strategy_team_id', 'rl_training_runs', ['strategy_team_id'])
    op.create_index('ix_rl_training_runs_mlflow_run_id', 'rl_training_runs', ['mlflow_run_id'])
    op.create_index('ix_rl_training_runs_mlflow_experiment_id', 'rl_training_runs', ['mlflow_experiment_id'])
    op.create_index('ix_rl_training_runs_status', 'rl_training_runs', ['status'])
    op.create_index('ix_rl_training_runs_test_sharpe_ratio', 'rl_training_runs', ['test_sharpe_ratio'])
    op.create_index('ix_rl_training_runs_passed_validation', 'rl_training_runs', ['passed_validation'])

    # 5. Create portfolio_allocations table
    op.create_table(
        'portfolio_allocations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique allocation identifier'),
        sa.Column('allocation_name', sa.String(100), nullable=False,
                  comment='Human-readable allocation name'),
        sa.Column('strategy_team_id', UUID(as_uuid=True), nullable=True,
                  comment='FK to strategy_teams table (NULL for reserve)'),
        sa.Column('symbol', sa.String(20), nullable=True,
                  comment='Trading symbol (NULL for reserve)'),
        sa.Column('allocated_capital_usd', sa.Float, nullable=False,
                  comment='Capital allocated in USD'),
        sa.Column('allocated_percentage', sa.Float, nullable=False,
                  comment='Percentage of total portfolio'),
        sa.Column('total_portfolio_capital_usd', sa.Float, nullable=False,
                  comment='Total portfolio capital at allocation time'),
        sa.Column('max_drawdown_limit', sa.Float, nullable=True,
                  comment='Maximum allowed drawdown'),
        sa.Column('max_leverage', sa.Float, nullable=True,
                  server_default='1.0',
                  comment='Maximum leverage allowed'),
        sa.Column('max_correlated_exposure_pct', sa.Float, nullable=True,
                  comment='Maximum combined exposure to correlated instruments'),
        sa.Column('allocation_mode', sa.String(20), nullable=False,
                  server_default='static',
                  comment='Allocation mode: static, dynamic'),
        sa.Column('rebalance_frequency', sa.String(20), nullable=False,
                  server_default='manual',
                  comment='Rebalancing frequency'),
        sa.Column('next_rebalance_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Next scheduled rebalancing timestamp'),
        sa.Column('last_rebalanced_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Last rebalancing timestamp'),
        sa.Column('sharpe_threshold', sa.Float, nullable=True,
                  comment='Increase allocation if Sharpe ratio > threshold'),
        sa.Column('drawdown_threshold', sa.Float, nullable=True,
                  comment='Reduce allocation if drawdown > threshold'),
        sa.Column('correlation_threshold', sa.Float, nullable=True,
                  comment='Reduce allocation if correlation > threshold'),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='true',
                  comment='Whether this allocation is currently active'),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False,
                  comment='Effective start date'),
        sa.Column('effective_until', sa.DateTime(timezone=True), nullable=True,
                  comment='Effective end date (NULL = indefinite)'),
        sa.Column('current_capital_usd', sa.Float, nullable=True,
                  comment='Current capital value (allocated + P&L)'),
        sa.Column('realized_pnl_usd', sa.Float, nullable=True,
                  comment='Realized P&L for this allocation'),
        sa.Column('unrealized_pnl_usd', sa.Float, nullable=True,
                  comment='Unrealized P&L for this allocation'),
        sa.Column('current_drawdown_pct', sa.Float, nullable=True,
                  comment='Current drawdown percentage'),
        sa.Column('created_by', sa.String(100), nullable=False,
                  server_default='system',
                  comment='User or system that created this allocation'),
        sa.Column('notes', sa.Text, nullable=True,
                  comment='Allocation notes and rationale'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        comment='Portfolio capital allocation management (static and dynamic)'
    )

    # Indexes for portfolio_allocations
    op.create_index('ix_portfolio_allocations_strategy_team_id', 'portfolio_allocations', ['strategy_team_id'])
    op.create_index('ix_portfolio_allocations_symbol', 'portfolio_allocations', ['symbol'])
    op.create_index('ix_portfolio_allocations_allocation_mode', 'portfolio_allocations', ['allocation_mode'])
    op.create_index('ix_portfolio_allocations_is_active', 'portfolio_allocations', ['is_active'])
    op.create_index('ix_portfolio_allocations_effective_from', 'portfolio_allocations', ['effective_from'])
    op.create_index('ix_portfolio_allocations_next_rebalance_at', 'portfolio_allocations', ['next_rebalance_at'])

    # 6. Create mcp_tools table
    op.create_table(
        'mcp_tools',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique tool identifier'),
        sa.Column('tool_name', sa.String(100), nullable=False, unique=True,
                  comment='Unique tool name'),
        sa.Column('display_name', sa.String(200), nullable=False,
                  comment='Human-readable display name'),
        sa.Column('tool_type', sa.String(50), nullable=False,
                  comment='Tool category'),
        sa.Column('description', sa.Text, nullable=False,
                  comment='Tool description for LLM'),
        sa.Column('input_schema', JSON, nullable=False,
                  comment='JSON schema for tool input'),
        sa.Column('output_schema', JSON, nullable=False,
                  comment='JSON schema for tool output'),
        sa.Column('implementation_path', sa.String(500), nullable=False,
                  comment='Python import path'),
        sa.Column('version', sa.String(20), nullable=False,
                  server_default='1.0.0',
                  comment='Tool version'),
        sa.Column('allowed_agent_types', JSON, nullable=False,
                  comment='List of agent types allowed to use this tool'),
        sa.Column('requires_approval', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether tool usage requires human approval'),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='true',
                  comment='Whether tool is currently available'),
        sa.Column('is_beta', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether tool is in beta testing'),
        sa.Column('total_calls', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Total number of tool calls'),
        sa.Column('successful_calls', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Number of successful tool calls'),
        sa.Column('avg_execution_time_ms', sa.Float, nullable=True,
                  comment='Average execution time in milliseconds'),
        sa.Column('last_called_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp of last tool call'),
        sa.Column('error_count', sa.Integer, nullable=False,
                  server_default='0',
                  comment='Total errors encountered'),
        sa.Column('last_error_message', sa.Text, nullable=True,
                  comment='Most recent error message'),
        sa.Column('config', JSON, nullable=True,
                  comment='Tool-specific configuration'),
        sa.Column('rate_limit_per_minute', sa.Integer, nullable=True,
                  comment='Rate limit for this tool (calls per minute)'),
        sa.Column('timeout_seconds', sa.Integer, nullable=True,
                  server_default='30',
                  comment='Tool execution timeout in seconds'),
        sa.Column('created_by', sa.String(100), nullable=False,
                  server_default='system',
                  comment='User or system that created this tool'),
        sa.Column('notes', sa.Text, nullable=True,
                  comment='Tool notes and usage guidelines'),
        sa.Column('documentation_url', sa.String(500), nullable=True,
                  comment='URL to tool documentation'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        comment='MCP tool registry for agent capabilities'
    )

    # Indexes for mcp_tools
    op.create_index('ix_mcp_tools_tool_name', 'mcp_tools', ['tool_name'])
    op.create_index('ix_mcp_tools_tool_type', 'mcp_tools', ['tool_type'])
    op.create_index('ix_mcp_tools_is_active', 'mcp_tools', ['is_active'])

    # 7. Create decision_log table (will be converted to TimescaleDB hypertable in next migration)
    op.create_table(
        'decision_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique decision identifier'),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False,
                  comment='Decision timestamp (hypertable partition key)'),
        sa.Column('agent_id', UUID(as_uuid=True), nullable=False,
                  comment='FK to agents table'),
        sa.Column('agent_type', sa.String(50), nullable=False,
                  comment='Agent type (denormalized)'),
        sa.Column('strategy_team_id', UUID(as_uuid=True), nullable=True,
                  comment='FK to strategy_teams table'),
        sa.Column('symbol', sa.String(20), nullable=True,
                  comment='Trading symbol'),
        sa.Column('timeframe', sa.String(10), nullable=True,
                  comment='Chart timeframe'),
        sa.Column('input_data', JSON, nullable=False,
                  comment='Input data provided to agent'),
        sa.Column('reasoning', sa.Text, nullable=True,
                  comment="Agent's chain-of-thought reasoning"),
        sa.Column('decision_type', sa.String(50), nullable=False,
                  comment='Decision type'),
        sa.Column('decision_data', JSON, nullable=False,
                  comment='Decision output'),
        sa.Column('confidence', sa.Float, nullable=True,
                  comment='Agent confidence score (0.0-1.0)'),
        sa.Column('was_executed', sa.Boolean, nullable=False,
                  server_default='false',
                  comment='Whether decision led to actual trade execution'),
        sa.Column('execution_result', JSON, nullable=True,
                  comment='Execution outcome if executed'),
        sa.Column('pnl_impact', sa.Float, nullable=True,
                  comment='P&L impact of this decision (USD)'),
        sa.Column('sharpe_impact', sa.Float, nullable=True,
                  comment='Impact on portfolio Sharpe ratio'),
        sa.Column('decision_latency_ms', sa.Integer, nullable=True,
                  comment='Time taken for agent to make decision (ms)'),
        sa.Column('model_version', sa.String(100), nullable=True,
                  comment='RL model version if RL-enabled agent'),
        comment='Agent decision log - TimescaleDB hypertable with 90-day retention'
    )

    # Indexes for decision_log (composite indexes for time-series queries)
    op.create_index('ix_decision_log_decided_at', 'decision_log', ['decided_at'])
    op.create_index('ix_decision_log_agent_id', 'decision_log', ['agent_id'])
    op.create_index('ix_decision_log_agent_type', 'decision_log', ['agent_type'])
    op.create_index('ix_decision_log_strategy_team_id', 'decision_log', ['strategy_team_id'])
    op.create_index('ix_decision_log_symbol', 'decision_log', ['symbol'])
    op.create_index('ix_decision_log_decision_type', 'decision_log', ['decision_type'])
    op.create_index('ix_decision_log_agent_time', 'decision_log', ['agent_id', 'decided_at'])
    op.create_index('ix_decision_log_symbol_time', 'decision_log', ['symbol', 'decided_at'])
    op.create_index('ix_decision_log_team_time', 'decision_log', ['strategy_team_id', 'decided_at'])
    op.create_index('ix_decision_log_type_time', 'decision_log', ['decision_type', 'decided_at'])


def downgrade():
    # Drop tables in reverse order to respect dependencies
    op.drop_table('decision_log')
    op.drop_table('mcp_tools')
    op.drop_table('portfolio_allocations')
    op.drop_table('rl_training_runs')
    op.drop_table('model_configurations')
    op.drop_table('agents')
    op.drop_table('strategy_teams')
