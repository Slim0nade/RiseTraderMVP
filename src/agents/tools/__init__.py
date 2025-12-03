"""
MCP Tools for RiseTrader Multi-Agent System.

Provides function-based tools for AutoGen agents to access:
- ML forecasting models (TCN, XGBoost, LSTM)
- Regime detection
- Kelly criterion position sizing
- Technical indicators
- Market data queries

All tools are async functions that can be passed directly to AutoGen AssistantAgent.
"""

from src.agents.tools.mcp_tools import (
    get_tcn_forecast,
    get_xgboost_forecast,
    get_lstm_forecast,
    get_regime_classification,
    calculate_kelly_criterion,
    get_technical_indicators,
    get_market_data,
    get_forecast_accuracy,
)

__all__ = [
    "get_tcn_forecast",
    "get_xgboost_forecast",
    "get_lstm_forecast",
    "get_regime_classification",
    "calculate_kelly_criterion",
    "get_technical_indicators",
    "get_market_data",
    "get_forecast_accuracy",
]
