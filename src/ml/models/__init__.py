"""
RiseTrader ML Models Package

Contains all forecasting models:
- Base classes (BaseForecaster, ModelConfig, ForecastResult)
- Legacy models (LSTM, XGBoost)
- Temporal models (TCN, BiGRU)
- Transformer models (FEDformer, TFT)
- Ensemble models (MoE)
- RL models (PPO)
"""

# Base classes
from .base import (
    BaseForecaster,
    EnsembleForecaster,
    ModelConfig,
    ForecastResult
)

# Legacy models (backward compatibility)
from .base_model import BaseModel
from .lstm_forecaster import LSTMForecaster
from .xgboost_forecaster import XGBoostForecaster

# Temporal models
from .temporal import (
    TCN,
    TCNConfig,
    BiGRUAttention,
    GRUConfig,
    create_tcn_for_crude_oil,
    create_tcn_for_gold,
    create_bigru_for_crude_oil,
    create_bigru_for_gold,
)

# Transformer models
from .transformer import (
    FEDformer,
    FEDformerConfig,
    TemporalFusionTransformer,
    TFTConfig,
    create_fedformer_for_crude_oil,
    create_fedformer_for_gold,
    create_tft_for_crude_oil,
    create_tft_for_gold,
)

# Ensemble models
from .ensemble import (
    MixtureOfExperts,
    MoEConfig,
    create_moe_for_crude_oil,
    create_moe_for_gold,
)

# RL models
from .rl import (
    PPOTrader,
    PPOConfig,
    TradingAction,
    create_ppo_for_crude_oil,
    create_ppo_for_gold,
)

# Config loader
from .configs import load_config, list_configs, get_model_config

__all__ = [
    # Base
    'BaseForecaster',
    'EnsembleForecaster', 
    'ModelConfig',
    'ForecastResult',
    'BaseModel',
    # Legacy
    'LSTMForecaster',
    'XGBoostForecaster',
    # Temporal
    'TCN',
    'TCNConfig',
    'BiGRUAttention',
    'GRUConfig',
    'create_tcn_for_crude_oil',
    'create_tcn_for_gold',
    'create_bigru_for_crude_oil',
    'create_bigru_for_gold',
    # Transformer
    'FEDformer',
    'FEDformerConfig',
    'TemporalFusionTransformer',
    'TFTConfig',
    'create_fedformer_for_crude_oil',
    'create_fedformer_for_gold',
    'create_tft_for_crude_oil',
    'create_tft_for_gold',
    # Ensemble
    'MixtureOfExperts',
    'MoEConfig',
    'create_moe_for_crude_oil',
    'create_moe_for_gold',
    # RL
    'PPOTrader',
    'PPOConfig',
    'TradingAction',
    'create_ppo_for_crude_oil',
    'create_ppo_for_gold',
    # Config
    'load_config',
    'list_configs',
    'get_model_config',
]
