"""Create backtesting tables

Revision ID: 002_backtesting_tables
Revises: 001_backtesting_enums
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '002_backtesting_tables'
down_revision: Union[str, None] = '001_backtesting_enums'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all backtesting tables with indexes."""

    # BacktestConfiguration table
    op.create_table(
        'backtest_configurations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('initial_capital', sa.Numeric(18, 2), nullable=False),
        sa.Column('execution_mode', sa.Enum('full_pipeline', 'synthetic_fast', name='execution_mode'), nullable=False),
        sa.Column('agent_config_ref', sa.String(255), nullable=True),
        sa.Column('slippage_pct', sa.Numeric(8, 6), nullable=False, server_default='0.001'),
        sa.Column('commission_pct', sa.Numeric(8, 6), nullable=False, server_default='0.0005'),
        sa.Column('commission_fixed', sa.Numeric(10, 2), nullable=False, server_default='0.0'),
        sa.Column('max_leverage', sa.Numeric(5, 2), nullable=False, server_default='1.0'),
        sa.Column('allow_short_selling', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('config_params', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_backtest_config_name', 'backtest_configurations', ['name'])
    op.create_index('idx_backtest_config_symbol', 'backtest_configurations', ['symbol', 'start_date', 'end_date'])

    # BacktestRun table
    op.create_table(
        'backtest_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('config_id', UUID(as_uuid=True), sa.ForeignKey('backtest_configurations.id'), nullable=False),
        sa.Column('status', sa.Enum('running', 'completed', 'failed', 'timeout', name='run_status'), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('random_seed', sa.Integer, nullable=True),
        sa.Column('total_return_pct', sa.Numeric(10, 4), nullable=True),
        sa.Column('sharpe_ratio', sa.Numeric(10, 4), nullable=True),
        sa.Column('max_drawdown_pct', sa.Numeric(10, 4), nullable=True),
        sa.Column('max_drawdown_duration_days', sa.Integer, nullable=True),
        sa.Column('win_rate', sa.Numeric(5, 4), nullable=True),
        sa.Column('total_trades', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avg_trade_duration_hours', sa.Numeric(10, 2), nullable=True),
        sa.Column('profit_factor', sa.Numeric(10, 4), nullable=True),
        sa.Column('final_capital', sa.Numeric(18, 2), nullable=True),
        sa.Column('metrics', JSONB, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('candles_processed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('agent_decisions_count', sa.Integer, nullable=False, server_default='0'),
    )
    op.create_index('idx_backtest_run_config_status', 'backtest_runs', ['config_id', 'status'])
    op.create_index('idx_backtest_run_start_time', 'backtest_runs', ['start_time'], postgresql_using='btree')

    # SimulatedTrade table
    op.create_table(
        'simulated_trades',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('backtest_run_id', UUID(as_uuid=True), sa.ForeignKey('backtest_runs.id'), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('action', sa.Enum('buy', 'sell', 'close_long', 'close_short', name='trade_action'), nullable=False),
        sa.Column('entry_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('entry_price', sa.Numeric(18, 8), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('exit_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('gross_pnl', sa.Numeric(18, 2), nullable=True),
        sa.Column('fees_paid', sa.Numeric(18, 2), nullable=False),
        sa.Column('net_pnl', sa.Numeric(18, 2), nullable=True),
        sa.Column('holding_duration_seconds', sa.Integer, nullable=True),
        sa.Column('decision_context', JSONB, nullable=True),
        sa.Column('slippage_applied', sa.Numeric(18, 8), nullable=False),
    )
    op.create_index('idx_simulated_trade_run', 'simulated_trades', ['backtest_run_id', 'entry_timestamp'])
    op.create_index('idx_simulated_trade_symbol', 'simulated_trades', ['symbol', 'entry_timestamp'])

    # PortfolioSnapshot table
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('backtest_run_id', UUID(as_uuid=True), sa.ForeignKey('backtest_runs.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cash_balance', sa.Numeric(18, 2), nullable=False),
        sa.Column('positions', JSONB, nullable=False),
        sa.Column('total_value', sa.Numeric(18, 2), nullable=False),
        sa.Column('unrealized_pnl', sa.Numeric(18, 2), nullable=False),
        sa.Column('realized_pnl', sa.Numeric(18, 2), nullable=False),
        sa.Column('buying_power', sa.Numeric(18, 2), nullable=False),
    )
    op.create_index('idx_portfolio_snapshot_run_time', 'portfolio_snapshots', ['backtest_run_id', 'timestamp'])

    # AgentDecisionLog table
    op.create_table(
        'agent_decision_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('backtest_run_id', UUID(as_uuid=True), sa.ForeignKey('backtest_runs.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('agent_identifier', sa.String(255), nullable=False),
        sa.Column('decision_type', sa.Enum('signal', 'risk', 'execution', 'other', name='decision_type'), nullable=False),
        sa.Column('input_data', JSONB, nullable=False),
        sa.Column('output_decision', JSONB, nullable=False),
        sa.Column('execution_outcome', sa.String(50), nullable=True),
        sa.Column('processing_time_ms', sa.Integer, nullable=True),
        sa.Column('correlation_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_index('idx_agent_log_run_time', 'agent_decision_logs', ['backtest_run_id', 'timestamp'])
    op.create_index('idx_agent_log_agent', 'agent_decision_logs', ['agent_identifier', 'timestamp'])
    op.create_index('idx_agent_log_correlation', 'agent_decision_logs', ['correlation_id'])

    # ParameterGrid table
    op.create_table(
        'parameter_grids',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('base_config_id', UUID(as_uuid=True), sa.ForeignKey('backtest_configurations.id'), nullable=False),
        sa.Column('parameters', JSONB, nullable=False),
        sa.Column('total_combinations', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_parameter_grid_name', 'parameter_grids', ['name'])

    # GridSearchResult table
    op.create_table(
        'grid_search_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('grid_id', UUID(as_uuid=True), sa.ForeignKey('parameter_grids.id'), nullable=False),
        sa.Column('backtest_run_id', UUID(as_uuid=True), sa.ForeignKey('backtest_runs.id'), nullable=False),
        sa.Column('parameter_values', JSONB, nullable=False),
        sa.Column('rank_by_sharpe', sa.Integer, nullable=True),
        sa.Column('rank_by_return', sa.Integer, nullable=True),
        sa.Column('rank_by_drawdown', sa.Integer, nullable=True),
        sa.Column('is_statistically_significant', sa.Boolean, nullable=False, server_default='false'),
    )
    op.create_index('idx_grid_result_grid_rank', 'grid_search_results', ['grid_id', 'rank_by_sharpe'])
    op.create_index('idx_grid_result_run', 'grid_search_results', ['backtest_run_id'])


def downgrade() -> None:
    """Drop all backtesting tables in reverse dependency order."""
    op.drop_table('grid_search_results')
    op.drop_table('parameter_grids')
    op.drop_table('agent_decision_logs')
    op.drop_table('portfolio_snapshots')
    op.drop_table('simulated_trades')
    op.drop_table('backtest_runs')
    op.drop_table('backtest_configurations')
