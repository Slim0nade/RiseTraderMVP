"""
FEDformer (Frequency Enhanced Decomposed Transformer) for RiseTrader
Best performer for weekly/monthly commodity forecasting per 2025 research:
- 38.5% MAE reduction vs LSTM
- 56.6% MAE reduction vs GRU
- Operates in frequency domain via Fourier attention
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

from .base import BaseForecaster, ForecastResult, ModelConfig


@dataclass
class FEDformerConfig(ModelConfig):
    """FEDformer-specific configuration"""
    d_model: int = 256
    n_heads: int = 8
    e_layers: int = 2  # Encoder layers
    d_layers: int = 1  # Decoder layers
    d_ff: int = 512
    dropout: float = 0.1
    activation: str = "gelu"
    # Frequency components
    modes: int = 32  # Number of Fourier modes to keep
    mode_select: str = "random"  # 'random' or 'low'
    # Decomposition
    moving_avg: int = 25  # Window for moving average decomposition


class SeriesDecomp(nn.Module):
    """Series decomposition: Trend + Seasonal"""
    
    def __init__(self, kernel_size: int):
        super().__init__()
        self.moving_avg = nn.AvgPool1d(
            kernel_size=kernel_size,
            stride=1,
            padding=kernel_size // 2,
            count_include_pad=False
        )
        
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Decompose series into trend and seasonal components.
        
        Args:
            x: (batch, seq_len, features)
            
        Returns:
            seasonal: (batch, seq_len, features)
            trend: (batch, seq_len, features)
        """
        # Pool along sequence dimension
        x_t = x.transpose(1, 2)  # (batch, features, seq)
        trend = self.moving_avg(x_t)
        trend = trend.transpose(1, 2)  # (batch, seq, features)
        
        # Handle edge cases from padding
        if trend.size(1) != x.size(1):
            trend = F.interpolate(
                trend.transpose(1, 2),
                size=x.size(1),
                mode='linear',
                align_corners=False
            ).transpose(1, 2)
            
        seasonal = x - trend
        return seasonal, trend


