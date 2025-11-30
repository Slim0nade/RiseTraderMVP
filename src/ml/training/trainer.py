"""
Model Trainer - Orchestrates model training with early stopping and metric tracking.
Based on research.md TD-005 (MLflow integration)
"""

from typing import Dict, Any, Optional
import numpy as np
from datetime import datetime


class ModelTrainer:
    """
    Coordinates model training with early stopping, validation, and metric calculation.
    """
    
    def __init__(self, model, config: Dict[str, Any]):
        self.model = model
        self.config = config
        self.training_history = []
    
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Train model with configured hyperparameters.
        """
        training_config = self.config.get('training', {})
        
        metrics = self.model.train(
            X_train,
            y_train,
            X_val=X_val,
            y_val=y_val,
            **training_config
        )
        
        self.training_history.append({
            'timestamp': datetime.utcnow(),
            'metrics': metrics
        })
        
        return metrics
    
    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, float]:
        """Evaluate model on test set."""
        predictions = self.model.predict(X_test)
        
        # Calculate evaluation metrics
        from src.ml.evaluation.metrics import calculate_metrics
        metrics = calculate_metrics(y_test, predictions)
        
        return metrics
