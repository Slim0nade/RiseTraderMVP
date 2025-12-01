"""Create model_metrics table.

Revision ID: 008
Revises: 007
Create Date: 2025-11-29
"""

from alembic import op
import sqlalchemy as sa


revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'model_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('model_type', sa.String(20), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=False, index=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('forecast_horizon', sa.String(10), nullable=False),
        sa.Column('mpe', sa.Float(), nullable=False),
        sa.Column('mse', sa.Float(), nullable=False),  # Mean Squared Error
        sa.Column('rmse', sa.Float(), nullable=False),
        sa.Column('mae', sa.Float(), nullable=False),
        sa.Column('mape', sa.Float(), nullable=False),
        sa.Column('directional_accuracy', sa.Float()),
        sa.Column('evaluation_date', sa.DateTime(), nullable=False),
        sa.Column('sample_size', sa.Integer()),
        sa.Column('mlflow_run_id', sa.String(100)),
        sa.Column('calculated_at', sa.DateTime(), nullable=False)  # For API compatibility
    )

    op.create_index('idx_metrics_lookup', 'model_metrics', ['model_version', 'forecast_horizon'])
    op.create_index('idx_metrics_symbol_horizon', 'model_metrics', ['symbol', 'forecast_horizon'])


def downgrade():
    op.drop_table('model_metrics')
