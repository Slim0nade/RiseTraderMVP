"""create mt4_positions table

Revision ID: 003
Revises: 002
Create Date: 2025-11-22 14:00:02.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mt4_positions table."""
    # Create position_direction enum
    op.execute("CREATE TYPE position_direction AS ENUM ('BUY', 'SELL')")

    # Create mt4_positions table
    op.create_table(
        'mt4_positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ticket_number', sa.Integer(), nullable=False),
        sa.Column('magic_number', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column(
            'direction',
            sa.Enum('BUY', 'SELL', name='position_direction'),
            nullable=False
        ),
        sa.Column('volume', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('open_price', sa.Numeric(precision=10, scale=5), nullable=False),
        sa.Column('current_price', sa.Numeric(precision=10, scale=5), nullable=False),
        sa.Column('unrealized_pnl', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('stop_loss', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('take_profit', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('open_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['order_id'],
            ['mt4_orders.id'],
            ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_number'),
        comment='Open position tracking with P&L'
    )

    # Create indexes
    op.create_index('idx_mt4_position_ticket', 'mt4_positions', ['ticket_number'])
    op.create_index('idx_mt4_position_magic', 'mt4_positions', ['magic_number'])
    op.create_index('idx_mt4_position_symbol', 'mt4_positions', ['symbol'])


def downgrade() -> None:
    """Drop mt4_positions table."""
    op.drop_index('idx_mt4_position_symbol', table_name='mt4_positions')
    op.drop_index('idx_mt4_position_magic', table_name='mt4_positions')
    op.drop_index('idx_mt4_position_ticket', table_name='mt4_positions')
    op.drop_table('mt4_positions')
    op.execute('DROP TYPE position_direction')
