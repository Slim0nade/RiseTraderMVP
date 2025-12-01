"""
Integration tests for MLTrainingService.
Tests complete training pipeline orchestration with all components.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from src.services.ml_training_service import MLTrainingService
from src.database.models.training_runs import TrainingRun, TrainingStatus
from src.database.models.model_metrics import ModelMetrics


@pytest.fixture
def mock_data_loader():
    """Mock MarketDataLoader for testing."""
    loader = AsyncMock()

    # Create sample OHLCV data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
    sample_df = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.randn(100) * 2 + 75,
        'high': np.random.randn(100) * 2 + 77,
        'low': np.random.randn(100) * 2 + 73,
        'close': np.random.randn(100) * 2 + 75,
        'volume': np.random.randint(100000, 1000000, 100)
    })

    loader.load_ohlcv.return_value = sample_df
    return loader


@pytest.fixture
def mock_training_run_repo():
    """Mock TrainingRunRepository."""
    repo = AsyncMock()

    # Mock create response
    created_run = Mock(spec=TrainingRun)
    created_run.id = 1
    created_run.run_name = 'test_run'
    created_run.symbol = 'CrudeOIL'
    created_run.model_type = 'xgboost'
    created_run.status = TrainingStatus.RUNNING
    repo.create.return_value = created_run

    # Mock update_status response
    updated_run = Mock(spec=TrainingRun)
    updated_run.id = 1
    updated_run.status = TrainingStatus.COMPLETED
    repo.update_status.return_value = updated_run

    return repo


@pytest.fixture
def mock_metrics_repo():
    """Mock ModelMetricsRepository."""
    repo = AsyncMock()

    # Mock create response
    created_metrics = Mock(spec=ModelMetrics)
    created_metrics.id = 1
    created_metrics.model_version = 'v1.0.0'
    created_metrics.rmse = 0.8
    repo.create.return_value = created_metrics

    return repo


@pytest.fixture
def training_config():
    """Standard training configuration."""
    return {
        'data': {
            'train_window_days': 30
        },
        'features': {
            'lag_periods': [1, 2, 3, 5, 10]
        },
        'model': {
            'hidden_size': 128,
            'num_layers': 2,
            'learning_rate': 0.001
        },
        'training': {
            'epochs': 50,
            'batch_size': 32
        }
    }


@pytest.fixture
def ml_training_service(mock_data_loader, mock_training_run_repo, mock_metrics_repo):
    """Create MLTrainingService with mocked dependencies."""
    return MLTrainingService(
        data_loader=mock_data_loader,
        training_run_repo=mock_training_run_repo,
        metrics_repo=mock_metrics_repo
    )


class TestMLTrainingServiceInitialization:
    """Test service initialization."""

    def test_initialization_with_dependencies(
        self, mock_data_loader, mock_training_run_repo, mock_metrics_repo
    ):
        """Test service initializes with all dependencies."""
        service = MLTrainingService(
            data_loader=mock_data_loader,
            training_run_repo=mock_training_run_repo,
            metrics_repo=mock_metrics_repo
        )

        assert service.data_loader == mock_data_loader
        assert service.training_run_repo == mock_training_run_repo
        assert service.metrics_repo == mock_metrics_repo
        assert hasattr(service, 'feature_eng')
        assert hasattr(service, 'validator')

    def test_feature_engineering_initialized(self, ml_training_service):
        """Test FeatureEngineering is initialized."""
        from src.ml.data.feature_engineering import FeatureEngineering

        assert isinstance(ml_training_service.feature_eng, FeatureEngineering)

    def test_validator_initialized(self, ml_training_service):
        """Test WalkForwardValidator is initialized."""
        from src.ml.training.validator import WalkForwardValidator

        assert isinstance(ml_training_service.validator, WalkForwardValidator)


class TestMLTrainingServiceTrainModel:
    """Test train_model orchestration."""

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_train_model_xgboost_success(
        self,
        mock_xgb_class,
        mock_trainer_class,
        ml_training_service,
        mock_data_loader,
        mock_training_run_repo,
        mock_metrics_repo,
        training_config
    ):
        """Test successful XGBoost model training workflow."""
        # Setup mocks
        mock_model = Mock()
        mock_xgb_class.return_value = mock_model

        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.5, 'val_loss': 0.6}
        mock_trainer.evaluate.return_value = {
            'mpe': 2.5,
            'rmse': 0.8,
            'mae': 0.6,
            'mape': 3.2,
            'directional_accuracy': 65.5
        }
        mock_trainer_class.return_value = mock_trainer

        # Execute training
        result = await ml_training_service.train_model(
            symbol='CrudeOIL',
            model_type='xgboost',
            config=training_config,
            run_name='test_xgboost_run'
        )

        # Verify training run created
        mock_training_run_repo.create.assert_called_once()
        create_call = mock_training_run_repo.create.call_args
        assert create_call.kwargs['run_name'] == 'test_xgboost_run'
        assert create_call.kwargs['symbol'] == 'CrudeOIL'
        assert create_call.kwargs['model_type'] == 'xgboost'
        assert create_call.kwargs['status'] == 'running'

        # Verify data loading
        mock_data_loader.load_ohlcv.assert_called_once()

        # Verify model creation
        mock_xgb_class.assert_called_once()

        # Verify training
        mock_trainer.train.assert_called_once()
        mock_trainer.evaluate.assert_called_once()

        # Verify training run updated to completed
        mock_training_run_repo.update_status.assert_called_once()
        update_call = mock_training_run_repo.update_status.call_args
        assert update_call.args[0] == 1  # run.id
        assert update_call.kwargs['status'] == 'completed'
        assert 'final_metrics' in update_call.kwargs

        # Verify metrics saved
        mock_metrics_repo.create.assert_called_once()
        metrics_call = mock_metrics_repo.create.call_args
        assert metrics_call.kwargs['model_type'] == 'xgboost'
        assert metrics_call.kwargs['symbol'] == 'CrudeOIL'
        assert metrics_call.kwargs['mpe'] == 2.5
        assert metrics_call.kwargs['rmse'] == 0.8

        # Verify result structure
        assert 'training_run_id' in result
        assert 'metrics' in result
        assert 'model_version' in result
        assert result['training_run_id'] == 1
        assert result['metrics']['rmse'] == 0.8

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.LSTMForecaster')
    async def test_train_model_lstm_success(
        self,
        mock_lstm_class,
        mock_trainer_class,
        ml_training_service,
        mock_data_loader,
        mock_training_run_repo,
        mock_metrics_repo,
        training_config
    ):
        """Test successful LSTM model training workflow."""
        # Setup mocks
        mock_model = Mock()
        mock_lstm_class.return_value = mock_model

        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.4, 'val_loss': 0.5}
        mock_trainer.evaluate.return_value = {
            'mpe': 1.8,
            'rmse': 0.6,
            'mae': 0.5,
            'mape': 2.5,
            'directional_accuracy': 70.2
        }
        mock_trainer_class.return_value = mock_trainer

        # Execute training
        result = await ml_training_service.train_model(
            symbol='EURUSD',
            model_type='lstm',
            config=training_config,
            run_name='test_lstm_run'
        )

        # Verify LSTM model created
        mock_lstm_class.assert_called_once()

        # Verify result
        assert result['metrics']['rmse'] == 0.6
        assert result['metrics']['directional_accuracy'] == 70.2

    @pytest.mark.asyncio
    async def test_train_model_unknown_model_type(
        self,
        ml_training_service,
        training_config,
        mock_training_run_repo
    ):
        """Test training with unknown model type raises error."""
        with pytest.raises(ValueError, match="Unknown model type"):
            await ml_training_service.train_model(
                symbol='CrudeOIL',
                model_type='unknown_model',
                config=training_config,
                run_name='test_run'
            )

        # Verify training run marked as failed
        mock_training_run_repo.update_status.assert_called_once()
        update_call = mock_training_run_repo.update_status.call_args
        assert update_call.kwargs['status'] == 'failed'
        assert 'error_message' in update_call.kwargs


class TestMLTrainingServiceDataLoading:
    """Test data loading integration."""

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_data_loading_date_range(
        self,
        mock_xgb_class,
        mock_trainer_class,
        ml_training_service,
        mock_data_loader,
        training_config
    ):
        """Test data loading with correct date range."""
        # Setup mocks
        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.5}
        mock_trainer.evaluate.return_value = {'rmse': 0.8, 'mpe': 2.0, 'mae': 0.6, 'mape': 3.0}
        mock_trainer_class.return_value = mock_trainer

        await ml_training_service.train_model(
            symbol='CrudeOIL',
            model_type='xgboost',
            config=training_config,
            run_name='test_run'
        )

        # Verify load_ohlcv called with symbol and date range
        mock_data_loader.load_ohlcv.assert_called_once()
        call_args = mock_data_loader.load_ohlcv.call_args
        assert call_args.args[0] == 'CrudeOIL'

        # Check date range (should be ~30 days)
        start_date = call_args.args[1]
        end_date = call_args.args[2]
        date_diff = (end_date - start_date).days
        assert 25 <= date_diff <= 35  # Allow some tolerance

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_data_loading_custom_window(
        self,
        mock_xgb_class,
        mock_trainer_class,
        ml_training_service,
        mock_data_loader
    ):
        """Test data loading with custom train window."""
        config = {
            'data': {'train_window_days': 60},
            'features': {'lag_periods': [1, 2, 3]},
            'model': {},
            'training': {}
        }

        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.5}
        mock_trainer.evaluate.return_value = {'rmse': 0.8, 'mpe': 2.0, 'mae': 0.6, 'mape': 3.0}
        mock_trainer_class.return_value = mock_trainer

        await ml_training_service.train_model(
            symbol='CrudeOIL',
            model_type='xgboost',
            config=config,
            run_name='test_run'
        )

        # Verify 60-day window
        call_args = mock_data_loader.load_ohlcv.call_args
        start_date = call_args.args[1]
        end_date = call_args.args[2]
        date_diff = (end_date - start_date).days
        assert 55 <= date_diff <= 65


class TestMLTrainingServiceFeatureEngineering:
    """Test feature engineering integration."""

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_feature_engineering_applied(
        self,
        mock_xgb_class,
        mock_trainer_class,
        ml_training_service,
        training_config
    ):
        """Test feature engineering creates lag and technical features."""
        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.5}
        mock_trainer.evaluate.return_value = {'rmse': 0.8, 'mpe': 2.0, 'mae': 0.6, 'mape': 3.0}
        mock_trainer_class.return_value = mock_trainer

        # Mock feature engineering methods
        with patch.object(ml_training_service.feature_eng, 'create_lag_features') as mock_lag, \
             patch.object(ml_training_service.feature_eng, 'create_rolling_features') as mock_rolling, \
             patch.object(ml_training_service.feature_eng, 'create_technical_indicators') as mock_tech:

            # Make each return the input df for chaining
            mock_lag.side_effect = lambda df, periods: df
            mock_rolling.side_effect = lambda df, windows: df
            mock_tech.side_effect = lambda df: df

            await ml_training_service.train_model(
                symbol='CrudeOIL',
                model_type='xgboost',
                config=training_config,
                run_name='test_run'
            )

            # Verify all feature engineering steps called
            mock_lag.assert_called_once()
            mock_rolling.assert_called_once()
            mock_tech.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_feature_engineering_lag_periods(
        self,
        mock_xgb_class,
        mock_trainer_class,
        ml_training_service,
        training_config
    ):
        """Test feature engineering uses configured lag periods."""
        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.5}
        mock_trainer.evaluate.return_value = {'rmse': 0.8, 'mpe': 2.0, 'mae': 0.6, 'mape': 3.0}
        mock_trainer_class.return_value = mock_trainer

        with patch.object(ml_training_service.feature_eng, 'create_lag_features') as mock_lag, \
             patch.object(ml_training_service.feature_eng, 'create_rolling_features') as mock_rolling, \
             patch.object(ml_training_service.feature_eng, 'create_technical_indicators') as mock_tech:

            mock_lag.side_effect = lambda df, periods: df
            mock_rolling.side_effect = lambda df, windows: df
            mock_tech.side_effect = lambda df: df

            await ml_training_service.train_model(
                symbol='CrudeOIL',
                model_type='xgboost',
                config=training_config,
                run_name='test_run'
            )

            # Verify lag periods from config
            call_args = mock_lag.call_args
            assert call_args.args[1] == [1, 2, 3, 5, 10]


class TestMLTrainingServiceValidation:
    """Test walk-forward validation integration."""

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.ModelTrainer')
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_walk_forward_split_used(
        self,
        mock_xgb_class,
        mock_trainer_class,
        ml_training_service,
        training_config
    ):
        """Test walk-forward validation split is used."""
        mock_trainer = Mock()
        mock_trainer.train.return_value = {'train_loss': 0.5}
        mock_trainer.evaluate.return_value = {'rmse': 0.8, 'mpe': 2.0, 'mae': 0.6, 'mape': 3.0}
        mock_trainer_class.return_value = mock_trainer

        with patch.object(ml_training_service.validator, 'split') as mock_split:
            # Create mock splits
            train_df = pd.DataFrame({'close': [1, 2, 3], 'timestamp': pd.date_range('2024-01-01', periods=3)})
            val_df = pd.DataFrame({'close': [4, 5], 'timestamp': pd.date_range('2024-01-04', periods=2)})
            test_df = pd.DataFrame({'close': [6, 7], 'timestamp': pd.date_range('2024-01-06', periods=2)})
            mock_split.return_value = [(train_df, val_df, test_df)]

            await ml_training_service.train_model(
                symbol='CrudeOIL',
                model_type='xgboost',
                config=training_config,
                run_name='test_run'
            )

            # Verify split was called
            mock_split.assert_called_once()

            # Verify trainer used split data
            mock_trainer.train.assert_called_once()
            mock_trainer.evaluate.assert_called_once()


class TestMLTrainingServiceErrorHandling:
    """Test error handling in training pipeline."""

    @pytest.mark.asyncio
    @patch('src.services.ml_training_service.XGBoostForecaster')
    async def test_training_failure_updates_run_status(
        self,
        mock_xgb_class,
        ml_training_service,
        mock_data_loader,
        mock_training_run_repo,
        training_config
    ):
        """Test failed training updates run status to failed."""
        # Make model training raise an error
        mock_xgb_class.side_effect = RuntimeError("Training failed")

        with pytest.raises(RuntimeError, match="Training failed"):
            await ml_training_service.train_model(
                symbol='CrudeOIL',
                model_type='xgboost',
                config=training_config,
                run_name='test_run'
            )

        # Verify training run marked as failed
        mock_training_run_repo.update_status.assert_called_once()
        update_call = mock_training_run_repo.update_status.call_args
        assert update_call.kwargs['status'] == 'failed'
        assert 'Training failed' in update_call.kwargs['error_message']

    @pytest.mark.asyncio
    async def test_data_loading_failure(
        self,
        ml_training_service,
        mock_data_loader,
        mock_training_run_repo,
        training_config
    ):
        """Test data loading failure is handled."""
        mock_data_loader.load_ohlcv.side_effect = Exception("Data load failed")

        with pytest.raises(Exception, match="Data load failed"):
            await ml_training_service.train_model(
                symbol='CrudeOIL',
                model_type='xgboost',
                config=training_config,
                run_name='test_run'
            )

        # Verify status updated
        update_call = mock_training_run_repo.update_status.call_args
        assert update_call.kwargs['status'] == 'failed'


class TestMLTrainingServicePrepareArrays:
    """Test data preparation helper method."""

    def test_prepare_arrays_xgboost(self, ml_training_service):
        """Test array preparation for XGBoost."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=10),
            'close': np.arange(10, dtype=float),
            'feature1': np.arange(10, dtype=float),
            'feature2': np.arange(10, 20, dtype=float)
        })

        X, y = ml_training_service._prepare_arrays(df, 'xgboost')

        assert X.shape == (10, 2)  # 2 features
        assert y.shape == (10,)
        assert X.dtype == np.float32
        assert y.dtype == np.float32

    def test_prepare_arrays_lstm(self, ml_training_service):
        """Test array preparation for LSTM with reshaping."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=10),
            'close': np.arange(10, dtype=float),
            'feature1': np.arange(10, dtype=float),
            'feature2': np.arange(10, 20, dtype=float)
        })

        X, y = ml_training_service._prepare_arrays(df, 'lstm')

        assert X.ndim == 3  # LSTM needs 3D input
        assert y.shape == (10, 1)
        assert X.dtype == np.float32
        assert y.dtype == np.float32

    def test_prepare_arrays_excludes_timestamp_and_close(self, ml_training_service):
        """Test timestamp and close are excluded from features."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5),
            'close': [100, 101, 102, 103, 104],
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50]
        })

        X, y = ml_training_service._prepare_arrays(df, 'xgboost')

        # Only feature1 and feature2 should be in X
        assert X.shape[1] == 2
        # y should be close values
        np.testing.assert_array_equal(y, np.array([100, 101, 102, 103, 104], dtype=np.float32))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
