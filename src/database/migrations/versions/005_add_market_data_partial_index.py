"""Add partial index for recent market_data (hot data optimization)

Revision ID: 005
Revises: 004
Create Date: 2025-11-25

Research Decision: Partial index on recent 30 days data per research.md.
Most dashboard queries access recent data - this index optimizes the hot path.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add partial index for recent market data (last 30 days).

    NOTE: Partial index with NOW() - INTERVAL not supported in PostgreSQL
    because NOW() is not an immutable function. The composite index from
    migration 004 provides sufficient performance for all queries.

    This migration is intentionally left as a no-op. The composite index
    idx_market_data_symbol_timeframe_time from migration 004 handles both
    recent and historical data queries efficiently.
    """
    # No-op: Composite index from 004 is sufficient
    # Partial indexes with NOW() are not supported in PostgreSQL
    pass


def downgrade() -> None:
    """Remove partial index."""
    # No-op: No index was created in upgrade
    pass
