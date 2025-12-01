"""
Mixture of Experts (MoE) Ensemble for RiseTrader
Sparse MoE achieves 17-33% error reduction over dense models.
Based on Time-MoE and Moirai-MoE architectures.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Type

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from ..base import BaseForecaster, ForecastResult, ModelConfig


@dataclass
class MoEConfig(ModelConfig):
    """MoE-specific configuration"""
    num_experts: int = 8
    top_k: int = 2  # Number of experts to activate per token
    expert_hidden_size: int = 256
    expert_type: str = "gru"  # "gru", "tcn", "transformer"
    use_shared_expert: bool = True
    load_balancing_weight: float = 0.01
    router_type: str = "learned"  # "learned", "volatility", "regime"


class Expert(nn.Module):
    """Single expert network - can be GRU, TCN, or Transformer-based."""
    
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: int,
        expert_type: str = "gru",
        dropout: float = 0.2
    ):
        super().__init__()
        self.expert_type = expert_type
        
        if expert_type == "gru":
            self.encoder = nn.GRU(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=2,
                batch_first=True,
                bidirectional=True,
                dropout=dropout
            )
            self.output = nn.Linear(hidden_size * 2, output_size)
            
        elif expert_type == "tcn":
            # Simplified TCN expert
            self.encoder = nn.Sequential(
                nn.Conv1d(input_size, hidden_size, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Conv1d(hidden_size, hidden_size, kernel_size=3, padding=2, dilation=2),
                nn.ReLU(),
                nn.Dropout(dropout),
            )
            self.output = nn.Linear(hidden_size, output_size)
            
        elif expert_type == "transformer":
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_size,
                nhead=4,
                dim_feedforward=hidden_size * 2,
                dropout=dropout,
                batch_first=True
            )
            self.input_proj = nn.Linear(input_size, hidden_size)
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.output = nn.Linear(hidden_size, output_size)
            
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_size)
        Returns:
            output: (batch, output_size)
        """
        if self.expert_type == "gru":
            out, _ = self.encoder(x)
            out = out[:, -1, :]  # Last timestep
            
        elif self.expert_type == "tcn":
            out = self.encoder(x.transpose(1, 2))
            out = out[:, :, -1]  # Last timestep
            
        elif self.expert_type == "transformer":
            out = self.input_proj(x)
            out = self.encoder(out)
            out = out[:, -1, :]
            
        return self.output(out)


