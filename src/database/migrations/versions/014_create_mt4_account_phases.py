"""Create mt4_account_phases sidecar table for ForTrade broker phase tracking.

Revision ID: 014_create_mt4_account_phases
Revises: 013
Create Date: 2026-04-30

Purpose:
    ForTrade (the broker) periodically adjusts CFD pricing — at least once a
    month — producing structural premium changes vs. NYMEX exchange prices.
    The 2026-04-29 analysis identified 6 distinct phases in the MT4 source
    history, each with its own offset characteristics:

      Phase 1 (initial demo)   : ~0% premium, clean tracking
      Phase 2 (Apr-Jun 2025)   : +3% structural premium, smooth drift
      Phase 3 (outage)         : no MT4 data
      Phase 4 (live, Nov-Feb)  : +0.8% normal broker spread
      Phase 5 (Mar-Apr 2026)   : +4.5% premium during Hormuz crisis
      Phase 6 (current)        : ~0% premium, cleanest tracking observed

    These are real broker pricing dynamics, not bad data — Phase 2 and 5
    are usable training samples covering different volatility regimes.

    This sidecar table lets backtests, training queries, and live execution
    join MT4 rows to their phase metadata without adding a column to the
    13.5M-row market_data table. The view `market_data_with_phase` performs
    the join automatically.

Schema:
    mt4_account_phases — one row per phase with date range and statistics
    market_data_with_phase — view that joins market_data to its phase

Reference:
    .serena/memories/2026-04-29-mt4-broker-premium-and-correct-training-architecture.md
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '014_create_mt4_account_phases'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── 1. Create the mt4_account_phases sidecar table ─────────────────
    op.create_table(
        'mt4_account_phases',
        sa.Column('phase', sa.Text(), primary_key=True,
                  comment='Stable phase id e.g. phase_1, phase_4, phase_6'),
        sa.Column('start_time', postgresql.TIMESTAMP(timezone=True),
                  nullable=False, comment='Inclusive start timestamp UTC'),
        sa.Column('end_time', postgresql.TIMESTAMP(timezone=True),
                  nullable=True,
                  comment='Inclusive end timestamp UTC; NULL = open-ended (current phase)'),
        sa.Column('label', sa.Text(), nullable=False,
                  comment='Human-readable phase description'),
        sa.Column('mean_offset_bc_minus_mt4', sa.Numeric(10, 4), nullable=True,
                  comment='Mean (BC.close - MT4.close) over phase, USD'),
        sa.Column('pct_premium', sa.Numeric(8, 4), nullable=True,
                  comment='Mean offset as % of price (positive = MT4 above BC)'),
        sa.Column('intraday_std', sa.Numeric(10, 4), nullable=True,
                  comment='Mean per-minute std of (BC-MT4); proxy for execution lag'),
        sa.Column('quality', sa.Text(), nullable=False,
                  comment="One of: clean | premium | volatile_premium | outage"),
        sa.Column('use_for_training', sa.Boolean(), nullable=False,
                  server_default=sa.text('TRUE'),
                  comment='Whether this phase is recommended for ML training (informational)'),
        sa.Column('use_for_execution_validation', sa.Boolean(), nullable=False,
                  server_default=sa.text('TRUE'),
                  comment='Whether to use this phase for backtest-vs-live comparison'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text('NOW()')),
    )

    # Index for time-range lookups when joining to market_data
    op.create_index(
        'ix_mt4_phase_time_range',
        'mt4_account_phases',
        ['start_time', 'end_time'],
    )

    # Constraint: end_time, if present, must be > start_time
    op.create_check_constraint(
        'ck_mt4_phase_time_order',
        'mt4_account_phases',
        'end_time IS NULL OR end_time > start_time',
    )

    # ─── 2. Seed the 6 known phases from 2026-04-29 analysis ────────────
    # Reference: data/quality/mt4_segments.csv + 04-29 memory
    op.execute("""
        INSERT INTO mt4_account_phases
            (phase, start_time, end_time, label, mean_offset_bc_minus_mt4,
             pct_premium, intraday_std, quality, use_for_training,
             use_for_execution_validation, notes)
        VALUES
            ('phase_1',
             '2024-08-19 00:00:00+00',
             '2025-03-25 23:59:59+00',
             'Initial demo (clean)',
             0.003, 0.000, 0.030, 'clean', TRUE, TRUE,
             'Demo feed tracked NYMEX within bid-ask spread.'),
            ('phase_2',
             '2025-04-08 00:00:00+00',
             '2025-06-18 23:59:59+00',
             'Premium regime (Apr-Jun 2025)',
             -1.956, 3.020, 0.165, 'premium', TRUE, TRUE,
             'Smooth ~3% structural premium for ~2 months. Possibly broker '
             'switched WTI->Brent reference or added carry layer. r²=0.70 '
             'vs price level, lag-1 autocorr=+0.79. Usable training data; '
             'returns/z-score features survive intact.'),
            ('phase_3',
             '2025-06-19 00:00:00+00',
             '2025-11-24 23:59:59+00',
             'Outage (no MT4 data)',
             NULL, NULL, NULL, 'outage', FALSE, FALSE,
             '5-month MT4 outage; BC backfill landed in Apr 2026.'),
            ('phase_4',
             '2025-11-25 00:00:00+00',
             '2026-02-27 23:59:59+00',
             'Live (Nov 2025 - Feb 2026)',
             -0.487, 0.800, 0.048, 'clean', TRUE, TRUE,
             'Live broker phase, consistent ~0.8% spread. Gold-standard '
             'segment for execution validation.'),
            ('phase_5',
             '2026-03-01 00:00:00+00',
             '2026-04-02 23:59:59+00',
             'Hormuz crisis (high premium + lag)',
             -4.395, 4.570, 0.508, 'volatile_premium', TRUE, TRUE,
             'Extreme volatility caused broker to widen premium to ~4.5% AND '
             'tick-lag during fast moves (10x normal intraday std). Data is '
             'structurally consistent but execution-quality data is poor. '
             'Useful for stress-period training; do NOT use for execution '
             'simulation without aware slippage model.'),
            ('phase_6',
             '2026-04-19 00:00:00+00',
             NULL,  -- open-ended; current phase
             'Current (cleanest tracking observed)',
             0.156, -0.164, 0.087, 'clean', TRUE, TRUE,
             'Post-outage demo. MT4 mid-quotes NYMEX within bid-ask spread. '
             'Better tracking than Phase 4. Current paper-trading regime.');
    """)

    # ─── 3. Create the join view ────────────────────────────────────────
    # Performance note: this view does a range join. For full table scans
    # this is fine; for hot loops, callers should add an explicit
    # `WHERE time BETWEEN ? AND ?` to limit the row set first.
    op.execute("""
        CREATE OR REPLACE VIEW market_data_with_phase AS
        SELECT
            md.*,
            p.phase           AS account_phase,
            p.label           AS account_phase_label,
            p.quality         AS account_phase_quality,
            p.pct_premium     AS account_phase_pct_premium,
            p.intraday_std    AS account_phase_intraday_std
        FROM market_data md
        LEFT JOIN mt4_account_phases p
          ON md.source = 'MT4'
         AND md.time >= p.start_time
         AND (p.end_time IS NULL OR md.time <= p.end_time);
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS market_data_with_phase")
    op.drop_index('ix_mt4_phase_time_range', table_name='mt4_account_phases')
    op.drop_table('mt4_account_phases')
