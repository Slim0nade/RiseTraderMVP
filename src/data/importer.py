"""
Database importer for market data.

Imports downloaded CSV data into the PostgreSQL database,
handling duplicates, timezone conversion, and data validation.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .base import DataSource, Timeframe

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of an import operation."""
    file_path: Path
    symbol: str
    source: DataSource
    timeframe: Timeframe
    total_rows: int
    inserted: int
    updated: int
    skipped: int
    errors: int
    success: bool
    error_message: Optional[str] = None


class DataImporter:
    """
    Imports market data into PostgreSQL database.
    
    Features:
    - Duplicate detection and handling
    - Timezone normalization to UTC
    - Batch inserts for performance
    - Data validation
    """
    
    def __init__(self, session_factory):
        """
        Initialize importer with session factory.
        
        Args:
            session_factory: SQLAlchemy async session factory
        """
        self.session_factory = session_factory
        self.batch_size = 1000
    
    async def import_csv(
        self,
        file_path: Path,
        symbol: str,
        source: DataSource,
        timeframe: Timeframe = Timeframe.M1,
        source_timezone: str = "UTC",
        update_existing: bool = False
    ) -> ImportResult:
        """
        Import CSV file into database.
        
        Args:
            file_path: Path to CSV file
            symbol: Internal symbol name
            source: Data source
            timeframe: Timeframe of the data
            source_timezone: Timezone of the source data
            update_existing: Whether to update existing records
            
        Returns:
            ImportResult with statistics
        """
        logger.info(f"Importing {file_path} as {symbol} from {source.value}")
        
        try:
            # Read CSV
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            
            if df.empty:
                return ImportResult(
                    file_path=file_path,
                    symbol=symbol,
                    source=source,
                    timeframe=timeframe,
                    total_rows=0,
                    inserted=0,
                    updated=0,
                    skipped=0,
                    errors=0,
                    success=False,
                    error_message="CSV file is empty"
                )
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            # Convert timezone to UTC
            df = self._convert_timezone(df, source_timezone)
            
            # Validate data
            df = self._validate_data(df)
            
            # Import to database
            inserted, updated, skipped, errors = await self._import_dataframe(
                df, symbol, source, timeframe, update_existing
            )
            
            return ImportResult(
                file_path=file_path,
                symbol=symbol,
                source=source,
                timeframe=timeframe,
                total_rows=len(df),
                inserted=inserted,
                updated=updated,
                skipped=skipped,
                errors=errors,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return ImportResult(
                file_path=file_path,
                symbol=symbol,
                source=source,
                timeframe=timeframe,
                total_rows=0,
                inserted=0,
                updated=0,
                skipped=0,
                errors=1,
                success=False,
                error_message=str(e)
            )
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to standard format."""
        column_map = {
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Last': 'close',
            'last': 'close',
            'Volume': 'volume',
            'vol': 'volume',
        }
        
        df = df.rename(columns=column_map)
        
        # Ensure required columns exist
        required = ['open', 'high', 'low', 'close']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Add volume if missing
        if 'volume' not in df.columns:
            df['volume'] = 0
        
        return df
    
    def _convert_timezone(self, df: pd.DataFrame, source_tz: str) -> pd.DataFrame:
        """Convert index to UTC timezone."""
        if df.index.tz is None:
            # Localize to source timezone
            df.index = df.index.tz_localize(source_tz)
        
        # Convert to UTC
        df.index = df.index.tz_convert('UTC')
        
        return df
    
    def _validate_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean data."""
        # Remove rows with NaN in OHLC
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        
        # Ensure high >= low
        invalid_bars = df['high'] < df['low']
        if invalid_bars.any():
            logger.warning(f"Found {invalid_bars.sum()} bars with high < low, swapping")
            df.loc[invalid_bars, ['high', 'low']] = df.loc[invalid_bars, ['low', 'high']].values
        
        # Ensure open and close are within high-low range
        df['open'] = df['open'].clip(df['low'], df['high'])
        df['close'] = df['close'].clip(df['low'], df['high'])
        
        # Fill NaN volume with 0
        df['volume'] = df['volume'].fillna(0).astype(int)
        
        # Sort by time
        df = df.sort_index()
        
        # Remove duplicates (keep last)
        df = df[~df.index.duplicated(keep='last')]
        
        return df
    
    async def _import_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        source: DataSource,
        timeframe: Timeframe,
        update_existing: bool
    ) -> Tuple[int, int, int, int]:
        """Import DataFrame to database."""
        # Import here to avoid circular dependency
        from src.database.models.market_data import MarketData
        
        inserted = 0
        updated = 0
        skipped = 0
        errors = 0
        
        async with self.session_factory() as session:
            # Process in batches
            records = []
            
            for i, (timestamp, row) in enumerate(df.iterrows()):
                try:
                    record_data = {
                        'time': timestamp.to_pydatetime(),
                        'symbol': symbol,
                        'import_symbol': symbol,  # Could be different
                        'source': source.value,
                        'timeframe': timeframe.value,
                        'open': Decimal(str(row['open'])),
                        'high': Decimal(str(row['high'])),
                        'low': Decimal(str(row['low'])),
                        'last': Decimal(str(row['close'])),
                        'change': Decimal('0'),
                        'change_percent': Decimal('0'),
                        'volume': int(row['volume']),
                    }
                    
                    # Check for existing record
                    existing = await session.execute(
                        select(MarketData).where(
                            and_(
                                MarketData.time == record_data['time'],
                                MarketData.symbol == symbol,
                                MarketData.source == source.value,
                                MarketData.timeframe == timeframe.value
                            )
                        )
                    )
                    existing_record = existing.scalar_one_or_none()
                    
                    if existing_record:
                        if update_existing:
                            # Update existing record
                            for key, value in record_data.items():
                                if key not in ['time', 'symbol', 'source', 'timeframe']:
                                    setattr(existing_record, key, value)
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        # Create new record
                        new_record = MarketData(**record_data)
                        session.add(new_record)
                        inserted += 1
                    
                    # Commit in batches
                    if (i + 1) % self.batch_size == 0:
                        await session.commit()
                        logger.info(f"Progress: {i + 1}/{len(df)} rows processed")
                        
                except Exception as e:
                    logger.warning(f"Error processing row {i}: {e}")
                    errors += 1
                    continue
            
            # Final commit
            await session.commit()
        
        logger.info(f"Import complete: {inserted} inserted, {updated} updated, "
                   f"{skipped} skipped, {errors} errors")
        
        return inserted, updated, skipped, errors
    
    async def import_directory(
        self,
        directory: Path,
        symbol: str,
        source: DataSource,
        timeframe: Timeframe = Timeframe.M1,
        pattern: str = "*.csv"
    ) -> List[ImportResult]:
        """Import all matching CSV files from a directory."""
        results = []
        
        files = sorted(directory.glob(pattern))
        logger.info(f"Found {len(files)} files matching {pattern} in {directory}")
        
        for file_path in files:
            result = await self.import_csv(
                file_path=file_path,
                symbol=symbol,
                source=source,
                timeframe=timeframe
            )
            results.append(result)
        
        # Summary
        total_inserted = sum(r.inserted for r in results)
        total_updated = sum(r.updated for r in results)
        total_errors = sum(r.errors for r in results)
        
        logger.info(f"Directory import complete: {total_inserted} inserted, "
                   f"{total_updated} updated, {total_errors} errors across {len(files)} files")
        
        return results


