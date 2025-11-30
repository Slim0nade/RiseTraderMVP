"""Model Predictor - In-memory model loading and batch prediction."""

import numpy as np
from typing import Dict, Any, Optional


class ModelPredictor:
    """Handles model loading and prediction generation."""
    
    def __init__(self):
        self.loaded_models = {}
    
    def load_model(self, model_path: str, model_type: str):
        """Load model into memory."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        if model_type == 'lstm':
            model = LSTMForecaster(input_size=10, hidden_size=128, num_layers=2)
        else:
            model = XGBoostForecaster()
        
        model.load(model_path)
        self.loaded_models[model_path] = model
        return model
    
    def predict(self, model_path: str, X: np.ndarray) -> np.ndarray:
        """Generate predictions using loaded model."""
        if model_path not in self.loaded_models:
            raise ValueError(f"Model not loaded: {model_path}")
        
        model = self.loaded_models[model_path]
        return model.predict(X)
