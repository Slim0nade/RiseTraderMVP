"""Create exogenous_variables table.

Revision ID: 009
Revises: 008
Create Date: 2025-11-29
"""

from alembic import op
import sqlalchemy as sa


revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'exogenous_variables',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('variable_name', sa.String(50), nullable=False, index=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, index=True),
        sa.Column('value', sa.Float()),
        sa.Column('is_event', sa.Boolean(), default=False),
        sa.Column('source', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), nullable=False)
    )
    
    op.create_index('idx_exogenous_lookup', 'exogenous_variables', ['variable_name', 'timestamp'])


def downgrade():
    op.drop_table('exogenous_variables')
