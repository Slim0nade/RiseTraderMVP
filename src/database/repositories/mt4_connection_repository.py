"""
MT4 Connection Repository for EA registry management.

Handles CRUD operations for MT4 Expert Advisor connections.
"""
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mt4_connection import MT4Connection
from .base import BaseRepository


class MT4ConnectionRepository(BaseRepository[MT4Connection]):
    """
    Repository for MT4 EA connection management.

    Provides methods for EA registration, health monitoring, and status tracking.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize MT4 connection repository.

        Args:
            session: Async database session
        """
        super().__init__(MT4Connection, session)

    async def get_by_ea_id(self, ea_id: str) -> Optional[MT4Connection]:
        """
        Get connection by EA ID.

        Args:
            ea_id: Human-readable EA identifier

        Returns:
            MT4Connection instance or None
        """
        query = select(MT4Connection).where(MT4Connection.ea_id == ea_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_magic_number(self, magic_number: int) -> Optional[MT4Connection]:
        """
        Get connection by magic number.

        Args:
            magic_number: MT4 magic number

        Returns:
            MT4Connection instance or None
        """
        query = select(MT4Connection).where(
            MT4Connection.magic_number == magic_number
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_connections(self) -> List[MT4Connection]:
        """
        Get all active EA connections.

        Returns:
            List of active MT4Connection instances
        """
        query = select(MT4Connection).where(MT4Connection.status == 'ACTIVE')
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_status(self, status: str) -> List[MT4Connection]:
        """
        Get all connections with specific status.

        Args:
            status: Connection status (ACTIVE, INACTIVE, ERROR, RECONNECTING)

        Returns:
            List of MT4Connection instances
        """
        query = select(MT4Connection).where(MT4Connection.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stale_connections(
        self,
        heartbeat_timeout_seconds: int = 90
    ) -> List[MT4Connection]:
        """
        Get connections with stale heartbeats.

        Args:
            heartbeat_timeout_seconds: Maximum seconds since last heartbeat

        Returns:
            List of stale MT4Connection instances
        """
        cutoff_time = datetime.utcnow() - timedelta(seconds=heartbeat_timeout_seconds)

        query = select(MT4Connection).where(
            MT4Connection.status == 'ACTIVE',
            MT4Connection.last_heartbeat < cutoff_time
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_heartbeat(self, ea_id: str) -> Optional[MT4Connection]:
        """
        Update last heartbeat timestamp for EA.

        Args:
            ea_id: EA identifier

        Returns:
            Updated MT4Connection instance or None
        """
        query = (
            update(MT4Connection)
            .where(MT4Connection.ea_id == ea_id)
            .values(
                last_heartbeat=datetime.utcnow(),
                error_count=0,  # Reset error count on successful heartbeat
                updated_at=datetime.utcnow()
            )
            .returning(MT4Connection)
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def update_status(
        self,
        ea_id: str,
        status: str,
        increment_errors: bool = False
    ) -> Optional[MT4Connection]:
        """
        Update connection status.

        Args:
            ea_id: EA identifier
            status: New status (ACTIVE, INACTIVE, ERROR, RECONNECTING)
            increment_errors: Whether to increment error count

        Returns:
            Updated MT4Connection instance or None
        """
        values = {
            "status": status,
            "updated_at": datetime.utcnow()
        }

        if increment_errors:
            # Increment error_count using database-side increment
            query = select(MT4Connection).where(MT4Connection.ea_id == ea_id)
            result = await self.session.execute(query)
            conn = result.scalar_one_or_none()

            if conn:
                values["error_count"] = conn.error_count + 1

        query = (
            update(MT4Connection)
            .where(MT4Connection.ea_id == ea_id)
            .values(**values)
            .returning(MT4Connection)
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def is_magic_number_available(self, magic_number: int) -> bool:
        """
        Check if magic number is available (not in use).

        Args:
            magic_number: Magic number to check

        Returns:
            True if available, False if already in use
        """
        query = select(MT4Connection).where(
            MT4Connection.magic_number == magic_number
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is None

    async def is_port_available(self, port: int) -> bool:
        """
        Check if port is available (not in use).

        Args:
            port: Port number to check

        Returns:
            True if available, False if already in use
        """
        query = select(MT4Connection).where(
            (MT4Connection.rep_port == port) | (MT4Connection.pub_port == port)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is None

    async def get_next_available_magic_number(
        self,
        min_value: int = 100000,
        max_value: int = 999999
    ) -> Optional[int]:
        """
        Get next available magic number in sequence.

        Args:
            min_value: Minimum magic number value
            max_value: Maximum magic number value

        Returns:
            Next available magic number or None if range exhausted
        """
        query = select(MT4Connection.magic_number).order_by(
            MT4Connection.magic_number.desc()
        ).limit(1)

        result = await self.session.execute(query)
        last_magic = result.scalar_one_or_none()

        if last_magic is None:
            # No connections yet, start from min_value
            return min_value

        next_magic = last_magic + 1

        if next_magic > max_value:
            # Range exhausted
            return None

        return next_magic

    async def delete_by_ea_id(self, ea_id: str) -> bool:
        """
        Delete connection by EA ID.

        Args:
            ea_id: EA identifier

        Returns:
            True if deleted, False if not found
        """
        connection = await self.get_by_ea_id(ea_id)
        if connection is None:
            return False

        await self.session.delete(connection)
        await self.session.commit()
        return True

    async def count_by_status(self, status: str) -> int:
        """
        Count connections by status.

        Args:
            status: Connection status

        Returns:
            Count of connections
        """
        query = select(MT4Connection).where(MT4Connection.status == status)
        result = await self.session.execute(query)
        return len(list(result.scalars().all()))

    async def get_connection_health_summary(self) -> dict:
        """
        Get summary of connection health across all EAs.

        Returns:
            Dictionary with health metrics
        """
        all_connections = await self.get_all(limit=1000)

        summary = {
            "total": len(all_connections),
            "active": 0,
            "inactive": 0,
            "error": 0,
            "reconnecting": 0,
            "healthy": 0,
            "stale": 0
        }

        for conn in all_connections:
            summary[conn.status.lower()] = summary.get(conn.status.lower(), 0) + 1

            if conn.is_healthy():
                summary["healthy"] += 1
            else:
                summary["stale"] += 1

        return summary
