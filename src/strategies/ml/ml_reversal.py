"""
ML Reversal Strategy

Uses a trained XGBoost or LSTM reversal classifier to generate buy/sell
signals based on predicted peaks and valleys.

On each tick the strategy:
  1. Buffers OHLCV into a deque
  2. Builds a DataFrame → compute_features_from_ohlcv()
  3. Runs model.predict_proba() → class + confidence
  4. Maps: valley → buy, peak → sell, neither → hold
  5. ATR-based stop loss (2× ATR + random offset) and take profit (3× ATR)

Model is loaded lazily on the first process_tick() call from disk:
  - XGBoost: models/reversal_classifier/{symbol}_{timeframe}/model.json
  - LSTM: models/reversal_classifier/{symbol}_{timeframe}/lstm_model.pt

Author: Claude (RiseTrader Phase 4 - ML Pipeline Refactor)
"""
import json
import logging
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Deque, Dict, List, Optional

import numpy as np
import pandas as pd

from src.services.market_tick import MarketTick
from src.ml.features.reversal_features import compute_features_from_ohlcv, get_feature_columns

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models" / "reversal_classifier"


@dataclass
class MLReversalParams:
    """ML Reversal strategy parameters."""
    # Model location
    model_dir: str = ""  # Override at init; defaults to MODELS_DIR/{symbol}_{timeframe}
    model_type: str = "xgboost"  # "xgboost" or "lstm"

    # ATR-based risk management
    atr_period: int = 14
    atr_stop_multiplier: float = 2.0
    atr_tp_multiplier: float = 3.0

    # Anti-stop-hunt random offset (pips)
    min_offset_pips: int = 5
    max_offset_pips: int = 15

    # Confidence threshold — only act when prediction confidence >= this
    min_confidence: float = 0.55

    # Position sizing (fixed for backtest; live path uses RiskManagerAgent)
    quantity: Decimal = Decimal("1.0")

    # Lookback bars for feature computation buffer
    lookback_bars: int = 250  # Need 200 for MA_200 + 50 extra for derived features


@dataclass
class MLReversalSignal:
    """Signal emitted by MLReversalStrategy."""
    action: Optional[str]  # "buy", "sell", "close", or None
    quantity: Decimal
    confidence: float
    reason: str
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