class Router(nn.Module):
    """
    Router network that assigns inputs to experts.
    Supports learned routing, volatility-based, and regime-based routing.
    """
    
    def __init__(
        self,
        input_size: int,
        num_experts: int,
        top_k: int = 2,
        router_type: str = "learned"
    ):
        super().__init__()
        self.num_experts = num_experts
        self.top_k = top_k
        self.router_type = router_type
        
        if router_type == "learned":
            # Learned gating network
            self.gate = nn.Sequential(
                nn.Linear(input_size, input_size),
                nn.ReLU(),
                nn.Linear(input_size, num_experts)
            )
        elif router_type == "volatility":
            # Volatility-based routing (2 experts: high/low vol)
            self.vol_threshold = nn.Parameter(torch.tensor(0.5))
        elif router_type == "regime":
            # Regime-based routing using clustering
            self.regime_proj = nn.Linear(input_size, 16)
            self.gate = nn.Linear(16, num_experts)
            
    def forward(
        self,
        x: torch.Tensor,
        volatility: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Compute routing weights.
        
        Args:
            x: (batch, seq_len, input_size)
            volatility: Optional volatility features
            
        Returns:
            weights: (batch, top_k) - weights for selected experts
            indices: (batch, top_k) - indices of selected experts
            load_balancing_loss: Auxiliary loss for balanced expert usage
        """
        batch_size = x.size(0)
        
        # Use last timestep representation
        x_last = x[:, -1, :]
        
        if self.router_type == "learned":
            logits = self.gate(x_last)  # (batch, num_experts)
            
        elif self.router_type == "volatility":
            if volatility is None:
                # Compute volatility from returns
                returns = torch.diff(x[:, :, 0], dim=1)
                volatility = returns.std(dim=1, keepdim=True)
                
            # Binary routing based on volatility
            high_vol = (volatility > self.vol_threshold).float()
            logits = torch.zeros(batch_size, self.num_experts, device=x.device)
            logits[:, :self.num_experts//2] = 1 - high_vol
            logits[:, self.num_experts//2:] = high_vol
            
        elif self.router_type == "regime":
            regime_repr = F.relu(self.regime_proj(x_last))
            logits = self.gate(regime_repr)
            
        # Top-k selection
        weights, indices = torch.topk(F.softmax(logits, dim=-1), self.top_k, dim=-1)
        
        # Normalize weights
        weights = weights / weights.sum(dim=-1, keepdim=True)
        
        # Load balancing loss (encourage uniform expert usage)
        prob = F.softmax(logits, dim=-1)
        load = prob.mean(dim=0)  # Average probability per expert
        target_load = 1.0 / self.num_experts
        load_balancing_loss = ((load - target_load) ** 2).sum()
        
        return weights, indices, load_balancing_loss


class MixtureOfExperts(BaseForecaster):
    """
    Sparse Mixture of Experts for time series forecasting.
    
    Architecture:
    - Multiple specialized expert networks (GRU/TCN/Transformer)
    - Learned router that activates top-K experts per sample
    - Optional shared expert for common patterns
    
    Research performance:
    - Time-MoE: 20% zero-shot error reduction
    - Moirai-MoE: 17% improvement over dense baseline
    - Up to 33% MSE improvement for volatile assets
    
    Key benefits:
    - Capacity scaling without proportional compute increase
    - Specialization for different market regimes
    - Efficient inference (only top-K experts active)
    
    Usage:
        config = MoEConfig.for_crude_oil_daily()
        model = MixtureOfExperts(config, input_size=10)
        history = model.fit(train_df, val_df)
        forecast = model.predict(recent_data)
    """
    
    def __init__(self, config: MoEConfig, input_size: int):
        super().__init__(config)
        self.input_size = input_size
        self.config: MoEConfig = config
        
        # Create experts
        self.experts = nn.ModuleList([
            Expert(
                input_size=input_size,
                hidden_size=config.expert_hidden_size,
                output_size=config.prediction_length,
                expert_type=config.expert_type,
                dropout=0.2
            )
            for _ in range(config.num_experts)
        ])
        
        # Shared expert (always activated)
        self.shared_expert = None
        if config.use_shared_expert:
            self.shared_expert = Expert(
                input_size=input_size,
                hidden_size=config.expert_hidden_size,
                output_size=config.prediction_length,
                expert_type=config.expert_type,
                dropout=0.2
            )
            
        # Router
        self.router = Router(
            input_size=input_size,
            num_experts=config.num_experts,
            top_k=config.top_k,
            router_type=config.router_type
        )
        
        # Output combination
        self.output_proj = nn.Linear(config.prediction_length, config.prediction_length)
        
        # Uncertainty estimation
        self.uncertainty_layer = nn.Linear(config.prediction_length, config.prediction_length)
        
        self.to(self.device)
        
    def forward(
        self,
        x: torch.Tensor,
        return_uncertainty: bool = False,
        return_routing: bool = False
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor], Optional[Dict]]:
        """
        Forward pass with sparse expert routing.
        
        Args:
            x: (batch, seq_len, input_size)
            return_uncertainty: Return variance estimate
            return_routing: Return expert routing info
            
        Returns:
            predictions: (batch, prediction_length)
            log_var: Optional uncertainty
            routing_info: Optional dict with expert weights/indices
        """
        batch_size = x.size(0)
        
        # Get routing weights
        weights, indices, self._load_balance_loss = self.router(x)
        
        # Compute expert outputs (only for selected experts)
        expert_outputs = torch.zeros(
            batch_size, self.config.top_k, self.config.prediction_length,
            device=x.device
        )
        
        for i in range(self.config.top_k):
            expert_idx = indices[:, i]  # (batch,)
            
            # Process each sample with its assigned expert
            for b in range(batch_size):
                expert_outputs[b, i] = self.experts[expert_idx[b]](x[b:b+1])
                
        # Weighted combination
        weights_expanded = weights.unsqueeze(-1)  # (batch, top_k, 1)
        combined = (expert_outputs * weights_expanded).sum(dim=1)  # (batch, pred_len)
        
        # Add shared expert
        if self.shared_expert is not None:
            shared_out = self.shared_expert(x)
            combined = combined + 0.5 * shared_out  # Equal weight to shared
            combined = combined / 1.5  # Normalize
            
        predictions = self.output_proj(combined)
        
        log_var = None
        if return_uncertainty:
            log_var = self.uncertainty_layer(combined)
            
        routing_info = None
        if return_routing:
            routing_info = {
                "expert_weights": weights.detach().cpu().numpy(),
                "expert_indices": indices.detach().cpu().numpy()
            }
            
        return predictions, log_var, routing_info
    
    def _prepare_data(
        self,
        df: pd.DataFrame,
        target_col: str = "close"
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Prepare data."""
        feature_cols = [c for c in df.columns if c not in [target_col, "symbol", "time"]]
        all_cols = feature_cols + [target_col]
        data = df[all_cols].values
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
        """Train with load balancing loss."""
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
        
        history = {"train_loss": [], "val_loss": [], "load_balance_loss": []}
        best_val_loss = float('inf')
        patience_counter = 0
        best_state = None
        
        for epoch in range(self.config.max_epochs):
            train_loss = 0.0
            lb_loss = 0.0
            
            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()
                pred, log_var, _ = self.forward(X_batch, return_uncertainty=True)
                
                # Main prediction loss
                if log_var is not None:
                    precision = torch.exp(-log_var)
                    pred_loss = torch.mean(precision * (pred - y_batch) ** 2 + log_var)
                else:
                    pred_loss = F.mse_loss(pred, y_batch)
                    
                # Total loss with load balancing
                loss = pred_loss + self.config.load_balancing_weight * self._load_balance_loss
                
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.parameters(), 1.0)
                optimizer.step()
                
                train_loss += pred_loss.item()
                lb_loss += self._load_balance_loss.item()
                
            train_loss /= len(train_loader)
            lb_loss /= len(train_loader)
            history["train_loss"].append(train_loss)
            history["load_balance_loss"].append(lb_loss)
            
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
                val_str = f", val: {val_loss:.6f}" if val_loader else ""
                print(f"Epoch {epoch+1}: train: {train_loss:.6f}, lb: {lb_loss:.6f}{val_str}")
                
        self._is_fitted = True
        return history
    
    def _validate(self, val_loader: DataLoader) -> float:
        self.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                pred, _, _ = self.forward(X_batch)
                val_loss += F.mse_loss(pred, y_batch).item()
        self.train()
        return val_loss / len(val_loader)
    
    def predict(
        self,
        data: pd.DataFrame,
        target_col: str = "close",
        return_uncertainty: bool = True
    ) -> ForecastResult:
        """Generate forecast with routing info."""
        import time
        start_time = time.time()
        
        self.eval()
        
        feature_cols = [c for c in data.columns if c not in [target_col, "symbol", "time"]]
        all_cols = feature_cols + [target_col]
        features = data[all_cols].values[-self.config.lookback_window:]
        X = torch.FloatTensor(features).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            pred, log_var, routing_info = self.forward(
                X, return_uncertainty=return_uncertainty, return_routing=True
            )
            
        predictions = pred.cpu().numpy()[0]
        
        lower_bound = upper_bound = confidence_scores = None
        if log_var is not None:
            std = np.sqrt(np.exp(log_var.cpu().numpy()[0]))
            lower_bound = predictions - 1.96 * std
            upper_bound = predictions + 1.96 * std
            confidence_scores = 1.0 / (1.0 + std)
            
        # Include routing info in feature importance
        feature_importance = None
        if routing_info:
            expert_weights = routing_info["expert_weights"][0]
            expert_indices = routing_info["expert_indices"][0]
            feature_importance = {
                f"expert_{idx}": float(w)
                for idx, w in zip(expert_indices, expert_weights)
            }
            
        return ForecastResult(
            timestamp=datetime.now(),
            symbol=data.get("symbol", ["UNKNOWN"])[0] if "symbol" in data.columns else "UNKNOWN",
            model_name="MoE",
            model_version=self.model_version,
            predictions=predictions,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            confidence_scores=confidence_scores,
            direction_prob=float(np.mean(np.diff(predictions) > 0)) if len(predictions) > 1 else None,
            inference_time_ms=(time.time() - start_time) * 1000,
            feature_importance=feature_importance
        )


