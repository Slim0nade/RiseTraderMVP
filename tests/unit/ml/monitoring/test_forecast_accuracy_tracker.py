"""
Unit tests for ForecastAccuracyTracker.
Tests calculation of MAE, MSE, RMSE, MAPE metrics for forecast accuracy.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.ml.monitoring.forecast_accuracy_tracker import ForecastAccuracyTracker


class TestForecastAccuracyTracker:
    """Test ForecastAccuracyTracker functionality."""

    @pytest.fixture
    def tracker(self):
        """Create ForecastAccuracyTracker instance."""
        mock_forecast_repo = Mock()
        mock_market_data_repo = Mock()
        mock_metrics_repo = Mock()

        return ForecastAccuracyTracker(
            forecast_repo=mock_forecast_repo,
            market_data_repo=mock_market_data_repo,
            metrics_repo=mock_metrics_repo
        )

    def test_initialization(self, tracker):
        """Test ForecastAccuracyTracker initialization."""
        assert tracker.forecast_repo is not None
        assert tracker.market_data_repo is not None
        assert tracker.metrics_repo is not None

    def test_calculate_mae(self, tracker):
        """Test Mean Absolute Error calculation."""
        actual = np.array([100.0, 102.0, 104.0, 103.0, 105.0])
        predicted = np.array([99.5, 101.5, 105.0, 102.5, 106.0])

        mae = tracker.calculate_mae(actual, predicted)

        # MAE = mean(|100-99.5|, |102-101.5|, |104-105|, |103-102.5|, |105-106|)
        # MAE = mean(0.5, 0.5, 1.0, 0.5, 1.0) = 3.5 / 5 = 0.7
        assert abs(mae - 0.7) < 0.001

    def test_calculate_mse(self, tracker):
        """Test Mean Squared Error calculation."""
        actual = np.array([100.0, 102.0, 104.0])
        predicted = np.array([101.0, 103.0, 103.0])

        mse = tracker.calculate_mse(actual, predicted)

        # MSE = mean((100-101)^2, (102-103)^2, (104-103)^2)
        # MSE = mean(1, 1, 1) = 1.0
        assert abs(mse - 1.0) < 0.001

    def test_calculate_rmse(self, tracker):
        """Test Root Mean Squared Error calculation."""
        actual = np.array([100.0, 102.0, 104.0])
        predicted = np.array([101.0, 103.0, 103.0])

        rmse = tracker.calculate_rmse(actual, predicted)

        # RMSE = sqrt(MSE) = sqrt(1.0) = 1.0
        assert abs(rmse - 1.0) < 0.001

    def test_calculate_mape(self, tracker):
        """Test Mean Absolute Percentage Error calculation."""
        actual = np.array([100.0, 200.0, 300.0])
        predicted = np.array([95.0, 210.0, 285.0])

        mape = tracker.calculate_mape(actual, predicted)

        # MAPE = mean(|100-95|/100, |200-210|/200, |300-285|/300) * 100
        # MAPE = mean(0.05, 0.05, 0.05) * 100 = 5.0
        assert abs(mape - 5.0) < 0.001

    def test_calculate_mape_zero_actual(self, tracker):
        """Test MAPE handles zero actual values."""
        actual = np.array([100.0, 0.0, 200.0])
        predicted = np.array([95.0, 10.0, 190.0])

        mape = tracker.calculate_mape(actual, predicted)

        # Should skip zero actual values
        # MAPE = mean(|100-95|/100, |200-190|/200) * 100
        # MAPE = mean(0.05, 0.05) * 100 = 5.0
        assert abs(mape - 5.0) < 0.001

    def test_calculate_directional_accuracy(self, tracker):
        """Test directional accuracy calculation."""
        actual = np.array([100.0, 102.0, 101.0, 104.0, 103.0])
        predicted = np.array([99.0, 103.0, 100.0, 105.0, 102.0])

        # Direction changes (actual): up, down, up, down
        # Direction changes (predicted): up, down, up, down
        # All 4 correct = 100%

        accuracy = tracker.calculate_directional_accuracy(actual, predicted)

        assert abs(accuracy - 100.0) < 0.001

    def test_calculate_directional_accuracy_partial(self, tracker):
        """Test directional accuracy with partial matches."""
        actual = np.array([100.0, 102.0, 101.0, 104.0])
        predicted = np.array([99.0, 101.0, 102.0, 103.0])

        # Direction changes (actual): up, down, up
        # Direction changes (predicted): up, up, up
        # 1 correct out of 3 = 33.33%

        accuracy = tracker.calculate_directional_accuracy(actual, predicted)

        assert abs(accuracy - 33.33) < 0.1

    @pytest.mark.asyncio
    async def test_evaluate_forecast_accuracy(self, tracker):
        """Test evaluating accuracy for a specific forecast."""
        # Mock forecast
        mock_forecast = Mock()
        mock_forecast.symbol = "CrudeOIL"
        mock_forecast.forecast_horizon = "1h"
        mock_forecast.predicted_value = 75.5
        mock_forecast.timestamp = datetime.utcnow() - timedelta(hours=2)

        # Mock actual market data (1 hour after forecast)
        mock_actual = Mock()
        mock_actual.close = 75.8

        tracker.market_data_repo.get_by_timestamp = AsyncMock(return_value=mock_actual)

        result = await tracker.evaluate_forecast_accuracy(mock_forecast)

        assert result is not None
        assert 'mae' in result
        assert 'mse' in result
        assert 'mape' in result
        assert abs(result['mae'] - 0.3) < 0.001  # |75.5 - 75.8| = 0.3

    @pytest.mark.asyncio
    async def test_evaluate_forecast_no_actual_data(self, tracker):
        """Test evaluation when actual data is not yet available."""
        mock_forecast = Mock()
        mock_forecast.symbol = "CrudeOIL"
        mock_forecast.forecast_horizon = "1h"
        mock_forecast.timestamp = datetime.utcnow()

        tracker.market_data_repo.get_by_timestamp = AsyncMock(return_value=None)

        result = await tracker.evaluate_forecast_accuracy(mock_forecast)

        assert result is None  # Cannot evaluate yet

    @pytest.mark.asyncio
    async def test_batch_evaluate_forecasts(self, tracker):
        """Test batch evaluation of multiple forecasts."""
        # Mock forecasts
        forecasts = [
            Mock(
                id=i,
                symbol="CrudeOIL",
                forecast_horizon="1h",
                predicted_value=75.0 + i * 0.1,
                timestamp=datetime.utcnow() - timedelta(hours=2)
            )
            for i in range(5)
        ]

        # Mock actual data
        actuals = [
            Mock(close=75.0 + i * 0.1 + 0.05)  # Small error
            for i in range(5)
        ]

        tracker.market_data_repo.get_by_timestamp = AsyncMock(side_effect=actuals)

        results = await tracker.batch_evaluate_forecasts(forecasts)

        assert len(results) == 5
        for result in results:
            assert 'forecast_id' in result
            assert 'mae' in result
            assert 'mse' in result

    @pytest.mark.asyncio
    async def test_calculate_model_accuracy_metrics(self, tracker):
        """Test calculating aggregate accuracy for a model."""
        symbol = "CrudeOIL"
        model_version = "v1.0.0"
        horizon = "1h"

        # Mock forecasts
        mock_forecasts = [
            Mock(
                predicted_value=75.0 + i * 0.1,
                timestamp=datetime.utcnow() - timedelta(hours=i+2)
            )
            for i in range(10)
        ]

        # Mock actuals
        mock_actuals = [
            Mock(close=75.0 + i * 0.1 + 0.05)
            for i in range(10)
        ]

        tracker.forecast_repo.get_by_model_and_horizon = AsyncMock(return_value=mock_forecasts)
        tracker.market_data_repo.get_by_timestamp = AsyncMock(side_effect=mock_actuals)

        metrics = await tracker.calculate_model_accuracy_metrics(
            symbol=symbol,
            model_version=model_version,
            forecast_horizon=horizon
        )

        assert metrics is not None
        assert metrics['symbol'] == symbol
        assert metrics['model_version'] == model_version
        assert metrics['forecast_horizon'] == horizon
        assert 'mae' in metrics
        assert 'mse' in metrics
        assert 'rmse' in metrics
        assert 'mape' in metrics
        assert 'directional_accuracy' in metrics
        assert metrics['sample_count'] == 10

    @pytest.mark.asyncio
    async def test_store_accuracy_metrics(self, tracker):
        """Test storing calculated metrics to database."""
        metrics = {
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'forecast_horizon': '1h',
            'mae': 0.25,
            'mse': 0.08,
            'rmse': 0.28,
            'mape': 0.35,
            'directional_accuracy': 85.5,
            'sample_count': 100
        }

        tracker.metrics_repo.create = AsyncMock(return_value=Mock(id=1))

        result = await tracker.store_accuracy_metrics(metrics)

        assert result is not None
        tracker.metrics_repo.create.assert_called_once()

    def test_empty_arrays(self, tracker):
        """Test metrics calculation with empty arrays."""
        actual = np.array([])
        predicted = np.array([])

        mae = tracker.calculate_mae(actual, predicted)
        mse = tracker.calculate_mse(actual, predicted)

        assert np.isnan(mae) or mae == 0.0
        assert np.isnan(mse) or mse == 0.0

    def test_mismatched_array_lengths(self, tracker):
        """Test error handling for mismatched array lengths."""
        actual = np.array([100.0, 102.0, 104.0])
        predicted = np.array([101.0, 103.0])  # Shorter

        with pytest.raises(ValueError):
            tracker.calculate_mae(actual, predicted)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
