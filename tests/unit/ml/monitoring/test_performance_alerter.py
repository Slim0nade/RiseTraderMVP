"""
Unit tests for PerformanceAlerter.
Tests threshold-based alerting for model performance degradation.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from src.ml.monitoring.performance_alerter import PerformanceAlerter, AlertLevel, AlertType


class TestPerformanceAlerter:
    """Test PerformanceAlerter functionality."""

    @pytest.fixture
    def alerter(self):
        """Create PerformanceAlerter instance."""
        mock_metrics_repo = Mock()
        mock_notification_service = Mock()

        return PerformanceAlerter(
            metrics_repo=mock_metrics_repo,
            notification_service=mock_notification_service,
            mae_threshold_warning=1.0,
            mae_threshold_critical=2.0,
            mape_threshold_warning=5.0,
            mape_threshold_critical=10.0
        )

    def test_initialization(self, alerter):
        """Test PerformanceAlerter initialization."""
        assert alerter.mae_threshold_warning == 1.0
        assert alerter.mae_threshold_critical == 2.0
        assert alerter.mape_threshold_warning == 5.0
        assert alerter.mape_threshold_critical == 10.0

    def test_check_mae_no_alert(self, alerter):
        """Test MAE check when within acceptable range."""
        mae = 0.5

        alert = alerter.check_mae_threshold(mae, "CrudeOIL", "v1.0.0")

        assert alert is None

    def test_check_mae_warning(self, alerter):
        """Test MAE check triggers warning."""
        mae = 1.5  # Between warning and critical

        alert = alerter.check_mae_threshold(mae, "CrudeOIL", "v1.0.0")

        assert alert is not None
        assert alert['level'] == AlertLevel.WARNING
        assert alert['type'] == AlertType.MAE_HIGH
        assert alert['value'] == 1.5
        assert 'CrudeOIL' in alert['message']

    def test_check_mae_critical(self, alerter):
        """Test MAE check triggers critical alert."""
        mae = 2.5  # Above critical threshold

        alert = alerter.check_mae_threshold(mae, "CrudeOIL", "v1.0.0")

        assert alert is not None
        assert alert['level'] == AlertLevel.CRITICAL
        assert alert['type'] == AlertType.MAE_HIGH
        assert alert['value'] == 2.5

    def test_check_mape_no_alert(self, alerter):
        """Test MAPE check when within acceptable range."""
        mape = 3.0

        alert = alerter.check_mape_threshold(mape, "CrudeOIL", "v1.0.0")

        assert alert is None

    def test_check_mape_warning(self, alerter):
        """Test MAPE check triggers warning."""
        mape = 7.5

        alert = alerter.check_mape_threshold(mape, "CrudeOIL", "v1.0.0")

        assert alert is not None
        assert alert['level'] == AlertLevel.WARNING
        assert alert['type'] == AlertType.MAPE_HIGH

    def test_check_mape_critical(self, alerter):
        """Test MAPE check triggers critical alert."""
        mape = 12.0

        alert = alerter.check_mape_threshold(mape, "CrudeOIL", "v1.0.0")

        assert alert is not None
        assert alert['level'] == AlertLevel.CRITICAL
        assert alert['type'] == AlertType.MAPE_HIGH

    def test_check_directional_accuracy_no_alert(self, alerter):
        """Test directional accuracy check when high."""
        accuracy = 85.0

        alert = alerter.check_directional_accuracy(accuracy, "CrudeOIL", "v1.0.0")

        assert alert is None

    def test_check_directional_accuracy_warning(self, alerter):
        """Test directional accuracy triggers warning when low."""
        accuracy = 55.0

        alert = alerter.check_directional_accuracy(accuracy, "CrudeOIL", "v1.0.0")

        assert alert is not None
        assert alert['level'] == AlertLevel.WARNING
        assert alert['type'] == AlertType.DIRECTIONAL_ACCURACY_LOW

    def test_check_directional_accuracy_critical(self, alerter):
        """Test directional accuracy triggers critical when very low."""
        accuracy = 45.0

        alert = alerter.check_directional_accuracy(accuracy, "CrudeOIL", "v1.0.0")

        assert alert is not None
        assert alert['level'] == AlertLevel.CRITICAL
        assert alert['type'] == AlertType.DIRECTIONAL_ACCURACY_LOW

    @pytest.mark.asyncio
    async def test_evaluate_metrics_no_alerts(self, alerter):
        """Test metric evaluation with good performance."""
        metrics = {
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'forecast_horizon': '1h',
            'mae': 0.5,
            'mape': 3.0,
            'directional_accuracy': 85.0
        }

        alerts = await alerter.evaluate_metrics(metrics)

        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_evaluate_metrics_multiple_alerts(self, alerter):
        """Test metric evaluation with multiple threshold violations."""
        metrics = {
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'forecast_horizon': '1h',
            'mae': 2.5,  # Critical
            'mape': 12.0,  # Critical
            'directional_accuracy': 45.0  # Critical
        }

        alerts = await alerter.evaluate_metrics(metrics)

        assert len(alerts) == 3
        assert all(alert['level'] == AlertLevel.CRITICAL for alert in alerts)

    @pytest.mark.asyncio
    async def test_send_alert_email(self, alerter):
        """Test sending alert via email notification."""
        alert = {
            'level': AlertLevel.CRITICAL,
            'type': AlertType.MAE_HIGH,
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'value': 2.5,
            'message': 'MAE is critically high'
        }

        alerter.notification_service.send_email = AsyncMock()

        await alerter.send_alert(alert)

        alerter.notification_service.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_slack(self, alerter):
        """Test sending alert via Slack notification."""
        alert = {
            'level': AlertLevel.WARNING,
            'type': AlertType.MAPE_HIGH,
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'value': 7.5,
            'message': 'MAPE is elevated'
        }

        alerter.notification_service.send_slack_message = AsyncMock()

        await alerter.send_alert(alert, channel='slack')

        alerter.notification_service.send_slack_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_model_performance(self, alerter):
        """Test continuous monitoring of model performance."""
        mock_metrics = Mock()
        mock_metrics.mae = 1.5
        mock_metrics.mape = 7.0
        mock_metrics.directional_accuracy = 55.0

        alerter.metrics_repo.get_latest_by_model = AsyncMock(return_value=mock_metrics)
        alerter.notification_service.send_email = AsyncMock()

        alerts = await alerter.monitor_model_performance(
            symbol='CrudeOIL',
            model_version='v1.0.0',
            forecast_horizon='1h'
        )

        # Should trigger 2 warnings (MAE and MAPE)
        assert len(alerts) >= 2

    @pytest.mark.asyncio
    async def test_monitor_model_no_metrics(self, alerter):
        """Test monitoring when no metrics available."""
        alerter.metrics_repo.get_latest_by_model = AsyncMock(return_value=None)

        alerts = await alerter.monitor_model_performance(
            symbol='CrudeOIL',
            model_version='v1.0.0',
            forecast_horizon='1h'
        )

        assert len(alerts) == 0

    def test_alert_serialization(self, alerter):
        """Test alert can be serialized to JSON."""
        import json

        alert = {
            'level': AlertLevel.WARNING,
            'type': AlertType.MAE_HIGH,
            'symbol': 'CrudeOIL',
            'model_version': 'v1.0.0',
            'value': 1.5,
            'message': 'MAE is elevated',
            'timestamp': datetime.utcnow().isoformat()
        }

        # Should not raise exception
        json_str = json.dumps(alert)
        assert json_str is not None

    @pytest.mark.asyncio
    async def test_batch_monitor_multiple_models(self, alerter):
        """Test monitoring multiple models in batch."""
        models = [
            {'symbol': 'CrudeOIL', 'model_version': 'v1.0.0', 'forecast_horizon': '1h'},
            {'symbol': 'CrudeOIL', 'model_version': 'v1.0.0', 'forecast_horizon': '4h'},
            {'symbol': 'EURUSD', 'model_version': 'v1.0.0', 'forecast_horizon': '1h'}
        ]

        mock_metrics = Mock()
        mock_metrics.mae = 0.5
        mock_metrics.mape = 3.0
        mock_metrics.directional_accuracy = 85.0

        alerter.metrics_repo.get_latest_by_model = AsyncMock(return_value=mock_metrics)

        all_alerts = await alerter.batch_monitor_models(models)

        assert len(all_alerts) == 0  # No alerts for good performance

    def test_custom_thresholds(self):
        """Test creating alerter with custom thresholds."""
        custom_alerter = PerformanceAlerter(
            metrics_repo=Mock(),
            notification_service=Mock(),
            mae_threshold_warning=0.5,
            mae_threshold_critical=1.0,
            mape_threshold_warning=2.0,
            mape_threshold_critical=5.0
        )

        # Should trigger warning with lower threshold
        alert = custom_alerter.check_mae_threshold(0.7, "CrudeOIL", "v1.0.0")
        assert alert is not None
        assert alert['level'] == AlertLevel.WARNING


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
