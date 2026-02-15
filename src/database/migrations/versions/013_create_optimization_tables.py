"""Create optimization_runs and price_alerts tables

Revision ID: 013
Revises: 012_add_zigzag_label
Create Date: 2026-01-18

Tables:
- optimization_runs: Persistent record of optimization runs with results
- price_alerts: Configured price levels to monitor for open positions
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012_add_zigzag_label'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create optimization_runs and price_alerts tables with indexes."""

    # OptimizationRun table
    op.create_table(
        'optimization_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', sa.String(36), nullable=False, unique=True),
        sa.Column('strategy', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('param_grid', JSONB, nullable=False),
        sa.Column('results', JSONB, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('total_combinations', sa.Integer, nullable=False),
        sa.Column('combinations_tested', sa.Integer, nullable=False, server_default='0'),
        sa.Column('best_params', JSONB, nullable=True),
        sa.Column('best_metric_value', sa.Numeric(10, 4), nullable=True),
        sa.Column('optimization_target', sa.String(50), nullable=False, server_default='sharpe_ratio'),
        sa.Column('initial_capital', sa.Numeric(18, 2), nullable=False, server_default='10000.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
    )

    # Indexes for optimization_runs
    op.create_index('idx_optimization_runs_job_id', 'optimization_runs', ['job_id'], unique=True)
    op.create_index('idx_optimization_runs_strategy', 'optimization_runs', ['strategy'])
    op.create_index('idx_optimization_runs_symbol', 'optimization_runs', ['symbol'])
    op.create_index('idx_optimization_runs_status', 'optimization_runs', ['status'])
    op.create_index('idx_optimization_runs_strategy_symbol', 'optimization_runs', ['strategy', 'symbol'])
    op.create_index('idx_optimization_runs_created_at', 'optimization_runs', ['created_at'], postgresql_using='btree')

    # PriceAlert table
    op.create_table(
        'price_alerts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('ticket', sa.Integer, nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('price_level', sa.Numeric(18, 6), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('triggered', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('alert_data', JSONB, nullable=True),
    )

    # Indexes for price_alerts
    op.create_index('idx_price_alerts_ticket', 'price_alerts', ['ticket'])
    op.create_index(
        'idx_price_alerts_active',
        'price_alerts',
        ['ticket', 'triggered'],
        postgresql_where=sa.text('triggered = false')
    )

    # Unique constraint to prevent duplicate alerts
    op.create_unique_constraint(
        'uq_price_alert_ticket_type_level',
        'price_alerts',
        ['ticket', 'alert_type', 'price_level']
    )


def downgrade() -> None:
    """Drop optimization_runs and price_alerts tables."""
    op.drop_table('price_alerts')
    op.drop_table('optimization_runs')
