"""
Unit tests for ML configuration loader with Pydantic validation
Tests YAML loading, validation, and error handling
"""

import pytest
from pathlib import Path
import yaml
import tempfile

from src.ml.training.config import (
    LSTMModelConfig,
    XGBoostModelConfig,
    TrainingConfig,
    FeaturesConfig,
    DataConfig,
    LSTMFullConfig,
    XGBoostFullConfig,
    load_lstm_config,
    load_xgboost_config,
)


class TestLSTMConfigLoading:
    """Test suite for LSTM configuration loading"""

    def test_load_lstm_config_from_file(self, tmp_path):
        """Test loading LSTM config from YAML file"""
        config_data = {
            "model": {
                "type": "lstm",
                "num_layers": 2,
                "hidden_size": 128,
                "dropout": 0.2,
                "bidirectional": True,
                "attention": True,
                "output_size": 1,
            },
            "training": {
                "learning_rate": 0.001,
                "batch_size": 64,
                "max_epochs": 100,
                "early_stopping_patience": 10,
                "optimizer": "adam",
                "loss_function": "mse",
                "gradient_clip": 1.0,
            },
            "features": {
                "lookback_window": 60,
                "forecast_horizons": ["1h", "4h", "24h"],
                "include_exogenous": True,
                "exogenous_variables": ["DXY", "VIX", "NEWS_EVENT"],
                "use_technical_indicators": True,
                "indicators": ["rsi_14", "macd"],
            },
            "data": {
                "train_window_days": 30,
                "val_window_days": 5,
                "test_window_days": 5,
                "slide_days": 5,
                "min_data_points": 1000,
            },
        }

        # Write temp config file
        config_file = tmp_path / "test_lstm_config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Load config
        config = load_lstm_config(str(config_file))

        assert config.model.type == "lstm"
        assert config.model.num_layers == 2
        assert config.training.learning_rate == 0.001
        assert config.features.lookback_window == 60

    def test_lstm_model_config_validation(self):
        """Test Pydantic validation for LSTM model config"""
        # Valid config
        config = LSTMModelConfig(
            type="lstm",
            num_layers=2,
            hidden_size=128,
            dropout=0.2,
            bidirectional=True,
            attention=True,
            output_size=1,
        )

        assert config.num_layers == 2
        assert config.hidden_size == 128

    def test_lstm_model_config_invalid_layers(self):
        """Test validation error for invalid number of layers"""
        with pytest.raises(ValueError):
            LSTMModelConfig(
                type="lstm",
                num_layers=0,  # Invalid: must be >= 1
                hidden_size=128,
                dropout=0.2,
                bidirectional=True,
                attention=True,
                output_size=1,
            )

    def test_lstm_model_config_invalid_dropout(self):
        """Test validation error for invalid dropout value"""
        with pytest.raises(ValueError):
            LSTMModelConfig(
                type="lstm",
                num_layers=2,
                hidden_size=128,
                dropout=1.5,  # Invalid: must be <= 0.5
                bidirectional=True,
                attention=True,
                output_size=1,
            )


class TestXGBoostConfigLoading:
    """Test suite for XGBoost configuration loading"""

    def test_load_xgboost_config_from_file(self, tmp_path):
        """Test loading XGBoost config from YAML file"""
        config_data = {
            "model": {
                "type": "xgboost",
                "max_depth": 6,
                "learning_rate": 0.1,
                "n_estimators": 100,
                "objective": "reg:squarederror",
                "booster": "gbtree",
            },
            "training": {
                "early_stopping_rounds": 10,
                "eval_metric": "rmse",
                "verbose": True,
            },
            "features": {
                "lookback_window": 60,
                "forecast_horizons": ["1h", "4h", "24h"],
                "include_exogenous": True,
                "exogenous_variables": ["DXY", "VIX"],
                "lag_periods": [1, 2, 3, 5, 10],
                "rolling_windows": [5, 10, 20],
                "use_technical_indicators": True,
                "indicators": ["rsi_14", "macd"],
            },
            "data": {
                "train_window_days": 30,
                "val_window_days": 5,
                "test_window_days": 5,
                "slide_days": 5,
                "min_data_points": 1000,
            },
        }

        # Write temp config file
        config_file = tmp_path / "test_xgboost_config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Load config
        config = load_xgboost_config(str(config_file))

        assert config.model.type == "xgboost"
        assert config.model.max_depth == 6
        assert config.training.eval_metric == "rmse"


