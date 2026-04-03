"""
MLPredictionAgent - Real ML Reversal Forecasting

Responsibilities:
- Load trained XGBoost reversal models from disk
- Generate real-time reversal predictions via ReversalPredictor
- Emit forecast_updated events with reversal probabilities
- Graceful degradation: if model missing, ML weight stays 0.0

Performance Target: <50ms inference time
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np
import structlog

from ..base_agent import BaseAgent
from ..event_bus import Event, EventPriority

logger = structlog.get_logger(__name__)

# Default model directory relative to project root
DEFAULT_MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "reversal_classifier"


class MLPredictionAgent(BaseAgent):
    """
    Generates ML-powered reversal predictions using trained XGBoost models.

    Loads per-symbol models from disk (models/reversal_classifier/{symbol}_{timeframe}/)
    and delegates inference to ReversalPredictor with full feature parity.

    Graceful degradation: if no model file exists for a symbol, predictions are skipped
    and the forecast_updated event is not emitted (ML weight stays 0.0 in signal generator).
    """

    def __init__(self, agent_id: str, event_bus, agent_registry, config: Dict[str, Any]):
        super().__init__(
            agent_id=agent_id,
            event_bus=event_bus,
            agent_registry=agent_registry,
            config=config,
            priority=5,  # Data/ML layer
        )

        # Configuration
        self.forecast_horizons = config.get("forecast_horizons", [5, 15, 60])
        self.confidence_threshold = config.get("confidence_threshold", 0.6)
        self.models_dir = Path(config.get("models_dir", str(DEFAULT_MODELS_DIR)))

        # Timeframes to load models for (H1 primary, M30 secondary)
        self.model_timeframes = config.get("model_timeframes", ["H1"])
        # Weights for multi-timeframe ensemble
        self.timeframe_weights = config.get("timeframe_weights", {"H1": 1.0})

        # Loaded predictors keyed by "{symbol}_{timeframe}"
        self._predictors: Dict[str, Any] = {}
        # Symbols that have no model (avoid repeated warnings)
        self._missing_models: set = set()

        # Feature buffer for tick tracking (minimum bars before prediction)
        self.feature_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self.feature_window = 100

        # Stats
        self.predictions_made = 0
        self.high_confidence_predictions = 0
        self.low_confidence_predictions = 0
        self.model_load_failures = 0

    async def initialize(self) -> None:
        """Load ML models and subscribe to events."""
        self.subscribe_to_event("new_tick")

        # Discover and load available models
        await self._load_models()

        self.logger.info(
            "ml_prediction_agent_initialized",
            loaded_models=list(self._predictors.keys()),
            models_dir=str(self.models_dir),
            timeframes=self.model_timeframes,
        )

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self.logger.info(
            "ml_prediction_agent_cleanup",
            predictions_made=self.predictions_made,
            high_confidence=self.high_confidence_predictions,
            low_confidence=self.low_confidence_predictions,
            load_failures=self.model_load_failures,
        )

    async def process_event(self, event: Event) -> None:
        """Process incoming events."""
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
        Generate forecast on new tick.

        Updates feature buffer and runs inference if enough data.
        """
        start_time = time.time()

        symbol = tick_data.get("symbol")
        if not symbol:
            return

        # Check if any model exists for this symbol
        has_model = any(
            f"{symbol}_{tf}" in self._predictors
            for tf in self.model_timeframes
        )
        if not has_model:
            if symbol not in self._missing_models:
                self.logger.debug("no_model_for_symbol", symbol=symbol)
                self._missing_models.add(symbol)
            return

        # Track ticks in buffer
        if symbol not in self.feature_buffer:
            self.feature_buffer[symbol] = []

        self.feature_buffer[symbol].append(tick_data)

        if len(self.feature_buffer[symbol]) > self.feature_window:
            self.feature_buffer[symbol] = self.feature_buffer[symbol][-self.feature_window:]

        # Generate forecast if we have enough data
        if len(self.feature_buffer[symbol]) >= 20:
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
        Generate reversal forecast using trained models.

        For each available timeframe model, runs ReversalPredictor and
        ensembles results if multiple timeframes are available.
        """
        from src.api.dependencies import get_db_context

        timeframe_results = {}

        async with get_db_context() as session:
            for tf in self.model_timeframes:
                key = f"{symbol}_{tf}"
                if key not in self._predictors:
                    continue

                predictor = self._predictors[key]

                # Update session for this prediction cycle
                predictor.session = session
                predictor.feature_extractor.session = session

                try:
                    result = await predictor.predict(
                        symbol=symbol,
                        timeframe=tf,
                    )

                    if result.get("error"):
                        continue

                    timeframe_results[tf] = result

                except Exception as e:
                    self.logger.error(
                        "prediction_failed",
                        symbol=symbol,
                        timeframe=tf,
                        error=str(e),
                    )

        if not timeframe_results:
            return

        # Ensemble across timeframes (or use single result)
        ensemble = self._ensemble_timeframes(timeframe_results)

        # Check confidence threshold
        if ensemble["confidence"] < self.confidence_threshold:
            self.low_confidence_predictions += 1
            return

        self.predictions_made += 1
        self.high_confidence_predictions += 1

        # Emit forecast with reversal probabilities
        forecast_data = {
            "symbol": symbol,
            "prediction": ensemble["prediction"],
            "confidence": ensemble["confidence"],
            "valley_prob": ensemble["valley_prob"],
            "peak_prob": ensemble["peak_prob"],
            "neutral_prob": ensemble["neutral_prob"],
            "signal": ensemble["signal"],
            "timeframe_results": {
                tf: {
                    "valley_prob": r["valley_prob"],
                    "peak_prob": r["peak_prob"],
                    "signal": r["signal"],
                    "confidence": r["confidence"],
                }
                for tf, r in timeframe_results.items()
            },
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
            signal=ensemble["signal"],
            confidence=ensemble["confidence"],
            valley_prob=ensemble["valley_prob"],
            peak_prob=ensemble["peak_prob"],
        )

    def _ensemble_timeframes(
        self, timeframe_results: Dict[str, Dict]
    ) -> Dict[str, float]:
        """
        Ensemble predictions from multiple timeframes.

        Uses weighted average based on self.timeframe_weights.
        Falls back to single-timeframe result if only one available.
        """
        if len(timeframe_results) == 1:
            tf, result = next(iter(timeframe_results.items()))
            # Map reversal probs to a directional prediction score
            # valley_prob → buy pressure, peak_prob → sell pressure
            prediction = result["valley_prob"] - result["peak_prob"]
            # Shift from [-1,1] to [0,1] range for compatibility
            prediction = (prediction + 1.0) / 2.0
            return {
                "prediction": prediction,
                "confidence": result["confidence"],
                "valley_prob": result["valley_prob"],
                "peak_prob": result["peak_prob"],
                "neutral_prob": result["neutral_prob"],
                "signal": result["signal"],
            }

        # Weighted average across timeframes
        total_weight = 0.0
        valley_sum = 0.0
        peak_sum = 0.0
        neutral_sum = 0.0
        conf_sum = 0.0

        for tf, result in timeframe_results.items():
            w = self.timeframe_weights.get(tf, 0.5)
            valley_sum += result["valley_prob"] * w
            peak_sum += result["peak_prob"] * w
            neutral_sum += result["neutral_prob"] * w
            conf_sum += result["confidence"] * w
            total_weight += w

        if total_weight == 0:
            return {
                "prediction": 0.5,
                "confidence": 0.0,
                "valley_prob": 0.0,
                "peak_prob": 0.0,
                "neutral_prob": 1.0,
                "signal": "WAIT",
            }

        valley_prob = valley_sum / total_weight
        peak_prob = peak_sum / total_weight
        neutral_prob = neutral_sum / total_weight
        confidence = conf_sum / total_weight

        prediction = (valley_prob - peak_prob + 1.0) / 2.0

        # Determine ensemble signal
        if peak_prob > 0.65:
            signal = "SHORT"
        elif valley_prob > 0.65:
            signal = "LONG"
        else:
            signal = "WAIT"

        return {
            "prediction": prediction,
            "confidence": confidence,
            "valley_prob": valley_prob,
            "peak_prob": peak_prob,
            "neutral_prob": neutral_prob,
            "signal": signal,
        }

    async def _load_models(self) -> None:
        """
        Load trained XGBoost models from disk.

        Scans models/reversal_classifier/ for {symbol}_{timeframe}/model.json files.
        Models that fail to load are logged and skipped (graceful degradation).
        """
        from src.ml.inference.reversal_predictor import ReversalPredictor
        from src.api.dependencies import get_db_context

        if not self.models_dir.exists():
            self.logger.warning(
                "models_dir_not_found",
                path=str(self.models_dir),
            )
            return

        async with get_db_context() as session:
            # Scan for model directories
            for model_dir in sorted(self.models_dir.iterdir()):
                if not model_dir.is_dir():
                    continue

                model_file = model_dir / "model.json"
                if not model_file.exists():
                    continue

                dir_name = model_dir.name  # e.g., "CrudeOIL_H1"
                parts = dir_name.rsplit("_", 1)
                if len(parts) != 2:
                    continue

                symbol, timeframe = parts

                # Only load requested timeframes
                if timeframe not in self.model_timeframes:
                    continue

                try:
                    predictor = ReversalPredictor(
                        session=session,
                        model_path=model_dir,
                    )
                    self._predictors[dir_name] = predictor

                    self.logger.info(
                        "model_loaded",
                        symbol=symbol,
                        timeframe=timeframe,
                        model_dir=str(model_dir),
                    )

                except Exception as e:
                    self.model_load_failures += 1
                    self.logger.error(
                        "model_load_failed",
                        model_dir=str(model_dir),
                        error=str(e),
                    )
