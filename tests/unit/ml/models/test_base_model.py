"""
Unit tests for BaseModel abstract interface
Tests common model interface for LSTM and XGBoost
"""

import pytest
from abc import ABC
import numpy as np

from src.ml.models.base_model import BaseModel


class MockModel(BaseModel):
    """Concrete implementation for testing"""

    def train(self, X, y, **kwargs):
        """Mock train implementation"""
        self.is_trained = True
        return {"loss": 0.5}

    def predict(self, X):
        """Mock predict implementation"""
        if not self.is_trained:
            raise ValueError("Model not trained")
        return np.random.random(len(X))

    def save(self, filepath):
        """Mock save implementation"""
        return True

    def load(self, filepath):
        """Mock load implementation"""
        self.is_trained = True
        return True


class TestBaseModel:
    """Test suite for BaseModel interface"""

    def test_base_model_is_abstract(self):
        """Test that BaseModel cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseModel()

    def test_concrete_model_implements_interface(self):
        """Test that concrete model implements all abstract methods"""
        model = MockModel()

        assert hasattr(model, 'train')
        assert hasattr(model, 'predict')
        assert hasattr(model, 'save')
        assert hasattr(model, 'load')

    def test_model_train_method(self):
        """Test model train method"""
        model = MockModel()

        X = np.random.random((100, 10))
        y = np.random.random(100)

        metrics = model.train(X, y)

        assert isinstance(metrics, dict)
        assert 'loss' in metrics

    def test_model_predict_requires_training(self):
        """Test that predict requires model to be trained"""
        model = MockModel()

        X = np.random.random((10, 10))

        with pytest.raises(ValueError, match="not trained"):
            model.predict(X)

    def test_model_predict_after_training(self):
        """Test predict works after training"""
        model = MockModel()

        X_train = np.random.random((100, 10))
        y_train = np.random.random(100)

        model.train(X_train, y_train)

        X_test = np.random.random((10, 10))
        predictions = model.predict(X_test)

        assert len(predictions) == len(X_test)

    def test_model_save_and_load(self):
        """Test model save and load"""
        model = MockModel()

        # Save
        saved = model.save("/tmp/test_model.pkl")
        assert saved is True

        # Load
        loaded = model.load("/tmp/test_model.pkl")
        assert loaded is True
