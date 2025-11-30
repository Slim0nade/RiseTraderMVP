"""
Unified Model Registry for RiseTrader ML Models

Supports both MVP models (LSTM, XGBoost) and SOTA models (TCN, BiGRU, FEDformer, TFT, MoE, PPO).
"""

from enum import Enum
from typing import Union, Dict, Any

from .base_model import BaseModel  # MVP base class
from .base import BaseForecaster, ModelConfig, ForecastHorizon, AssetType  # SOTA base class
from .adapters import SOTAtoMVPAdapter, MVPtoSOTAAdapter


class ModelType(str, Enum):
    """Enumeration of all available model types"""

    # MVP Models (Phase 003 - Original Implementation)
    LSTM = "lstm"
    XGBOOST = "xgboost"

    # SOTA Models (Parallel Implementation)
    TCN = "tcn"
    BIGRU = "bigru"
    FEDFORMER = "fedformer"
    TFT = "tft"
    MOE = "moe"
    PPO = "ppo"


def create_model(
    model_type: ModelType,
    config: Dict[str, Any] = None,
    **kwargs
) -> Union[BaseModel, BaseForecaster]:
    """
    Factory function to create any model type.

    Supports both MVP and SOTA models with automatic adapter wrapping if needed.

    Args:
        model_type: Type of model to create (from ModelType enum)
        config: Model configuration dictionary (optional)
        **kwargs: Additional model-specific parameters

    Returns:
        Model instance (either BaseModel or BaseForecaster)

    Raises:
        ValueError: If model_type is unknown
        ImportError: If required model module is not available

    Example:
        >>> # Create MVP LSTM model
        >>> lstm = create_model(ModelType.LSTM, input_size=10, hidden_size=128)
        >>>
        >>> # Create SOTA TCN model
        >>> tcn = create_model(ModelType.TCN, config={'asset_type': 'crude_oil'})
    """
    if config is None:
        config = {}

    # MVP Models
    if model_type == ModelType.LSTM:
        from .lstm_forecaster import LSTMForecaster
        return LSTMForecaster(**kwargs)

    elif model_type == ModelType.XGBOOST:
        from .xgboost_forecaster import XGBoostForecaster
        return XGBoostForecaster(**kwargs)

    # SOTA Models (check if they exist before importing)
    elif model_type == ModelType.TCN:
        try:
            from .temporal.tcn import create_tcn_for_crude_oil
            return create_tcn_for_crude_oil(**kwargs)
        except ImportError:
            raise ImportError(
                "TCN model not found. Ensure SOTA models are properly installed. "
                "See IMPLEMENTATION_GUIDE.md for setup instructions."
            )

    elif model_type == ModelType.BIGRU:
        try:
            from .temporal.gru import create_bigru_for_gold
            return create_bigru_for_gold(**kwargs)
        except ImportError:
            raise ImportError(
                "BiGRU model not found. Ensure SOTA models are properly installed."
            )

    elif model_type == ModelType.FEDFORMER:
        try:
            from .transformers.fedformer import create_fedformer_for_crude_oil
            return create_fedformer_for_crude_oil(**kwargs)
        except ImportError:
            raise ImportError(
                "FEDformer model not found. Ensure SOTA models are properly installed."
            )

    elif model_type == ModelType.TFT:
        try:
            from .transformers.tft import create_tft_for_gold
            return create_tft_for_gold(**kwargs)
        except ImportError:
            raise ImportError(
                "TFT model not found. Ensure SOTA models are properly installed."
            )

    elif model_type == ModelType.MOE:
        try:
            from .ensemble.moe import create_moe_for_crude_oil
            return create_moe_for_crude_oil(**kwargs)
        except ImportError:
            raise ImportError(
                "MoE model not found. Ensure SOTA models are properly installed."
            )

    elif model_type == ModelType.PPO:
        try:
            from .rl.ppo import create_ppo_for_crude_oil
            return create_ppo_for_crude_oil(**kwargs)
        except ImportError:
            raise ImportError(
                "PPO model not found. Ensure SOTA models are properly installed."
            )

    else:
        raise ValueError(f"Unknown model type: {model_type}")


def create_mvp_model_with_adapter(
    model_type: ModelType,
    config: Dict[str, Any] = None,
    **kwargs
) -> BaseModel:
    """
    Create any model and wrap SOTA models with adapter for MVP compatibility.

    This is useful when you need to use SOTA models with existing MVP infrastructure
    (API endpoints, services, repositories) that expect BaseModel interface.

    Args:
        model_type: Type of model to create
        config: Model configuration
        **kwargs: Additional parameters

    Returns:
        BaseModel instance (MVP models as-is, SOTA models wrapped in adapter)

    Example:
        >>> # SOTA model wrapped for MVP compatibility
        >>> tcn = create_mvp_model_with_adapter(ModelType.TCN)
        >>> # Can now use with existing MVP services
        >>> service.train_model(tcn, X_train, y_train)
    """
    model = create_model(model_type, config, **kwargs)

    # If SOTA model, wrap with adapter
    if isinstance(model, BaseForecaster):
        return SOTAtoMVPAdapter(model)

    # MVP model, return as-is
    return model


def create_sota_model_with_adapter(
    model_type: ModelType,
    model_config: ModelConfig,
    **kwargs
) -> BaseForecaster:
    """
    Create any model and wrap MVP models with adapter for SOTA compatibility.

    This is useful when you need to use MVP models in SOTA workflows that expect
    BaseForecaster interface.

    Args:
        model_type: Type of model to create
        model_config: SOTA ModelConfig instance
        **kwargs: Additional parameters

    Returns:
        BaseForecaster instance (SOTA models as-is, MVP models wrapped in adapter)

    Example:
        >>> # MVP model wrapped for SOTA compatibility
        >>> config = ModelConfig.for_crude_oil_daily()
        >>> lstm = create_sota_model_with_adapter(ModelType.LSTM, config)
        >>> # Can now use with SOTA workflows
        >>> result = lstm.predict(df, return_uncertainty=True)
    """
    # Convert ModelConfig to dict for MVP models
    config_dict = {
        'model_name': model_config.model_name,
        'asset_type': model_config.asset_type.value,
        'forecast_horizon': model_config.forecast_horizon.value,
    }

    model = create_model(model_type, config_dict, **kwargs)

    # If MVP model, wrap with adapter
    if isinstance(model, BaseModel):
        return MVPtoSOTAAdapter(model, model_config)

    # SOTA model, return as-is
    return model


# Export key classes and functions
__all__ = [
    # Base classes
    'BaseModel',
    'BaseForecaster',
    'ModelConfig',
    'ForecastHorizon',
    'AssetType',
    # Adapters
    'SOTAtoMVPAdapter',
    'MVPtoSOTAAdapter',
    # Registry
    'ModelType',
    'create_model',
    'create_mvp_model_with_adapter',
    'create_sota_model_with_adapter',
]
