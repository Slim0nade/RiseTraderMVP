"""
LiveTradingService - Autonomous trading loop that bypasses the agent coordinator.

Runs on a configurable interval and, for each symbol:
  1. Fetches latest 100 H1 candles from PostgreSQL
  2. Runs three strategies (momentum, mean-reversion, breakout)
  3. Validates the signal against basic risk rules
  4. Places or logs a market order via MT4

Configuration (environment variables):
  LIVE_TRADING_ENABLED      - "true" to activate (default: false)
  LIVE_TRADING_SYMBOLS      - Comma-separated list (default: CrudeOIL,USA500,GBPJPY.)
  LIVE_TRADING_INTERVAL     - Seconds between cycles (default: 300)
  LIVE_TRADING_DRY_RUN      - "false" to send real orders (default: true)
  MAX_OPEN_POSITIONS        - Hard cap on concurrent positions (default: 5)
  MAX_DAILY_LOSS            - USD daily loss limit (default: 1000)
"""

import asyncio
import os
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
import yaml

from src.database.repositories.market_data_repository import MarketDataRepository
from src.utils.atr_calculator import Candle, InsufficientDataError, calculate_atr_wilder
from src.services.backtesting.value_area_strategy import ValueAreaStrategy, ValueAreaParams
from src.services.market_tick import MarketTick
from src.services.stealth_stop_manager import StealthStopManager
from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier
from src.trading.regime.strategy_router import StrategyRouter
from src.trading.risk.tiered_position_sizer import TieredPositionSizer
from pathlib import Path

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# ML Model paths
# ---------------------------------------------------------------------------
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "reversal_classifier"

# ---------------------------------------------------------------------------
# Contract metadata
# ---------------------------------------------------------------------------

# Key: symbol as stored in DB / sent to MT4.  "GBPJPY." keeps the trailing dot
# because that is what the MT4 EA expects for that instrument.
CONTRACT_SIZES: Dict[str, int] = {
    "CrudeOIL": 1000,
    "USA500": 50,
    "GBPJPY.": 100_000,
    "XAUUSD": 100,
    "BRENT_OIL": 1000,
    "#TSLA": 1000,
}

# Pip size per symbol (used for anti-stop-hunt offset, not for P&L math)
PIP_VALUES: Dict[str, float] = {
    "CrudeOIL": 0.01,
    "USA500": 0.01,
    "GBPJPY.": 0.001,
    "XAUUSD": 0.01,
    "BRENT_OIL": 0.01,
    "#TSLA": 0.01,
}

# Default pip size for any symbol not in the map above
DEFAULT_PIP = 0.01

# DB symbol mapping — MT4 symbols may differ from DB symbols
# MT4 uses "GBPJPY." / "#TSLA" but DB stores "GBPJPY" / "TSLA"
MT4_TO_DB_SYMBOL: Dict[str, str] = {
    "GBPJPY.": "GBPJPY",
    "#TSLA": "TSLA",
}

# ---------------------------------------------------------------------------
# Per-symbol strategy weights (MoE path a)
# ---------------------------------------------------------------------------
# Each symbol gets its own ensemble weights that override the defaults in
# _combine_signals.  Rationale per symbol:
#   - CrudeOIL: proven ensemble from backtest (VA +209%, ML Rev +156%).
#     Heavier VA + ML Reversal (only persisted model), lighter trend tools.
#   - USA500: index → respects VAH/VAL, trends well. Drop mean-rev (gap risk).
#   - GBPJPY.: FX pair, XGB F1 weakest (0.094) → lean on trend/momentum.
#   - #TSLA: single-name beta, news-driven, wide spread → trend + momentum
#     + breakout only. NO mean-reversion (gap risk on news/earnings).
#
# Weights need NOT sum to 1.0 — _combine_signals normalizes by total weight.
# A strategy absent from the dict gets weight 0 (effectively disabled for
# that symbol).  Strategy names must match the keys produced by
# _generate_signal's signals dict (ml_reversal, value_area, momentum,
# trend_following, mean_reversion, breakout).
SYMBOL_WEIGHTS: Dict[str, Dict[str, float]] = {
    "CrudeOIL": {
        "value_area": 0.30,
        "ml_reversal": 0.25,
        "momentum": 0.20,
        "trend_following": 0.10,
        "mean_reversion": 0.10,
        "breakout": 0.05,
    },
    "USA500": {
        "value_area": 0.35,
        "trend_following": 0.25,
        "momentum": 0.20,
        "breakout": 0.15,
        "ml_reversal": 0.05,
    },
    "GBPJPY.": {
        "trend_following": 0.35,
        "momentum": 0.25,
        "value_area": 0.20,
        "breakout": 0.15,
        "mean_reversion": 0.05,
    },
    "#TSLA": {
        "trend_following": 0.35,
        "momentum": 0.30,
        "breakout": 0.25,
        "value_area": 0.10,
    },
}


def _symbol_weights(symbol: str) -> Optional[Dict[str, float]]:
    """Look up per-symbol ensemble weights; returns None if not configured."""
    return SYMBOL_WEIGHTS.get(symbol)

def _db_symbol(mt4_symbol: str) -> str:
    """Convert MT4 symbol to DB symbol for candle lookups."""
    return MT4_TO_DB_SYMBOL.get(mt4_symbol, mt4_symbol)

def _ml_model_symbol(mt4_symbol: str) -> str:
    """Convert MT4 symbol to ML model directory name."""
    return MT4_TO_DB_SYMBOL.get(mt4_symbol, mt4_symbol)

# Minimum lot size accepted by MT4
MIN_LOTS = 0.01

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _env_bool(key: str, default: bool) -> bool:
    """Parse a boolean environment variable ('true'/'false', case-insensitive)."""
    raw = os.environ.get(key, "").strip().lower()
    if raw == "true":
        return True
    if raw == "false":
        return False
    return default


def _env_symbols(key: str, default: List[str]) -> List[str]:
    """Parse a comma-separated symbol list from an environment variable."""
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


def _env_float(key: str, default: float) -> float:
    """Parse a float environment variable."""
    try:
        return float(os.environ.get(key, ""))
    except (ValueError, TypeError):
        return default


def _env_int(key: str, default: int) -> int:
    """Parse an int environment variable."""
    try:
        return int(os.environ.get(key, ""))
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Trading-mode threshold resolution
# ---------------------------------------------------------------------------

# Code-level defaults — used only when config/risk.yaml is missing.
_PAPER_THRESHOLD_DEFAULT: float = 0.35
_PAPER_CONFIDENCE_DEFAULT: float = 0.35
_LIVE_THRESHOLD_DEFAULT: float = 0.60
_LIVE_CONFIDENCE_DEFAULT: float = 0.60

# Position-cap defaults — used only when config/risk.yaml is missing or the
# position_caps block is absent.  Never change _LIVE_CAP_DEFAULT below 1.
_PAPER_CAP_DEFAULT: int = 5          # Max concurrent paper positions per symbol
_LIVE_CAP_DEFAULT: int = 1           # Hard cap for live — NEVER relax
_PAPER_AGGREGATE_PCT_DEFAULT: float = 8.0  # 8% aggregate exposure cap (paper)

_RISK_YAML = Path(__file__).resolve().parent.parent.parent / "config" / "risk.yaml"


def _load_thresholds(is_paper: bool) -> Tuple[float, float, str]:
    """
    Return (signal_threshold, min_confidence, source) for the given mode.

    source is "yaml" when config/risk.yaml was found and parsed successfully,
    or "default" when the file is absent or unreadable (a warning is logged).

    Raises AssertionError if the live threshold is not at least 0.20 above
    the paper threshold (fat-finger guard).  This is checked regardless of
    which mode is active so a bad YAML is caught immediately on startup.
    """
    paper_st = _PAPER_THRESHOLD_DEFAULT
    paper_mc = _PAPER_CONFIDENCE_DEFAULT
    live_st = _LIVE_THRESHOLD_DEFAULT
    live_mc = _LIVE_CONFIDENCE_DEFAULT
    source = "default"

    if _RISK_YAML.exists():
        try:
            with open(_RISK_YAML, "r") as fh:
                data: Dict[str, Any] = yaml.safe_load(fh) or {}
            thr = data.get("thresholds", {})
            paper_block = thr.get("paper", {})
            live_block = thr.get("live", {})
            paper_st = float(paper_block.get("signal_threshold", paper_st))
            paper_mc = float(paper_block.get("min_confidence", paper_mc))
            live_st = float(live_block.get("signal_threshold", live_st))
            live_mc = float(live_block.get("min_confidence", live_mc))
            source = "yaml"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "risk_yaml_load_failed",
                path=str(_RISK_YAML),
                error=str(exc),
                fallback="coded defaults",
            )

    # Fat-finger guard: live must be strictly tighter than paper by at least 0.20.
    assert live_st >= paper_st + 0.20, (
        f"config/risk.yaml invariant violated: live_signal_threshold ({live_st}) "
        f"must be >= paper_signal_threshold ({paper_st}) + 0.20"
    )
    assert live_mc >= paper_mc + 0.20, (
        f"config/risk.yaml invariant violated: live_min_confidence ({live_mc}) "
        f"must be >= paper_min_confidence ({paper_mc}) + 0.20"
    )

    if is_paper:
        return paper_st, paper_mc, source
    return live_st, live_mc, source