class TestTrainingConfig:
    """Test suite for training configuration"""

    def test_training_config_valid(self):
        """Test valid training configuration"""
        config = TrainingConfig(
            learning_rate=0.001,
            batch_size=64,
            max_epochs=100,
            early_stopping_patience=10,
            optimizer="adam",
            loss_function="mse",
            gradient_clip=1.0,
        )

        assert config.learning_rate == 0.001
        assert config.batch_size == 64

    def test_training_config_invalid_learning_rate(self):
        """Test validation error for invalid learning rate"""
        with pytest.raises(ValueError):
            TrainingConfig(
                learning_rate=-0.001,  # Invalid: must be > 0
                batch_size=64,
                max_epochs=100,
                early_stopping_patience=10,
                optimizer="adam",
                loss_function="mse",
                gradient_clip=1.0,
            )

    def test_training_config_invalid_optimizer(self):
        """Test validation error for invalid optimizer"""
        with pytest.raises(ValueError):
            TrainingConfig(
                learning_rate=0.001,
                batch_size=64,
                max_epochs=100,
                early_stopping_patience=10,
                optimizer="invalid_optimizer",  # Invalid: not in allowed list
                loss_function="mse",
                gradient_clip=1.0,
            )


class TestFeaturesConfig:
    """Test suite for features configuration"""

    def test_features_config_valid(self):
        """Test valid features configuration"""
        config = FeaturesConfig(
            lookback_window=60,
            forecast_horizons=["1h", "4h", "24h"],
            include_exogenous=True,
            exogenous_variables=["DXY", "VIX"],
            use_technical_indicators=True,
            indicators=["rsi_14", "macd"],
        )

        assert config.lookback_window == 60
        assert len(config.forecast_horizons) == 3

    def test_features_config_invalid_lookback_window(self):
        """Test validation error for invalid lookback window"""
        with pytest.raises(ValueError):
            FeaturesConfig(
                lookback_window=5,  # Invalid: must be >= 10
                forecast_horizons=["1h"],
                include_exogenous=False,
                exogenous_variables=[],
                use_technical_indicators=False,
                indicators=[],
            )


class TestDataConfig:
    """Test suite for data configuration"""

    def test_data_config_valid(self):
        """Test valid data configuration"""
        config = DataConfig(
            train_window_days=30,
            val_window_days=5,
            test_window_days=5,
            slide_days=5,
            min_data_points=1000,
        )

        assert config.train_window_days == 30
        assert config.val_window_days == 5

    def test_data_config_invalid_train_window(self):
        """Test validation error for invalid train window"""
        with pytest.raises(ValueError):
            DataConfig(
                train_window_days=200,  # Invalid: must be <= 180
                val_window_days=5,
                test_window_days=5,
                slide_days=5,
                min_data_points=1000,
            )


class TestConfigErrorHandling:
    """Test suite for configuration error handling"""

    def test_load_config_file_not_found(self):
        """Test error handling for missing config file"""
        with pytest.raises(FileNotFoundError):
            load_lstm_config("/nonexistent/path/to/config.yaml")

    def test_load_config_invalid_yaml(self, tmp_path):
        """Test error handling for invalid YAML syntax"""
        config_file = tmp_path / "invalid.yaml"
        with open(config_file, "w") as f:
            f.write("invalid: yaml: syntax:")

        with pytest.raises(yaml.YAMLError):
            load_lstm_config(str(config_file))

    def test_load_config_missing_required_field(self, tmp_path):
        """Test error handling for missing required fields"""
        config_data = {
            "model": {"type": "lstm"},  # Missing required fields
            "training": {},
            "features": {},
            "data": {},
        }

        config_file = tmp_path / "incomplete.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ValueError):
            load_lstm_config(str(config_file))
