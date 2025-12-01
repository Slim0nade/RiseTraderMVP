"""MLInferenceService - Real-time ML forecast generation with caching."""

from typing import Dict, Any, List, Optional
import numpy as np
import time
from datetime import datetime

from src.ml.inference.predictor import ModelPredictor
from src.ml.inference.cache import ForecastCache
from src.database.repositories.forecast_repository import ForecastRepository
from src.ml.data.market_data_loader import MarketDataLoader
from src.ml.data.feature_engineering import FeatureEngineering


class MLInferenceService:
    """Service for real-time ML forecast generation with <50ms latency."""

    def __init__(
        self,
        predictor: ModelPredictor,
        cache: ForecastCache,
        forecast_repo: ForecastRepository,
        data_loader: MarketDataLoader
    ):
        self.predictor = predictor
        self.cache = cache
        self.forecast_repo = forecast_repo
        self.data_loader = data_loader
        self.feature_eng = FeatureEngineering()

    async def generate_forecast(
        self,
        symbol: str,
        horizon: str,
        model_version: str,
        model_type: str = 'lstm',
        model_path: Optional[str] = None,
        include_confidence: bool = False
    ) -> Dict[str, Any]:
        """
        Generate forecast for symbol and horizon with cache checking.

        Workflow:
        1. Check cache for recent forecast
        2. If cache miss, load model and generate prediction
        3. Store forecast in database
        4. Cache forecast with 5-minute TTL
        5. Return forecast with metadata

        Args:
            symbol: Trading symbol (e.g., 'CrudeOIL')
            horizon: Forecast horizon (e.g., '30d', '1h')
            model_version: Model version to use
            model_type: Model type ('lstm', 'xgboost', 'ensemble')
            model_path: Optional path to model file
            include_confidence: Whether to include confidence intervals

        Returns:
            Dict with forecast data and metadata
        """
        start_time = time.perf_counter()

        # Step 1: Check cache
        cache_key = self.cache.make_key(symbol, horizon, model_version)
        cached_forecast = self.cache.get(cache_key)

        if cached_forecast:
            cached_forecast['cache_hit'] = True
            return cached_forecast

        # Step 2: Load recent market data for inference
        df = await self.data_loader.load_recent_ohlcv(symbol, lookback_days=30)

        # Step 3: Engineer features
        lag_periods = [1, 2, 3, 5, 10]
        df = self.feature_eng.create_lag_features(df, lag_periods)
        df = self.feature_eng.create_rolling_features(df, [5, 10, 20])
        df = self.feature_eng.create_technical_indicators(df)

        # Step 4: Prepare input array
        X = self._prepare_input_array(df, model_type)

        # Step 5: Load model if not already loaded
        if model_path is None:
            model_path = f'/models/{model_type}_{model_version}.pth'

        if model_path not in self.predictor.loaded_models:
            self.predictor.load_model(model_path, model_type)

        # Step 6: Generate prediction
        predictions = self.predictor.predict(model_path, X)
        predicted_value = float(predictions[0])

        # Step 7: Calculate confidence intervals if requested
        lower_bound = None
        upper_bound = None
        confidence_score = None

        if include_confidence:
            # Simple confidence estimation (can be enhanced with model-specific methods)
            std_dev = 2.0  # Placeholder - should come from model uncertainty
            lower_bound = predicted_value - (1.96 * std_dev)  # 95% CI
            upper_bound = predicted_value + (1.96 * std_dev)
            confidence_score = 0.85  # Placeholder - should come from model

        # Step 8: Calculate inference time
        inference_time_ms = (time.perf_counter() - start_time) * 1000

        # Step 9: Store forecast in database
        forecast = await self.forecast_repo.create(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            forecast_horizon=horizon,
            model_type=model_type,
            model_version=model_version,
            predicted_value=predicted_value,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            confidence_score=confidence_score,
            inference_time_ms=inference_time_ms
        )

        # Step 10: Build response
        result = {
            'id': forecast.id,
            'symbol': symbol,
            'forecast_horizon': horizon,
            'model_type': model_type,
            'model_version': model_version,
            'predicted_value': predicted_value,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'confidence_score': confidence_score,
            'inference_time_ms': inference_time_ms,
            'cache_hit': False,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Step 11: Cache forecast
        self.cache.set(cache_key, result)

        return result

    async def generate_forecasts(
        self,
        symbol: str,
        horizons: List[str],
        model_version: str,
        model_type: str = 'lstm',
        include_confidence: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Generate forecasts for multiple horizons.

        Args:
            symbol: Trading symbol
            horizons: List of forecast horizons (e.g., ['1h', '4h', '1d'])
            model_version: Model version to use
            model_type: Model type
            include_confidence: Whether to include confidence intervals

        Returns:
            List of forecast dictionaries
        """
        forecasts = []

        for horizon in horizons:
            forecast = await self.generate_forecast(
                symbol=symbol,
                horizon=horizon,
                model_version=model_version,
                model_type=model_type,
                include_confidence=include_confidence
            )
            forecasts.append(forecast)

        return forecasts

    def _prepare_input_array(self, df, model_type: str) -> np.ndarray:
        """
        Convert DataFrame to model input array.

        Args:
            df: DataFrame with features
            model_type: Type of model ('lstm', 'xgboost', etc.)

        Returns:
            Numpy array formatted for model input
        """
        # Exclude timestamp and target columns
        feature_cols = [c for c in df.columns if c not in ['timestamp', 'close']]
        X = df[feature_cols].values

        if model_type == 'lstm':
            # LSTM expects 3D input (batch, seq_len, features)
            # Use last 60 timesteps for prediction
            if len(X) >= 60:
                X = X[-60:]
            X = X.reshape(1, len(X), -1)
        else:
            # XGBoost expects 2D input (samples, features)
            # Use only the most recent timestep
            X = X[-1:, :]

        return X.astype(np.float32)
