"""Create forecasts table.

Revision ID: 006
Revises: 005
Create Date: 2025-11-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'forecasts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(20), nullable=False, index=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, index=True),
        sa.Column('forecast_horizon', sa.String(10), nullable=False),
        sa.Column('model_type', sa.String(20), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=False),
        sa.Column('mlflow_run_id', sa.String(100)),
        sa.Column('predicted_value', sa.Float(), nullable=False),
        sa.Column('lower_bound', sa.Float()),
        sa.Column('upper_bound', sa.Float()),
        sa.Column('confidence_score', sa.Float()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('inference_time_ms', sa.Float())
    )
    
    # Composite indexes
    op.create_index(
        'idx_forecast_lookup',
        'forecasts',
        ['symbol', 'timestamp', 'forecast_horizon', 'model_version']
    )
    op.create_index(
        'idx_forecast_latest',
        'forecasts',
        ['symbol', 'forecast_horizon', 'created_at']
    )


def downgrade():
    op.drop_table('forecasts')
