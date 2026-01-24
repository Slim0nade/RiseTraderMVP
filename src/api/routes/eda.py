"""
EDA (Exploratory Data Analysis) API Routes

Automated data quality analysis, distributions, correlations, and comparisons
for market data. Helps validate data integrity before backtesting and ML training.
"""
import structlog
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData
from ..dependencies import get_db
from src.services.eda.data_quality import DataQualityAnalyzer

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/eda", tags=["eda"])


async def fetch_market_data_df(
    db: AsyncSession,
    symbol: str,
    timeframe: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = None
) -> pd.DataFrame:
    """
    Fetch market data from database and convert to pandas DataFrame.

    Args:
        db: Database session
        symbol: Trading symbol
        timeframe: Candle timeframe
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Optional row limit

    Returns:
        DataFrame with columns [time, open, high, low, close, volume]
    """
    # Build query
    query = select(MarketData).where(
        and_(
            MarketData.symbol == symbol,
            MarketData.timeframe == timeframe
        )
    )

    if start_date:
        query = query.where(MarketData.time >= start_date)
    if end_date:
        query = query.where(MarketData.time <= end_date)

    query = query.order_by(MarketData.time.desc())

    if limit:
        query = query.limit(limit)

    result = await db.execute(query)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for {symbol} {timeframe}"
        )

    # Convert to DataFrame
    data = []
    for row in rows:
        data.append({
            'time': row.time,
            'open': float(row.open) if isinstance(row.open, (str, int)) else row.open,
            'high': float(row.high) if isinstance(row.high, (str, int)) else row.high,
            'low': float(row.low) if isinstance(row.low, (str, int)) else row.low,
            'close': float(row.close) if isinstance(row.close, (str, int)) else row.close,
            'volume': int(row.volume) if isinstance(row.volume, (str, float)) else row.volume,
        })

    df = pd.DataFrame(data)
    df = df.sort_values('time').reset_index(drop=True)

    logger.info("market_data_fetched", symbol=symbol, timeframe=timeframe, rows=len(df))

    return df


@router.get("/quality/{symbol}")
async def get_data_quality(
    symbol: str,
    timeframe: str = Query("M5", description="Candle timeframe"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive data quality analysis."""
    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        df = await fetch_market_data_df(db, symbol, timeframe, start_dt, end_dt, limit=50000)

        analyzer = DataQualityAnalyzer(df)
        result = analyzer.analyze()

        response = {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "data_points": len(df),
            "date_range": {
                "start": df['time'].min().isoformat(),
                "end": df['time'].max().isoformat()
            },
            "checks": result["checks"],
            "issues": result["issues"],
            "score": result["score"]
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("data_quality_analysis_failed", symbol=symbol, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data quality analysis failed: {str(e)}"
        )
