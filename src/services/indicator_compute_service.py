"""
Indicator Compute Service

Computes technical indicators (RSI, MACD, ATR, Bollinger Bands, MAs)
from market_data and stores them in the indicators table.

Extracted from scripts/compute_indicators.py for reuse by API routes,
MCP tools, and the training pipeline.
"""
import logging
from decimal import Decimal
from typing import Dict, List

import numpy as np
import pandas as pd
from sqlalchemy import and_, cast, delete, func, select, Text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData
from src.database.models.indicators import Indicators

logger = logging.getLogger(__name__)

# All symbols with sufficient H1 data for training
ALL_SYMBOLS = ["CrudeOIL", "XAUUSD", "GBPJPY", "BRENT_OIL", "USA500"]

# Minimum candles required to compute indicators (200 for MA_200)
MIN_CANDLES = 200

# Batch size for DB inserts
BATCH_SIZE = 5000


def compute_indicators_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical indicators from OHLCV DataFrame.

    Reuses the same math as TechnicalIndicatorsCalculator but vectorized
    over the entire DataFrame for bulk processing.

    Args:
        df: DataFrame with columns: open, high, low, close, volume
            Must be sorted by time ascending.

    Returns:
        DataFrame with added indicator columns: rsi, macd, macd_signal, atr,
        bb_upper, bb_middle, bb_lower, ma_20, ma_50, ma_200
    """
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # ---- RSI(14) ----
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # ---- MACD(12, 26, 9) ----
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # ---- ATR(14) ----
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(14).mean()

    # ---- Bollinger Bands(20, 2) ----
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_middle"] = sma20
    df["bb_lower"] = sma20 - 2 * std20

    # ---- Moving Averages ----
    df["ma_20"] = close.rolling(20).mean()
    df["ma_50"] = close.rolling(50).mean()
    df["ma_200"] = close.rolling(200).mean()

    return df


class IndicatorComputeService:
    """
    Service for computing and storing technical indicators.

    Usage:
        async with db.get_session() as session:
            service = IndicatorComputeService(session)
            result = await service.compute_for_symbol("CrudeOIL", "H1")
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def compute_for_symbol(
        self,
        symbol: str,
        timeframe: str,
        force: bool = False,
    ) -> Dict:
        """
        Compute and store indicators for one symbol/timeframe.

        Returns dict with stats about the computation.
        """
        # Check existing
        if not force:
            existing = await self._count_existing(symbol, timeframe)
            if existing > 0:
                logger.info(f"{symbol} {timeframe}: {existing} indicator rows exist. Use force=True to recompute.")
                return {"symbol": symbol, "timeframe": timeframe, "status": "skipped", "existing": existing}

        # Load candles
        logger.info(f"Loading {symbol} {timeframe} candles...")
        df = await self._load_candles(symbol, timeframe)

        if df.empty:
            logger.warning(f"{symbol} {timeframe}: No candle data found")
            return {"symbol": symbol, "timeframe": timeframe, "status": "no_data", "candles": 0}

        if len(df) < MIN_CANDLES:
            logger.warning(f"{symbol} {timeframe}: Only {len(df)} candles (need {MIN_CANDLES})")
            return {"symbol": symbol, "timeframe": timeframe, "status": "insufficient", "candles": len(df)}

        logger.info(f"{symbol} {timeframe}: {len(df)} candles loaded")

        # Compute indicators
        df = compute_indicators_df(df)

        # Insert to DB
        upserted = await self._insert_indicators(symbol, timeframe, df)
        logger.info(f"{symbol} {timeframe}: {upserted} indicator rows upserted")

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "success",
            "candles": len(df),
            "upserted": upserted,
        }

    async def compute_batch(
        self,
        symbols: List[str],
        timeframes: List[str],
        force: bool = False,
    ) -> List[Dict]:
        """Compute indicators for multiple symbol/timeframe pairs."""
        results = []
        for timeframe in timeframes:
            for symbol in symbols:
                result = await self.compute_for_symbol(symbol, timeframe, force=force)
                results.append(result)
        return results

    async def _load_candles(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load all OHLCV candles for a symbol/timeframe from market_data."""
        stmt = (
            select(
                MarketData.id,
                MarketData.time,
                MarketData.open,
                MarketData.high,
                MarketData.low,
                MarketData.last.label("close"),
                MarketData.volume,
            )
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                )
            )
            .order_by(MarketData.time.asc())
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["id", "time", "open", "high", "low", "close", "volume"])

        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        df["volume"] = df["volume"].astype(int)

        return df

    async def _count_existing(self, symbol: str, timeframe: str) -> int:
        """Count existing indicator rows for a symbol/timeframe."""
        stmt = (
            select(func.count(Indicators.id))
            .where(
                and_(
                    Indicators.symbol == symbol,
                    Indicators.timeframe == timeframe,
                    Indicators.rsi.isnot(None),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _insert_indicators(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> int:
        """Delete existing rows then bulk insert new indicator rows."""
        required_cols = ["rsi", "macd", "macd_signal", "atr", "bb_upper", "bb_middle", "bb_lower", "ma_20"]
        valid_mask = df[required_cols].notna().all(axis=1)
        valid_df = df[valid_mask].copy()

        if valid_df.empty:
            logger.warning(f"No valid indicator rows for {symbol} {timeframe}")
            return 0

        # Delete existing
        del_stmt = delete(Indicators).where(
            and_(
                Indicators.symbol == symbol,
                Indicators.timeframe == timeframe,
            )
        )
        result = await self.session.execute(del_stmt)
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Deleted {deleted} existing indicator rows for {symbol} {timeframe}")

        # Bulk insert
        total_inserted = 0
        for batch_start in range(0, len(valid_df), BATCH_SIZE):
            batch = valid_df.iloc[batch_start : batch_start + BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(
                    Indicators(
                        market_data_id=int(row["id"]),
                        time=row["time"],
                        symbol=symbol,
                        timeframe=timeframe,
                        rsi=Decimal(str(round(row["rsi"], 6))) if pd.notna(row["rsi"]) else None,
                        macd=Decimal(str(round(row["macd"], 6))) if pd.notna(row["macd"]) else None,
                        macd_signal=Decimal(str(round(row["macd_signal"], 6))) if pd.notna(row["macd_signal"]) else None,
                        atr=Decimal(str(round(row["atr"], 6))) if pd.notna(row["atr"]) else None,
                        bb_upper=Decimal(str(round(row["bb_upper"], 6))) if pd.notna(row["bb_upper"]) else None,
                        bb_middle=Decimal(str(round(row["bb_middle"], 6))) if pd.notna(row["bb_middle"]) else None,
                        bb_lower=Decimal(str(round(row["bb_lower"], 6))) if pd.notna(row["bb_lower"]) else None,
                        ma_20=Decimal(str(round(row["ma_20"], 6))) if pd.notna(row["ma_20"]) else None,
                        ma_50=Decimal(str(round(row["ma_50"], 6))) if pd.notna(row["ma_50"]) else None,
                        ma_200=Decimal(str(round(row["ma_200"], 6))) if pd.notna(row["ma_200"]) else None,
                        zigzag_label=0,
                    )
                )
            self.session.add_all(rows)
            await self.session.flush()
            total_inserted += len(rows)

        await self.session.commit()
        return total_inserted
