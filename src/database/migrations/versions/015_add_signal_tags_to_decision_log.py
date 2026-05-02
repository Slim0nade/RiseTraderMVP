"""Add signal tagging columns to decision_log for Karpathy-style iteration.

Revision ID: 015_add_signal_tags_to_decision_log
Revises: 014_create_mt4_account_phases
Create Date: 2026-05-01

Purpose:
    Without per-signal tagging we cannot tell which model version, regime, or
    account_phase produced a trade — making any later analysis or iteration
    impossible.  This migration adds 5 tag columns to decision_log:

    1. strategy_version — which versioned strategy produced the signal
       (e.g. 'crude_oil_v3', 'value_area@1.2.0').  Backfilled to 'legacy'
       for all pre-existing rows.

    2. model_artifact_hash — sha256 hex of the model file bytes when a trained
       ML model was used; NULL for pure-rules signals.  Allows exact
       reproducibility: load the hash, find the artifact, re-run.

    3. regime — market regime string from RegimeDetectionAgent at signal time
       (e.g. 'high_volatility', 'trending_up').  NULL when regime detection
       was not running or failed — never faked.

    4. feature_hash — sha256 hex of the feature vector JSON (sorted keys) that
       was fed into the model; NULL when no feature vector was used.  Lets us
       detect data-drift: same model + different hash = regime shift.

    5. account_phase — placeholder varchar receiver for migration 014's
       mt4_account_phases table.  No FK constraint yet — migration 014 may or
       may not be applied on a given DB.  The FK will be added in a later
       migration once join semantics are finalised.  NULL until then.

Backfill:
    All existing rows receive strategy_version='legacy' so that GROUP BY
    queries on strategy_version always return at least one bucket and analysts
    know the provenance boundary.

Downgrade:
    DROP the five columns cleanly.  Idempotent on fresh DBs.
"""

from alembic import op
import sqlalchemy as sa


revision = '015_add_signal_tags_to_decision_log'
down_revision = '014_create_mt4_account_phases'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add strategy_version ─────────────────────────────────────────────
    # VARCHAR, NOT NULL after backfill.  We add as nullable first, backfill,
    # then apply NOT NULL — this avoids locking issues on large tables.
    op.add_column(
        'decision_log',
        sa.Column(
            'strategy_version',
            sa.String(100),
            nullable=True,
            comment=(
                "Versioned strategy identifier that generated this signal "
                "(e.g. 'crude_oil_v3', 'value_area@1.2.0').  "
                "'legacy' for rows inserted before migration 015."
            ),
        ),
    )

    # ── 2. Add model_artifact_hash ──────────────────────────────────────────
    op.add_column(
        'decision_log',
        sa.Column(
            'model_artifact_hash',
            sa.String(64),
            nullable=True,
            comment=(
                "SHA-256 hex of the model artifact file bytes (model.json / "
                "model.pkl) when a trained ML model was used.  "
                "NULL for pure-rules signals — never synthesised."
            ),
        ),
    )

    # ── 3. Add regime ────────────────────────────────────────────────────────
    op.add_column(
        'decision_log',
        sa.Column(
            'regime',
            sa.String(50),
            nullable=True,
            comment=(
                "Market regime from RegimeDetectionAgent at signal time "
                "(e.g. 'high_volatility', 'trending_up', 'ranging').  "
                "NULL when regime agent was not running or classification "
                "raised an exception — never faked."
            ),
        ),
    )

    # ── 4. Add feature_hash ─────────────────────────────────────────────────
    op.add_column(
        'decision_log',
        sa.Column(
            'feature_hash',
            sa.String(64),
            nullable=True,
            comment=(
                "SHA-256 hex of json.dumps(feature_vector, sort_keys=True) "
                "when a feature vector was built for this signal.  "
                "NULL when no feature vector was used.  "
                "Enables data-drift detection: same model + different hash "
                "indicates regime or data-source change."
            ),
        ),
    )

    # ── 5. Add account_phase ─────────────────────────────────────────────────
    # Placeholder varchar — receiver for mt4_account_phases join once
    # migration 014 is confirmed live.  No FK constraint yet.
    op.add_column(
        'decision_log',
        sa.Column(
            'account_phase',
            sa.String(50),
            nullable=True,
            comment=(
                "MT4 broker account phase identifier "
                "(e.g. 'Phase_4_live', 'Phase_6_current').  "
                "Placeholder column — FK to mt4_account_phases will be "
                "added in a later migration once join semantics are "
                "finalised.  NULL until then."
            ),
        ),
    )

    # ── 6. Backfill existing rows ────────────────────────────────────────────
    # Mark all pre-migration rows as 'legacy' so GROUP BY strategy_version
    # always returns at least one bucket and analysts know the provenance
    # boundary.  Other new columns stay NULL for legacy rows — that is correct.
    op.execute(
        "UPDATE decision_log SET strategy_version = 'legacy' "
        "WHERE strategy_version IS NULL"
    )

    # ── 7. Enforce NOT NULL on strategy_version after backfill ──────────────
    op.alter_column('decision_log', 'strategy_version', nullable=False)

    # ── 8. Composite index on (strategy_version, decided_at) ────────────────
    # Supports the primary iteration query:
    #   SELECT strategy_version, COUNT(*) FROM decision_log GROUP BY 1
    op.create_index(
        'ix_decision_log_strategy_version_time',
        'decision_log',
        ['strategy_version', 'decided_at'],
    )

    # ── 9. Index on regime for regime-bucketed P&L attribution ───────────────
    op.create_index(
        'ix_decision_log_regime_time',
        'decision_log',
        ['regime', 'decided_at'],
        postgresql_where=sa.text('regime IS NOT NULL'),
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_decision_log_regime_time', table_name='decision_log')
    op.drop_index(
        'ix_decision_log_strategy_version_time', table_name='decision_log'
    )

    # Drop columns in reverse order
    op.drop_column('decision_log', 'account_phase')
    op.drop_column('decision_log', 'feature_hash')
    op.drop_column('decision_log', 'regime')
    op.drop_column('decision_log', 'model_artifact_hash')
    op.drop_column('decision_log', 'strategy_version')
