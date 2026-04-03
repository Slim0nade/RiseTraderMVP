"""
src.trading.filters — Signal quality filters applied after signal generation.

Exported symbols:
    TrendFilter:       Suppress counter-trend reversal signals using MA + ADX confirmations.
    CrossAssetFilter:  Confirm or reject signals using related instrument price action.
"""

from src.trading.filters.trend_filter import TrendFilter
from src.trading.filters.cross_asset_filter import CrossAssetFilter

__all__ = ["TrendFilter", "CrossAssetFilter"]
