"""
Unit tests for XGBoost Forecaster model.
Tests XGBoost with engineered features.
Based on research.md TD-002
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path


class TestXGBoostForecasterInitialization:
    """Test suite for XGBoost model initialization."""

    def test_xgboost_forecaster_imports(self):
        """Test XGBoost forecaster can be imported."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        assert XGBoostForecaster is not None

    def test_xgboost_init_with_default_params(self):
        """Test XGBoost initialization with default parameters."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster()
        
        assert model.max_depth == 6  # Default from config
        assert model.learning_rate == 0.1
        assert model.n_estimators == 100

    def test_xgboost_init_with_custom_params(self):
        """Test XGBoost initialization with custom parameters."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(
            max_depth=8,
            learning_rate=0.05,
            n_estimators=200,
            subsample=0.9
        )
        
        assert model.max_depth == 8
        assert model.learning_rate == 0.05
        assert model.n_estimators == 200
        assert model.subsample == 0.9


class TestXGBoostForecasterTraining:
    """Test suite for XGBoost training."""

    def test_train_with_valid_data(self):
        """Test training with valid tabular data."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=10)
        
        # Create sample data (2D: samples x features)
        X_train = np.random.randn(100, 20).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        X_val = np.random.randn(20, 20).astype(np.float32)
        y_val = np.random.randn(20).astype(np.float32)
        
        metrics = model.train(X_train, y_train, X_val, y_val)
        
        assert isinstance(metrics, dict)
        assert 'train_rmse' in metrics
        assert 'val_rmse' in metrics
        assert model.is_trained is True

    def test_train_with_early_stopping(self):
        """Test early stopping based on validation performance."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(
            n_estimators=100,
            early_stopping_rounds=5
        )
        
        X_train = np.random.randn(100, 15).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        X_val = np.random.randn(20, 15).astype(np.float32)
        y_val = np.random.randn(20).astype(np.float32)
        
        metrics = model.train(X_train, y_train, X_val, y_val)
        
        assert 'best_iteration' in metrics
        # Should stop before max iterations
        assert metrics['best_iteration'] <= 100

    def test_train_tracks_feature_importance(self):
        """Test that feature importance is tracked after training."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=10)
        
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        
        model.train(X_train, y_train)
        
        importance = model.get_feature_importance()
        assert importance is not None
        assert len(importance) == 10

    def test_train_requires_2d_input(self):
        """Test that training requires 2D input (samples, features)."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster()
        
        # 1D input should fail
        X_train = np.random.randn(100).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        
        with pytest.raises(ValueError, match="2D.*shape"):
            model.train(X_train, y_train)


class TestXGBoostForecasterPrediction:
    """Test suite for XGBoost prediction."""

    def test_predict_returns_correct_shape(self):
        """Test predict returns correct output shape."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=5)
        
        # Train model first
        X_train = np.random.randn(100, 15).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        model.train(X_train, y_train)
        
        # Predict
        X_test = np.random.randn(20, 15).astype(np.float32)
        predictions = model.predict(X_test)
        
        assert predictions.shape == (20,)
        assert isinstance(predictions, np.ndarray)

    def test_predict_requires_trained_model(self):
        """Test prediction requires trained model."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster()
        X_test = np.random.randn(20, 15).astype(np.float32)
        
        with pytest.raises(ValueError, match="not.*trained"):
            model.predict(X_test)

    def test_predict_consistent_with_training_features(self):
        """Test prediction requires same number of features as training."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=5)
        
        # Train with 10 features
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        model.train(X_train, y_train)
        
        # Predict with wrong number of features
        X_test_wrong = np.random.randn(20, 15).astype(np.float32)
        
        with pytest.raises(ValueError, match="feature.*mismatch"):
            model.predict(X_test_wrong)


class TestXGBoostForecasterSaveLoad:
    """Test suite for XGBoost save/load functionality."""

    def test_save_creates_model_file(self, tmp_path):
        """Test save creates model file."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=5)
        
        # Train model
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        model.train(X_train, y_train)
        
        # Save
        model_path = tmp_path / "xgboost_model.json"
        model.save(str(model_path))
        
        assert model_path.exists()

    def test_load_restores_model_predictions(self, tmp_path):
        """Test load restores exact model predictions."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        # Train and save model
        model1 = XGBoostForecaster(n_estimators=5, random_state=42)
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        model1.train(X_train, y_train)
        
        model_path = tmp_path / "xgboost_model.json"
        model1.save(str(model_path))
        
        # Create new model and load
        model2 = XGBoostForecaster()
        model2.load(str(model_path))
        
        # Verify predictions match
        X_test = np.random.randn(20, 10).astype(np.float32)
        pred1 = model1.predict(X_test)
        pred2 = model2.predict(X_test)
        
        np.testing.assert_array_almost_equal(pred1, pred2, decimal=5)

    def test_load_sets_trained_flag(self, tmp_path):
        """Test load sets is_trained flag."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        # Save trained model
        model1 = XGBoostForecaster(n_estimators=5)
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        model1.train(X_train, y_train)
        
        model_path = tmp_path / "xgboost_model.json"
        model1.save(str(model_path))
        
        # Load into new model
        model2 = XGBoostForecaster()
        assert model2.is_trained is False
        
        model2.load(str(model_path))
        assert model2.is_trained is True


class TestXGBoostForecasterFeatureImportance:
    """Test suite for feature importance analysis."""

    def test_get_feature_importance_after_training(self):
        """Test feature importance is available after training."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=10)
        
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        model.train(X_train, y_train)
        
        importance = model.get_feature_importance()
        
        assert isinstance(importance, dict)
        assert len(importance) == 10
        assert all(v >= 0 for v in importance.values())

    def test_get_feature_importance_with_feature_names(self):
        """Test feature importance with named features."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(n_estimators=10)
        
        feature_names = [f"feature_{i}" for i in range(10)]
        X_train = np.random.randn(100, 10).astype(np.float32)
        y_train = np.random.randn(100).astype(np.float32)
        
        model.train(X_train, y_train, feature_names=feature_names)
        importance = model.get_feature_importance()
        
        assert all(name in importance for name in feature_names)

    def test_get_feature_importance_before_training_fails(self):
        """Test getting feature importance before training fails."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster()
        
        with pytest.raises(ValueError, match="not.*trained"):
            model.get_feature_importance()


class TestXGBoostForecasterHyperparameters:
    """Test suite for hyperparameter configuration."""

    def test_custom_objective_function(self):
        """Test custom objective function."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(objective='reg:squarederror')
        assert model.objective == 'reg:squarederror'

    def test_regularization_parameters(self):
        """Test L1/L2 regularization parameters."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(
            reg_alpha=0.1,  # L1
            reg_lambda=1.0   # L2
        )
        
        assert model.reg_alpha == 0.1
        assert model.reg_lambda == 1.0

    def test_tree_parameters(self):
        """Test tree-specific parameters."""
        from src.ml.models.xgboost_forecaster import XGBoostForecaster
        
        model = XGBoostForecaster(
            max_depth=8,
            min_child_weight=2,
            gamma=0.1
        )
        
        assert model.max_depth == 8
        assert model.min_child_weight == 2
        assert model.gamma == 0.1
