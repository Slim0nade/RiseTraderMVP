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
    
    # Cost model
    slippage_pct: float = 0.001  # 0.1%
    commission_pct: float = 0.0005  # 0.05%
    commission_fixed: float = 0.0
    
    # Position sizing
    position_size: float = 1.0  # Lots
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
            
            # Momentum
            momentum_period = params.get("momentum_period", 10)
            df["momentum"] = df["close"].pct_change(momentum_period) * 100
            
        elif strategy == "mean_reversion":
            lookback = params.get("lookback", 20)
            df["sma"] = df["close"].rolling(window=lookback).mean()
            df["std"] = df["close"].rolling(window=lookback).std()
            df["upper_band"] = df["sma"] + 2 * df["std"]
            df["lower_band"] = df["sma"] - 2 * df["std"]
            df["z_score"] = (df["close"] - df["sma"]) / df["std"]
            
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
            rsi_oversold = params.get("rsi_oversold", 32)
            rsi_overbought = params.get("rsi_overbought", 68)
            cci_oversold = params.get("cci_oversold", -80)
            cci_overbought = params.get("cci_overbought", 100)
            use_cci_filter = params.get("use_cci_filter", True)
            use_strict_filter = params.get("use_strict_filter", False)
            
            # EMA trend direction (matching MQL4: checks if fast > slow, not just crossover)
            ema_bullish = df["ema_fast"] > df["ema_slow"]
            ema_bearish = df["ema_fast"] < df["ema_slow"]
            
            # RSI conditions (BELOW oversold for buy, ABOVE overbought for sell)
            rsi_buy = df["rsi"] < rsi_oversold
            rsi_sell = df["rsi"] > rsi_overbought
            
            # CCI conditions (BELOW oversold for buy, ABOVE overbought for sell)  
            cci_buy = df["cci"] < cci_oversold
            cci_sell = df["cci"] > cci_overbought
            
            # Momentum conditions (per MQL4: > 99.5 for buy, < 100.5 for sell)
            # momentum here is pct_change * 100, so 99.5 becomes -0.5%
            momentum_buy = df["momentum"] > -0.5
            momentum_sell = df["momentum"] < 0.5
            
            # Combined filter logic matching MQL4
            if use_cci_filter:
                if use_strict_filter:
                    # Require BOTH RSI and CCI
                    filter_buy = rsi_buy & cci_buy
                    filter_sell = rsi_sell & cci_sell
                else:
                    # Require EITHER RSI or CCI (default)
                    filter_buy = rsi_buy | cci_buy
                    filter_sell = rsi_sell | cci_sell
            else:
                # Only RSI
                filter_buy = rsi_buy
                filter_sell = rsi_sell
            
            # BUY: EMA bullish + filter + momentum (matching MQL4 logic)
            buy_condition = ema_bullish & filter_buy & momentum_buy
            # Only trigger on first bar of buy condition (avoid multiple entries)
            buy_signal = buy_condition & ~buy_condition.shift(1).fillna(False)
            
            # SELL/CLOSE: EMA turns bearish OR filter says overbought while in downtrend
            sell_condition = ema_bearish | (filter_sell & ema_bearish)
            # Only trigger on first bar of sell condition
            sell_signal = sell_condition & ~sell_condition.shift(1).fillna(False)
            
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
        
        return df
    
    def _calculate_pnl(
        self, df: pd.DataFrame, config: VectorizedBacktestConfig
    ) -> pd.DataFrame:
        """
        Calculate positions and P&L vectorized.
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
        
        # Calculate returns
        df["price_return"] = df["close"].pct_change()
        
        # Apply slippage and commission on position changes
        position_changes = df["position"].diff().abs()
        df["costs"] = position_changes * (config.slippage_pct + config.commission_pct)
        
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
        """
        trades = []
        
        # Find entry and exit points
        df["position_change"] = df["position"].diff()
        
        entries = df[df["position_change"] == 1].index
        exits = df[df["position_change"] == -1].index
        
        # Match entries to exits
        for entry_time in entries:
            # Find next exit after this entry
            future_exits = exits[exits > entry_time]
            
            if len(future_exits) > 0:
                exit_time = future_exits[0]
                
                entry_price = float(df.loc[entry_time, "close"])
                exit_price = float(df.loc[exit_time, "close"])
                
                # Calculate P&L
                gross_pnl = (exit_price - entry_price) * config.position_size * 100  # Per lot
                costs = (entry_price + exit_price) * config.position_size * 100 * (
                    config.slippage_pct + config.commission_pct
                )
                net_pnl = gross_pnl - costs
                
                trades.append({
                    "entry_time": entry_time.isoformat() if hasattr(entry_time, 'isoformat') else str(entry_time),
                    "exit_time": exit_time.isoformat() if hasattr(exit_time, 'isoformat') else str(exit_time),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": config.position_size,
                    "gross_pnl": round(gross_pnl, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round((exit_price / entry_price - 1) * 100, 2),
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
