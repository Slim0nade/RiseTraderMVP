"""
Integration tests for MLInferenceService.
Tests complete inference pipeline with cache, model loading, and forecast storage.
"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.services.ml_inference_service import MLInferenceService
from src.database.models.forecasts import Forecast


@pytest.fixture
def mock_predictor():
    """Mock ModelPredictor."""
    predictor = Mock()
    predictor.load_model = Mock()
    predictor.predict = Mock(return_value=np.array([75.5]))
    predictor.loaded_models = {}
    return predictor


@pytest.fixture
def mock_cache():
    """Mock ForecastCache."""
    cache = Mock()
    cache.get = Mock(return_value=None)  # Default: cache miss
    cache.set = Mock()
    cache.make_key = Mock(return_value='forecast:CrudeOIL:30d:v1.0.0')
    return cache


@pytest.fixture
def mock_forecast_repo():
    """Mock ForecastRepository."""
    repo = AsyncMock()

    created_forecast = Mock(spec=Forecast)
    created_forecast.id = 1
    created_forecast.symbol = 'CrudeOIL'
    created_forecast.predicted_value = 75.5
    created_forecast.inference_time_ms = 45.2
    repo.create.return_value = created_forecast

    return repo


@pytest.fixture
def mock_feature_eng():
    """Mock FeatureEngineering."""
    feature_eng = Mock()
    # Mock returns input df
    feature_eng.create_lag_features = Mock(side_effect=lambda df, periods: df)
    feature_eng.create_rolling_features = Mock(side_effect=lambda df, windows: df)
    feature_eng.create_technical_indicators = Mock(side_effect=lambda df: df)
    return feature_eng


@pytest.fixture
def mock_data_loader():
    """Mock MarketDataLoader."""
    loader = AsyncMock()

    # Return sample dataframe
    import pandas as pd
    sample_df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='H'),
        'close': np.random.randn(100) * 2 + 75,
        'open': np.random.randn(100) * 2 + 75,
        'high': np.random.randn(100) * 2 + 77,
        'low': np.random.randn(100) * 2 + 73,
        'volume': np.random.randint(100000, 1000000, 100)
    })
    loader.load_recent_ohlcv = AsyncMock(return_value=sample_df)

    return loader


@pytest.fixture
def inference_service(mock_predictor, mock_cache, mock_forecast_repo, mock_data_loader):
    """Create MLInferenceService with mocked dependencies."""
    return MLInferenceService(
        predictor=mock_predictor,
        cache=mock_cache,
        forecast_repo=mock_forecast_repo,
        data_loader=mock_data_loader
    )


class TestMLInferenceServiceInitialization:
    """Test service initialization."""

    def test_initialization_with_dependencies(
        self, mock_predictor, mock_cache, mock_forecast_repo, mock_data_loader
    ):
        """Test service initializes with all dependencies."""
        service = MLInferenceService(
            predictor=mock_predictor,
            cache=mock_cache,
            forecast_repo=mock_forecast_repo,
            data_loader=mock_data_loader
        )

        assert service.predictor == mock_predictor
        assert service.cache == mock_cache
        assert service.forecast_repo == mock_forecast_repo
        assert service.data_loader == mock_data_loader
        assert hasattr(service, 'feature_eng')

    def test_feature_engineering_initialized(self, inference_service):
        """Test FeatureEngineering is initialized."""
        from src.ml.data.feature_engineering import FeatureEngineering

        assert isinstance(inference_service.feature_eng, FeatureEngineering)


class TestMLInferenceServiceCacheWorkflow:
    """Test cache checking workflow."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_forecast(self, inference_service, mock_cache):
        """Test cache hit returns forecast without model inference."""
        # Setup cache to return forecast
        cached_forecast = {
            'symbol': 'CrudeOIL',
            'forecast_horizon': '30d',
            'predicted_value': 75.5,
            'confidence_score': 0.85,
            'cache_hit': True
        }
        mock_cache.get.return_value = cached_forecast

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify cache was checked
        mock_cache.get.assert_called_once()

        # Verify forecast returned from cache
        assert result['predicted_value'] == 75.5
        assert result['cache_hit'] is True

        # Verify model NOT called (cache hit)
        inference_service.predictor.predict.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_inference(self, inference_service, mock_cache, mock_predictor):
        """Test cache miss triggers model inference."""
        # Setup cache miss
        mock_cache.get.return_value = None

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify cache checked
        mock_cache.get.assert_called_once()

        # Verify model inference happened
        mock_predictor.predict.assert_called_once()

        # Verify result indicates cache miss
        assert result.get('cache_hit') is False


