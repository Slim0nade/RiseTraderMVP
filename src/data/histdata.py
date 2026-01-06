"""
HistData downloader.

Downloads free 1-minute historical data from the FX-1-Minute-Data GitHub repository.
This repository contains data from HistData.com with 25+ years of history.

Repository: https://github.com/philipperemy/FX-1-Minute-Data
Data available: 2000-present for most forex pairs, commodities, and indices.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .base import (
    BaseDataDownloader,
    DataSource,
    Timeframe,
    OHLCVBar,
    DownloadResult,
    validate_date_range,
)

logger = logging.getLogger(__name__)


# HistData symbol mappings (from the GitHub repo)
HISTDATA_SYMBOLS = {
    "CrudeOIL": "wticousd",  # WTI Crude Oil
    "GOLD": "xauusd",
    "SILVER": "xagusd",
    "DXY": "usdx",  # US Dollar Index (check availability)
    "SPX500": "spx500usd",
    "EURUSD": "eurusd",
    "GBPUSD": "gbpusd",
    "USDJPY": "usdjpy",
    "USDCAD": "usdcad",
    "AUDUSD": "audusd",
    "NZDUSD": "nzdusd",
    "USDCHF": "usdchf",
    "BRENT": "bcousd",  # Brent Crude
    "NATGAS": "natgasusd",  # Natural Gas
}


class HistDataDownloader(BaseDataDownloader):
    """
    Downloads historical data from the FX-1-Minute-Data GitHub repository.
    
    This uses the `histdata` Python package or direct download from GitHub.
    Data is available as 1-minute bid quotes in CSV format.
    """
    
    source = DataSource.HISTDATA
    REPO_URL = "https://github.com/philipperemy/FX-1-Minute-Data"
    
    def __init__(self, data_dir: Path = None, use_package: bool = True):
        super().__init__(data_dir)
        self.use_package = use_package
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if histdata package is available."""
        try:
            import histdata
            self._histdata_available = True
            logger.info("histdata package is available")
        except ImportError:
            self._histdata_available = False
            logger.warning("histdata package not installed. Install with: pip install histdata")
    
    def _get_histdata_symbol(self, symbol: str) -> str:
        """Convert internal symbol to histdata symbol."""
        return HISTDATA_SYMBOLS.get(symbol, symbol.lower())
    
    async def download_with_package(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.DataFrame]:
        """Download using the histdata Python package."""
        if not self._histdata_available:
            raise RuntimeError("histdata package not available")
        
        from histdata import download_hist_data
        from histdata.api import Platform, TimeFrame
        
        histdata_symbol = self._get_histdata_symbol(symbol)
        
        all_data = []
        current_year = start_date.year
        
        while current_year <= end_date.year:
            try:
                logger.info(f"Downloading {histdata_symbol} for year {current_year}")
                
                # Download returns a generator of DataFrames
                data = download_hist_data(
                    year=current_year,
                    pair=histdata_symbol,
                    platform=Platform.GENERIC_ASCII,
                    time_frame=TimeFrame.ONE_MINUTE
                )
                
                for df in data:
                    if df is not None and not df.empty:
                        all_data.append(df)
                
            except Exception as e:
                logger.warning(f"Failed to download {histdata_symbol} for {current_year}: {e}")
            
            current_year += 1
        
        if not all_data:
            return None
        
        # Combine all DataFrames
        combined_df = pd.concat(all_data, ignore_index=True)
        
        # Standard column names
        combined_df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        combined_df['time'] = pd.to_datetime(combined_df['time'])
        combined_df.set_index('time', inplace=True)
        
        # Filter to requested date range
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        combined_df = combined_df[(combined_df.index >= start_dt) & (combined_df.index <= end_dt)]
        
        return combined_df
    
    async def download_from_github(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.DataFrame]:
        """
        Download directly from GitHub raw files.
        
        Files are organized by year: {symbol}/{year}.csv
        """
        import aiohttp
        
        histdata_symbol = self._get_histdata_symbol(symbol)
        base_url = f"https://raw.githubusercontent.com/philipperemy/FX-1-Minute-Data/master/data/{histdata_symbol}"
        
        all_data = []
        
        async with aiohttp.ClientSession() as session:
            for year in range(start_date.year, end_date.year + 1):
                url = f"{base_url}/{year}.csv"
                
                try:
                    logger.info(f"Downloading {url}")
                    async with session.get(url) as response:
                        if response.status == 404:
                            logger.warning(f"No data for {histdata_symbol} {year}")
                            continue
                        
                        if response.status != 200:
                            logger.warning(f"HTTP {response.status} for {url}")
                            continue
                        
                        text = await response.text()
                        
                        # Parse CSV
                        from io import StringIO
                        df = pd.read_csv(
                            StringIO(text),
                            header=None,
                            names=['time', 'open', 'high', 'low', 'close', 'volume'],
                            parse_dates=['time']
                        )
                        
                        all_data.append(df)
                        logger.info(f"Downloaded {len(df)} rows for {year}")
                        
                except Exception as e:
                    logger.warning(f"Failed to download {url}: {e}")
        
        if not all_data:
            return None
        
        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df.set_index('time', inplace=True)
        combined_df.sort_index(inplace=True)
        
        # Filter to requested date range
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        combined_df = combined_df[(combined_df.index >= start_dt) & (combined_df.index <= end_dt)]
        
        return combined_df
    
    async def download(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: Timeframe = Timeframe.M1,
    ) -> DownloadResult:
        """
        Download data for a symbol and date range.
        
        HistData only provides M1 data, so other timeframes require resampling.
        """
        validate_date_range(start_date, end_date)
        
        logger.info(f"Downloading {symbol} from HistData: {start_date} to {end_date}")
        
        # Try package first, then GitHub
        df = None
        
        if self.use_package and self._histdata_available:
            try:
                df = await self.download_with_package(symbol, start_date, end_date)
            except Exception as e:
                logger.warning(f"Package download failed: {e}")
        
        if df is None or df.empty:
            logger.info("Falling back to GitHub download...")
            df = await self.download_from_github(symbol, start_date, end_date)
        
        if df is None or df.empty:
            return DownloadResult(
                symbol=symbol,
                source=self.source,
                timeframe=timeframe,
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.max.time()),
                bars_count=0,
                success=False,
                error="No data available"
            )
        
        # Resample if needed
        if timeframe != Timeframe.M1:
            df = self._resample(df, timeframe)
        
        # Save to CSV
        filepath = self.save_to_csv(df, symbol, timeframe, start_date, end_date)
        
        return DownloadResult(
            symbol=symbol,
            source=self.source,
            timeframe=timeframe,
            start_date=df.index.min(),
            end_date=df.index.max(),
            bars_count=len(df),
            success=True,
            file_path=filepath
        )
    
    def _resample(self, df: pd.DataFrame, timeframe: Timeframe) -> pd.DataFrame:
        """Resample M1 data to different timeframe."""
        resample_map = {
            Timeframe.M5: '5min',
            Timeframe.M15: '15min',
            Timeframe.M30: '30min',
            Timeframe.H1: '1h',
            Timeframe.H4: '4h',
            Timeframe.D1: '1D',
            Timeframe.W1: '1W',
            Timeframe.MN1: '1ME',
        }
        
        rule = resample_map.get(timeframe)
        if not rule:
            return df
        
        resampled = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return resampled
    
    async def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        return list(HISTDATA_SYMBOLS.keys())


async def main():
    """Test the downloader."""
    downloader = HistDataDownloader(data_dir=Path("data/downloads/histdata"))
    
    # Test with a short date range
    result = await downloader.download(
        symbol="CrudeOIL",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        timeframe=Timeframe.M1
    )
    
    print(f"Download result: {result}")
    
    if result.success and result.file_path:
        df = pd.read_csv(result.file_path, index_col=0, parse_dates=True)
        print(f"\nFirst 5 bars:\n{df.head()}")
        print(f"\nLast 5 bars:\n{df.tail()}")
        print(f"\nShape: {df.shape}")


if __name__ == "__main__":
    asyncio.run(main())
