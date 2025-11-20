"""
RegimeDetectionAgent - Market Regime Classification

Responsibilities:
- Classify market conditions (trending, ranging, volatile)
- Calculate regime-specific metrics (ADX, Bollinger Bands width, ATR)
- Emit regime_changed events when regime shifts
- Update regime context for other agents

Performance Target: <100ms regime detection
"""

import asyncio
import time
from collections import deque
from typing import Dict, Any, Optional, List

import numpy as np
import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class RegimeDetectionAgent(BaseAgent):
    """
    Detects and classifies market regimes

    Regime Types:
    1. trending_up - Strong upward trend
    2. trending_down - Strong downward trend
    3. ranging - Sideways, mean-reverting market
    4. high_volatility - Elevated volatility
    5. low_volatility - Compressed volatility

    Detection Methods:
    - ADX (Average Directional Index) for trend strength
    - Bollinger Bands width for volatility
    - ATR (Average True Range) for range
    - Linear regression slope for direction
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=6,  # Data/ML layer
        )

        # Configuration
        self.regimes = config.get("regimes", [
            "trending_up",
            "trending_down",
            "ranging",
            "high_volatility",
            "low_volatility",
        ])
        self.lookback_period = config.get("lookback_period", 100)
        self.update_frequency = config.get("update_frequency", 60)  # seconds

        # Price history
        self.price_history: Dict[str, deque] = {}

        # Current regime per symbol
        self.current_regime: Dict[str, str] = {}

        # Last update timestamp
        self.last_update: Dict[str, float] = {}

        # Stats
        self.regime_changes = 0
        self.regime_duration: Dict[str, float] = {}

    async def initialize(self) -> None:
        """Subscribe to events"""
        self.subscribe_to_event("new_tick")

        self.logger.info(
            "regime_detection_agent_initialized",
            regimes=self.regimes,
            lookback_period=self.lookback_period,
            update_frequency=self.update_frequency,
        )

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self.logger.info(
            "regime_detection_agent_cleanup",
            regime_changes=self.regime_changes,
            avg_duration=np.mean(list(self.regime_duration.values())) if self.regime_duration else 0,
        )

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        try:
            if event.event_type == "new_tick":
                await self._on_new_tick(event.data)

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_new_tick(self, tick_data: Dict[str, Any]) -> None:
        """
        Update regime on new tick

        Rate-limited by update_frequency
        """
        symbol = tick_data.get("symbol")

        # Initialize history
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.lookback_period)
            self.last_update[symbol] = 0

        # Add tick to history
        self.price_history[symbol].append(tick_data)

        # Check if enough time passed since last update
        current_time = time.time()
        if current_time - self.last_update[symbol] < self.update_frequency:
            return

        # Detect regime
        if len(self.price_history[symbol]) >= 20:  # Minimum data
            await self._detect_regime(symbol)
            self.last_update[symbol] = current_time

    async def _detect_regime(self, symbol: str) -> None:
        """
        Detect current market regime

        Args:
            symbol: Trading symbol
        """
        start_time = time.time()

        prices = list(self.price_history[symbol])

        # Calculate regime indicators
        adx = self._calculate_adx(prices)
        bb_width = self._calculate_bb_width(prices)
        atr = self._calculate_atr(prices)
        slope = self._calculate_slope(prices)
        volatility = self._calculate_volatility(prices)

        # Classify regime
        new_regime = self._classify_regime(adx, bb_width, atr, slope, volatility)

        # Check if regime changed
        old_regime = self.current_regime.get(symbol)

        if new_regime != old_regime:
            self.regime_changes += 1

            # Track duration
            if old_regime:
                duration = current_time - self.regime_duration.get(symbol, current_time)
                self.regime_duration[symbol] = duration

            # Update current regime
            self.current_regime[symbol] = new_regime

            # Emit regime change
            regime_data = {
                "symbol": symbol,
                "regime": new_regime,
                "previous_regime": old_regime,
                "adx": adx,
                "bb_width": bb_width,
                "atr": atr,
                "slope": slope,
                "volatility": volatility,
                "timestamp": time.time(),
            }

            await self.publish_event(
                event_type="regime_changed",
                data=regime_data,
                priority=EventPriority.HIGH,
            )

            # Store in context
            await self.set_context(f"regime_{symbol}", new_regime, ttl=3600)
            await self.set_context(f"volatility_{symbol}", volatility, ttl=3600)

            self.logger.info(
                "regime_changed",
                symbol=symbol,
                old_regime=old_regime,
                new_regime=new_regime,
                adx=adx,
                volatility=volatility,
            )

        detection_time = time.time() - start_time

        if detection_time > 0.1:  # Warn if >100ms
            self.logger.warning(
                "regime_detection_slow",
                symbol=symbol,
                detection_time=detection_time,
            )

    def _calculate_adx(self, prices: List[Dict[str, Any]], period: int = 14) -> float:
        """
        Calculate Average Directional Index (ADX)

        Measures trend strength (0-100):
        - ADX < 20: Weak or no trend
        - ADX 20-40: Strong trend
        - ADX > 40: Very strong trend

        Args:
            prices: Price data
            period: ADX period

        Returns:
            ADX value (0-100)
        """
        if len(prices) < period + 1:
            return 25.0  # Neutral

        highs = np.array([p["high"] for p in prices])
        lows = np.array([p["low"] for p in prices])
        closes = np.array([p["close"] for p in prices])

        # True Range
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        # Directional Movement
        plus_dm = np.maximum(highs[1:] - highs[:-1], 0)
        minus_dm = np.maximum(lows[:-1] - lows[1:], 0)

        # Smooth with EMA
        atr = self._ema(tr, period)
        plus_di = 100 * self._ema(plus_dm, period) / atr[-1] if atr[-1] != 0 else 0
        minus_di = 100 * self._ema(minus_dm, period) / atr[-1] if atr[-1] != 0 else 0

        # Calculate ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0
        adx = dx  # Simplified - full ADX needs smoothing

        return float(np.clip(adx, 0, 100))

    def _calculate_bb_width(self, prices: List[Dict[str, Any]], period: int = 20) -> float:
        """
        Calculate Bollinger Bands width

        Normalized width indicates volatility state

        Args:
            prices: Price data
            period: BB period

        Returns:
            Normalized BB width
        """
        if len(prices) < period:
            return 0.04  # Default 4%

        closes = np.array([p["close"] for p in prices])

        ma = np.mean(closes[-period:])
        std = np.std(closes[-period:])

        # Bollinger Bands
        upper = ma + 2 * std
        lower = ma - 2 * std

        # Width normalized by price
        width = (upper - lower) / ma if ma != 0 else 0.04

        return float(width)

    def _calculate_atr(self, prices: List[Dict[str, Any]], period: int = 14) -> float:
        """
        Calculate Average True Range (ATR)

        Measures volatility

        Args:
            prices: Price data
            period: ATR period

        Returns:
            ATR value (normalized)
        """
        if len(prices) < period + 1:
            return 0.02  # Default 2%

        highs = np.array([p["high"] for p in prices])
        lows = np.array([p["low"] for p in prices])
        closes = np.array([p["close"] for p in prices])

        # True Range
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        # Average
        atr = np.mean(tr[-period:])

        # Normalize by price
        normalized_atr = atr / closes[-1] if closes[-1] != 0 else 0.02

        return float(normalized_atr)

    def _calculate_slope(self, prices: List[Dict[str, Any]], period: int = 20) -> float:
        """
        Calculate linear regression slope

        Measures trend direction

        Args:
            prices: Price data
            period: Lookback period

        Returns:
            Slope (positive = uptrend, negative = downtrend)
        """
        if len(prices) < period:
            return 0.0

        closes = np.array([p["close"] for p in prices[-period:]])
        x = np.arange(len(closes))

        # Linear regression
        slope, _ = np.polyfit(x, closes, 1)

        # Normalize by price
        normalized_slope = slope / closes[-1] if closes[-1] != 0 else 0.0

        return float(normalized_slope)

    def _calculate_volatility(self, prices: List[Dict[str, Any]], period: int = 20) -> float:
        """
        Calculate historical volatility

        Standard deviation of returns

        Args:
            prices: Price data
            period: Lookback period

        Returns:
            Volatility (annualized)
        """
        if len(prices) < period + 1:
            return 0.02  # Default 2%

        closes = np.array([p["close"] for p in prices])

        # Calculate returns
        returns = np.diff(closes[-period:]) / closes[-(period + 1):-1]

        # Standard deviation
        volatility = np.std(returns)

        # Annualize (assuming 1-minute bars, 252 trading days)
        annualized_vol = volatility * np.sqrt(252 * 24 * 60)

        return float(annualized_vol)

    def _classify_regime(
        self,
        adx: float,
        bb_width: float,
        atr: float,
        slope: float,
        volatility: float,
    ) -> str:
        """
        Classify regime based on indicators

        Priority:
        1. Volatility regimes (high/low vol)
        2. Trend regimes (trending up/down)
        3. Range regime

        Args:
            adx: Trend strength
            bb_width: Bollinger Bands width
            atr: Average True Range
            slope: Price slope
            volatility: Historical volatility

        Returns:
            Regime name
        """
        # Thresholds
        high_vol_threshold = 0.03  # 3%
        low_vol_threshold = 0.01  # 1%
        strong_trend_adx = 30
        slope_threshold = 0.0001

        # 1. High volatility regime
        if volatility > high_vol_threshold or bb_width > 0.06:
            return "high_volatility"

        # 2. Low volatility regime
        if volatility < low_vol_threshold and bb_width < 0.02:
            return "low_volatility"

        # 3. Trending regimes
        if adx > strong_trend_adx:
            if slope > slope_threshold:
                return "trending_up"
            elif slope < -slope_threshold:
                return "trending_down"

        # 4. Ranging regime (default)
        return "ranging"

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        Calculate Exponential Moving Average

        Args:
            data: Input data
            period: EMA period

        Returns:
            EMA values
        """
        if len(data) == 0:
            return np.array([])

        alpha = 2 / (period + 1)
        ema = np.zeros(len(data))
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]

        return ema
