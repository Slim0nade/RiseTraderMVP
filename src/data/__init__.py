"""
Data pipeline module for RiseTrader.

Provides downloaders for multiple free data sources:
- Dukascopy: Tick data (2009-present) for forex, commodities, indices
- HistData: 1-minute data (2000-present) from GitHub repo
- OANDA: REST API for daily updates (requires free account)

Supports importing into PostgreSQL database for ML training and backtesting.
"""

from .base import (
    BaseDataDownloader,
    DataSource,
    Timeframe,
    OHLCVBar,
    DownloadResult,
    SymbolMapping,
    SYMBOL_MAPPINGS,
    validate_date_range,
    split_date_range,
)
from .dukascopy import DukascopyDownloader
from .histdata import HistDataDownloader
from .oanda import OANDADownloader
from .importer import DataImporter, ImportResult
from .pipeline import DataPipelineManager, DataCoverage, GapInfo
from .sync import DataSyncService, SymbolConfig, SyncResult

__all__ = [
    # Base classes
    "BaseDataDownloader",
    "DataSource",
    "Timeframe",
    "OHLCVBar",
    "DownloadResult",
    "SymbolMapping",
    "SYMBOL_MAPPINGS",
    "validate_date_range",
    "split_date_range",
    # Downloaders
    "DukascopyDownloader",
    "HistDataDownloader",
    "OANDADownloader",
    # Importer
    "DataImporter",
    "ImportResult",
    # Pipeline
    "DataPipelineManager",
    "DataCoverage",
    "GapInfo",
    # Sync Service
    "DataSyncService",
    "SymbolConfig",
    "SyncResult",
]
