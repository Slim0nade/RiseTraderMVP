"""Create training_runs table.

Revision ID: 007
Revises: 006
Create Date: 2025-11-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM


revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    training_status = ENUM('pending', 'running', 'completed', 'failed', 'cancelled', name='training_status')
    training_status.create(op.get_bind())
    
    op.create_table(
        'training_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('run_name', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False, index=True),
        sa.Column('model_type', sa.String(20), nullable=False),
        sa.Column('mlflow_run_id', sa.String(100), unique=True),
        sa.Column('hyperparameters', JSONB, nullable=False),
        sa.Column('feature_config', JSONB, nullable=False),
        sa.Column('training_config', JSONB, nullable=False),
        sa.Column('status', training_status, nullable=False),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('duration_seconds', sa.Integer()),
        sa.Column('final_metrics', JSONB),
        sa.Column('model_version', sa.String(50)),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(100))
    )
    
    op.create_index('idx_training_status', 'training_runs', ['status', 'created_at'])
    op.create_index('idx_training_symbol', 'training_runs', ['symbol', 'model_type'])


def downgrade():
    op.drop_table('training_runs')
    op.execute('DROP TYPE training_status')