class FourierBlock(nn.Module):
    """
    Fourier Block for frequency-domain attention.
    Operates on Fourier coefficients instead of time-domain values.
    """
    
    def __init__(
        self,
        d_model: int,
        n_heads: int,
        modes: int = 32,
        mode_select: str = "random"
    ):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.modes = modes
        self.mode_select = mode_select
        
        # Learnable frequency filters
        self.scale = 1 / (d_model * d_model)
        self.weights = nn.Parameter(
            self.scale * torch.rand(n_heads, modes, d_model // n_heads, d_model // n_heads, dtype=torch.cfloat)
        )
        
    def forward(self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
        """
        Frequency-domain attention.
        
        Args:
            q, k, v: (batch, heads, seq_len, d_head)
            
        Returns:
            output: (batch, heads, seq_len, d_head)
        """
        batch, heads, seq_len, d_head = q.shape
        
        # FFT on sequence dimension
        q_fft = torch.fft.rfft(q, dim=2)
        k_fft = torch.fft.rfft(k, dim=2)
        v_fft = torch.fft.rfft(v, dim=2)
        
        # Keep only selected modes
        modes = min(self.modes, seq_len // 2 + 1)
        
        if self.mode_select == "random":
            # Random mode selection (paper default)
            idx = torch.randperm(seq_len // 2 + 1)[:modes]
        else:
            # Low frequency modes
            idx = torch.arange(modes)
            
        q_fft = q_fft[:, :, idx, :]
        k_fft = k_fft[:, :, idx, :]
        v_fft = v_fft[:, :, idx, :]
        
        # Frequency domain attention
        # Multiply by learnable weights
        weights = self.weights[:, :modes, :, :]
        
        # Element-wise complex multiplication
        out_fft = torch.einsum("bhmd,hmde->bhme", v_fft, weights)
        
        # Pad back to full spectrum
        out_full = torch.zeros(batch, heads, seq_len // 2 + 1, d_head, dtype=torch.cfloat, device=q.device)
        out_full[:, :, idx, :] = out_fft
        
        # Inverse FFT
        output = torch.fft.irfft(out_full, n=seq_len, dim=2)
        
        return output.real


class FEDformerEncoderLayer(nn.Module):
    """FEDformer encoder layer with frequency attention"""
    
    def __init__(
        self,
        d_model: int,
        n_heads: int,
        d_ff: int,
        modes: int,
        dropout: float = 0.1,
        activation: str = "gelu"
    ):
        super().__init__()
        
        # Frequency attention
        self.fourier_attn = FourierBlock(d_model, n_heads, modes)
        
        # Layer norms
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        
        # Feed-forward
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU() if activation == "gelu" else nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_ff, d_model),
            nn.Dropout(dropout)
        )
        
        self.dropout = nn.Dropout(dropout)
        
        # Projections for Q, K, V
        self.n_heads = n_heads
        self.d_head = d_model // n_heads
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, seq_len, d_model = x.shape
        
        # Project Q, K, V
        q = self.q_proj(x).view(batch, seq_len, self.n_heads, self.d_head).transpose(1, 2)
        k = self.k_proj(x).view(batch, seq_len, self.n_heads, self.d_head).transpose(1, 2)
        v = self.v_proj(x).view(batch, seq_len, self.n_heads, self.d_head).transpose(1, 2)
        
        # Frequency attention
        attn_out = self.fourier_attn(q, k, v)
        attn_out = attn_out.transpose(1, 2).contiguous().view(batch, seq_len, d_model)
        attn_out = self.out_proj(attn_out)
        
        # Residual + norm
        x = self.norm1(x + self.dropout(attn_out))
        
        # Feed-forward + residual
        x = self.norm2(x + self.ff(x))
        
        return x


class FEDformer(BaseForecaster):
    """
    Frequency Enhanced Decomposed Transformer
    
    Optimal for: Weekly/monthly crude oil and commodity forecasting
    
    Key innovations:
    1. Series decomposition into trend + seasonal
    2. Fourier attention - O(L log L) complexity
    3. Frequency-domain learnable filters
    
    Research performance:
    - 38.5% MAE reduction vs LSTM on Bloomberg Commodity Index
    - 56.6% MAE reduction vs GRU
    - Best for horizons > 7 days
    
    Usage:
        config = FEDformerConfig.for_crude_oil_weekly()
        model = FEDformer(config, input_size=10)
        history = model.fit(train_df, val_df)
        forecast = model.predict(recent_data)
    """
    
    def __init__(self, config: FEDformerConfig, input_size: int):
        super().__init__(config)
        self.input_size = input_size
        self.config: FEDformerConfig = config
        
        # Series decomposition
        self.decomp = SeriesDecomp(config.moving_avg)
        
        # Input embedding
        self.enc_embedding = nn.Linear(input_size, config.d_model)
        self.dec_embedding = nn.Linear(input_size, config.d_model)
        
        # Positional encoding
        self.pos_encoding = self._get_positional_encoding(
            config.lookback_window + config.prediction_length,
            config.d_model
        )
        
        # Encoder layers
        self.encoder_layers = nn.ModuleList([
            FEDformerEncoderLayer(
                config.d_model,
                config.n_heads,
                config.d_ff,
                config.modes,
                config.dropout,
                config.activation
            )
            for _ in range(config.e_layers)
        ])
        
        # Decoder (simplified - uses trend for autoregressive prediction)
        self.decoder_proj = nn.Linear(config.d_model, config.d_model)
        
        # Output projection
        self.output_layer = nn.Linear(config.d_model, 1)
        
        # For multi-step: project to all horizons at once
        self.horizon_proj = nn.Linear(config.lookback_window, config.prediction_length)
        
        # Uncertainty estimation
        self.uncertainty_layer = nn.Linear(config.d_model, 1)
        
        self.to(self.device)
        
    def _get_positional_encoding(self, max_len: int, d_model: int) -> torch.Tensor:
        """Sinusoidal positional encoding"""
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        return pe.unsqueeze(0)  # (1, max_len, d_model)
        
    def forward(
        self,
        x: torch.Tensor,
        return_uncertainty: bool = False
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Forward pass.
        
        Args:
            x: (batch, seq_len, features)
            return_uncertainty: Return variance estimate
            
        Returns:
            predictions: (batch, prediction_length)
            log_var: Optional (batch, prediction_length)
        """
        batch_size, seq_len, _ = x.shape
        
        # Decompose input
        seasonal, trend = self.decomp(x)
        
        # Embed
        enc_out = self.enc_embedding(seasonal)  # (batch, seq, d_model)
        
        # Add positional encoding
        enc_out = enc_out + self.pos_encoding[:, :seq_len, :].to(x.device)
        
        # Encoder
        for layer in self.encoder_layers:
            enc_out = layer(enc_out)
            
        # Project to predictions
        # Use last encoder output
        enc_last = enc_out  # (batch, seq, d_model)
        
        # Predict at each position
        pred_per_step = self.output_layer(enc_last).squeeze(-1)  # (batch, seq)
        
        # Project to prediction horizon
        predictions = self.horizon_proj(pred_per_step)  # (batch, pred_len)
        
        # Add trend extrapolation
        trend_last = trend[:, -1, 0]  # Last trend value
        predictions = predictions + trend_last.unsqueeze(-1)
        
        if return_uncertainty:
            # Estimate uncertainty from encoder representation
            enc_mean = enc_out.mean(dim=1)  # (batch, d_model)
            log_var = self.uncertainty_layer(enc_mean).squeeze(-1)  # (batch, 1)
            log_var = log_var.expand(-1, self.config.prediction_length)
            return predictions, log_var
            
        return predictions, None
    
    def _prepare_data(
        self,
        df: pd.DataFrame,
        target_col: str = "close"
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Prepare data for training."""
        feature_cols = [c for c in df.columns if c != target_col]
        data = df[feature_cols + [target_col]].values
        target_idx = len(feature_cols)
        
        lookback = self.config.lookback_window
        pred_len = self.config.prediction_length
        
        X, y = [], []
        for i in range(lookback, len(data) - pred_len + 1):
            X.append(data[i-lookback:i])
            y.append(data[i:i+pred_len, target_idx])
            
        return torch.FloatTensor(np.array(X)), torch.FloatTensor(np.array(y))
    
    def fit(
        self,
        train_data: pd.DataFrame,
        val_data: Optional[pd.DataFrame] = None,
        target_col: str = "close",
        **kwargs
    ) -> Dict[str, List[float]]:
        """Train the model."""
        self.train()
        
        X_train, y_train = self._prepare_data(train_data, target_col)
        X_train, y_train = X_train.to(self.device), y_train.to(self.device)
        
        train_loader = DataLoader(
            TensorDataset(X_train, y_train),
            batch_size=self.config.batch_size,
            shuffle=True
        )
        
        val_loader = None
        if val_data is not None:
            X_val, y_val = self._prepare_data(val_data, target_col)
            X_val, y_val = X_val.to(self.device), y_val.to(self.device)
            val_loader = DataLoader(
                TensorDataset(X_val, y_val),
                batch_size=self.config.batch_size
            )
            
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.config.learning_rate,
            weight_decay=0.01
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=self.config.max_epochs
        )
        
        history = {"train_loss": [], "val_loss": []}
        best_val_loss = float('inf')
        patience_counter = 0
        best_state = None
        
        for epoch in range(self.config.max_epochs):
            train_loss = 0.0
            
            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()
                pred, log_var = self.forward(X_batch, return_uncertainty=True)
                
                if log_var is not None:
                    precision = torch.exp(-log_var)
                    loss = torch.mean(precision * (pred - y_batch) ** 2 + log_var)
                else:
                    loss = F.mse_loss(pred, y_batch)
                    
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()
                
            scheduler.step()
            train_loss /= len(train_loader)
            history["train_loss"].append(train_loss)
            
            if val_loader is not None:
                val_loss = self._validate(val_loader)
                history["val_loss"].append(val_loss)
                
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    best_state = {k: v.cpu().clone() for k, v in self.state_dict().items()}
                else:
                    patience_counter += 1
                    if patience_counter >= self.config.early_stopping_patience:
                        print(f"Early stopping at epoch {epoch+1}")
                        if best_state:
                            self.load_state_dict(best_state)
                        break
                        
            if (epoch + 1) % 10 == 0:
                val_str = f", val_loss: {val_loss:.6f}" if val_loader else ""
                print(f"Epoch {epoch+1}: train_loss: {train_loss:.6f}{val_str}")
                
        self._is_fitted = True
        return history
    
    def _validate(self, val_loader: DataLoader) -> float:
        self.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                pred, _ = self.forward(X_batch)
                val_loss += F.mse_loss(pred, y_batch).item()
        self.train()
        return val_loss / len(val_loader)
    
    def predict(
        self,
        data: pd.DataFrame,
        target_col: str = "close",
        return_uncertainty: bool = True
    ) -> ForecastResult:
        """Generate forecast."""
        import time
        start_time = time.time()
        
        self.eval()
        
        feature_cols = [c for c in data.columns if c != target_col]
        features = data[feature_cols + [target_col]].values[-self.config.lookback_window:]
        X = torch.FloatTensor(features).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            pred, log_var = self.forward(X, return_uncertainty=return_uncertainty)
            
        predictions = pred.cpu().numpy()[0]
        
        lower_bound = upper_bound = confidence_scores = None
        if log_var is not None:
            std = np.sqrt(np.exp(log_var.cpu().numpy()[0]))
            lower_bound = predictions - 1.96 * std
            upper_bound = predictions + 1.96 * std
            confidence_scores = 1.0 / (1.0 + std)
            
        return ForecastResult(
            timestamp=datetime.now(),
            symbol=data.get("symbol", ["UNKNOWN"])[0] if "symbol" in data.columns else "UNKNOWN",
            model_name="FEDformer",
            model_version=self.model_version,
            predictions=predictions,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            confidence_scores=confidence_scores,
            direction_prob=float(np.mean(np.diff(predictions) > 0)) if len(predictions) > 1 else None,
            inference_time_ms=(time.time() - start_time) * 1000
        )


# =============================================================================
# Factory Functions
# =============================================================================

def create_fedformer_for_crude_oil(input_features: int = 10) -> FEDformer:
    """
    Create FEDformer optimized for weekly/monthly crude oil forecasting.
    
    Research: 38.5% MAE reduction vs LSTM, 56.6% vs GRU
    Best for horizons > 7 days
    """
    config = FEDformerConfig(
        model_name="fedformer_crude_oil_weekly",
        asset_type="crude_oil",
        forecast_horizon="weekly",
        lookback_window=60,
        prediction_length=14,
        d_model=256,
        n_heads=8,
        e_layers=2,
        d_layers=1,
        d_ff=512,
        dropout=0.1,
        modes=32,
        moving_avg=25,
        learning_rate=1e-4,
        batch_size=32,
        max_epochs=100,
        early_stopping_patience=15,
    )
    return FEDformer(config, input_size=input_features)


def create_fedformer_for_gold(input_features: int = 10) -> FEDformer:
    """Create FEDformer for weekly/monthly gold forecasting."""
    config = FEDformerConfig(
        model_name="fedformer_gold_weekly",
        asset_type="gold",
        forecast_horizon="weekly",
        lookback_window=60,
        prediction_length=14,
        d_model=256,
        n_heads=8,
        e_layers=2,
        d_layers=1,
        d_ff=512,
        dropout=0.1,
        modes=32,
        moving_avg=25,
        learning_rate=1e-4,
        batch_size=32,
        max_epochs=100,
        early_stopping_patience=15,
    )
    return FEDformer(config, input_size=input_features)
