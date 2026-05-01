"""Add TWELVEDATA to datasource enum

Revision ID: 005_add_twelvedata_datasource
Revises: 004_optimization_tables
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '005_add_twelvedata_datasource'
down_revision: Union[str, None] = '004_optimization_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE datasource ADD VALUE IF NOT EXISTS 'TWELVEDATA'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass
