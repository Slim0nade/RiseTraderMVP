"""
Dukascopy data downloader.

Downloads free tick/OHLCV data from Dukascopy's historical data service.
Supports forex pairs, commodities (gold, oil), and indices.

Data available from ~2009-2010 to present depending on instrument.
"""
import asyncio
import gzip
import io
import logging
import struct
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple, AsyncIterator
from urllib.parse import urljoin

import aiohttp
import pandas as pd

from .base import (
    BaseDataDownloader,
    DataSource,
    Timeframe,
    OHLCVBar,
    DownloadResult,
    SymbolMapping,
    split_date_range,
    validate_date_range,
)

logger = logging.getLogger(__name__)


# Dukascopy symbol mappings
DUKASCOPY_SYMBOLS = {
    "CrudeOIL": "USOUSD",  # WTI Crude Oil (Light Sweet Crude)
    "GOLD": "XAUUSD",
    "SILVER": "XAGUSD", 
    "SPX500": "USA500IDXUSD",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCAD": "USDCAD",
    "AUDUSD": "AUDUSD",
    "NZDUSD": "NZDUSD",
    "USDCHF": "USDCHF",
    # Note: DXY and VIX not directly available on Dukascopy
}

# Point values for price conversion (Dukascopy stores prices as integers)
POINT_VALUES = {
    "USOUSD": 0.001,  # Oil: 3 decimals
    "XAUUSD": 0.001,  # Gold: 3 decimals
    "XAGUSD": 0.001,  # Silver: 3 decimals
    "USA500IDXUSD": 0.1,  # Index: 1 decimal
    # Forex pairs: 5 decimals (default)
}


