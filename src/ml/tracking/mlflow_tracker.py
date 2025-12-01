"""
MLflowTracker - Wrapper for MLflow experiment tracking and artifact logging.

Provides simplified interface for:
- Experiment management
- Parameter and metric logging
- Model artifact storage
- Run management
"""

from typing import Dict, Any, Optional, List
import mlflow
import mlflow.pytorch
import mlflow.sklearn
from pathlib import Path
import logging
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class MLflowTracker:
    """
    MLflow tracking wrapper for ML experiment management.

    Features:
    - Experiment creation and management
    - Parameter, metric, and artifact logging
    - Model versioning and registration
    - Run search and comparison
    - Context manager support
    """

    def __init__(
        self,
        experiment_name: str,
        tracking_uri: Optional[str] = None,
        artifact_location: Optional[str] = None
    ):
        """
        Initialize MLflowTracker.

        Args:
            experiment_name: Name of the MLflow experiment
            tracking_uri: MLflow tracking server URI (e.g., 'http://localhost:5000')
            artifact_location: Location to store artifacts (optional)
        """
        self.experiment_name = experiment_name
        self.tracking_uri = tracking_uri or "http://localhost:5000"
        self.artifact_location = artifact_location

        # Set tracking URI
        mlflow.set_tracking_uri(self.tracking_uri)

        # Create or get experiment
        self.experiment_id = self._get_or_create_experiment()

        logger.info(f"MLflow tracker initialized for experiment: {experiment_name}")

    def _get_or_create_experiment(self) -> str:
        """
        Get existing experiment or create new one.

        Returns:
            Experiment ID
        """
        experiment = mlflow.get_experiment_by_name(self.experiment_name)

        if experiment is None:
            # Create new experiment
            experiment_id = mlflow.create_experiment(
                name=self.experiment_name,
                artifact_location=self.artifact_location
            )
            logger.info(f"Created new experiment: {self.experiment_name} (ID: {experiment_id})")
        else:
            experiment_id = experiment.experiment_id
            logger.info(f"Using existing experiment: {self.experiment_name} (ID: {experiment_id})")

        return experiment_id

    def start_run(
        self,
        run_name: Optional[str] = None,
        nested: bool = False,
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Start a new MLflow run.

        Args:
            run_name: Optional name for the run
            nested: Whether to create nested run
            tags: Optional tags to set for the run

        Returns:
            Run ID
        """
        run = mlflow.start_run(
            experiment_id=self.experiment_id,
            run_name=run_name,
            nested=nested,
            tags=tags
        )

        run_id = run.info.run_id
        logger.info(f"Started MLflow run: {run_name or run_id}")
        return run_id

    def end_run(self, status: str = "FINISHED"):
        """
        End the current MLflow run.

        Args:
            status: Run status ('FINISHED', 'FAILED', 'KILLED')
        """
        mlflow.end_run(status=status)
        logger.info(f"Ended MLflow run with status: {status}")

    @contextmanager
    def run(
        self,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ):
        """
        Context manager for MLflow runs.

        Example:
            with tracker.run("training_run"):
                tracker.log_param("lr", 0.001)
                tracker.log_metric("loss", 0.5)

        Args:
            run_name: Optional run name
            tags: Optional tags

        Yields:
            Run ID
        """
        try:
            run_id = self.start_run(run_name=run_name, tags=tags)
            yield run_id
        finally:
            self.end_run()

    def log_param(self, key: str, value: Any):
        """
        Log a single parameter.

        Args:
            key: Parameter name
            value: Parameter value
        """
        try:
            mlflow.log_param(key, value)
        except Exception as e:
            logger.error(f"Failed to log parameter {key}: {str(e)}")

    def log_params(self, params: Dict[str, Any]):
        """
        Log multiple parameters.

        Args:
            params: Dictionary of parameter key-value pairs
        """
        try:
            mlflow.log_params(params)
            logger.debug(f"Logged {len(params)} parameters")
        except Exception as e:
            logger.error(f"Failed to log parameters: {str(e)}")

    def log_metric(self, key: str, value: float, step: Optional[int] = None):
        """
        Log a single metric.

        Args:
            key: Metric name
            value: Metric value
            step: Optional step number for time-series metrics
        """
        try:
            mlflow.log_metric(key, value, step=step)
        except Exception as e:
            logger.error(f"Failed to log metric {key}: {str(e)}")

    def log_metrics(self, metrics: Dict[str, float], step: Optional[int] = None):
        """
        Log multiple metrics.

        Args:
            metrics: Dictionary of metric key-value pairs
            step: Optional step number
        """
        try:
            for key, value in metrics.items():
                mlflow.log_metric(key, value, step=step)
            logger.debug(f"Logged {len(metrics)} metrics")
        except Exception as e:
            logger.error(f"Failed to log metrics: {str(e)}")

    def set_tag(self, key: str, value: str):
        """
        Set a single tag.

        Args:
            key: Tag name
            value: Tag value
        """
        try:
            mlflow.set_tag(key, value)
        except Exception as e:
            logger.error(f"Failed to set tag {key}: {str(e)}")

    def set_tags(self, tags: Dict[str, str]):
        """
        Set multiple tags.

        Args:
            tags: Dictionary of tag key-value pairs
        """
        try:
            mlflow.set_tags(tags)
            logger.debug(f"Set {len(tags)} tags")
        except Exception as e:
            logger.error(f"Failed to set tags: {str(e)}")

    def log_artifact(self, local_path: str, artifact_path: Optional[str] = None):
        """
        Log an artifact file.

        Args:
            local_path: Path to local file
            artifact_path: Optional relative path within artifact directory
        """
        try:
            mlflow.log_artifact(local_path, artifact_path=artifact_path)
            logger.debug(f"Logged artifact: {local_path}")
        except Exception as e:
            logger.error(f"Failed to log artifact {local_path}: {str(e)}")

    def log_dict(self, dictionary: Dict[str, Any], file_name: str):
        """
        Log dictionary as JSON artifact.

        Args:
            dictionary: Dictionary to log
            file_name: Name of JSON file
        """
        try:
            mlflow.log_dict(dictionary, file_name)
            logger.debug(f"Logged dictionary as: {file_name}")
        except Exception as e:
            logger.error(f"Failed to log dictionary: {str(e)}")

    def log_model(
        self,
        model: Any,
        artifact_path: str = "model",
        registered_model_name: Optional[str] = None,
        signature: Optional[Any] = None,
        **kwargs
    ):
        """
        Log ML model artifact.

        Args:
            model: Model object (PyTorch, scikit-learn, etc.)
            artifact_path: Path within artifact directory
            registered_model_name: Name for model registry
            signature: Model signature (input/output schema)
            **kwargs: Additional arguments for model logging
        """
        try:
            # Detect model type and use appropriate logger
            if hasattr(model, 'state_dict'):  # PyTorch
                mlflow.pytorch.log_model(
                    pytorch_model=model,
                    artifact_path=artifact_path,
                    registered_model_name=registered_model_name,
                    signature=signature,
                    **kwargs
                )
            elif hasattr(model, 'fit') and hasattr(model, 'predict'):  # scikit-learn/XGBoost
                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path=artifact_path,
                    registered_model_name=registered_model_name,
                    signature=signature,
                    **kwargs
                )

            logger.info(f"Logged model to: {artifact_path}")

        except Exception as e:
            logger.error(f"Failed to log model: {str(e)}")

    def log_training_metadata(
        self,
        metadata: Dict[str, Any]
    ):
        """
        Log complete training metadata (params, metrics, tags).

        Args:
            metadata: Dictionary with keys: params, metrics, tags
        """
        if 'params' in metadata:
            self.log_params(metadata['params'])

        if 'metrics' in metadata:
            self.log_metrics(metadata['metrics'])

        if 'tags' in metadata:
            self.set_tags(metadata['tags'])

        logger.info("Logged complete training metadata")

    def search_runs(
        self,
        filter_string: str = "",
        max_results: int = 1000
    ) -> List[Any]:
        """
        Search runs in the experiment.

        Args:
            filter_string: Filter string (e.g., "metrics.rmse < 0.5")
            max_results: Maximum number of results

        Returns:
            List of Run objects
        """
        try:
            runs = mlflow.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string=filter_string,
                max_results=max_results
            )
            logger.debug(f"Found {len(runs)} runs")
            return runs
        except Exception as e:
            logger.error(f"Failed to search runs: {str(e)}")
            return []

    def get_run(self, run_id: str) -> Optional[Any]:
        """
        Get specific run by ID.

        Args:
            run_id: MLflow run ID

        Returns:
            Run object or None
        """
        try:
            return mlflow.get_run(run_id)
        except Exception as e:
            logger.error(f"Failed to get run {run_id}: {str(e)}")
            return None

    def get_experiment_id(self) -> str:
        """Get experiment ID."""
        return self.experiment_id
