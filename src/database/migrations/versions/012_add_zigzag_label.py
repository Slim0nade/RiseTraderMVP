"""Add zigzag_label column to indicators table

Revision ID: 012_add_zigzag_label
Revises: 011
Create Date: 2026-01-14

Purpose:
    Add a single column to store ZigZag-derived peak/valley labels
    for ML training. Simple approach - no extra tables.
    
    Label values:
    -  1 = PEAK (potential short signal)
    -  0 = NEITHER (no reversal) - default
    - -1 = VALLEY (potential long signal)
"""
from alembic import op
import sqlalchemy as sa


revision = '012_add_zigzag_label'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add zigzag_label column with default 0 (neither)
    op.add_column(
        'indicators',
        sa.Column('zigzag_label', sa.SmallInteger(), nullable=True, default=0)
    )
    
    # Index for fast filtering by label (find all peaks/valleys)
    op.create_index(
        'ix_indicators_zigzag_label',
        'indicators',
        ['zigzag_label']
    )
    
    # Composite index for querying labels by symbol/timeframe
    op.create_index(
        'ix_indicators_symbol_timeframe_zigzag',
        'indicators',
        ['symbol', 'timeframe', 'zigzag_label']
    )


def downgrade() -> None:
    op.drop_index('ix_indicators_symbol_timeframe_zigzag', table_name='indicators')
    op.drop_index('ix_indicators_zigzag_label', table_name='indicators')
    op.drop_column('indicators', 'zigzag_label')
