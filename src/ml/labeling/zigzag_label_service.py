"""
ZigZag Label Service

Service to populate the indicators table with ZigZag labels
for ML training data generation.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData
from src.database.models.indicators import Indicators
from src.ml.labeling.zigzag_labeler import ZigZagLabeler, ZigZagConfig, get_config_for_timeframe

logger = logging.getLogger(__name__)


class ZigZagLabelService:
    """
    Service for generating and storing ZigZag labels.
    
    Usage:
        service = ZigZagLabelService(session)
        stats = await service.label_symbol('CrudeOIL', 'H1')
        print(f"Labeled {stats['total']} candles")
    """
    
    def __init__(
        self,
        session: AsyncSession,
        config: Optional[ZigZagConfig] = None
    ):
        self.session = session
        self.labeler = ZigZagLabeler(config)
    
    async def label_symbol(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        batch_size: int = 10000
    ) -> Dict[str, Any]:
        """
        Generate ZigZag labels for a symbol/timeframe and store in database.
        
        Args:
            symbol: Trading symbol (e.g., 'CrudeOIL')
            timeframe: Candle timeframe (e.g., 'H1')
            start_date: Optional start date filter
            end_date: Optional end date filter
            batch_size: Batch size for database updates
            
        Returns:
            Dict with labeling statistics
        """
        logger.info(f"Starting ZigZag labeling for {symbol} {timeframe}")
        
        # 1. Load candles from market_data
        candles_df = await self._load_candles(symbol, timeframe, start_date, end_date)
        
        if candles_df.empty:
            logger.warning(f"No candles found for {symbol} {timeframe}")
            return {'total': 0, 'error': 'No candles found'}
        
        logger.info(f"Loaded {len(candles_df)} candles")
        
        # 2. Apply ZigZag labels
        labeled_df = self.labeler.label_dataframe(candles_df)
        stats = self.labeler.get_statistics(labeled_df)
        
        logger.info(
            f"Labels generated: {stats['peaks']} peaks, {stats['valleys']} valleys, "
            f"{stats['reversal_pct']}% reversals"
        )
        
        # 3. Update indicators table
        updated = await self._update_indicators(
            symbol, timeframe, labeled_df, batch_size
        )
        
        stats['updated_rows'] = updated
        stats['symbol'] = symbol
        stats['timeframe'] = timeframe
        
        logger.info(f"Updated {updated} indicator rows with ZigZag labels")
        
        return stats
    
    async def _load_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Load candles from market_data table."""
        
        stmt = (
            select(
                MarketData.id,
                MarketData.time,
                MarketData.open,
                MarketData.high,
                MarketData.low,
                MarketData.last.label('close'),
                MarketData.volume
            )
            .where(MarketData.symbol == symbol)
            .where(MarketData.timeframe == timeframe)
            .order_by(MarketData.time.asc())
        )
        
        if start_date:
            stmt = stmt.where(MarketData.time >= start_date)
        if end_date:
            stmt = stmt.where(MarketData.time <= end_date)
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=['id', 'time', 'open', 'high', 'low', 'close', 'volume'])
        
        # Convert Decimal to float
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        
        return df
    
    async def _update_indicators(
        self,
        symbol: str,
        timeframe: str,
        labeled_df: pd.DataFrame,
        batch_size: int
    ) -> int:
        """Update indicators table with ZigZag labels."""
        
        # Create a mapping of time -> label
        label_map = dict(zip(labeled_df['time'], labeled_df['zigzag_label']))
        
        # Get indicator IDs for this symbol/timeframe
        stmt = (
            select(Indicators.id, Indicators.time)
            .where(Indicators.symbol == symbol)
            .where(Indicators.timeframe == timeframe)
        )
        
        result = await self.session.execute(stmt)
        indicators = result.all()
        
        if not indicators:
            logger.warning(f"No indicators found for {symbol} {timeframe}")
            return 0
        
        # Build update batches
        updates = []
        for ind_id, ind_time in indicators:
            label = label_map.get(ind_time, 0)
            if label != 0:  # Only update reversals to save queries
                updates.append({'id': ind_id, 'zigzag_label': int(label)})
        
        # Reset all labels to 0 first (clean slate)
        reset_stmt = (
            update(Indicators)
            .where(Indicators.symbol == symbol)
            .where(Indicators.timeframe == timeframe)
            .values(zigzag_label=0)
        )
        await self.session.execute(reset_stmt)
        
        # Batch update reversals
        updated = 0
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            
            for upd in batch:
                stmt = (
                    update(Indicators)
                    .where(Indicators.id == upd['id'])
                    .values(zigzag_label=upd['zigzag_label'])
                )
                await self.session.execute(stmt)
                updated += 1
            
            await self.session.flush()
            logger.debug(f"Updated batch {i//batch_size + 1}, total: {updated}")
        
        await self.session.commit()
        
        return updated
    
    async def get_label_distribution(
        self,
        symbol: str,
        timeframe: str
    ) -> Dict[str, int]:
        """Get current label distribution from database."""
        
        stmt = (
            select(
                Indicators.zigzag_label,
                func.count(Indicators.id).label('count')
            )
            .where(Indicators.symbol == symbol)
            .where(Indicators.timeframe == timeframe)
            .group_by(Indicators.zigzag_label)
        )
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        distribution = {'peak': 0, 'valley': 0, 'neither': 0, 'total': 0}
        
        for label, count in rows:
            if label == 1:
                distribution['peak'] = count
            elif label == -1:
                distribution['valley'] = count
            else:
                distribution['neither'] = count
            distribution['total'] += count
        
        return distribution
    
    async def label_symbol_multi_timeframe(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        batch_size: int = 10000,
    ) -> Dict[str, Any]:
        """
        Generate ZigZag labels for a symbol across multiple timeframes.

        Uses timeframe-specific ZigZag parameters (depth, deviation, backstep)
        so that M15 labels capture short-term swings while D1 labels capture
        major reversals.

        Args:
            symbol: Trading symbol (e.g. 'CrudeOIL').
            timeframes: List of timeframes to label. Default: M15, H1, H4, D1.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            batch_size: Batch size for DB updates.

        Returns:
            Dict keyed by timeframe with labeling statistics for each.
        """
        if timeframes is None:
            timeframes = ["M15", "H1", "H4", "D1"]

        results: Dict[str, Any] = {}
        for tf in timeframes:
            cfg = get_config_for_timeframe(tf, symbol=symbol)
            self.labeler = ZigZagLabeler(cfg)
            logger.info(
                f"Labeling {symbol} {tf} with depth={cfg.depth}, "
                f"deviation={cfg.deviation}, backstep={cfg.backstep}, point={cfg.point}"
            )
            stats = await self.label_symbol(
                symbol=symbol,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
                batch_size=batch_size,
            )
            results[tf] = stats

        return results

    async def clear_labels(self, symbol: str, timeframe: str) -> int:
        """Clear all ZigZag labels for a symbol/timeframe."""
        
        stmt = (
            update(Indicators)
            .where(Indicators.symbol == symbol)
            .where(Indicators.timeframe == timeframe)
            .values(zigzag_label=0)
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        return result.rowcount


async def run_labeling(
    symbol: str = 'CrudeOIL',
    timeframe: str = 'H1',
    database_url: Optional[str] = None
):
    """
    Standalone function to run labeling.
    
    Usage:
        python -m src.ml.labeling.zigzag_label_service
    """
    from src.database.config import initialize_database, get_database
    
    # Initialize database
    if database_url:
        initialize_database(database_url)
    else:
        initialize_database()
    
    db = get_database()
    
    async with db.get_session() as session:
        service = ZigZagLabelService(session)
        stats = await service.label_symbol(symbol, timeframe)
        
        print("\n" + "="*50)
        print(f"ZigZag Labeling Complete: {symbol} {timeframe}")
        print("="*50)
        print(f"Total candles:    {stats.get('total_candles', 0):,}")
        print(f"Peaks:            {stats.get('peaks', 0):,} ({stats.get('peak_pct', 0)}%)")
        print(f"Valleys:          {stats.get('valleys', 0):,} ({stats.get('valley_pct', 0)}%)")
        print(f"Neither:          {stats.get('neither', 0):,}")
        print(f"Avg bars between: {stats.get('avg_bars_between_reversals', 0)}")
        print(f"DB rows updated:  {stats.get('updated_rows', 0):,}")
        print("="*50)
        
        return stats


if __name__ == '__main__':
    import sys
    
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'CrudeOIL'
    timeframe = sys.argv[2] if len(sys.argv) > 2 else 'H1'
    
    asyncio.run(run_labeling(symbol, timeframe))
