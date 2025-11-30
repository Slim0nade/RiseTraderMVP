"""
XGBoost Forecaster - Gradient boosted trees for time series forecasting
Based on research.md TD-002: XGBoost with engineered features
"""

import xgboost as xgb
import numpy as np
from typing import Dict, Any, Optional, List
from pathlib import Path

from .base_model import BaseModel


class XGBoostForecaster(BaseModel):
    """
    XGBoost forecaster for time series prediction.
    
    Features:
    - Gradient boosted decision trees
    - Early stopping on validation set
    - Feature importance tracking
    - Regularization (L1/L2)
    
    Based on research.md TD-002.
    """
    
    def __init__(
        self,
        max_depth: int = 6,
        learning_rate: float = 0.1,
        n_estimators: int = 100,
        objective: str = 'reg:squarederror',
        booster: str = 'gbtree',
        gamma: float = 0,
        min_child_weight: int = 1,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0,
        reg_lambda: float = 1,
        random_state: Optional[int] = None,
        early_stopping_rounds: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize XGBoost forecaster.
        
        Args:
            max_depth: Maximum tree depth
            learning_rate: Learning rate (eta)
            n_estimators: Number of boosting rounds
            objective: Loss function ('reg:squarederror', 'reg:absoluteerror')
            booster: Booster type ('gbtree', 'gblinear', 'dart')
            gamma: Minimum loss reduction for split
            min_child_weight: Minimum sum of instance weight in child
            subsample: Subsample ratio of training instances
            colsample_bytree: Subsample ratio of columns when constructing each tree
            reg_alpha: L1 regularization term on weights
            reg_lambda: L2 regularization term on weights
            random_state: Random seed for reproducibility
            early_stopping_rounds: Rounds for early stopping (None = disabled)
        """
        super().__init__()
        
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.n_estimators = n_estimators
        self.objective = objective
        self.booster = booster
        self.gamma = gamma
        self.min_child_weight = min_child_weight
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.random_state = random_state
        self.early_stopping_rounds = early_stopping_rounds
        
        # XGBoost model (will be initialized during training)
        self.model = None
        self.feature_names = None
        self.n_features = None
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        feature_names: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Train the XGBoost model.
        
        Args:
            X: Training features (2D array: samples x features)
            y: Training targets (1D array)
            X_val: Validation features
            y_val: Validation targets
            feature_names: List of feature names for interpretability
            
        Returns:
            Dictionary of training metrics
        """
        # Validate input shape
        if X.ndim != 2:
            raise ValueError(
                f"X must be 2D array with shape (samples, features), "
                f"got shape {X.shape}"
            )
        
        self.n_features = X.shape[1]
        self.feature_names = feature_names or [f"f{i}" for i in range(self.n_features)]
        
        # Create DMatrix for XGBoost
        dtrain = xgb.DMatrix(X, label=y, feature_names=self.feature_names)
        
        # Setup parameters
        params = {
            'max_depth': self.max_depth,
            'learning_rate': self.learning_rate,
            'objective': self.objective,
            'booster': self.booster,
            'gamma': self.gamma,
            'min_child_weight': self.min_child_weight,
            'subsample': self.subsample,
            'colsample_bytree': self.colsample_bytree,
            'reg_alpha': self.reg_alpha,
            'reg_lambda': self.reg_lambda,
            'seed': self.random_state,
            'verbosity': 0
        }
        
        # Setup evaluation
        evals = [(dtrain, 'train')]
        evals_result = {}
        
        if X_val is not None and y_val is not None:
            dval = xgb.DMatrix(X_val, label=y_val, feature_names=self.feature_names)
            evals.append((dval, 'val'))
        
        # Train model
        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=self.n_estimators,
            evals=evals,
            early_stopping_rounds=self.early_stopping_rounds,
            evals_result=evals_result,
            verbose_eval=False
        )
        
        self.is_trained = True
        
        # Calculate final metrics
        train_preds = self.model.predict(dtrain)
        train_rmse = np.sqrt(np.mean((y - train_preds) ** 2))
        
        metrics = {
            'train_rmse': train_rmse,
            'best_iteration': self.model.best_iteration if hasattr(self.model, 'best_iteration') else self.n_estimators
        }
        
        if X_val is not None:
            val_preds = self.model.predict(dval)
            val_rmse = np.sqrt(np.mean((y_val - val_preds) ** 2))
            metrics['val_rmse'] = val_rmse
        
        return metrics
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.
        
        Args:
            X: Input features (2D array: samples x features)
            
        Returns:
            Predictions array (1D)
        """
        if not self.is_trained:
            raise ValueError("Model has not been trained yet")
        
        if X.shape[1] != self.n_features:
            raise ValueError(
                f"Feature dimension mismatch: expected {self.n_features}, "
                f"got {X.shape[1]}"
            )
        
        dtest = xgb.DMatrix(X, feature_names=self.feature_names)
        predictions = self.model.predict(dtest)
        
        return predictions
    
    def get_feature_importance(self, importance_type: str = 'weight') -> Dict[str, float]:
        """
        Get feature importance scores.
        
        Args:
            importance_type: Type of importance ('weight', 'gain', 'cover')
            
        Returns:
            Dictionary mapping feature names to importance scores
        """
        if not self.is_trained:
            raise ValueError("Model has not been trained yet")
        
        importance = self.model.get_score(importance_type=importance_type)
        
        # Ensure all features are present (even if zero importance)
        full_importance = {name: 0.0 for name in self.feature_names}
        full_importance.update(importance)
        
        return full_importance
    
    def save(self, filepath: str) -> bool:
        """
        Save model to disk.
        
        Args:
            filepath: Path to save model (will be saved as JSON)
            
        Returns:
            True if successful
        """
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        # XGBoost native save format (JSON)
        self.model.save_model(filepath)
        
        # Save metadata
        metadata_path = Path(filepath).with_suffix('.meta.npy')
        metadata = {
            'feature_names': self.feature_names,
            'n_features': self.n_features,
            'is_trained': self.is_trained
        }
        np.save(metadata_path, metadata)
        
        return True
    
    def load(self, filepath: str) -> bool:
        """
        Load model from disk.
        
        Args:
            filepath: Path to load model from
            
        Returns:
            True if successful
        """
        # Load model
        self.model = xgb.Booster()
        self.model.load_model(filepath)
        
        # Load metadata
        metadata_path = Path(filepath).with_suffix('.meta.npy')
        metadata = np.load(metadata_path, allow_pickle=True).item()
        
        self.feature_names = metadata['feature_names']
        self.n_features = metadata['n_features']
        self.is_trained = metadata['is_trained']
        
        return True
