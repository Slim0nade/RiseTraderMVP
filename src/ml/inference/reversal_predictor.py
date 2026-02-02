"""
Reversal Predictor - Real-time inference for reversal classification

Loads trained model from MLflow registry and predicts reversal probabilities
for live market data WITHOUT using ZigZag (which repaints).

Usage:
    predictor = ReversalPredictor(session, model_version='v123')
    result = await predictor.predict('CrudeOIL', 'H1', current_time)

    if result['peak_prob'] > 0.75:
        # High confidence peak - consider SHORT
    elif result['valley_prob'] > 0.75:
        # High confidence valley - consider LONG
"""
import logging
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path

import numpy as np
import mlflow
import mlflow.xgboost
from sqlalchemy.ext.asyncio import AsyncSession

from src.ml.features.reversal_features import ReversalFeatureExtractor

logger = logging.getLogger(__name__)


class ReversalPredictor:
    """
    Real-time reversal prediction service.

    Loads trained model and predicts reversal probabilities
    for current market conditions.
    """

    def __init__(
        self,
        session: AsyncSession,
        model_uri: Optional[str] = None,
        model_path: Optional[Path] = None,
        threshold_peak: float = 0.75,
        threshold_valley: float = 0.75
    ):
        """
        Initialize reversal predictor.

        Args:
            session: Database session
            model_uri: MLflow model URI (e.g., 'models:/reversal_classifier/v1')
            model_path: Alternative: direct path to saved model
            threshold_peak: Probability threshold for peak signals (default 0.75)
            threshold_valley: Probability threshold for valley signals (default 0.75)
        """
        self.session = session
        self.threshold_peak = threshold_peak
        self.threshold_valley = threshold_valley
        self.feature_extractor = ReversalFeatureExtractor(session)

        # Load model
        if model_uri:
            self.model = mlflow.xgboost.load_model(model_uri)
            logger.info(f"Loaded model from MLflow: {model_uri}")
        elif model_path:
            self.model = mlflow.xgboost.load_model(str(model_path))
            logger.info(f"Loaded model from path: {model_path}")
        else:
            raise ValueError("Must provide either model_uri or model_path")

        # Load feature names if available
        self.feature_names = None
        try:
            if model_uri:
                # Try to load feature names from MLflow artifacts
                client = mlflow.tracking.MlflowClient()
                run_id = model_uri.split('/')[-1]  # Extract run ID
                artifact_path = client.download_artifacts(run_id, 'feature_names.txt')
                with open(artifact_path, 'r') as f:
                    self.feature_names = [line.strip() for line in f.readlines()]
                logger.info(f"Loaded {len(self.feature_names)} feature names")
        except Exception as e:
            logger.warning(f"Could not load feature names: {e}")

    async def predict(
        self,
        symbol: str,
        timeframe: str,
        current_time: Optional[datetime] = None,
        lookback_bars: int = 100
    ) -> Dict[str, float]:
        """
        Predict reversal probability for current candle.

        Args:
            symbol: Trading symbol (e.g., 'CrudeOIL')
            timeframe: Candle timeframe (e.g., 'H1')
            current_time: Time to predict for (defaults to now)
            lookback_bars: Number of historical bars to load for feature calculation

        Returns:
            Dict with predictions:
            {
                'valley_prob': 0.15,
                'neutral_prob': 0.10,
                'peak_prob': 0.75,
                'signal': 'SHORT',  # or 'LONG' or 'WAIT'
                'confidence': 0.75,
                'timestamp': '2024-01-01T12:00:00'
            }
        """
        if current_time is None:
            current_time = datetime.utcnow()

        logger.debug(f"Predicting reversal for {symbol} {timeframe} at {current_time}")

        # Extract features for current candle
        X, feature_names = await self.feature_extractor.extract_live_features(
            symbol=symbol,
            timeframe=timeframe,
            current_time=current_time,
            lookback_bars=lookback_bars
        )

        if len(X) == 0:
            logger.warning(f"No features extracted for {symbol} {timeframe}")
            return self._empty_prediction(current_time)

        # Verify feature consistency
        if self.feature_names and feature_names != self.feature_names:
            logger.warning(
                f"Feature mismatch! Expected {len(self.feature_names)}, "
                f"got {len(feature_names)}"
            )

        # Predict probabilities
        # Model expects labels {0, 1, 2} for {valley, neutral, peak}
        probs = self.model.predict_proba(X)[0]

        valley_prob = float(probs[0])
        neutral_prob = float(probs[1])
        peak_prob = float(probs[2])

        # Generate signal based on thresholds
        signal, confidence = self._generate_signal(
            valley_prob, peak_prob, neutral_prob
        )

        result = {
            'valley_prob': valley_prob,
            'neutral_prob': neutral_prob,
            'peak_prob': peak_prob,
            'signal': signal,
            'confidence': confidence,
            'timestamp': current_time.isoformat(),
            'symbol': symbol,
            'timeframe': timeframe
        }

        logger.debug(f"Prediction: {result}")

        return result

    async def predict_batch(
        self,
        symbol: str,
        timeframe: str,
        times: List[datetime],
        lookback_bars: int = 100
    ) -> List[Dict[str, float]]:
        """
        Predict reversals for multiple time points.

        Useful for backtesting or generating historical signals.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            times: List of timestamps to predict for
            lookback_bars: Number of bars for feature calculation

        Returns:
            List of prediction dicts
        """
        results = []

        for t in times:
            result = await self.predict(
                symbol=symbol,
                timeframe=timeframe,
                current_time=t,
                lookback_bars=lookback_bars
            )
            results.append(result)

        return results

    def _generate_signal(
        self,
        valley_prob: float,
        peak_prob: float,
        neutral_prob: float
    ) -> tuple[str, float]:
        """
        Generate trading signal from probabilities.

        Returns:
            (signal, confidence) tuple where signal is 'LONG', 'SHORT', or 'WAIT'
        """
        # Check if peak probability exceeds threshold
        if peak_prob > self.threshold_peak:
            return 'SHORT', peak_prob

        # Check if valley probability exceeds threshold
        if valley_prob > self.threshold_valley:
            return 'LONG', valley_prob

        # No clear signal
        return 'WAIT', neutral_prob

    def _empty_prediction(self, current_time: datetime) -> Dict[str, float]:
        """Return empty prediction when no data available."""
        return {
            'valley_prob': 0.0,
            'neutral_prob': 1.0,
            'peak_prob': 0.0,
            'signal': 'WAIT',
            'confidence': 0.0,
            'timestamp': current_time.isoformat(),
            'error': 'No data available'
        }

    def set_thresholds(self, peak: float, valley: float):
        """Update probability thresholds."""
        self.threshold_peak = peak
        self.threshold_valley = valley
        logger.info(f"Updated thresholds: peak={peak}, valley={valley}")

    def get_model_info(self) -> Dict:
        """Get information about the loaded model."""
        return {
            'model_type': type(self.model).__name__,
            'threshold_peak': self.threshold_peak,
            'threshold_valley': self.threshold_valley,
            'feature_count': len(self.feature_names) if self.feature_names else 'unknown',
            'feature_names': self.feature_names
        }


# Singleton predictor instance (for API use)
_predictor_cache: Dict[str, ReversalPredictor] = {}


async def get_predictor(
    session: AsyncSession,
    model_version: str = 'latest',
    model_uri: Optional[str] = None
) -> ReversalPredictor:
    """
    Get or create predictor instance.

    Caches predictor by model version to avoid reloading.

    Args:
        session: Database session
        model_version: Model version to load (e.g., 'v1', 'latest')
        model_uri: Explicit MLflow URI (overrides model_version)

    Returns:
        ReversalPredictor instance
    """
    cache_key = model_uri or model_version

    if cache_key not in _predictor_cache:
        if model_uri is None:
            model_uri = f"models:/reversal_classifier/{model_version}"

        _predictor_cache[cache_key] = ReversalPredictor(
            session=session,
            model_uri=model_uri
        )

        logger.info(f"Created new predictor: {cache_key}")

    return _predictor_cache[cache_key]


def clear_predictor_cache():
    """Clear predictor cache (useful for testing or model updates)."""
    global _predictor_cache
    _predictor_cache = {}
    logger.info("Predictor cache cleared")
