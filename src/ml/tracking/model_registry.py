"""
ModelRegistry - Manage ML model versions and stage transitions.

Provides lifecycle management for ML models:
- Model registration
- Stage transitions (Development → Staging → Production)
- Version management
- Model aliases
"""

from typing import Dict, Any, Optional, List
from mlflow.tracking import MlflowClient
import mlflow
import logging
from datetime import datetime


logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    MLflow Model Registry wrapper for model lifecycle management.

    Stages:
    - None: Initial registration
    - Staging: Models being tested/validated
    - Production: Models serving production traffic
    - Archived: Old models kept for reference

    Features:
    - Model registration and versioning
    - Stage transitions with approval tracking
    - Model aliases for easy reference
    - Model search and discovery
    - Rollback support
    """

    VALID_STAGES = ["None", "Staging", "Production", "Archived"]

    def __init__(self, tracking_uri: Optional[str] = None):
        """
        Initialize ModelRegistry.

        Args:
            tracking_uri: MLflow tracking server URI
        """
        self.tracking_uri = tracking_uri or "http://localhost:5000"
        mlflow.set_tracking_uri(self.tracking_uri)

        # Initialize MLflow client
        self.client = MlflowClient(tracking_uri=self.tracking_uri)

        logger.info(f"ModelRegistry initialized with tracking URI: {self.tracking_uri}")

    def register_model(
        self,
        name: str,
        run_id: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Register a new model version.

        Args:
            name: Model name (e.g., 'lstm_forecaster_crudeOIL')
            run_id: MLflow run ID containing the model
            description: Optional model description
            tags: Optional tags for the model version

        Returns:
            Model version number
        """
        try:
            # Create registered model if doesn't exist
            try:
                self.client.create_registered_model(
                    name=name,
                    description=description
                )
                logger.info(f"Created new registered model: {name}")
            except Exception:
                # Model already exists
                pass

            # Create model version
            model_version = self.client.create_model_version(
                name=name,
                source=f"runs:/{run_id}/model",
                run_id=run_id,
                description=description,
                tags=tags
            )

            version = model_version.version
            logger.info(f"Registered model {name} version {version}")

            return version

        except Exception as e:
            logger.error(f"Failed to register model {name}: {str(e)}")
            raise

    def promote_model(
        self,
        name: str,
        version: str,
        stage: str,
        archive_existing_versions: bool = True
    ):
        """
        Promote model to a new stage.

        Args:
            name: Model name
            version: Model version
            stage: Target stage ('Staging', 'Production', 'Archived')
            archive_existing_versions: Archive existing models in target stage
        """
        if stage not in self.VALID_STAGES:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {self.VALID_STAGES}")

        try:
            # Archive existing production models if promoting to production
            if stage == "Production" and archive_existing_versions:
                self._archive_existing_production_models(name)

            # Transition model to new stage
            self.client.transition_model_version_stage(
                name=name,
                version=version,
                stage=stage
            )

            logger.info(f"Promoted model {name} version {version} to {stage}")

        except Exception as e:
            logger.error(f"Failed to promote model {name} v{version} to {stage}: {str(e)}")
            raise

    def archive_model(self, name: str, version: str):
        """
        Archive a model version.

        Args:
            name: Model name
            version: Model version
        """
        self.promote_model(name, version, stage="Archived", archive_existing_versions=False)

    def get_model_version(self, name: str, version: str) -> Any:
        """
        Get specific model version details.

        Args:
            name: Model name
            version: Model version

        Returns:
            ModelVersion object
        """
        try:
            return self.client.get_model_version(name=name, version=version)
        except Exception as e:
            logger.error(f"Failed to get model {name} v{version}: {str(e)}")
            raise

    def get_latest_version(
        self,
        name: str,
        stage: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get latest model version, optionally filtered by stage.

        Args:
            name: Model name
            stage: Optional stage filter ('Staging', 'Production')

        Returns:
            Latest ModelVersion or None
        """
        try:
            filter_string = f"name='{name}'"
            versions = self.client.search_model_versions(filter_string)

            if stage:
                versions = [v for v in versions if v.current_stage == stage]

            if not versions:
                return None

            # Sort by version number (descending)
            versions.sort(key=lambda v: int(v.version), reverse=True)
            return versions[0]

        except Exception as e:
            logger.error(f"Failed to get latest version for {name}: {str(e)}")
            return None

    def list_model_versions(
        self,
        name: str,
        stage: Optional[str] = None
    ) -> List[Any]:
        """
        List all versions of a model.

        Args:
            name: Model name
            stage: Optional stage filter

        Returns:
            List of ModelVersion objects
        """
        try:
            filter_string = f"name='{name}'"
            versions = self.client.search_model_versions(filter_string)

            if stage:
                versions = [v for v in versions if v.current_stage == stage]

            # Sort by version number (descending)
            versions.sort(key=lambda v: int(v.version), reverse=True)

            return versions

        except Exception as e:
            logger.error(f"Failed to list versions for {name}: {str(e)}")
            return []

    def delete_model_version(self, name: str, version: str):
        """
        Delete a specific model version.

        Args:
            name: Model name
            version: Model version
        """
        try:
            self.client.delete_model_version(name=name, version=version)
            logger.info(f"Deleted model {name} version {version}")
        except Exception as e:
            logger.error(f"Failed to delete model {name} v{version}: {str(e)}")
            raise

    def update_model_description(
        self,
        name: str,
        version: str,
        description: str
    ):
        """
        Update model version description.

        Args:
            name: Model name
            version: Model version
            description: New description
        """
        try:
            self.client.update_model_version(
                name=name,
                version=version,
                description=description
            )
            logger.info(f"Updated description for {name} v{version}")
        except Exception as e:
            logger.error(f"Failed to update description for {name} v{version}: {str(e)}")
            raise

    def get_model_uri(
        self,
        name: str,
        stage: Optional[str] = None,
        version: Optional[str] = None
    ) -> str:
        """
        Get model URI for loading.

        Args:
            name: Model name
            stage: Stage name ('Production', 'Staging') - mutually exclusive with version
            version: Version number - mutually exclusive with stage

        Returns:
            Model URI (e.g., 'models:/model_name/Production' or 'models:/model_name/1')
        """
        if stage and version:
            raise ValueError("Cannot specify both stage and version")

        if stage:
            return f"models:/{name}/{stage}"
        elif version:
            return f"models:/{name}/{version}"
        else:
            raise ValueError("Must specify either stage or version")

    def search_models(self, filter_string: str = "") -> List[Any]:
        """
        Search registered models.

        Args:
            filter_string: MLflow filter string

        Returns:
            List of RegisteredModel objects
        """
        try:
            return self.client.search_registered_models(filter_string=filter_string)
        except Exception as e:
            logger.error(f"Failed to search models: {str(e)}")
            return []

    def set_model_alias(self, name: str, version: str, alias: str):
        """
        Set an alias for a model version.

        Aliases provide human-readable references (e.g., 'champion', 'challenger').

        Args:
            name: Model name
            version: Model version
            alias: Alias name
        """
        try:
            self.client.set_registered_model_alias(
                name=name,
                alias=alias,
                version=version
            )
            logger.info(f"Set alias '{alias}' for {name} v{version}")
        except Exception as e:
            logger.error(f"Failed to set alias for {name} v{version}: {str(e)}")
            raise

    def get_model_by_alias(self, name: str, alias: str) -> Optional[Any]:
        """
        Get model version by alias.

        Args:
            name: Model name
            alias: Alias name

        Returns:
            ModelVersion or None
        """
        try:
            return self.client.get_model_version_by_alias(name=name, alias=alias)
        except Exception as e:
            logger.error(f"Failed to get model by alias {alias}: {str(e)}")
            return None

    def rollback_to_version(
        self,
        name: str,
        version: str,
        target_stage: str = "Production"
    ):
        """
        Rollback to a previous model version.

        Archives current production model and promotes specified version.

        Args:
            name: Model name
            version: Version to rollback to
            target_stage: Stage to promote to (default: Production)
        """
        logger.info(f"Rolling back {name} to version {version}")

        # Archive current production models
        current_prod_versions = self.list_model_versions(name, stage="Production")
        for v in current_prod_versions:
            self.archive_model(name, v.version)

        # Promote rollback version
        self.promote_model(name, version, stage=target_stage, archive_existing_versions=False)

        logger.info(f"Rollback complete: {name} v{version} is now in {target_stage}")

    def _archive_existing_production_models(self, name: str):
        """
        Archive all existing production versions of a model.

        Args:
            name: Model name
        """
        prod_versions = self.list_model_versions(name, stage="Production")

        for version in prod_versions:
            self.client.transition_model_version_stage(
                name=name,
                version=version.version,
                stage="Archived"
            )
            logger.info(f"Archived {name} v{version.version} (was Production)")

    def get_model_metadata(self, name: str, version: str) -> Dict[str, Any]:
        """
        Get complete metadata for a model version.

        Args:
            name: Model name
            version: Model version

        Returns:
            Dictionary with model metadata
        """
        try:
            model_version = self.get_model_version(name, version)

            return {
                'name': name,
                'version': version,
                'stage': model_version.current_stage,
                'description': model_version.description,
                'source': model_version.source,
                'run_id': model_version.run_id,
                'creation_timestamp': model_version.creation_timestamp,
                'last_updated_timestamp': model_version.last_updated_timestamp,
                'tags': model_version.tags
            }

        except Exception as e:
            logger.error(f"Failed to get metadata for {name} v{version}: {str(e)}")
            return {}
