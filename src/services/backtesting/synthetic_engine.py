"""
Synthetic trading engine for fast backtesting.

Rule-based trading logic that doesn't require LLM agents.
Designed for hyperparameter optimization and rapid testing (100x+ faster).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np

from src.services.market_tick import MarketTick
from .crude_oil_strategy import CrudeOilStrategy, CrudeOilParams, create_crude_oil_strategy
from .value_area_strategy import ValueAreaStrategy, ValueAreaParams, create_value_area_strategy
from src.strategies.spreads.crack_spread import CrackSpreadStrategy, create_crack_spread_strategy
from src.strategies.spreads.wti_brent_spread import WTIBrentSpreadStrategy, create_wti_brent_spread_strategy
from src.strategies.agriculture.seasonal_ma import SeasonalMAStrategy, create_seasonal_ma_strategy
from src.strategies.carry.gbpjpy_carry import GBPJPYCarryStrategy, create_gbpjpy_carry_strategy
from src.strategies.crisis.vix_regime import VixRegimeStrategy, create_vix_regime_strategy
from src.strategies.crisis.crash_portfolio import CrashPortfolioStrategy, create_crash_portfolio_strategy


@dataclass
class SyntheticSignal:
    """
    Trading signal from synthetic engine.

    Attributes:
        action: 'buy', 'sell', 'close', or None
        quantity: Position size (primary leg)
        confidence: Signal confidence (0.0-1.0)
        reason: Human-readable reason for decision
        stop_loss: Optional stop loss price for the trade
        take_profit: Optional take profit price for the trade
        secondary_symbol: Secondary leg symbol (spread strategies only, e.g. 'GASOLINE', 'BRENT_OIL')
        secondary_action: Secondary leg action — opposite of primary for dollar-neutral spreads
        secondary_quantity: Secondary leg lot size (e.g. 0.42 GASOLINE lots per 1 CrudeOIL lot)

    For spread strategies:
        - primary leg  = (action, quantity) on the strategy's primary symbol
        - secondary leg = (secondary_action, secondary_quantity) on secondary_symbol
        - Both legs must be executed atomically; P&L is the sum of both legs
        - Single-symbol strategies leave secondary_* fields as None
    """
    action: Optional[str]
    quantity: Decimal
    confidence: float
    reason: str
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    # Spread/multi-leg fields (None for single-symbol strategies)
    secondary_symbol: Optional[str] = None
    secondary_action: Optional[str] = None
    secondary_quantity: Optional[Decimal] = None


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

        # Initialize Value Area strategy if selected
        self._value_area_strategy: Optional[ValueAreaStrategy] = None
        if strategy == "value_area":
            self._value_area_strategy = create_value_area_strategy(**{
                k: v for k, v in self.params.items()
                if k != 'quantity'
            })
            if 'quantity' in self.params:
                self._value_area_strategy.params.quantity = self.params['quantity']

        # Initialize Crack Spread strategy if selected
        # Note: multi-symbol — accepts ticks from CrudeOIL and GASOLINE
        self._crack_spread_strategy: Optional[CrackSpreadStrategy] = None
        if strategy == "crack_spread":
            self._crack_spread_strategy = create_crack_spread_strategy(**{
                k: v for k, v in self.params.items()
                if k != 'quantity'
            })

        # Initialize WTI-Brent Spread strategy if selected
        # Note: multi-symbol — accepts ticks from CrudeOIL and BRENT_OIL
        self._wti_brent_strategy: Optional[WTIBrentSpreadStrategy] = None
        if strategy == "wti_brent_spread":
            self._wti_brent_strategy = create_wti_brent_spread_strategy(**{
                k: v for k, v in self.params.items()
                if k not in ('quantity',)
            })

        # Initialize Seasonal MA strategy if selected (CORN or WHEAT)
        self._seasonal_ma_strategy: Optional[SeasonalMAStrategy] = None
        if strategy in ("seasonal_ma_corn", "seasonal_ma_wheat"):
            symbol_for_strategy = "CORN" if strategy == "seasonal_ma_corn" else "WHEAT"
            init_params = {k: v for k, v in self.params.items() if k != 'quantity'}
            init_params["symbol"] = symbol_for_strategy
            self._seasonal_ma_strategy = create_seasonal_ma_strategy(**init_params)
            if 'quantity' in self.params:
                self._seasonal_ma_strategy.params.quantity = self.params['quantity']

        # Initialize GBPJPY Carry Trade strategy if selected
        self._gbpjpy_carry_strategy: Optional[GBPJPYCarryStrategy] = None
        if strategy == "gbpjpy_carry":
            self._gbpjpy_carry_strategy = create_gbpjpy_carry_strategy(**{
                k: v for k, v in self.params.items()
                if k != 'quantity'
            })
            if 'quantity' in self.params:
                self._gbpjpy_carry_strategy.params.quantity = self.params['quantity']

        # Initialize VIX Regime strategy if selected
        # Note: consumes USA500 ticks; returns regime multipliers, never trades directly
        self._vix_regime_strategy: Optional[VixRegimeStrategy] = None
        if strategy == "vix_regime":
            init_params = {k: v for k, v in self.params.items() if k != 'quantity'}
            self._vix_regime_strategy = create_vix_regime_strategy(**init_params)
            if 'quantity' in self.params:
                self._vix_regime_strategy.params.quantity = self.params['quantity']

        # Initialize Crash Portfolio strategy if selected
        # Note: multi-symbol — accepts ticks from USA500, CrudeOIL, USA100, GOLD, etc.
        # In backtest mode operates on the primary_symbol only.
        self._crash_portfolio_strategy: Optional[CrashPortfolioStrategy] = None
        if strategy == "crash_portfolio":
            init_params = {k: v for k, v in self.params.items() if k != 'quantity'}
            self._crash_portfolio_strategy = create_crash_portfolio_strategy(**init_params)
            if 'quantity' in self.params:
                self._crash_portfolio_strategy.params.quantity = self.params['quantity']

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
            },
            "value_area": {
                "lookback_periods": 24,
                "value_area_percent": 0.70,
                "tpo_resolution": 0.10,
                "require_rejection": True,
                "min_penetration_atr": 0.3,
                "max_penetration_atr": 2.0,
                "atr_period": 14,
                "stop_atr_multiplier": 1.5,
                "target_mode": "poc",
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
                "quantity": Decimal("1.0")
            },
            # ── Phase 2: Multi-instrument + Spread strategies ──────────────
            # RISK NOTE: Lot sizes below are fixed for signal-quality measurement.
            # The 2% account-risk cap (CLAUDE.md ABSOLUTE RULE) is enforced only in
            # the live/paper execution path via RiskManagerAgent._calculate_position_size().
            # When sizing for live trading, RiskManagerAgent overrides these lot sizes.
            # Do NOT add a 2% cap here — it would distort backtest P&L comparisons
            # and make it impossible to compare strategy quality across accounts.
            "crack_spread": {
                # Spread: gasoline_barrel_price − crude_price (= gas_gal × 42 − crude)
                # Entry at ±1.5σ, exit at ±0.3σ (mean), stop at 2.5σ
                # Hedge ratio: 0.42 GASOLINE lots per 1 CrudeOIL lot (dollar-neutral)
                "lookback": 20,
                "entry_sigma": 1.5,
                "exit_sigma": 0.3,
                "stop_sigma": 2.5,
                "q2_sigma_addon": 0.3,       # Q2 (Apr-Jun): wider entry (+0.3σ)
                "q3_sigma_addon": 0.5,       # Q3 (Jul-Sep): widest entry (+0.5σ)
                "crude_lots": Decimal("1.0"),  # Fixed for backtest (live sizing uses RiskManagerAgent)
                "crude_symbol": "CrudeOIL",
                "gasoline_symbol": "GASOLINE",
                "max_tick_age_seconds": 3600,
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
                "enable_seasonality": True,
            },
            "wti_brent_spread": {
                # Spread: BRENT_OIL − CrudeOIL (same barrel units, no conversion)
                # Entry at ±1.5σ, exit at ±0.3σ band, stop at 2.5σ
                # 1:1 lot ratio (both 1,000 bbl contracts)
                "lookback_period": 20,
                "entry_sigma": 1.5,
                "exit_band": 0.3,
                "stop_sigma": 2.5,
                "quantity": Decimal("1.0"),  # Fixed for backtest (live sizing uses RiskManagerAgent)
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
            },
            "seasonal_ma_corn": {
                # CORN: seasonal MA crossover. Long bias Mar-Jun, Short Sep-Nov, Neutral otherwise.
                "symbol": "CORN",
                "fast_period": 10,
                "slow_period": 30,
                "quantity": Decimal("0.01"),
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
                "hold_through_neutral": True,
            },
            "seasonal_ma_wheat": {
                # WHEAT: seasonal MA crossover. Long bias Feb-May, Short Jul-Sep, Neutral otherwise.
                "symbol": "WHEAT",
                "fast_period": 10,
                "slow_period": 30,
                "quantity": Decimal("0.01"),
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
                "hold_through_neutral": True,
            },
            "gbpjpy_carry": {
                # GBPJPY long-only carry trade. Entry on 20-SMA pullback while above 50-SMA.
                # Stop: 2× ATR(14). Exit: close below 50-SMA.
                "trend_sma_period": 50,
                "entry_sma_period": 20,
                "atr_period": 14,
                "atr_stop_multiplier": 2.0,
                "pullback_tolerance": 0.003,
                "quantity": Decimal("0.01"),
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
            },
            # ── Phase 3: Crisis / Regime strategies ───────────────────────────
            # RISK NOTE: vix_regime never trades directly. It emits regime signals
            # and strategy_multipliers that other strategies consume for sizing.
            # Sizing multipliers only apply in the live/paper path (RiskManagerAgent).
            "vix_regime": {
                # USA500 rolling drawdown proxy for VIX.
                # Elevated: 5-day drop > 3% → momentum 2x, carry/mean-rev disabled
                # Crisis:  10-day drop > 7% → crude_oil_v3 2.5x, crash_portfolio on
                "proxy_symbol": "USA500",
                "elevated_threshold_pct": 3.0,
                "elevated_lookback": 5,
                "crisis_threshold_pct": 7.0,
                "crisis_lookback": 10,
                "quantity": Decimal("1.0"),
            },
            "crash_portfolio": {
                # Crisis pre-positioning: SHORT crude/equities, LONG gold/bonds/USD.
                # Triggered by USA500 drawdown > 7% in 10 bars.
                # Exit when USA500 recovers > 3% from crash low.
                # ATR-based stops with anti-stop-hunt random pip offset.
                # BACKTEST NOTE: In backtest mode, primary_symbol is the traded symbol.
                # In live mode, all 6 positions deploy simultaneously.
                "crisis_drawdown_threshold": 0.07,    # 7% drawdown = crisis
                "recovery_threshold": 0.03,           # 3% recovery = easing
                "drawdown_lookback": 10,              # bars for drawdown computation
                "atr_period": 14,
                "atr_stop_multiplier": 2.5,           # wider in crisis (more noise)
                "atr_trail_multiplier": 2.0,          # trail at 2× ATR once profitable
                "min_offset_pips": 5,
                "max_offset_pips": 15,
                "short_allocation": 0.60,             # 60% to short book
                "long_allocation": 0.40,              # 40% to long book
                "primary_symbol": "USA500",           # backtest primary
                "quantity": Decimal("0.01"),          # fixed for backtest
                "use_time_filter": True,
                "trading_start_hour": 8,
                "trading_end_hour": 20,
            },
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
        elif self.strategy == "value_area":
            return self._value_area_strategy_handler(tick)
        elif self.strategy == "crack_spread":
            return self._crack_spread_handler(tick)
        elif self.strategy == "wti_brent_spread":
            return self._wti_brent_spread_handler(tick)
        elif self.strategy in ("seasonal_ma_corn", "seasonal_ma_wheat"):
            return self._seasonal_ma_handler(tick)
        elif self.strategy == "gbpjpy_carry":
            return self._gbpjpy_carry_handler(tick)
        elif self.strategy == "vix_regime":
            return self._vix_regime_handler(tick)
        elif self.strategy == "crash_portfolio":
            return self._crash_portfolio_handler(tick)
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

        # Convert CrudeOilSignal to SyntheticSignal (including SL/TP)
        return SyntheticSignal(
            action=signal.action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=Decimal(str(signal.stop_loss)) if signal.stop_loss else None,
            take_profit=Decimal(str(signal.take_profit)) if signal.take_profit else None,
        )

    def _value_area_strategy_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        Value Area Trading strategy handler.

        Mean-reversion strategy trading from VAH/VAL back to POC.
        Uses TPO profile analysis for value area calculation.
        """
        if self._value_area_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Value Area strategy not initialized"
            )

        # Delegate to the full strategy implementation
        signal = self._value_area_strategy.process_tick(tick)

        # Sync position state
        self.has_position = self._value_area_strategy.has_position
        self.entry_price = self._value_area_strategy.entry_price

        # Convert ValueAreaSignal to SyntheticSignal
        return SyntheticSignal(
            action=signal.action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=Decimal(str(signal.stop_loss)) if signal.stop_loss else None,
            take_profit=Decimal(str(signal.take_profit)) if signal.take_profit else None,
        )

    def _crack_spread_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        Crack spread strategy handler.

        Multi-symbol: accepts ticks from CrudeOIL or GASOLINE.
        Spread = gasoline_barrel_price − crude_price.
        Hedge ratio: 0.42 GASOLINE lots per 1 CrudeOIL lot (dollar-neutral).
        Entry ±1.5σ, exit ±0.3σ, stop 2.5σ.

        Spread leg mapping (both legs must be executed atomically):
            buy_spread  → sell CrudeOIL (primary), buy  GASOLINE (secondary)
            sell_spread → buy  CrudeOIL (primary), sell GASOLINE (secondary)
            close       → close both legs
        """
        if self._crack_spread_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Crack spread strategy not initialized",
            )
        signal = self._crack_spread_strategy.process_tick(tick)
        self.has_position = self._crack_spread_strategy.has_position
        self.entry_price = self._crack_spread_strategy.entry_price

        # Map spread direction to per-leg actions so backtest_service
        # can track both legs independently with correct P&L.
        primary_action: Optional[str]
        secondary_action: Optional[str]
        if signal.action == "buy_spread":
            # Buy GASOLINE (long), Sell CrudeOIL (short)
            primary_action = "sell"       # CrudeOIL leg
            secondary_action = "buy"      # GASOLINE leg
        elif signal.action == "sell_spread":
            # Sell GASOLINE (short), Buy CrudeOIL (long)
            primary_action = "buy"        # CrudeOIL leg
            secondary_action = "sell"     # GASOLINE leg
        elif signal.action == "close":
            primary_action = "close"
            secondary_action = "close"
        else:
            primary_action = signal.action
            secondary_action = None

        params = self._crack_spread_strategy.params
        return SyntheticSignal(
            action=primary_action,
            quantity=signal.crude_quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=Decimal(str(signal.stop_spread)) if signal.stop_spread is not None else None,
            take_profit=Decimal(str(signal.target_spread)) if signal.target_spread is not None else None,
            secondary_symbol=params.gasoline_symbol,
            secondary_action=secondary_action,
            secondary_quantity=signal.gasoline_quantity if signal.gasoline_quantity != Decimal("0") else None,
        )

    def _wti_brent_spread_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        WTI-Brent spread strategy handler.

        Multi-symbol: accepts ticks from CrudeOIL or BRENT_OIL.
        Spread = BRENT_OIL − CrudeOIL (same barrel units, 1:1 ratio).
        Entry ±1.5σ, exit at ±0.3σ band, stop 2.5σ.

        Spread leg mapping (both legs must be executed atomically):
            buy  (long spread)  → buy  BRENT_OIL (primary), sell CrudeOIL (secondary)
            sell (short spread) → sell BRENT_OIL (primary), buy  CrudeOIL (secondary)
            close_long/_short   → close both legs
        """
        if self._wti_brent_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="WTI-Brent spread strategy not initialized",
            )
        signal = self._wti_brent_strategy.process_tick(tick)
        self.has_position = self._wti_brent_strategy.has_position
        self.entry_price = self._wti_brent_strategy.entry_price

        # Map spread direction to per-leg actions so backtest_service
        # can track both legs independently with correct P&L.
        # Primary = BRENT_OIL; secondary = CrudeOIL (opposite direction).
        primary_action = signal.action
        secondary_action: Optional[str] = None
        if signal.action == "buy":
            secondary_action = "sell"    # sell CrudeOIL leg
        elif signal.action == "sell":
            secondary_action = "buy"     # buy CrudeOIL leg
        elif signal.action in ("close_long", "close_short"):
            secondary_action = "close"

        secondary_qty = signal.quantity if signal.quantity != Decimal("0.0") else None

        return SyntheticSignal(
            action=primary_action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=Decimal(str(signal.stop_loss)) if signal.stop_loss is not None else None,
            take_profit=Decimal(str(signal.take_profit)) if signal.take_profit is not None else None,
            secondary_symbol=self._wti_brent_strategy.SYMBOL_WTI,  # "CrudeOIL"
            secondary_action=secondary_action,
            secondary_quantity=secondary_qty,
        )

    def _seasonal_ma_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        Seasonal MA Crossover handler for CORN and WHEAT.

        Single-symbol: only accepts ticks matching the configured symbol.
        Signals only fire during seasonally-aligned windows.
        """
        if self._seasonal_ma_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Seasonal MA strategy not initialized",
            )
        signal = self._seasonal_ma_strategy.process_tick(tick)
        self.has_position = self._seasonal_ma_strategy.has_position
        self.entry_price = self._seasonal_ma_strategy.entry_price
        return SyntheticSignal(
            action=signal.action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=Decimal(str(signal.stop_loss)) if signal.stop_loss is not None else None,
            take_profit=Decimal(str(signal.take_profit)) if signal.take_profit is not None else None,
        )

    def _gbpjpy_carry_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        GBPJPY Carry Trade handler.

        Long-only. Entry on 20-SMA pullback while price > 50-SMA.
        Stop: 2× ATR(14). Exit: close below 50-SMA.
        InsufficientDataError propagates if < atr_period+1 candles.
        """
        if self._gbpjpy_carry_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="GBPJPY carry strategy not initialized",
            )
        signal = self._gbpjpy_carry_strategy.process_tick(tick)
        self.has_position = self._gbpjpy_carry_strategy.has_position
        self.entry_price = self._gbpjpy_carry_strategy.entry_price
        return SyntheticSignal(
            action=signal.action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=Decimal(str(signal.stop_loss)) if signal.stop_loss is not None else None,
            take_profit=Decimal(str(signal.take_profit)) if signal.take_profit is not None else None,
        )

    def _vix_regime_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        VIX Regime (USA500 proxy) handler.

        This strategy never trades directly. It classifies the current macro
        risk regime using USA500 rolling drawdown and emits strategy_multipliers
        for consumption by signal_generator and live risk sizing logic.

        Only USA500 ticks update the buffer; other ticks return the last regime.
        The SyntheticSignal.action is always None; backtest P&L will be flat.

        Regime → action mapping:
            normal / elevated / crisis → None (no direct trade)
        """
        if self._vix_regime_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="VIX regime strategy not initialized",
            )
        signal = self._vix_regime_strategy.process_tick(tick)
        # has_position / entry_price stay False/None — this strategy never trades
        return SyntheticSignal(
            action=signal.action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
        )

    def _crash_portfolio_handler(self, tick: MarketTick) -> SyntheticSignal:
        """
        Crash Portfolio pre-positioning handler.

        Accepts ticks from USA500 (primary for crisis detection) or any of the
        6 portfolio symbols. In backtest mode, signals always reference the
        primary_symbol (default: USA500).

        Action mapping:
            'deploy'    → SHORT primary if in short book, else LONG
            'close_all' → Close the primary symbol position
            None        → Hold or warming up

        Multi-symbol deployment list is included in the SyntheticSignal reason
        for live-mode pipeline consumption. The `secondary_*` fields are not
        populated here — the RiskManagerAgent fan-out handles the 6-leg deployment.

        InsufficientDataError propagates if ATR cannot be computed.
        """
        if self._crash_portfolio_strategy is None:
            return SyntheticSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Crash portfolio strategy not initialized",
            )
        signal = self._crash_portfolio_strategy.process_tick(tick)
        self.has_position = self._crash_portfolio_strategy.has_position
        self.entry_price = self._crash_portfolio_strategy.entry_price

        # Map 'deploy' → 'sell' (shorting USA500 as primary in backtest)
        # or 'buy' if primary is in the long book
        params = self._crash_portfolio_strategy.params
        if signal.action == "deploy":
            if params.primary_symbol in params.short_symbols:
                primary_action = "sell"
            else:
                primary_action = "buy"
        elif signal.action == "close_all":
            primary_action = "close"
        else:
            primary_action = signal.action  # None

        return SyntheticSignal(
            action=primary_action,
            quantity=signal.quantity,
            confidence=signal.confidence,
            reason=signal.reason,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

    def reset(self) -> None:
        """Reset engine state for new backtest."""
        self.price_history.clear()
        self.has_position = False
        self.entry_price = None

        # Reset CrudeOil strategy if initialized
        if self._crude_oil_strategy is not None:
            self._crude_oil_strategy.reset()

        # Reset Value Area strategy if initialized
        if self._value_area_strategy is not None:
            self._value_area_strategy.reset()

        # Reset Phase 2 strategies
        if self._crack_spread_strategy is not None:
            self._crack_spread_strategy.reset()
        if self._wti_brent_strategy is not None:
            self._wti_brent_strategy.reset()
        if self._seasonal_ma_strategy is not None:
            self._seasonal_ma_strategy.reset()
        if self._gbpjpy_carry_strategy is not None:
            self._gbpjpy_carry_strategy.reset()
        if self._vix_regime_strategy is not None:
            self._vix_regime_strategy.reset()
        if self._crash_portfolio_strategy is not None:
            self._crash_portfolio_strategy.reset()

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
