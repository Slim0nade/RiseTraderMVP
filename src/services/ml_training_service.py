"""ML Training Service - Orchestrates model training with data loading, feature engineering, and MLflow logging."""

from typing import Dict, Any
import numpy as np
from datetime import datetime, timedelta

from src.ml.data.market_data_loader import MarketDataLoader
from src.ml.data.feature_engineering import FeatureEngineering
from src.ml.training.trainer import ModelTrainer
from src.ml.training.validator import WalkForwardValidator
from src.database.repositories.training_run_repository import TrainingRunRepository
from src.database.repositories.model_metrics_repository import ModelMetricsRepository

# Import unified model registry for MVP and SOTA models
from src.ml.models import ModelType, create_model
from src.ml.models.adapters import SOTAtoMVPAdapter
from src.ml.models.base import BaseForecaster


class MLTrainingService:
    """Service for ML model training pipeline."""
    
    def __init__(
        self,
        data_loader: MarketDataLoader,
        training_run_repo: TrainingRunRepository,
        metrics_repo: ModelMetricsRepository
    ):
        self.data_loader = data_loader
        self.training_run_repo = training_run_repo
        self.metrics_repo = metrics_repo
        self.feature_eng = FeatureEngineering()
        self.validator = WalkForwardValidator()
    
    async def train_model(
        self,
        symbol: str,
        model_type: str,
        config: Dict[str, Any],
        run_name: str
    ) -> Dict[str, Any]:
        """
        Execute complete training pipeline.
        
        1. Create training run record
        2. Load and prepare data
        3. Train model with walk-forward validation
        4. Save metrics to database
        5. Return training results
        """
        # Create training run
        run = await self.training_run_repo.create(
            run_name=run_name,
            symbol=symbol,
            model_type=model_type,
            status="running",
            started_at=datetime.utcnow(),
            hyperparameters=config
        )
        
        try:
            # Load historical data
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=config.get('data', {}).get('train_window_days', 30))
            
            df = await self.data_loader.load_ohlcv(symbol, start_date, end_date)
            
            # Engineer features
            lag_periods = config.get('features', {}).get('lag_periods', [1, 2, 3, 5, 10])
            df = self.feature_eng.create_lag_features(df, lag_periods)
            df = self.feature_eng.create_rolling_features(df, [5, 10, 20])
            df = self.feature_eng.create_technical_indicators(df)
            
            # Prepare train/val split
            splits = self.validator.split(df)
            train_df, val_df, test_df = splits[0]  # Use first split
            
            # Create model using unified factory (supports both MVP and SOTA models)
            try:
                model_enum = ModelType(model_type)
            except ValueError:
                raise ValueError(f"Unknown model type: {model_type}. "
                               f"Supported types: {[t.value for t in ModelType]}")

            # Create model instance
            model = create_model(model_enum, config=config, **config.get('model', {}))

            # If SOTA model (BaseForecaster), wrap with adapter for MVP compatibility
            # This allows SOTA models to work with existing training infrastructure
            if isinstance(model, BaseForecaster):
                model = SOTAtoMVPAdapter(model)
            
            # Train model
            trainer = ModelTrainer(model, config)
            
            X_train, y_train = self._prepare_arrays(train_df, model_type)
            X_val, y_val = self._prepare_arrays(val_df, model_type)
            
            metrics = trainer.train(X_train, y_train, X_val, y_val)
            
            # Evaluate on test set
            X_test, y_test = self._prepare_arrays(test_df, model_type)
            test_metrics = trainer.evaluate(X_test, y_test)
            
            # Update training run
            await self.training_run_repo.update_status(
                run.id,
                status="completed",
                completed_at=datetime.utcnow(),
                final_metrics=test_metrics,
                model_version="v1.0.0"
            )
            
            # Save metrics
            await self.metrics_repo.create(
                model_type=model_type,
                model_version="v1.0.0",
                symbol=symbol,
                forecast_horizon="1h",
                **test_metrics
            )
            
            return {
                'training_run_id': run.id,
                'metrics': test_metrics,
                'model_version': "v1.0.0"
            }
            
        except Exception as e:
            await self.training_run_repo.update_status(
                run.id,
                status="failed",
                error_message=str(e)
            )
            raise
    
    def _prepare_arrays(self, df, model_type: str):
        """Convert DataFrame to training arrays."""
        feature_cols = [c for c in df.columns if c not in ['timestamp', 'close']]
        X = df[feature_cols].values
        y = df['close'].values
        
        if model_type == 'lstm':
            # Reshape for LSTM (batch, seq_len, features)
            X = X.reshape(1, len(X), -1) if X.ndim == 2 else X
            y = y.reshape(-1, 1)
        
        return X.astype(np.float32), y.astype(np.float32)
