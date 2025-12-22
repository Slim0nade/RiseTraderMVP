"""
Trading repository for unified access to account, positions, and trading history.

Provides high-level API for the Dashboard API endpoints with keyset pagination support.
"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.account import AccountInfo
from ..models.positions import OpenPosition
from ..models.trading_history import TradingHistory
from .base import BaseRepository


class TradingRepository:
    """
    Unified trading repository for Dashboard API.

    Combines account info, positions, and trading history with pagination support.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize trading repository.

        Args:
            session: Async database session
        """
        self.session = session

    # =============================================================================
    # Account Info Methods (T030)
    # =============================================================================

    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        Get latest account information.

        Returns:
            Latest AccountInfo record or None if no account data

        Example:
            account = await trading_repo.get_account_info()
            if account:
                print(f"Balance: {account.balance}, Equity: {account.equity}")
        """
        query = (
            select(AccountInfo)
            .order_by(desc(AccountInfo.time))
            .limit(1)
        )

        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_account_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AccountInfo]:
        """
        Get account info history for time range.

        Args:
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum number of records to return

        Returns:
            List of AccountInfo records ordered by time (newest first)
        """
        query = select(AccountInfo)

        if start_time:
            query = query.where(AccountInfo.time >= start_time)

        if end_time:
            query = query.where(AccountInfo.time <= end_time)

        query = query.order_by(desc(AccountInfo.time)).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # =============================================================================
    # Position Methods (T031)
    # =============================================================================

    async def get_open_positions(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[OpenPosition]:
        """
        Get all open positions with optional symbol filter.

        Args:
            symbol: Optional symbol to filter positions
            limit: Maximum number of positions to return

        Returns:
            List of OpenPosition records

        Example:
            # Get all open positions
            positions = await trading_repo.get_open_positions()

            # Get positions for specific symbol
            crude_positions = await trading_repo.get_open_positions(symbol="CrudeOIL")
        """
        query = select(OpenPosition)

        if symbol:
            query = query.where(OpenPosition.symbol == symbol)

        query = query.order_by(desc(OpenPosition.last_update)).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_position_by_number(self, number: str) -> Optional[OpenPosition]:
        """
        Get specific position by position number.

        Args:
            number: Position number (ticket)

        Returns:
            OpenPosition or None if not found
        """
        query = select(OpenPosition).where(OpenPosition.number == number)

        result = await self.session.execute(query)
        return result.scalars().first()

    # =============================================================================
    # Trading History Methods with Keyset Pagination (T032)
    # =============================================================================

    async def get_trading_history(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        trade_type: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Tuple[List[TradingHistory], Optional[str]]:
        """
        Get trading history with keyset pagination support.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            trade_type: Optional trade type filter ("BUY" or "SELL")
            cursor: Keyset pagination cursor (format: "timestamp_id")
            limit: Number of records to return

        Returns:
            Tuple of (list of TradingHistory records, next_cursor)

        Example:
            # First page
            trades, next_cursor = await trading_repo.get_trading_history(
                symbol="CrudeOIL",
                limit=50
            )

            # Next page
            more_trades, cursor = await trading_repo.get_trading_history(
                symbol="CrudeOIL",
                cursor=next_cursor,
                limit=50
            )
        """
        query = select(TradingHistory)

        # Apply filters
        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if start_date:
            query = query.where(TradingHistory.close_time >= start_date)

        if end_date:
            query = query.where(TradingHistory.close_time <= end_date)

        if trade_type:
            query = query.where(TradingHistory.type == trade_type)

        # Apply keyset pagination
        if cursor:
            try:
                # Cursor format: "timestamp_id"
                cursor_parts = cursor.split("_")
                cursor_time = datetime.fromisoformat(cursor_parts[0])
                cursor_id = int(cursor_parts[1])

                # Continue from cursor position
                query = query.where(
                    (TradingHistory.close_time < cursor_time) |
                    (
                        (TradingHistory.close_time == cursor_time) &
                        (TradingHistory.id < cursor_id)
                    )
                )
            except (ValueError, IndexError):
                # Invalid cursor - ignore and start from beginning
                pass

        # Order and limit
        query = query.order_by(
            desc(TradingHistory.close_time),
            desc(TradingHistory.id)
        ).limit(limit + 1)  # Fetch one extra to determine if there's a next page

        result = await self.session.execute(query)
        records = list(result.scalars().all())

        # Calculate next cursor
        next_cursor = None
        if len(records) > limit:
            # There's a next page
            last_record = records[limit - 1]
            next_cursor = f"{last_record.close_time.isoformat()}_{last_record.id}"
            records = records[:limit]  # Trim the extra record

        return records, next_cursor

    async def get_recent_trades(
        self,
        limit: int = 10,
        symbol: Optional[str] = None,
    ) -> List[TradingHistory]:
        """
        Get most recent closed trades.

        Args:
            limit: Number of recent trades to return
            symbol: Optional symbol filter

        Returns:
            List of TradingHistory records (newest first)
        """
        query = select(TradingHistory)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        query = query.order_by(desc(TradingHistory.close_time)).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_trade_by_number(self, number: str) -> Optional[TradingHistory]:
        """
        Get specific trade by trade number.

        Args:
            number: Trade number (ticket)

        Returns:
            TradingHistory or None if not found
        """
        query = select(TradingHistory).where(TradingHistory.number == number)

        result = await self.session.execute(query)
        return result.scalars().first()

    # =============================================================================
    # Aggregate Methods
    # =============================================================================

    async def get_total_profit(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
    ) -> float:
        """
        Calculate total profit for time range.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            symbol: Optional symbol filter

        Returns:
            Total profit (sum of all trade profits)
        """
        from sqlalchemy import func

        query = select(func.sum(TradingHistory.profit))

        if start_date:
            query = query.where(TradingHistory.close_time >= start_date)

        if end_date:
            query = query.where(TradingHistory.close_time <= end_date)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        result = await self.session.execute(query)
        total = result.scalar()

        return float(total) if total else 0.0

    async def get_trade_count(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
        trade_type: Optional[str] = None,
    ) -> int:
        """
        Count trades matching filters.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            symbol: Optional symbol filter
            trade_type: Optional trade type filter

        Returns:
            Number of matching trades
        """
        from sqlalchemy import func

        query = select(func.count(TradingHistory.id))

        if start_date:
            query = query.where(TradingHistory.close_time >= start_date)

        if end_date:
            query = query.where(TradingHistory.close_time <= end_date)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if trade_type:
            query = query.where(TradingHistory.type == trade_type)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_position_by_id(self, position_id: int) -> Optional[OpenPosition]:
        """
        Get position by ID.

        Args:
            position_id: Position ID

        Returns:
            OpenPosition or None if not found
        """
        query = select(OpenPosition).where(OpenPosition.id == position_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_trade_by_id(self, trade_id: int) -> Optional[TradingHistory]:
        """
        Get trade by ID.

        Args:
            trade_id: Trade ID

        Returns:
            TradingHistory or None if not found
        """
        query = select(TradingHistory).where(TradingHistory.id == trade_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_trading_history(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        trade_type: Optional[str] = None,
    ) -> int:
        """
        Count trading history records with filters.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            trade_type: Optional trade type filter

        Returns:
            Total count of matching records
        """
        query = select(func.count()).select_from(TradingHistory)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)
        if start_date:
            query = query.where(TradingHistory.close_time >= start_date)
        if end_date:
            query = query.where(TradingHistory.close_time <= end_date)
        if trade_type:
            query = query.where(TradingHistory.trade_type == trade_type)

        result = await self.session.execute(query)
        return result.scalar() or 0
