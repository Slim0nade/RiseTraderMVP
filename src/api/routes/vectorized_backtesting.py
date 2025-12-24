"""
Vectorized Backtesting API Routes

High-performance backtesting endpoints using vectorized processing.
100x faster than row-by-row processing.
"""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.services.backtesting.vectorized_engine import (
    VectorizedBacktestConfig,
    VectorizedBacktestEngine,
    VectorizedBacktestResult,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/backtesting/vectorized", tags=["backtesting-vectorized"])


# =============================================================================
# Request/Response Models
# =============================================================================

class VectorizedBacktestRequest(BaseModel):
    """Request to run a vectorized backtest."""
    
    symbol: str = Field(..., description="Trading symbol (e.g., 'CrudeOIL')")
    timeframe: str = Field(..., description="Candle timeframe (M1, M5, M15, H1, H4, D1)")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD or ISO format)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD or ISO format)")
    strategy: str = Field(
        default="ma_crossover",
        description="Strategy name: ma_crossover, rsi, crude_oil_v3, mean_reversion"
    )
    strategy_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Strategy-specific parameters"
    )
    initial_capital: float = Field(default=10000.0, description="Starting capital")
    slippage_pct: float = Field(default=0.001, description="Slippage percentage (0.001 = 0.1%)")
    commission_pct: float = Field(default=0.0005, description="Commission percentage")
    position_size: float = Field(default=1.0, description="Position size in lots")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "timeframe": "M5",
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "strategy": "crude_oil_v3",
                "strategy_params": {
                    "ema_fast": 8,
                    "ema_slow": 29,
                    "rsi_period": 10
                },
                "initial_capital": 10000.0
            }
        }


