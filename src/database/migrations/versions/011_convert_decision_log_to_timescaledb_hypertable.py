"""Convert decision_log to TimescaleDB hypertable with retention policy.

This migration converts the decision_log table into a TimescaleDB hypertable
for efficient time-series data management with automatic partitioning and
implements a 90-day retention policy.

Revision ID: 011
Revises: 010
Create Date: 2025-12-02
"""

from alembic import op
import sqlalchemy as sa


revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    """Convert decision_log to TimescaleDB hypertable and add retention policy."""

    # 1. Check if TimescaleDB extension is available
    # If not available, skip hypertable creation and continue with indexes
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'"
    ))
    timescaledb_available = result.scalar() > 0

    if timescaledb_available:
        # Create TimescaleDB hypertable partitioned by decided_at (timestamp column)
        # This enables automatic partitioning and optimized time-series queries
        op.execute("""
            SELECT create_hypertable(
                'decision_log',
                'decided_at',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
        """)
        print("✓ TimescaleDB hypertable created for decision_log")
    else:
        print("⚠ TimescaleDB not available - skipping hypertable creation")
        print("  Note: Run with TimescaleDB for optimal performance")

    # 2. Create additional time-series optimized indexes
    # These work with the actual decision_log schema from migration 010

    # GIN index for JSON columns - cast to JSONB for indexing
    # Note: JSON type requires casting to JSONB for GIN indexing
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_input_data_gin
        ON decision_log USING gin ((input_data::jsonb));
    """)

    # GIN index for JSON decision_data column (flexible decision queries)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_decision_data_gin
        ON decision_log USING gin ((decision_data::jsonb));
    """)

    # GIN index for JSON execution_result column (execution analysis)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_execution_result_gin
        ON decision_log USING gin ((execution_result::jsonb))
        WHERE execution_result IS NOT NULL;
    """)

    # Index for executed decisions (filtering executed vs rejected)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_executed_time
        ON decision_log (was_executed, decided_at DESC);
    """)

    # Partial index for high-latency decisions (performance monitoring)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_high_latency
        ON decision_log (agent_id, decision_latency_ms, decided_at DESC)
        WHERE decision_latency_ms > 1000;
    """)

    # Index for PnL impact analysis
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_pnl_impact
        ON decision_log (pnl_impact, decided_at DESC)
        WHERE pnl_impact IS NOT NULL;
    """)

    # Index for confidence-based queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_confidence
        ON decision_log (confidence, decided_at DESC)
        WHERE confidence IS NOT NULL;
    """)

    # Composite index for model version tracking
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_model_version
        ON decision_log (model_version, decided_at DESC)
        WHERE model_version IS NOT NULL;
    """)

    # 3-5. TimescaleDB-specific features (retention, compression, continuous aggregates)
    # Only apply if TimescaleDB is available
    if timescaledb_available:
        # 3. Add retention policy: automatically delete data older than 90 days
        op.execute("""
            SELECT add_retention_policy(
                'decision_log',
                INTERVAL '90 days',
                if_not_exists => TRUE
            );
        """)
        print("✓ 90-day retention policy added")

        # 4. Enable compression for chunks older than 7 days
        op.execute("""
            ALTER TABLE decision_log SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'agent_id, symbol',
                timescaledb.compress_orderby = 'decided_at DESC'
            );
        """)

        op.execute("""
            SELECT add_compression_policy(
                'decision_log',
                INTERVAL '7 days',
                if_not_exists => TRUE
            );
        """)
        print("✓ Compression policy added (7-day threshold)")

        # 5. Create continuous aggregate for hourly metrics
        op.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS decision_log_hourly
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', decided_at) AS hour,
                agent_id,
                agent_type,
                symbol,
                decision_type,
                COUNT(*) AS decision_count,
                AVG(confidence) AS avg_confidence,
                AVG(decision_latency_ms) AS avg_latency_ms,
                COUNT(CASE WHEN was_executed = true THEN 1 END) AS executed_count,
                SUM(pnl_impact) AS total_pnl_impact,
                AVG(sharpe_impact) AS avg_sharpe_impact
            FROM decision_log
            GROUP BY hour, agent_id, agent_type, symbol, decision_type;
        """)

        op.execute("""
            SELECT add_continuous_aggregate_policy(
                'decision_log_hourly',
                start_offset => INTERVAL '3 hours',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '1 hour',
                if_not_exists => TRUE
            );
        """)
        print("✓ Continuous aggregate view created with refresh policy")
    else:
        print("⚠ Skipping TimescaleDB-specific features (retention, compression, continuous aggregates)")

    print("\n✓ Migration 011 completed successfully")
    print(f"  - Indexes created: 8")
    print(f"  - TimescaleDB features: {'enabled' if timescaledb_available else 'disabled (extension not available)'}")


def downgrade():
    """Remove TimescaleDB features and revert to standard table."""

    # 1. Drop continuous aggregate and its policy
    op.execute("DROP MATERIALIZED VIEW IF EXISTS decision_log_hourly CASCADE;")

    # 2. Remove compression policy and disable compression
    op.execute("""
        SELECT remove_compression_policy('decision_log', if_exists => TRUE);
    """)

    op.execute("""
        ALTER TABLE decision_log SET (
            timescaledb.compress = false
        );
    """)

    # 3. Remove retention policy
    op.execute("""
        SELECT remove_retention_policy('decision_log', if_exists => TRUE);
    """)

    # 4. Drop additional indexes (created in upgrade)
    op.execute("DROP INDEX IF EXISTS idx_decision_log_input_data_gin;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_decision_data_gin;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_execution_result_gin;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_executed_time;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_high_latency;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_pnl_impact;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_confidence;")
    op.execute("DROP INDEX IF EXISTS idx_decision_log_model_version;")

    # 5. Note: Cannot easily revert hypertable to regular table without data loss
    # In production, this would require a full data migration
    # For now, we leave it as a hypertable but with policies removed
    print("WARNING: Hypertable conversion not reverted. Manual intervention required for full downgrade.")