def _load_position_caps() -> Tuple[int, int, float, str]:
    """
    Return (paper_cap, live_cap, paper_aggregate_pct, source) from config/risk.yaml.

    paper_cap           — max concurrent paper positions per symbol (default 5)
    live_cap            — max concurrent live positions per symbol  (default 1, NEVER > 1)
    paper_aggregate_pct — max aggregate exposure % of balance for paper (default 8.0)
    source              — "yaml" if loaded from file, "default" otherwise

    Raises AssertionError if live_cap != 1 — the live-mode hard cap is a
    safety invariant that must never be relaxed without explicit code change.
    """
    paper_cap = _PAPER_CAP_DEFAULT
    live_cap = _LIVE_CAP_DEFAULT
    paper_agg_pct = _PAPER_AGGREGATE_PCT_DEFAULT
    source = "default"

    if _RISK_YAML.exists():
        try:
            with open(_RISK_YAML, "r") as fh:
                data: Dict[str, Any] = yaml.safe_load(fh) or {}
            caps = data.get("position_caps", {})
            paper_block = caps.get("paper", {})
            live_block = caps.get("live", {})
            if caps:  # only update source to "yaml" if the block was present
                paper_cap = int(paper_block.get("max_open_per_symbol", paper_cap))
                live_cap = int(live_block.get("max_open_per_symbol", live_cap))
                paper_agg_pct = float(
                    paper_block.get("max_aggregate_exposure_pct", paper_agg_pct)
                )
                source = "yaml"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "risk_yaml_position_caps_load_failed",
                path=str(_RISK_YAML),
                error=str(exc),
                fallback="coded defaults",
            )

    # Safety invariant: live cap must always be 1.
    assert live_cap == 1, (
        f"config/risk.yaml position_caps.live.max_open_per_symbol must be 1 "
        f"(got {live_cap}). Live-mode per-symbol cap is a hard safety invariant."
    )

    return paper_cap, live_cap, paper_agg_pct, source


def _resolve_trading_mode() -> bool:
    """
    Determine whether we are in paper mode.

    Resolution order (paper wins for safety):
      1. PAPER_VALIDATION_MODE=true  → paper
      2. ENABLE_PAPER_TRADING=true   → paper
      3. ENABLE_LIVE_TRADING=true    → live
      4. Neither set                 → paper (safe default)
    """
    if os.getenv("PAPER_VALIDATION_MODE", "").strip().lower() == "true":
        return True
    if os.getenv("ENABLE_PAPER_TRADING", "").strip().lower() == "true":
        return True
    if os.getenv("ENABLE_LIVE_TRADING", "").strip().lower() == "true":
        return False
    return True  # default: paper


# ---------------------------------------------------------------------------
# Signal helpers — copied verbatim from SignalGeneratorAgent
# ---------------------------------------------------------------------------

def _momentum_strategy(prices: List[Dict]) -> Dict[str, float]:
    """
    10/30 MA crossover momentum strategy.

    Input:  prices list with 'close' keys, oldest-first, minimum 30 entries.
    Output: {"score": float in [-1.0, 1.0], "confidence": 0.7}

    Positive score = bullish, negative = bearish, 0 = neutral.
    """
    closes = np.array([float(p["close"]) for p in prices])
    short_ma = np.mean(closes[-10:])
    long_ma = np.mean(closes[-30:])
    current = closes[-1]

    diff = short_ma - long_ma

    if current > short_ma and short_ma > long_ma:
        # Bullish: scale continuation with MA separation strength
        raw_score = min(abs(diff) / long_ma * 20, 1.0)  # Normalize diff as % of price
        if abs(diff) > long_ma * 0.01:  # MAs separated by > 1% of price = strong continuation
            continuation_factor = min(0.5 + abs(diff) / long_ma * 20, 0.9)
        else:
            continuation_factor = 0.5
        score = raw_score * continuation_factor
    elif current < short_ma and short_ma < long_ma:
        raw_score = min(abs(diff) / long_ma * 20, 1.0)
        if abs(diff) > long_ma * 0.01:
            continuation_factor = min(0.5 + abs(diff) / long_ma * 20, 0.9)
        else:
            continuation_factor = 0.5
        score = -(raw_score * continuation_factor)
    else:
        score = 0.0

    return {"score": score, "confidence": 0.7}


def _mean_reversion_strategy(prices: List[Dict]) -> Dict[str, float]:
    """
    Bollinger Bands (20-period, 2σ) mean-reversion strategy.

    Input:  prices list with 'close' keys, oldest-first, minimum 20 entries.
    Output: {"score": float in [-1.0, 1.0], "confidence": 0.6}

    Positive score = price below lower band (buy), negative = above upper band (sell).
    """
    closes = np.array([float(p["close"]) for p in prices])
    ma = np.mean(closes[-20:])
    std = np.std(closes[-20:])

    if std == 0.0:
        return {"score": 0.0, "confidence": 0.0}

    upper = ma + 2 * std
    lower = ma - 2 * std
    current = closes[-1]

    if current < lower:
        score = min((lower - current) / std, 1.0)
    elif current > upper:
        score = max((upper - current) / std, -1.0)
    else:
        score = 0.0

    return {"score": score, "confidence": 0.6}


def _breakout_strategy(prices: List[Dict]) -> Dict[str, float]:
    """
    20-period high/low breakout strategy.

    Input:  prices list with 'high', 'low', 'close' keys, oldest-first, minimum 21 entries.
    Output: {"score": float in [-1.0, 1.0], "confidence": 0.65}

    Positive score = bullish breakout, negative = bearish breakout, 0 = inside range.
    """
    closes = np.array([float(p["close"]) for p in prices])
    highs = np.array([float(p["high"]) for p in prices])
    lows = np.array([float(p["low"]) for p in prices])

    recent_high = np.max(highs[-20:])
    recent_low = np.min(lows[-20:])
    current = closes[-1]

    range_size = recent_high - recent_low
    if range_size <= 0.0:
        return {"score": 0.0, "confidence": 0.0}

    # Position within 20-bar range (0 = at low, 1 = at high)
    position = (current - recent_low) / range_size

    if position >= 0.85:  # Upper 15% of range → bullish breakout zone
        score = position  # 0.85 to 1.0
        return {"score": score, "confidence": 0.65}
    elif position <= 0.15:  # Lower 15% of range → bearish breakout zone
        score = -(1.0 - position)  # -0.85 to -1.0
        return {"score": score, "confidence": 0.65}
    else:
        return {"score": 0.0, "confidence": 0.0}


def _trend_following_strategy(prices: List[Dict]) -> Optional[Dict[str, float]]:
    """
    Trend-following using EMA20/EMA50 alignment + price position.

    Fires CONTINUOUSLY during sustained trends (unlike momentum which
    dampens after the initial crossover).

    BUY when: price > EMA20 > EMA50 (uptrend)
    SELL when: price < EMA20 < EMA50 (downtrend)

    Score scales with EMA separation and price distance from EMA20.
    Returns None if no clear trend.
    """
    if len(prices) < 50:
        return None

    closes = np.array([float(p["close"]) for p in prices])

    # EMA20 and EMA50
    def _ema(data, period):
        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
        return ema

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)

    current = closes[-1]
    e20 = ema20[-1]
    e50 = ema50[-1]

    # Uptrend: price > EMA20 > EMA50
    if current > e20 and e20 > e50:
        # EMA separation as % of price
        separation = (e20 - e50) / e50
        # Price distance above EMA20
        distance = (current - e20) / e20
        # Score: combination of separation strength + price distance
        raw_score = min(separation * 20 + distance * 10, 1.0)
        # Confidence from EMA slope (last 5 bars of EMA20)
        ema20_slope = (ema20[-1] - ema20[-6]) / ema20[-6] if len(ema20) >= 6 else 0
        confidence = min(0.5 + abs(ema20_slope) * 50, 0.90)
        return {"score": max(0.3, raw_score), "confidence": confidence}

    # Downtrend: price < EMA20 < EMA50
    elif current < e20 and e20 < e50:
        separation = (e50 - e20) / e50
        distance = (e20 - current) / e20
        raw_score = min(separation * 20 + distance * 10, 1.0)
        ema20_slope = (ema20[-1] - ema20[-6]) / ema20[-6] if len(ema20) >= 6 else 0
        confidence = min(0.5 + abs(ema20_slope) * 50, 0.90)
        return {"score": -max(0.3, raw_score), "confidence": confidence}

    return None