class VectorizedBacktestResponse(BaseModel):
    """Response from vectorized backtest."""
    
    success: bool
    run_id: str
    execution_time_ms: float
    candles_processed: int
    
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
    
    # Optional detailed data
    trades: Optional[list] = None
    equity_curve_sample: Optional[list] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "execution_time_ms": 245.5,
                "candles_processed": 125000,
                "initial_capital": 10000.0,
                "final_capital": 11234.56,
                "total_return_pct": 12.35,
                "sharpe_ratio": 1.45,
                "sortino_ratio": 1.89,
                "max_drawdown_pct": -8.5,
                "max_drawdown_duration_days": 12,
                "total_trades": 47,
                "winning_trades": 28,
                "losing_trades": 19,
                "win_rate": 59.57,
                "profit_factor": 1.85,
                "avg_trade_pnl": 26.27
            }
        }


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/run",
    response_model=VectorizedBacktestResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a vectorized backtest (100x faster)",
    description="""
    Execute a high-performance vectorized backtest.
    
    **Key Features:**
    - Processes 500K+ candles in <1 second
    - All indicators calculated vectorized
    - Returns complete results synchronously
    
    **Supported Strategies:**
    - `ma_crossover`: Moving average crossover (fast_period, slow_period)
    - `rsi`: RSI overbought/oversold (rsi_period, rsi_oversold, rsi_overbought)
    - `crude_oil_v3`: Multi-indicator crude oil (ema_fast, ema_slow, rsi_period, cci_period)
    - `mean_reversion`: Bollinger band reversion (lookback, std_threshold)
    
    **Performance:**
    - 10 days of M5 data (~3K candles): ~50ms
    - 1 month of M5 data (~8.6K candles): ~100ms
    - 1 year of M5 data (~100K candles): ~500ms
    - 5 years of M5 data (~500K candles): ~1-2s
    """,
    responses={
        200: {"description": "Backtest completed successfully"},
        400: {"description": "Invalid request parameters"},
        404: {"description": "No data found for symbol/timeframe"},
        500: {"description": "Internal server error"},
    },
)
async def run_vectorized_backtest(
    request: VectorizedBacktestRequest,
    db: AsyncSession = Depends(get_db),
) -> VectorizedBacktestResponse:
    """
    Run a vectorized backtest and return results immediately.
    
    This endpoint is synchronous - it completes the entire backtest
    before returning, which is possible because vectorized processing
    is extremely fast (500K candles in <2 seconds).
    """
    try:
        # Parse dates
        try:
            if "T" in request.start_date:
                start_date = datetime.fromisoformat(request.start_date.replace("Z", "+00:00"))
            else:
                start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
                
            if "T" in request.end_date:
                end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))
            else:
                end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date format: {e}"
            )
        
        # Build config
        config = VectorizedBacktestConfig(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=request.strategy,
            strategy_params=request.strategy_params or {},
            initial_capital=request.initial_capital,
            slippage_pct=request.slippage_pct,
            commission_pct=request.commission_pct,
            position_size=request.position_size,
        )
        
        # Run backtest
        engine = VectorizedBacktestEngine(db)
        result = await engine.run(config)
        
        logger.info(
            "vectorized_backtest_api_success",
            run_id=str(result.run_id),
            symbol=request.symbol,
            candles=result.candles_processed,
            execution_time_ms=result.execution_time_ms,
            total_return_pct=result.total_return_pct,
        )
        
        return VectorizedBacktestResponse(
            success=True,
            run_id=str(result.run_id),
            execution_time_ms=round(result.execution_time_ms, 2),
            candles_processed=result.candles_processed,
            initial_capital=result.initial_capital,
            final_capital=round(result.final_capital, 2),
            total_return_pct=round(result.total_return_pct, 2),
            sharpe_ratio=round(result.sharpe_ratio, 2),
            sortino_ratio=round(result.sortino_ratio, 2),
            max_drawdown_pct=round(result.max_drawdown_pct, 2),
            max_drawdown_duration_days=result.max_drawdown_duration_days,
            total_trades=result.total_trades,
            winning_trades=result.winning_trades,
            losing_trades=result.losing_trades,
            win_rate=round(result.win_rate, 2),
            profit_factor=round(result.profit_factor, 2),
            avg_trade_pnl=round(result.avg_trade_pnl, 2),
            trades=result.trades[:50] if result.trades else None,  # First 50 trades
            equity_curve_sample=result.equity_curve[-100:] if result.equity_curve else None,  # Last 100 points
        )
        
    except ValueError as e:
        logger.warning(
            "vectorized_backtest_no_data",
            symbol=request.symbol,
            timeframe=request.timeframe,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
        
    except Exception as e:
        logger.error(
            "vectorized_backtest_api_error",
            symbol=request.symbol,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {str(e)}"
        )


@router.get(
    "/strategies",
    summary="List available strategies for vectorized backtesting",
    description="Get list of strategies with their parameters and descriptions.",
)
async def list_vectorized_strategies() -> Dict[str, Any]:
    """List available vectorized strategies."""
    return {
        "strategies": [
            {
                "name": "ma_crossover",
                "description": "Moving average crossover strategy. Buys when fast MA crosses above slow MA.",
                "parameters": {
                    "fast_period": {"type": "int", "default": 10, "description": "Fast MA period"},
                    "slow_period": {"type": "int", "default": 30, "description": "Slow MA period"},
                }
            },
            {
                "name": "rsi",
                "description": "RSI overbought/oversold strategy. Buys at oversold, sells at overbought.",
                "parameters": {
                    "rsi_period": {"type": "int", "default": 14, "description": "RSI calculation period"},
                    "rsi_oversold": {"type": "int", "default": 30, "description": "Oversold threshold"},
                    "rsi_overbought": {"type": "int", "default": 70, "description": "Overbought threshold"},
                }
            },
            {
                "name": "crude_oil_v3",
                "description": "Multi-indicator crude oil strategy with EMA, RSI, CCI, and momentum.",
                "parameters": {
                    "ema_fast": {"type": "int", "default": 8, "description": "Fast EMA period"},
                    "ema_slow": {"type": "int", "default": 29, "description": "Slow EMA period"},
                    "rsi_period": {"type": "int", "default": 10, "description": "RSI period"},
                    "rsi_overbought": {"type": "int", "default": 68, "description": "RSI overbought"},
                    "rsi_oversold": {"type": "int", "default": 32, "description": "RSI oversold"},
                    "cci_period": {"type": "int", "default": 20, "description": "CCI period"},
                    "cci_overbought": {"type": "int", "default": 100, "description": "CCI overbought"},
                    "cci_oversold": {"type": "int", "default": -80, "description": "CCI oversold"},
                    "momentum_period": {"type": "int", "default": 10, "description": "Momentum period"},
                }
            },
            {
                "name": "mean_reversion",
                "description": "Bollinger band mean reversion. Buys at lower band, sells at mean.",
                "parameters": {
                    "lookback": {"type": "int", "default": 20, "description": "Lookback period"},
                    "std_threshold": {"type": "float", "default": 2.0, "description": "Std dev threshold"},
                }
            },
        ]
    }


@router.post(
    "/debug",
    summary="Debug backtest signal generation",
    description="Returns detailed diagnostic info about data loading and signal generation.",
)
async def debug_vectorized_backtest(
    request: VectorizedBacktestRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Debug endpoint to diagnose why backtests might return 0 trades.
    
    Returns:
    - Data statistics (row count, date range, price range)
    - Indicator samples (first/last values)
    - Signal counts (how many buy/sell signals generated)
    - Sample signals with timestamps
    """
    from datetime import datetime
    import pandas as pd
    from sqlalchemy import text
    
    try:
        # Parse dates
        if "T" in request.start_date:
            start_date = datetime.fromisoformat(request.start_date.replace("Z", "+00:00"))
        else:
            start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
            
        if "T" in request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))
        else:
            end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        # Load data
        query = text("""
            SELECT 
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
            ORDER BY time ASC
        """)
        
        result = await db.execute(
            query,
            {
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        
        rows = result.fetchall()
        
        if not rows:
            return {
                "error": "No data found",
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "suggestion": "Check if the timeframe format matches DB (e.g., 'M5' vs '5m')"
            }
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
        
        # Data stats
        data_stats = {
            "row_count": len(df),
            "date_range": {
                "first": str(df.index[0]),
                "last": str(df.index[-1]),
            },
            "price_range": {
                "min": float(df["close"].min()),
                "max": float(df["close"].max()),
                "mean": float(df["close"].mean()),
            },
        }
        
        # Calculate indicators for crude_oil_v3
        params = request.strategy_params or {}
        ema_fast = params.get("ema_fast", 8)
        ema_slow = params.get("ema_slow", 29)
        rsi_period = params.get("rsi_period", 10)
        cci_period = params.get("cci_period", 20)
        momentum_period = params.get("momentum_period", 10)
        rsi_oversold = params.get("rsi_oversold", 32)
        rsi_overbought = params.get("rsi_overbought", 68)
        cci_oversold = params.get("cci_oversold", -80)
        cci_overbought = params.get("cci_overbought", 100)
        
        # Calculate indicators
        df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
        
        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=rsi_period).mean()
        avg_loss = loss.rolling(window=rsi_period).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # CCI
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        sma = typical_price.rolling(window=cci_period).mean()
        mad = typical_price.rolling(window=cci_period).apply(
            lambda x: abs(x - x.mean()).mean(), raw=True
        )
        df["cci"] = (typical_price - sma) / (0.015 * mad)
        
        # Momentum
        df["momentum"] = df["close"].pct_change(momentum_period) * 100
        
        # Check conditions
        df["ema_bullish"] = df["ema_fast"] > df["ema_slow"]
        df["ema_cross_up"] = df["ema_bullish"] & ~df["ema_bullish"].shift(1).fillna(False)
        df["ema_cross_down"] = ~df["ema_bullish"] & df["ema_bullish"].shift(1).fillna(True)
        df["rsi_oversold"] = df["rsi"] < rsi_oversold
        df["rsi_overbought"] = df["rsi"] > rsi_overbought
        df["cci_oversold"] = df["cci"] < cci_oversold
        df["cci_overbought"] = df["cci"] > cci_overbought
        df["momentum_buy"] = df["momentum"] > -0.5
        df["momentum_sell"] = df["momentum"] < 0.5
        
        # Combined buy signal (matching crude_oil_v3 logic)
        df["filter_buy"] = df["rsi_oversold"] | df["cci_oversold"]  # Either RSI or CCI
        df["buy_signal"] = df["ema_cross_up"] & df["filter_buy"] & df["momentum_buy"]
        
        # Sell signal
        df["filter_sell"] = df["rsi_overbought"] | df["cci_overbought"]
        df["sell_signal"] = df["ema_cross_down"] | (df["filter_sell"] & ~df["ema_bullish"])
        
        # Count signals
        signal_stats = {
            "ema_cross_up_count": int(df["ema_cross_up"].sum()),
            "ema_cross_down_count": int(df["ema_cross_down"].sum()),
            "rsi_oversold_count": int(df["rsi_oversold"].sum()),
            "rsi_overbought_count": int(df["rsi_overbought"].sum()),
            "cci_oversold_count": int(df["cci_oversold"].sum()),
            "cci_overbought_count": int(df["cci_overbought"].sum()),
            "filter_buy_count": int(df["filter_buy"].sum()),
            "momentum_buy_count": int(df["momentum_buy"].sum()),
            "buy_signal_count": int(df["buy_signal"].sum()),
            "sell_signal_count": int(df["sell_signal"].sum()),
        }
        
        # Sample indicator values
        indicator_samples = {
            "first_100_rows": {
                "rsi_min": float(df["rsi"].head(100).min()) if not df["rsi"].head(100).isna().all() else None,
                "rsi_max": float(df["rsi"].head(100).max()) if not df["rsi"].head(100).isna().all() else None,
                "cci_min": float(df["cci"].head(100).min()) if not df["cci"].head(100).isna().all() else None,
                "cci_max": float(df["cci"].head(100).max()) if not df["cci"].head(100).isna().all() else None,
            },
            "overall": {
                "rsi_min": float(df["rsi"].min()) if not df["rsi"].isna().all() else None,
                "rsi_max": float(df["rsi"].max()) if not df["rsi"].isna().all() else None,
                "rsi_mean": float(df["rsi"].mean()) if not df["rsi"].isna().all() else None,
                "cci_min": float(df["cci"].min()) if not df["cci"].isna().all() else None,
                "cci_max": float(df["cci"].max()) if not df["cci"].isna().all() else None,
                "cci_mean": float(df["cci"].mean()) if not df["cci"].isna().all() else None,
            }
        }
        
        # Sample buy signals (if any)
        buy_signals = df[df["buy_signal"]].head(10)
        sample_buys = []
        for idx, row in buy_signals.iterrows():
            sample_buys.append({
                "time": str(idx),
                "close": float(row["close"]),
                "rsi": float(row["rsi"]) if not pd.isna(row["rsi"]) else None,
                "cci": float(row["cci"]) if not pd.isna(row["cci"]) else None,
                "momentum": float(row["momentum"]) if not pd.isna(row["momentum"]) else None,
            })
        
        # Diagnosis
        diagnosis = []
        if signal_stats["ema_cross_up_count"] == 0:
            diagnosis.append("NO EMA crossovers detected - check if EMA periods are appropriate for this data")
        if signal_stats["rsi_oversold_count"] == 0 and signal_stats["cci_oversold_count"] == 0:
            diagnosis.append(f"NO oversold conditions - RSI never < {rsi_oversold}, CCI never < {cci_oversold}")
        if signal_stats["filter_buy_count"] > 0 and signal_stats["ema_cross_up_count"] > 0 and signal_stats["buy_signal_count"] == 0:
            diagnosis.append("Filters pass but no alignment with EMA crossover - signals happen at different times")
        if indicator_samples["overall"]["rsi_min"] and indicator_samples["overall"]["rsi_min"] > rsi_oversold:
            diagnosis.append(f"RSI never goes below {rsi_oversold} (min: {indicator_samples['overall']['rsi_min']:.1f})")
        if indicator_samples["overall"]["cci_min"] and indicator_samples["overall"]["cci_min"] > cci_oversold:
            diagnosis.append(f"CCI never goes below {cci_oversold} (min: {indicator_samples['overall']['cci_min']:.1f})")
        
        if not diagnosis:
            if signal_stats["buy_signal_count"] > 0:
                diagnosis.append(f"✅ Found {signal_stats['buy_signal_count']} buy signals!")
            else:
                diagnosis.append("Unknown issue - all individual conditions pass but no combined signals")
        
        return {
            "data_stats": data_stats,
            "signal_stats": signal_stats,
            "indicator_samples": indicator_samples,
            "sample_buy_signals": sample_buys,
            "diagnosis": diagnosis,
            "parameters_used": {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi_period": rsi_period,
                "rsi_oversold": rsi_oversold,
                "rsi_overbought": rsi_overbought,
                "cci_period": cci_period,
                "cci_oversold": cci_oversold,
                "cci_overbought": cci_overbought,
            }
        }
        
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        return {
            "error": str(e),
            "type": type(e).__name__
        }
