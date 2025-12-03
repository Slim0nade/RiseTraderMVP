"""
MCP Tool Implementations for Intelligent Multi-Agent Trading System.

This module provides ML model and calculation tools that agents can call
via the MCP (Model Context Protocol).
"""

from .forecasting_tools import get_tcn_forecast, get_tft_prediction, get_fedformer_regime
from .calculation_tools import calculate_kelly, calculate_atr
from .market_structure_tools import get_support_resistance, detect_liquidity_clusters
from .data_retrieval_tools import get_economic_events, get_cot_data

__all__ = [
    "get_tcn_forecast",
    "get_tft_prediction",
    "get_fedformer_regime",
    "calculate_kelly",
    "calculate_atr",
    "get_support_resistance",
    "detect_liquidity_clusters",
    "get_economic_events",
    "get_cot_data",
]
