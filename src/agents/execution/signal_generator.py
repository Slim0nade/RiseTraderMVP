"""
SignalGeneratorAgent - Multi-Strategy Trading Signal Generation

Responsibilities:
- Subscribe to new_tick, forecast_updated, regime_changed events
- Combine multiple trading strategies (momentum, mean reversion, breakout, ML)
- Calculate signal confidence using weighted voting
- Emit signal_generated events with position sizing recommendations

Performance Target: <50ms signal generation
"""

import asyncio
import time
from collections import deque
from typing import Dict, Any, Optional, List

import numpy as np
import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority
from src.strategies.signals.contrarian_filter import ContrariánFilter, create_contrarian_filter

logger = structlog.get_logger(__name__)


class SignalGeneratorAgent(BaseAgent):
    """
    Generates trading signals from multiple strategies

    Strategy Combination:
    1. Momentum Strategy (weight: 0.3)
    2. Mean Reversion Strategy (weight: 0.25)
    3. Breakout Strategy (weight: 0.25)
    4. ML Forecast Strategy (weight: 0.2)

    Signal Calculation:
    - Weighted vote from all enabled strategies
    - Confidence threshold (default: 0.6)
    - Position type: BUY, SELL, or HOLD
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=1,  # Highest priority - critical for trading
        )

        # Strategy configuration
        self.strategies = config.get("strategies", [])
        self.signal_threshold = config.get("signal_threshold", 0.6)
        self.min_confidence = config.get("min_confidence", 0.5)

        # Strategy weights
        self.strategy_weights = {}
        for strategy in self.strategies:
            if strategy.get("enabled", True):
                self.strategy_weights[strategy["name"]] = strategy.get("weight", 0.25)

        # Market data
        self.price_history: Dict[str, deque] = {}
        self.max_history = 100  # Keep last 100 bars

        # ML forecast
        self.latest_forecast: Optional[Dict[str, Any]] = None

        # Market regime
        self.current_regime: Optional[str] = None

        # Signal stats
        self.signals_generated = 0
        self.signals_buy = 0
        self.signals_sell = 0
        self.signals_hold = 0

        # Contrarian filter: flips signals when recent loss rate exceeds threshold.
        # Disable by setting enable_contrarian_filter=False in agent config.
        self.enable_contrarian_filter: bool = config.get("enable_contrarian_filter", True)
        self._contrarian_filter: Optional[ContrariánFilter] = (
            create_contrarian_filter() if self.enable_contrarian_filter else None
        )

    async def initialize(self) -> None:
        """Subscribe to relevant events"""
        self.subscribe_to_event("new_tick")
        self.subscribe_to_event("forecast_updated")
        self.subscribe_to_event("regime_changed")

        self.logger.info(
            "signal_generator_initialized",
            strategies=list(self.strategy_weights.keys()),
            threshold=self.signal_threshold,
        )

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self.logger.info(
            "signal_generator_cleanup",
            signals_generated=self.signals_generated,
            buy=self.signals_buy,
            sell=self.signals_sell,
            hold=self.signals_hold,
        )

    async def process_event(self, event: Event) -> None:
        """Process incoming events"""
        start_time = time.time()

        try:
            if event.event_type == "new_tick":
                await self._on_new_tick(event.data)

            elif event.event_type == "forecast_updated":
                await self._on_forecast_updated(event.data)

            elif event.event_type == "regime_changed":
                await self._on_regime_changed(event.data)

            processing_time = time.time() - start_time
            if processing_time > 0.05:  # Warn if >50ms
                self.logger.warning(
                    "signal_generation_slow",
                    event_type=event.event_type,
                    processing_time=processing_time,
                )

        except Exception as e:
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

    async def _on_new_tick(self, tick_data: Dict[str, Any]) -> None:
        """
        Handle new tick data

        Updates price history and triggers signal generation
        """
        symbol = tick_data.get("symbol")
        close = tick_data.get("close")

        if not symbol or close is None:
            return

        # Initialize price history for symbol
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.max_history)

        # Add to history
        self.price_history[symbol].append({
            "timestamp": tick_data.get("timestamp"),
            "open": tick_data.get("open"),
            "high": tick_data.get("high"),
            "low": tick_data.get("low"),
            "close": close,
            "volume": tick_data.get("volume", 0),
        })

        # Generate signal if we have enough history
        if len(self.price_history[symbol]) >= 20:  # Minimum bars
            await self._generate_signal(symbol)

    async def _on_forecast_updated(self, forecast_data: Dict[str, Any]) -> None:
        """Handle ML forecast update"""
        self.latest_forecast = forecast_data

        self.logger.debug(
            "forecast_updated",
            symbol=forecast_data.get("symbol"),
            prediction=forecast_data.get("prediction"),
            confidence=forecast_data.get("confidence"),
        )

        # Re-evaluate signal with new forecast
        symbol = forecast_data.get("symbol")
        if symbol and symbol in self.price_history:
            await self._generate_signal(symbol)

    async def _on_regime_changed(self, regime_data: Dict[str, Any]) -> None:
        """Handle market regime change"""
        self.current_regime = regime_data.get("regime")

        self.logger.info(
            "regime_changed",
            old_regime=regime_data.get("previous_regime"),
            new_regime=self.current_regime,
        )

        # Re-evaluate all signals with new regime
        for symbol in self.price_history.keys():
            await self._generate_signal(symbol)

    def _get_regime_weights(self, regime: Optional[str]) -> tuple:
        """
        Return (strategy_weights_dict, position_size_multiplier) for a given regime.

        Weights are relative (do not need to sum to 1.0).
        ml_forecast weight is 0.0 for all regimes — ML is fake until Phase 4.

        Args:
            regime: One of "high_volatility", "trending_up", "trending_down",
                    "ranging", "low_volatility", or None

        Returns:
            Tuple of (weights_dict, position_size_multiplier)

        Ranges:
            - weights: 0.0 to 0.5 per strategy
            - multiplier: 0.5 (low_vol) or 1.0 (all others)
        """
        if regime == "high_volatility":
            return (
                {
                    "crude_oil_v3": 0.4,
                    "ma_crossover": 0.3,
                    "momentum": 0.2,
                    "mean_reversion": 0.1,
                    "breakout": 0.0,
                    "ml_forecast": 0.0,
                },
                1.0,
            )
        elif regime in ("trending_up", "trending_down"):
            return (
                {
                    "ma_crossover": 0.4,
                    "momentum": 0.35,
                    "breakout": 0.25,
                    "crude_oil_v3": 0.0,
                    "mean_reversion": 0.0,
                    "ml_forecast": 0.0,
                },
                1.0,
            )
        elif regime == "ranging":
            return (
                {
                    "value_area": 0.4,
                    "mean_reversion": 0.35,
                    "momentum": 0.15,
                    "breakout": 0.1,
                    "crude_oil_v3": 0.0,
                    "ma_crossover": 0.0,
                    "ml_forecast": 0.0,
                },
                1.0,
            )
        elif regime == "low_volatility":
            return (
                {
                    "value_area": 0.5,
                    "mean_reversion": 0.3,
                    "momentum": 0.0,
                    "breakout": 0.0,
                    "crude_oil_v3": 0.0,
                    "ma_crossover": 0.0,
                    "ml_forecast": 0.0,
                },
                0.5,  # Half position size in low-volatility regimes
            )
        else:
            # None or unknown regime: use default configured weights unchanged
            return (self.strategy_weights, 1.0)

    async def _generate_signal(self, symbol: str) -> None:
        """
        Generate trading signal by combining all strategies

        Args:
            symbol: Trading symbol
        """
        if symbol not in self.price_history:
            return

        prices = list(self.price_history[symbol])
        if len(prices) < 20:
            return

        # Select weights for current regime (replaces fixed self.strategy_weights)
        regime_weights, size_multiplier = self._get_regime_weights(self.current_regime)

        self.logger.debug(
            "regime_weights_active",
            regime=self.current_regime,
            weights=regime_weights,
            size_multiplier=size_multiplier,
        )

        # Calculate each strategy signal using regime-adjusted weights as gate
        strategy_signals = {}

        if regime_weights.get("momentum", 0.0) > 0.0:
            strategy_signals["momentum"] = self._momentum_strategy(prices)

        if regime_weights.get("mean_reversion", 0.0) > 0.0:
            strategy_signals["mean_reversion"] = self._mean_reversion_strategy(prices)

        if regime_weights.get("breakout", 0.0) > 0.0:
            strategy_signals["breakout"] = self._breakout_strategy(prices)

        # ml_forecast always skipped — fake model (Phase 4 fix)
        # if regime_weights.get("ml_forecast", 0.0) > 0.0 and self.latest_forecast:
        #     strategy_signals["ml_forecast"] = self._ml_forecast_strategy()

        # Combine signals using weighted voting with regime weights
        combined_signal = self._combine_signals(strategy_signals, regime_weights)

        # Check threshold
        if abs(combined_signal["score"]) < self.signal_threshold:
            return  # Signal too weak

        # Check confidence
        if combined_signal["confidence"] < self.min_confidence:
            return

        # Determine action
        if combined_signal["score"] > 0:
            action = "BUY"
            self.signals_buy += 1
        elif combined_signal["score"] < 0:
            action = "SELL"
            self.signals_sell += 1
        else:
            action = "HOLD"
            self.signals_hold += 1

        self.signals_generated += 1

        # Apply contrarian filter: if recent loss rate exceeds threshold, flip direction.
        # Filter uses lowercase buy/sell; signal_generator uses uppercase BUY/SELL.
        confidence = combined_signal["confidence"]
        contrarian_flipped = False
        contrarian_reason = None
        if self._contrarian_filter is not None and action in ("BUY", "SELL"):
            cf_result = await self._contrarian_filter.apply(
                strategy_name="combined",
                action=action.lower(),
                confidence=confidence,
                symbol=symbol,
            )
            if cf_result.was_flipped:
                action = cf_result.filtered_action.upper()
                confidence = cf_result.filtered_confidence
                contrarian_flipped = True
                contrarian_reason = cf_result.reason
                self.logger.info(
                    "contrarian_filter_flip",
                    symbol=symbol,
                    original_action=cf_result.original_action,
                    filtered_action=cf_result.filtered_action,
                    loss_rate=round(cf_result.loss_rate, 3),
                    trades_analyzed=cf_result.trades_analyzed,
                    reason=cf_result.reason,
                )

        # Emit signal
        signal_data = {
            "symbol": symbol,
            "action": action,
            "score": combined_signal["score"],
            "confidence": confidence,
            "strategy_votes": strategy_signals,
            "current_price": prices[-1]["close"],
            "regime": self.current_regime,
            "position_size_multiplier": size_multiplier,
            "contrarian_flipped": contrarian_flipped,
            "contrarian_reason": contrarian_reason,
            "timestamp": time.time(),
        }

        await self.publish_event(
            event_type="signal_generated",
            data=signal_data,
            priority=EventPriority.HIGH,
        )

        # Store in context
        await self.set_context(f"last_signal_{symbol}", signal_data, ttl=300)

        self.logger.info(
            "signal_generated",
            symbol=symbol,
            action=action,
            score=combined_signal["score"],
            confidence=combined_signal["confidence"],
        )

    def _momentum_strategy(self, prices: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Momentum strategy: Follow the trend

        Signal:
        - Positive if price > short MA and short MA > long MA (bullish)
        - Negative if price < short MA and short MA < long MA (bearish)
        """
        closes = np.array([p["close"] for p in prices])

        # Calculate moving averages
        short_ma = np.mean(closes[-10:])  # 10-period MA
        long_ma = np.mean(closes[-30:])  # 30-period MA
        current = closes[-1]

        # Calculate momentum score
        if current > short_ma and short_ma > long_ma:
            score = min((current - long_ma) / long_ma, 1.0)  # Bullish
        elif current < short_ma and short_ma < long_ma:
            score = max((current - long_ma) / long_ma, -1.0)  # Bearish
        else:
            score = 0.0  # Neutral

        return {"score": score, "confidence": 0.7}

    def _mean_reversion_strategy(self, prices: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Mean reversion strategy: Buy oversold, sell overbought

        Uses Bollinger Bands:
        - Buy if price < lower band
        - Sell if price > upper band
        """
        closes = np.array([p["close"] for p in prices])

        # Bollinger Bands (20 period, 2 std)
        ma = np.mean(closes[-20:])
        std = np.std(closes[-20:])
        upper = ma + 2 * std
        lower = ma - 2 * std
        current = closes[-1]

        # Calculate score
        if current < lower:
            # Oversold - buy signal
            score = min((lower - current) / std, 1.0)
        elif current > upper:
            # Overbought - sell signal
            score = max((upper - current) / std, -1.0)
        else:
            score = 0.0

        return {"score": score, "confidence": 0.6}

    def _breakout_strategy(self, prices: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Breakout strategy: Trade range breakouts

        Signal:
        - Buy if price breaks above recent high
        - Sell if price breaks below recent low
        """
        closes = np.array([p["close"] for p in prices])
        highs = np.array([p["high"] for p in prices])
        lows = np.array([p["low"] for p in prices])

        # Recent range (20 periods)
        recent_high = np.max(highs[-20:-1])  # Exclude current bar
        recent_low = np.min(lows[-20:-1])
        current = closes[-1]

        # Breakout threshold
        range_size = recent_high - recent_low
        breakout_threshold = range_size * 0.01  # 1% beyond range

        # Calculate score
        if current > recent_high + breakout_threshold:
            # Bullish breakout
            score = min((current - recent_high) / range_size, 1.0)
        elif current < recent_low - breakout_threshold:
            # Bearish breakout
            score = max((current - recent_low) / range_size, -1.0)
        else:
            score = 0.0

        return {"score": score, "confidence": 0.65}

    def _ml_forecast_strategy(self) -> Dict[str, float]:
        """
        ML forecast strategy: Use ML prediction

        Signal based on ML model prediction
        """
        if not self.latest_forecast:
            return {"score": 0.0, "confidence": 0.0}

        prediction = self.latest_forecast.get("prediction", 0.5)
        confidence = self.latest_forecast.get("confidence", 0.0)

        # Convert prediction to signal score (-1 to 1)
        # Assuming prediction is probability of upward movement (0-1)
        score = (prediction - 0.5) * 2  # Map [0,1] to [-1,1]

        return {"score": score, "confidence": confidence}

    def _combine_signals(
        self,
        strategy_signals: Dict[str, Dict[str, float]],
        regime_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Combine strategy signals using weighted voting.

        Args:
            strategy_signals: Dict of strategy_name -> {score, confidence}
            regime_weights: Weights to use for combination. If None, falls back to
                            self.strategy_weights. Obtained from _get_regime_weights().

        Returns:
            Combined signal with score and confidence.
            score range: [-1.0, 1.0]
            confidence range: [0.0, 1.0]
        """
        weights = regime_weights if regime_weights is not None else self.strategy_weights

        weighted_sum = 0.0
        total_weight = 0.0
        confidence_sum = 0.0
        count = 0

        for strategy_name, signal in strategy_signals.items():
            weight = weights.get(strategy_name, 0.0)
            if weight <= 0.0:
                continue

            score = signal.get("score", 0.0)
            confidence = signal.get("confidence", 0.0)

            weighted_sum += score * weight * confidence
            total_weight += weight * confidence
            confidence_sum += confidence
            count += 1

        if total_weight == 0 or count == 0:
            return {"score": 0.0, "confidence": 0.0}

        combined_score = weighted_sum / total_weight
        combined_confidence = confidence_sum / count

        return {
            "score": combined_score,
            "confidence": combined_confidence,
        }
