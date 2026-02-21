"""Create backtesting ENUM types

Revision ID: 001_backtesting_enums
Revises:
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_backtesting_enums'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ENUM types for backtesting engine."""
    # ExecutionMode ENUM
    op.execute("""
        CREATE TYPE execution_mode AS ENUM ('full_pipeline', 'synthetic_fast')
    """)

    # RunStatus ENUM
    op.execute("""
        CREATE TYPE run_status AS ENUM ('running', 'completed', 'failed', 'timeout')
    """)

    # TradeAction ENUM
    op.execute("""
        CREATE TYPE trade_action AS ENUM ('buy', 'sell', 'close_long', 'close_short')
    """)

    # DecisionType ENUM
    op.execute("""
        CREATE TYPE decision_type AS ENUM ('signal', 'risk', 'execution', 'other')
    """)


def downgrade() -> None:
    """Drop ENUM types for backtesting engine."""
    op.execute("DROP TYPE IF EXISTS decision_type CASCADE")
    op.execute("DROP TYPE IF EXISTS trade_action CASCADE")
    op.execute("DROP TYPE IF EXISTS run_status CASCADE")
    op.execute("DROP TYPE IF EXISTS execution_mode CASCADE")
