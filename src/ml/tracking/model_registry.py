"""Model Registry - MLflow model versioning and stage management."""

from mlflow.tracking import MlflowClient


class ModelRegistry:
    """MLflow Model Registry for production model management."""
    
    def __init__(self, tracking_uri: str = "http://localhost:5000"):
        self.client = MlflowClient(tracking_uri=tracking_uri)
    
    def transition_stage(
        self,
        model_name: str,
        version: int,
        stage: str  # "Staging", "Production", "Archived"
    ):
        """Transition model version to new stage."""
        self.client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage=stage
        )
    
    def get_production_model(self, model_name: str):
        """Get latest production model."""
        return self.client.get_latest_versions(model_name, stages=["Production"])[0]
    
    def register_model(self, run_id: str, model_path: str, model_name: str):
        """Register model from MLflow run."""
        model_uri = f"runs:/{run_id}/{model_path}"
        return mlflow.register_model(model_uri, model_name)
