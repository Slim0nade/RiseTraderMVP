"""Create strategy_performance table

Revision ID: 008
Revises: 007
Create Date: 2025-11-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create strategy_performance table for tracking strategy metrics by period."""

    # Create ENUM type for performance period using raw SQL with IF NOT EXISTS
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE performance_period AS ENUM ('daily', 'weekly', 'monthly', 'all_time');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        'strategy_performance',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column(
            'period',
            sa.Enum('daily', 'weekly', 'monthly', 'all_time', name='performance_period', create_type=False),
            nullable=False
        ),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('losing_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('win_rate', sa.Numeric(precision=5, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_profit', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_loss', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0.00'),
        sa.Column('net_profit', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0.00'),
        sa.Column('sharpe_ratio', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('max_drawdown', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('average_win', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('average_loss', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['strategy_id'],
            ['strategies.id'],
            name='fk_strategy_performance_strategy_id',
            ondelete='CASCADE'
        )
    )

    # Create index on strategy_id for quick lookups
    op.create_index(
        'ix_strategy_performance_strategy_id',
        'strategy_performance',
        ['strategy_id']
    )

    # Create composite index for strategy_id and period
    op.create_index(
        'ix_strategy_performance_strategy_id_period',
        'strategy_performance',
        ['strategy_id', 'period']
    )

    # Create unique constraint to prevent duplicate period records for same strategy
    op.create_index(
        'uq_strategy_performance_strategy_period_dates',
        'strategy_performance',
        ['strategy_id', 'period', 'period_start', 'period_end'],
        unique=True
    )

    # Create index on period for filtering
    op.create_index(
        'ix_strategy_performance_period',
        'strategy_performance',
        ['period']
    )

    # Create index on period_start for time-based queries
    op.create_index(
        'ix_strategy_performance_period_start',
        'strategy_performance',
        ['period_start']
    )


def downgrade() -> None:
    """Drop strategy_performance table and related objects."""
    op.drop_index('ix_strategy_performance_period_start', table_name='strategy_performance')
    op.drop_index('ix_strategy_performance_period', table_name='strategy_performance')
    op.drop_index('uq_strategy_performance_strategy_period_dates', table_name='strategy_performance')
    op.drop_index('ix_strategy_performance_strategy_id_period', table_name='strategy_performance')
    op.drop_index('ix_strategy_performance_strategy_id', table_name='strategy_performance')
    op.drop_table('strategy_performance')

    # Drop ENUM type using raw SQL
    op.execute("DROP TYPE IF EXISTS performance_period")
