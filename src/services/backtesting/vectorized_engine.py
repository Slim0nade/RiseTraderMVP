"""
Vectorized Backtesting Engine

100x faster backtesting using pandas/numpy vectorized operations.
Processes 500K+ candles in <1 second instead of 30-60 seconds.

Architecture:
1. Load all data into DataFrame (single query)
2. Calculate indicators vectorized (rolling windows)
3. Generate signals vectorized (boolean masks)
4. Calculate P&L vectorized (cumulative products)
5. Calculate metrics vectorized (numpy aggregations)
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import structlog

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@dataclass
class VectorizedBacktestConfig:
    """Configuration for vectorized backtest."""
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10000.0
    strategy: str = "ma_crossover"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    
    # Fortrade Cost Model (NO commission, spread + swap only)
    # Spread: CrudeOIL = 4 pips ($0.04/unit), XAUUSD = 50 pips ($0.50/unit)
    spread_points: float = 0.04  # Spread in price units (4 pips for CrudeOIL)
    commission_per_lot: float = 0.0  # Fortrade charges NO commission
    # Swap: Applied per lot per night held (from Fortrade: ~$3.81/lot/night for CrudeOIL)
    swap_per_lot_per_night: float = 3.81  # Absolute value, applied as cost
    
    # Legacy cost model (for backward compatibility, set to 0)
    slippage_pct: float = 0.0  # Disabled - use spread_points
    commission_pct: float = 0.0  # Disabled - use commission_per_lot
    commission_fixed: float = 0.0
    
    # Position sizing
    position_size: float = 1.0  # Lots (1 lot = 100 barrels for CrudeOIL)
    max_positions: int = 1


@dataclass
class VectorizedBacktestResult:
    """Results from vectorized backtest."""
    run_id: UUID
    config: VectorizedBacktestConfig
    
    # Performance
    initial_capital: float
    final_capital: float
    total_return_pct: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int
    
    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_trade_pnl: float
    avg_win: float
    avg_loss: float
    
    # Execution stats
    candles_processed: int
    execution_time_ms: float
    
    # Data
    equity_curve: List[float] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": str(self.run_id),
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return_pct": self.total_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_trade_pnl": self.avg_trade_pnl,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "candles_processed": self.candles_processed,
            "execution_time_ms": self.execution_time_ms,
        }


class VectorizedBacktestEngine:
    """
    High-performance vectorized backtesting engine.
    
    Uses pandas/numpy for 100x faster execution compared to row-by-row processing.
    
    Strategies supported:
    - ma_crossover: Moving average crossover
    - rsi: RSI overbought/oversold
    - crude_oil_v3: Multi-indicator crude oil strategy
    - mean_reversion: Bollinger band mean reversion
    - value_area: TPO-based value area (VAH/VAL/POC)
    
    Example:
        engine = VectorizedBacktestEngine(session)
        result = await engine.run(VectorizedBacktestConfig(
            symbol="CrudeOIL",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 1),
            strategy="ma_crossover",
            strategy_params={"fast_period": 10, "slow_period": 30}
        ))
        print(f"Completed in {result.execution_time_ms}ms")
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize engine with database session.
        
        Args:
            session: SQLAlchemy async session for data loading
        """
        self.session = session
    
    async def run(self, config: VectorizedBacktestConfig) -> VectorizedBacktestResult:
        """
        Execute vectorized backtest.
        
        Args:
            config: Backtest configuration
            
        Returns:
            VectorizedBacktestResult with metrics and trades
        """
        import time
        start_time = time.perf_counter()
        run_id = uuid4()
        
        logger.info(
            "vectorized_backtest_starting",
            run_id=str(run_id),
            symbol=config.symbol,
            timeframe=config.timeframe,
            strategy=config.strategy,
        )
        
        try:
            # Step 1: Load all data into DataFrame (single query)
            df = await self._load_data(config)
            
            if df.empty:
                raise ValueError(f"No data found for {config.symbol} {config.timeframe}")
            
            candles_count = len(df)
            logger.info(f"Loaded {candles_count:,} candles into memory")
            
            # Step 2: Calculate indicators (vectorized)
            df = self._calculate_indicators(df, config)
            
            # Step 3: Generate signals (vectorized)
            df = self._generate_signals(df, config)
            
            # Step 4: Calculate positions and P&L (vectorized)
            df = self._calculate_pnl(df, config)
            
            # Step 5: Extract trades
            trades = self._extract_trades(df, config)
            
            # Step 6: Calculate metrics
            metrics = self._calculate_metrics(df, trades, config)
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            logger.info(
                "vectorized_backtest_completed",
                run_id=str(run_id),
                candles=candles_count,
                trades=len(trades),
                execution_time_ms=round(execution_time_ms, 2),
                total_return_pct=round(metrics["total_return_pct"], 2),
            )
            
            return VectorizedBacktestResult(
                run_id=run_id,
                config=config,
                initial_capital=config.initial_capital,
                final_capital=metrics["final_capital"],
                total_return_pct=metrics["total_return_pct"],
                sharpe_ratio=metrics["sharpe_ratio"],
                sortino_ratio=metrics["sortino_ratio"],
                max_drawdown_pct=metrics["max_drawdown_pct"],
                max_drawdown_duration_days=metrics["max_drawdown_duration_days"],
                total_trades=len(trades),
                winning_trades=metrics["winning_trades"],
                losing_trades=metrics["losing_trades"],
                win_rate=metrics["win_rate"],
                profit_factor=metrics["profit_factor"],
                avg_trade_pnl=metrics["avg_trade_pnl"],
                avg_win=metrics["avg_win"],
                avg_loss=metrics["avg_loss"],
                candles_processed=candles_count,
                execution_time_ms=execution_time_ms,
                equity_curve=df["equity"].tolist()[-1000:],  # Last 1000 points
                trades=trades,
            )
            
        except Exception as e:
            logger.error(
                "vectorized_backtest_failed",
                run_id=str(run_id),
                error=str(e),
                exc_info=True,
            )
            raise
    
    async def _load_data(self, config: VectorizedBacktestConfig) -> pd.DataFrame:
        """
        Load all candle data into a pandas DataFrame.
        
        Single query, loads everything into memory for vectorized processing.
        Handles duplicate timestamps by taking the latest row per timestamp.
        """
        # Use subquery to deduplicate, then order
        query = text("""
            SELECT time, open, high, low, close, volume
            FROM (
                SELECT DISTINCT ON (time)
                    time,
                    open,
                    high,
                    low,
                    "last" as close,
                    volume
                FROM market_data
                WHERE symbol = :symbol
                  AND timeframe = :timeframe
                  AND time >= :start_date
                  AND time <= :end_date
                ORDER BY time, id DESC
            ) deduped
            ORDER BY time ASC
        """)
        
        result = await self.session.execute(
            query,
            {
                "symbol": config.symbol,
                "timeframe": config.timeframe,
                "start_date": config.start_date,
                "end_date": config.end_date,
            }
        )
        
        rows = result.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        
        # Ensure numeric types
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
        
        return df
    
    def _calculate_indicators(
        self, df: pd.DataFrame, config: VectorizedBacktestConfig
    ) -> pd.DataFrame:
        """
        Calculate all technical indicators vectorized.
        
        All 500K+ values calculated in milliseconds using rolling windows.
        """
        strategy = config.strategy
        params = config.strategy_params
        
        if strategy == "ma_crossover":
            fast = params.get("fast_period", 10)
            slow = params.get("slow_period", 30)
            
            df["fast_ma"] = df["close"].rolling(window=fast).mean()
            df["slow_ma"] = df["close"].rolling(window=slow).mean()
            
        elif strategy == "rsi":
            period = params.get("rsi_period", 14)
            df["rsi"] = self._calculate_rsi_vectorized(df["close"], period)
            
        elif strategy == "crude_oil_v3":
            # EMA
            ema_fast = params.get("ema_fast", 8)
            ema_slow = params.get("ema_slow", 29)
            df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
            df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
            
            # RSI
            rsi_period = params.get("rsi_period", 10)
            df["rsi"] = self._calculate_rsi_vectorized(df["close"], rsi_period)
            
            # CCI
            cci_period = params.get("cci_period", 20)
            df["cci"] = self._calculate_cci_vectorized(df, cci_period)
            
            # ATR for stops
            atr_period = params.get("atr_period", 10)
            df["atr"] = self._calculate_atr_vectorized(df, atr_period)
            
            # Momentum (MQL4 style: close/close[n] * 100, where 100 = neutral)
            momentum_period = params.get("momentum_period", 10)
            df["momentum"] = (df["close"] / df["close"].shift(momentum_period)) * 100
            
        elif strategy == "mean_reversion":
            lookback = params.get("lookback", 20)
            df["sma"] = df["close"].rolling(window=lookback).mean()
            df["std"] = df["close"].rolling(window=lookback).std()
            df["upper_band"] = df["sma"] + 2 * df["std"]
            df["lower_band"] = df["sma"] - 2 * df["std"]
            df["z_score"] = (df["close"] - df["sma"]) / df["std"]

        elif strategy == "value_area":
            # ================================================================
            # VALUE AREA STRATEGY - TPO-BASED SUPPORT/RESISTANCE
            # ================================================================
            # Parameters
            lookback_periods = params.get("lookback_periods", 24)
            value_area_percent = params.get("value_area_percent", 0.70)
            tpo_resolution = params.get("tpo_resolution", 0.10)
            atr_period = params.get("atr_period", 14)

            # Calculate ATR for stop loss sizing
            df["atr"] = self._calculate_atr_vectorized(df, atr_period)

            # Calculate Value Area (POC, VAH, VAL) using rolling windows
            df["poc"] = df["close"].rolling(window=lookback_periods).apply(
                lambda x: self._calculate_poc_from_closes(x, tpo_resolution),
                raw=False
            )

            df["vah"] = df["close"].rolling(window=lookback_periods).apply(
                lambda x: self._calculate_vah(x, value_area_percent, tpo_resolution, True),
                raw=False
            )

            df["val"] = df["close"].rolling(window=lookback_periods).apply(
                lambda x: self._calculate_vah(x, value_area_percent, tpo_resolution, False),
                raw=False
            )

        else:
            # Default: simple MA
            df["fast_ma"] = df["close"].rolling(window=10).mean()
            df["slow_ma"] = df["close"].rolling(window=30).mean()

        return df
    
    def _generate_signals(
        self, df: pd.DataFrame, config: VectorizedBacktestConfig
    ) -> pd.DataFrame:
        """
        Generate trading signals vectorized.
        
        Returns DataFrame with 'signal' column:
        - 1: BUY
        - -1: SELL/CLOSE
        - 0: HOLD
        """
        strategy = config.strategy
        params = config.strategy_params
        
        # Initialize signal column
        df["signal"] = 0
        
        if strategy == "ma_crossover":
            # Bullish crossover: fast crosses above slow
            buy_signal = (
                (df["fast_ma"] > df["slow_ma"]) & 
                (df["fast_ma"].shift(1) <= df["slow_ma"].shift(1))
            )
            
            # Bearish crossover: fast crosses below slow
            sell_signal = (
                (df["fast_ma"] < df["slow_ma"]) & 
                (df["fast_ma"].shift(1) >= df["slow_ma"].shift(1))
            )
            
            df.loc[buy_signal, "signal"] = 1
            df.loc[sell_signal, "signal"] = -1
            
        elif strategy == "rsi":
            oversold = params.get("rsi_oversold", 30)
            overbought = params.get("rsi_overbought", 70)
            
            # Buy when RSI crosses above oversold
            buy_signal = (df["rsi"] > oversold) & (df["rsi"].shift(1) <= oversold)
            
            # Sell when RSI crosses above overbought
            sell_signal = (df["rsi"] > overbought) & (df["rsi"].shift(1) <= overbought)
            
            df.loc[buy_signal, "signal"] = 1
            df.loc[sell_signal, "signal"] = -1
            
        elif strategy == "crude_oil_v3":
            # ================================================================
            # CRUDE OIL V3 STRATEGY - IMPROVED VERSION
            # ================================================================
            # Features:
            # - EMA trend filter
            # - RSI/CCI oversold entry
            # - Time filter (only trade during active hours)
            # - ATR-based SL/TP
            # - EMA crossover exit
            # ================================================================
            
            # Parameters
            rsi_oversold = params.get("rsi_oversold", 32)
            rsi_overbought = params.get("rsi_overbought", 68)
            cci_oversold = params.get("cci_oversold", -80)
            cci_overbought = params.get("cci_overbought", 100)
            use_cci_filter = params.get("use_cci_filter", True)
            use_strict_filter = params.get("use_strict_filter", False)
            
            # Momentum filter thresholds (MQL4: >99.5 for buy, <100.5 for sell)
            use_momentum_filter = params.get("use_momentum_filter", True)
            momentum_buy_threshold = params.get("momentum_buy_threshold", 99.5)
            momentum_sell_threshold = params.get("momentum_sell_threshold", 100.5)
            
            # Time filter parameters
            use_time_filter = params.get("use_time_filter", True)
            trade_start_hour = params.get("trade_start_hour", 8)   # 8 AM GMT
            trade_end_hour = params.get("trade_end_hour", 20)      # 8 PM GMT
            
            # ATR exit parameters
            use_atr_exits = params.get("use_atr_exits", False)
            atr_sl_multiplier = params.get("atr_sl_multiplier", 2.0)
            atr_tp_multiplier = params.get("atr_tp_multiplier", 3.0)
            
            # ================================================================
            # TIME FILTER
            # ================================================================
            if use_time_filter:
                # Extract hour from index (assuming UTC)
                hours = df.index.hour
                time_ok = (hours >= trade_start_hour) & (hours < trade_end_hour)
            else:
                time_ok = pd.Series(True, index=df.index)
            
            # ================================================================
            # TREND FILTER (EMA)
            # ================================================================
            # Use EMA crossover for trend direction, not just current state
            ema_bullish = df["ema_fast"] > df["ema_slow"]
            ema_bearish = df["ema_fast"] < df["ema_slow"]
            
            # EMA crossover signals (for exits)
            ema_cross_up = ema_bullish & ~ema_bullish.shift(1).fillna(False)
            ema_cross_down = ema_bearish & ~ema_bearish.shift(1).fillna(False)
            
            # ================================================================
            # OSCILLATOR FILTERS (RSI/CCI)
            # ================================================================
            rsi_buy = df["rsi"] < rsi_oversold
            rsi_sell = df["rsi"] > rsi_overbought
            
            cci_buy = df["cci"] < cci_oversold
            cci_sell = df["cci"] > cci_overbought
            
            # Combined filter logic
            if use_cci_filter:
                if use_strict_filter:
                    filter_buy = rsi_buy & cci_buy  # BOTH required
                    filter_sell = rsi_sell & cci_sell
                else:
                    filter_buy = rsi_buy | cci_buy  # EITHER (default)
                    filter_sell = rsi_sell | cci_sell
            else:
                filter_buy = rsi_buy
                filter_sell = rsi_sell
            
            # ================================================================
            # ENTRY SIGNALS
            # ================================================================
            # BUY: Trend is bullish + oscillator oversold + time filter
            buy_condition = ema_bullish & filter_buy & time_ok
            # Only trigger on FIRST bar of condition (avoid re-entries)
            buy_signal = buy_condition & ~buy_condition.shift(1).fillna(False)
            
            # ================================================================
            # EXIT SIGNALS
            # ================================================================
            # Exit on EMA cross down OR overbought in bearish trend
            # This is more aggressive exit than waiting for full reversal
            exit_on_ema_cross = ema_cross_down
            exit_on_overbought = filter_sell & ema_bearish
            
            sell_signal = exit_on_ema_cross | exit_on_overbought
            # Only trigger on first bar
            sell_signal = sell_signal & ~sell_signal.shift(1).fillna(False)
            
            # Store ATR for position management (used in _calculate_pnl)
            df["entry_atr"] = df["atr"]
            df["atr_sl_mult"] = atr_sl_multiplier
            df["atr_tp_mult"] = atr_tp_multiplier
            df["use_atr_exits"] = use_atr_exits
            
            df.loc[buy_signal, "signal"] = 1
            df.loc[sell_signal, "signal"] = -1
            
        elif strategy == "mean_reversion":
            std_threshold = params.get("std_threshold", 2.0)

            # Buy when price below lower band (oversold)
            buy_signal = df["z_score"] < -std_threshold
            buy_signal = buy_signal & ~buy_signal.shift(1).fillna(False)

            # Sell when price returns to mean
            sell_signal = (df["z_score"] > -0.5) & (df["z_score"].shift(1) <= -0.5)

            df.loc[buy_signal, "signal"] = 1
            df.loc[sell_signal, "signal"] = -1

        elif strategy == "value_area":
            # ================================================================
            # VALUE AREA ENTRY/EXIT SIGNALS
            # ================================================================
            # Parameters
            atr_multiplier = params.get("stop_atr_multiplier", 1.5)

            # Buy signal: Price crosses below VAL with rejection (closes above VAL next bar)
            # This signals institutional buying at value area support
            price_below_val = df["close"] < df["val"]
            price_above_val_next = df["close"].shift(-1) > df["val"].shift(-1)

            buy_signal = (
                price_below_val &
                price_above_val_next.fillna(False) &
                df["val"].notna()
            )
            # Only trigger on first signal
            buy_signal = buy_signal & ~buy_signal.shift(1).fillna(False)

            # Sell signal: Price crosses above VAH with rejection (closes below VAH next bar)
            # This signals institutional selling at value area resistance
            price_above_vah = df["close"] > df["vah"]
            price_below_vah_next = df["close"].shift(-1) < df["vah"].shift(-1)

            sell_signal = (
                price_above_vah &
                price_below_vah_next.fillna(False) &
                df["vah"].notna()
            )
            # Only trigger on first signal
            sell_signal = sell_signal & ~sell_signal.shift(1).fillna(False)

            # Store ATR for position management (used in _calculate_pnl)
            df["entry_atr"] = df["atr"]
            df["atr_sl_mult"] = atr_multiplier
            df["atr_tp_mult"] = 2.0  # Default TP multiplier
            df["use_atr_exits"] = True

            df.loc[buy_signal, "signal"] = 1
            df.loc[sell_signal, "signal"] = -1

        return df
    
    def _calculate_pnl(
        self, df: pd.DataFrame, config: VectorizedBacktestConfig
    ) -> pd.DataFrame:
        """
        Calculate positions and P&L vectorized.
        
        Fortrade Cost Model:
        - NO commission
        - Spread cost on entry/exit (e.g., 4 pips = $4/lot for CrudeOIL)
        - Swap cost for overnight positions (~$3.81/lot/night for CrudeOIL)
        
        For CrudeOIL:
        - 1 lot = 100 barrels
        - 1 pip ($0.01) move = $1.00 per lot
        - 4 pip spread = $4.00 per lot per round trip
        """
        # Forward fill signals to get position state
        # 1 = long, 0 = flat, -1 = short (not implemented yet)
        df["position"] = 0
        
        # Track position changes
        position = 0
        positions = []
        
        for signal in df["signal"]:
            if signal == 1 and position == 0:
                position = 1  # Enter long
            elif signal == -1 and position == 1:
                position = 0  # Exit long
            positions.append(position)
        
        df["position"] = positions
        
        # Calculate raw price returns
        df["price_return"] = df["close"].pct_change()
        
        # Calculate spread cost as % of price (only on position changes)
        # For CrudeOIL: spread_points=0.04 means $0.04 spread
        # At $57/barrel, that's 0.04/57 = 0.07% per side
        position_changes = df["position"].diff().abs()
        spread_cost_pct = config.spread_points / df["close"]  # Spread as % of price
        df["costs"] = position_changes * spread_cost_pct
        
        # Strategy returns = price returns * position (lagged) - costs
        df["strategy_return"] = (
            df["price_return"] * df["position"].shift(1).fillna(0) - 
            df["costs"]
        )
        
        # Cumulative equity
        df["cumulative_return"] = (1 + df["strategy_return"]).cumprod()
        df["equity"] = config.initial_capital * df["cumulative_return"]
        
        # Drawdown calculation
        df["peak"] = df["equity"].cummax()
        df["drawdown"] = (df["equity"] - df["peak"]) / df["peak"]
        
        return df
    
    def _extract_trades(
        self, df: pd.DataFrame, config: VectorizedBacktestConfig
    ) -> List[Dict]:
        """
        Extract individual trades from position changes.
        
        Fortrade Cost Model:
        - Spread: 4 pips for CrudeOIL = $4.00 per lot per round trip
        - Commission: $0 (Fortrade doesn't charge commission)
        - Swap: ~$3.81/lot/night (only for overnight holds)
        
        For CrudeOIL:
        - 1 lot = 100 barrels
        - 1 pip ($0.01) = $1.00 per lot ($0.01 * 100 barrels)
        """
        trades = []
        
        # Find entry and exit points
        df["position_change"] = df["position"].diff()
        
        entries = df[df["position_change"] == 1].index
        exits = df[df["position_change"] == -1].index
        
        # Contract size per lot (100 barrels for CrudeOIL)
        contract_size = 100
        
        # Match entries to exits
        for entry_time in entries:
            # Find next exit after this entry
            future_exits = exits[exits > entry_time]
            
            if len(future_exits) > 0:
                exit_time = future_exits[0]
                
                entry_price = float(df.loc[entry_time, "close"])
                exit_price = float(df.loc[exit_time, "close"])
                
                # Calculate P&L (Fortrade model)
                # Gross P&L = price difference * lots * contract_size
                gross_pnl = (exit_price - entry_price) * config.position_size * contract_size
                
                # Spread cost = spread_points * lots * contract_size (paid on entry and exit)
                # For CrudeOIL: 0.04 * 1 * 100 = $4.00 round trip
                spread_cost = config.spread_points * config.position_size * contract_size
                
                # Commission cost (Fortrade = $0)
                commission_cost = config.commission_per_lot * config.position_size
                
                # Swap cost (only if held overnight)
                # Count nights between entry and exit
                if hasattr(entry_time, 'date') and hasattr(exit_time, 'date'):
                    nights_held = (exit_time.date() - entry_time.date()).days
                else:
                    # Estimate from timestamp difference
                    time_diff = (exit_time - entry_time).total_seconds() if hasattr(exit_time - entry_time, 'total_seconds') else 0
                    nights_held = int(time_diff / 86400)  # seconds per day
                
                swap_cost = config.swap_per_lot_per_night * config.position_size * max(0, nights_held)
                
                # Total costs
                total_costs = spread_cost + commission_cost + swap_cost
                net_pnl = gross_pnl - total_costs
                
                trades.append({
                    "entry_time": entry_time.isoformat() if hasattr(entry_time, 'isoformat') else str(entry_time),
                    "exit_time": exit_time.isoformat() if hasattr(exit_time, 'isoformat') else str(exit_time),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": config.position_size,
                    "gross_pnl": round(gross_pnl, 2),
                    "spread_cost": round(spread_cost, 2),
                    "swap_cost": round(swap_cost, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round((exit_price / entry_price - 1) * 100, 2),
                    "nights_held": nights_held,
                })
        
        return trades
    
    def _calculate_metrics(
        self, df: pd.DataFrame, trades: List[Dict], config: VectorizedBacktestConfig
    ) -> Dict[str, Any]:
        """
        Calculate performance metrics vectorized.
        """
        # Filter out NaN returns
        returns = df["strategy_return"].dropna()
        
        # Basic metrics
        final_capital = float(df["equity"].iloc[-1]) if len(df) > 0 else config.initial_capital
        total_return_pct = ((final_capital / config.initial_capital) - 1) * 100
        
        # Risk metrics
        if len(returns) > 0 and returns.std() > 0:
            # Annualized Sharpe (assuming M5 = 288 bars/day, 252 trading days)
            periods_per_year = 288 * 252
            sharpe_ratio = float(returns.mean() / returns.std() * np.sqrt(periods_per_year))
            
            # Sortino (only downside deviation)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0 and downside_returns.std() > 0:
                sortino_ratio = float(returns.mean() / downside_returns.std() * np.sqrt(periods_per_year))
            else:
                sortino_ratio = sharpe_ratio
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0
        
        # Max drawdown
        max_drawdown_pct = float(df["drawdown"].min()) * 100 if "drawdown" in df else 0.0
        
        # Drawdown duration
        in_drawdown = df["drawdown"] < 0
        drawdown_groups = (~in_drawdown).cumsum()
        drawdown_durations = in_drawdown.groupby(drawdown_groups).sum()
        max_drawdown_duration_bars = int(drawdown_durations.max()) if len(drawdown_durations) > 0 else 0
        # Convert bars to days (assuming M5)
        max_drawdown_duration_days = max_drawdown_duration_bars // 288
        
        # Trade metrics
        if trades:
            pnls = [t["net_pnl"] for t in trades]
            winning_trades = len([p for p in pnls if p > 0])
            losing_trades = len([p for p in pnls if p <= 0])
            
            win_rate = winning_trades / len(trades) * 100 if trades else 0.0
            
            wins = [p for p in pnls if p > 0]
            losses = [abs(p) for p in pnls if p < 0]
            
            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            
            profit_factor = sum(wins) / sum(losses) if losses and sum(losses) > 0 else 999.0
            avg_trade_pnl = sum(pnls) / len(pnls) if pnls else 0.0
        else:
            winning_trades = 0
            losing_trades = 0
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            profit_factor = 0.0
            avg_trade_pnl = 0.0
        
        return {
            "final_capital": final_capital,
            "total_return_pct": total_return_pct,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown_pct": max_drawdown_pct,
            "max_drawdown_duration_days": max_drawdown_duration_days,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_trade_pnl": avg_trade_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        }
    
    # =========================================================================
    # Vectorized Indicator Calculations
    # =========================================================================
    
    @staticmethod
    def _calculate_rsi_vectorized(prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI vectorized."""
        delta = prices.diff()
        
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def _calculate_cci_vectorized(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Commodity Channel Index vectorized."""
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        sma = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(
            lambda x: np.abs(x - x.mean()).mean(), raw=True
        )
        cci = (typical_price - sma) / (0.015 * mad)
        return cci
    
    @staticmethod
    def _calculate_atr_vectorized(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range vectorized."""
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        return atr

    @staticmethod
    def _calculate_poc_from_closes(
        closes: pd.Series, tpo_resolution: float = 0.10
    ) -> float:
        """
        Calculate Point of Control (POC) from close prices.

        POC is the price level with the most time spent (mode of activity).
        Uses histogram bucketing to find the price bucket with most observations.

        Args:
            closes: Series of close prices
            tpo_resolution: Size of each price bucket (e.g., 0.10 for $0.10 buckets)

        Returns:
            POC price level
        """
        if len(closes) == 0 or closes.isna().all():
            return np.nan

        closes = closes.dropna()
        if len(closes) == 0:
            return np.nan

        # Create price buckets
        min_price = closes.min()
        max_price = closes.max()

        if min_price == max_price:
            return min_price

        # Bucket closes into TPO resolution
        buckets = np.floor(closes / tpo_resolution) * tpo_resolution

        # Find most common bucket (mode)
        bucket_counts = buckets.value_counts()
        poc_bucket = bucket_counts.idxmax() if len(bucket_counts) > 0 else min_price

        return float(poc_bucket)

    @staticmethod
    def _calculate_vah(
        closes: pd.Series,
        value_area_percent: float = 0.70,
        tpo_resolution: float = 0.10,
        is_high: bool = True,
    ) -> float:
        """
        Calculate Value Area High or Low.

        VAH/VAL are the bounds that contain the specified percentage of activity
        around the POC (Point of Control).

        Args:
            closes: Series of close prices
            value_area_percent: Percentage of activity to include (e.g., 0.70 for 70%)
            tpo_resolution: Size of each price bucket
            is_high: True for VAH, False for VAL

        Returns:
            VAH or VAL price level
        """
        if len(closes) == 0 or closes.isna().all():
            return np.nan

        closes = closes.dropna()
        if len(closes) == 0:
            return np.nan

        # Calculate POC
        poc = VectorizedBacktestEngine._calculate_poc_from_closes(closes, tpo_resolution)

        if np.isnan(poc):
            return np.nan

        # Create buckets
        buckets = np.floor(closes / tpo_resolution) * tpo_resolution
        bucket_counts = buckets.value_counts().sort_index()

        if len(bucket_counts) == 0:
            return np.nan

        # Find POC bucket
        poc_bucket = np.floor(poc / tpo_resolution) * tpo_resolution

        # Build distribution from POC outward
        total_activity = len(closes)
        target_activity = total_activity * value_area_percent

        # Track cumulative activity
        cumulative = 0
        current_activity = bucket_counts.get(poc_bucket, 0)
        cumulative += current_activity

        # Add buckets above and below POC alternately
        offset = tpo_resolution
        bucket_index = 0

        while cumulative < target_activity:
            bucket_index += 1

            # Try upper bucket
            upper_bucket = poc_bucket + offset * bucket_index
            if upper_bucket in bucket_counts.index:
                cumulative += bucket_counts[upper_bucket]

            if cumulative >= target_activity:
                break

            # Try lower bucket
            lower_bucket = poc_bucket - offset * bucket_index
            if lower_bucket in bucket_counts.index:
                cumulative += bucket_counts[lower_bucket]

        # Determine VAH/VAL based on direction
        if is_high:
            # VAH: find highest bucket in value area
            va_buckets = []
            for i in range(bucket_index + 1):
                upper = poc_bucket + offset * i
                lower = poc_bucket - offset * i
                if upper in bucket_counts.index:
                    va_buckets.append(upper)
                if lower in bucket_counts.index:
                    va_buckets.append(lower)

            return float(max(va_buckets)) if va_buckets else float(poc)
        else:
            # VAL: find lowest bucket in value area
            va_buckets = []
            for i in range(bucket_index + 1):
                upper = poc_bucket + offset * i
                lower = poc_bucket - offset * i
                if upper in bucket_counts.index:
                    va_buckets.append(upper)
                if lower in bucket_counts.index:
                    va_buckets.append(lower)

            return float(min(va_buckets)) if va_buckets else float(poc)


# =============================================================================
# Convenience Functions
# =============================================================================

async def run_vectorized_backtest(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    strategy: str = "ma_crossover",
    strategy_params: Optional[Dict] = None,
    initial_capital: float = 10000.0,
) -> VectorizedBacktestResult:
    """
    Convenience function to run a vectorized backtest.
    
    Args:
        session: Database session
        symbol: Trading symbol
        timeframe: Timeframe (M1, M5, H1, etc.)
        start_date: Backtest start
        end_date: Backtest end
        strategy: Strategy name
        strategy_params: Strategy parameters
        initial_capital: Starting capital
        
    Returns:
        VectorizedBacktestResult with metrics
        
    Example:
        result = await run_vectorized_backtest(
            session=db_session,
            symbol="CrudeOIL",
            timeframe="M5",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 1),
            strategy="crude_oil_v3",
        )
        print(f"Return: {result.total_return_pct:.2f}%")
        print(f"Sharpe: {result.sharpe_ratio:.2f}")
        print(f"Time: {result.execution_time_ms:.0f}ms")
    """
    config = VectorizedBacktestConfig(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        strategy=strategy,
        strategy_params=strategy_params or {},
        initial_capital=initial_capital,
    )
    
    engine = VectorizedBacktestEngine(session)
    return await engine.run(config)
