"""create mt4_connections table

Revision ID: 001
Revises:
Create Date: 2025-11-22 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mt4_connections table."""
    # Create connection_status enum
    op.execute(
        "CREATE TYPE connection_status AS ENUM ('ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING')"
    )

    # Create mt4_connections table
    op.create_table(
        'mt4_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ea_id', sa.String(length=50), nullable=False),
        sa.Column('magic_number', sa.Integer(), nullable=False),
        sa.Column('rep_port', sa.Integer(), nullable=False),
        sa.Column('pub_port', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING', name='connection_status'),
            nullable=False
        ),
        sa.Column(
            'mt4_server_host',
            sa.String(length=100),
            nullable=False,
            server_default='75.154.254.174'
        ),
        sa.Column('encryption_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('client_public_key', sa.String(length=64), nullable=True),
        sa.Column('server_public_key', sa.String(length=64), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ea_id'),
        sa.UniqueConstraint('magic_number'),
        comment='Expert Advisor connection registry'
    )

    # Create indexes
    op.create_index('idx_mt4_connection_magic', 'mt4_connections', ['magic_number'])
    op.create_index('idx_mt4_connection_status', 'mt4_connections', ['status'])
    op.create_index('idx_mt4_connection_ea_id', 'mt4_connections', ['ea_id'])


def downgrade() -> None:
    """Drop mt4_connections table."""
    op.drop_index('idx_mt4_connection_ea_id', table_name='mt4_connections')
    op.drop_index('idx_mt4_connection_status', table_name='mt4_connections')
    op.drop_index('idx_mt4_connection_magic', table_name='mt4_connections')
    op.drop_table('mt4_connections')
    op.execute('DROP TYPE connection_status')
