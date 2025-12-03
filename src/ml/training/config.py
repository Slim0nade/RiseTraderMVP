"""
ML Configuration Loader with Pydantic Validation
Loads and validates LSTM and XGBoost configuration from YAML files
Based on spec: 003-ml-forecasting-pipeline/research.md TD-008
"""

from pathlib import Path
from typing import List, Union, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# LSTM Configuration Models
# ============================================================================

class LSTMModelConfig(BaseModel):
    """LSTM model architecture configuration"""
    type: str = "lstm"
    num_layers: int = Field(ge=1, le=5)
    hidden_size: int = Field(ge=32, le=512)
    dropout: float = Field(ge=0.0, le=0.5)
    bidirectional: bool
    attention: bool
    output_size: int = 1


class TrainingConfig(BaseModel):
    """Training hyperparameters configuration"""
    learning_rate: float = Field(gt=0.0, le=0.1)
    batch_size: int = Field(ge=8, le=256)
    max_epochs: int = Field(ge=1, le=500)
    early_stopping_patience: int = Field(ge=1, le=50)
    optimizer: str
    loss_function: str
    gradient_clip: float = Field(gt=0.0)

    @field_validator("optimizer")
    @classmethod
    def validate_optimizer(cls, v):
        """Validate optimizer is one of allowed values"""
        allowed = ["adam", "sgd", "rmsprop"]
        if v not in allowed:
            raise ValueError(f"optimizer must be one of {allowed}")
        return v

    @field_validator("loss_function")
    @classmethod
    def validate_loss_function(cls, v):
        """Validate loss function is one of allowed values"""
        allowed = ["mse", "mae", "huber"]
        if v not in allowed:
            raise ValueError(f"loss_function must be one of {allowed}")
        return v


class FeaturesConfig(BaseModel):
    """Feature engineering configuration"""
    lookback_window: int = Field(ge=10, le=200)
    forecast_horizons: List[str]
    include_exogenous: bool
    exogenous_variables: List[str]
    use_technical_indicators: bool
    indicators: List[str]


class DataConfig(BaseModel):
    """Data preparation configuration"""
    train_window_days: int = Field(ge=7, le=180)
    val_window_days: int = Field(ge=1, le=30)
    test_window_days: int = Field(ge=1, le=30)
    slide_days: int = Field(ge=1, le=30)
    min_data_points: int = Field(ge=100)


class LSTMFullConfig(BaseModel):
    """Complete LSTM configuration"""
    model: LSTMModelConfig
    training: TrainingConfig
    features: FeaturesConfig
    data: DataConfig


# ============================================================================
# XGBoost Configuration Models
# ============================================================================

class XGBoostModelConfig(BaseModel):
    """XGBoost model configuration"""
    type: str = "xgboost"
    max_depth: int = Field(ge=1, le=15)
    learning_rate: float = Field(gt=0.0, le=1.0)
    n_estimators: int = Field(ge=10, le=1000)
    objective: str
    booster: str = "gbtree"
    gamma: float = Field(ge=0.0)
    min_child_weight: int = Field(ge=1)
    subsample: float = Field(gt=0.0, le=1.0)
    colsample_bytree: float = Field(gt=0.0, le=1.0)
    reg_alpha: float = Field(ge=0.0)
    reg_lambda: float = Field(ge=0.0)

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, v):
        """Validate objective function"""
        allowed = ["reg:squarederror", "reg:squaredlogerror", "reg:logistic"]
        if v not in allowed:
            raise ValueError(f"objective must be one of {allowed}")
        return v


class XGBoostTrainingConfig(BaseModel):
    """XGBoost training configuration"""
    early_stopping_rounds: int = Field(ge=1, le=50)
    eval_metric: str
    verbose: bool

    @field_validator("eval_metric")
    @classmethod
    def validate_eval_metric(cls, v):
        """Validate evaluation metric"""
        allowed = ["rmse", "mae", "mape"]
        if v not in allowed:
            raise ValueError(f"eval_metric must be one of {allowed}")
        return v


class XGBoostFeaturesConfig(BaseModel):
    """XGBoost feature engineering configuration"""
    lookback_window: int = Field(ge=10, le=200)
    forecast_horizons: List[str]
    include_exogenous: bool
    exogenous_variables: List[str]
    lag_periods: List[int]
    rolling_windows: List[int]
    use_technical_indicators: bool
    indicators: List[str]


class XGBoostFullConfig(BaseModel):
    """Complete XGBoost configuration"""
    model: XGBoostModelConfig
    training: XGBoostTrainingConfig
    features: XGBoostFeaturesConfig
    data: DataConfig


# ============================================================================
# Configuration Loaders
# ============================================================================

def load_lstm_config(config_path: str) -> LSTMFullConfig:
    """
    Load and validate LSTM configuration from YAML file

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Validated LSTMFullConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML syntax is invalid
        ValueError: If validation fails
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)

    # Validate and parse with Pydantic
    return LSTMFullConfig(**config_data)


def load_xgboost_config(config_path: str) -> XGBoostFullConfig:
    """
    Load and validate XGBoost configuration from YAML file

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Validated XGBoostFullConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML syntax is invalid
        ValueError: If validation fails
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)

    # Validate and parse with Pydantic
    return XGBoostFullConfig(**config_data)


def get_default_lstm_config_path() -> str:
    """Get default path to LSTM config file"""
    return "config/ml/lstm_config.yaml"


def get_default_xgboost_config_path() -> str:
    """Get default path to XGBoost config file"""
    return "config/ml/xgboost_config.yaml"


def load_config(config_path: str, model_type: Optional[str] = None) -> Union[LSTMFullConfig, XGBoostFullConfig]:
    """
    Generic config loader that determines model type from path or parameter

    Args:
        config_path: Path to YAML configuration file
        model_type: Optional model type ('lstm' or 'xgboost')

    Returns:
        Validated config object (LSTMFullConfig or XGBoostFullConfig)
    """
    if model_type is None:
        # Infer from filename
        if 'lstm' in config_path.lower():
            model_type = 'lstm'
        elif 'xgboost' in config_path.lower() or 'xgb' in config_path.lower():
            model_type = 'xgboost'
        else:
            raise ValueError(f"Cannot infer model type from path: {config_path}")

    if model_type == 'lstm':
        return load_lstm_config(config_path)
    elif model_type == 'xgboost':
        return load_xgboost_config(config_path)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
