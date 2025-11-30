"""MLflow Tracker - Experiment tracking wrapper."""

import mlflow
from typing import Dict, Any


class MLflowTracker:
    """Wrapper for MLflow experiment tracking."""
    
    def __init__(self, tracking_uri: str = "http://localhost:5000"):
        mlflow.set_tracking_uri(tracking_uri)
        self.active_run = None
    
    def start_run(self, experiment_name: str, run_name: str):
        """Start MLflow run."""
        mlflow.set_experiment(experiment_name)
        self.active_run = mlflow.start_run(run_name=run_name)
        return self.active_run.info.run_id
    
    def log_params(self, params: Dict[str, Any]):
        """Log hyperparameters."""
        mlflow.log_params(params)
    
    def log_metrics(self, metrics: Dict[str, float], step: int = None):
        """Log metrics."""
        mlflow.log_metrics(metrics, step=step)
    
    def log_model(self, model, artifact_path: str, model_type: str = "pytorch"):
        """Log model artifacts."""
        if model_type == "pytorch":
            mlflow.pytorch.log_model(model, artifact_path)
        elif model_type == "xgboost":
            mlflow.xgboost.log_model(model, artifact_path)
    
    def end_run(self):
        """End active run."""
        if self.active_run:
            mlflow.end_run()
            self.active_run = None
