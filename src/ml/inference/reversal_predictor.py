"""
Reversal Predictor - Real-time inference for reversal classification

Loads trained XGBoost model from disk and predicts reversal probabilities
for live market data WITHOUT using ZigZag (which repaints).

Usage:
    predictor = ReversalPredictor(session, model_path=Path('models/reversal_classifier/CrudeOIL_H1'))
    result = await predictor.predict('CrudeOIL', 'H1', current_time)

    if result['peak_prob'] > 0.65:
        # High confidence peak - consider SHORT
    elif result['valley_prob'] > 0.65:
        # High confidence valley - consider LONG
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

import numpy as np
import xgboost as xgb
from sqlalchemy.ext.asyncio import AsyncSession

from src.ml.features.reversal_features import ReversalFeatureExtractor

logger = logging.getLogger(__name__)


class ReversalPredictor:
    """
    Real-time reversal prediction service.

    Loads trained XGBoost model from disk and predicts reversal probabilities
    for current market conditions.
    """

    def __init__(
        self,
        session: AsyncSession,
        model_path: Optional[Path] = None,
        threshold_peak: float = 0.65,
        threshold_valley: float = 0.65
    ):
        """
        Initialize reversal predictor.

        Args:
            session: Database session for feature extraction
            model_path: Path to model directory containing model.json + feature_names.txt
            threshold_peak: Probability threshold for peak signals
            threshold_valley: Probability threshold for valley signals
        """
        self.session = session
        self.threshold_peak = threshold_peak
        self.threshold_valley = threshold_valley
        self.feature_extractor = ReversalFeatureExtractor(session)
        self.model = None
        self.booster = None
        self.feature_names = None
        self.metadata = None

        if model_path:
            self._load_from_disk(model_path)

    def _load_from_disk(self, model_dir: Path) -> None:
        """
        Load XGBoost model from disk directory.

        Expects:
          - model_dir/model.json (XGBoost native format)
          - model_dir/feature_names.txt (one feature per line)
          - model_dir/metadata.json (optional, training info)
        """
        model_dir = Path(model_dir)
        model_file = model_dir / "model.json"

        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_file}")

        # Load XGBoost model — booster format saved by get_booster().save_model()
        # Use Booster directly for predict_proba via DMatrix
        self.booster = xgb.Booster()
        self.booster.load_model(str(model_file))
        self.model = True  # Flag that model is loaded (booster used directly)
        logger.info(f"Loaded XGBoost booster from {model_file}")

        # Load feature names (supports both .json and .txt formats)
        feature_json = model_dir / "feature_names.json"
        feature_txt = model_dir / "feature_names.txt"
        if feature_json.exists():
            with open(feature_json, "r") as f:
                self.feature_names = json.load(f)
            logger.info(f"Loaded {len(self.feature_names)} feature names from JSON")
        elif feature_txt.exists():
            with open(feature_txt, "r") as f:
                self.feature_names = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(self.feature_names)} feature names from TXT")

        # Load metadata (optional)
        metadata_file = model_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                self.metadata = json.load(f)
            logger.info(
                f"Model metadata: {self.metadata.get('model_name', 'unknown')}, "
                f"F1={self.metadata.get('reversal_f1', 'N/A')}"
            )

    def is_loaded(self) -> bool:
        """Check if a model is loaded and ready for predictions."""
        return self.booster is not None

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
        if not self.is_loaded():
            return self._empty_prediction(current_time or datetime.utcnow())

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
        if self.feature_names and len(feature_names) != len(self.feature_names):
            logger.warning(
                f"Feature count mismatch! Expected {len(self.feature_names)}, "
                f"got {len(feature_names)}"
            )

        # Predict probabilities via DMatrix → booster
        # Model expects labels {0, 1, 2} for {valley, neutral, peak}
        dmatrix = xgb.DMatrix(X, feature_names=self.feature_names)
        probs = self.booster.predict(dmatrix)[0]

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
        """Predict reversals for multiple time points."""
        results = []
        for t in times:
            result = await self.predict(symbol, timeframe, t, lookback_bars)
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
        if peak_prob > self.threshold_peak:
            return 'SHORT', peak_prob

        if valley_prob > self.threshold_valley:
            return 'LONG', valley_prob

        return 'WAIT', max(valley_prob, peak_prob)

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
            'model_loaded': self.is_loaded(),
            'threshold_peak': self.threshold_peak,
            'threshold_valley': self.threshold_valley,
            'feature_count': len(self.feature_names) if self.feature_names else 0,
            'metadata': self.metadata,
        }
