"""Add max_candles column to backtest_configurations

Revision ID: 003
Revises: 002
Create Date: 2025-01-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add max_candles column with default value to prevent infinite backtest loops."""
    op.add_column(
        'backtest_configurations',
        sa.Column('max_candles', sa.Integer(), nullable=False, server_default='150000')
    )
    # Remove server_default after adding the column (so future rows use application default)
    op.alter_column('backtest_configurations', 'max_candles', server_default=None)


def downgrade() -> None:
    """Remove max_candles column."""
    op.drop_column('backtest_configurations', 'max_candles')
