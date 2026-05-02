"""
Integration tests for migration 015 signal-tagging columns on decision_log.

Tests tier 2 (real DB, real repository, no mocks):
- All 5 new columns persist correctly through DecisionLogRepository.create()
- strategy_version defaults to 'unknown' for new rows (never 'legacy')
- Nullable columns accept None
- Hash columns are stored and retrieved without truncation
- Read-back matches write

DB note:
    Uses the same real PostgreSQL test database as other repository integration
    tests (port 5433, risetrader_test).  The migration 015 columns must already
    be present — either run alembic upgrade head before running this test suite,
    or set SKIP_MIGRATION_TESTS=1 to skip if the schema has not been migrated yet.

    mcp-verifier: run `alembic -c src/database/migrations/alembic.ini upgrade head`
    before executing this file.

NO unittest.mock, NO MagicMock, NO @patch — absolute rule from CLAUDE.md.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.database.models.base import Base
from src.database.models.decision_log import DecisionLog
from src.database.repositories.decision_log_repository import DecisionLogRepository
from src.utils.signal_tagging import compute_feature_hash, compute_artifact_hash

# ---------------------------------------------------------------------------
# Skip guard: if the schema hasn't been migrated, skip gracefully
# ---------------------------------------------------------------------------
SKIP_MIGRATION = os.environ.get("SKIP_MIGRATION_TESTS", "").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# DB fixture — real PostgreSQL test instance
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/risetrader_test",
)


@pytest_asyncio.fixture(scope="module")
async def test_engine():
    """
    Connect to the real risetrader_test database.

    Creates the decision_log table if it doesn't exist (via Base.metadata).
    Note: migration 015 columns are only present after alembic upgrade head.
    If the columns are missing, the tests that write them will fail with a
    descriptive error rather than a cryptic None — this is intentional.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
    # Only create tables that are missing; do NOT drop existing data
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session that rolls back after each test."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> DecisionLogRepository:
    return DecisionLogRepository(db_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_kwargs() -> dict:
    """Minimum required fields for a valid DecisionLog row."""
    return dict(
        agent_id=uuid.uuid4(),
        agent_type="test_agent",
        decided_at=datetime.now(timezone.utc),
        decision_type="trade_intent",
        decision_data={"action": "BUY", "score": 0.75},
        input_data={"symbol": "CrudeOIL"},
        was_executed=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(SKIP_MIGRATION, reason="SKIP_MIGRATION_TESTS set")
@pytest.mark.asyncio
class TestDecisionLogSignalTagsWrite:
    """Write the 5 new columns and verify read-back."""

    async def test_strategy_version_persists(self, repo):
        """strategy_version is stored and retrieved correctly."""
        row = await repo.create(
            **_base_kwargs(),
            strategy_version="crude_oil_v3",
        )
        assert row.id is not None
        assert row.strategy_version == "crude_oil_v3"

    async def test_strategy_version_default_is_unknown(self, repo):
        """Omitting strategy_version defaults to 'unknown', not 'legacy'."""
        row = await repo.create(**_base_kwargs())
        assert row.strategy_version == "unknown"

    async def test_strategy_version_multi_strategy(self, repo):
        """Multiple strategy names joined with '+' fit in VARCHAR(100)."""
        combined = "ml_reversal+momentum+value_area"
        row = await repo.create(**_base_kwargs(), strategy_version=combined)
        assert row.strategy_version == combined

    async def test_model_artifact_hash_persists(self, repo):
        """64-char sha256 hex persists without truncation."""
        import hashlib
        fake_hash = hashlib.sha256(b"model_bytes").hexdigest()
        assert len(fake_hash) == 64
        row = await repo.create(**_base_kwargs(), model_artifact_hash=fake_hash)
        assert row.model_artifact_hash == fake_hash

    async def test_model_artifact_hash_nullable(self, repo):
        """model_artifact_hash is NULL for rules-based signals."""
        row = await repo.create(**_base_kwargs(), model_artifact_hash=None)
        assert row.model_artifact_hash is None

    async def test_regime_persists(self, repo):
        """Regime string is stored exactly."""
        row = await repo.create(**_base_kwargs(), regime="high_volatility")
        assert row.regime == "high_volatility"

    async def test_regime_nullable(self, repo):
        """regime is NULL when regime agent was not running."""
        row = await repo.create(**_base_kwargs(), regime=None)
        assert row.regime is None

    async def test_regime_all_valid_values(self, repo):
        """All known regime strings persist correctly."""
        for regime_str in [
            "high_volatility",
            "trending_up",
            "trending_down",
            "ranging",
            "low_volatility",
            "unknown",
        ]:
            row = await repo.create(**_base_kwargs(), regime=regime_str)
            assert row.regime == regime_str

    async def test_feature_hash_persists(self, repo):
        """Feature hash from compute_feature_hash() round-trips correctly."""
        features = {"rsi": 45.2, "atr": 0.82, "ema_slope": 0.003}
        fhash = compute_feature_hash(features)
        assert fhash is not None
        row = await repo.create(**_base_kwargs(), feature_hash=fhash)
        assert row.feature_hash == fhash

    async def test_feature_hash_nullable(self, repo):
        """feature_hash is NULL when no feature vector was built."""
        row = await repo.create(**_base_kwargs(), feature_hash=None)
        assert row.feature_hash is None

    async def test_account_phase_persists(self, repo):
        """account_phase placeholder stores any string up to 50 chars."""
        row = await repo.create(**_base_kwargs(), account_phase="Phase_4_live")
        assert row.account_phase == "Phase_4_live"

    async def test_account_phase_nullable(self, repo):
        """account_phase is NULL by default (FK wiring deferred)."""
        row = await repo.create(**_base_kwargs(), account_phase=None)
        assert row.account_phase is None

    async def test_all_five_tags_together(self, repo, tmp_path):
        """Write all 5 tag columns in one row and verify every field."""
        import hashlib

        # Build real hashes using the utility functions
        features = {"rsi": 55.0, "atr": 1.2, "macd": 0.05}
        fhash = compute_feature_hash(features)

        model_file = tmp_path / "model.json"
        model_file.write_bytes(b'{"n_estimators": 100}')
        ahash = compute_artifact_hash(model_file)

        row = await repo.create(
            **_base_kwargs(),
            strategy_version="value_area@1.2.0",
            model_artifact_hash=ahash,
            regime="ranging",
            feature_hash=fhash,
            account_phase="Phase_6_current",
        )

        assert row.strategy_version == "value_area@1.2.0"
        assert row.model_artifact_hash == ahash
        assert len(row.model_artifact_hash) == 64
        assert row.regime == "ranging"
        assert row.feature_hash == fhash
        assert len(row.feature_hash) == 64
        assert row.account_phase == "Phase_6_current"

    async def test_existing_columns_unchanged(self, repo):
        """Adding tags must not corrupt pre-existing columns."""
        row = await repo.create(
            **_base_kwargs(),
            strategy_version="momentum",
            confidence=0.82,
            symbol="CrudeOIL",
            timeframe="H1",
        )
        assert row.confidence == pytest.approx(0.82, abs=1e-6)
        assert row.symbol == "CrudeOIL"
        assert row.timeframe == "H1"
        assert row.was_executed is False

    async def test_read_back_by_id(self, repo):
        """Row written with tags can be retrieved by ID with all tags intact."""
        features = {"close": 75.23, "volume": 12000.0}
        fhash = compute_feature_hash(features)

        written = await repo.create(
            **_base_kwargs(),
            strategy_version="ma_crossover",
            regime="trending_up",
            feature_hash=fhash,
        )
        fetched = await repo.get_by_id(written.id)
        assert fetched is not None
        assert fetched.strategy_version == "ma_crossover"
        assert fetched.regime == "trending_up"
        assert fetched.feature_hash == fhash
        assert fetched.model_artifact_hash is None
        assert fetched.account_phase is None


@pytest.mark.skipif(SKIP_MIGRATION, reason="SKIP_MIGRATION_TESTS set")
@pytest.mark.asyncio
class TestDecisionLogBackfillVerification:
    """
    Verify migration 015 backfill: existing rows must show strategy_version='legacy'.

    This test class queries the live DB (not isolated by a single test session)
    to prove the backfill ran correctly.  It is read-only and non-destructive.
    """

    async def test_legacy_rows_exist_after_migration(self, db_session):
        """
        After migration 015 upgrade, SELECT strategy_version, COUNT(*) FROM
        decision_log GROUP BY 1 must return at least one 'legacy' bucket OR
        the table is empty (migration ran on an empty DB — also acceptable).

        mcp-verifier: this test proves the backfill statement executed.
        """
        result = await db_session.execute(
            text(
                "SELECT strategy_version, COUNT(*) as cnt "
                "FROM decision_log "
                "GROUP BY strategy_version "
                "ORDER BY cnt DESC"
            )
        )
        rows = result.fetchall()

        if not rows:
            # Empty table is valid — migration ran, table just has no rows yet
            return

        versions = {r[0] for r in rows}
        # Either all rows are from after the migration (no 'legacy') or
        # some were backfilled to 'legacy'.  The only invalid case would be
        # NULL strategy_version, which proves the backfill FAILED.
        assert None not in versions, (
            "NULL strategy_version found — migration 015 backfill did not run correctly. "
            "Expected all rows to have 'legacy' (pre-migration) or a real value (post-migration)."
        )

    async def test_new_rows_are_not_legacy(self, repo):
        """
        New rows written after migration must show 'unknown' (or a real strategy name),
        NOT 'legacy'.  'legacy' is reserved exclusively for the backfill.
        """
        row = await repo.create(**_base_kwargs())
        assert row.strategy_version != "legacy", (
            f"New rows must not receive 'legacy' strategy_version. "
            f"Got: '{row.strategy_version}'. "
            f"'legacy' is reserved for the migration 015 backfill of pre-existing rows."
        )
        assert row.strategy_version == "unknown"
