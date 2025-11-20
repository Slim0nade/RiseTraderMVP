"""
Trading history repository for completed trades.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.trading_history import TradingHistory
from .base import BaseRepository


class TradingHistoryRepository(BaseRepository[TradingHistory]):
    """
    Repository for trading history and completed trades.

    Provides analytics and reporting on trade performance.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(TradingHistory, session)

    async def get_trades_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
        simulation: Optional[bool] = None,
    ) -> List[TradingHistory]:
        """
        Get trades for a specific symbol.

        Args:
            symbol: Trading symbol
            limit: Maximum number of records
            simulation: Optional simulation filter

        Returns:
            List of TradingHistory instances ordered by time
        """
        query = (
            select(TradingHistory)
            .where(TradingHistory.symbol == symbol)
            .order_by(desc(TradingHistory.time))
            .limit(limit)
        )

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_trades_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        symbol: Optional[str] = None,
        simulation: Optional[bool] = None,
    ) -> List[TradingHistory]:
        """
        Get trades within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            symbol: Optional symbol filter
            simulation: Optional simulation filter

        Returns:
            List of TradingHistory instances
        """
        query = select(TradingHistory).where(
            and_(
                TradingHistory.time >= start_date,
                TradingHistory.time <= end_date,
            )
        )

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        query = query.order_by(TradingHistory.time)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_performance_metrics(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        simulation: Optional[bool] = None,
    ) -> Dict[str, any]:
        """
        Calculate performance metrics for trades.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date
            end_date: Optional end date
            simulation: Optional simulation filter

        Returns:
            Dictionary with performance metrics
        """
        query = select(TradingHistory)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if start_date:
            query = query.where(TradingHistory.time >= start_date)

        if end_date:
            query = query.where(TradingHistory.time <= end_date)

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        result = await self.session.execute(query)
        trades = list(result.scalars().all())

        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "average_profit": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0,
                "profit_factor": 0.0,
            }

        profitable_trades = [t for t in trades if t.is_profitable]
        losing_trades = [t for t in trades if t.profit and t.profit < 0]

        total_profit = sum(float(t.profit) for t in trades if t.profit)
        winning_profit = sum(float(t.profit) for t in profitable_trades if t.profit)
        losing_profit = abs(sum(float(t.profit) for t in losing_trades if t.profit))

        return {
            "total_trades": len(trades),
            "winning_trades": len(profitable_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(profitable_trades) / len(trades) * 100 if trades else 0.0,
            "total_profit": total_profit,
            "average_profit": total_profit / len(trades) if trades else 0.0,
            "average_win": (
                winning_profit / len(profitable_trades)
                if profitable_trades
                else 0.0
            ),
            "average_loss": (
                losing_profit / len(losing_trades) if losing_trades else 0.0
            ),
            "profit_factor": (
                winning_profit / losing_profit if losing_profit > 0 else 0.0
            ),
        }

    async def get_daily_pnl(
        self,
        start_date: datetime,
        end_date: datetime,
        symbol: Optional[str] = None,
        simulation: Optional[bool] = None,
    ) -> List[Dict[str, any]]:
        """
        Get daily P&L aggregates.

        Args:
            start_date: Start date
            end_date: End date
            symbol: Optional symbol filter
            simulation: Optional simulation filter

        Returns:
            List of daily P&L dictionaries
        """
        query = select(
            func.date(TradingHistory.time).label("date"),
            func.count(TradingHistory.id).label("trades"),
            func.sum(TradingHistory.profit).label("profit"),
        ).where(
            and_(
                TradingHistory.time >= start_date,
                TradingHistory.time <= end_date,
            )
        )

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        query = query.group_by(func.date(TradingHistory.time)).order_by(
            func.date(TradingHistory.time)
        )

        result = await self.session.execute(query)
        return [
            {
                "date": row.date.isoformat(),
                "trades": row.trades,
                "profit": float(row.profit) if row.profit else 0.0,
            }
            for row in result.all()
        ]

    async def get_symbol_performance(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        simulation: Optional[bool] = None,
    ) -> List[Dict[str, any]]:
        """
        Get performance metrics by symbol.

        Args:
            start_date: Optional start date
            end_date: Optional end date
            simulation: Optional simulation filter

        Returns:
            List of symbol performance dictionaries
        """
        query = select(
            TradingHistory.symbol,
            func.count(TradingHistory.id).label("trades"),
            func.sum(TradingHistory.profit).label("total_profit"),
            func.avg(TradingHistory.profit).label("avg_profit"),
        )

        if start_date:
            query = query.where(TradingHistory.time >= start_date)

        if end_date:
            query = query.where(TradingHistory.time <= end_date)

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        query = query.group_by(TradingHistory.symbol).order_by(
            desc(func.sum(TradingHistory.profit))
        )

        result = await self.session.execute(query)
        return [
            {
                "symbol": row.symbol,
                "trades": row.trades,
                "total_profit": float(row.total_profit) if row.total_profit else 0.0,
                "avg_profit": float(row.avg_profit) if row.avg_profit else 0.0,
            }
            for row in result.all()
        ]

    async def get_recent_trades(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        simulation: Optional[bool] = None,
    ) -> List[TradingHistory]:
        """
        Get most recent trades.

        Args:
            limit: Maximum number of records
            symbol: Optional symbol filter
            simulation: Optional simulation filter

        Returns:
            List of TradingHistory instances
        """
        query = select(TradingHistory).order_by(desc(TradingHistory.time)).limit(limit)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_total_pnl(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        simulation: Optional[bool] = None,
    ) -> Decimal:
        """
        Calculate total P&L.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date
            end_date: Optional end date
            simulation: Optional simulation filter

        Returns:
            Total P&L as Decimal
        """
        query = select(func.sum(TradingHistory.profit)).select_from(TradingHistory)

        if symbol:
            query = query.where(TradingHistory.symbol == symbol)

        if start_date:
            query = query.where(TradingHistory.time >= start_date)

        if end_date:
            query = query.where(TradingHistory.time <= end_date)

        if simulation is not None:
            query = query.where(TradingHistory.simulation == simulation)

        result = await self.session.execute(query)
        total = result.scalar()
        return Decimal(total) if total else Decimal(0)
