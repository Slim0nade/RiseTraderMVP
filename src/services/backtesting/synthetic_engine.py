"""
Synthetic trading engine for fast backtesting.

Rule-based trading logic that doesn't require LLM agents.
Designed for hyperparameter optimization and rapid testing (100x+ faster).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np

from .data_replay_engine import MarketTick
from .crude_oil_strategy import CrudeOilStrategy, CrudeOilParams, create_crude_oil_strategy


@dataclass
class SyntheticSignal:
    """
    Trading signal from synthetic engine.

    Attributes:
        action: 'buy', 'sell', 'close', or None
        quantity: Position size
        confidence: Signal confidence (0.0-1.0)
        reason: Human-readable reason for decision
    """
    action: Optional[str]
    quantity: Decimal
    confidence: float
    reason: str


class SyntheticEngine:
    """
    Rule-based trading engine for fast backtesting.

    Implements common technical analysis strategies without LLM overhead:
    - Moving average crossovers
    - RSI-based signals
    - Trend following
    - Mean reversion

    Designed for:
    - Hyperparameter optimization
    - Quick strategy validation
    - Baseline performance comparison
    """

    def __init__(
        self,
        strategy: str = "ma_crossover",
        params: Optional[Dict] = None
    ):
        """
        Initialize synthetic engine with strategy.

        Args:
            strategy: Strategy name ('ma_crossover', 'rsi', 'trend_following')
            params: Strategy-specific parameters

        Supported strategies:
        - ma_crossover: Moving average crossover (params: fast_period, slow_period)
        - rsi: RSI overbought/oversold (params: rsi_period, oversold, overbought)
        - trend_following: Simple trend following (params: trend_period)
        - mean_reversion: Mean reversion (params: lookback, std_threshold)
        """
        self.strategy = strategy
        self.params = params or self._default_params(strategy)

        # Initialize CrudeOil strategy if selected
        self._crude_oil_strategy: Optional[CrudeOilStrategy] = None
        if strategy == "crude_oil_v3":
            self._crude_oil_strategy = create_crude_oil_strategy(**{
                k: v for k, v in self.params.items() 
                if k != 'quantity'
            })
            if 'quantity' in self.params:
                self._crude_oil_strategy.params.quantity = self.params['quantity']

        # Price history for indicators
        self.price_history: List[Decimal] = []
        self.max_history = 200  # Keep last 200 candles

        # Current position state
        self.has_position = False
        self.entry_price: Optional[Decimal] = None

    @staticmethod
    def _default_params(strategy: str) -> Dict:
        """Get default parameters for strategy."""
        defaults = {
            "ma_crossover": {
                "fast_period": 10,
                "slow_period": 30,
                "quantity": Decimal("1.0")
            },
            "rsi": {
                "rsi_period": 14,
                "oversold": 30,
                "overbought": 70,
                "quantity": Decimal("1.0")
            },
            "trend_following": {
                "trend_period": 20,
                "quantity": Decimal("1.0")
            },
            "mean_reversion": {
                "lookback": 20,
                "std_threshold": 2.0,
                "quantity": Decimal("1.0")
            },
            "crude_oil_v3": {
                "ema_fast": 8,
                "ema_slow": 29,
                "rsi_period": 10,
                "rsi_overbought": 68,
                "rsi_oversold": 32,
                "cci_period": 20,
                "cci_overbought": 100,
                "cci_oversold": -80,
                "atr_period": 10,
                "atr_multiplier": 2.0,
                "risk_reward_ratio": 2.5,
                "momentum_period": 10,
                "use_cci_filter": True,
                "use_strict_filter": False,
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
                "quantity": Decimal("1.0")
            }
        }
        return defaults.get(strategy, {})

    def process_tick(self, tick: MarketTick) -> SyntheticSignal:
        """
        Process market tick and generate trading signal.

        Args:
            tick: Market tick data

        Returns:
            SyntheticSignal with trading decision
        """
        # Update price history
        self.price_history.append(tick.close)
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)

        # Route to strategy-specific logic
        if self.strategy == "ma_crossover":
            return self._ma_crossover_strategy(tick)
        elif self.strategy == "rsi":
            return self._rsi_strategy(tick)
        elif self.strategy == "trend_following":
            return self._trend_following_strategy(tick)
        elif self.strategy == "mean_reversion":
            return self._mean_reversion_strategy(tick)
        elif self.strategy == "crude_oil_v3":
            return self._crude_oil_v3_strategy(tick)
        else:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Unknown strategy: {self.strategy}"
            )

    def _ma_crossover_strategy(self, tick: MarketTick) -> SyntheticSignal:
        """
        Moving average crossover strategy.

        Buy when fast MA crosses above slow MA.
        Sell when fast MA crosses below slow MA.
        """
        fast_period = self.params["fast_period"]
        slow_period = self.params["slow_period"]
        quantity = self.params["quantity"]

        # Need enough history
        if len(self.price_history) < slow_period:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Warming up: insufficient history"
            )

        # Calculate moving averages
        prices = np.array([float(p) for p in self.price_history])
        fast_ma = np.mean(prices[-fast_period:])
        slow_ma = np.mean(prices[-slow_period:])

        # Previous MAs for crossover detection
        if len(prices) > slow_period:
            prev_fast_ma = np.mean(prices[-fast_period-1:-1])
            prev_slow_ma = np.mean(prices[-slow_period-1:-1])
        else:
            prev_fast_ma = fast_ma
            prev_slow_ma = slow_ma

        # Detect crossover
        if not self.has_position:
            # Bullish crossover: fast crosses above slow
            if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
                self.has_position = True
                self.entry_price = tick.close
                return SyntheticSignal(
                    action="buy",
                    quantity=quantity,
                    confidence=0.7,
                    reason=f"MA crossover: fast({fast_ma:.4f}) > slow({slow_ma:.4f})"
                )
        else:
            # Bearish crossover: fast crosses below slow
            if prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
                self.has_position = False
                self.entry_price = None
                return SyntheticSignal(
                    action="close",
                    quantity=quantity,
                    confidence=0.7,
                    reason=f"MA crossover: fast({fast_ma:.4f}) < slow({slow_ma:.4f})"
                )

        return SyntheticSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason="No crossover detected"
        )

    def _rsi_strategy(self, tick: MarketTick) -> SyntheticSignal:
        """
        RSI overbought/oversold strategy.

        Buy when RSI < oversold threshold.
        Sell when RSI > overbought threshold.
        """
        rsi_period = self.params["rsi_period"]
        oversold = self.params["oversold"]
        overbought = self.params["overbought"]
        quantity = self.params["quantity"]

        # Need enough history for RSI
        if len(self.price_history) < rsi_period + 1:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Warming up: insufficient history for RSI"
            )

        # Calculate RSI
        rsi = self._calculate_rsi(rsi_period)

        if not self.has_position:
            # Oversold: buy signal
            if rsi < oversold:
                self.has_position = True
                self.entry_price = tick.close
                return SyntheticSignal(
                    action="buy",
                    quantity=quantity,
                    confidence=0.6,
                    reason=f"RSI oversold: {rsi:.2f} < {oversold}"
                )
        else:
            # Overbought: sell signal
            if rsi > overbought:
                self.has_position = False
                self.entry_price = None
                return SyntheticSignal(
                    action="close",
                    quantity=quantity,
                    confidence=0.6,
                    reason=f"RSI overbought: {rsi:.2f} > {overbought}"
                )

        return SyntheticSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"RSI neutral: {rsi:.2f}"
        )

    def _trend_following_strategy(self, tick: MarketTick) -> SyntheticSignal:
        """
        Simple trend following strategy.

        Buy when price is above moving average.
        Sell when price is below moving average.
        """
        trend_period = self.params["trend_period"]
        quantity = self.params["quantity"]

        if len(self.price_history) < trend_period:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Warming up"
            )

        # Calculate trend (moving average)
        prices = np.array([float(p) for p in self.price_history])
        ma = np.mean(prices[-trend_period:])
        current_price = float(tick.close)

        if not self.has_position:
            # Price above MA: buy
            if current_price > ma * 1.01:  # 1% above MA
                self.has_position = True
                self.entry_price = tick.close
                return SyntheticSignal(
                    action="buy",
                    quantity=quantity,
                    confidence=0.5,
                    reason=f"Price above MA: {current_price:.4f} > {ma:.4f}"
                )
        else:
            # Price below MA: sell
            if current_price < ma * 0.99:  # 1% below MA
                self.has_position = False
                self.entry_price = None
                return SyntheticSignal(
                    action="close",
                    quantity=quantity,
                    confidence=0.5,
                    reason=f"Price below MA: {current_price:.4f} < {ma:.4f}"
                )

        return SyntheticSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason="Following trend"
        )

    def _mean_reversion_strategy(self, tick: MarketTick) -> SyntheticSignal:
        """
        Mean reversion strategy.

        Buy when price deviates below mean by threshold.
        Sell when price returns to mean.
        """
        lookback = self.params["lookback"]
        std_threshold = self.params["std_threshold"]
        quantity = self.params["quantity"]

        if len(self.price_history) < lookback:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Warming up"
            )

        # Calculate mean and standard deviation
        prices = np.array([float(p) for p in self.price_history[-lookback:]])
        mean = np.mean(prices)
        std = np.std(prices)
        current_price = float(tick.close)

        # Z-score
        z_score = (current_price - mean) / std if std > 0 else 0

        if not self.has_position:
            # Price significantly below mean: buy (expecting reversion)
            if z_score < -std_threshold:
                self.has_position = True
                self.entry_price = tick.close
                return SyntheticSignal(
                    action="buy",
                    quantity=quantity,
                    confidence=0.6,
                    reason=f"Mean reversion: z-score={z_score:.2f}"
                )
        else:
            # Price returned to mean: close
            if z_score > -0.5:  # Close to mean
                self.has_position = False
                self.entry_price = None
                return SyntheticSignal(
                    action="close",
                    quantity=quantity,
                    confidence=0.6,
                    reason=f"Reverted to mean: z-score={z_score:.2f}"
                )

        return SyntheticSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"Waiting: z-score={z_score:.2f}"
        )

    def _calculate_rsi(self, period: int) -> float:
        """
        Calculate RSI indicator.

        Args:
            period: RSI period (typically 14)

        Returns:
            RSI value (0-100)
        """
        if len(self.price_history) < period + 1:
            return 50.0  # Neutral RSI

        # Calculate price changes
        prices = np.array([float(p) for p in self.price_history[-(period+1):]])
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Average gains and losses
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0  # All gains

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _crude_oil_v3_strategy(self, tick: MarketTick) -> SyntheticSignal:
        """
        CrudeOIL Trader V3 strategy.

        Multi-indicator strategy with EMA, RSI, CCI, Momentum confirmation.
        Includes ATR-based stop loss/take profit and time filters.
        """
        if self._crude_oil_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="CrudeOil strategy not initialized"
            )
        
        # Delegate to the full strategy implementation
        signal = self._crude_oil_strategy.process_tick(tick)

        # DEBUG logging for signal generation (log every 500th tick to avoid spam)
        from structlog import get_logger
        logger = get_logger()
        if not hasattr(self, '_tick_count'):
            self._tick_count = 0
        self._tick_count += 1

        if self._tick_count % 500 == 0 or signal.action:
            logger.info(
                "crude_oil_signal_sample",
                tick_num=self._tick_count,
                action=signal.action,
                quantity=float(signal.quantity) if signal.quantity else 0,
                confidence=signal.confidence,
                reason=signal.reason[:50] if signal.reason else None,
                timestamp=str(tick.timestamp)
            )

        # Sync position state
        self.has_position = self._crude_oil_strategy.has_position
        self.entry_price = self._crude_oil_strategy.entry_price

        # Convert CrudeOilSignal to SyntheticSignal
        return SyntheticSignal(
            action=signal.action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason
        )

    def reset(self) -> None:
        """Reset engine state for new backtest."""
        self.price_history.clear()
        self.has_position = False
        self.entry_price = None
        
        # Reset CrudeOil strategy if initialized
        if self._crude_oil_strategy is not None:
            self._crude_oil_strategy.reset()

    def get_state(self) -> Dict:
        """
        Get current engine state.

        Returns:
            Dictionary with current state information
        """
        return {
            "strategy": self.strategy,
            "params": self.params,
            "has_position": self.has_position,
            "entry_price": str(self.entry_price) if self.entry_price else None,
            "price_history_length": len(self.price_history)
        }
