"""
Temporal Convolutional Network (TCN) for RiseTrader
Best performer for daily Crude Oil forecasting per 2023-2025 research:
- WTI MAE: 1.444
- Brent MAE: 1.295
"""
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from ..base import BaseForecaster, ForecastResult, ModelConfig


@dataclass
class TCNConfig(ModelConfig):
    """TCN-specific configuration"""
    num_channels: List[int] = None  # Channel sizes per layer
    kernel_size: int = 3
    dropout: float = 0.2
    use_skip_connections: bool = True
    use_weight_norm: bool = True
    
    def __post_init__(self):
        if self.num_channels is None:
            # Default: 4 layers with increasing channels
            self.num_channels = [64, 128, 256, 128]


class CausalConv1d(nn.Module):
    """Causal convolution - no future leakage"""
    
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int = 1,
        use_weight_norm: bool = True
    ):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        
        conv = nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size,
            padding=self.padding,
            dilation=dilation
        )
        
        if use_weight_norm:
            conv = nn.utils.weight_norm(conv)
            
        self.conv = conv
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, channels, seq_len)
        out = self.conv(x)
        # Remove future padding
        if self.padding > 0:
            out = out[:, :, :-self.padding]
        return out


class TemporalBlock(nn.Module):
    """
    Residual block with dilated causal convolutions.
    
    Structure:
    input -> Conv1d -> ReLU -> Dropout -> Conv1d -> ReLU -> Dropout -> + -> output
                                                                       ^
                                                                       |
    input --------------------------------------------------------> 1x1 Conv (if needed)
    """
    
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int,
        dropout: float = 0.2,
        use_weight_norm: bool = True
    ):
        super().__init__()
        
        self.conv1 = CausalConv1d(
            in_channels, out_channels, kernel_size, 
            dilation=dilation, use_weight_norm=use_weight_norm
        )
        self.conv2 = CausalConv1d(
            out_channels, out_channels, kernel_size,
            dilation=dilation, use_weight_norm=use_weight_norm
        )
        
        self.dropout = nn.Dropout(dropout)
        self.relu = nn.ReLU()
        
        # Downsample for residual if channel mismatch
        self.downsample = None
        if in_channels != out_channels:
            ds = nn.Conv1d(in_channels, out_channels, 1)
            if use_weight_norm:
                ds = nn.utils.weight_norm(ds)
            self.downsample = ds
            
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x if self.downsample is None else self.downsample(x)
        
        out = self.relu(self.conv1(x))
        out = self.dropout(out)
        out = self.relu(self.conv2(out))
        out = self.dropout(out)
        
        return self.relu(out + residual)


