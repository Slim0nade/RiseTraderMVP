"""
Base Model Interface for RiseTrader ML Models
All forecasting models inherit from this base class for consistency.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
import torch.nn as nn


class ForecastHorizon(str, Enum):
    """Supported forecast horizons"""
    INTRADAY = "intraday"      # 1-4 hours
    DAILY = "daily"            # 1-5 days
    WEEKLY = "weekly"          # 1-2 weeks
    MONTHLY = "monthly"        # 1 month+


class AssetType(str, Enum):
    """Supported asset types with specific configurations"""
    CRUDE_OIL = "crude_oil"    # WTI, Brent
    GOLD = "gold"              # XAUUSD
    FOREX = "forex"            # Currency pairs


@dataclass
class ModelConfig:
    """Base configuration for all models"""
    model_name: str
    asset_type: AssetType
    forecast_horizon: ForecastHorizon
    lookback_window: int
    prediction_length: int
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    seed: int = 42
    
    # Training params
    learning_rate: float = 1e-4
    batch_size: int = 32
    max_epochs: int = 100
    early_stopping_patience: int = 10
    
    @classmethod
    def for_crude_oil_daily(cls) -> "ModelConfig":
        """Optimal config for crude oil daily forecasting (TCN/GRU)"""
        return cls(
            model_name="crude_oil_daily",
            asset_type=AssetType.CRUDE_OIL,
            forecast_horizon=ForecastHorizon.DAILY,
            lookback_window=30,
            prediction_length=5,
            learning_rate=1e-3,
            batch_size=64,
        )
    
    @classmethod
    def for_crude_oil_weekly(cls) -> "ModelConfig":
        """Optimal config for crude oil weekly forecasting (FEDformer)"""
        return cls(
            model_name="crude_oil_weekly",
            asset_type=AssetType.CRUDE_OIL,
            forecast_horizon=ForecastHorizon.WEEKLY,
            lookback_window=60,
            prediction_length=14,
            learning_rate=1e-4,
            batch_size=32,
        )
    
    @classmethod
    def for_gold_daily(cls) -> "ModelConfig":
        """Optimal config for gold daily forecasting"""
        return cls(
            model_name="gold_daily",
            asset_type=AssetType.GOLD,
            forecast_horizon=ForecastHorizon.DAILY,
            lookback_window=30,
            prediction_length=5,
            learning_rate=1e-3,
            batch_size=64,
        )
    
    @classmethod
    def for_gold_weekly(cls) -> "ModelConfig":
        """Optimal config for gold weekly forecasting (DPformer/TFT)"""
        return cls(
            model_name="gold_weekly",
            asset_type=AssetType.GOLD,
            forecast_horizon=ForecastHorizon.WEEKLY,
            lookback_window=60,
            prediction_length=14,
            learning_rate=1e-4,
            batch_size=32,
        )


@dataclass
class ForecastResult:
    """Standard forecast output format"""
    timestamp: datetime
    symbol: str
    model_name: str
    model_version: str
    predictions: np.ndarray
    lower_bound: Optional[np.ndarray] = None
    upper_bound: Optional[np.ndarray] = None
    confidence_scores: Optional[np.ndarray] = None
    direction_prob: Optional[float] = None
    inference_time_ms: float = 0.0
    feature_importance: Optional[Dict[str, float]] = None


class BaseForecaster(ABC, nn.Module):
    """Abstract base class for all RiseTrader forecasting models."""
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.model_version = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._is_fitted = False
        torch.manual_seed(config.seed)
        np.random.seed(config.seed)
        
    @property
    def device(self) -> torch.device:
        return torch.device(self.config.device)
    
    @abstractmethod
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        pass
    
    @abstractmethod
    def fit(self, train_data: pd.DataFrame, val_data: Optional[pd.DataFrame] = None, **kwargs) -> Dict[str, List[float]]:
        pass
    
    @abstractmethod
    def predict(self, data: pd.DataFrame, return_uncertainty: bool = True) -> ForecastResult:
        pass
    
    def evaluate(self, y_true: np.ndarray, y_pred: np.ndarray, prices: Optional[np.ndarray] = None) -> Dict[str, float]:
        mae = np.mean(np.abs(y_true - y_pred))
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-8))) * 100
        mpe = np.mean((y_true - y_pred) / (y_true + 1e-8)) * 100
        
        metrics = {"mae": float(mae), "rmse": float(rmse), "mape": float(mape), "mpe": float(mpe)}
        
        if prices is not None and len(prices) > 1:
            true_direction = np.sign(np.diff(prices[:len(y_true)+1]))
            pred_direction = np.sign(y_pred[:-1] - prices[:len(y_pred)-1])
            if len(true_direction) > 0 and len(pred_direction) > 0:
                min_len = min(len(true_direction), len(pred_direction))
                directional_acc = np.mean(true_direction[:min_len] == pred_direction[:min_len]) * 100
                metrics["directional_accuracy"] = float(directional_acc)
        
        return metrics
    
    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = {"model_state_dict": self.state_dict(), "config": self.config, "model_version": self.model_version, "is_fitted": self._is_fitted}
        torch.save(checkpoint, path)
    
    def load(self, path: Union[str, Path]) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self.load_state_dict(checkpoint["model_state_dict"])
        self.model_version = checkpoint["model_version"]
        self._is_fitted = checkpoint["is_fitted"]


class EnsembleForecaster(BaseForecaster):
    """Base class for ensemble models"""
    
    def __init__(self, config: ModelConfig, base_models: List[BaseForecaster]):
        super().__init__(config)
        self.base_models = nn.ModuleList(base_models)
        self.n_models = len(base_models)
    
    @abstractmethod
    def combine_predictions(self, predictions: List[torch.Tensor], weights: Optional[torch.Tensor] = None) -> torch.Tensor:
        pass
