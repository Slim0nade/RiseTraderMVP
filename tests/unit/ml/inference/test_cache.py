"""
Unit tests for ForecastCache.
Tests Redis integration with 5-minute TTL for forecast caching.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock

from src.ml.inference.cache import ForecastCache


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = Mock()
    redis.get = Mock(return_value=None)
    redis.setex = Mock()
    return redis


@pytest.fixture
def cache_default(mock_redis):
    """Create ForecastCache with default TTL (5 minutes)."""
    return ForecastCache(mock_redis)


@pytest.fixture
def cache_custom_ttl(mock_redis):
    """Create ForecastCache with custom TTL."""
    return ForecastCache(mock_redis, ttl_seconds=600)


@pytest.fixture
def sample_forecast():
    """Sample forecast data for testing."""
    return {
        'symbol': 'CrudeOIL',
        'horizon': '30d',
        'model_version': 'v1.0.0',
        'predicted_value': 75.5,
        'confidence_lower': 73.2,
        'confidence_upper': 77.8,
        'timestamp': '2024-01-15T10:00:00Z'
    }


class TestForecastCacheInitialization:
    """Test ForecastCache initialization."""

    def test_initialization_with_default_ttl(self, mock_redis):
        """Test cache initializes with default 5-minute TTL."""
        cache = ForecastCache(mock_redis)

        assert cache.redis == mock_redis
        assert cache.ttl == 300  # 5 minutes in seconds

    def test_initialization_with_custom_ttl(self, mock_redis):
        """Test cache initializes with custom TTL."""
        cache = ForecastCache(mock_redis, ttl_seconds=600)

        assert cache.redis == mock_redis
        assert cache.ttl == 600

    def test_redis_client_stored(self, cache_default, mock_redis):
        """Test Redis client is stored as attribute."""
        assert hasattr(cache_default, 'redis')
        assert cache_default.redis == mock_redis

    def test_ttl_stored(self, cache_default):
        """Test TTL is stored as attribute."""
        assert hasattr(cache_default, 'ttl')
        assert isinstance(cache_default.ttl, int)


class TestForecastCacheGet:
    """Test get operations."""

    def test_get_cached_forecast(self, cache_default, mock_redis, sample_forecast):
        """Test retrieving cached forecast."""
        # Mock Redis returning cached data
        cached_json = json.dumps(sample_forecast)
        mock_redis.get.return_value = cached_json

        result = cache_default.get('forecast:CrudeOIL:30d:v1.0.0')

        # Verify Redis get called
        mock_redis.get.assert_called_once_with('forecast:CrudeOIL:30d:v1.0.0')

        # Verify result deserialized correctly
        assert result == sample_forecast
        assert result['predicted_value'] == 75.5

    def test_get_cache_miss(self, cache_default, mock_redis):
        """Test get returns None on cache miss."""
        mock_redis.get.return_value = None

        result = cache_default.get('forecast:GOLD:7d:v2.0.0')

        assert result is None
        mock_redis.get.assert_called_once()

    def test_get_with_different_keys(self, cache_default, mock_redis):
        """Test get with various cache keys."""
        keys = [
            'forecast:CrudeOIL:1h:v1.0.0',
            'forecast:EURUSD:4h:v2.1.0',
            'forecast:BTCUSD:1d:v3.0.0'
        ]

        for key in keys:
            mock_redis.get.return_value = None
            result = cache_default.get(key)
            assert result is None

    def test_get_deserializes_json(self, cache_default, mock_redis):
        """Test get properly deserializes JSON data."""
        forecast = {'value': 100.5, 'symbol': 'TEST', 'nested': {'key': 'value'}}
        mock_redis.get.return_value = json.dumps(forecast)

        result = cache_default.get('test_key')

        assert isinstance(result, dict)
        assert result['value'] == 100.5
        assert result['nested']['key'] == 'value'

    def test_get_handles_complex_forecast_data(self, cache_default, mock_redis):
        """Test get handles complex forecast with confidence intervals."""
        complex_forecast = {
            'symbol': 'CrudeOIL',
            'predictions': [75.1, 75.5, 76.0],
            'confidence_intervals': [[73.0, 77.0], [73.2, 77.8], [73.5, 78.0]],
            'metadata': {
                'model_type': 'lstm',
                'ensemble': True
            }
        }
        mock_redis.get.return_value = json.dumps(complex_forecast)

        result = cache_default.get('complex_key')

        assert result['predictions'] == [75.1, 75.5, 76.0]
        assert result['metadata']['ensemble'] is True

    def test_get_with_empty_string_returned(self, cache_default, mock_redis):
        """Test get handles empty string from Redis."""
        mock_redis.get.return_value = ''

        # Empty string should still try to parse as JSON, which will fail
        # This tests the actual behavior - should handle gracefully or error
        # Based on implementation, json.loads('') will raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            cache_default.get('key')


class TestForecastCacheSet:
    """Test set operations."""

    def test_set_forecast(self, cache_default, mock_redis, sample_forecast):
        """Test caching forecast with TTL."""
        key = 'forecast:CrudeOIL:30d:v1.0.0'

        cache_default.set(key, sample_forecast)

        # Verify setex called with correct arguments
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        assert call_args.args[0] == key
        assert call_args.args[1] == 300  # Default TTL
        # Verify JSON serialization
        stored_json = call_args.args[2]
        assert json.loads(stored_json) == sample_forecast

    def test_set_with_custom_ttl(self, cache_custom_ttl, mock_redis, sample_forecast):
        """Test set uses custom TTL."""
        key = 'test_key'

        cache_custom_ttl.set(key, sample_forecast)

        call_args = mock_redis.setex.call_args
        assert call_args.args[1] == 600  # Custom TTL

    def test_set_serializes_to_json(self, cache_default, mock_redis):
        """Test set properly serializes data to JSON."""
        data = {
            'number': 123,
            'string': 'test',
            'boolean': True,
            'null': None,
            'list': [1, 2, 3],
            'nested': {'key': 'value'}
        }

        cache_default.set('key', data)

        call_args = mock_redis.setex.call_args
        stored_json = call_args.args[2]

        # Verify valid JSON
        deserialized = json.loads(stored_json)
        assert deserialized == data

    def test_set_multiple_forecasts(self, cache_default, mock_redis):
        """Test setting multiple forecasts."""
        forecasts = [
            ('key1', {'value': 100.0}),
            ('key2', {'value': 200.0}),
            ('key3', {'value': 300.0})
        ]

        for key, data in forecasts:
            cache_default.set(key, data)

        assert mock_redis.setex.call_count == 3

    def test_set_overwrites_existing_key(self, cache_default, mock_redis):
        """Test setting same key overwrites previous value."""
        key = 'forecast:TEST:1h:v1.0.0'

        # Set first value
        cache_default.set(key, {'value': 100.0})

        # Set second value (overwrite)
        cache_default.set(key, {'value': 200.0})

        # Verify both calls made (Redis will handle overwriting)
        assert mock_redis.setex.call_count == 2

    def test_set_with_empty_dict(self, cache_default, mock_redis):
        """Test setting empty dictionary."""
        cache_default.set('key', {})

        call_args = mock_redis.setex.call_args
        assert json.loads(call_args.args[2]) == {}

    def test_set_with_large_forecast_data(self, cache_default, mock_redis):
        """Test caching large forecast with many fields."""
        large_forecast = {
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'horizon': '30d',
            'predictions': list(range(100)),  # 100 values
            'confidence_lower': list(range(0, 100)),
            'confidence_upper': list(range(100, 200)),
            'features_used': [f'feature_{i}' for i in range(50)],
            'metadata': {
                'timestamp': '2024-01-15T10:00:00Z',
                'model_type': 'ensemble',
                'components': ['lstm', 'xgboost', 'tft']
            }
        }

        cache_default.set('large_key', large_forecast)

        call_args = mock_redis.setex.call_args
        stored_json = call_args.args[2]
        deserialized = json.loads(stored_json)

        assert len(deserialized['predictions']) == 100
        assert len(deserialized['features_used']) == 50


class TestForecastCacheMakeKey:
    """Test cache key generation."""

    def test_make_key_standard_format(self, cache_default):
        """Test make_key generates correct format."""
        key = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')

        assert key == 'forecast:CrudeOIL:30d:v1.0.0'

    def test_make_key_different_symbols(self, cache_default):
        """Test make_key with different symbols."""
        symbols = ['CrudeOIL', 'GOLD', 'EURUSD', 'BTCUSD']

        for symbol in symbols:
            key = cache_default.make_key(symbol, '1h', 'v1.0.0')
            assert key.startswith('forecast:')
            assert symbol in key

    def test_make_key_different_horizons(self, cache_default):
        """Test make_key with different forecast horizons."""
        horizons = ['1h', '4h', '1d', '7d', '30d']

        for horizon in horizons:
            key = cache_default.make_key('CrudeOIL', horizon, 'v1.0.0')
            assert horizon in key

    def test_make_key_different_versions(self, cache_default):
        """Test make_key with different model versions."""
        versions = ['v1.0.0', 'v2.1.0', 'v3.0.0-beta']

        for version in versions:
            key = cache_default.make_key('CrudeOIL', '30d', version)
            assert version in key

    def test_make_key_uniqueness(self, cache_default):
        """Test make_key generates unique keys for different inputs."""
        key1 = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')
        key2 = cache_default.make_key('CrudeOIL', '30d', 'v2.0.0')
        key3 = cache_default.make_key('GOLD', '30d', 'v1.0.0')

        assert key1 != key2  # Different versions
        assert key1 != key3  # Different symbols
        assert key2 != key3

    def test_make_key_consistency(self, cache_default):
        """Test make_key generates same key for same inputs."""
        key1 = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')
        key2 = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')

        assert key1 == key2

    def test_make_key_with_special_characters(self, cache_default):
        """Test make_key with special characters in inputs."""
        key = cache_default.make_key('CRUDE-OIL', '1h', 'v1.0.0-beta.1')

        assert 'CRUDE-OIL' in key
        assert 'v1.0.0-beta.1' in key


class TestForecastCacheIntegration:
    """Integration tests for complete cache workflows."""

    def test_set_then_get_workflow(self, cache_default, mock_redis, sample_forecast):
        """Test complete set -> get workflow."""
        key = 'forecast:CrudeOIL:30d:v1.0.0'

        # Set forecast
        cache_default.set(key, sample_forecast)

        # Mock Redis to return what was set
        set_call_args = mock_redis.setex.call_args
        stored_json = set_call_args.args[2]
        mock_redis.get.return_value = stored_json

        # Get forecast
        result = cache_default.get(key)

        assert result == sample_forecast

    def test_make_key_then_cache_workflow(self, cache_default, mock_redis, sample_forecast):
        """Test make_key -> set -> get workflow."""
        # Generate key
        key = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')

        # Cache forecast
        cache_default.set(key, sample_forecast)

        # Retrieve forecast
        stored_json = mock_redis.setex.call_args.args[2]
        mock_redis.get.return_value = stored_json
        result = cache_default.get(key)

        assert result['symbol'] == 'CrudeOIL'
        assert result['predicted_value'] == 75.5

    def test_multiple_forecasts_workflow(self, cache_default, mock_redis):
        """Test caching multiple forecasts for different symbols."""
        forecasts = {
            'CrudeOIL': {'value': 75.5, 'horizon': '30d'},
            'GOLD': {'value': 1850.2, 'horizon': '30d'},
            'EURUSD': {'value': 1.0825, 'horizon': '30d'}
        }

        # Cache all forecasts
        for symbol, forecast in forecasts.items():
            key = cache_default.make_key(symbol, '30d', 'v1.0.0')
            cache_default.set(key, forecast)

        assert mock_redis.setex.call_count == 3

    def test_cache_miss_then_set_workflow(self, cache_default, mock_redis, sample_forecast):
        """Test cache miss followed by set (typical API pattern)."""
        key = 'forecast:CrudeOIL:30d:v1.0.0'

        # Check cache (miss)
        mock_redis.get.return_value = None
        result = cache_default.get(key)
        assert result is None

        # Generate and cache forecast
        cache_default.set(key, sample_forecast)

        # Verify cache was updated
        mock_redis.setex.assert_called_once()


class TestForecastCacheEdgeCases:
    """Test edge cases and error handling."""

    def test_get_with_invalid_json_in_cache(self, cache_default, mock_redis):
        """Test get handles invalid JSON from Redis."""
        mock_redis.get.return_value = 'invalid json {'

        with pytest.raises(json.JSONDecodeError):
            cache_default.get('key')

    def test_set_with_non_serializable_data(self, cache_default, mock_redis):
        """Test set fails with non-JSON-serializable data."""
        # Python objects like functions can't be JSON serialized
        invalid_data = {'function': lambda x: x}

        with pytest.raises(TypeError):
            cache_default.set('key', invalid_data)

    def test_cache_with_zero_ttl(self, mock_redis):
        """Test cache with zero TTL."""
        cache = ForecastCache(mock_redis, ttl_seconds=0)

        cache.set('key', {'value': 100})

        call_args = mock_redis.setex.call_args
        assert call_args.args[1] == 0

    def test_cache_with_very_large_ttl(self, mock_redis):
        """Test cache with very large TTL."""
        cache = ForecastCache(mock_redis, ttl_seconds=86400)  # 1 day

        cache.set('key', {'value': 100})

        call_args = mock_redis.setex.call_args
        assert call_args.args[1] == 86400

    def test_get_with_none_value_in_forecast(self, cache_default, mock_redis):
        """Test get handles forecasts with None values."""
        forecast = {'value': None, 'confidence': None}
        mock_redis.get.return_value = json.dumps(forecast)

        result = cache_default.get('key')

        assert result['value'] is None
        assert result['confidence'] is None


class TestForecastCacheRealWorldScenarios:
    """Test realistic trading scenarios."""

    def test_crude_oil_multi_horizon_caching(self, cache_default, mock_redis):
        """Test caching forecasts for multiple horizons."""
        horizons = {
            '1h': 75.5,
            '4h': 76.2,
            '1d': 77.0,
            '7d': 78.5,
            '30d': 80.0
        }

        for horizon, value in horizons.items():
            key = cache_default.make_key('CrudeOIL', horizon, 'v1.0.0')
            forecast = {'predicted_value': value, 'horizon': horizon}
            cache_default.set(key, forecast)

        assert mock_redis.setex.call_count == 5

    def test_model_version_rollout_scenario(self, cache_default, mock_redis):
        """Test caching during model version rollout."""
        # Old version still cached
        old_key = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')
        cache_default.set(old_key, {'value': 75.0, 'version': 'v1.0.0'})

        # New version deployed
        new_key = cache_default.make_key('CrudeOIL', '30d', 'v2.0.0')
        cache_default.set(new_key, {'value': 76.0, 'version': 'v2.0.0'})

        # Both versions coexist temporarily
        assert old_key != new_key

    def test_high_frequency_caching_scenario(self, cache_default, mock_redis):
        """Test caching with high-frequency updates."""
        key = cache_default.make_key('BTCUSD', '1h', 'v1.0.0')

        # Simulate rapid updates (every minute)
        for minute in range(5):
            forecast = {
                'value': 45000 + (minute * 100),
                'timestamp': f'2024-01-15T10:{minute:02d}:00Z'
            }
            cache_default.set(key, forecast)

        # Verify all updates cached (last one wins in Redis)
        assert mock_redis.setex.call_count == 5

    def test_ensemble_forecast_caching(self, cache_default, mock_redis):
        """Test caching ensemble forecast with multiple components."""
        ensemble_forecast = {
            'symbol': 'CrudeOIL',
            'horizon': '30d',
            'ensemble_prediction': 75.5,
            'component_predictions': {
                'lstm': 75.2,
                'xgboost': 75.8,
                'tft': 75.5
            },
            'weights': {
                'lstm': 0.4,
                'xgboost': 0.3,
                'tft': 0.3
            },
            'confidence_interval': [73.0, 78.0]
        }

        key = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0_ensemble')
        cache_default.set(key, ensemble_forecast)

        # Verify complex structure serialized
        call_args = mock_redis.setex.call_args
        stored_json = call_args.args[2]
        deserialized = json.loads(stored_json)

        assert deserialized['component_predictions']['lstm'] == 75.2

    def test_cache_invalidation_on_retrain(self, cache_default, mock_redis):
        """Test cache key changes on model retrain."""
        # Old model forecast
        old_key = cache_default.make_key('CrudeOIL', '30d', 'v1.0.0')
        cache_default.set(old_key, {'value': 75.0})

        # After retrain, new version
        new_key = cache_default.make_key('CrudeOIL', '30d', 'v1.1.0')
        cache_default.set(new_key, {'value': 76.0})

        # Keys are different, so old cache naturally invalidated
        assert old_key != new_key


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
