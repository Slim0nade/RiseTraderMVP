"""Add composite indexes for market_data performance optimization

Revision ID: 004
Revises: 003
Create Date: 2025-11-25

Research Decision: Add composite index (symbol, timeframe, time DESC) for efficient
chart data queries per research.md recommendations.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add composite index on market_data table for optimal query performance.

    This index supports the most common query pattern:
    WHERE symbol = ? AND timeframe = ? ORDER BY time DESC LIMIT 500

    Expected to reduce query time from ~2s to <500ms for 500 candlesticks.
    """
    # Check if index already exists before creating
    connection = op.get_bind()

    # Check for existing index
    result = connection.execute(sa.text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'market_data'
        AND indexname = 'idx_market_data_symbol_timeframe_time'
    """))

    if not result.fetchone():
        # Create composite index on (symbol, timeframe, time DESC)
        # This is the primary access pattern for chart data queries
        op.execute("""
            CREATE INDEX idx_market_data_symbol_timeframe_time
            ON market_data (symbol, timeframe, time DESC)
        """)


def downgrade() -> None:
    """Remove composite index."""
    op.drop_index('idx_market_data_symbol_timeframe_time', table_name='market_data')
