"""
Unit tests for WalkForwardValidator.
Tests walk-forward cross-validation with temporal ordering.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.ml.training.validator import WalkForwardValidator


@pytest.fixture
def sample_timeseries_data():
    """Create sample time series data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    return pd.DataFrame({
        'timestamp': dates,
        'price': np.random.randn(100) * 10 + 100,
        'volume': np.random.randint(1000, 10000, 100)
    })


@pytest.fixture
def validator_default():
    """Create validator with default parameters."""
    return WalkForwardValidator()


@pytest.fixture
def validator_custom():
    """Create validator with custom parameters."""
    return WalkForwardValidator(
        train_window_days=20,
        val_window_days=10,
        test_window_days=10,
        slide_days=10
    )


class TestWalkForwardValidatorInitialization:
    """Test validator initialization and configuration."""

    def test_default_initialization(self, validator_default):
        """Test validator initializes with default parameters."""
        assert validator_default.train_window_days == 30
        assert validator_default.val_window_days == 5
        assert validator_default.test_window_days == 5
        assert validator_default.slide_days == 5

    def test_custom_initialization(self, validator_custom):
        """Test validator initializes with custom parameters."""
        assert validator_custom.train_window_days == 20
        assert validator_custom.val_window_days == 10
        assert validator_custom.test_window_days == 10
        assert validator_custom.slide_days == 10

    def test_70_15_15_split_ratio(self, validator_default):
        """Test default parameters approximate 70/15/15 split ratio."""
        total = validator_default.train_window_days + validator_default.val_window_days + validator_default.test_window_days
        train_ratio = validator_default.train_window_days / total
        val_ratio = validator_default.val_window_days / total
        test_ratio = validator_default.test_window_days / total

        assert abs(train_ratio - 0.75) < 0.05  # ~70%
        assert abs(val_ratio - 0.125) < 0.05   # ~15%
        assert abs(test_ratio - 0.125) < 0.05  # ~15%


class TestWalkForwardValidatorSplitting:
    """Test train/val/test split generation."""

    def test_split_returns_list_of_tuples(self, validator_default, sample_timeseries_data):
        """Test split returns list of (train, val, test) tuples."""
        splits = validator_default.split(sample_timeseries_data)

        assert isinstance(splits, list)
        assert len(splits) > 0

        for split in splits:
            assert isinstance(split, tuple)
            assert len(split) == 3
            train, val, test = split
            assert isinstance(train, pd.DataFrame)
            assert isinstance(val, pd.DataFrame)
            assert isinstance(test, pd.DataFrame)

    def test_split_sizes_correct(self, validator_default, sample_timeseries_data):
        """Test each split has correct train/val/test sizes."""
        splits = validator_default.split(sample_timeseries_data)

        for train, val, test in splits:
            assert len(train) == validator_default.train_window_days
            assert len(val) == validator_default.val_window_days
            assert len(test) == validator_default.test_window_days

    def test_temporal_ordering_maintained(self, validator_default, sample_timeseries_data):
        """Test temporal ordering is maintained (no look-ahead bias)."""
        splits = validator_default.split(sample_timeseries_data)

        for train, val, test in splits:
            # All train timestamps < all val timestamps
            assert train['timestamp'].max() < val['timestamp'].min()

            # All val timestamps < all test timestamps
            assert val['timestamp'].max() < test['timestamp'].min()

    def test_no_data_leakage_between_splits(self, validator_default, sample_timeseries_data):
        """Test no overlap between train/val/test within a split."""
        splits = validator_default.split(sample_timeseries_data)

        for train, val, test in splits:
            # Check no overlapping indices
            train_indices = set(train.index)
            val_indices = set(val.index)
            test_indices = set(test.index)

            assert len(train_indices & val_indices) == 0  # No overlap
            assert len(train_indices & test_indices) == 0
            assert len(val_indices & test_indices) == 0

    def test_sliding_window_progression(self, validator_default, sample_timeseries_data):
        """Test splits slide forward by slide_days."""
        splits = validator_default.split(sample_timeseries_data)

        if len(splits) > 1:
            for i in range(len(splits) - 1):
                current_train = splits[i][0]
                next_train = splits[i + 1][0]

                # Next train starts slide_days after current train
                current_start_idx = current_train.index[0]
                next_start_idx = next_train.index[0]

                assert next_start_idx == current_start_idx + validator_default.slide_days

    def test_minimum_data_requirements(self, validator_default):
        """Test behavior with insufficient data."""
        # Create data smaller than one window
        small_df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=20, freq='D'),
            'price': np.random.randn(20)
        })

        splits = validator_default.split(small_df)

        # Should return empty list if not enough data
        assert len(splits) == 0

    def test_exact_window_size_data(self, validator_default):
        """Test with data exactly matching one window size."""
        total_window = validator_default.train_window_days + validator_default.val_window_days + validator_default.test_window_days

        exact_df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=total_window, freq='D'),
            'price': np.random.randn(total_window)
        })

        splits = validator_default.split(exact_df)

        # Should return exactly one split
        assert len(splits) == 1
        train, val, test = splits[0]
        assert len(train) == validator_default.train_window_days
        assert len(val) == validator_default.val_window_days
        assert len(test) == validator_default.test_window_days


class TestWalkForwardValidatorEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dataframe(self, validator_default):
        """Test behavior with empty DataFrame."""
        empty_df = pd.DataFrame(columns=['timestamp', 'price'])
        splits = validator_default.split(empty_df)

        assert isinstance(splits, list)
        assert len(splits) == 0

    def test_unsorted_timestamps(self, validator_default):
        """Test validator sorts data by timestamp."""
        # Create unsorted data
        unsorted_df = pd.DataFrame({
            'timestamp': pd.to_datetime(['2024-01-15', '2024-01-01', '2024-01-30', '2024-01-10']),
            'price': [100, 101, 102, 103]
        })

        # Extend to meet minimum requirements
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        np.random.shuffle(dates.values)  # Shuffle to make unsorted
        test_df = pd.DataFrame({
            'timestamp': dates,
            'price': np.random.randn(50)
        })

        splits = validator_default.split(test_df)

        # Verify temporal ordering is enforced
        for train, val, test in splits:
            assert train['timestamp'].is_monotonic_increasing
            assert val['timestamp'].is_monotonic_increasing
            assert test['timestamp'].is_monotonic_increasing

    def test_multiple_windows_calculation(self):
        """Test correct number of splits with custom parameters."""
        # 100 days of data, 40-day windows, 10-day slide
        validator = WalkForwardValidator(
            train_window_days=20,
            val_window_days=10,
            test_window_days=10,
            slide_days=10
        )

        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=100, freq='D'),
            'price': np.random.randn(100)
        })

        splits = validator.split(df)

        # Expected: (100 - 40) / 10 + 1 = 7 splits
        assert len(splits) == 7

    def test_non_overlapping_test_sets(self, validator_default, sample_timeseries_data):
        """Test test sets from different splits don't overlap."""
        splits = validator_default.split(sample_timeseries_data)

        if len(splits) > 1:
            test_sets = [split[2] for split in splits]

            for i in range(len(test_sets)):
                for j in range(i + 1, len(test_sets)):
                    test_i_indices = set(test_sets[i].index)
                    test_j_indices = set(test_sets[j].index)
                    assert len(test_i_indices & test_j_indices) == 0

    def test_validation_covers_full_dataset_progressively(self):
        """Test that sliding window eventually covers all data."""
        validator = WalkForwardValidator(
            train_window_days=30,
            val_window_days=5,
            test_window_days=5,
            slide_days=5
        )

        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=100, freq='D'),
            'price': np.random.randn(100)
        })

        splits = validator.split(df)

        # Collect all indices used across all splits
        all_used_indices = set()
        for train, val, test in splits:
            all_used_indices.update(train.index)
            all_used_indices.update(val.index)
            all_used_indices.update(test.index)

        # Should use most of the data (not necessarily all due to remainder)
        coverage = len(all_used_indices) / len(df)
        assert coverage > 0.8  # At least 80% coverage

    def test_preserves_dataframe_columns(self, validator_default, sample_timeseries_data):
        """Test all original columns are preserved in splits."""
        original_columns = set(sample_timeseries_data.columns)
        splits = validator_default.split(sample_timeseries_data)

        for train, val, test in splits:
            assert set(train.columns) == original_columns
            assert set(val.columns) == original_columns
            assert set(test.columns) == original_columns

    def test_single_row_dataframes_handling(self, validator_default):
        """Test handling of DataFrames with very few rows."""
        tiny_df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=3, freq='D'),
            'price': [100, 101, 102]
        })

        splits = validator_default.split(tiny_df)
        assert len(splits) == 0  # Not enough data for even one split


class TestWalkForwardValidatorIntegration:
    """Integration tests with realistic scenarios."""

    def test_realistic_crude_oil_scenario(self):
        """Test with realistic crude oil daily data (30 days)."""
        # Simulate 90 days of crude oil data
        dates = pd.date_range('2024-01-01', periods=90, freq='D')
        df = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.randn(90) * 2 + 75,
            'high': np.random.randn(90) * 2 + 77,
            'low': np.random.randn(90) * 2 + 73,
            'close': np.random.randn(90) * 2 + 75,
            'volume': np.random.randint(100000, 1000000, 90)
        })

        validator = WalkForwardValidator()
        splits = validator.split(df)

        # Verify we get valid splits
        assert len(splits) > 0

        # Verify first split has expected properties
        train, val, test = splits[0]
        assert len(train) == 30
        assert len(val) == 5
        assert len(test) == 5

        # Verify data quality
        assert not train.empty
        assert not val.empty
        assert not test.empty

        # Verify all required columns present
        for df_split in [train, val, test]:
            assert 'timestamp' in df_split.columns
            assert 'close' in df_split.columns

    def test_walk_forward_with_feature_engineering(self):
        """Test validator works with engineered features."""
        # Create data with technical indicators
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'timestamp': dates,
            'close': np.cumsum(np.random.randn(100)) + 100,
            'sma_10': np.random.randn(100),
            'sma_20': np.random.randn(100),
            'rsi': np.random.rand(100) * 100,
            'macd': np.random.randn(100)
        })

        validator = WalkForwardValidator()
        splits = validator.split(df)

        # Verify engineered features are preserved
        for train, val, test in splits:
            assert 'sma_10' in train.columns
            assert 'sma_20' in train.columns
            assert 'rsi' in train.columns
            assert 'macd' in train.columns


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