# =============================================================================
# Factory Functions
# =============================================================================

def create_moe_for_crude_oil(input_features: int = 10) -> MixtureOfExperts:
    """
    Create MoE optimized for crude oil forecasting.
    
    Research: Up to 33% MSE improvement for volatile stocks/commodities.
    Uses regime-based routing for oil's distinct market regimes.
    """
    config = MoEConfig(
        model_name="moe_crude_oil",
        asset_type="crude_oil",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=5,
        num_experts=8,
        top_k=2,
        expert_hidden_size=128,
        expert_type="gru",
        use_shared_expert=True,
        load_balancing_weight=0.01,
        router_type="volatility",  # Oil has distinct high/low vol regimes
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=100,
        early_stopping_patience=15,
    )
    return MixtureOfExperts(config, input_size=input_features)


def create_moe_for_gold(input_features: int = 10) -> MixtureOfExperts:
    """Create MoE for gold forecasting."""
    config = MoEConfig(
        model_name="moe_gold",
        asset_type="gold",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=5,
        num_experts=6,
        top_k=2,
        expert_hidden_size=128,
        expert_type="gru",
        use_shared_expert=True,
        load_balancing_weight=0.01,
        router_type="learned",
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=100,
        early_stopping_patience=15,
    )
    return MixtureOfExperts(config, input_size=input_features)
