"""
ForecastAccuracyTracker - Calculate and track ML forecast accuracy metrics.

Provides:
- MAE, MSE, RMSE, MAPE calculation
- Directional accuracy (up/down prediction correctness)
- Batch forecast evaluation
- Model performance aggregation
"""

import numpy as np
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from src.database.repositories.forecast_repository import ForecastRepository
from src.database.repositories.market_data_repository import MarketDataRepository
from src.database.repositories.model_metrics_repository import ModelMetricsRepository
from src.database.models.forecasts import Forecast
from src.database.models.model_metrics import ModelMetrics


logger = logging.getLogger(__name__)


class ForecastAccuracyTracker:
    """
    Track and evaluate forecast accuracy metrics.

    Calculates statistical metrics comparing forecasts to actual market data:
    - MAE: Mean Absolute Error
    - MSE: Mean Squared Error
    - RMSE: Root Mean Squared Error
    - MAPE: Mean Absolute Percentage Error
    - Directional Accuracy: % of correct direction predictions
    """

    def __init__(
        self,
        forecast_repo: ForecastRepository,
        market_data_repo: MarketDataRepository,
        metrics_repo: ModelMetricsRepository
    ):
        """
        Initialize ForecastAccuracyTracker.

        Args:
            forecast_repo: Repository for forecast data
            market_data_repo: Repository for actual market data
            metrics_repo: Repository for storing metrics
        """
        self.forecast_repo = forecast_repo
        self.market_data_repo = market_data_repo
        self.metrics_repo = metrics_repo

        logger.info("ForecastAccuracyTracker initialized")

    def calculate_mae(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        """
        Calculate Mean Absolute Error.

        MAE = mean(|actual - predicted|)

        Args:
            actual: Array of actual values
            predicted: Array of predicted values

        Returns:
            MAE value

        Raises:
            ValueError: If arrays have different lengths
        """
        if len(actual) != len(predicted):
            raise ValueError(f"Array length mismatch: actual={len(actual)}, predicted={len(predicted)}")

        if len(actual) == 0:
            return 0.0

        mae = np.mean(np.abs(actual - predicted))
        return float(mae)

    def calculate_mse(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        """
        Calculate Mean Squared Error.

        MSE = mean((actual - predicted)^2)

        Args:
            actual: Array of actual values
            predicted: Array of predicted values

        Returns:
            MSE value

        Raises:
            ValueError: If arrays have different lengths
        """
        if len(actual) != len(predicted):
            raise ValueError(f"Array length mismatch: actual={len(actual)}, predicted={len(predicted)}")

        if len(actual) == 0:
            return 0.0

        mse = np.mean(np.square(actual - predicted))
        return float(mse)

    def calculate_rmse(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        """
        Calculate Root Mean Squared Error.

        RMSE = sqrt(MSE)

        Args:
            actual: Array of actual values
            predicted: Array of predicted values

        Returns:
            RMSE value
        """
        mse = self.calculate_mse(actual, predicted)
        rmse = np.sqrt(mse)
        return float(rmse)

    def calculate_mape(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        """
        Calculate Mean Absolute Percentage Error.

        MAPE = mean(|actual - predicted| / |actual|) * 100

        Skips entries where actual is zero to avoid division by zero.

        Args:
            actual: Array of actual values
            predicted: Array of predicted values

        Returns:
            MAPE value as percentage

        Raises:
            ValueError: If arrays have different lengths
        """
        if len(actual) != len(predicted):
            raise ValueError(f"Array length mismatch: actual={len(actual)}, predicted={len(predicted)}")

        if len(actual) == 0:
            return 0.0

        # Filter out zero actual values
        mask = actual != 0
        if not np.any(mask):
            logger.warning("All actual values are zero, cannot calculate MAPE")
            return 0.0

        actual_filtered = actual[mask]
        predicted_filtered = predicted[mask]

        mape = np.mean(np.abs((actual_filtered - predicted_filtered) / actual_filtered)) * 100
        return float(mape)

    def calculate_directional_accuracy(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        """
        Calculate directional accuracy (% of correct up/down predictions).

        Compares direction of change between consecutive values.

        Args:
            actual: Array of actual values
            predicted: Array of predicted values

        Returns:
            Directional accuracy as percentage (0-100)
        """
        if len(actual) < 2 or len(predicted) < 2:
            return 0.0

        # Calculate direction changes
        actual_direction = np.sign(np.diff(actual))
        predicted_direction = np.sign(np.diff(predicted))

        # Compare directions
        correct_directions = np.sum(actual_direction == predicted_direction)
        total_directions = len(actual_direction)

        accuracy = (correct_directions / total_directions) * 100 if total_directions > 0 else 0.0
        return float(accuracy)

    async def evaluate_forecast_accuracy(self, forecast: Forecast) -> Optional[Dict[str, Any]]:
        """
        Evaluate accuracy of a single forecast against actual data.

        Args:
            forecast: Forecast object to evaluate

        Returns:
            Dictionary with accuracy metrics or None if actual data not available
        """
        try:
            # Parse forecast horizon to determine target timestamp
            horizon_map = {
                '1h': timedelta(hours=1),
                '4h': timedelta(hours=4),
                '1d': timedelta(days=1)
            }

            if forecast.forecast_horizon not in horizon_map:
                logger.warning(f"Unknown forecast horizon: {forecast.forecast_horizon}")
                return None

            target_time = forecast.timestamp + horizon_map[forecast.forecast_horizon]

            # Get actual market data at target time
            actual_data = await self.market_data_repo.get_by_timestamp(
                symbol=forecast.symbol,
                timestamp=target_time
            )

            if not actual_data:
                logger.debug(f"Actual data not yet available for forecast {forecast.id}")
                return None

            actual_value = actual_data.close
            predicted_value = forecast.predicted_value

            # Calculate metrics
            actual_arr = np.array([actual_value])
            predicted_arr = np.array([predicted_value])

            mae = self.calculate_mae(actual_arr, predicted_arr)
            mse = self.calculate_mse(actual_arr, predicted_arr)
            mape = self.calculate_mape(actual_arr, predicted_arr)

            return {
                'forecast_id': forecast.id,
                'actual_value': float(actual_value),
                'predicted_value': float(predicted_value),
                'mae': mae,
                'mse': mse,
                'rmse': np.sqrt(mse),
                'mape': mape,
                'evaluated_at': datetime.utcnow()
            }

        except Exception as e:
            logger.error(f"Failed to evaluate forecast {forecast.id}: {str(e)}")
            return None

    async def batch_evaluate_forecasts(self, forecasts: List[Forecast]) -> List[Dict[str, Any]]:
        """
        Evaluate accuracy for multiple forecasts in batch.

        Args:
            forecasts: List of Forecast objects

        Returns:
            List of evaluation results
        """
        results = []

        for forecast in forecasts:
            result = await self.evaluate_forecast_accuracy(forecast)
            if result:
                results.append(result)

        logger.info(f"Evaluated {len(results)} out of {len(forecasts)} forecasts")
        return results

    async def calculate_model_accuracy_metrics(
        self,
        symbol: str,
        model_version: str,
        forecast_horizon: str,
        lookback_days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate aggregate accuracy metrics for a model over a time period.

        Args:
            symbol: Trading symbol
            model_version: Model version identifier
            forecast_horizon: Forecast horizon (e.g., '1h', '4h', '1d')
            lookback_days: Number of days to look back

        Returns:
            Dictionary with aggregate metrics or None if insufficient data
        """
        try:
            # Get forecasts for this model and horizon
            start_date = datetime.utcnow() - timedelta(days=lookback_days)
            forecasts = await self.forecast_repo.get_by_model_and_horizon(
                symbol=symbol,
                model_version=model_version,
                forecast_horizon=forecast_horizon,
                start_date=start_date
            )

            if not forecasts:
                logger.warning(f"No forecasts found for {symbol} {model_version} {forecast_horizon}")
                return None

            # Evaluate all forecasts
            evaluations = await self.batch_evaluate_forecasts(forecasts)

            if len(evaluations) < 10:
                logger.warning(f"Insufficient evaluations ({len(evaluations)}) for reliable metrics")
                return None

            # Aggregate metrics
            actual_values = np.array([e['actual_value'] for e in evaluations])
            predicted_values = np.array([e['predicted_value'] for e in evaluations])

            mae = self.calculate_mae(actual_values, predicted_values)
            mse = self.calculate_mse(actual_values, predicted_values)
            rmse = self.calculate_rmse(actual_values, predicted_values)
            mape = self.calculate_mape(actual_values, predicted_values)
            directional_accuracy = self.calculate_directional_accuracy(actual_values, predicted_values)

            metrics = {
                'symbol': symbol,
                'model_version': model_version,
                'forecast_horizon': forecast_horizon,
                'mae': mae,
                'mse': mse,
                'rmse': rmse,
                'mape': mape,
                'directional_accuracy': directional_accuracy,
                'sample_count': len(evaluations),
                'lookback_days': lookback_days,
                'calculated_at': datetime.utcnow()
            }

            logger.info(f"Calculated metrics for {symbol} {model_version}: MAE={mae:.4f}, MAPE={mape:.2f}%")
            return metrics

        except Exception as e:
            logger.error(f"Failed to calculate model metrics: {str(e)}")
            return None

    async def store_accuracy_metrics(self, metrics: Dict[str, Any]) -> Optional[ModelMetrics]:
        """
        Store calculated accuracy metrics to database.

        Args:
            metrics: Dictionary with metric values

        Returns:
            Created ModelMetrics object or None if failed
        """
        try:
            model_metrics = await self.metrics_repo.create(
                symbol=metrics['symbol'],
                model_version=metrics['model_version'],
                forecast_horizon=metrics['forecast_horizon'],
                mae=metrics['mae'],
                mse=metrics['mse'],
                rmse=metrics['rmse'],
                mape=metrics['mape'],
                directional_accuracy=metrics.get('directional_accuracy'),
                sample_count=metrics['sample_count']
            )

            logger.info(f"Stored metrics for {metrics['symbol']} {metrics['model_version']}")
            return model_metrics

        except Exception as e:
            logger.error(f"Failed to store metrics: {str(e)}")
            return None

    async def update_model_metrics(
        self,
        symbol: str,
        model_version: str,
        forecast_horizon: str
    ) -> bool:
        """
        Calculate and store updated metrics for a model.

        Convenience method combining calculation and storage.

        Args:
            symbol: Trading symbol
            model_version: Model version
            forecast_horizon: Forecast horizon

        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate metrics
            metrics = await self.calculate_model_accuracy_metrics(
                symbol=symbol,
                model_version=model_version,
                forecast_horizon=forecast_horizon
            )

            if not metrics:
                return False

            # Store metrics
            stored = await self.store_accuracy_metrics(metrics)

            return stored is not None

        except Exception as e:
            logger.error(f"Failed to update model metrics: {str(e)}")
            return False
