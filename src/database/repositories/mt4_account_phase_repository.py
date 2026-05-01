"""
Repository for MT4 account phase metadata (ForTrade broker pricing regimes).

Used by training pipelines, backtest engines, and live execution to filter
or annotate MT4 rows by their broker phase. The 6 known phases correspond
to detected regime changes in the BC-MT4 price offset.

Reference:
    .serena/memories/2026-04-29-mt4-broker-premium-and-correct-training-architecture.md
    src/database/migrations/versions/014_create_mt4_account_phases.py
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mt4_account_phase import MT4AccountPhase
from .base import BaseRepository


class MT4AccountPhaseRepository(BaseRepository[MT4AccountPhase]):
    """Repository for MT4 ForTrade broker phase metadata."""

    def __init__(self, session: AsyncSession):
        super().__init__(MT4AccountPhase, session)

    async def list_all(self) -> List[MT4AccountPhase]:
        """All phases ordered chronologically."""
        result = await self.session.execute(
            select(MT4AccountPhase).order_by(MT4AccountPhase.start_time)
        )
        return list(result.scalars().all())

    async def get_phase_at(self, ts: datetime) -> Optional[MT4AccountPhase]:
        """Return the phase containing `ts`, or None if no phase covers it."""
        result = await self.session.execute(
            select(MT4AccountPhase).where(
                MT4AccountPhase.start_time <= ts,
                or_(
                    MT4AccountPhase.end_time.is_(None),
                    MT4AccountPhase.end_time >= ts,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_current_phase(self) -> Optional[MT4AccountPhase]:
        """Return the open-ended current phase (end_time IS NULL)."""
        result = await self.session.execute(
            select(MT4AccountPhase).where(MT4AccountPhase.end_time.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_clean_phases(
        self, training: bool = False, execution: bool = False
    ) -> List[MT4AccountPhase]:
        """
        Phases marked usable for training and/or execution validation.

        Args:
            training: filter to phases with use_for_training = TRUE
            execution: filter to phases with use_for_execution_validation = TRUE

        Both flags can be combined; the result intersects them.
        """
        query = select(MT4AccountPhase)
        if training:
            query = query.where(MT4AccountPhase.use_for_training.is_(True))
        if execution:
            query = query.where(
                MT4AccountPhase.use_for_execution_validation.is_(True)
            )
        query = query.order_by(MT4AccountPhase.start_time)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_clean_phase_time_ranges(
        self, training: bool = False, execution: bool = False
    ) -> List[tuple[datetime, Optional[datetime]]]:
        """Convenience: return (start, end) tuples for clean phases.
        Useful for building OR-of-time-range filters in market_data queries.
        """
        phases = await self.list_clean_phases(
            training=training, execution=execution
        )
        return [(p.start_time, p.end_time) for p in phases]

    async def upsert_phase(self, phase: MT4AccountPhase) -> MT4AccountPhase:
        """Insert or update a phase definition."""
        existing = await self.session.get(MT4AccountPhase, phase.phase)
        if existing is None:
            self.session.add(phase)
            await self.session.flush()
            return phase
        # Update mutable fields
        for field in (
            "start_time", "end_time", "label", "mean_offset_bc_minus_mt4",
            "pct_premium", "intraday_std", "quality",
            "use_for_training", "use_for_execution_validation", "notes",
        ):
            setattr(existing, field, getattr(phase, field))
        await self.session.flush()
        return existing
