"""Create strategy_allocations table

Revision ID: 007
Revises: 006
Create Date: 2025-11-28

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create strategy_allocations table for tracking capital allocation history."""
    op.create_table(
        'strategy_allocations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('allocated_capital', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('allocated_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('allocation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['strategy_id'],
            ['strategies.id'],
            name='fk_strategy_allocations_strategy_id',
            ondelete='CASCADE'
        )
    )

    # Create index on strategy_id for quick lookups
    op.create_index(
        'ix_strategy_allocations_strategy_id',
        'strategy_allocations',
        ['strategy_id']
    )

    # Create composite index for strategy_id and allocation_date (for sorting)
    op.create_index(
        'ix_strategy_allocations_strategy_id_date',
        'strategy_allocations',
        ['strategy_id', 'allocation_date'],
        postgresql_ops={'allocation_date': 'DESC'}
    )

    # Create index on allocation_date for time-based queries
    op.create_index(
        'ix_strategy_allocations_allocation_date',
        'strategy_allocations',
        ['allocation_date']
    )


def downgrade() -> None:
    """Drop strategy_allocations table and related indexes."""
    op.drop_index('ix_strategy_allocations_allocation_date', table_name='strategy_allocations')
    op.drop_index('ix_strategy_allocations_strategy_id_date', table_name='strategy_allocations')
    op.drop_index('ix_strategy_allocations_strategy_id', table_name='strategy_allocations')
    op.drop_table('strategy_allocations')
