"""
Model Predictor - In-memory model loading and batch prediction.

Supports loading models from:
- Local file paths
- MLflow Model Registry (by name and stage/version)
"""

import numpy as np
from typing import Dict, Any, Optional
import mlflow
import mlflow.pytorch
import mlflow.sklearn
import logging
from pathlib import Path

from src.ml.tracking.model_registry import ModelRegistry


logger = logging.getLogger(__name__)


class ModelPredictor:
    """
    Handles model loading and prediction generation.

    Features:
    - In-memory model caching
    - MLflow Model Registry integration
    - Automatic model type detection
    - Batch prediction support
    """

    def __init__(
        self,
        model_registry: Optional[ModelRegistry] = None,
        tracking_uri: Optional[str] = None
    ):
        """
        Initialize ModelPredictor.

        Args:
            model_registry: Optional ModelRegistry instance
            tracking_uri: MLflow tracking URI for registry
        """
        self.loaded_models = {}
        self.model_registry = model_registry or ModelRegistry(tracking_uri=tracking_uri)

        logger.info("ModelPredictor initialized")

    def load_model(
        self,
        model_path: str,
        model_type: str,
        model_name: Optional[str] = None
    ):
        """
        Load model into memory from local path.

        Args:
            model_path: Path to model file
            model_type: Type of model ('lstm', 'xgboost')
            model_name: Optional name for caching

        Returns:
            Loaded model instance
        """
        cache_key = model_name or model_path

        # Check cache first
        if cache_key in self.loaded_models:
            logger.debug(f"Using cached model: {cache_key}")
            return self.loaded_models[cache_key]

        logger.info(f"Loading model from path: {model_path}")

        try:
            from src.ml.models.lstm_forecaster import LSTMForecaster
            from src.ml.models.xgboost_forecaster import XGBoostForecaster

            if model_type == 'lstm':
                model = LSTMForecaster(input_size=10, hidden_size=128, num_layers=2)
                model.load(model_path)
            elif model_type == 'xgboost':
                model = XGBoostForecaster()
                model.load(model_path)
            else:
                raise ValueError(f"Unsupported model type: {model_type}")

            # Cache the model
            self.loaded_models[cache_key] = model
            logger.info(f"Model loaded successfully: {cache_key}")

            return model

        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {str(e)}")
            raise

    def load_model_from_registry(
        self,
        model_name: str,
        stage: Optional[str] = None,
        version: Optional[str] = None,
        model_type: str = 'pytorch'
    ):
        """
        Load model from MLflow Model Registry.

        Args:
            model_name: Registered model name
            stage: Model stage ('Production', 'Staging') - mutually exclusive with version
            version: Model version number - mutually exclusive with stage
            model_type: Model type ('pytorch', 'sklearn')

        Returns:
            Loaded model instance
        """
        # Generate cache key
        if stage:
            cache_key = f"{model_name}:{stage}"
        elif version:
            cache_key = f"{model_name}:v{version}"
        else:
            raise ValueError("Must specify either stage or version")

        # Check cache first
        if cache_key in self.loaded_models:
            logger.debug(f"Using cached model from registry: {cache_key}")
            return self.loaded_models[cache_key]

        logger.info(f"Loading model from MLflow Registry: {cache_key}")

        try:
            # Get model URI
            model_uri = self.model_registry.get_model_uri(
                name=model_name,
                stage=stage,
                version=version
            )

            # Load model using MLflow
            if model_type == 'pytorch':
                model = mlflow.pytorch.load_model(model_uri)
            elif model_type == 'sklearn' or model_type == 'xgboost':
                model = mlflow.sklearn.load_model(model_uri)
            else:
                model = mlflow.pyfunc.load_model(model_uri)

            # Cache the model
            self.loaded_models[cache_key] = model
            logger.info(f"Model loaded from registry: {cache_key}")

            return model

        except Exception as e:
            logger.error(f"Failed to load model from registry {model_name}: {str(e)}")
            raise

    def load_production_model(self, model_name: str, model_type: str = 'pytorch'):
        """
        Convenience method to load production model.

        Args:
            model_name: Registered model name
            model_type: Model type

        Returns:
            Production model instance
        """
        return self.load_model_from_registry(
            model_name=model_name,
            stage='Production',
            model_type=model_type
        )

    def predict(
        self,
        model_identifier: str,
        X: np.ndarray,
        from_registry: bool = False
    ) -> np.ndarray:
        """
        Generate predictions using loaded model.

        Args:
            model_identifier: Model path, name, or cache key
            X: Input features for prediction
            from_registry: Whether model_identifier refers to registry model

        Returns:
            Predictions array
        """
        # Get model from cache
        if model_identifier not in self.loaded_models:
            raise ValueError(f"Model not loaded: {model_identifier}. Load it first using load_model() or load_model_from_registry()")

        model = self.loaded_models[model_identifier]

        try:
            logger.debug(f"Generating predictions with model: {model_identifier}")
            predictions = model.predict(X)
            return predictions

        except Exception as e:
            logger.error(f"Prediction failed for {model_identifier}: {str(e)}")
            raise

    def predict_batch(
        self,
        model_identifier: str,
        X_batch: np.ndarray,
        batch_size: int = 32
    ) -> np.ndarray:
        """
        Generate predictions in batches for large datasets.

        Args:
            model_identifier: Model identifier
            X_batch: Large input array
            batch_size: Batch size for processing

        Returns:
            Predictions array
        """
        if model_identifier not in self.loaded_models:
            raise ValueError(f"Model not loaded: {model_identifier}")

        model = self.loaded_models[model_identifier]
        num_samples = len(X_batch)
        all_predictions = []

        logger.info(f"Generating batch predictions for {num_samples} samples")

        for i in range(0, num_samples, batch_size):
            batch = X_batch[i:i + batch_size]
            predictions = model.predict(batch)
            all_predictions.append(predictions)

        return np.concatenate(all_predictions)

    def unload_model(self, model_identifier: str):
        """
        Remove model from memory cache.

        Args:
            model_identifier: Model identifier to unload
        """
        if model_identifier in self.loaded_models:
            del self.loaded_models[model_identifier]
            logger.info(f"Unloaded model: {model_identifier}")
        else:
            logger.warning(f"Model not in cache: {model_identifier}")

    def clear_cache(self):
        """Clear all loaded models from memory."""
        num_models = len(self.loaded_models)
        self.loaded_models.clear()
        logger.info(f"Cleared {num_models} models from cache")

    def list_loaded_models(self) -> list:
        """
        Get list of currently loaded models.

        Returns:
            List of model identifiers in cache
        """
        return list(self.loaded_models.keys())

    def get_model_info(self, model_identifier: str) -> Dict[str, Any]:
        """
        Get information about a loaded model.

        Args:
            model_identifier: Model identifier

        Returns:
            Dictionary with model information
        """
        if model_identifier not in self.loaded_models:
            return {'loaded': False}

        model = self.loaded_models[model_identifier]

        return {
            'loaded': True,
            'identifier': model_identifier,
            'model_type': type(model).__name__,
            'in_cache': True
        }
