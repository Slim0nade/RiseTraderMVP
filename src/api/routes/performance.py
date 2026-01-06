"""
Performance Analytics API Routes
"""
import structlog
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import TradingHistory, OpenPosition
from ..dependencies import get_db
from ..models import (
    PerformanceByStrategyResponse,
    PerformanceChartResponse,
    TradingPerformanceMetricsResponse,
    PerformanceSummaryResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PerformanceSummaryResponse:
    """Get overall performance summary."""
    try:
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        query = select(TradingHistory).where(
            TradingHistory.close_time >= start_date,
            TradingHistory.close_time <= end_date,
        )
        result = await db.execute(query)
        trades = result.scalars().all()

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.profit > 0)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        total_profit = sum(t.profit for t in trades if t.profit > 0)
        total_loss = abs(sum(t.profit for t in trades if t.profit < 0))
        net_profit = sum(t.profit for t in trades)

        avg_win = Decimal(total_profit / winning_trades) if winning_trades > 0 else Decimal(0)
        avg_loss = Decimal(total_loss / losing_trades) if losing_trades > 0 else Decimal(0)

        profit_factor = Decimal(total_profit / total_loss) if total_loss > 0 else None

        return PerformanceSummaryResponse(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 2),
            total_profit=Decimal(total_profit),
            total_loss=Decimal(total_loss),
            net_profit=Decimal(net_profit),
            average_win=avg_win,
            average_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=None,  # TODO: Calculate
            max_drawdown_percent=None,
            sharpe_ratio=None,  # TODO: Calculate
            current_balance=Decimal(50000 + net_profit),  # TODO: Get from account
            period_start=start_date,
            period_end=end_date,
        )
    except Exception as e:
        logger.error("get_performance_summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=TradingPerformanceMetricsResponse)
async def get_performance_metrics(
    db: AsyncSession = Depends(get_db),
) -> TradingPerformanceMetricsResponse:
    """Get detailed performance metrics (placeholder)."""
    logger.warning("get_performance_metrics_not_fully_implemented")
    return TradingPerformanceMetricsResponse(
        total_trades=0,
        open_positions=0,
        closed_positions=0,
        gross_profit=Decimal(0),
        gross_loss=Decimal(0),
        net_profit=Decimal(0),
        profit_factor=None,
        win_rate=0.0,
        average_win=Decimal(0),
        average_loss=Decimal(0),
        largest_win=Decimal(0),
        largest_loss=Decimal(0),
        average_trade=Decimal(0),
        max_drawdown=None,
        max_drawdown_pct=None,
        current_drawdown=None,
        sharpe_ratio=None,
        sortino_ratio=None,
        calmar_ratio=None,
        consecutive_wins=0,
        consecutive_losses=0,
        max_consecutive_wins=0,
        max_consecutive_losses=0,
        starting_balance=Decimal(50000),
        current_balance=Decimal(50000),
        peak_balance=Decimal(50000),
        total_return=Decimal(0),
        total_return_pct=0.0,
        period_start=datetime.utcnow() - timedelta(days=30),
        period_end=datetime.utcnow(),
        trading_days=30,
    )


@router.get("/by-strategy", response_model=PerformanceByStrategyResponse)
async def get_performance_by_strategy(
    db: AsyncSession = Depends(get_db),
) -> PerformanceByStrategyResponse:
    """Get performance breakdown by strategy (placeholder)."""
    summary = await get_performance_summary(db=db)
    return PerformanceByStrategyResponse(
        strategies=[],
        total_strategies=0,
        overall_performance=summary,
    )


@router.get("/chart", response_model=PerformanceChartResponse)
async def get_performance_chart(
    db: AsyncSession = Depends(get_db),
) -> PerformanceChartResponse:
    """Get chart data for equity curve (placeholder)."""
    return PerformanceChartResponse(
        equity_curve=[],
        start_date=datetime.utcnow() - timedelta(days=30),
        end_date=datetime.utcnow(),
        period_type="daily",
    )


@router.get("/equity-curve")
async def get_equity_curve(
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get equity curve data over time.
    Returns timestamp, equity, and drawdown values.
    """
    try:
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Query trading history to build equity curve
        query = select(TradingHistory).where(
            TradingHistory.close_time >= start_date,
            TradingHistory.close_time <= end_date,
        ).order_by(TradingHistory.close_time)

        result = await db.execute(query)
        trades = result.scalars().all()

        # Build equity curve from cumulative P&L
        initial_balance = Decimal("50000")  # TODO: Get from account settings
        equity_curve = []
        current_equity = initial_balance
        peak_equity = initial_balance

        for trade in trades:
            current_equity += trade.profit
            peak_equity = max(peak_equity, current_equity)
            drawdown = current_equity - peak_equity

            equity_curve.append({
                "timestamp": trade.close_time.isoformat(),
                "equity": float(current_equity),
                "drawdown": float(drawdown),
            })

        logger.info(
            "get_equity_curve_success",
            points=len(equity_curve),
            start=start_date,
            end=end_date,
        )

        return equity_curve

    except Exception as e:
        logger.error("get_equity_curve_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-pnl")
async def get_daily_pnl(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Get daily P&L aggregated by date.
    Returns date and pnl for each trading day.
    """
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Query trading history and aggregate by day
        query = select(
            func.date(TradingHistory.close_time).label('date'),
            func.sum(TradingHistory.profit).label('pnl'),
            func.count(TradingHistory.id).label('trades')
        ).where(
            TradingHistory.close_time >= start_date,
            TradingHistory.close_time <= end_date,
        ).group_by(
            func.date(TradingHistory.close_time)
        ).order_by(
            func.date(TradingHistory.close_time)
        )

        result = await db.execute(query)
        daily_data = result.all()

        daily_pnl = [
            {
                "date": str(row.date),
                "pnl": float(row.pnl),
                "trades": row.trades,
            }
            for row in daily_data
        ]

        logger.info(
            "get_daily_pnl_success",
            days_requested=days,
            days_returned=len(daily_pnl),
        )

        return daily_pnl

    except Exception as e:
        logger.error("get_daily_pnl_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
