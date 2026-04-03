"""
Reversal Feature Extractor

Extracts features for reversal point classification (peaks/valleys)
using ZigZag-labeled data from the indicators table.

Features include:
- Technical indicators (RSI, MACD, ATR, Bollinger Bands)
- Reversal-specific derived features (RSI divergence, volume climax, candle patterns)
- Temporal features (hour, day of week, session)
- Price action features (wicks, body size, recent swings)
- Regime features (ADX, Hurst exponent, ATR ratio) — added for retraining

The module-level function ``compute_features_from_ohlcv`` provides a
standalone path that takes a plain OHLCV DataFrame, computes indicators
in-memory, then derives the full reversal feature set.  Both the DB-backed
``ReversalFeatureExtractor`` and the backtest ``MLReversalStrategy`` call
this same function to guarantee feature parity between training and inference.
"""
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import cast, select, and_, Text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData
from src.database.models.indicators import Indicators
from src.ml.data.feature_engineering import FeatureEngineering
from src.services.indicator_compute_service import compute_indicators_df

logger = logging.getLogger(__name__)


# ── Regime feature helpers ────────────────────────────────────────────────────

def _compute_hurst_rs(closes: np.ndarray, max_lag: int = 20) -> float:
    """
    Estimate the Hurst exponent via rescaled range (R/S) analysis.

    Interpretation:
        H > 0.5: trending / persistent series
        H = 0.5: random walk (Brownian motion)
        H < 0.5: mean-reverting series

    For each lag n from 2 to max_lag:
        1. Split ``closes`` into non-overlapping blocks of size n.
        2. For each block compute R/S = (max - min of cumulative deviation) /
           (std of block).  Blocks with zero std are skipped.
        3. Mean R/S_n across all valid blocks.
    Hurst = slope of linear regression: log(R/S_n) ~ H * log(n).

    Args:
        closes:  1-D numpy array of close prices, oldest first.
                 Minimum recommended length: 2 * max_lag.
        max_lag: Upper bound on lag for the regression. Default 20.

    Returns:
        float in [0.0, 1.0].  Returns 0.5 (random-walk default) when
        fewer than 3 valid (lag, R/S) pairs are available.

    Edge cases:
        - All closes identical → every S == 0 → all blocks skipped → 0.5.
        - len(closes) < max_lag → computed on available blocks; 0.5 if < 3
          valid lags.
    """
    if len(closes) < max_lag:
        return 0.5

    log_lags = []
    log_rs = []

    for lag in range(2, max_lag + 1):
        n_blocks = len(closes) // lag
        if n_blocks < 1:
            continue
        rs_values = []
        for i in range(n_blocks):
            block = closes[i * lag:(i + 1) * lag]
            mean = np.mean(block)
            deviations = block - mean
            cumdev = np.cumsum(deviations)
            R = np.max(cumdev) - np.min(cumdev)
            S = np.std(block, ddof=1)
            if S > 0:
                rs_values.append(R / S)
        if rs_values:
            log_lags.append(np.log(lag))
            log_rs.append(np.log(np.mean(rs_values)))

    if len(log_lags) < 3:
        return 0.5

    slope, _ = np.polyfit(log_lags, log_rs, 1)
    return float(np.clip(slope, 0.0, 1.0))