class TCN(BaseForecaster):
    """
    Temporal Convolutional Network
    
    Optimal for: Daily crude oil forecasting (WTI, Brent)
    
    Architecture:
    - Stack of residual blocks with exponentially increasing dilation
    - Receptive field grows exponentially: 2^L * (K-1) + 1
    - Causal convolutions prevent future data leakage
    
    Usage:
        config = TCNConfig.for_crude_oil_daily()
        model = TCN(config, input_size=10)
        history = model.fit(train_df, val_df)
        forecast = model.predict(recent_data)
    """
    
    def __init__(
        self,
        config: TCNConfig,
        input_size: int,  # Number of input features
    ):
        super().__init__(config)
        self.input_size = input_size
        self.config: TCNConfig = config
        
        # Build TCN layers with increasing dilation
        layers = []
        num_levels = len(config.num_channels)
        
        for i in range(num_levels):
            dilation = 2 ** i
            in_ch = input_size if i == 0 else config.num_channels[i-1]
            out_ch = config.num_channels[i]
            
            layers.append(
                TemporalBlock(
                    in_ch, out_ch,
                    kernel_size=config.kernel_size,
                    dilation=dilation,
                    dropout=config.dropout,
                    use_weight_norm=config.use_weight_norm
                )
            )
            
        self.tcn = nn.Sequential(*layers)
        
        # Output projection
        self.output_layer = nn.Linear(
            config.num_channels[-1],
            config.prediction_length
        )
        
        # For uncertainty estimation
        self.uncertainty_layer = nn.Linear(
            config.num_channels[-1],
            config.prediction_length
        )
        
        self.to(self.device)
        
    @property
    def receptive_field(self) -> int:
        """Calculate receptive field size"""
        num_levels = len(self.config.num_channels)
        return 2 ** num_levels * (self.config.kernel_size - 1) + 1
        
    def forward(
        self,
        x: torch.Tensor,
        return_uncertainty: bool = False
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Forward pass.
        
        Args:
            x: Input tensor (batch, seq_len, features)
            return_uncertainty: Return log-variance for confidence intervals
            
        Returns:
            predictions: (batch, prediction_length)
            log_var: Optional uncertainty (batch, prediction_length)
        """
        # TCN expects (batch, channels, seq_len)
        x = x.transpose(1, 2)
        
        # Apply TCN
        out = self.tcn(x)
        
        # Use last timestep's representation
        out = out[:, :, -1]  # (batch, channels)
        
        # Predict
        predictions = self.output_layer(out)
        
        if return_uncertainty:
            log_var = self.uncertainty_layer(out)
            return predictions, log_var
            
        return predictions, None
    
    def _prepare_data(
        self,
        df: pd.DataFrame,
        target_col: str = "close"
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Prepare sliding window data for training.
        
        Returns:
            X: (num_samples, lookback_window, num_features)
            y: (num_samples, prediction_length)
        """
        # Get feature columns (exclude target from features)
        feature_cols = [c for c in df.columns if c != target_col]
        
        # Include target in features for autoregressive prediction
        data = df[feature_cols + [target_col]].values
        target_idx = len(feature_cols)
        
        lookback = self.config.lookback_window
        pred_len = self.config.prediction_length
        
        X, y = [], []
        for i in range(lookback, len(data) - pred_len + 1):
            X.append(data[i-lookback:i])
            y.append(data[i:i+pred_len, target_idx])
            
        X = torch.FloatTensor(np.array(X))
        y = torch.FloatTensor(np.array(y))
        
        return X, y
    
    def fit(
        self,
        train_data: pd.DataFrame,
        val_data: Optional[pd.DataFrame] = None,
        target_col: str = "close",
        **kwargs
    ) -> Dict[str, List[float]]:
        """
        Train the TCN model.
        
        Args:
            train_data: Training DataFrame with features + target
            val_data: Validation DataFrame
            target_col: Name of target column
            
        Returns:
            Training history with train/val losses
        """
        self.train()
        
        # Prepare data
        X_train, y_train = self._prepare_data(train_data, target_col)
        X_train, y_train = X_train.to(self.device), y_train.to(self.device)
        
        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True
        )
        
        if val_data is not None:
            X_val, y_val = self._prepare_data(val_data, target_col)
            X_val, y_val = X_val.to(self.device), y_val.to(self.device)
            val_dataset = TensorDataset(X_val, y_val)
            val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size)
        
        # Optimizer
        optimizer = torch.optim.Adam(
            self.parameters(),
            lr=self.config.learning_rate
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5
        )
        
        # Training loop
        history = {"train_loss": [], "val_loss": []}
        best_val_loss = float('inf')
        patience_counter = 0
        
        for epoch in range(self.config.max_epochs):
            # Training
            train_loss = 0.0
            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()
                
                pred, log_var = self.forward(X_batch, return_uncertainty=True)
                
                # Gaussian negative log-likelihood for uncertainty
                if log_var is not None:
                    precision = torch.exp(-log_var)
                    loss = torch.mean(
                        precision * (pred - y_batch) ** 2 + log_var
                    )
                else:
                    loss = F.mse_loss(pred, y_batch)
                    
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.parameters(), 1.0)
                optimizer.step()
                
                train_loss += loss.item()
                
            train_loss /= len(train_loader)
            history["train_loss"].append(train_loss)
            
            # Validation
            if val_data is not None:
                val_loss = self._validate(val_loader)
                history["val_loss"].append(val_loss)
                scheduler.step(val_loss)
                
                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    # Save best model state
                    best_state = {k: v.cpu().clone() for k, v in self.state_dict().items()}
                else:
                    patience_counter += 1
                    if patience_counter >= self.config.early_stopping_patience:
                        print(f"Early stopping at epoch {epoch+1}")
                        # Restore best model
                        self.load_state_dict(best_state)
                        break
                        
            if (epoch + 1) % 10 == 0:
                val_str = f", val_loss: {val_loss:.6f}" if val_data is not None else ""
                print(f"Epoch {epoch+1}: train_loss: {train_loss:.6f}{val_str}")
                
        self._is_fitted = True
        return history
    
    def _validate(self, val_loader: DataLoader) -> float:
        """Calculate validation loss"""
        self.eval()
        val_loss = 0.0
        
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                pred, _ = self.forward(X_batch)
                loss = F.mse_loss(pred, y_batch)
                val_loss += loss.item()
                
        self.train()
        return val_loss / len(val_loader)
    
    def predict(
        self,
        data: pd.DataFrame,
        target_col: str = "close",
        return_uncertainty: bool = True
    ) -> ForecastResult:
        """
        Generate forecast.
        
        Args:
            data: DataFrame with at least lookback_window rows
            target_col: Target column name
            return_uncertainty: Compute confidence intervals
            
        Returns:
            ForecastResult with predictions and metadata
        """
        import time
        start_time = time.time()
        
        self.eval()
        
        # Prepare input
        feature_cols = [c for c in data.columns if c != target_col]
        features = data[feature_cols + [target_col]].values[-self.config.lookback_window:]
        X = torch.FloatTensor(features).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            pred, log_var = self.forward(X, return_uncertainty=return_uncertainty)
            
        predictions = pred.cpu().numpy()[0]
        
        # Confidence intervals from learned variance
        lower_bound = None
        upper_bound = None
        confidence_scores = None
        
        if log_var is not None:
            std = np.sqrt(np.exp(log_var.cpu().numpy()[0]))
            lower_bound = predictions - 1.96 * std  # 95% CI
            upper_bound = predictions + 1.96 * std
            confidence_scores = 1.0 / (1.0 + std)  # Higher confidence when lower std
            
        inference_time = (time.time() - start_time) * 1000
        
        return ForecastResult(
            timestamp=datetime.now(),
            symbol=data.get("symbol", ["UNKNOWN"])[0] if "symbol" in data.columns else "UNKNOWN",
            model_name="TCN",
            model_version=self.model_version,
            predictions=predictions,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            confidence_scores=confidence_scores,
            direction_prob=float(np.mean(np.diff(predictions) > 0)) if len(predictions) > 1 else None,
            inference_time_ms=inference_time
        )