def _ml_reversal_strategy(prices: List[Dict], symbol: str) -> Optional[Dict[str, float]]:
    """
    ML Reversal strategy using trained XGBoost model.

    Loads the model for the given symbol (if available) and predicts
    reversal probabilities from price features.

    Returns: {"score": float, "confidence": float} or None if model not available.
    """
    ml_sym = _ml_model_symbol(symbol)
    model_dir = MODELS_DIR / f"{ml_sym}_H1"
    model_file = model_dir / "model.json"

    if not model_file.exists():
        return None

    # Model quality gate — block low-accuracy and stale models before loading XGBoost
    metadata_file = model_dir / "metadata.json"
    if metadata_file.exists():
        import json as _json
        with open(metadata_file) as f:
            meta = _json.load(f)
        reversal_f1 = meta.get("reversal_f1", meta.get("rev_f1", 0.0))
        peak_f1 = meta.get("peak_f1", 0.0)
        valley_f1 = meta.get("valley_f1", 0.0)

        # Minimum reversal F1 gate.
        # Peaks+valleys are ~6% of all H1 candles (severe class imbalance), so
        # realistic F1 scores for XGBoost on this task are in the 0.08-0.15 range
        # even for models that add positive P&L in backtest (CrudeOIL backtest
        # returned +156% with F1=0.117).  The prior 0.30 gate was calibrated for
        # a balanced-class model and permanently blocked every ml_reversal
        # signal in production.  0.08 keeps clearly-broken runs out while
        # letting real imbalanced-class models activate.
        MIN_REVERSAL_F1 = 0.08
        if reversal_f1 < MIN_REVERSAL_F1:
            logger.warning(
                "ml_model_quality_gate_blocked",
                symbol=symbol,
                reversal_f1=reversal_f1,
                peak_f1=peak_f1,
                valley_f1=valley_f1,
                min_required=MIN_REVERSAL_F1,
            )
            return None

        # Model staleness check — block models older than 14 days
        training_date_str = meta.get("training_date", meta.get("trained_at", ""))
        if training_date_str:
            from datetime import datetime, timezone
            try:
                training_date = datetime.fromisoformat(str(training_date_str).replace("Z", "+00:00"))
                if training_date.tzinfo is None:
                    training_date = training_date.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - training_date).days
                MAX_MODEL_AGE_DAYS = 14
                if age_days > MAX_MODEL_AGE_DAYS:
                    logger.warning(
                        "ml_model_stale",
                        symbol=symbol,
                        training_date=training_date_str,
                        age_days=age_days,
                        max_age=MAX_MODEL_AGE_DAYS,
                    )
                    return None
            except (ValueError, TypeError):
                pass

    try:
        import xgboost as xgb
        from src.ml.features.reversal_features import compute_features_from_ohlcv

        # Build DataFrame from prices — add synthetic 'time' column for feature extractor
        import pandas as pd
        df = pd.DataFrame(prices)
        # Feature extractor needs a 'time' column — generate hourly timestamps
        df['time'] = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=len(df), freq='h')
        if len(df) < 200:
            logger.debug("ml_reversal_insufficient_data", symbol=symbol, rows=len(df))
            return None

        # Compute features
        features_df = compute_features_from_ohlcv(df)
        if features_df is None or len(features_df) == 0:
            return None

        # Load feature names
        feature_names_file = model_dir / "feature_names.json"
        if feature_names_file.exists():
            import json
            with open(feature_names_file) as f:
                feature_names = json.load(f)
        else:
            feature_names = list(features_df.columns)

        # Filter to model features and take last row
        available = [f for f in feature_names if f in features_df.columns]
        if len(available) < len(feature_names) * 0.8:
            logger.warning("ml_reversal_missing_features", symbol=symbol,
                         available=len(available), expected=len(feature_names))
            return None

        last_row = features_df[available].iloc[-1:].values
        last_row = np.nan_to_num(last_row, nan=0.0)

        # Load model and predict
        booster = xgb.Booster()
        booster.load_model(str(model_file))
        dmatrix = xgb.DMatrix(last_row, feature_names=available)
        probs = booster.predict(dmatrix)[0]

        # probs: [no_reversal_prob, peak_prob, valley_prob]
        if len(probs) >= 3:
            peak_prob = float(probs[1])
            valley_prob = float(probs[2])
        elif len(probs) == 2:
            peak_prob = float(probs[1])
            valley_prob = 0.0
        else:
            return None

        # Convert to score: valley (buy signal) = positive, peak (sell signal) = negative
        if valley_prob > peak_prob and valley_prob > 0.45:
            score = valley_prob
            confidence = valley_prob
        elif peak_prob > valley_prob and peak_prob > 0.45:
            score = -peak_prob
            confidence = peak_prob
        else:
            score = 0.0
            confidence = max(peak_prob, valley_prob)

        logger.info("ml_reversal_signal", symbol=symbol,
                    peak_prob=round(peak_prob, 4), valley_prob=round(valley_prob, 4),
                    score=round(score, 4), confidence=round(confidence, 4))

        return {"score": score, "confidence": confidence}

    except Exception as e:
        logger.warning("ml_reversal_error", symbol=symbol, error=str(e))
        return None


# ---------------------------------------------------------------------------
# Value Area strategy — cached per symbol
# ---------------------------------------------------------------------------
_value_area_cache: Dict[str, ValueAreaStrategy] = {}


def _value_area_strategy(prices: List[Dict]) -> Optional[Dict[str, float]]:
    """
    Value Area (TPO profile) mean-reversion strategy.

    Feeds candle data into a ValueAreaStrategy instance, returns the last
    signal as {score, confidence}.  The strategy is cached and accumulates
    history across calls.

    Returns None if insufficient data for a value area calculation.
    """
    if len(prices) < 25:
        return None

    # Use a single shared instance so TPO profile accumulates
    cache_key = "default"
    if cache_key not in _value_area_cache:
        _value_area_cache[cache_key] = ValueAreaStrategy(
            ValueAreaParams(
                lookback_periods=24,
                value_area_percent=0.70,
                use_time_filter=False,
            )
        )

    strategy = _value_area_cache[cache_key]
    strategy.reset()

    # Feed all candle history
    last_signal = None
    for i, p in enumerate(prices):
        tick = MarketTick(
            timestamp=datetime(2024, 1, 1) + timedelta(hours=i),
            symbol="",
            open=Decimal(str(p["open"])),
            high=Decimal(str(p["high"])),
            low=Decimal(str(p["low"])),
            close=Decimal(str(p["close"])),
            volume=int(p.get("volume", 0)),
        )
        last_signal = strategy.process_tick(tick)

    if last_signal is None or last_signal.action is None:
        return {"score": 0.0, "confidence": 0.0}

    # Map action to score
    if last_signal.action == "buy":
        score = min(last_signal.confidence, 1.0)
    elif last_signal.action == "sell":
        score = -min(last_signal.confidence, 1.0)
    else:
        score = 0.0

    return {"score": score, "confidence": last_signal.confidence}