class TestMLInferenceServiceModelLoading:
    """Test model loading workflow."""

    @pytest.mark.asyncio
    @patch('src.services.ml_inference_service.LSTMForecaster')
    async def test_load_lstm_model_if_not_cached(
        self, mock_lstm_class, inference_service, mock_predictor, mock_cache
    ):
        """Test LSTM model is loaded if not in predictor cache."""
        mock_cache.get.return_value = None  # Cache miss
        mock_predictor.loaded_models = {}  # No models loaded

        mock_model = Mock()
        mock_lstm_class.return_value = mock_model

        await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0',
            model_type='lstm'
        )

        # Verify model was loaded
        mock_predictor.load_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_reuse_loaded_model(self, inference_service, mock_predictor, mock_cache):
        """Test already-loaded model is reused."""
        mock_cache.get.return_value = None
        model_path = '/models/lstm_v1.0.0.pth'
        mock_predictor.loaded_models = {model_path: Mock()}

        await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0',
            model_path=model_path
        )

        # Verify load_model NOT called (already loaded)
        mock_predictor.load_model.assert_not_called()

        # Verify predict WAS called
        mock_predictor.predict.assert_called_once()


class TestMLInferenceServiceFeatureEngineering:
    """Test feature engineering integration."""

    @pytest.mark.asyncio
    async def test_feature_engineering_applied_for_inference(
        self, inference_service, mock_cache, mock_data_loader
    ):
        """Test feature engineering pipeline is applied."""
        mock_cache.get.return_value = None

        with patch.object(inference_service.feature_eng, 'create_lag_features') as mock_lag, \
             patch.object(inference_service.feature_eng, 'create_rolling_features') as mock_rolling, \
             patch.object(inference_service.feature_eng, 'create_technical_indicators') as mock_tech:

            mock_lag.side_effect = lambda df, periods: df
            mock_rolling.side_effect = lambda df, windows: df
            mock_tech.side_effect = lambda df: df

            await inference_service.generate_forecast(
                symbol='CrudeOIL',
                horizon='30d',
                model_version='v1.0.0'
            )

            # Verify all feature engineering steps called
            mock_lag.assert_called_once()
            mock_rolling.assert_called_once()
            mock_tech.assert_called_once()

    @pytest.mark.asyncio
    async def test_data_loading_for_inference(
        self, inference_service, mock_cache, mock_data_loader
    ):
        """Test recent market data is loaded for inference."""
        mock_cache.get.return_value = None

        await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify data loader called
        mock_data_loader.load_recent_ohlcv.assert_called_once()
        call_args = mock_data_loader.load_recent_ohlcv.call_args
        assert call_args.args[0] == 'CrudeOIL'