class MLReversalStrategy:
    """
    ML-powered reversal detection strategy.

    Loads a trained classifier and uses it to predict reversal points
    from real-time tick data, generating buy/sell signals.
    """

    def __init__(self, params: MLReversalParams, symbol: str = "CrudeOIL", timeframe: str = "H1"):
        self.params = params
        self.symbol = symbol
        self.timeframe = timeframe

        # Tick buffer — stores (time, open, high, low, close, volume) tuples
        self._buffer: Deque[Dict] = deque(maxlen=params.lookback_bars + 50)

        # Model (lazy loaded)
        self._model = None
        self._feature_names: List[str] = []
        self._model_loaded = False

        # Position state
        self.has_position = False
        self.entry_price: Optional[Decimal] = None
        self._position_direction: Optional[str] = None  # "buy" or "sell"

    def process_tick(self, tick: MarketTick) -> MLReversalSignal:
        """
        Process a market tick and generate a trading signal.

        The model is loaded lazily on the first call.
        """
        # Buffer the tick as OHLCV row
        self._buffer.append({
            "time": tick.timestamp,
            "open": float(tick.open),
            "high": float(tick.high),
            "low": float(tick.low),
            "close": float(tick.close),
            "volume": int(tick.volume) if tick.volume else 0,
        })

        # Need enough bars for indicator warm-up (200 for MA_200 + 50 for derived)
        if len(self._buffer) < self.params.lookback_bars:
            return MLReversalSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Warming up: {len(self._buffer)}/{self.params.lookback_bars}",
            )

        # Lazy load model
        if not self._model_loaded:
            self._load_model()
            if self._model is None:
                return MLReversalSignal(
                    action=None,
                    quantity=Decimal("0.0"),
                    confidence=0.0,
                    reason="Model not available",
                )

        # Build features from buffer
        predicted_class, confidence = self._predict(tick)

        if predicted_class is None:
            return MLReversalSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Prediction failed",
            )

        # Map predictions to actions
        # Classes: -1 = valley (buy opportunity), 0 = neither, 1 = peak (sell opportunity)
        current_atr = self._get_current_atr()

        if not self.has_position:
            if predicted_class == -1 and confidence >= self.params.min_confidence:
                # Valley predicted → BUY
                offset = Decimal(str(random.randint(self.params.min_offset_pips, self.params.max_offset_pips))) * Decimal("0.01")
                sl = tick.close - Decimal(str(current_atr * self.params.atr_stop_multiplier)) - offset
                tp = tick.close + Decimal(str(current_atr * self.params.atr_tp_multiplier))
                self.has_position = True
                self.entry_price = tick.close
                self._position_direction = "buy"
                return MLReversalSignal(
                    action="buy",
                    quantity=self.params.quantity,
                    confidence=confidence,
                    reason=f"Valley predicted (conf={confidence:.3f}, ATR={current_atr:.4f})",
                    stop_loss=sl,
                    take_profit=tp,
                )

            elif predicted_class == 1 and confidence >= self.params.min_confidence:
                # Peak predicted → SELL
                offset = Decimal(str(random.randint(self.params.min_offset_pips, self.params.max_offset_pips))) * Decimal("0.01")
                sl = tick.close + Decimal(str(current_atr * self.params.atr_stop_multiplier)) + offset
                tp = tick.close - Decimal(str(current_atr * self.params.atr_tp_multiplier))
                self.has_position = True
                self.entry_price = tick.close
                self._position_direction = "sell"
                return MLReversalSignal(
                    action="sell",
                    quantity=self.params.quantity,
                    confidence=confidence,
                    reason=f"Peak predicted (conf={confidence:.3f}, ATR={current_atr:.4f})",
                    stop_loss=sl,
                    take_profit=tp,
                )

        else:
            # Close on opposite signal
            if self._position_direction == "buy" and predicted_class == 1 and confidence >= self.params.min_confidence:
                self.has_position = False
                self.entry_price = None
                self._position_direction = None
                return MLReversalSignal(
                    action="close",
                    quantity=self.params.quantity,
                    confidence=confidence,
                    reason=f"Peak predicted, closing long (conf={confidence:.3f})",
                )

            elif self._position_direction == "sell" and predicted_class == -1 and confidence >= self.params.min_confidence:
                self.has_position = False
                self.entry_price = None
                self._position_direction = None
                return MLReversalSignal(
                    action="close",
                    quantity=self.params.quantity,
                    confidence=confidence,
                    reason=f"Valley predicted, closing short (conf={confidence:.3f})",
                )

        return MLReversalSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=confidence,
            reason=f"Hold (class={predicted_class}, conf={confidence:.3f})",
        )

    def _load_model(self) -> None:
        """Load model and feature names from disk."""
        model_dir = Path(self.params.model_dir) if self.params.model_dir else MODELS_DIR / f"{self.symbol}_{self.timeframe}"
        self._model_loaded = True  # Don't retry on failure

        if self.params.model_type == "xgboost":
            model_path = model_dir / "model.json"
            if not model_path.exists():
                logger.warning(f"XGBoost model not found at {model_path}")
                return

            import xgboost as xgb
            self._model = xgb.XGBClassifier()
            self._model.load_model(str(model_path))
            logger.info(f"Loaded XGBoost model from {model_path}")

        elif self.params.model_type == "lstm":
            model_path = model_dir / "lstm_model.pt"
            config_path = model_dir / "lstm_config.json"
            if not model_path.exists():
                logger.warning(f"LSTM model not found at {model_path}")
                return

            import torch
            from src.ml.training.train_reversal_classifier import LSTMClassifier

            with open(config_path) as f:
                lstm_config = json.load(f)

            self._model = LSTMClassifier(
                input_size=lstm_config["n_features"],
                hidden_size=lstm_config.get("hidden_size", 128),
                num_layers=lstm_config.get("num_layers", 2),
                num_classes=3,
                dropout=lstm_config.get("dropout", 0.2),
            )
            self._model.load_state_dict(torch.load(str(model_path), map_location="cpu"))
            self._model.eval()
            logger.info(f"Loaded LSTM model from {model_path}")

        # Load feature names
        feature_path = model_dir / "feature_names.json"
        if feature_path.exists():
            with open(feature_path) as f:
                self._feature_names = json.load(f)
        else:
            # Fall back to .txt format
            txt_path = model_dir / "feature_names.txt"
            if txt_path.exists():
                self._feature_names = txt_path.read_text().strip().split("\n")

    def _predict(self, tick: MarketTick) -> tuple:
        """
        Run prediction on current buffer state.

        Returns (predicted_class, confidence) or (None, 0.0) on error.
        """
        try:
            # Build DataFrame from buffer
            df = pd.DataFrame(list(self._buffer))
            df["time"] = pd.to_datetime(df["time"])

            # Compute all features
            df = compute_features_from_ohlcv(df)

            # Get the last row's features
            feature_cols = self._feature_names if self._feature_names else get_feature_columns(df)

            # Filter to only columns that exist (handles feature name mismatches gracefully)
            available_cols = [c for c in feature_cols if c in df.columns]
            if len(available_cols) < len(feature_cols) * 0.8:
                logger.warning(f"Only {len(available_cols)}/{len(feature_cols)} features available")

            last_row = df[available_cols].iloc[-1:]

            # Drop NaN — if the last row has NaN, we can't predict
            if last_row.isna().any(axis=1).iloc[0]:
                return None, 0.0

            X = last_row.values

            if self.params.model_type == "xgboost":
                proba = self._model.predict_proba(X)[0]
                # Classes are [-1, 0, 1] mapped to indices [0, 1, 2]
                predicted_idx = np.argmax(proba)
                class_map = {0: -1, 1: 0, 2: 1}  # idx → label
                predicted_class = class_map[predicted_idx]
                confidence = float(proba[predicted_idx])
                return predicted_class, confidence

            elif self.params.model_type == "lstm":
                import torch
                with torch.no_grad():
                    X_tensor = torch.FloatTensor(X).unsqueeze(0)  # (1, 1, n_features)
                    output = self._model(X_tensor)
                    proba = torch.softmax(output, dim=1).numpy()[0]
                    predicted_idx = np.argmax(proba)
                    class_map = {0: -1, 1: 0, 2: 1}
                    return class_map[predicted_idx], float(proba[predicted_idx])

        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return None, 0.0

    def _get_current_atr(self) -> float:
        """Get ATR from the last computed features in the buffer."""
        if len(self._buffer) < self.params.atr_period + 1:
            return 0.0

        # Compute ATR from buffer directly (simple average true range)
        buffer_list = list(self._buffer)
        recent = buffer_list[-(self.params.atr_period + 1):]
        true_ranges = []
        for i in range(1, len(recent)):
            hl = recent[i]["high"] - recent[i]["low"]
            hc = abs(recent[i]["high"] - recent[i - 1]["close"])
            lc = abs(recent[i]["low"] - recent[i - 1]["close"])
            true_ranges.append(max(hl, hc, lc))
        return float(np.mean(true_ranges)) if true_ranges else 0.0

    def reset(self) -> None:
        """Reset state for new backtest run."""
        self._buffer.clear()
        self.has_position = False
        self.entry_price = None
        self._position_direction = None
        # Don't reset model — it stays loaded across runs


def create_ml_reversal_strategy(
    symbol: str = "CrudeOIL",
    timeframe: str = "H1",
    model_dir: str = "",
    model_type: str = "xgboost",
    atr_period: int = 14,
    atr_stop_multiplier: float = 2.0,
    atr_tp_multiplier: float = 3.0,
    min_confidence: float = 0.55,
    lookback_bars: int = 250,
    **kwargs,
) -> MLReversalStrategy:
    """Factory function for MLReversalStrategy."""
    params = MLReversalParams(
        model_dir=model_dir,
        model_type=model_type,
        atr_period=atr_period,
        atr_stop_multiplier=atr_stop_multiplier,
        atr_tp_multiplier=atr_tp_multiplier,
        min_confidence=min_confidence,
        lookback_bars=lookback_bars,
    )
    if "quantity" in kwargs:
        params.quantity = kwargs["quantity"]
    return MLReversalStrategy(params, symbol=symbol, timeframe=timeframe)