class DukascopyDownloader(BaseDataDownloader):
    """
    Downloads historical data from Dukascopy.
    
    Dukascopy provides free tick data that can be aggregated into OHLCV bars.
    Data URL format: https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YEAR}/{MONTH}/{DAY}/{HOUR}h_ticks.bi5
    
    The bi5 format is a gzipped binary format with tick data.
    """
    
    source = DataSource.DUKASCOPY
    BASE_URL = "https://datafeed.dukascopy.com/datafeed/"
    
    def __init__(self, data_dir: Path = None):
        super().__init__(data_dir)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 RiseTrader/1.0"}
            )
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_dukascopy_symbol(self, symbol: str) -> str:
        """Convert internal symbol to Dukascopy symbol."""
        return DUKASCOPY_SYMBOLS.get(symbol, symbol)
    
    def _get_point_value(self, dukascopy_symbol: str) -> float:
        """Get point value for price conversion."""
        return POINT_VALUES.get(dukascopy_symbol, 0.00001)  # Default for forex
    
    def _build_url(self, symbol: str, dt: datetime) -> str:
        """Build URL for hourly tick data file."""
        duka_symbol = self._get_dukascopy_symbol(symbol)
        # Month is 0-indexed in Dukascopy URLs
        month = dt.month - 1
        return f"{self.BASE_URL}{duka_symbol}/{dt.year}/{month:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"
    
    async def _download_hour(self, symbol: str, dt: datetime) -> List[Tuple[datetime, float, float]]:
        """
        Download and parse tick data for one hour.
        
        Returns list of (timestamp, ask, bid) tuples.
        """
        url = self._build_url(symbol, dt)
        duka_symbol = self._get_dukascopy_symbol(symbol)
        point_value = self._get_point_value(duka_symbol)
        
        session = await self._get_session()
        ticks = []
        
        try:
            async with session.get(url) as response:
                if response.status == 404:
                    # No data for this hour (market closed, etc.)
                    return []
                
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return []
                
                # Read and decompress bi5 data
                compressed_data = await response.read()
                
                if len(compressed_data) == 0:
                    return []
                
                try:
                    data = gzip.decompress(compressed_data)
                except Exception as e:
                    logger.warning(f"Failed to decompress {url}: {e}")
                    return []
                
                # Parse binary tick data
                # Format: 4 bytes timestamp (ms offset), 4 bytes ask, 4 bytes bid, 
                #         4 bytes ask volume, 4 bytes bid volume = 20 bytes per tick
                tick_size = 20
                num_ticks = len(data) // tick_size
                
                base_time = dt.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                
                for i in range(num_ticks):
                    offset = i * tick_size
                    try:
                        ms_offset, ask_int, bid_int, ask_vol, bid_vol = struct.unpack(
                            '>IIIff', data[offset:offset + tick_size]
                        )
                        
                        tick_time = base_time + timedelta(milliseconds=ms_offset)
                        ask_price = ask_int * point_value
                        bid_price = bid_int * point_value
                        
                        ticks.append((tick_time, ask_price, bid_price))
                    except struct.error:
                        continue
                
                return ticks
                
        except aiohttp.ClientError as e:
            logger.warning(f"Network error downloading {url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return []
    
    def _aggregate_ticks_to_bars(
        self,
        ticks: List[Tuple[datetime, float, float]],
        timeframe: Timeframe
    ) -> List[OHLCVBar]:
        """Aggregate tick data into OHLCV bars."""
        if not ticks:
            return []
        
        # Determine bar duration
        durations = {
            Timeframe.M1: timedelta(minutes=1),
            Timeframe.M5: timedelta(minutes=5),
            Timeframe.M15: timedelta(minutes=15),
            Timeframe.M30: timedelta(minutes=30),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.H4: timedelta(hours=4),
            Timeframe.D1: timedelta(days=1),
        }
        bar_duration = durations.get(timeframe, timedelta(minutes=1))
        
        # Group ticks into bars
        bars = []
        current_bar_start = None
        current_ticks = []
        
        for tick_time, ask, bid in sorted(ticks, key=lambda x: x[0]):
            # Use mid price
            price = (ask + bid) / 2
            
            # Calculate bar start time
            if timeframe == Timeframe.M1:
                bar_start = tick_time.replace(second=0, microsecond=0)
            elif timeframe == Timeframe.M5:
                bar_start = tick_time.replace(minute=(tick_time.minute // 5) * 5, second=0, microsecond=0)
            elif timeframe == Timeframe.M15:
                bar_start = tick_time.replace(minute=(tick_time.minute // 15) * 15, second=0, microsecond=0)
            elif timeframe == Timeframe.M30:
                bar_start = tick_time.replace(minute=(tick_time.minute // 30) * 30, second=0, microsecond=0)
            elif timeframe == Timeframe.H1:
                bar_start = tick_time.replace(minute=0, second=0, microsecond=0)
            elif timeframe == Timeframe.H4:
                bar_start = tick_time.replace(hour=(tick_time.hour // 4) * 4, minute=0, second=0, microsecond=0)
            else:
                bar_start = tick_time.replace(hour=0, minute=0, second=0, microsecond=0)
            
            if current_bar_start is None:
                current_bar_start = bar_start
                current_ticks = [(tick_time, price)]
            elif bar_start == current_bar_start:
                current_ticks.append((tick_time, price))
            else:
                # Close current bar and start new one
                if current_ticks:
                    prices = [p for _, p in current_ticks]
                    bars.append(OHLCVBar(
                        time=current_bar_start,
                        open=Decimal(str(prices[0])),
                        high=Decimal(str(max(prices))),
                        low=Decimal(str(min(prices))),
                        close=Decimal(str(prices[-1])),
                        volume=len(current_ticks)
                    ))
                current_bar_start = bar_start
                current_ticks = [(tick_time, price)]
        
        # Don't forget the last bar
        if current_ticks:
            prices = [p for _, p in current_ticks]
            bars.append(OHLCVBar(
                time=current_bar_start,
                open=Decimal(str(prices[0])),
                high=Decimal(str(max(prices))),
                low=Decimal(str(min(prices))),
                close=Decimal(str(prices[-1])),
                volume=len(current_ticks)
            ))
        
        return bars
    
    async def download(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: Timeframe = Timeframe.M1,
    ) -> DownloadResult:
        """
        Download data for a symbol and date range.
        
        Downloads tick data hour by hour and aggregates into OHLCV bars.
        """
        validate_date_range(start_date, end_date)
        
        duka_symbol = self._get_dukascopy_symbol(symbol)
        logger.info(f"Downloading {symbol} ({duka_symbol}) from {start_date} to {end_date}")
        
        all_ticks = []
        current_date = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        hours_to_download = []
        while current_date <= end_datetime:
            hours_to_download.append(current_date)
            current_date += timedelta(hours=1)
        
        logger.info(f"Downloading {len(hours_to_download)} hours of tick data...")
        
        # Download with concurrency limit
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
        
        async def download_with_limit(dt):
            async with semaphore:
                return await self._download_hour(symbol, dt)
        
        # Download in batches to show progress
        batch_size = 24  # One day at a time
        for i in range(0, len(hours_to_download), batch_size):
            batch = hours_to_download[i:i + batch_size]
            results = await asyncio.gather(*[download_with_limit(dt) for dt in batch])
            
            for ticks in results:
                all_ticks.extend(ticks)
            
            if i % (batch_size * 7) == 0:  # Log weekly progress
                logger.info(f"Progress: {i}/{len(hours_to_download)} hours downloaded, {len(all_ticks)} ticks so far")
        
        logger.info(f"Downloaded {len(all_ticks)} total ticks")
        
        # Aggregate to bars
        bars = self._aggregate_ticks_to_bars(all_ticks, timeframe)
        logger.info(f"Aggregated into {len(bars)} {timeframe.value} bars")
        
        if not bars:
            return DownloadResult(
                symbol=symbol,
                source=self.source,
                timeframe=timeframe,
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.max.time()),
                bars_count=0,
                success=False,
                error="No data available for this date range"
            )
        
        # Save to CSV
        df = self.bars_to_dataframe(bars)
        filepath = self.save_to_csv(df, symbol, timeframe, start_date, end_date)
        
        await self.close()
        
        return DownloadResult(
            symbol=symbol,
            source=self.source,
            timeframe=timeframe,
            start_date=bars[0].time,
            end_date=bars[-1].time,
            bars_count=len(bars),
            success=True,
            file_path=filepath
        )
    
    async def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        return list(DUKASCOPY_SYMBOLS.keys())


async def main():
    """Test the downloader."""
    downloader = DukascopyDownloader(data_dir=Path("data/downloads/dukascopy"))
    
    # Test with a short date range
    result = await downloader.download(
        symbol="CrudeOIL",
        start_date=date(2024, 12, 1),
        end_date=date(2024, 12, 7),
        timeframe=Timeframe.M1
    )
    
    print(f"Download result: {result}")
    
    if result.success and result.file_path:
        df = pd.read_csv(result.file_path, index_col=0, parse_dates=True)
        print(f"\nFirst 5 bars:\n{df.head()}")
        print(f"\nLast 5 bars:\n{df.tail()}")


if __name__ == "__main__":
    asyncio.run(main())
