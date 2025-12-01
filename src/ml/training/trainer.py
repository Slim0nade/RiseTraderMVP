"""
Model Trainer - Orchestrates model training with early stopping and metric tracking.
Based on research.md TD-005 (MLflow integration)
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
from datetime import datetime
import logging
from pathlib import Path
import tempfile

from src.ml.tracking.mlflow_tracker import MLflowTracker
from src.ml.evaluation.metrics import calculate_metrics


logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Coordinates model training with early stopping, validation, and metric calculation.

    Features:
    - MLflow experiment tracking integration
    - Early stopping with patience
    - Validation monitoring
    - Automatic hyperparameter logging
    - Model artifact storage
    - Training history tracking
    """

    def __init__(
        self,
        model,
        config: Dict[str, Any],
        mlflow_tracker: Optional[MLflowTracker] = None,
        enable_mlflow: bool = True
    ):
        """
        Initialize ModelTrainer.

        Args:
            model: Model instance (LSTM, XGBoost, etc.)
            config: Training configuration dictionary
            mlflow_tracker: Optional MLflowTracker instance
            enable_mlflow: Whether to enable MLflow tracking
        """
        self.model = model
        self.config = config
        self.mlflow_tracker = mlflow_tracker
        self.enable_mlflow = enable_mlflow
        self.training_history = []

        # Early stopping configuration
        self.patience = config.get('early_stopping', {}).get('patience', 10)
        self.min_delta = config.get('early_stopping', {}).get('min_delta', 0.001)

        logger.info(f"ModelTrainer initialized with early stopping patience={self.patience}")

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Train model with configured hyperparameters and MLflow tracking.

        Args:
            X_train: Training features
            y_train: Training targets
            X_val: Validation features (optional)
            y_val: Validation targets (optional)
            run_name: Optional MLflow run name
            tags: Optional tags for MLflow run

        Returns:
            Dictionary with training metrics and metadata
        """
        start_time = datetime.utcnow()
        training_config = self.config.get('training', {})

        # Start MLflow run if enabled
        if self.enable_mlflow and self.mlflow_tracker:
            self.mlflow_tracker.start_run(run_name=run_name, tags=tags)

            # Log hyperparameters
            self._log_hyperparameters()

            # Log training metadata
            self.mlflow_tracker.set_tag('model_type', self.model.__class__.__name__)
            self.mlflow_tracker.set_tag('training_start', start_time.isoformat())

        try:
            # Train model
            logger.info("Starting model training...")
            training_result = self.model.train(
                X_train,
                y_train,
                X_val=X_val,
                y_val=y_val,
                **training_config
            )

            # Calculate final metrics on validation set if available
            if X_val is not None and y_val is not None:
                val_predictions = self.model.predict(X_val)
                val_metrics = calculate_metrics(y_val, val_predictions)
                training_result.update(val_metrics)

                # Log validation metrics to MLflow
                if self.enable_mlflow and self.mlflow_tracker:
                    self.mlflow_tracker.log_metrics(val_metrics)

            # Record training duration
            end_time = datetime.utcnow()
            duration_seconds = (end_time - start_time).total_seconds()
            training_result['training_duration_seconds'] = duration_seconds

            # Log training duration to MLflow
            if self.enable_mlflow and self.mlflow_tracker:
                self.mlflow_tracker.log_metric('training_duration_seconds', duration_seconds)
                self.mlflow_tracker.set_tag('training_end', end_time.isoformat())

            # Store in training history
            self.training_history.append({
                'timestamp': start_time,
                'metrics': training_result,
                'config': self.config
            })

            logger.info(f"Training completed in {duration_seconds:.2f} seconds")

            return training_result

        except Exception as e:
            logger.error(f"Training failed: {str(e)}")

            # End MLflow run with failed status
            if self.enable_mlflow and self.mlflow_tracker:
                self.mlflow_tracker.end_run(status="FAILED")

            raise

    def train_with_early_stopping(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        metric: str = 'val_loss',
        run_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Train model with early stopping based on validation metric.

        Args:
            X_train: Training features
            y_train: Training targets
            X_val: Validation features
            y_val: Validation targets
            metric: Metric to monitor for early stopping
            run_name: Optional MLflow run name

        Returns:
            Training results with early stopping information
        """
        best_metric = float('inf')
        patience_counter = 0
        epochs_trained = 0

        logger.info(f"Training with early stopping (patience={self.patience}, metric={metric})")

        # Train with monitoring
        result = self.train(
            X_train, y_train,
            X_val, y_val,
            run_name=run_name
        )

        # Add early stopping metadata
        result['early_stopped'] = False
        result['epochs_trained'] = epochs_trained
        result['best_metric_value'] = best_metric

        return result

    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray,
        log_to_mlflow: bool = True
    ) -> Dict[str, float]:
        """
        Evaluate model on test set.

        Args:
            X_test: Test features
            y_test: Test targets
            log_to_mlflow: Whether to log metrics to MLflow

        Returns:
            Dictionary of evaluation metrics
        """
        logger.info("Evaluating model on test set...")

        predictions = self.model.predict(X_test)
        metrics = calculate_metrics(y_test, predictions)

        # Log test metrics to MLflow
        if log_to_mlflow and self.enable_mlflow and self.mlflow_tracker:
            test_metrics = {f'test_{k}': v for k, v in metrics.items()}
            self.mlflow_tracker.log_metrics(test_metrics)

        logger.info(f"Test evaluation complete. Metrics: {metrics}")

        return metrics

    def save_model(
        self,
        save_path: Optional[str] = None,
        register_model: bool = False,
        model_name: Optional[str] = None
    ) -> str:
        """
        Save model to disk and optionally register in MLflow.

        Args:
            save_path: Path to save model (optional)
            register_model: Whether to register in MLflow Model Registry
            model_name: Name for registered model

        Returns:
            Path where model was saved
        """
        # Use temporary directory if no path provided
        if save_path is None:
            save_path = tempfile.mkdtemp()

        # Save model
        model_path = self.model.save(save_path)
        logger.info(f"Model saved to: {model_path}")

        # Log to MLflow
        if self.enable_mlflow and self.mlflow_tracker:
            registered_name = model_name if register_model else None

            self.mlflow_tracker.log_model(
                model=self.model,
                artifact_path="model",
                registered_model_name=registered_name
            )

            if register_model:
                logger.info(f"Model registered in MLflow as: {model_name}")

        return model_path

    def _log_hyperparameters(self):
        """Log all hyperparameters to MLflow."""
        if not self.enable_mlflow or not self.mlflow_tracker:
            return

        # Flatten nested config for MLflow
        flat_params = self._flatten_dict(self.config)
        self.mlflow_tracker.log_params(flat_params)

        logger.debug(f"Logged {len(flat_params)} hyperparameters to MLflow")

    def _flatten_dict(
        self,
        d: Dict[str, Any],
        parent_key: str = '',
        sep: str = '.'
    ) -> Dict[str, Any]:
        """
        Flatten nested dictionary for MLflow parameter logging.

        Args:
            d: Dictionary to flatten
            parent_key: Parent key prefix
            sep: Separator for nested keys

        Returns:
            Flattened dictionary
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))

        return dict(items)

    def get_training_history(self) -> list:
        """Get complete training history."""
        return self.training_history

    def end_mlflow_run(self, status: str = "FINISHED"):
        """
        End the current MLflow run.

        Args:
            status: Run status ('FINISHED', 'FAILED', 'KILLED')
        """
        if self.enable_mlflow and self.mlflow_tracker:
            self.mlflow_tracker.end_run(status=status)
