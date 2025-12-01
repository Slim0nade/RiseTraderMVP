"""
PerformanceAlerter - Monitor model performance and send alerts on degradation.

Provides:
- Threshold-based alerting for MAE, MAPE, directional accuracy
- Multi-level alerts (INFO, WARNING, CRITICAL)
- Multiple notification channels (email, Slack, webhooks)
- Batch monitoring for multiple models
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from src.database.repositories.model_metrics_repository import ModelMetricsRepository


logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of performance alerts."""
    MAE_HIGH = "mae_high"
    MAPE_HIGH = "mape_high"
    DIRECTIONAL_ACCURACY_LOW = "directional_accuracy_low"
    SAMPLE_SIZE_LOW = "sample_size_low"


class PerformanceAlerter:
    """
    Monitor ML model performance and trigger alerts on degradation.

    Features:
    - Configurable thresholds for each metric
    - Multi-level alerting (warning, critical)
    - Notification service integration
    - Batch monitoring support
    """

    def __init__(
        self,
        metrics_repo: ModelMetricsRepository,
        notification_service: Any,
        mae_threshold_warning: float = 1.0,
        mae_threshold_critical: float = 2.0,
        mape_threshold_warning: float = 5.0,
        mape_threshold_critical: float = 10.0,
        directional_accuracy_threshold_warning: float = 60.0,
        directional_accuracy_threshold_critical: float = 50.0,
        min_sample_size: int = 50
    ):
        """
        Initialize PerformanceAlerter.

        Args:
            metrics_repo: Repository for model metrics
            notification_service: Service for sending notifications
            mae_threshold_warning: MAE warning threshold
            mae_threshold_critical: MAE critical threshold
            mape_threshold_warning: MAPE warning threshold (%)
            mape_threshold_critical: MAPE critical threshold (%)
            directional_accuracy_threshold_warning: Directional accuracy warning (%)
            directional_accuracy_threshold_critical: Directional accuracy critical (%)
            min_sample_size: Minimum sample size for reliable metrics
        """
        self.metrics_repo = metrics_repo
        self.notification_service = notification_service

        # Thresholds
        self.mae_threshold_warning = mae_threshold_warning
        self.mae_threshold_critical = mae_threshold_critical
        self.mape_threshold_warning = mape_threshold_warning
        self.mape_threshold_critical = mape_threshold_critical
        self.directional_accuracy_threshold_warning = directional_accuracy_threshold_warning
        self.directional_accuracy_threshold_critical = directional_accuracy_threshold_critical
        self.min_sample_size = min_sample_size

        logger.info(
            f"PerformanceAlerter initialized with thresholds: "
            f"MAE={mae_threshold_warning}/{mae_threshold_critical}, "
            f"MAPE={mape_threshold_warning}/{mape_threshold_critical}%"
        )

    def check_mae_threshold(
        self,
        mae: float,
        symbol: str,
        model_version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if MAE exceeds thresholds.

        Args:
            mae: Mean Absolute Error value
            symbol: Trading symbol
            model_version: Model version

        Returns:
            Alert dictionary if threshold exceeded, None otherwise
        """
        if mae >= self.mae_threshold_critical:
            return {
                'level': AlertLevel.CRITICAL,
                'type': AlertType.MAE_HIGH,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'MAE',
                'value': mae,
                'threshold': self.mae_threshold_critical,
                'message': f"CRITICAL: MAE ({mae:.4f}) exceeds critical threshold ({self.mae_threshold_critical}) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }
        elif mae >= self.mae_threshold_warning:
            return {
                'level': AlertLevel.WARNING,
                'type': AlertType.MAE_HIGH,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'MAE',
                'value': mae,
                'threshold': self.mae_threshold_warning,
                'message': f"WARNING: MAE ({mae:.4f}) exceeds warning threshold ({self.mae_threshold_warning}) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }

        return None

    def check_mape_threshold(
        self,
        mape: float,
        symbol: str,
        model_version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if MAPE exceeds thresholds.

        Args:
            mape: Mean Absolute Percentage Error (%)
            symbol: Trading symbol
            model_version: Model version

        Returns:
            Alert dictionary if threshold exceeded, None otherwise
        """
        if mape >= self.mape_threshold_critical:
            return {
                'level': AlertLevel.CRITICAL,
                'type': AlertType.MAPE_HIGH,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'MAPE',
                'value': mape,
                'threshold': self.mape_threshold_critical,
                'message': f"CRITICAL: MAPE ({mape:.2f}%) exceeds critical threshold ({self.mape_threshold_critical}%) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }
        elif mape >= self.mape_threshold_warning:
            return {
                'level': AlertLevel.WARNING,
                'type': AlertType.MAPE_HIGH,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'MAPE',
                'value': mape,
                'threshold': self.mape_threshold_warning,
                'message': f"WARNING: MAPE ({mape:.2f}%) exceeds warning threshold ({self.mape_threshold_warning}%) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }

        return None

    def check_directional_accuracy(
        self,
        accuracy: float,
        symbol: str,
        model_version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if directional accuracy is below thresholds.

        Args:
            accuracy: Directional accuracy (%)
            symbol: Trading symbol
            model_version: Model version

        Returns:
            Alert dictionary if threshold violated, None otherwise
        """
        if accuracy <= self.directional_accuracy_threshold_critical:
            return {
                'level': AlertLevel.CRITICAL,
                'type': AlertType.DIRECTIONAL_ACCURACY_LOW,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'Directional Accuracy',
                'value': accuracy,
                'threshold': self.directional_accuracy_threshold_critical,
                'message': f"CRITICAL: Directional accuracy ({accuracy:.2f}%) below critical threshold ({self.directional_accuracy_threshold_critical}%) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }
        elif accuracy <= self.directional_accuracy_threshold_warning:
            return {
                'level': AlertLevel.WARNING,
                'type': AlertType.DIRECTIONAL_ACCURACY_LOW,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'Directional Accuracy',
                'value': accuracy,
                'threshold': self.directional_accuracy_threshold_warning,
                'message': f"WARNING: Directional accuracy ({accuracy:.2f}%) below warning threshold ({self.directional_accuracy_threshold_warning}%) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }

        return None

    def check_sample_size(
        self,
        sample_count: int,
        symbol: str,
        model_version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if sample size is sufficient for reliable metrics.

        Args:
            sample_count: Number of samples used for metrics
            symbol: Trading symbol
            model_version: Model version

        Returns:
            Alert if sample size too low, None otherwise
        """
        if sample_count < self.min_sample_size:
            return {
                'level': AlertLevel.WARNING,
                'type': AlertType.SAMPLE_SIZE_LOW,
                'symbol': symbol,
                'model_version': model_version,
                'metric': 'Sample Count',
                'value': sample_count,
                'threshold': self.min_sample_size,
                'message': f"WARNING: Sample size ({sample_count}) below minimum ({self.min_sample_size}) for {symbol} {model_version}",
                'timestamp': datetime.utcnow()
            }

        return None

    async def evaluate_metrics(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Evaluate all metrics against thresholds.

        Args:
            metrics: Dictionary with model metrics

        Returns:
            List of alerts triggered
        """
        alerts = []

        symbol = metrics.get('symbol', 'UNKNOWN')
        model_version = metrics.get('model_version', 'UNKNOWN')

        # Check MAE
        if 'mae' in metrics:
            alert = self.check_mae_threshold(metrics['mae'], symbol, model_version)
            if alert:
                alerts.append(alert)

        # Check MAPE
        if 'mape' in metrics:
            alert = self.check_mape_threshold(metrics['mape'], symbol, model_version)
            if alert:
                alerts.append(alert)

        # Check directional accuracy
        if 'directional_accuracy' in metrics:
            alert = self.check_directional_accuracy(
                metrics['directional_accuracy'],
                symbol,
                model_version
            )
            if alert:
                alerts.append(alert)

        # Check sample size
        if 'sample_count' in metrics:
            alert = self.check_sample_size(metrics['sample_count'], symbol, model_version)
            if alert:
                alerts.append(alert)

        return alerts

    async def send_alert(self, alert: Dict[str, Any], channel: str = 'email') -> bool:
        """
        Send alert via notification service.

        Args:
            alert: Alert dictionary
            channel: Notification channel ('email', 'slack', 'webhook')

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if channel == 'email':
                await self.notification_service.send_email(
                    subject=f"[{alert['level'].upper()}] Model Performance Alert",
                    body=alert['message'],
                    alert_data=alert
                )
            elif channel == 'slack':
                await self.notification_service.send_slack_message(
                    message=alert['message'],
                    level=alert['level'],
                    alert_data=alert
                )
            elif channel == 'webhook':
                await self.notification_service.send_webhook(
                    url=self.notification_service.webhook_url,
                    payload=alert
                )
            else:
                logger.warning(f"Unknown notification channel: {channel}")
                return False

            logger.info(f"Sent {alert['level']} alert via {channel}: {alert['type']}")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert via {channel}: {str(e)}")
            return False

    async def monitor_model_performance(
        self,
        symbol: str,
        model_version: str,
        forecast_horizon: str,
        send_notifications: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Monitor performance for a specific model and send alerts if needed.

        Args:
            symbol: Trading symbol
            model_version: Model version
            forecast_horizon: Forecast horizon
            send_notifications: Whether to send notifications for alerts

        Returns:
            List of alerts triggered
        """
        try:
            # Get latest metrics
            metrics_obj = await self.metrics_repo.get_latest_by_model(
                symbol=symbol,
                model_version=model_version,
                forecast_horizon=forecast_horizon
            )

            if not metrics_obj:
                logger.debug(f"No metrics found for {symbol} {model_version} {forecast_horizon}")
                return []

            # Convert to dictionary
            metrics = {
                'symbol': metrics_obj.symbol,
                'model_version': metrics_obj.model_version,
                'forecast_horizon': metrics_obj.forecast_horizon,
                'mae': metrics_obj.mae,
                'mape': metrics_obj.mape,
                'directional_accuracy': metrics_obj.directional_accuracy,
                'sample_count': metrics_obj.sample_count
            }

            # Evaluate metrics
            alerts = await self.evaluate_metrics(metrics)

            # Send notifications if enabled
            if send_notifications and alerts:
                for alert in alerts:
                    await self.send_alert(alert)

            if alerts:
                logger.warning(f"Generated {len(alerts)} alerts for {symbol} {model_version}")

            return alerts

        except Exception as e:
            logger.error(f"Failed to monitor model performance: {str(e)}")
            return []

    async def batch_monitor_models(
        self,
        models: List[Dict[str, str]],
        send_notifications: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Monitor multiple models in batch.

        Args:
            models: List of model specifications (symbol, version, horizon)
            send_notifications: Whether to send notifications

        Returns:
            All alerts from all models
        """
        all_alerts = []

        for model in models:
            alerts = await self.monitor_model_performance(
                symbol=model['symbol'],
                model_version=model['model_version'],
                forecast_horizon=model['forecast_horizon'],
                send_notifications=send_notifications
            )
            all_alerts.extend(alerts)

        logger.info(f"Batch monitoring complete: {len(all_alerts)} total alerts from {len(models)} models")
        return all_alerts
