"""
Evaluation Metrics - Financial forecasting metrics (MPE, RMSE, MAE, MAPE, directional accuracy).
Based on research.md TD-007
"""

import numpy as np
from typing import Dict


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Calculate comprehensive evaluation metrics for forecasts.
    
    Args:
        y_true: Actual values
        y_pred: Predicted values
        
    Returns:
        Dictionary of metrics (MPE, RMSE, MAE, MAPE, directional_accuracy)
    """
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    
    # Mean Percentage Error (bias)
    mpe = np.mean((y_true - y_pred) / y_true) * 100
    
    # Root Mean Squared Error
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    
    # Mean Absolute Error
    mae = np.mean(np.abs(y_true - y_pred))
    
    # Mean Absolute Percentage Error
    mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100
    
    # Directional Accuracy (% correct direction predictions)
    if len(y_true) > 1:
        direction_true = np.sign(np.diff(y_true))
        direction_pred = np.sign(np.diff(y_pred))
        directional_accuracy = np.mean(direction_true == direction_pred) * 100
    else:
        directional_accuracy = None
    
    return {
        'mpe': float(mpe),
        'rmse': float(rmse),
        'mae': float(mae),
        'mape': float(mape),
        'directional_accuracy': float(directional_accuracy) if directional_accuracy is not None else None
    }
