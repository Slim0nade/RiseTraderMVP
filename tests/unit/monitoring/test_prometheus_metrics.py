"""
Unit tests for Prometheus metrics recording.
Tests metric recording for training, inference, and accuracy.
"""

import pytest
from unittest.mock import Mock, patch

from src.monitoring.prometheus_metrics import PrometheusMetricsRecorder


class TestPrometheusMetricsRecorder:
    """Test Prometheus metrics recording."""

    def test_record_training_duration(self):
        """Test recording training duration."""
        # Should not raise exception
        PrometheusMetricsRecorder.record_training_duration(
            symbol='CrudeOIL',
            model_type='lstm',
            model_version='v1.0.0',
            duration_seconds=1200.5
        )

    def test_record_training_completion(self):
        """Test recording training completion."""
        PrometheusMetricsRecorder.record_training_completion(
            symbol='CrudeOIL',
            model_type='lstm',
            status='completed'
        )

    def test_record_training_failure(self):
        """Test recording training failure."""
        PrometheusMetricsRecorder.record_training_failure(
            symbol='CrudeOIL',
            model_type='xgboost',
            error_type='insufficient_data'
        )

    def test_record_inference_latency(self):
        """Test recording inference latency."""
        PrometheusMetricsRecorder.record_inference_latency(
            symbol='CrudeOIL',
            model_type='ensemble',
            forecast_horizon='1h',
            latency_seconds=0.045
        )

    def test_record_inference_request_cache_hit(self):
        """Test recording inference request with cache hit."""
        PrometheusMetricsRecorder.record_inference_request(
            symbol='CrudeOIL',
            model_type='lstm',
            forecast_horizon='4h',
            cache_hit=True
        )

    def test_record_inference_request_cache_miss(self):
        """Test recording inference request with cache miss."""
        PrometheusMetricsRecorder.record_inference_request(
            symbol='EURUSD',
            model_type='xgboost',
            forecast_horizon='1d',
            cache_hit=False
        )

    def test_record_model_accuracy_full(self):
        """Test recording full model accuracy metrics."""
        PrometheusMetricsRecorder.record_model_accuracy(
            symbol='CrudeOIL',
            model_version='v1.0.0',
            forecast_horizon='1h',
            mae=0.25,
            mape=3.5,
            rmse=0.32,
            directional_accuracy=85.5
        )

    def test_record_model_accuracy_without_directional(self):
        """Test recording accuracy without directional accuracy."""
        PrometheusMetricsRecorder.record_model_accuracy(
            symbol='CrudeOIL',
            model_version='v1.0.0',
            forecast_horizon='4h',
            mae=0.45,
            mape=5.2,
            rmse=0.58
        )

    def test_record_forecast_generated(self):
        """Test recording forecast generation."""
        PrometheusMetricsRecorder.record_forecast_generated(
            symbol='CrudeOIL',
            model_type='ensemble',
            forecast_horizon='1h'
        )

    def test_record_model_stage_transition(self):
        """Test recording model stage transition."""
        PrometheusMetricsRecorder.record_model_stage_transition(
            model_name='lstm_forecaster_CrudeOIL',
            from_stage='Staging',
            to_stage='Production'
        )

    def test_update_model_counts(self):
        """Test updating model stage counts."""
        PrometheusMetricsRecorder.update_model_counts(
            production_count=3,
            staging_count=2
        )

    def test_record_market_data_load(self):
        """Test recording market data load."""
        PrometheusMetricsRecorder.record_data_load(
            symbol='CrudeOIL',
            duration_seconds=1.5,
            data_points=10000,
            data_type='market'
        )

    def test_record_exogenous_data_load(self):
        """Test recording exogenous data load."""
        PrometheusMetricsRecorder.record_data_load(
            symbol='DXY',
            duration_seconds=0.8,
            data_points=5000,
            data_type='exogenous'
        )

    def test_record_mlflow_model_load(self):
        """Test recording MLflow model load."""
        PrometheusMetricsRecorder.record_mlflow_model_load(
            model_name='lstm_forecaster_CrudeOIL',
            stage='Production'
        )

    def test_record_mlflow_model_registration(self):
        """Test recording MLflow model registration."""
        PrometheusMetricsRecorder.record_mlflow_model_registration(
            model_name='xgboost_forecaster_EURUSD'
        )

    def test_error_handling(self):
        """Test error handling in metrics recording."""
        # Should not raise exception even with invalid inputs
        PrometheusMetricsRecorder.record_training_duration(
            symbol='',
            model_type='',
            model_version='',
            duration_seconds=-1.0
        )

    def test_multiple_recordings(self):
        """Test recording multiple metrics in sequence."""
        # Simulate full training workflow
        PrometheusMetricsRecorder.record_training_duration(
            symbol='CrudeOIL',
            model_type='lstm',
            model_version='v1.0.0',
            duration_seconds=600.0
        )

        PrometheusMetricsRecorder.record_training_completion(
            symbol='CrudeOIL',
            model_type='lstm',
            status='completed'
        )

        PrometheusMetricsRecorder.record_model_accuracy(
            symbol='CrudeOIL',
            model_version='v1.0.0',
            forecast_horizon='1h',
            mae=0.25,
            mape=3.5,
            rmse=0.32,
            directional_accuracy=85.5
        )

        # Should complete without errors


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
