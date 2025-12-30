"""
Simple Technical Indicators Calculator for Backtesting.

Calculates basic technical indicators from OHLCV data for agent decision making.
Uses pandas and ta-lib for efficient vectorized calculations.
"""

from decimal import Decimal
from typing import Dict, List, Optional
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class TechnicalIndicatorsCalculator:
    """
    Calculate technical indicators from historical price data.

    Designed for backtesting where we have historical data but want to calculate
    indicators as if we were trading in real-time (no look-ahead bias).
    """

    def __init__(self, lookback_period: int = 200):
        """
        Initialize calculator.

        Args:
            lookback_period: Number of bars to keep in history for indicator calculation
        """
        self.lookback_period = lookback_period
        self.price_history: List[Dict] = []

    def update(self, tick: 'MarketTick') -> None:
        """
        Update price history with new tick data.

        Args:
            tick: New market tick data
        """
        self.price_history.append({
            'timestamp': tick.timestamp,
            'open': float(tick.open),
            'high': float(tick.high),
            'low': float(tick.low),
            'close': float(tick.close),
            'volume': tick.volume,
        })

        # Keep only last N bars
        if len(self.price_history) > self.lookback_period:
            self.price_history = self.price_history[-self.lookback_period:]

    def calculate_indicators(self) -> Dict[str, float]:
        """
        Calculate technical indicators from current price history.

        Returns:
            Dictionary of indicator values
        """
        if len(self.price_history) < 20:  # Need minimum data
            logger.debug(
                "insufficient_data_for_indicators",
                bars_available=len(self.price_history),
                bars_required=20,
            )
            return {}

        try:
            # Convert to DataFrame
            df = pd.DataFrame(self.price_history)

            indicators = {}

            # Moving Averages
            if len(df) >= 20:
                indicators['SMA_20'] = df['close'].rolling(20).mean().iloc[-1]
            if len(df) >= 50:
                indicators['SMA_50'] = df['close'].rolling(50).mean().iloc[-1]
            if len(df) >= 200:
                indicators['SMA_200'] = df['close'].rolling(200).mean().iloc[-1]

            # EMA
            if len(df) >= 12:
                indicators['EMA_12'] = df['close'].ewm(span=12, adjust=False).mean().iloc[-1]
            if len(df) >= 26:
                indicators['EMA_26'] = df['close'].ewm(span=26, adjust=False).mean().iloc[-1]

            # RSI
            if len(df) >= 14:
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                indicators['RSI_14'] = (100 - (100 / (1 + rs))).iloc[-1]

            # MACD
            if len(df) >= 26:
                ema12 = df['close'].ewm(span=12, adjust=False).mean()
                ema26 = df['close'].ewm(span=26, adjust=False).mean()
                macd = ema12 - ema26
                signal = macd.ewm(span=9, adjust=False).mean()
                indicators['MACD'] = macd.iloc[-1]
                indicators['MACD_signal'] = signal.iloc[-1]
                indicators['MACD_histogram'] = (macd - signal).iloc[-1]

            # Bollinger Bands
            if len(df) >= 20:
                sma20 = df['close'].rolling(20).mean()
                std20 = df['close'].rolling(20).std()
                indicators['BB_upper'] = (sma20 + 2 * std20).iloc[-1]
                indicators['BB_middle'] = sma20.iloc[-1]
                indicators['BB_lower'] = (sma20 - 2 * std20).iloc[-1]
                indicators['BB_width'] = ((indicators['BB_upper'] - indicators['BB_lower']) / indicators['BB_middle']) * 100

            # ATR (Average True Range)
            if len(df) >= 14:
                high_low = df['high'] - df['low']
                high_close = abs(df['high'] - df['close'].shift())
                low_close = abs(df['low'] - df['close'].shift())
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                indicators['ATR_14'] = true_range.rolling(14).mean().iloc[-1]

            # Volume indicators
            if len(df) >= 20:
                indicators['volume_sma_20'] = df['volume'].rolling(20).mean().iloc[-1]
                indicators['volume_ratio'] = df['volume'].iloc[-1] / indicators['volume_sma_20']

            # Price momentum
            if len(df) >= 10:
                indicators['momentum_10'] = ((df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

            # Stochastic Oscillator
            if len(df) >= 14:
                low_14 = df['low'].rolling(14).min()
                high_14 = df['high'].rolling(14).max()
                k = ((df['close'] - low_14) / (high_14 - low_14)) * 100
                indicators['Stoch_K'] = k.iloc[-1]
                indicators['Stoch_D'] = k.rolling(3).mean().iloc[-1]

            # Clean up NaN values
            indicators = {k: round(v, 4) for k, v in indicators.items() if pd.notna(v)}

            logger.debug(
                "indicators_calculated",
                bars_used=len(df),
                indicators_count=len(indicators),
                indicator_names=list(indicators.keys()),
            )

            return indicators

        except Exception as e:
            logger.error(
                "indicator_calculation_failed",
                error=str(e),
                history_length=len(self.price_history),
                exc_info=True,
            )
            return {}

    def get_summary(self) -> str:
        """Get human-readable summary of current indicators."""
        indicators = self.calculate_indicators()

        if not indicators:
            return "Insufficient data for indicator calculation"

        summary_parts = []

        # Trend
        if 'SMA_20' in indicators and 'SMA_50' in indicators:
            if indicators['SMA_20'] > indicators['SMA_50']:
                summary_parts.append("Uptrend (SMA20>SMA50)")
            else:
                summary_parts.append("Downtrend (SMA20<SMA50)")

        # Momentum
        if 'RSI_14' in indicators:
            rsi = indicators['RSI_14']
            if rsi > 70:
                summary_parts.append(f"Overbought (RSI={rsi:.1f})")
            elif rsi < 30:
                summary_parts.append(f"Oversold (RSI={rsi:.1f})")
            else:
                summary_parts.append(f"Neutral RSI={rsi:.1f}")

        # MACD
        if 'MACD' in indicators and 'MACD_signal' in indicators:
            if indicators['MACD'] > indicators['MACD_signal']:
                summary_parts.append("MACD Bullish")
            else:
                summary_parts.append("MACD Bearish")

        return ", ".join(summary_parts) if summary_parts else "Indicators calculated"
