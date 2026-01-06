"""
Base classes and utilities for data downloaders.
"""
import asyncio
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Iterator

import pandas as pd

# Configure logging to stderr for MCP compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


class DataSource(str, Enum):
    """Data source enum matching database."""
    MT4 = "MT4"
    BC = "BC"  # Barchart
    CSV = "CSV"
    DUKASCOPY = "DUKASCOPY"
    HISTDATA = "HISTDATA"
    OANDA = "OANDA"


class Timeframe(str, Enum):
    """Timeframe enum matching database."""
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


@dataclass
class SymbolMapping:
    """Maps internal symbol to source-specific symbol."""
    internal: str  # Our symbol (e.g., CrudeOIL)
    source_symbol: str  # Source's symbol (e.g., WTICOUSD for Dukascopy)
    source: DataSource
    description: str = ""


# Symbol mappings for different data sources
SYMBOL_MAPPINGS: Dict[DataSource, Dict[str, SymbolMapping]] = {
    DataSource.DUKASCOPY: {
        "CrudeOIL": SymbolMapping("CrudeOIL", "WTICOUSD", DataSource.DUKASCOPY, "WTI Crude Oil CFD"),
        "GOLD": SymbolMapping("GOLD", "XAUUSD", DataSource.DUKASCOPY, "Gold Spot"),
        "DXY": SymbolMapping("DXY", "USXUSD", DataSource.DUKASCOPY, "US Dollar Index"),  # Check availability
        "SPX500": SymbolMapping("SPX500", "USA500IDXUSD", DataSource.DUKASCOPY, "S&P 500 Index CFD"),
        "EURUSD": SymbolMapping("EURUSD", "EURUSD", DataSource.DUKASCOPY, "EUR/USD"),
    },
    DataSource.HISTDATA: {
        "CrudeOIL": SymbolMapping("CrudeOIL", "WTICOUSD", DataSource.HISTDATA, "WTI Crude Oil"),
        "GOLD": SymbolMapping("GOLD", "XAUUSD", DataSource.HISTDATA, "Gold"),
        "DXY": SymbolMapping("DXY", "USDX", DataSource.HISTDATA, "US Dollar Index"),
        "SPX500": SymbolMapping("SPX500", "SPX500USD", DataSource.HISTDATA, "S&P 500"),
        "EURUSD": SymbolMapping("EURUSD", "EURUSD", DataSource.HISTDATA, "EUR/USD"),
    },
    DataSource.OANDA: {
        "CrudeOIL": SymbolMapping("CrudeOIL", "WTICO_USD", DataSource.OANDA, "WTI Crude Oil"),
        "GOLD": SymbolMapping("GOLD", "XAU_USD", DataSource.OANDA, "Gold"),
        "SPX500": SymbolMapping("SPX500", "SPX500_USD", DataSource.OANDA, "S&P 500"),
        "EURUSD": SymbolMapping("EURUSD", "EUR_USD", DataSource.OANDA, "EUR/USD"),
    },
}


@dataclass
class OHLCVBar:
    """Standard OHLCV bar structure."""
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
        }


@dataclass
class DownloadResult:
    """Result of a download operation."""
    symbol: str
    source: DataSource
    timeframe: Timeframe
    start_date: datetime
    end_date: datetime
    bars_count: int
    success: bool
    error: Optional[str] = None
    file_path: Optional[Path] = None


class BaseDataDownloader(ABC):
    """Abstract base class for data downloaders."""
    
    source: DataSource
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path("data/downloads")
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    async def download(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: Timeframe = Timeframe.M1,
    ) -> DownloadResult:
        """Download data for a symbol and date range."""
        pass
    
    @abstractmethod
    async def get_available_symbols(self) -> List[str]:
        """Get list of available symbols from this source."""
        pass
    
    def get_symbol_mapping(self, internal_symbol: str) -> Optional[SymbolMapping]:
        """Get source-specific symbol mapping."""
        mappings = SYMBOL_MAPPINGS.get(self.source, {})
        return mappings.get(internal_symbol)
    
    def bars_to_dataframe(self, bars: List[OHLCVBar]) -> pd.DataFrame:
        """Convert list of bars to DataFrame."""
        if not bars:
            return pd.DataFrame()
        
        df = pd.DataFrame([bar.to_dict() for bar in bars])
        df.set_index('time', inplace=True)
        df.sort_index(inplace=True)
        return df
    
    def save_to_csv(self, df: pd.DataFrame, symbol: str, timeframe: Timeframe,
                    start_date: date, end_date: date) -> Path:
        """Save DataFrame to CSV file."""
        filename = f"{symbol}_{self.source.value}_{timeframe.value}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
        filepath = self.data_dir / filename
        df.to_csv(filepath)
        logger.info(f"Saved {len(df)} bars to {filepath}")
        return filepath


def validate_date_range(start_date: date, end_date: date) -> bool:
    """Validate date range."""
    if start_date > end_date:
        raise ValueError(f"Start date {start_date} is after end date {end_date}")
    if end_date > date.today():
        raise ValueError(f"End date {end_date} is in the future")
    return True


def split_date_range(start_date: date, end_date: date, chunk_days: int = 30) -> List[Tuple[date, date]]:
    """Split date range into chunks for batch downloading."""
    chunks = []
    current_start = start_date
    
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)
        chunks.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return chunks