async def quick_import(
    file_path: str,
    symbol: str,
    source: str,
    timeframe: str = "M1",
    database_url: str = None
) -> ImportResult:
    """
    Quick import function for CLI usage.
    
    Example:
        python -m src.data.importer data.csv CrudeOIL DUKASCOPY M1
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    
    # Default database URL
    if database_url is None:
        database_url = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
    
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    importer = DataImporter(session_factory)
    
    result = await importer.import_csv(
        file_path=Path(file_path),
        symbol=symbol,
        source=DataSource(source),
        timeframe=Timeframe(timeframe)
    )
    
    await engine.dispose()
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python -m src.data.importer <file_path> <symbol> <source> [timeframe]")
        print("Example: python -m src.data.importer data.csv CrudeOIL DUKASCOPY M1")
        sys.exit(1)
    
    file_path = sys.argv[1]
    symbol = sys.argv[2]
    source = sys.argv[3]
    timeframe = sys.argv[4] if len(sys.argv) > 4 else "M1"
    
    result = asyncio.run(quick_import(file_path, symbol, source, timeframe))
    
    print(f"\nImport Result:")
    print(f"  File: {result.file_path}")
    print(f"  Symbol: {result.symbol}")
    print(f"  Source: {result.source.value}")
    print(f"  Total rows: {result.total_rows}")
    print(f"  Inserted: {result.inserted}")
    print(f"  Updated: {result.updated}")
    print(f"  Skipped: {result.skipped}")
    print(f"  Errors: {result.errors}")
    print(f"  Success: {result.success}")