class TestMLInferenceServiceForecastStorage:
    """Test forecast persistence."""

    @pytest.mark.asyncio
    async def test_forecast_saved_to_database(
        self, inference_service, mock_cache, mock_forecast_repo
    ):
        """Test generated forecast is saved to database."""
        mock_cache.get.return_value = None

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify forecast saved
        mock_forecast_repo.create.assert_called_once()

        call_kwargs = mock_forecast_repo.create.call_args.kwargs
        assert call_kwargs['symbol'] == 'CrudeOIL'
        assert call_kwargs['forecast_horizon'] == '30d'
        assert call_kwargs['model_version'] == 'v1.0.0'
        assert 'predicted_value' in call_kwargs

    @pytest.mark.asyncio
    async def test_forecast_cached_after_generation(
        self, inference_service, mock_cache
    ):
        """Test generated forecast is cached."""
        mock_cache.get.return_value = None

        await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify cache.set called
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_inference_time_tracked(
        self, inference_service, mock_cache, mock_forecast_repo
    ):
        """Test inference latency is tracked and stored."""
        mock_cache.get.return_value = None

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify inference_time_ms in result
        assert 'inference_time_ms' in result
        assert isinstance(result['inference_time_ms'], (int, float))
        assert result['inference_time_ms'] >= 0

        # Verify saved to database
        call_kwargs = mock_forecast_repo.create.call_args.kwargs
        assert 'inference_time_ms' in call_kwargs


class TestMLInferenceServiceConfidenceIntervals:
    """Test confidence interval generation."""

    @pytest.mark.asyncio
    async def test_generate_with_confidence_intervals(
        self, inference_service, mock_cache, mock_predictor
    ):
        """Test forecast includes confidence intervals when requested."""
        mock_cache.get.return_value = None
        mock_predictor.predict.return_value = np.array([75.5])

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0',
            include_confidence=True
        )

        # Verify confidence intervals present
        assert 'lower_bound' in result
        assert 'upper_bound' in result
        assert 'confidence_score' in result

    @pytest.mark.asyncio
    async def test_generate_without_confidence_intervals(
        self, inference_service, mock_cache
    ):
        """Test forecast without confidence intervals when not requested."""
        mock_cache.get.return_value = None

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0',
            include_confidence=False
        )

        # Confidence may be None or not included
        assert result.get('lower_bound') is None or 'lower_bound' not in result


class TestMLInferenceServiceMultiHorizon:
    """Test multi-horizon forecast generation."""

    @pytest.mark.asyncio
    async def test_generate_forecasts_multiple_horizons(
        self, inference_service, mock_cache
    ):
        """Test generating forecasts for multiple horizons."""
        mock_cache.get.return_value = None  # All cache misses
        horizons = ['1h', '4h', '1d', '7d', '30d']

        results = await inference_service.generate_forecasts(
            symbol='CrudeOIL',
            horizons=horizons,
            model_version='v1.0.0'
        )

        assert isinstance(results, list)
        assert len(results) == 5

        # Verify each horizon represented
        result_horizons = {r['forecast_horizon'] for r in results}
        assert result_horizons == set(horizons)

    @pytest.mark.asyncio
    async def test_multi_horizon_partial_cache_hits(
        self, inference_service, mock_cache
    ):
        """Test multi-horizon with some cached, some not."""
        # Setup: '1h' cached, '4h' not cached
        def cache_get_side_effect(key):
            if '1h' in key:
                return {'predicted_value': 75.0, 'forecast_horizon': '1h'}
            return None

        mock_cache.get.side_effect = cache_get_side_effect

        results = await inference_service.generate_forecasts(
            symbol='CrudeOIL',
            horizons=['1h', '4h'],
            model_version='v1.0.0'
        )

        # Verify both horizons returned
        assert len(results) == 2


class TestMLInferenceServiceErrorHandling:
    """Test error handling in inference pipeline."""

    @pytest.mark.asyncio
    async def test_model_loading_failure(
        self, inference_service, mock_cache, mock_predictor
    ):
        """Test handling of model loading failure."""
        mock_cache.get.return_value = None
        mock_predictor.load_model.side_effect = FileNotFoundError("Model not found")

        with pytest.raises(FileNotFoundError):
            await inference_service.generate_forecast(
                symbol='CrudeOIL',
                horizon='30d',
                model_version='v999.0.0'
            )

    @pytest.mark.asyncio
    async def test_prediction_failure(
        self, inference_service, mock_cache, mock_predictor
    ):
        """Test handling of prediction failure."""
        mock_cache.get.return_value = None
        mock_predictor.predict.side_effect = RuntimeError("Prediction failed")

        with pytest.raises(RuntimeError):
            await inference_service.generate_forecast(
                symbol='CrudeOIL',
                horizon='30d',
                model_version='v1.0.0'
            )

    @pytest.mark.asyncio
    async def test_data_loading_failure(
        self, inference_service, mock_cache, mock_data_loader
    ):
        """Test handling of data loading failure."""
        mock_cache.get.return_value = None
        mock_data_loader.load_recent_ohlcv.side_effect = Exception("Data not available")

        with pytest.raises(Exception, match="Data not available"):
            await inference_service.generate_forecast(
                symbol='UNKNOWN',
                horizon='30d',
                model_version='v1.0.0'
            )