def _combine_signals(
    strategy_signals: Dict[str, Dict[str, float]],
    regime_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Agreement-weighted voting. ML weight is capped and requires corroboration.

    Step 1: Count directional agreement (how many strategies agree on BUY vs SELL).
    Step 2: If ML disagrees with the majority of non-ML strategies, halve ML weight
            and redistribute the freed weight back to the agreeing strategies.
    Step 3: Use sqrt(confidence) to dampen overconfident models before combining.

    Inputs (per strategy entry in strategy_signals):
        score      — float in [-1.0, 1.0]; negative = SELL, positive = BUY, 0 = neutral
        confidence — float in [0.0, 1.0]; model certainty

    Args:
        strategy_signals: Dict mapping strategy name → {score, confidence}.
        regime_weights: Optional dict of {strategy_name: weight} from StrategyRouter.
            When provided, these weights replace the hardcoded defaults for every
            strategy present in the dict.  Any strategy not in regime_weights but
            still present in strategy_signals gets a weight of 0.0 (blocked).
            When None, the hardcoded defaults are used (backward-compat).

    Output:
        score      — combined directional score in [-1.0, 1.0]
        confidence — arithmetic mean of all per-strategy confidences

    Edge cases:
        - Empty dict or all weights zero → {"score": 0.0, "confidence": 0.0}
        - ML only (no non-ML strategies) → no penalty; full weight applied
        - All strategies neutral (|score| <= 0.01) → non_ml_direction = 0; no penalty
    """
    # Default weights — used when no regime filter is active.
    _default_weights = {
        "ml_reversal": 0.25,
        "value_area": 0.25,
        "momentum": 0.20,
        "mean_reversion": 0.15,
        "breakout": 0.15,
    }

    # Choose the weight source: regime-specific or default.
    if regime_weights is not None:
        weights = dict(regime_weights)
    else:
        weights = dict(_default_weights)

    # Step 1: Determine non-ML consensus direction
    non_ml_scores = []
    for name, sig in strategy_signals.items():
        if name == "ml_reversal":
            continue
        s = sig.get("score", 0.0)
        if abs(s) > 0.01:
            non_ml_scores.append(s)

    non_ml_direction = int(np.sign(np.mean(non_ml_scores))) if non_ml_scores else 0

    # Step 2: Check if ML disagrees with non-ML consensus; if so halve its weight
    # and redistribute the freed weight evenly across the non-ML strategies present.
    ml_sig = strategy_signals.get("ml_reversal", {})
    ml_direction = int(np.sign(ml_sig.get("score", 0.0)))
    ml_weight = weights.get("ml_reversal", 0.0)

    effective_weights = dict(weights)
    if ml_weight > 0 and ml_direction != 0 and non_ml_direction != 0 and ml_direction != non_ml_direction:
        freed = ml_weight * 0.5
        effective_weights["ml_reversal"] = ml_weight - freed
        redistrib = freed / max(len(non_ml_scores), 1)
        for name in strategy_signals:
            if name != "ml_reversal" and name in effective_weights:
                effective_weights[name] += redistrib

    # Step 3: Weighted combination with sqrt(confidence) dampening
    weighted_sum = 0.0
    total_weight = 0.0
    confidence_sum = 0.0
    count = 0

    for name, signal in strategy_signals.items():
        w = effective_weights.get(name, 0.0)
        if w <= 0:
            continue
        score = signal.get("score", 0.0)
        conf = signal.get("confidence", 0.0)
        effective_conf = conf ** 0.5  # Dampen overconfident models
        weighted_sum += score * w * effective_conf
        total_weight += w * effective_conf
        confidence_sum += conf
        count += 1

    if total_weight == 0.0 or count == 0:
        return {"score": 0.0, "confidence": 0.0}

    return {
        "score": weighted_sum / total_weight,
        "confidence": confidence_sum / count,
    }


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

class LiveTradingService:
    """
    Lightweight autonomous trading loop for live MT4 execution.

    Lifecycle:
        service = LiveTradingService()
        await service.start()          # begins the async loop
        await service.stop()           # graceful shutdown

    The loop:
        1. Fetch 100 H1 candles for each configured symbol
        2. Run three strategies and combine into a single signal
        3. Validate the signal against risk limits
        4. Place or dry-run a market order via MT4

    All configuration is read from environment variables at construction time.
    """

    def __init__(self) -> None:
        # Configuration from environment
        self.enabled: bool = _env_bool("LIVE_TRADING_ENABLED", False)
        self.symbols: List[str] = _env_symbols(
            "LIVE_TRADING_SYMBOLS",
            ["CrudeOIL", "USA500", "GBPJPY."],
        )
        self.interval: int = _env_int("LIVE_TRADING_INTERVAL", 300)
        self.dry_run: bool = False  # LIVE MODE — approved by Slim 2026-03-22 22:45 UTC
        self.max_open_positions: int = _env_int("MAX_OPEN_POSITIONS", 5)
        self.max_daily_loss: float = _env_float("MAX_DAILY_LOSS", 1000.0)

        # Trading mode — resolved once at init from env flags; never re-read mid-run.
        # Paper mode uses lower thresholds to generate signals for quality validation;
        # live mode requires higher conviction before real-money execution.
        # Resolution: PAPER_VALIDATION_MODE > ENABLE_PAPER_TRADING > ENABLE_LIVE_TRADING
        # If neither paper nor live env flag is set, we default to paper (safer).
        self._paper_mode: bool = _resolve_trading_mode()

        # Signal thresholds — mode-aware, loaded from config/risk.yaml at startup.
        # Paper: 0.35/0.35  (more signals → quality data for validation gate)
        # Live:  0.60/0.60  (higher conviction required for real-money execution)
        # If config/risk.yaml is absent, coded defaults above are used (warning logged).
        # RegimeRouter still enforces per-regime thresholds on top of these.
        self._signal_threshold: float
        self._min_confidence: float
        self._threshold_source: str
        self._signal_threshold, self._min_confidence, self._threshold_source = (
            _load_thresholds(self._paper_mode)
        )

        # Position caps — mode-aware, loaded from config/risk.yaml position_caps block.
        # Paper: up to _max_paper_per_symbol concurrent positions per symbol.
        #        Aggregate exposure across all open positions on a symbol ≤ 8% of balance.
        # Live:  hard cap of 1 per symbol — assert in _validate_signal.
        self._max_paper_per_symbol: int
        self._max_live_per_symbol: int
        self._max_aggregate_paper_pct: float
        self._caps_source: str
        (
            self._max_paper_per_symbol,
            self._max_live_per_symbol,
            self._max_aggregate_paper_pct,
            self._caps_source,
        ) = _load_position_caps()

        # Runtime state
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Daily P&L tracking (reset at midnight UTC)
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: Optional[str] = None  # YYYY-MM-DD

        # Post-loss cooldown: symbol → (blocked_direction, cycles_remaining)
        self._direction_cooldowns: Dict[str, Tuple[str, int]] = {}
        self._cooldown_cycles: int = 12  # 12 × 5min = 1 hour

        # Position tracking for loss detection
        self._prev_open_tickets: Dict[int, Dict] = {}

        # Recent losses: symbol → [(direction, loss_amount, timestamp), ...]
        self._recent_losses: Dict[str, List[Tuple[str, float, datetime]]] = {}

        # Stale candle fingerprint cache
        self._last_candle_fingerprint: Dict[str, str] = {}

        # Regime classification + strategy routing
        # Load tunable thresholds from config/regime.yaml when the file exists.
        # Absence of the file is safe — both classes fall back to coded defaults.
        _regime_config = (
            Path(__file__).resolve().parent.parent.parent / "config" / "regime.yaml"
        )
        _regime_config_path: Optional[str] = (
            str(_regime_config) if _regime_config.exists() else None
        )
        self._regime_classifier: RegimeClassifier = RegimeClassifier(
            config_path=_regime_config_path
        )
        self._strategy_router: StrategyRouter = StrategyRouter(
            config_path=_regime_config_path
        )

        # Shared position sizer — persisted so _last_adjusted_stop survives
        # the gap between _validate_signal() and stop/TP calculation in _process_symbol()
        self._sizer: TieredPositionSizer = TieredPositionSizer()

        # Cross-asset confirmation filter — checks related instruments agree
        from src.trading.filters.cross_asset_filter import CrossAssetFilter
        self._cross_asset_filter: CrossAssetFilter = CrossAssetFilter()

        # Stealth stop manager for trailing stops + anti-stop-hunt
        mt4_host = os.environ.get("MT4_HOST", "192.168.0.123")
        mt4_port = _env_int("MT4_COMMAND_PORT", 5555)
        stealth_yaml = Path(__file__).resolve().parent.parent.parent / "config" / "stealth_stops.yaml"
        if stealth_yaml.exists():
            self._stealth_mgr: Optional[StealthStopManager] = StealthStopManager.load_from_yaml(
                str(stealth_yaml), mt4_host=mt4_host, mt4_port=mt4_port
            )
        else:
            self._stealth_mgr = StealthStopManager(mt4_host=mt4_host, mt4_port=mt4_port)
        logger.info("stealth_stop_manager_attached", yaml_loaded=stealth_yaml.exists())

        # Paper validation gate — must collect 50 signals before live execution
        # NOTE: self._paper_mode already set above via _resolve_trading_mode().
        self._paper_validator = None
        if self._paper_mode:
            from src.services.paper_validation_service import PaperValidationService
            self._paper_validator = PaperValidationService()
            logger.info("paper_validation_mode_enabled")

        logger.info(
            "live_trading_service_created",
            enabled=self.enabled,
            symbols=self.symbols,
            interval_seconds=self.interval,
            dry_run=self.dry_run,
            max_open_positions=self.max_open_positions,
            max_daily_loss=self.max_daily_loss,
            paper_mode=self._paper_mode,
            signal_threshold=self._signal_threshold,
            min_confidence=self._min_confidence,
            threshold_source=self._threshold_source,
            max_paper_per_symbol=self._max_paper_per_symbol,
            max_live_per_symbol=self._max_live_per_symbol,
            max_aggregate_paper_pct=self._max_aggregate_paper_pct,
            caps_source=self._caps_source,
        )

    # ------------------------------------------------------------------
    # Public lifecycle API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the autonomous trading loop as a background asyncio task."""
        if not self.enabled:
            logger.warning(
                "live_trading_not_started",
                reason="LIVE_TRADING_ENABLED is not 'true'",
            )
            return

        if self._running:
            logger.warning("live_trading_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="live_trading_loop")
        logger.info(
            "live_trading_started",
            symbols=self.symbols,
            interval_seconds=self.interval,
            dry_run=self.dry_run,
        )

    def stop(self) -> None:
        """Signal the trading loop to stop after the current cycle finishes."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("live_trading_stop_requested")

    async def wait_stopped(self) -> None:
        """Await full stop of the background task (useful for graceful shutdown)."""
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("live_trading_stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """
        The main trading loop.  Runs every self.interval seconds.

        Each iteration:
        1. Reset daily P&L counter if date has rolled over.
        2. For each symbol, generate + validate + execute (or dry-run) a signal.
        3. Sleep until the next cycle.
        """
        logger.info("live_trading_loop_started")

        while self._running:
            cycle_start = time.monotonic()
            self._maybe_reset_daily_pnl()

            # Detect closed positions (loss detection for cooldown)
            await self._detect_closed_positions()

            # Check paper trade outcomes every cycle
            if self._paper_validator:
                for sym in self.symbols:
                    try:
                        latest_price = await self._get_latest_price(sym)
                        if latest_price > 0:
                            # 72-hour timeout for stale paper trades
                            for trade in self._paper_validator._open_trades.get(sym, []):
                                if not trade.resolved:
                                    age = (datetime.now(timezone.utc) - trade.entry_time).total_seconds()
                                    if age > 72 * 3600:  # 72 hours without resolution
                                        self._paper_validator._resolve(trade, trade.entry_price, "loss")
                                        logger.warning("paper_trade_timeout", symbol=sym,
                                                       age_hours=round(age / 3600, 1),
                                                       entry_price=trade.entry_price)
                            # Remove timed-out trades from open list
                            open_trades = self._paper_validator._open_trades.get(sym, [])
                            self._paper_validator._open_trades[sym] = [t for t in open_trades if not t.resolved]

                            # Check TP/SL outcomes
                            results = self._paper_validator.check_outcomes(sym, latest_price)
                            for result in results:
                                logger.info("paper_trade_resolved", symbol=sym,
                                            outcome=result.outcome, pnl=round(result.pnl, 2))
                    except Exception:
                        pass  # Don't let paper tracking crash the main loop

                status = self._paper_validator.get_validation_status()
                logger.info("paper_validation_status",
                            total=status["total_signals"],
                            wins=status["wins"], losses=status["losses"],
                            win_rate=status["win_rate"],
                            profit_factor=status["profit_factor"],
                            criteria_met=status["criteria_met"])

                if status["criteria_met"]:
                    logger.warning("PAPER_VALIDATION_PASSED",
                                   message="All criteria met. Set PAPER_VALIDATION_MODE=false to enable live execution.",
                                   total_signals=status["total_signals"],
                                   win_rate=status["win_rate"],
                                   profit_factor=status["profit_factor"])

            for symbol in self.symbols:
                try:
                    await self._process_symbol(symbol)
                except Exception:
                    # Never let one symbol crash the whole loop
                    logger.exception("symbol_cycle_error", symbol=symbol)

            # Stealth stop manager: sync positions and check trailing each cycle
            if self._stealth_mgr and not self.dry_run:
                try:
                    await self._stealth_mgr.sync_positions()
                    # Trail all monitored positions
                    for ticket, pos in list(self._stealth_mgr._monitored_positions.items()):
                        try:
                            atr = await self._stealth_mgr.get_atr(pos.symbol)
                            new_stop = self._stealth_mgr.calculate_trail_stop(
                                pos, pos.current_price, atr
                            )
                            if new_stop is not None:
                                await self._stealth_mgr.modify_stop(ticket, new_stop)
                                pos.current_stop = new_stop
                        except Exception:
                            logger.debug("stealth_trail_skip", ticket=ticket)
                except Exception:
                    logger.exception("stealth_stop_cycle_error")

            elapsed = time.monotonic() - cycle_start
            sleep_for = max(0.0, self.interval - elapsed)

            logger.info(
                "trading_cycle_complete",
                elapsed_seconds=round(elapsed, 2),
                sleep_seconds=round(sleep_for, 1),
            )

            try:
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                break

        logger.info("live_trading_loop_exited")

    # ------------------------------------------------------------------
    # Per-symbol processing
    # ------------------------------------------------------------------

    async def _process_symbol(self, symbol: str) -> None:
        """
        Full pipeline for one symbol in one cycle.

        Args:
            symbol: DB/MT4 symbol string (e.g. "CrudeOIL", "GBPJPY.")
        """
        # 1. Fetch candles (250 needed for ML features like MA_200)
        candles_raw, candle_objs = await self._fetch_candles(symbol, limit=300)
        if len(candles_raw) < 30:
            logger.warning(
                "insufficient_candles_skipping",
                symbol=symbol,
                got=len(candles_raw),
                need=30,
            )
            return

        # 1b. Stale candle check — skip if H1 data hasn't changed since last cycle
        fingerprint = "|".join(f"{c['close']:.5f}" for c in candles_raw[-5:])
        if fingerprint == self._last_candle_fingerprint.get(symbol):
            logger.debug("stale_candles_skipping", symbol=symbol)
            return
        self._last_candle_fingerprint[symbol] = fingerprint

        # 2. Classify market regime and get regime-specific strategy config.
        #    Fallback to UNKNOWN if classification raises (never crash the loop).
        try:
            regime, regime_meta = self._regime_classifier.classify(candles_raw)
        except Exception:
            logger.exception("regime_classify_error", symbol=symbol)
            regime = MarketRegime.UNKNOWN
            regime_meta = {}

        strategy_config = self._strategy_router.get_strategy_config(regime)

        logger.info(
            "regime_classified",
            symbol=symbol,
            regime=regime.value,
            allow_trading=strategy_config["allow_trading"],
            strategies=list(strategy_config["strategies"].keys()),
            signal_threshold=strategy_config["signal_threshold"],
            regime_reason=strategy_config["reason"],
            adx=regime_meta.get("adx"),
            atr_ratio=regime_meta.get("atr_ratio"),
            hurst=regime_meta.get("hurst"),
            trending_score=regime_meta.get("trending_score"),
            ranging_score=regime_meta.get("ranging_score"),
            volatile_triggers=regime_meta.get("volatile_triggers", []),
        )

        if not strategy_config["allow_trading"]:
            logger.info(
                "regime_trading_halted",
                symbol=symbol,
                regime=regime.value,
                reason=strategy_config["reason"],
            )
            return

        # 3. Generate signal — only the regime-allowed strategies are run.
        action, score, confidence, ml_confidence = self._generate_signal(
            candles_raw, symbol=symbol, strategy_config=strategy_config
        )

        current_price = float(candles_raw[-1]["close"])

        # RL Decision Log — full justification for every signal
        logger.info(
            "rl_decision_log",
            symbol=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            score=round(score, 4),
            confidence=round(confidence, 4),
            current_price=current_price,
            candle_count=len(candles_raw),
            last_5_closes=[round(float(c["close"]), 5) for c in candles_raw[-5:]],
            last_5_volumes=[float(c.get("volume", 0)) for c in candles_raw[-5:]],
            atr_14=round(self._compute_atr(symbol, candle_objs) or 0.0, 5),
            dry_run=self.dry_run,
            justification=(
                f"ML+technical consensus: score={round(score,4)}, conf={round(confidence,4)}. "
                f"Threshold: score>={self._signal_threshold}, conf>={self._min_confidence}. "
                f"{'PASSED' if abs(score) >= self._signal_threshold and confidence >= self._min_confidence else 'FILTERED'}. "
                f"Price: {current_price}, Candles: {len(candles_raw)}"
            ),
        )

        logger.info(
            "signal_generated",
            symbol=symbol,
            action=action,
            score=round(score, 4),
            confidence=round(confidence, 4),
            current_price=current_price,
        )

        if action == "HOLD":
            # HOLD diagnosis — helps understand why GBPJPY/USA500 aren't signaling
            logger.info("signal_hold_diagnosis",
                        symbol=symbol,
                        regime=regime.value if hasattr(regime, 'value') else str(regime),
                        combined_score=round(score, 4),
                        combined_confidence=round(confidence, 4),
                        threshold=strategy_config.get("signal_threshold", self._signal_threshold),
                        candle_count=len(candles_raw),
                        allow_trading=strategy_config.get("allow_trading", True))
            return

        # 3b. Trend filter — suppress counter-trend signals (e.g. ML calling every
        #     new high a "peak" SELL during a sustained rally).
        from src.trading.filters.trend_filter import TrendFilter
        suppress, tf_reason = TrendFilter().should_suppress(candles_raw, action)
        if suppress:
            logger.info(
                "trend_filter_suppressed",
                symbol=symbol,
                action=action,
                reason=tf_reason,
            )
            return

        # 3c. Cross-asset confirmation — related instruments must agree
        confirmation, ca_reason = await self._cross_asset_filter.check_confirmation(symbol, action)
        logger.info(
            "cross_asset_check",
            symbol=symbol,
            action=action,
            confirmation=round(confirmation, 3),
            reason=ca_reason,
        )
        if confirmation < -0.3:
            logger.info(
                "cross_asset_rejected",
                symbol=symbol,
                action=action,
                reason=ca_reason,
            )
            return

        # 3d. Post-loss cooldown — block same direction after stop-out
        if symbol in self._direction_cooldowns:
            blocked_dir, remaining = self._direction_cooldowns[symbol]
            if remaining > 0:
                self._direction_cooldowns[symbol] = (blocked_dir, remaining - 1)
                if action == blocked_dir:
                    logger.info(
                        "cooldown_blocked",
                        symbol=symbol,
                        action=action,
                        blocked_direction=blocked_dir,
                        cycles_remaining=remaining,
                    )
                    return
            else:
                del self._direction_cooldowns[symbol]

        # 4. Compute ATR for position sizing and stop distance
        atr = self._compute_atr(symbol, candle_objs)
        if atr is None:
            return

        # 5. Paper validation gate — record signal BEFORE sizer (validates signal quality, not account size)
        #    Paper TP: 1.5×ATR for faster resolution (live keeps original distances)
        #    Paper SL: 2×ATR (unchanged)
        if self._paper_validator and not self._paper_validator.get_validation_status()["criteria_met"]:
            paper_sl_distance = 2.0 * atr
            paper_tp_distance = 1.5 * atr  # Tighter TP for faster paper resolution
            paper_stop = current_price - paper_sl_distance if action == "BUY" else current_price + paper_sl_distance
            paper_tp = current_price + paper_tp_distance if action == "BUY" else current_price - paper_tp_distance
            self._paper_validator.record_signal(
                symbol=symbol, action=action,
                entry_price=current_price,
                stop_loss=paper_stop, take_profit=paper_tp,
                regime=regime.value if hasattr(regime, 'value') else str(regime),
                lots=0.01,
                atr=atr,
            )
            logger.info("paper_signal_recorded", symbol=symbol, action=action,
                        price=round(current_price, 5), regime=str(regime),
                        atr=round(atr, 5),
                        paper_sl_distance=round(paper_sl_distance, 5),
                        paper_tp_distance=round(paper_tp_distance, 5),
                        paper_sl=round(paper_stop, 5), paper_tp=round(paper_tp, 5))
            return  # Skip real execution — paper mode collects signal quality data

        # 6. Risk validation (tiered sizing + pyramiding)
        approved, reason, position_size_lots = await self._validate_signal(
            symbol=symbol,
            action=action,
            current_price=current_price,
            atr=atr,
            confidence=confidence,
            ml_confidence=ml_confidence,
        )

        if not approved:
            logger.info(
                "signal_rejected",
                symbol=symbol,
                action=action,
                reason=reason,
            )
            return

        # 6. Compute stop-loss and take-profit
        pip = PIP_VALUES.get(symbol, DEFAULT_PIP)
        offset = random.uniform(5, 15) * pip  # Anti-stop-hunt offset

        # Check if the position sizer tightened the stop for a small account.
        # _last_adjusted_stop is set when min-lot risk would exceed 5% at 2×ATR.
        if self._sizer._last_adjusted_stop is not None:
            stop_distance = self._sizer._last_adjusted_stop
            tp_distance = stop_distance * 1.5  # Preserve R:R with tighter stop
            self._sizer._last_adjusted_stop = None
            logger.info(
                "using_adjusted_stop",
                symbol=symbol,
                stop_distance=round(stop_distance, 4),
                tp_distance=round(tp_distance, 4),
            )
        else:
            stop_distance = 2.0 * atr
            tp_distance = 3.0 * atr

        if action == "BUY":
            stop_loss = current_price - stop_distance - offset
            take_profit = current_price + tp_distance
        else:
            stop_loss = current_price + stop_distance + offset
            take_profit = current_price - tp_distance

        # RL Execution Log — full trade justification for reinforcement learning
        logger.info(
            "rl_trade_decision",
            symbol=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            lots=position_size_lots,
            entry_price=current_price,
            stop_loss=round(stop_loss, 5),
            take_profit=round(take_profit, 5),
            atr=round(atr, 5),
            risk_reward=round(tp_distance / stop_distance, 2) if stop_distance > 0 else 0,
            stop_distance_atr=round(stop_distance / atr, 2) if atr > 0 else 0,
            tp_distance_atr=round(tp_distance / atr, 2) if atr > 0 else 0,
            anti_hunt_offset=round(offset, 5),
            signal_score=round(score, 4),
            signal_confidence=round(confidence, 4),
            dry_run=self.dry_run,
            daily_pnl=round(self._daily_pnl, 2),
            justification=(
                f"{'LIVE' if not self.dry_run else 'DRY-RUN'} {action} {position_size_lots} lots {symbol} @ {current_price}. "
                f"SL={round(stop_loss,2)} ({round(stop_distance,2)} from entry, "
                f"{round(stop_distance/atr,2) if atr > 0 else '?'}xATR+offset), "
                f"TP={round(take_profit,2)} ({round(tp_distance,2)} from entry, "
                f"{round(tp_distance/atr,2) if atr > 0 else '?'}xATR). "
                f"R:R={round(tp_distance/stop_distance,2) if stop_distance > 0 else 0}. "
                f"ML+technical score={round(score,4)}, confidence={round(confidence,4)}. "
                f"Daily P&L so far: ${round(self._daily_pnl,2)}"
            ),
        )

        # 7. Execute or dry-run (paper gate already checked at step 5)
        await self._execute_or_dryrun(
            symbol=symbol,
            action=action,
            lots=position_size_lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_price=current_price,
            atr=atr,
        )

    # ------------------------------------------------------------------
    # Candle fetch
    # ------------------------------------------------------------------

    async def _fetch_candles(
        self, symbol: str, limit: int = 100
    ) -> Tuple[List[Dict], List[Candle]]:
        """
        Fetch the latest H1 candles for a symbol from PostgreSQL.

        Args:
            symbol: Trading symbol string.
            limit:  Maximum number of candles to retrieve (newest-first from DB).

        Returns:
            Tuple of:
              - price_dicts: List of {"open", "high", "low", "close", "volume"} in
                             chronological order (oldest first), suitable for strategies.
              - candle_objs: List of Candle dataclass instances in the same order,
                             suitable for calculate_atr_wilder().

        DB note: get_latest_ticks() returns newest-first, so we reverse the result.
        All price fields in the DB are stored as Decimal strings; cast to float here.
        """
        from src.api.dependencies import get_db_context

        db_sym = _db_symbol(symbol)
        async with get_db_context() as db:
            repo = MarketDataRepository(db)
            rows = await repo.get_latest_ticks(symbol=db_sym, timeframe="H1", limit=limit)

        # Reverse: DB returns newest-first; strategies need oldest-first
        rows = list(reversed(rows))

        price_dicts: List[Dict] = []
        candle_objs: List[Candle] = []

        for row in rows:
            open_ = float(row.open)
            high_ = float(row.high)
            low_ = float(row.low)
            close_ = float(row.last)  # MarketData stores close as `last`
            vol_ = float(row.volume) if row.volume is not None else 0.0

            price_dicts.append({
                "open": open_,
                "high": high_,
                "low": low_,
                "close": close_,
                "volume": vol_,
            })
            candle_objs.append(
                Candle(
                    timestamp=row.time if isinstance(row.time, datetime) else datetime.utcnow(),
                    open=open_,
                    high=high_,
                    low=low_,
                    close=close_,
                    volume=vol_,
                )
            )

        return price_dicts, candle_objs

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def _generate_signal(
        self,
        prices: List[Dict],
        symbol: str = "CrudeOIL",
        strategy_config: Optional[Dict] = None,
    ) -> Tuple[str, float, float, float]:
        """
        Run regime-allowed strategies and combine their votes.

        Args:
            prices: Chronological list of OHLCV price dicts (oldest first).
                    Must have at least 30 entries for all strategies to run.
            symbol: Symbol name used for ML model lookup.
            strategy_config: Optional dict from StrategyRouter.get_strategy_config().
                If provided, only strategies listed in strategy_config["strategies"]
                are run and their weights are used in place of the defaults in
                _combine_signals.  The signal threshold is taken from
                strategy_config["signal_threshold"] instead of
                self._signal_threshold.
                If None (backward-compat), all strategies run with default weights
                and self._signal_threshold is used.

        Returns:
            Tuple of (action, score, confidence, ml_confidence):
              - action:         "BUY", "SELL", or "HOLD"
              - score:          Combined weighted score in [-1.0, 1.0]
              - confidence:     Average blended confidence in [0.0, 1.0]
              - ml_confidence:  Raw ML model confidence (for pyramid decisions)

        Signals are only emitted when abs(score) >= threshold AND
        confidence >= self._min_confidence.
        """
        # Determine which strategies to run and their weights.
        # Composition:
        #   - RegimeRouter decides which strategies are *allowed* for this regime.
        #   - SYMBOL_WEIGHTS overrides weights within the allowed set per symbol
        #     (so CrudeOIL, USA500, GBPJPY., #TSLA each get their own mixture).
        # Final allowed = SYMBOL_WEIGHTS ∩ regime_allowed, renormalized to sum=1.
        if strategy_config is not None:
            regime_allowed: Optional[Dict[str, float]] = strategy_config.get("strategies")
            threshold = float(strategy_config.get("signal_threshold", self._signal_threshold))
        else:
            regime_allowed = None
            threshold = self._signal_threshold

        symbol_w = _symbol_weights(symbol)

        if symbol_w is not None and regime_allowed is not None:
            # Intersect so we never run e.g. mean_reversion in a strong trend regime
            # even if SYMBOL_WEIGHTS lists it.
            overlap = {s: w for s, w in symbol_w.items() if s in regime_allowed}
            total = sum(overlap.values())
            if total > 0:
                allowed: Optional[Dict[str, float]] = {k: v / total for k, v in overlap.items()}
                logger.info(
                    "symbol_weights_applied",
                    symbol=symbol,
                    weights={k: round(v, 3) for k, v in allowed.items()},
                    regime_allowed=list(regime_allowed.keys()),
                    source="SYMBOL_WEIGHTS_x_regime",
                )
            else:
                # No overlap — fall back to regime weights so we still emit something.
                allowed = regime_allowed
                logger.info(
                    "symbol_weights_no_overlap",
                    symbol=symbol,
                    symbol_weights=list(symbol_w.keys()),
                    regime_allowed=list(regime_allowed.keys()),
                    fallback="regime_weights",
                )
        elif symbol_w is not None:
            allowed = symbol_w
            logger.info(
                "symbol_weights_applied",
                symbol=symbol,
                weights={k: round(v, 3) for k, v in allowed.items()},
                source="SYMBOL_WEIGHTS_only",
            )
        else:
            allowed = regime_allowed
            logger.info(
                "symbol_weights_default",
                symbol=symbol,
                note="no SYMBOL_WEIGHTS entry; using regime weights",
                regime_weights=(
                    list(regime_allowed.keys()) if regime_allowed else None
                ),
            )

        def _is_allowed(name: str) -> bool:
            """Return True when the strategy is not blocked by the regime config."""
            if allowed is None:
                return True
            return name in allowed

        signals: Dict[str, Dict[str, float]] = {}
        ml_confidence = 0.0

        # ML Reversal — highest priority, uses trained XGBoost model
        if _is_allowed("ml_reversal"):
            ml_signal = _ml_reversal_strategy(prices, symbol)
            if ml_signal is not None:
                signals["ml_reversal"] = ml_signal
                ml_confidence = ml_signal.get("confidence", 0.0)

        # Value Area — TPO profile mean-reversion (needs 25+ bars)
        if _is_allowed("value_area"):
            va_signal = _value_area_strategy(prices)
            if va_signal is not None:
                signals["value_area"] = va_signal

        # Momentum needs at least 30 bars (30-period MA)
        if _is_allowed("momentum"):
            if len(prices) >= 30:
                signals["momentum"] = _momentum_strategy(prices)

        # Trend following — EMA20/EMA50 alignment, fires during sustained trends
        if _is_allowed("trend_following"):
            if len(prices) >= 50:
                tf_sig = _trend_following_strategy(prices)
                if tf_sig is not None:
                    signals["trend_following"] = tf_sig

        # Mean reversion needs 20 bars (Bollinger Bands)
        if _is_allowed("mean_reversion"):
            if len(prices) >= 20:
                signals["mean_reversion"] = _mean_reversion_strategy(prices)

        # Breakout needs 21 bars (20-period range + current)
        if _is_allowed("breakout"):
            if len(prices) >= 21:
                signals["breakout"] = _breakout_strategy(prices)

        if not signals:
            return "HOLD", 0.0, 0.0, 0.0

        # Diagnostic logging: per-strategy raw output
        for name, result in signals.items():
            logger.info("strategy_raw_output",
                        symbol=symbol, strategy=name,
                        score=round(result.get("score", 0), 4),
                        confidence=round(result.get("confidence", 0), 4))

        combined = _combine_signals(signals, regime_weights=allowed)
        score = combined["score"]
        confidence = combined["confidence"]

        passed = abs(score) >= threshold and confidence >= self._min_confidence
        logger.info("signal_combine_result",
                    symbol=symbol, combined_score=round(score, 4),
                    combined_confidence=round(confidence, 4),
                    threshold=threshold, passed=passed,
                    strategies_active=list(signals.keys()))

        if not passed:
            return "HOLD", score, confidence, ml_confidence

        action = "BUY" if score > 0 else "SELL"
        return action, score, confidence, ml_confidence

    # ------------------------------------------------------------------
    # ATR calculation
    # ------------------------------------------------------------------

    def _compute_atr(self, symbol: str, candle_objs: List[Candle]) -> Optional[float]:
        """
        Compute Wilder's ATR(14) from the provided candles.

        Args:
            symbol:      Symbol name (used for error logging only).
            candle_objs: Chronological list of Candle instances (oldest first).
                         Must have at least 15 entries (14 periods + 1 seed).

        Returns:
            ATR value as a float, or None if data is insufficient.
            Never returns a hardcoded default — InsufficientDataError is caught
            and logged as a warning, and None propagates to the caller which
            will skip the symbol for this cycle.
        """
        try:
            atr = calculate_atr_wilder(candle_objs, period=14)
            if atr is None:
                logger.warning("atr_none_returned", symbol=symbol, candles=len(candle_objs))
                return None
            logger.debug("atr_computed", symbol=symbol, atr=round(atr, 5))
            return atr
        except InsufficientDataError as e:
            logger.warning(
                "atr_insufficient_data",
                symbol=symbol,
                got=e.got,
                need=e.need,
            )
            return None

    # ------------------------------------------------------------------
    # Risk validation
    # ------------------------------------------------------------------

    async def _validate_signal(
        self,
        symbol: str,
        action: str,
        current_price: float,
        atr: float,
        confidence: float = 0.5,
        ml_confidence: float = 0.0,
    ) -> Tuple[bool, str, float]:
        """
        Validate a signal against risk rules and compute position size in lots.

        Mode-aware position caps:
          paper mode — up to _max_paper_per_symbol (5) concurrent positions per
                       symbol, each independently obeying the 2% account-risk rule.
                       Aggregate risk across all open positions on a symbol must not
                       exceed _max_aggregate_paper_pct (8%) of account balance.
                       A 6th signal is rejected with reason
                       "paper_concurrent_cap_reached(5)" and logged.
          live mode  — hard cap of 1 per symbol (asserted, never relaxed).
                       Pyramid at same-direction + 95%+ ML confidence still allowed.

        Direction-conflict semantics are preserved in both modes: if any open
        position on the symbol is in the opposing direction, the signal is
        rejected with "opposing_direction".

        Checks (in order):
          1. Daily loss limit (5% of account) not breached.
          2. Global open position count below max.
          3. Mode-aware per-symbol cap check.
          4. Aggregate exposure cap (paper only).
          5. Per-position 2% account-risk rule (ATR check).
          6. Tiered position sizing based on ML confidence.
          7. Margin level validation (200% floor).

        Args:
            symbol:        Trading symbol.
            action:        "BUY" or "SELL".
            current_price: Current ask/bid price.
            atr:           Wilder ATR(14); stop distance = 2 * ATR.
            confidence:    ML signal confidence (0.0 to 1.0).

        Returns:
            Tuple of (approved, rejection_reason, position_size_lots).
        """
        sizer = self._sizer

        # 1. Daily loss limit (5% of account)
        balance = await self._get_account_balance()
        if sizer.check_daily_loss_halt(self._daily_pnl, balance):
            return False, f"daily_loss_halt (pnl={self._daily_pnl:.2f}, limit=5%)", 0.0

        if balance <= 0:
            return False, "insufficient_balance", 0.0

        # 1b. Post-loss direction block (1-hour cooldown)
        db_symbol = symbol.rstrip(".")
        if db_symbol in self._recent_losses:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            recent = [(d, p, t) for d, p, t in self._recent_losses[db_symbol] if t > cutoff]
            self._recent_losses[db_symbol] = recent
            for loss_dir, loss_amt, loss_time in recent:
                if loss_dir.upper() == action:
                    return False, f"post_loss_cooldown ({loss_dir} lost ${abs(loss_amt):.2f} at {loss_time.strftime('%H:%M')})", 0.0

        # 2. Open position count
        open_count, open_symbols, open_positions = await self._get_open_position_details()
        if open_count >= self.max_open_positions:
            return (
                False,
                f"max_open_positions_exceeded ({open_count}/{self.max_open_positions})",
                0.0,
            )

        # 3. Mode-aware per-symbol cap check.
        #
        # Collect positions for this symbol (both direction and lot-size matters).
        db_symbol = symbol.rstrip(".")
        symbol_positions = [
            pos for pos in open_positions
            if pos.get("symbol", "").rstrip(".") == db_symbol
            or pos.get("symbol") == symbol
        ]
        symbol_count = len(symbol_positions)
        existing_lots = sum(float(pos.get("lots", 0)) for pos in symbol_positions)

        # Direction-conflict check — applies in BOTH modes.
        # If any open position on this symbol is in the opposing direction, reject.
        opposing_positions = [
            pos for pos in symbol_positions
            if pos.get("type", "").upper() != action
        ]
        if opposing_positions:
            opp_dir = opposing_positions[0].get("type", "").upper()
            return (
                False,
                f"opposing_direction (existing={opp_dir}, signal={action})",
                0.0,
            )

        # Per-mode concurrency cap.
        if self._paper_mode:
            # Safety: live cap must be 1 — verified at init, double-check here.
            assert self._max_live_per_symbol == 1, (
                "live per-symbol cap must always be 1 — invariant violated"
            )
            max_per_symbol = self._max_paper_per_symbol
            if symbol_count >= max_per_symbol:
                logger.info(
                    "paper_concurrent_cap_reached",
                    symbol=symbol,
                    open_count=symbol_count,
                    cap=max_per_symbol,
                    action=action,
                    reason="logged_not_executed",
                )
                return (
                    False,
                    f"paper_concurrent_cap_reached({max_per_symbol})",
                    0.0,
                )
        else:
            # Live mode: hard cap of 1 per symbol.
            assert self._max_live_per_symbol == 1, (
                "live per-symbol cap must always be 1 — invariant violated"
            )
            if symbol_count >= self._max_live_per_symbol:
                # In live mode we support pyramiding: same direction + 95%+ conf.
                if symbol_count > 0:
                    existing_direction = symbol_positions[0].get("type", "").upper()
                    pyramid_conf = ml_confidence if ml_confidence > 0 else confidence
                    if action == existing_direction and pyramid_conf >= 0.95:
                        if existing_lots + MIN_LOTS <= sizer.max_total_lots:
                            logger.info(
                                "pyramid_eligible",
                                symbol=symbol,
                                action=action,
                                existing_lots=existing_lots,
                                confidence=round(confidence, 4),
                            )
                            # Fall through to sizing below
                        else:
                            return (
                                False,
                                f"pyramid_max_lots_reached ({existing_lots:.2f}/{sizer.max_total_lots})",
                                0.0,
                            )
                    else:
                        return (
                            False,
                            f"position_exists_low_confidence (ml={pyramid_conf:.2f} < 0.95)",
                            0.0,
                        )

        # 4. Aggregate exposure cap (paper mode only).
        #
        # Aggregate risk = sum of (lots × 2×ATR × contract_size) across all open
        # positions on this symbol, expressed as a percentage of account balance.
        # Uses the current ATR (same instrument, same timeframe — valid approximation;
        # ATR moves slowly relative to hourly cycles).  No synthetic estimates —
        # existing_lots comes directly from the live MT4 position list above.
        if self._paper_mode and symbol_count > 0:
            contract_size = float(CONTRACT_SIZES.get(symbol, 1000))
            # Risk per lot = 2×ATR × contract_size (stop distance × contract value)
            risk_per_lot = 2.0 * atr * contract_size
            existing_risk_usd = existing_lots * risk_per_lot
            aggregate_pct = (existing_risk_usd / balance) * 100.0 if balance > 0 else 0.0

            # Risk that the new position would add
            new_position_lots = sizer.calculate_lot_size(
                confidence=min(ml_confidence if ml_confidence > 0 else confidence, 0.70),
                account_balance=balance,
                symbol=symbol,
                atr=atr,
                existing_lots=existing_lots,
            )
            projected_risk_usd = existing_risk_usd + new_position_lots * risk_per_lot
            projected_pct = (projected_risk_usd / balance) * 100.0 if balance > 0 else 0.0

            logger.info(
                "paper_aggregate_exposure_check",
                symbol=symbol,
                open_positions_on_symbol=symbol_count,
                existing_lots=round(existing_lots, 4),
                existing_risk_usd=round(existing_risk_usd, 2),
                existing_aggregate_pct=round(aggregate_pct, 2),
                projected_pct=round(projected_pct, 2),
                cap_pct=self._max_aggregate_paper_pct,
            )

            if projected_pct > self._max_aggregate_paper_pct:
                return (
                    False,
                    f"aggregate_paper_exposure_capped "
                    f"(projected={projected_pct:.1f}% > cap={self._max_aggregate_paper_pct:.1f}%)",
                    0.0,
                )

        # 5. ATR check — per-position 2% rule depends on valid ATR
        if atr <= 0:
            return False, "zero_atr", 0.0

        # 6. Tiered position sizing based on ML confidence (raw, not blended)
        # Cap ML confidence for sizing — model probability != model accuracy
        # Until model F1 > 0.50, cap at 0.70 to prevent top-tier abuse
        sizing_conf = ml_confidence if ml_confidence > 0 else confidence
        sizing_conf = min(sizing_conf, 0.70)
        position_size_lots = sizer.calculate_lot_size(
            confidence=sizing_conf,
            account_balance=balance,
            symbol=symbol,
            atr=atr,
            existing_lots=existing_lots,
        )

        if position_size_lots <= 0:
            return False, "lot_size_zero_after_caps", 0.0

        # 7. Margin validation (200% floor)
        equity = balance + self._daily_pnl  # Approximate current equity
        account_info = await self._get_account_info()
        current_margin = float(account_info.get("margin", 0))

        margin_ok, projected_level = sizer.validate_margin_level(
            lots=position_size_lots,
            symbol=symbol,
            equity=float(account_info.get("equity", equity)),
            current_margin=current_margin,
        )

        if not margin_ok:
            return False, f"margin_level_below_floor ({projected_level:.0f}% < {sizer.margin_floor_pct}%)", 0.0

        logger.info(
            "signal_approved",
            symbol=symbol,
            action=action,
            confidence=round(confidence, 4),
            balance=round(balance, 2),
            lots=position_size_lots,
            existing_lots=existing_lots,
            open_positions_on_symbol=symbol_count,
            paper_mode=self._paper_mode,
            projected_margin_level=round(projected_level, 1),
        )
        return True, "", position_size_lots

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def _execute_or_dryrun(
        self,
        symbol: str,
        action: str,
        lots: float,
        stop_loss: float,
        take_profit: float,
        current_price: float,
        atr: float,
    ) -> None:
        """
        Place a real market order via MT4, or log a dry-run record.

        In dry-run mode this method only logs what it WOULD do.
        In live mode it calls mt4_client.create_instant_order() with the
        computed stop_loss and take_profit.

        Args:
            symbol:       Trading symbol.
            action:       "BUY" or "SELL".
            lots:         Position size in lots (already 2%-capped).
            stop_loss:    Computed stop-loss price (anti-stop-hunt offset applied).
            take_profit:  Computed take-profit price (3 × ATR from entry).
            current_price: Latest close price (informational).
            atr:          Wilder ATR(14) used in stop/TP calculation.
        """
        log_context = dict(
            symbol=symbol,
            action=action,
            lots=lots,
            current_price=round(current_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profit=round(take_profit, 5),
            atr=round(atr, 5),
            dry_run=self.dry_run,
        )

        if self.dry_run:
            logger.info("dry_run_order", **log_context)
            return

        # Live execution
        try:
            from src.services.mt4_sync_service import get_mt4_sync_service

            sync_service = get_mt4_sync_service()

            if sync_service.mt4_client is None or not sync_service.mt4_client.is_connected():
                logger.error(
                    "mt4_client_not_connected",
                    symbol=symbol,
                    hint="MT4SyncService must be started before live trading",
                )
                return

            mt4_client = sync_service.mt4_client

            response = await mt4_client.create_instant_order(
                symbol=symbol,
                direction=action,  # "BUY" or "SELL"
                volume=Decimal(str(lots)),
                stop_loss=Decimal(str(round(stop_loss, 5))),
                take_profit=Decimal(str(round(take_profit, 5))),
                comment=f"live_trading_svc atr={round(atr, 4)}",
            )

            if response and response.success:
                ticket = response.ticket_number or "?"
                logger.info(
                    "order_placed",
                    ticket=ticket,
                    **log_context,
                )
            else:
                error = response.error_message if response else "no response"
                logger.error(
                    "order_failed",
                    error=error,
                    **log_context,
                )

        except Exception:
            logger.exception("order_execution_error", **log_context)

    # ------------------------------------------------------------------
    # MT4 account / position helpers
    # ------------------------------------------------------------------

    async def _get_account_balance(self) -> float:
        """
        Query the most recent account balance from the account_info table in PostgreSQL.

        Returns:
            Balance as float, or 0.0 if no record is found.

        This avoids a live ZMQ round-trip for the balance check;
        the MT4SyncService already keeps account_info current.
        """
        try:
            from src.api.dependencies import get_db_context
            from sqlalchemy import text as sa_text

            async with get_db_context() as db:
                result = await db.execute(
                    sa_text(
                        "SELECT balance FROM account_info ORDER BY time DESC LIMIT 1"
                    )
                )
                row = result.first()
                if row:
                    return float(row[0])
        except Exception:
            logger.exception("get_account_balance_error")
        return 0.0

    async def _get_open_position_info(self) -> Tuple[int, List[str]]:
        """
        Fetch the count and symbol list of currently open live positions.

        Returns:
            Tuple of (count, list_of_symbols) from the open_positions table
            where simulation=false.  Symbol names are normalised (trailing dot
            stripped) so the caller can match against either form.
        """
        try:
            from src.api.dependencies import get_db_context
            from sqlalchemy import text as sa_text

            async with get_db_context() as db:
                result = await db.execute(
                    sa_text(
                        "SELECT symbol FROM open_positions WHERE simulation = false"
                    )
                )
                rows = result.fetchall()

            symbols = [row[0].rstrip(".") if row[0] else "" for row in rows]
            return len(symbols), symbols

        except Exception:
            logger.exception("get_open_positions_error")
            return 0, []

    async def _detect_closed_positions(self) -> None:
        """
        Compare current open positions to previous cycle's snapshot.
        Detect stop-outs and set cooldowns to block same-direction re-entry.
        """
        try:
            _, _, current_positions = await self._get_open_position_details()
            current_tickets = {p.get("ticket"): p for p in current_positions}

            for ticket, prev_pos in self._prev_open_tickets.items():
                if ticket not in current_tickets:
                    sym = prev_pos.get("symbol", "").rstrip(".")
                    direction = prev_pos.get("type", "").upper()
                    cur_price = float(prev_pos.get("curPrice", 0))
                    open_price = float(prev_pos.get("openPrice", 0))

                    # Estimate P&L direction (negative = loss)
                    if direction == "SELL":
                        est_pnl = open_price - cur_price
                    else:
                        est_pnl = cur_price - open_price

                    if est_pnl < 0:  # Was a loss
                        self._direction_cooldowns[sym] = (direction, self._cooldown_cycles)
                        if sym not in self._recent_losses:
                            self._recent_losses[sym] = []
                        self._recent_losses[sym].append(
                            (direction, est_pnl, datetime.now(timezone.utc))
                        )
                        self._daily_pnl += est_pnl
                        logger.warning(
                            "stop_loss_detected",
                            symbol=sym,
                            direction=direction,
                            ticket=ticket,
                            est_pnl=round(est_pnl, 2),
                            cooldown_cycles=self._cooldown_cycles,
                        )

            self._prev_open_tickets = current_tickets
        except Exception:
            logger.exception("detect_closed_positions_error")

    async def _get_open_position_details(self) -> Tuple[int, List[str], List[Dict]]:
        """
        Fetch open positions with full details (symbol, type, lots) for pyramid checks.

        Returns:
            Tuple of (count, symbol_list, position_dicts).
            Position dicts have keys: symbol, type, lots, price.
        """
        try:
            from src.services.mt4_sync_service import get_mt4_sync_service

            sync = get_mt4_sync_service()
            if sync.mt4_client and sync.mt4_client.is_connected():
                resp = await sync.mt4_client.get_open_positions()
                positions = resp.get("positions", []) if isinstance(resp, dict) else []
                symbols = [p.get("symbol", "").rstrip(".") for p in positions]
                return len(positions), symbols, positions
        except Exception:
            logger.exception("get_open_position_details_error")

        # Fallback to DB
        count, symbols = await self._get_open_position_info()
        return count, symbols, []

    async def _get_account_info(self) -> Dict:
        """
        Get account info (balance, equity, margin, freeMargin) from DB.

        Returns dict with keys: balance, equity, margin, freeMargin, marginLevel.
        """
        try:
            from src.api.dependencies import get_db_context
            from sqlalchemy import text as sa_text

            async with get_db_context() as db:
                result = await db.execute(
                    sa_text(
                        "SELECT balance, equity, margin, free_margin "
                        "FROM account_info ORDER BY time DESC LIMIT 1"
                    )
                )
                row = result.first()
                if row:
                    balance = float(row[0])
                    equity = float(row[1])
                    margin = float(row[2])
                    free_margin = float(row[3])
                    margin_level = (equity / margin * 100.0) if margin > 0 else 0.0
                    return {
                        "balance": balance,
                        "equity": equity,
                        "margin": margin,
                        "freeMargin": free_margin,
                        "marginLevel": margin_level,
                    }
        except Exception:
            logger.exception("get_account_info_error")

        return {"balance": 0, "equity": 0, "margin": 0, "freeMargin": 0, "marginLevel": 0}

    async def _get_latest_price(self, symbol: str) -> float:
        """Get latest close price for a symbol from DB."""
        try:
            from src.api.dependencies import get_db_context
            from sqlalchemy import text as sa_text
            db_sym = symbol.rstrip(".")
            async with get_db_context() as db:
                result = await db.execute(
                    sa_text("SELECT last FROM market_data WHERE symbol = :sym ORDER BY time DESC LIMIT 1"),
                    {"sym": db_sym}
                )
                row = result.first()
                if row:
                    return float(row[0])
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # Daily P&L reset
    # ------------------------------------------------------------------

    def _maybe_reset_daily_pnl(self) -> None:
        """
        Reset the daily P&L counter if the UTC date has rolled over since the
        last cycle.  Called at the start of every loop iteration.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_pnl_date != today:
            if self._daily_pnl_date is not None:
                logger.info(
                    "daily_pnl_reset",
                    previous_date=self._daily_pnl_date,
                    final_pnl=round(self._daily_pnl, 2),
                )
            self._daily_pnl = 0.0
            self._daily_pnl_date = today

    def record_closed_trade_pnl(self, pnl: float) -> None:
        """
        Update the in-memory daily P&L tracker after a trade closes.

        Args:
            pnl: Realized profit (positive) or loss (negative) in account currency.

        Call this from external code (e.g. the MT4 sync archiving path) so the
        daily-loss guard stays accurate during the current session.
        """
        self._daily_pnl += pnl
        logger.info(
            "daily_pnl_updated",
            trade_pnl=round(pnl, 2),
            session_total=round(self._daily_pnl, 2),
        )


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_live_trading_service: Optional[LiveTradingService] = None


def get_live_trading_service() -> LiveTradingService:
    """
    Get or create the global LiveTradingService singleton.

    Configuration is read from environment variables on first call.

    Returns:
        The shared LiveTradingService instance.
    """
    global _live_trading_service
    if _live_trading_service is None:
        _live_trading_service = LiveTradingService()
    return _live_trading_service
