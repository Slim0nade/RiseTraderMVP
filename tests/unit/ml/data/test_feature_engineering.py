"""
Unit tests for FeatureEngineering
Tests lag features, rolling statistics, and technical indicators
Based on research.md TD-002
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from src.ml.data.feature_engineering import FeatureEngineering


@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data for feature engineering"""
    dates = pd.date_range(start='2025-11-01', periods=200, freq='1H')
    data = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.uniform(75, 80, 200),
        'high': np.random.uniform(80, 85, 200),
        'low': np.random.uniform(70, 75, 200),
        'close': np.random.uniform(75, 80, 200),
        'volume': np.random.uniform(1000, 5000, 200),
    })
    return data


class TestFeatureEngineering:
    """Test suite for FeatureEngineering"""

    def test_create_lag_features(self, sample_ohlcv_data):
        """Test creation of lag features for XGBoost"""
        fe = FeatureEngineering()

        lag_periods = [1, 2, 3, 5, 10, 20, 60]
        df = fe.create_lag_features(sample_ohlcv_data, lag_periods=lag_periods)

        # Check lag features created
        for lag in lag_periods:
            assert f'close_lag_{lag}' in df.columns
            assert f'volume_lag_{lag}' in df.columns

        # Check lag values are correct
        assert df['close_lag_1'].iloc[1] == sample_ohlcv_data['close'].iloc[0]

    def test_create_rolling_statistics(self, sample_ohlcv_data):
        """Test creation of rolling window statistics"""
        fe = FeatureEngineering()

        windows = [5, 10, 20]
        df = fe.create_rolling_statistics(sample_ohlcv_data, windows=windows)

        # Check rolling features created
        for window in windows:
            assert f'close_rolling_mean_{window}' in df.columns
            assert f'close_rolling_std_{window}' in df.columns
            assert f'close_rolling_min_{window}' in df.columns
            assert f'close_rolling_max_{window}' in df.columns

    def test_calculate_rsi(self, sample_ohlcv_data):
        """Test RSI (Relative Strength Index) calculation"""
        fe = FeatureEngineering()

        df = fe.calculate_rsi(sample_ohlcv_data, period=14)

        assert 'rsi_14' in df.columns
        # RSI should be between 0 and 100
        assert df['rsi_14'].min() >= 0
        assert df['rsi_14'].max() <= 100

    def test_calculate_macd(self, sample_ohlcv_data):
        """Test MACD calculation"""
        fe = FeatureEngineering()

        df = fe.calculate_macd(
            sample_ohlcv_data,
            fast_period=12,
            slow_period=26,
            signal_period=9
        )

        assert 'macd' in df.columns
        assert 'macd_signal' in df.columns
        assert 'macd_histogram' in df.columns

    def test_calculate_bollinger_bands(self, sample_ohlcv_data):
        """Test Bollinger Bands calculation"""
        fe = FeatureEngineering()

        df = fe.calculate_bollinger_bands(sample_ohlcv_data, period=20, std_dev=2)

        assert 'bb_upper' in df.columns
        assert 'bb_lower' in df.columns
        assert 'bb_middle' in df.columns

        # Upper band should be > lower band
        assert (df['bb_upper'] >= df['bb_lower']).all()

    def test_calculate_atr(self, sample_ohlcv_data):
        """Test ATR (Average True Range) calculation"""
        fe = FeatureEngineering()

        df = fe.calculate_atr(sample_ohlcv_data, period=14)

        assert 'atr' in df.columns
        # ATR should be positive
        assert (df['atr'].dropna() >= 0).all()

    def test_create_all_technical_indicators(self, sample_ohlcv_data):
        """Test creating all technical indicators at once"""
        fe = FeatureEngineering()

        indicators = ['rsi_14', 'macd', 'bb_upper', 'bb_lower', 'atr']
        df = fe.create_technical_indicators(sample_ohlcv_data, indicators=indicators)

        for indicator in indicators:
            assert indicator in df.columns

    def test_normalize_features(self, sample_ohlcv_data):
        """Test feature normalization (Z-score)"""
        fe = FeatureEngineering()

        # Add some features first
        df = fe.create_lag_features(sample_ohlcv_data, lag_periods=[1, 2, 3])

        # Normalize
        df_normalized = fe.normalize_features(df, method='z-score')

        # Check normalization applied
        for col in df.select_dtypes(include=[np.number]).columns:
            if col not in ['timestamp']:
                mean = df_normalized[col].mean()
                std = df_normalized[col].std()
                # Z-score normalized should have ~0 mean, ~1 std
                assert abs(mean) < 0.1  # Close to 0
                assert abs(std - 1.0) < 0.1  # Close to 1

    def test_handle_missing_values(self, sample_ohlcv_data):
        """Test handling of missing values in features"""
        fe = FeatureEngineering()

        # Introduce missing values
        sample_ohlcv_data.loc[10:15, 'close'] = np.nan

        # Create features (will have NaNs)
        df = fe.create_lag_features(sample_ohlcv_data, lag_periods=[1, 2, 3])

        # Handle missing values
        df_clean = fe.handle_missing_values(df, method='forward_fill')

        # Should have no missing values
        assert df_clean.isna().sum().sum() == 0

    def test_create_returns_features(self, sample_ohlcv_data):
        """Test creation of return features"""
        fe = FeatureEngineering()

        periods = [1, 5, 10]
        df = fe.create_returns(sample_ohlcv_data, periods=periods)

        for period in periods:
            assert f'returns_{period}' in df.columns
            assert f'log_returns_{period}' in df.columns

    def test_create_volatility_features(self, sample_ohlcv_data):
        """Test creation of volatility features"""
        fe = FeatureEngineering()

        df = fe.create_volatility(sample_ohlcv_data, window=20)

        assert 'volatility_20' in df.columns
        # Volatility should be non-negative
        assert (df['volatility_20'].dropna() >= 0).all()

    def test_feature_engineering_pipeline(self, sample_ohlcv_data):
        """Test complete feature engineering pipeline"""
        fe = FeatureEngineering()

        config = {
            'lag_periods': [1, 2, 3, 5, 10],
            'rolling_windows': [5, 10, 20],
            'indicators': ['rsi_14', 'macd', 'bb_upper', 'bb_lower', 'atr'],
            'return_periods': [1, 5, 10],
            'normalize': True
        }

        df = fe.transform(sample_ohlcv_data, config=config)

        # Check all feature types created
        assert 'close_lag_1' in df.columns
        assert 'close_rolling_mean_10' in df.columns
        assert 'rsi_14' in df.columns
        assert 'returns_1' in df.columns

        # Should have no missing values after pipeline
        assert df.isna().sum().sum() == 0

    def test_feature_importance_tracking(self, sample_ohlcv_data):
        """Test tracking which features were created"""
        fe = FeatureEngineering()

        df = fe.create_lag_features(sample_ohlcv_data, lag_periods=[1, 2, 3])

        feature_list = fe.get_feature_names()

        assert 'close_lag_1' in feature_list
        assert 'close_lag_2' in feature_list
        assert 'close_lag_3' in feature_list

    def test_exogenous_feature_merge(self, sample_ohlcv_data):
        """Test merging exogenous variables (DXY, VIX) with OHLCV data"""
        fe = FeatureEngineering()

        # Create sample exogenous data
        exogenous_data = pd.DataFrame({
            'timestamp': sample_ohlcv_data['timestamp'],
            'DXY': np.random.uniform(100, 110, len(sample_ohlcv_data)),
            'VIX': np.random.uniform(15, 25, len(sample_ohlcv_data)),
        })

        df = fe.merge_exogenous_features(sample_ohlcv_data, exogenous_data)

        assert 'DXY' in df.columns
        assert 'VIX' in df.columns
        # Should have same length
        assert len(df) == len(sample_ohlcv_data)

    def test_create_features_for_lstm(self, sample_ohlcv_data):
        """Test feature creation optimized for LSTM (sequences)"""
        fe = FeatureEngineering()

        lookback = 60
        sequences = fe.create_sequences_for_lstm(
            sample_ohlcv_data,
            lookback_window=lookback,
            target_column='close'
        )

        X, y = sequences

        # Check shape: (samples, lookback, features)
        assert X.shape[1] == lookback
        assert len(X) == len(y)

    def test_create_features_for_xgboost(self, sample_ohlcv_data):
        """Test feature creation optimized for XGBoost (tabular)"""
        fe = FeatureEngineering()

        df = fe.create_features_for_xgboost(
            sample_ohlcv_data,
            lag_periods=[1, 2, 3, 5, 10],
            rolling_windows=[5, 10, 20],
            indicators=['rsi_14', 'macd']
        )

        # Should have lag features
        assert 'close_lag_1' in df.columns
        # Should have rolling features
        assert 'close_rolling_mean_10' in df.columns
        # Should have indicators
        assert 'rsi_14' in df.columns
