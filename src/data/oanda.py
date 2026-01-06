"""
OANDA data downloader.

Downloads historical data from OANDA's REST API.
Requires free demo account for API access.

OANDA provides:
- 20+ years of M1 data for forex and CFDs
- Up to 5000 candles per request
- Generous rate limits (120 requests/second)
"""
import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiohttp
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


# OANDA symbol mappings
OANDA_SYMBOLS = {
    "CrudeOIL": "WTICO_USD",  # WTI Crude Oil
    "GOLD": "XAU_USD",
    "SILVER": "XAG_USD",
    "SPX500": "SPX500_USD",
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "USDCAD": "USD_CAD",
    "AUDUSD": "AUD_USD",
    "NZDUSD": "NZD_USD",
    "USDCHF": "USD_CHF",
    "NATGAS": "NATGAS_USD",
    "COPPER": "COPPER_USD",
    # Note: DXY and VIX not available on OANDA
}

# OANDA timeframe mapping
OANDA_TIMEFRAMES = {
    Timeframe.M1: "M1",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.M30: "M30",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
    Timeframe.W1: "W",
    Timeframe.MN1: "M",
}


class OANDADownloader(BaseDataDownloader):
    """
    Downloads historical data from OANDA REST API.
    
    Requires:
    - OANDA demo or live account
    - API access token
    
    API docs: https://developer.oanda.com/rest-live-v20/instrument-ep/
    """
    
    source = DataSource.OANDA
    PRACTICE_URL = "https://api-fxpractice.oanda.com"
    LIVE_URL = "https://api-fxtrade.oanda.com"
    MAX_CANDLES = 5000  # OANDA limit per request
    
    def __init__(
        self,
        api_token: str = None,
        account_id: str = None,
        practice: bool = True,
        data_dir: Path = None
    ):
        super().__init__(data_dir)
        self.api_token = api_token or self._load_token_from_env()
        self.account_id = account_id
        self.base_url = self.PRACTICE_URL if practice else self.LIVE_URL
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _load_token_from_env(self) -> Optional[str]:
        """Load API token from environment."""
        import os
        return os.getenv("OANDA_API_TOKEN")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with auth headers."""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_oanda_symbol(self, symbol: str) -> str:
        """Convert internal symbol to OANDA symbol."""
        return OANDA_SYMBOLS.get(symbol, symbol.replace("/", "_"))
    
    def _get_oanda_timeframe(self, timeframe: Timeframe) -> str:
        """Convert internal timeframe to OANDA granularity."""
        return OANDA_TIMEFRAMES.get(timeframe, "M1")
    
    async def _fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime = None,
        count: int = None
    ) -> List[Dict[str, Any]]:
        """Fetch candles from OANDA API."""
        if not self.api_token:
            raise ValueError("OANDA API token not configured")
        
        oanda_symbol = self._get_oanda_symbol(symbol)
        granularity = self._get_oanda_timeframe(timeframe)
        
        url = f"{self.base_url}/v3/instruments/{oanda_symbol}/candles"
        
        params = {
            "granularity": granularity,
            "price": "MBA",  # Mid, Bid, Ask
        }
        
        if count:
            params["count"] = min(count, self.MAX_CANDLES)
        
        if start_time:
            params["from"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if end_time:
            params["to"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        session = await self._get_session()
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 401:
                    raise ValueError("Invalid OANDA API token")
                
                if response.status != 200:
                    text = await response.text()
                    logger.warning(f"OANDA API error {response.status}: {text}")
                    return []
                
                data = await response.json()
                return data.get("candles", [])
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return []
    
    def _parse_candles(self, candles: List[Dict]) -> List[OHLCVBar]:
        """Parse OANDA candles to OHLCVBar objects."""
        bars = []
        
        for candle in candles:
            if not candle.get("complete", True):
                continue  # Skip incomplete candles
            
            try:
                # Use mid prices
                mid = candle.get("mid", {})
                
                bar = OHLCVBar(
                    time=datetime.fromisoformat(candle["time"].replace("Z", "+00:00")),
                    open=Decimal(mid.get("o", "0")),
                    high=Decimal(mid.get("h", "0")),
                    low=Decimal(mid.get("l", "0")),
                    close=Decimal(mid.get("c", "0")),
                    volume=candle.get("volume", 0)
                )
                bars.append(bar)
                
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse candle: {e}")
                continue
        
        return bars
    
    async def download(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: Timeframe = Timeframe.M1,
    ) -> DownloadResult:
        """Download data for a symbol and date range."""
        validate_date_range(start_date, end_date)
        
        if not self.api_token:
            return DownloadResult(
                symbol=symbol,
                source=self.source,
                timeframe=timeframe,
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.max.time()),
                bars_count=0,
                success=False,
                error="OANDA API token not configured. Set OANDA_API_TOKEN env var."
            )
        
        logger.info(f"Downloading {symbol} from OANDA: {start_date} to {end_date}")
        
        all_bars = []
        current_start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        
        # Download in chunks
        while current_start < end_datetime:
            candles = await self._fetch_candles(
                symbol=symbol,
                timeframe=timeframe,
                start_time=current_start,
                count=self.MAX_CANDLES
            )
            
            if not candles:
                break
            
            bars = self._parse_candles(candles)
            
            if not bars:
                break
            
            all_bars.extend(bars)
            
            # Move to next chunk
            last_time = bars[-1].time
            if last_time <= current_start:
                break  # No progress
            
            current_start = last_time + timedelta(minutes=1)
            
            # Rate limiting
            await asyncio.sleep(0.1)
            
            logger.info(f"Downloaded {len(all_bars)} bars, last: {last_time}")
        
        # Filter to exact date range
        all_bars = [
            bar for bar in all_bars
            if datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc) <= bar.time <=
               datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        ]
        
        await self.close()
        
        if not all_bars:
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
        
        # Save to CSV
        df = self.bars_to_dataframe(all_bars)
        filepath = self.save_to_csv(df, symbol, timeframe, start_date, end_date)
        
        return DownloadResult(
            symbol=symbol,
            source=self.source,
            timeframe=timeframe,
            start_date=all_bars[0].time,
            end_date=all_bars[-1].time,
            bars_count=len(all_bars),
            success=True,
            file_path=filepath
        )
    
    async def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        return list(OANDA_SYMBOLS.keys())


async def main():
    """Test the downloader."""
    # Requires OANDA_API_TOKEN env var
    downloader = OANDADownloader(data_dir=Path("data/downloads/oanda"))
    
    symbols = await downloader.get_available_symbols()
    print(f"Available symbols: {symbols}")
    
    # Test download (requires valid token)
    result = await downloader.download(
        symbol="EURUSD",
        start_date=date(2024, 12, 1),
        end_date=date(2024, 12, 7),
        timeframe=Timeframe.M1
    )
    
    print(f"Download result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
