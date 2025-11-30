"""Performance Alerter - Alert when model accuracy degrades."""

from typing import Dict


class PerformanceAlerter:
    """Alert system for model performance degradation."""
    
    def __init__(self, mpe_threshold: float = 5.0, consecutive_hours: int = 3):
        self.mpe_threshold = mpe_threshold
        self.consecutive_hours = consecutive_hours
        self.degradation_counter = 0
    
    def check_and_alert(self, metrics: Dict[str, float]) -> bool:
        """Check if alert should be triggered."""
        if abs(metrics.get('mpe', 0)) > self.mpe_threshold:
            self.degradation_counter += 1
            
            if self.degradation_counter >= self.consecutive_hours:
                self._send_alert(metrics)
                self.degradation_counter = 0
                return True
        else:
            self.degradation_counter = 0
        
        return False
    
    def _send_alert(self, metrics: Dict[str, float]):
        """Send alert to monitoring system."""
        alert_message = {
            "severity": "WARNING",
            "message": f"Model performance degraded! MPE: {metrics['mpe']:.2f}%",
            "recommended_action": "Trigger model retraining",
            "metrics": metrics
        }
        # TODO: Send to monitoring system (Prometheus, Slack, PagerDuty)
        print(f"ALERT: {alert_message}")