# =============================================================================
# Asset-Specific Factory Functions
# =============================================================================

def create_tcn_for_crude_oil(input_features: int = 10) -> TCN:
    """
    Create TCN optimized for daily crude oil forecasting.
    
    Research findings:
    - TCN achieves lowest MAE (1.444 WTI, 1.295 Brent)
    - Optimal lookback: 30 days
    - Outperforms GRU, LSTM, Transformer for daily prediction
    
    Recommended features:
    - OHLCV
    - RSI, MACD, ATR
    - DXY (Dollar Index)
    - VIX
    """
    config = TCNConfig(
        model_name="tcn_crude_oil_daily",
        asset_type="crude_oil",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=5,
        num_channels=[64, 128, 256, 128],
        kernel_size=3,
        dropout=0.2,
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=100,
        early_stopping_patience=15,
    )
    
    return TCN(config, input_size=input_features)


def create_tcn_for_gold(input_features: int = 10) -> TCN:
    """
    Create TCN for daily gold forecasting.
    
    Note: For gold, BiGRU slightly outperforms TCN for daily,
    but TCN remains competitive and faster.
    """
    config = TCNConfig(
        model_name="tcn_gold_daily",
        asset_type="gold",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=5,
        num_channels=[64, 128, 128, 64],
        kernel_size=3,
        dropout=0.25,
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=100,
        early_stopping_patience=15,
    )
    
    return TCN(config, input_size=input_features)
