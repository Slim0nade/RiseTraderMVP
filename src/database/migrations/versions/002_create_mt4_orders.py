"""create mt4_orders table

Revision ID: 002
Revises: 001
Create Date: 2025-11-22 14:00:01.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mt4_orders table."""
    # Create order_direction enum
    op.execute("CREATE TYPE order_direction AS ENUM ('BUY', 'SELL')")

    # Create order_type enum
    op.execute(
        "CREATE TYPE order_type AS ENUM "
        "('MARKET', 'LIMIT', 'STOP', 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP')"
    )

    # Create order_status enum
    op.execute(
        "CREATE TYPE order_status AS ENUM "
        "('PENDING', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED')"
    )

    # Create mt4_orders table
    op.create_table(
        'mt4_orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('magic_number', sa.Integer(), nullable=False),
        sa.Column('ticket_number', sa.Integer(), nullable=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column(
            'direction',
            sa.Enum('BUY', 'SELL', name='order_direction'),
            nullable=False
        ),
        sa.Column('volume', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            'order_type',
            sa.Enum(
                'MARKET', 'LIMIT', 'STOP', 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP',
                name='order_type'
            ),
            nullable=False
        ),
        sa.Column('limit_price', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('stop_loss', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('take_profit', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('execution_price', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('required_margin', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'PENDING', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED',
                name='order_status'
            ),
            nullable=False
        ),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('correlation_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['magic_number'],
            ['mt4_connections.magic_number'],
            ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id'),
        sa.UniqueConstraint('ticket_number'),
        comment='Order lifecycle tracking'
    )

    # Create indexes
    op.create_index('idx_mt4_order_magic', 'mt4_orders', ['magic_number'])
    op.create_index('idx_mt4_order_ticket', 'mt4_orders', ['ticket_number'])
    op.create_index('idx_mt4_order_status', 'mt4_orders', ['status'])
    op.create_index('idx_mt4_order_correlation', 'mt4_orders', ['correlation_id'])
    op.create_index('idx_mt4_order_submitted', 'mt4_orders', ['submitted_at'])


def downgrade() -> None:
    """Drop mt4_orders table."""
    op.drop_index('idx_mt4_order_submitted', table_name='mt4_orders')
    op.drop_index('idx_mt4_order_correlation', table_name='mt4_orders')
    op.drop_index('idx_mt4_order_status', table_name='mt4_orders')
    op.drop_index('idx_mt4_order_ticket', table_name='mt4_orders')
    op.drop_index('idx_mt4_order_magic', table_name='mt4_orders')
    op.drop_table('mt4_orders')
    op.execute('DROP TYPE order_status')
    op.execute('DROP TYPE order_type')
    op.execute('DROP TYPE order_direction')
