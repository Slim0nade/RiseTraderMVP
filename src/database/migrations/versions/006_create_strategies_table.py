"""Create strategies table

Revision ID: 006
Revises: 005
Create Date: 2025-11-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create strategies table for storing trading strategy configurations."""

    # Create ENUM type for strategy status using raw SQL with IF NOT EXISTS
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE strategy_status AS ENUM ('ACTIVE', 'PAUSED', 'DISABLED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        'strategies',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'PAUSED', 'DISABLED', name='strategy_status', create_type=False),
            nullable=False,
            server_default='ACTIVE'
        ),
        sa.Column('allocated_capital', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0.00'),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_strategies_name')
    )

    # Create index on status for filtering
    op.create_index(
        'ix_strategies_status',
        'strategies',
        ['status']
    )

    # Create index on created_at for sorting
    op.create_index(
        'ix_strategies_created_at',
        'strategies',
        ['created_at']
    )


def downgrade() -> None:
    """Drop strategies table and related objects."""
    op.drop_index('ix_strategies_created_at', table_name='strategies')
    op.drop_index('ix_strategies_status', table_name='strategies')
    op.drop_table('strategies')

    # Drop ENUM type using raw SQL
    op.execute("DROP TYPE IF EXISTS strategy_status")
