"""
MLPredictionAgent - Ensemble ML Forecasting

Responsibilities:
- Load ML models from MLflow registry
- Generate real-time price forecasts
- Ensemble prediction (XGBoost, Transformer, LSTM)
- Emit forecast_updated events

Performance Target: <50ms inference time
"""

import asyncio
import time
from typing import Dict, Any, Optional, List

import numpy as np
import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)


class MLPredictionAgent(BaseAgent):
    """
    Generates ML-powered price forecasts

    Ensemble Models:
    1. XGBoost - Gradient boosting (weight: 0.4)
    2. Transformer - Attention-based time series (weight: 0.35)
    3. LSTM - Recurrent neural network (weight: 0.25)

    Forecast Horizons:
    - 5 minutes
    - 15 minutes
    - 60 minutes (1 hour)
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=5,  # Data/ML layer
        )

        # Model configuration
        self.models_config = config.get("models", [])
        self.forecast_horizons = config.get("forecast_horizons", [5, 15, 60])
        self.ensemble_method = config.get("ensemble_method", "weighted_average")
        self.confidence_threshold = config.get("confidence_threshold", 0.6)
        self.mlflow_tracking = config.get("mlflow_tracking", False)

        # Model weights
        self.model_weights = {}
        for model_config in self.models_config:
            model_type = model_config.get("type")
            weight = model_config.get("weight", 0.33)
            self.model_weights[model_type] = weight

        # Loaded models (placeholder - would load from MLflow)
        self.models: Dict[str, Any] = {}

        # Feature buffer for inference
        self.feature_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self.feature_window = 100  # Number of bars for features

        # Stats
        self.predictions_made = 0
        self.high_confidence_predictions = 0
        self.low_confidence_predictions = 0

    async def initialize(self) -> None:
        """Load ML models and subscribe to events"""
        self.subscribe_to_event("new_tick")

        try:
            # Load models from MLflow (placeholder)
            await self._load_models()

            self.logger.info(
                "ml_prediction_agent_initialized",
                models=list(self.models.keys()),
                horizons=self.forecast_horizons,
                ensemble_method=self.ensemble_method,
            )

        except Exception as e:
            self.logger.error("initialization_failed", error=str(e), exc_info=True)
            # Don't raise - allow agent to start without models

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self.logger.info(
            "ml_prediction_agent_cleanup",
            predictions_made=self.predictions_made,
            high_confidence=self.high_confidence_predictions,
            low_confidence=self.low_confidence_predictions,
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
        Generate forecast on new tick

        Updates feature buffer and runs inference
        """
        start_time = time.time()

        symbol = tick_data.get("symbol")

        # Initialize buffer for symbol
        if symbol not in self.feature_buffer:
            self.feature_buffer[symbol] = []

        # Add tick to buffer
        self.feature_buffer[symbol].append(tick_data)

        # Keep only recent history
        if len(self.feature_buffer[symbol]) > self.feature_window:
            self.feature_buffer[symbol] = self.feature_buffer[symbol][-self.feature_window:]

        # Generate forecast if we have enough data
        if len(self.feature_buffer[symbol]) >= 20:  # Minimum bars
            await self._generate_forecast(symbol)

        inference_time = time.time() - start_time

        if inference_time > 0.05:  # Warn if >50ms
            self.logger.warning(
                "inference_slow",
                symbol=symbol,
                inference_time=inference_time,
            )

    async def _generate_forecast(self, symbol: str) -> None:
        """
        Generate ensemble forecast

        Args:
            symbol: Trading symbol
        """
        ticks = self.feature_buffer[symbol]

        # Extract features
        features = self._extract_features(ticks)

        # Run each model
        model_predictions = {}

        for model_type, weight in self.model_weights.items():
            if model_type in self.models:
                prediction = await self._predict_with_model(model_type, features)
                model_predictions[model_type] = prediction

        # Ensemble predictions
        ensemble_result = self._ensemble_predictions(model_predictions)

        # Check confidence threshold
        if ensemble_result["confidence"] < self.confidence_threshold:
            self.low_confidence_predictions += 1
            # Don't emit low confidence predictions
            return

        self.predictions_made += 1
        self.high_confidence_predictions += 1

        # Emit forecast
        forecast_data = {
            "symbol": symbol,
            "prediction": ensemble_result["prediction"],
            "confidence": ensemble_result["confidence"],
            "model_predictions": model_predictions,
            "horizons": self.forecast_horizons,
            "timestamp": time.time(),
        }

        await self.publish_event(
            event_type="forecast_updated",
            data=forecast_data,
            priority=EventPriority.NORMAL,
        )

        # Store in context
        await self.set_context(
            f"forecast_{symbol}",
            forecast_data,
            ttl=300,
        )

        self.logger.debug(
            "forecast_generated",
            symbol=symbol,
            prediction=ensemble_result["prediction"],
            confidence=ensemble_result["confidence"],
        )

    def _extract_features(self, ticks: List[Dict[str, Any]]) -> np.ndarray:
        """
        Extract features for ML model

        Features:
        - Price changes (returns)
        - Moving averages
        - Volatility
        - Volume
        - Technical indicators

        Args:
            ticks: Recent tick data

        Returns:
            Feature array (n_features,)
        """
        closes = np.array([t["close"] for t in ticks])
        highs = np.array([t["high"] for t in ticks])
        lows = np.array([t["low"] for t in ticks])
        volumes = np.array([t.get("volume", 0) for t in ticks])

        features = []

        # Price returns (different periods)
        for period in [1, 5, 10, 20]:
            if len(closes) >= period + 1:
                returns = (closes[-1] - closes[-(period + 1)]) / closes[-(period + 1)]
                features.append(returns)
            else:
                features.append(0.0)

        # Moving averages
        for period in [5, 10, 20, 50]:
            if len(closes) >= period:
                ma = np.mean(closes[-period:])
                ma_ratio = closes[-1] / ma - 1  # Normalized
                features.append(ma_ratio)
            else:
                features.append(0.0)

        # Volatility (standard deviation of returns)
        if len(closes) >= 20:
            returns = np.diff(closes[-20:]) / closes[-20:-1]
            volatility = np.std(returns)
            features.append(volatility)
        else:
            features.append(0.0)

        # High-Low range
        if len(highs) >= 10:
            hl_range = np.mean(highs[-10:] - lows[-10:])
            hl_normalized = hl_range / closes[-1]
            features.append(hl_normalized)
        else:
            features.append(0.0)

        # Volume (normalized)
        if len(volumes) >= 10 and np.mean(volumes[-10:]) > 0:
            volume_ratio = volumes[-1] / np.mean(volumes[-10:])
            features.append(volume_ratio)
        else:
            features.append(1.0)

        # RSI (Relative Strength Index)
        if len(closes) >= 14:
            rsi = self._calculate_rsi(closes, period=14)
            features.append(rsi / 100.0)  # Normalize to [0, 1]
        else:
            features.append(0.5)

        return np.array(features)

    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """
        Calculate RSI indicator

        Args:
            prices: Price array
            period: RSI period

        Returns:
            RSI value (0-100)
        """
        if len(prices) < period + 1:
            return 50.0

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Average gains and losses
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    async def _predict_with_model(self, model_type: str, features: np.ndarray) -> Dict[str, Any]:
        """
        Run inference with specific model

        In production, this would use actual trained models.
        For now, we simulate predictions.

        Args:
            model_type: Model type (xgboost, transformer, lstm)
            features: Input features

        Returns:
            Prediction result with score and confidence
        """
        # Simulate model inference
        # In production: model.predict(features.reshape(1, -1))

        if model_type == "xgboost":
            # Simulate XGBoost prediction (fast, tree-based)
            score = 0.5 + (features[0] * 0.3)  # Use first feature (1-period return)
            confidence = 0.75

        elif model_type == "transformer":
            # Simulate Transformer prediction (attention-based)
            score = 0.5 + (features[0] * 0.25 + features[4] * 0.15)
            confidence = 0.70

        elif model_type == "lstm":
            # Simulate LSTM prediction (recurrent)
            score = 0.5 + (features[0] * 0.2 + features[1] * 0.1)
            confidence = 0.65

        else:
            score = 0.5
            confidence = 0.5

        # Clip to [0, 1]
        score = np.clip(score, 0.0, 1.0)

        return {
            "score": score,
            "confidence": confidence,
        }

    def _ensemble_predictions(self, model_predictions: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """
        Combine predictions from multiple models

        Methods:
        - weighted_average: Weight by model weight and confidence
        - voting: Majority vote
        - stacking: Meta-model (not implemented)

        Args:
            model_predictions: Dict of model_type -> {score, confidence}

        Returns:
            Ensemble result with prediction and confidence
        """
        if not model_predictions:
            return {"prediction": 0.5, "confidence": 0.0}

        if self.ensemble_method == "weighted_average":
            weighted_sum = 0.0
            total_weight = 0.0

            for model_type, prediction in model_predictions.items():
                weight = self.model_weights.get(model_type, 0.33)
                score = prediction.get("score", 0.5)
                confidence = prediction.get("confidence", 0.5)

                weighted_sum += score * weight * confidence
                total_weight += weight * confidence

            if total_weight == 0:
                return {"prediction": 0.5, "confidence": 0.0}

            ensemble_prediction = weighted_sum / total_weight

            # Average confidence
            avg_confidence = np.mean([p["confidence"] for p in model_predictions.values()])

            return {
                "prediction": ensemble_prediction,
                "confidence": avg_confidence,
            }

        elif self.ensemble_method == "voting":
            # Simple majority vote
            votes = [1 if p["score"] > 0.5 else 0 for p in model_predictions.values()]
            majority = np.mean(votes)

            avg_confidence = np.mean([p["confidence"] for p in model_predictions.values()])

            return {
                "prediction": majority,
                "confidence": avg_confidence,
            }

        else:
            # Default to simple average
            avg_prediction = np.mean([p["score"] for p in model_predictions.values()])
            avg_confidence = np.mean([p["confidence"] for p in model_predictions.values()])

            return {
                "prediction": avg_prediction,
                "confidence": avg_confidence,
            }

    async def _load_models(self) -> None:
        """
        Load ML models from MLflow registry

        In production, this would:
        1. Connect to MLflow tracking server
        2. Load latest models for each type
        3. Verify model signatures
        4. Warm up models with dummy inference
        """
        for model_config in self.models_config:
            model_type = model_config.get("type")
            version = model_config.get("version", "latest")

            # Placeholder - in production, load actual models
            # model = mlflow.pyfunc.load_model(f"models:/{model_type}/{version}")

            self.models[model_type] = {
                "type": model_type,
                "version": version,
                "loaded": True,
            }

            self.logger.info(
                "model_loaded",
                model_type=model_type,
                version=version,
            )