def _compute_adx_series(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Compute a full ADX(period) series using Wilder's smoothed method.

    The returned array is the same length as the input arrays.  The first
    ``2 * period`` positions are filled with NaN (insufficient warm-up data).

    Wilder's smoothing steps (same math as trend_filter._compute_adx):
        per-bar: +DM, -DM, TR (length n-1 from n input bars)
        → Wilder accumulator smooth over `period` bars
        → +DI, -DI, DX
        → Wilder mean-smooth DX over `period` bars → ADX

    Args:
        highs, lows, closes: 1-D arrays, same length, oldest first.
        period: ADX lookback. Default 14.

    Returns:
        np.ndarray of shape (len(closes),), dtype float64.
        Values at indices [0 .. 2*period-2] are np.nan (warm-up).
        Values at indices [2*period-1 ..] are ADX in [0, 100].

    Edge cases:
        - Fewer than 2*period+1 bars: all NaN.
        - Flat price series: ADX approaches 0 (no directional movement).
    """
    n = len(closes)
    result = np.full(n, np.nan, dtype=np.float64)

    min_bars = 2 * period + 1
    if n < min_bars:
        return result

    # Per-bar directional movement and true range (length n-1)
    up_move   = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]

    plus_dm  = np.where((up_move > down_move)   & (up_move   > 0), up_move,   0.0)
    minus_dm = np.where((down_move > up_move)    & (down_move > 0), down_move, 0.0)

    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:]  - closes[:-1]),
        ),
    )

    # Wilder accumulator smoothing for DM/TR (same as trend_filter._wilder_smooth_dm)
    def _wilder_acc(values: np.ndarray) -> np.ndarray:
        out = np.empty(len(values) - period + 1, dtype=np.float64)
        out[0] = float(np.sum(values[:period]))
        for i in range(1, len(out)):
            out[i] = out[i - 1] - out[i - 1] / period + values[period - 1 + i]
        return out

    s_plus  = _wilder_acc(plus_dm)
    s_minus = _wilder_acc(minus_dm)
    s_tr    = _wilder_acc(tr)

    with np.errstate(invalid="ignore", divide="ignore"):
        plus_di  = np.where(s_tr > 0, 100.0 * s_plus  / s_tr, 0.0)
        minus_di = np.where(s_tr > 0, 100.0 * s_minus / s_tr, 0.0)

    di_sum  = plus_di + minus_di
    di_diff = np.abs(plus_di - minus_di)
    with np.errstate(invalid="ignore", divide="ignore"):
        dx = np.where(di_sum > 0, 100.0 * di_diff / di_sum, 0.0)

    if len(dx) < period:
        return result

    # Wilder mean-smooth of DX → ADX series (same as trend_filter._wilder_smooth_adx)
    adx_out = np.empty(len(dx) - period + 1, dtype=np.float64)
    adx_out[0] = float(np.mean(dx[:period]))
    for i in range(1, len(adx_out)):
        adx_out[i] = adx_out[i - 1] - adx_out[i - 1] / period + dx[period - 1 + i] / period

    # Map back to full-length array.
    #
    # Index tracing (n input bars, period=14):
    #   up_move / tr          : length n-1   (bar[1]..bar[n-1])
    #   s_plus / s_tr (acc)   : length n-period   (seed covers bars 0..period-2 in DM space)
    #   dx                    : length n-period
    #   adx_out (Wilder mean) : length (n-period) - period + 1 = n - 2*period + 1
    #
    # adx_out[0] is the average of dx[0..period-1].
    # dx[0] corresponds to the first complete DM smoothing window, which
    # consumes original bars 0 through 2*period-2  (0-indexed).
    # Therefore adx_out[0] is placed at output index 2*period - 1.
    start_idx = 2 * period - 1
    result[start_idx : start_idx + len(adx_out)] = adx_out

    return result


# ── Standalone feature computation (no DB dependency) ────────────────────────

def compute_features_from_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all reversal features from a raw OHLCV DataFrame.

    This is the **single source of truth** for feature computation.
    Both the DB-backed training path and the tick-buffer backtest path
    call this function so that features match exactly.

    Args:
        df: DataFrame with columns: time, open, high, low, close, volume.
            Must be sorted by time ascending.  A ``zigzag_label`` column
            is added (all zeros) if missing so downstream code works.

    Returns:
        DataFrame with all indicator + derived + temporal + pattern columns.
        Rows with NaN (from indicator warm-up) are **not** dropped — the
        caller decides how to handle them.
    """
    # 1. Technical indicators (RSI, MACD, ATR, BB, MAs)
    df = compute_indicators_df(df)

    # Add zigzag_label placeholder if not present (inference path)
    if "zigzag_label" not in df.columns:
        df["zigzag_label"] = 0

    # 2. Reversal-specific derived features
    df = _calculate_reversal_features(df)

    # 3. Temporal features
    df = _add_temporal_features(df)

    # 4. Candlestick pattern features
    df = _add_candle_patterns(df)

    # 5. Regime features (ADX, Hurst, ATR ratio)
    df = _add_regime_features(df)

    return df


def _calculate_reversal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate reversal-specific derived features (standalone)."""
    df = df.copy()

    bb_width = df["bb_upper"] - df["bb_lower"]
    df["bb_distance_pct"] = ((df["close"] - df["bb_middle"]) / (bb_width / 2)) * 100
    df["bb_squeeze"] = bb_width / df["close"]

    df["distance_ma20"] = (df["close"] - df["ma_20"]) / df["ma_20"] * 100
    df["distance_ma50"] = (df["close"] - df["ma_50"]) / df["ma_50"] * 100

    df["atr_change"] = df["atr"].pct_change(periods=5)
    df["atr_percentile"] = df["atr"].rolling(window=50).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1]
    )

    df["rsi_lag5"] = df["rsi"].shift(5)
    df["close_lag5"] = df["close"].shift(5)
    df["rsi_divergence"] = np.where(
        (df["close"] > df["close_lag5"]) & (df["rsi"] < df["rsi_lag5"]),
        -1,
        np.where(
            (df["close"] < df["close_lag5"]) & (df["rsi"] > df["rsi_lag5"]),
            1,
            0,
        ),
    )

    df["volume_ma"] = df["volume"].rolling(window=20).mean()
    df["volume_spike"] = df["volume"] / df["volume_ma"]
    df["volume_trend"] = df["volume"].rolling(window=5).mean() / df["volume_ma"]

    df["macd_histogram"] = df["macd"] - df["macd_signal"]
    df["macd_histogram_change"] = df["macd_histogram"].diff()

    df["roc_5"] = df["close"].pct_change(periods=5) * 100
    df["roc_10"] = df["close"].pct_change(periods=10) * 100
    df["roc_20"] = df["close"].pct_change(periods=20) * 100

    df["high_5"] = df["high"].rolling(window=5).max()
    df["low_5"] = df["low"].rolling(window=5).min()
    df["swing_range"] = (df["high_5"] - df["low_5"]) / df["close"]

    return df


def _add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add time-based features (standalone)."""
    df = df.copy()

    df["hour"] = df["time"].dt.hour
    df["day_of_week"] = df["time"].dt.dayofweek
    df["day_of_month"] = df["time"].dt.day

    df["session_asian"] = ((df["hour"] >= 0) & (df["hour"] < 8)).astype(int)
    df["session_european"] = ((df["hour"] >= 8) & (df["hour"] < 16)).astype(int)
    df["session_us"] = (df["hour"] >= 16).astype(int)

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    return df


def _add_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Add candlestick pattern features (standalone)."""
    df = df.copy()

    df["body"] = abs(df["close"] - df["open"])
    df["range"] = df["high"] - df["low"]
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]

    df["body_pct"] = df["body"] / df["range"]
    df["upper_wick_pct"] = df["upper_wick"] / df["range"]
    df["lower_wick_pct"] = df["lower_wick"] / df["range"]

    df["is_doji"] = (df["body_pct"] < 0.1).astype(int)
    df["is_hammer"] = ((df["body_pct"] < 0.3) & (df["lower_wick_pct"] > 0.6)).astype(int)
    df["is_inverted_hammer"] = ((df["body_pct"] < 0.3) & (df["upper_wick_pct"] > 0.6)).astype(int)

    df["prev_body"] = df["body"].shift(1)
    df["is_engulfing"] = (df["body"] > 1.5 * df["prev_body"]).astype(int)

    return df


def _add_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add regime-context features to help the model learn that reversals
    look different in trending versus ranging markets.

    Three features are added:

    ``regime_adx`` — ADX(14) continuous value.
        Range: [0, 100].  > 25 = trending, < 20 = ranging.
        First 2*14 = 28 rows will be NaN (Wilder warm-up).

    ``regime_hurst`` — Hurst exponent from R/S analysis, rolling 50-bar window.
        Range: [0.0, 1.0].  > 0.5 = trending/persistent, < 0.5 = mean-reverting.
        First 49 rows default to 0.5 (insufficient window).

    ``regime_atr_ratio`` — ATR(14) divided by its 50-bar SMA.
        Range: (0, ∞).  > 1.0 = above-average volatility.
        NaN where ATR SMA is zero or ATR column is absent.

    Args:
        df: DataFrame that already has 'atr', 'high', 'low', 'close' columns
            (produced by compute_indicators_df before this call).

    Returns:
        DataFrame with three new columns appended.  Input is not mutated.
    """
    df = df.copy()

    highs  = df["high"].values.astype(np.float64)
    lows   = df["low"].values.astype(np.float64)
    closes = df["close"].values.astype(np.float64)

    # ---- regime_adx ----
    df["regime_adx"] = _compute_adx_series(highs, lows, closes, period=14)

    # ---- regime_hurst (rolling 50-bar window) ----
    hurst_values = []
    for i in range(len(df)):
        if i < 50:
            hurst_values.append(0.5)  # default for insufficient warm-up data
        else:
            window = closes[i - 50:i]
            hurst_values.append(_compute_hurst_rs(window))
    df["regime_hurst"] = hurst_values

    # ---- regime_atr_ratio ----
    if "atr" in df.columns:
        atr_sma = df["atr"].rolling(50).mean()
        df["regime_atr_ratio"] = df["atr"] / atr_sma.replace(0, np.nan)
    else:
        df["regime_atr_ratio"] = np.nan

    return df


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """
    Get the list of feature columns for training/inference.

    Shared by both the DB-backed extractor and standalone path.

    The exclusion list deliberately does NOT contain 'regime_adx',
    'regime_hurst', or 'regime_atr_ratio' — those are model features.
    """
    exclude_cols = [
        "time", "zigzag_label", "zigzag_value", "id",
        "open", "high", "low", "close",
        "rsi_lag5", "close_lag5",
        "prev_body", "body", "range", "upper_wick", "lower_wick",
        "high_5", "low_5",
        "volume_ma",
    ]

    return [
        col for col in df.columns
        if col not in exclude_cols and pd.api.types.is_numeric_dtype(df[col])
    ]


# ── DB-backed feature extractor ─────────────────────────────────────────────

class ReversalFeatureExtractor:
    """
    Extracts features for reversal classification from labeled data.

    Usage:
        extractor = ReversalFeatureExtractor(session)
        X, y, feature_names = await extractor.extract_training_data(
            symbol='CrudeOIL',
            timeframe='H1',
            start_date=start,
            end_date=end
        )
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.feature_engineering = FeatureEngineering()

    async def extract_training_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_reversal_distance: int = 5  # Minimum bars between labeled reversals
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Extract features and labels for training.

        Args:
            symbol: Trading symbol (e.g., 'CrudeOIL')
            timeframe: Candle timeframe (e.g., 'H1')
            start_date: Optional start date filter
            end_date: Optional end date filter
            min_reversal_distance: Filter out reversals closer than this

        Returns:
            Tuple of (X, y, feature_names) where:
            - X: Feature matrix (N, F) with F features
            - y: Labels (N,) with values {-1, 0, 1}
            - feature_names: List of feature column names
        """
        logger.info(f"Extracting training features for {symbol} {timeframe}")

        # 1. Load data from database
        df = await self._load_data(symbol, timeframe, start_date, end_date)

        if df.empty:
            logger.warning(f"No data found for {symbol} {timeframe}")
            return np.array([]), np.array([]), []

        logger.info(f"Loaded {len(df)} candles")

        # 2. Calculate derived features
        df = self._calculate_reversal_features(df)

        # 3. Add temporal features
        df = self._add_temporal_features(df)

        # 4. Add candle pattern features
        df = self._add_candle_patterns(df)

        # 5. Clean up: drop rows with NaN (from windowing/lag features)
        df = df.dropna()

        # 6. Filter reversals that are too close together (optional quality filter)
        if min_reversal_distance > 0:
            df = self._filter_close_reversals(df, min_reversal_distance)

        # 7. Extract features and labels
        feature_cols = self._get_feature_columns(df)
        X = df[feature_cols].values
        y = df['zigzag_label'].values.astype(int)

        logger.info(
            f"Extracted {len(X)} samples with {len(feature_cols)} features. "
            f"Class distribution: "
            f"valleys={np.sum(y == -1)}, "
            f"neither={np.sum(y == 0)}, "
            f"peaks={np.sum(y == 1)}"
        )

        return X, y, feature_cols

    async def extract_live_features(
        self,
        symbol: str,
        timeframe: str,
        current_time: datetime,
        lookback_bars: int = 100
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Extract features for current candle (live inference).

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            current_time: Current time
            lookback_bars: Number of historical bars to load for feature calculation

        Returns:
            Tuple of (features, feature_names) for current candle only
        """
        # Load recent data including current bar
        df = await self._load_data(
            symbol,
            timeframe,
            start_date=None,
            end_date=current_time
        )

        if len(df) < lookback_bars:
            logger.warning(f"Insufficient data: {len(df)} < {lookback_bars}")
            lookback_bars = len(df)

        # Take only the most recent bars
        df = df.tail(lookback_bars).copy()

        # Calculate features
        df = self._calculate_reversal_features(df)
        df = self._add_temporal_features(df)
        df = self._add_candle_patterns(df)

        # Get features for the last (current) candle
        feature_cols = self._get_feature_columns(df)

        # Return only the last row (current candle)
        if len(df) > 0:
            X = df[feature_cols].iloc[-1:].values
            return X, feature_cols
        else:
            return np.array([]), []

    async def _load_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Load market data + indicators from database."""

        # Query to join market_data with indicators
        stmt = (
            select(
                MarketData.time,
                MarketData.open,
                MarketData.high,
                MarketData.low,
                MarketData.last.label('close'),
                MarketData.volume,
                Indicators.rsi,
                Indicators.macd,
                Indicators.macd_signal,
                Indicators.atr,
                Indicators.bb_upper,
                Indicators.bb_middle,
                Indicators.bb_lower,
                Indicators.ma_20,
                Indicators.ma_50,
                Indicators.ma_200,
                Indicators.zigzag_label
            )
            .join(Indicators, and_(
                MarketData.time == Indicators.time,
                MarketData.symbol == Indicators.symbol,
                cast(MarketData.timeframe, Text) == Indicators.timeframe
            ))
            .where(MarketData.symbol == symbol)
            .where(cast(MarketData.timeframe, Text) == timeframe)
            .order_by(MarketData.time.asc())
        )

        if start_date:
            stmt = stmt.where(MarketData.time >= start_date)
        if end_date:
            stmt = stmt.where(MarketData.time <= end_date)

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume',
            'rsi', 'macd', 'macd_signal', 'atr',
            'bb_upper', 'bb_middle', 'bb_lower',
            'ma_20', 'ma_50', 'ma_200', 'zigzag_label'
        ])

        # Convert Decimal to float
        for col in df.columns:
            if col not in ['time', 'zigzag_label']:
                df[col] = df[col].astype(float)

        return df

    def _calculate_reversal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate reversal-specific derived features."""
        df = df.copy()

        # 1. Distance from Bollinger Bands (% distance from middle to upper/lower)
        bb_width = df['bb_upper'] - df['bb_lower']
        df['bb_distance_pct'] = ((df['close'] - df['bb_middle']) / (bb_width / 2)) * 100
        df['bb_squeeze'] = bb_width / df['close']  # Volatility contraction indicator

        # 2. Distance from moving averages
        df['distance_ma20'] = (df['close'] - df['ma_20']) / df['ma_20'] * 100
        df['distance_ma50'] = (df['close'] - df['ma_50']) / df['ma_50'] * 100

        # 3. ATR expansion (volatility spike)
        df['atr_change'] = df['atr'].pct_change(periods=5)  # 5-bar ATR change
        df['atr_percentile'] = df['atr'].rolling(window=50).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1]
        )

        # 4. RSI divergence (simplified version)
        # Check if RSI is making new highs/lows while price is not
        df['rsi_lag5'] = df['rsi'].shift(5)
        df['close_lag5'] = df['close'].shift(5)
        df['rsi_divergence'] = np.where(
            (df['close'] > df['close_lag5']) & (df['rsi'] < df['rsi_lag5']),
            -1,  # Bearish divergence
            np.where(
                (df['close'] < df['close_lag5']) & (df['rsi'] > df['rsi_lag5']),
                1,  # Bullish divergence
                0  # No divergence
            )
        )

        # 5. Volume features
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_spike'] = df['volume'] / df['volume_ma']  # > 2 = climax
        df['volume_trend'] = df['volume'].rolling(window=5).mean() / df['volume_ma']

        # 6. MACD features
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        df['macd_histogram_change'] = df['macd_histogram'].diff()

        # 7. Price momentum features
        df['roc_5'] = df['close'].pct_change(periods=5) * 100  # 5-bar rate of change
        df['roc_10'] = df['close'].pct_change(periods=10) * 100
        df['roc_20'] = df['close'].pct_change(periods=20) * 100

        # 8. Recent swing features
        df['high_5'] = df['high'].rolling(window=5).max()
        df['low_5'] = df['low'].rolling(window=5).min()
        df['swing_range'] = (df['high_5'] - df['low_5']) / df['close']

        return df

    def _add_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features."""
        df = df.copy()

        # Extract time components
        df['hour'] = df['time'].dt.hour
        df['day_of_week'] = df['time'].dt.dayofweek  # 0=Monday
        df['day_of_month'] = df['time'].dt.day

        # Trading session indicators (for 24-hour markets like oil)
        # Asian: 00:00-08:00 UTC, European: 08:00-16:00 UTC, US: 16:00-00:00 UTC
        df['session_asian'] = ((df['hour'] >= 0) & (df['hour'] < 8)).astype(int)
        df['session_european'] = ((df['hour'] >= 8) & (df['hour'] < 16)).astype(int)
        df['session_us'] = (df['hour'] >= 16).astype(int)

        # Cyclical encoding for hour (preserve 23->0 continuity)
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)

        # Cyclical encoding for day of week
        df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)

        return df

    def _add_candle_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add candlestick pattern features."""
        df = df.copy()

        # Basic candle metrics
        df['body'] = abs(df['close'] - df['open'])
        df['range'] = df['high'] - df['low']
        df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']

        # Normalized candle features
        df['body_pct'] = df['body'] / df['range']
        df['upper_wick_pct'] = df['upper_wick'] / df['range']
        df['lower_wick_pct'] = df['lower_wick'] / df['range']

        # Pattern detection (simplified)
        # Doji: small body relative to range
        df['is_doji'] = (df['body_pct'] < 0.1).astype(int)

        # Hammer/Inverted Hammer: small body, long lower/upper wick
        df['is_hammer'] = (
            (df['body_pct'] < 0.3) &
            (df['lower_wick_pct'] > 0.6)
        ).astype(int)

        df['is_inverted_hammer'] = (
            (df['body_pct'] < 0.3) &
            (df['upper_wick_pct'] > 0.6)
        ).astype(int)

        # Engulfing (requires prev candle)
        df['prev_body'] = df['body'].shift(1)
        df['is_engulfing'] = (df['body'] > 1.5 * df['prev_body']).astype(int)

        return df

    def _filter_close_reversals(
        self,
        df: pd.DataFrame,
        min_distance: int
    ) -> pd.DataFrame:
        """
        Filter out reversals that are too close together.

        This improves label quality by removing noisy reversals.
        """
        df = df.copy()

        # Find indices of reversals
        reversal_indices = df[df['zigzag_label'] != 0].index.tolist()

        # Mark reversals to keep
        keep_mask = np.ones(len(df), dtype=bool)
        last_kept = -min_distance

        for idx in reversal_indices:
            pos = df.index.get_loc(idx)
            if pos - last_kept < min_distance:
                # Too close to last reversal - mark as 'neither'
                df.loc[idx, 'zigzag_label'] = 0
            else:
                last_kept = pos

        return df

    def _get_feature_columns(self, df: pd.DataFrame) -> List[str]:
        """Get list of feature columns to use for training/inference."""

        # Exclude these columns from features
        exclude_cols = [
            'time', 'zigzag_label',  # Labels/metadata
            'open', 'high', 'low', 'close',  # Raw OHLC (use derived features instead)
            'rsi_lag5', 'close_lag5',  # Intermediate calculations
            'prev_body', 'body', 'range', 'upper_wick', 'lower_wick',  # Use _pct versions
            'high_5', 'low_5',  # Intermediate calculations
            'volume_ma'  # Use volume_spike and volume_trend instead
        ]

        # Get all numeric columns except excluded ones
        feature_cols = [
            col for col in df.columns
            if col not in exclude_cols and pd.api.types.is_numeric_dtype(df[col])
        ]

        return feature_cols

    def get_feature_statistics(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str]
    ) -> Dict:
        """Get statistics about extracted features."""

        return {
            'n_samples': len(X),
            'n_features': X.shape[1],
            'feature_names': feature_names,
            'class_distribution': {
                'valleys': int(np.sum(y == -1)),
                'neither': int(np.sum(y == 0)),
                'peaks': int(np.sum(y == 1))
            },
            'class_imbalance_ratio': {
                'valley_pct': float(np.sum(y == -1) / len(y) * 100),
                'peak_pct': float(np.sum(y == 1) / len(y) * 100),
                'neither_pct': float(np.sum(y == 0) / len(y) * 100)
            },
            'features_with_missing': int(np.sum(np.isnan(X), axis=0).sum()),
            'samples_with_missing': int(np.sum(np.isnan(X), axis=1).sum())
        }
