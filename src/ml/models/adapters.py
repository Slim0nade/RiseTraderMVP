"""
Adapters to bridge MVP and SOTA model implementations

Provides compatibility between:
- MVP: BaseModel (simple interface)
- SOTA: BaseForecaster (sophisticated nn.Module interface)
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from src.ml.models.base_model import BaseModel  # MVP
from src.ml.models.base import BaseForecaster, ForecastResult, ModelConfig  # SOTA


class SOTAtoMVPAdapter(BaseModel):
    """
    Wraps SOTA BaseForecaster to look like MVP BaseModel.

    Allows SOTA models (TCN, BiGRU, FEDformer, etc.) to be used
    with existing MVP infrastructure (API, services, repositories).
    """

    def __init__(self, sota_model: BaseForecaster):
        """
        Initialize adapter with SOTA model.

        Args:
            sota_model: SOTA model instance (BaseForecaster)
        """
        super().__init__()
        self.model = sota_model
        self.is_trained = False
        self.model_version = sota_model.model_version

    def train(self, X: np.ndarray, y: np.ndarray, X_val: Optional[np.ndarray] = None,
              y_val: Optional[np.ndarray] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert MVP train() call to SOTA fit().

        Args:
            X: Training features (numpy array)
            y: Training targets (numpy array)
            X_val: Validation features (optional)
            y_val: Validation targets (optional)
            **kwargs: Additional training parameters

        Returns:
            Dictionary of training metrics in MVP format
        """
        # Convert numpy arrays to DataFrame (SOTA expects this)
        train_df = self._arrays_to_dataframe(X, y)
        val_df = self._arrays_to_dataframe(X_val, y_val) if X_val is not None else None

        # Call SOTA fit method
        history = self.model.fit(train_df, val_df, **kwargs)
        self.is_trained = True

        # Convert SOTA history format to MVP format
        return {
            'train_loss': history.get('train_loss', [0.0])[-1] if history.get('train_loss') else 0.0,
            'val_loss': history.get('val_loss', [0.0])[-1] if val_df and history.get('val_loss') else None,
            'history': history  # Include full history for reference
        }

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Convert MVP predict() call to SOTA predict().

        Args:
            X: Features for prediction (numpy array)

        Returns:
            Array of predictions
        """
        # Convert numpy array to DataFrame
        df = self._arrays_to_dataframe(X, None)

        # Call SOTA predict method
        result: ForecastResult = self.model.predict(df, return_uncertainty=False)

        # Return just predictions (MVP interface)
        return result.predictions

    def save(self, filepath: str) -> bool:
        """
        Save SOTA model using its checkpoint system.

        Args:
            filepath: Path to save model

        Returns:
            True if successful
        """
        try:
            self.model.save(Path(filepath))
            return True
        except Exception as e:
            print(f"Error saving SOTA model: {e}")
            return False

    def load(self, filepath: str) -> bool:
        """
        Load SOTA model from checkpoint.

        Args:
            filepath: Path to load model from

        Returns:
            True if successful
        """
        try:
            self.model.load(Path(filepath))
            self.is_trained = True
            self.model_version = self.model.model_version
            return True
        except Exception as e:
            print(f"Error loading SOTA model: {e}")
            return False

    @staticmethod
    def _arrays_to_dataframe(X: Optional[np.ndarray], y: Optional[np.ndarray] = None) -> pd.DataFrame:
        """
        Convert numpy arrays to DataFrame expected by SOTA models.

        Args:
            X: Feature array (can be 2D or 3D for sequences)
            y: Target array (optional)

        Returns:
            DataFrame with features and optional target
        """
        if X is None:
            return pd.DataFrame()

        # Handle 3D arrays (batch, sequence, features) - flatten to 2D
        if X.ndim == 3:
            # Reshape (batch, seq, features) -> (batch*seq, features)
            X_flat = X.reshape(-1, X.shape[-1])
        else:
            X_flat = X

        # Create DataFrame with feature columns
        feature_cols = [f"feature_{i}" for i in range(X_flat.shape[-1])]
        df = pd.DataFrame(X_flat, columns=feature_cols)

        # Add target column if provided
        if y is not None:
            df['close'] = y.flatten() if y.ndim > 1 else y

        # Add timestamp index (required by some SOTA models)
        df['timestamp'] = pd.date_range(start='2020-01-01', periods=len(df), freq='H')

        return df


class MVPtoSOTAAdapter(BaseForecaster):
    """
    Wraps MVP BaseModel to look like SOTA BaseForecaster.

    Allows MVP models (LSTM, XGBoost) to be used in SOTA workflows
    and benefit from SOTA features like uncertainty quantification.
    """

    def __init__(self, mvp_model: BaseModel, config: ModelConfig):
        """
        Initialize adapter with MVP model.

        Args:
            mvp_model: MVP model instance (BaseModel)
            config: SOTA ModelConfig for metadata
        """
        super().__init__(config)
        self.mvp_model = mvp_model
        self._is_fitted = mvp_model.is_trained

    def forward(self, x):
        """
        Not used for MVP models (they don't use PyTorch forward pass).

        Args:
            x: Input tensor

        Raises:
            NotImplementedError: MVP models don't implement forward()
        """
        raise NotImplementedError("MVP models don't use forward() - use predict() instead")

    def fit(self, train_data: pd.DataFrame, val_data: Optional[pd.DataFrame] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert SOTA fit() to MVP train().

        Args:
            train_data: Training DataFrame
            val_data: Validation DataFrame (optional)
            **kwargs: Additional training parameters

        Returns:
            Training history in SOTA format
        """
        # Convert DataFrame to numpy arrays
        X_train, y_train = self._dataframe_to_arrays(train_data)
        X_val, y_val = self._dataframe_to_arrays(val_data) if val_data is not None else (None, None)

        # Call MVP train method
        metrics = self.mvp_model.train(X_train, y_train, X_val=X_val, y_val=y_val, **kwargs)
        self._is_fitted = True

        # Convert to SOTA history format (list of losses per epoch)
        return {
            'train_loss': [metrics.get('train_loss', 0.0)],
            'val_loss': [metrics.get('val_loss', 0.0)] if val_data is not None else []
        }

    def predict(self, data: pd.DataFrame, return_uncertainty: bool = True) -> ForecastResult:
        """
        Convert SOTA predict() to MVP predict().

        Args:
            data: Input DataFrame
            return_uncertainty: Whether to return uncertainty bounds (MVP models can't provide this)

        Returns:
            ForecastResult with predictions (no uncertainty from MVP models)
        """
        # Convert DataFrame to numpy array
        X, _ = self._dataframe_to_arrays(data)

        # Call MVP predict method
        predictions = self.mvp_model.predict(X)

        # Extract symbol if available
        symbol = data.get('symbol', pd.Series(['UNKNOWN']))[0] if 'symbol' in data.columns else 'UNKNOWN'

        # Create ForecastResult
        return ForecastResult(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            model_name=self.config.model_name,
            model_version=self.model_version,
            predictions=predictions,
            lower_bound=None,  # MVP models don't provide uncertainty
            upper_bound=None,
            confidence_scores=None,
            direction_prob=None,
            inference_time_ms=0.0,
            feature_importance=None
        )

    def save(self, path: Path) -> None:
        """
        Save MVP model using its save method.

        Args:
            path: Path to save model
        """
        self.mvp_model.save(str(path))

    def load(self, path: Path) -> None:
        """
        Load MVP model from disk.

        Args:
            path: Path to load model from
        """
        self.mvp_model.load(str(path))
        self._is_fitted = self.mvp_model.is_trained

    @staticmethod
    def _dataframe_to_arrays(df: pd.DataFrame) -> tuple:
        """
        Convert DataFrame to numpy arrays for MVP models.

        Args:
            df: Input DataFrame

        Returns:
            Tuple of (features, targets)
        """
        # Exclude metadata columns
        exclude_cols = ['close', 'symbol', 'timestamp']
        feature_cols = [c for c in df.columns if c not in exclude_cols]

        # Extract features
        X = df[feature_cols].values

        # Extract target if present
        y = df['close'].values if 'close' in df.columns else None

        return X, y
