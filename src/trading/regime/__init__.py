"""
src.trading.regime — Rule-based market regime detection.

Exported symbols:
    MarketRegime: Enum with TRENDING, RANGING, VOLATILE, UNKNOWN values.
    RegimeClassifier: Classifies market regime from OHLCV data using ADX,
                      ATR ratio, and Hurst exponent (R/S analysis).
"""

from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier

__all__ = ["MarketRegime", "RegimeClassifier"]
