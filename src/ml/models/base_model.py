"""
BaseModel - Abstract base class for ML forecasting models
Defines common interface for LSTM and XGBoost models
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import numpy as np


class BaseModel(ABC):
    """
    Abstract base class for ML forecasting models

    All models (LSTM, XGBoost) must implement:
    - train(): Train the model on data
    - predict(): Generate predictions
    - save(): Save model to disk
    - load(): Load model from disk
    """

    def __init__(self):
        """Initialize base model"""
        self.is_trained = False
        self.model_version = None

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Train the model on data

        Args:
            X: Training features
            y: Training targets
            **kwargs: Additional training parameters

        Returns:
            Dictionary of training metrics
        """
        pass

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions

        Args:
            X: Features for prediction

        Returns:
            Array of predictions
        """
        pass

    @abstractmethod
    def save(self, filepath: str) -> bool:
        """
        Save model to disk

        Args:
            filepath: Path to save model

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def load(self, filepath: str) -> bool:
        """
        Load model from disk

        Args:
            filepath: Path to load model from

        Returns:
            True if successful
        """
        pass
