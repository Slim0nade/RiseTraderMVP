"""
GRU (Gated Recurrent Unit) Models for RiseTrader
Competitive with TCN for daily crude oil/gold forecasting.
BiGRU achieves MAE of 15.188 for gold with 30-day windows.
"""
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
class GRUConfig(ModelConfig):
    """GRU-specific configuration"""
    hidden_size: int = 128
    num_layers: int = 2
    bidirectional: bool = True
    dropout: float = 0.2
    use_attention: bool = True
    attention_heads: int = 4


class AttentionLayer(nn.Module):
    """Multi-head self-attention for sequence modeling"""
    
    def __init__(self, hidden_size: int, num_heads: int = 4, dropout: float = 0.1):
        super().__init__()
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )
        self.norm = nn.LayerNorm(hidden_size)
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        # Self-attention
        attn_out, _ = self.attention(x, x, x, attn_mask=mask)
        # Residual + norm
        return self.norm(x + self.dropout(attn_out))


class BiGRUAttention(BaseForecaster):
    """
    Bidirectional GRU with Attention Mechanism
    
    Optimal for: Daily gold/crude oil forecasting
    
    Architecture:
    - Bidirectional GRU captures both past and "context" patterns
    - Multi-head attention weighs important timesteps
    - Linear projection for multi-step prediction
    
    Research findings:
    - BiGRU achieves MAE of 15.188 for gold
    - Outperforms LSTM for most commodities
    - Optimal lookback: 30 days
    
    Usage:
        config = GRUConfig.for_gold_daily()
        model = BiGRUAttention(config, input_size=10)
        history = model.fit(train_df, val_df)
        forecast = model.predict(recent_data)
    """
    
    def __init__(self, config: GRUConfig, input_size: int):
        super().__init__(config)
        self.input_size = input_size
        self.config: GRUConfig = config
        
        # Input projection
        self.input_proj = nn.Linear(input_size, config.hidden_size)
        
        # Bidirectional GRU
        self.gru = nn.GRU(
            input_size=config.hidden_size,
            hidden_size=config.hidden_size,
            num_layers=config.num_layers,
            batch_first=True,
            bidirectional=config.bidirectional,
            dropout=config.dropout if config.num_layers > 1 else 0
        )
        
        # Calculate output dimension
        gru_output_size = config.hidden_size * (2 if config.bidirectional else 1)
        
        # Projection after GRU
        self.gru_proj = nn.Linear(gru_output_size, config.hidden_size)
        
        # Attention layer
        self.attention = None
        if config.use_attention:
            self.attention = AttentionLayer(
                config.hidden_size,
                num_heads=config.attention_heads,
                dropout=config.dropout
            )
            
        # Output layers
        self.output_layer = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size // 2, config.prediction_length)
        )
        
        # Uncertainty estimation
        self.uncertainty_layer = nn.Linear(config.hidden_size, config.prediction_length)
        
        self.to(self.device)
        
    def forward(
        self,
        x: torch.Tensor,
        return_uncertainty: bool = False
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Forward pass.
        
        Args:
            x: (batch, seq_len, features)
            return_uncertainty: Return log-variance
            
        Returns:
            predictions: (batch, prediction_length)
            log_var: Optional (batch, prediction_length)
        """
        batch_size = x.size(0)
        
        # Project input
        x = self.input_proj(x)  # (batch, seq, hidden)
        
        # GRU
        gru_out, _ = self.gru(x)  # (batch, seq, hidden*2)
        
        # Project back to hidden size
        gru_out = self.gru_proj(gru_out)  # (batch, seq, hidden)
        
        # Apply attention
        if self.attention is not None:
            gru_out = self.attention(gru_out)
            
        # Use last timestep or attention-weighted sum
        if self.attention is not None:
            # Attention-weighted pooling
            weights = F.softmax(gru_out.mean(dim=-1, keepdim=True), dim=1)
            context = (gru_out * weights).sum(dim=1)
        else:
            context = gru_out[:, -1, :]
            
        # Predict
        predictions = self.output_layer(context)
        
        if return_uncertainty:
            log_var = self.uncertainty_layer(context)
            return predictions, log_var
            
        return predictions, None
    
    def _prepare_data(
        self,
        df: pd.DataFrame,
        target_col: str = "close"
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Prepare sliding window data."""
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
            
        optimizer = torch.optim.Adam(self.parameters(), lr=self.config.learning_rate)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5
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
                
            train_loss /= len(train_loader)
            history["train_loss"].append(train_loss)
            
            if val_loader is not None:
                val_loss = self._validate(val_loader)
                history["val_loss"].append(val_loss)
                scheduler.step(val_loss)
                
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
            model_name="BiGRUAttention",
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

def create_bigru_for_crude_oil(input_features: int = 10) -> BiGRUAttention:
    """Create BiGRU optimized for daily crude oil forecasting."""
    config = GRUConfig(
        model_name="bigru_crude_oil_daily",
        asset_type="crude_oil",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=5,
        hidden_size=128,
        num_layers=2,
        bidirectional=True,
        dropout=0.2,
        use_attention=True,
        attention_heads=4,
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=100,
        early_stopping_patience=15,
    )
    return BiGRUAttention(config, input_size=input_features)


def create_bigru_for_gold(input_features: int = 10) -> BiGRUAttention:
    """
    Create BiGRU optimized for daily gold forecasting.
    Research: BiGRU achieves MAE of 15.188 with 30-day windows.
    """
    config = GRUConfig(
        model_name="bigru_gold_daily",
        asset_type="gold",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=5,
        hidden_size=128,
        num_layers=2,
        bidirectional=True,
        dropout=0.25,
        use_attention=True,
        attention_heads=4,
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=100,
        early_stopping_patience=15,
    )
    return BiGRUAttention(config, input_size=input_features)