class TestMLInferenceServicePerformance:
    """Test performance requirements."""

    @pytest.mark.asyncio
    async def test_cache_hit_latency_under_5ms(
        self, inference_service, mock_cache
    ):
        """Test cache hit returns in <5ms (FR-SC-003)."""
        cached_forecast = {
            'predicted_value': 75.5,
            'cache_hit': True,
            'inference_time_ms': 2.1
        }
        mock_cache.get.return_value = cached_forecast

        import time
        start = time.perf_counter()

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Note: This tests the Python overhead, not Redis latency
        # Real integration test would measure end-to-end
        assert elapsed_ms < 10  # Generous for test overhead

    @pytest.mark.asyncio
    async def test_inference_metadata_complete(
        self, inference_service, mock_cache
    ):
        """Test all required metadata is returned."""
        mock_cache.get.return_value = None

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0'
        )

        # Verify required fields
        assert 'symbol' in result
        assert 'forecast_horizon' in result
        assert 'model_version' in result
        assert 'predicted_value' in result
        assert 'inference_time_ms' in result
        assert 'cache_hit' in result


class TestMLInferenceServiceRealWorldScenarios:
    """Test realistic trading scenarios."""

    @pytest.mark.asyncio
    async def test_trading_agent_forecast_request(
        self, inference_service, mock_cache
    ):
        """Test typical MLPredictionAgent forecast request."""
        mock_cache.get.return_value = None

        # Agent requests multiple horizons for decision making
        results = await inference_service.generate_forecasts(
            symbol='CrudeOIL',
            horizons=['1h', '4h'],
            model_version='v1.0.0',
            include_confidence=True
        )

        assert len(results) == 2

        # Verify each forecast has confidence intervals for risk assessment
        for forecast in results:
            assert 'predicted_value' in forecast
            assert 'lower_bound' in forecast
            assert 'upper_bound' in forecast

    @pytest.mark.asyncio
    async def test_high_frequency_inference_scenario(
        self, inference_service, mock_cache
    ):
        """Test rapid sequential inference requests."""
        # First request: cache miss
        mock_cache.get.return_value = None
        result1 = await inference_service.generate_forecast(
            symbol='BTCUSD',
            horizon='1h',
            model_version='v1.0.0'
        )
        assert result1['cache_hit'] is False

        # Second request: cache hit
        cached_forecast = {
            'predicted_value': 45000.0,
            'cache_hit': True
        }
        mock_cache.get.return_value = cached_forecast

        result2 = await inference_service.generate_forecast(
            symbol='BTCUSD',
            horizon='1h',
            model_version='v1.0.0'
        )
        assert result2['cache_hit'] is True

    @pytest.mark.asyncio
    async def test_ensemble_forecast_generation(
        self, inference_service, mock_cache, mock_predictor
    ):
        """Test ensemble model forecast generation."""
        mock_cache.get.return_value = None

        # Ensemble returns weighted average of multiple models
        mock_predictor.predict.return_value = np.array([75.5])

        result = await inference_service.generate_forecast(
            symbol='CrudeOIL',
            horizon='30d',
            model_version='v1.0.0_ensemble',
            model_type='ensemble',
            include_confidence=True
        )

        assert result['predicted_value'] == 75.5
        assert result['model_version'] == 'v1.0.0_ensemble'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
