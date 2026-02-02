"""
Reversal Classifier Training Pipeline

Trains XGBoost/LSTM classifier to predict reversal points (peaks/valleys)
using ZigZag-labeled historical data.

Features:
- Walk-forward validation for time-series
- Class imbalance handling (SMOTE, class weights)
- MLflow experiment tracking
- Hyperparameter tuning with Optuna (optional)
- Model versioning and deployment
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import xgboost as xgb
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score
)

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.config import get_database
from src.database.models.training_runs import TrainingRun, TrainingStatus
from src.ml.features.reversal_features import ReversalFeatureExtractor
from src.ml.tracking.mlflow_tracker import MLflowTracker
from src.ml.models.xgboost_forecaster import XGBoostForecaster

logger = logging.getLogger(__name__)


class ReversalClassifierTrainer:
    """
    Trains reversal classifier with walk-forward validation.

    Usage:
        trainer = ReversalClassifierTrainer(session)
        result = await trainer.train(
            symbol='CrudeOIL',
            timeframe='H1',
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 12, 31)
        )
    """

    def __init__(
        self,
        session: AsyncSession,
        mlflow_tracker: Optional[MLflowTracker] = None,
        enable_mlflow: bool = True
    ):
        self.session = session
        self.mlflow_tracker = mlflow_tracker or MLflowTracker()
        self.enable_mlflow = enable_mlflow
        self.feature_extractor = ReversalFeatureExtractor(session)

    async def train(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        model_type: str = 'xgboost',
        hyperparameters: Optional[Dict] = None,
        use_smote: bool = True,
        walk_forward: bool = True,
        n_splits: int = 5,
        run_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Train reversal classifier.

        Args:
            symbol: Trading symbol (e.g., 'CrudeOIL')
            timeframe: Candle timeframe (e.g., 'H1')
            start_date: Training start date
            end_date: Training end date
            model_type: 'xgboost' or 'lstm'
            hyperparameters: Model hyperparameters (defaults to preset)
            use_smote: Whether to apply SMOTE for class imbalance
            walk_forward: Use walk-forward validation (True) or simple train/val split
            n_splits: Number of walk-forward splits
            run_name: MLflow run name

        Returns:
            Dict with training metrics and model info
        """
        training_start = datetime.utcnow()

        # Create training run record
        run = TrainingRun(
            run_name=run_name or f"reversal_{symbol}_{timeframe}_{training_start.strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            model_type=model_type,
            hyperparameters=hyperparameters or {},
            feature_config={'use_smote': use_smote, 'walk_forward': walk_forward},
            training_config={'n_splits': n_splits},
            status=TrainingStatus.RUNNING,
            started_at=training_start
        )
        self.session.add(run)
        await self.session.commit()

        try:
            logger.info(f"Training reversal classifier: {symbol} {timeframe}")
            logger.info(f"Date range: {start_date} to {end_date}")

            # 1. Extract features and labels
            X, y, feature_names = await self.feature_extractor.extract_training_data(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )

            if len(X) == 0:
                raise ValueError("No training data available")

            logger.info(f"Extracted {len(X)} samples with {len(feature_names)} features")
            logger.info(f"Class distribution: {np.bincount(y + 1)}")  # +1 to handle -1, 0, 1

            # 2. Train model
            if walk_forward:
                results = await self._train_walk_forward(
                    X, y, feature_names, model_type, hyperparameters,
                    use_smote, n_splits, run
                )
            else:
                results = await self._train_simple_split(
                    X, y, feature_names, model_type, hyperparameters,
                    use_smote, run
                )

            # 3. Update training run with results
            run.status = TrainingStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
            run.final_metrics = results['metrics']
            run.model_version = results.get('model_version', 'unknown')

            await self.session.commit()

            logger.info(f"Training completed successfully. Run ID: {run.id}")

            return {
                'run_id': run.id,
                'mlflow_run_id': run.mlflow_run_id,
                **results
            }

        except Exception as e:
            logger.error(f"Training failed: {str(e)}")
            run.status = TrainingStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            await self.session.commit()
            raise

    async def _train_walk_forward(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        model_type: str,
        hyperparameters: Optional[Dict],
        use_smote: bool,
        n_splits: int,
        run: TrainingRun
    ) -> Dict[str, Any]:
        """
        Train with walk-forward validation.

        This is the proper way to validate time-series models.
        """
        logger.info(f"Starting walk-forward validation with {n_splits} splits")

        # TimeSeriesSplit for walk-forward
        tscv = TimeSeriesSplit(n_splits=n_splits)

        fold_metrics = []
        fold_models = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            logger.info(f"Training fold {fold + 1}/{n_splits}")

            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            # Handle class imbalance with SMOTE
            if use_smote:
                X_train, y_train = self._apply_smote(X_train, y_train)

            # Train model for this fold
            model, metrics = await self._train_single_model(
                X_train, y_train, X_val, y_val,
                feature_names, model_type, hyperparameters
            )

            fold_metrics.append(metrics)
            fold_models.append(model)

            logger.info(f"Fold {fold + 1} metrics: {metrics}")

        # Aggregate metrics across folds
        aggregated_metrics = self._aggregate_fold_metrics(fold_metrics)

        # Select best model (highest F1 score for reversals)
        best_fold = np.argmax([m.get('reversal_f1', 0) for m in fold_metrics])
        best_model = fold_models[best_fold]

        logger.info(f"Best fold: {best_fold + 1}")
        logger.info(f"Aggregated metrics: {aggregated_metrics}")

        # Save best model to MLflow
        if self.enable_mlflow:
            model_version = await self._save_model_to_mlflow(
                best_model, feature_names, aggregated_metrics, run
            )
        else:
            model_version = 'no_mlflow'

        return {
            'model': best_model,
            'metrics': aggregated_metrics,
            'fold_metrics': fold_metrics,
            'best_fold': best_fold,
            'model_version': model_version
        }

    async def _train_simple_split(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        model_type: str,
        hyperparameters: Optional[Dict],
        use_smote: bool,
        run: TrainingRun
    ) -> Dict[str, Any]:
        """Train with simple 80/20 train/val split."""

        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        logger.info(f"Train samples: {len(X_train)}, Val samples: {len(X_val)}")

        if use_smote:
            X_train, y_train = self._apply_smote(X_train, y_train)

        model, metrics = await self._train_single_model(
            X_train, y_train, X_val, y_val,
            feature_names, model_type, hyperparameters
        )

        if self.enable_mlflow:
            model_version = await self._save_model_to_mlflow(
                model, feature_names, metrics, run
            )
        else:
            model_version = 'no_mlflow'

        return {
            'model': model,
            'metrics': metrics,
            'model_version': model_version
        }

    async def _train_single_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: List[str],
        model_type: str,
        hyperparameters: Optional[Dict]
    ) -> Tuple[Any, Dict]:
        """Train a single model instance."""

        if model_type == 'xgboost':
            model = self._create_xgboost_classifier(hyperparameters)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        # Map labels from {-1, 0, 1} to {0, 1, 2} for XGBoost
        y_train_mapped = y_train + 1  # -1→0, 0→1, 1→2
        y_val_mapped = y_val + 1

        # Train
        model.fit(
            X_train, y_train_mapped,
            eval_set=[(X_val, y_val_mapped)],
            verbose=False
        )

        # Predict
        y_pred = model.predict(X_val)

        # Map predictions back to {-1, 0, 1}
        y_pred = y_pred - 1

        # Calculate metrics
        metrics = self._calculate_classification_metrics(y_val, y_pred)

        return model, metrics

    def _create_xgboost_classifier(
        self,
        hyperparameters: Optional[Dict]
    ) -> xgb.XGBClassifier:
        """Create XGBoost classifier with defaults or custom hyperparameters."""

        default_params = {
            'objective': 'multi:softprob',
            'num_class': 3,
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 200,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'gamma': 0.1,
            'min_child_weight': 5,
            'reg_alpha': 0.1,
            'reg_lambda': 1.0,
            'early_stopping_rounds': 20,
            'eval_metric': 'mlogloss',
            'random_state': 42,
            'tree_method': 'hist'  # Faster training
        }

        if hyperparameters:
            default_params.update(hyperparameters)

        return xgb.XGBClassifier(**default_params)

    def _apply_smote(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Apply SMOTE to handle class imbalance."""

        logger.info(f"Applying SMOTE. Original distribution: {np.bincount(y + 1)}")

        # SMOTE requires non-negative labels
        y_mapped = y + 1  # -1→0, 0→1, 1→2

        smote = SMOTE(random_state=42, k_neighbors=3)
        X_resampled, y_resampled = smote.fit_resample(X, y_mapped)

        # Map back to {-1, 0, 1}
        y_resampled = y_resampled - 1

        logger.info(f"After SMOTE: {np.bincount(y_resampled + 1)}")

        return X_resampled, y_resampled

    def _calculate_classification_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, float]:
        """Calculate comprehensive classification metrics."""

        # Overall metrics
        precision, recall, f1, support = precision_recall_fscore_support(
            y_true, y_pred, average=None, labels=[-1, 0, 1], zero_division=0
        )

        metrics = {
            # Per-class metrics
            'valley_precision': float(precision[0]),
            'valley_recall': float(recall[0]),
            'valley_f1': float(f1[0]),
            'neither_precision': float(precision[1]),
            'neither_recall': float(recall[1]),
            'neither_f1': float(f1[1]),
            'peak_precision': float(precision[2]),
            'peak_recall': float(recall[2]),
            'peak_f1': float(f1[2]),

            # Aggregate metrics
            'reversal_f1': float((f1[0] + f1[2]) / 2),  # Average of peak + valley F1
            'macro_f1': float(np.mean(f1)),
            'weighted_f1': float(np.average(f1, weights=support)),

            # Confusion matrix
            'confusion_matrix': confusion_matrix(y_true, y_pred, labels=[-1, 0, 1]).tolist()
        }

        return metrics

    def _aggregate_fold_metrics(self, fold_metrics: List[Dict]) -> Dict[str, float]:
        """Aggregate metrics across walk-forward folds."""

        aggregated = {}

        # Get all metric keys from first fold
        metric_keys = [k for k in fold_metrics[0].keys() if k != 'confusion_matrix']

        for key in metric_keys:
            values = [m[key] for m in fold_metrics]
            aggregated[f'{key}_mean'] = float(np.mean(values))
            aggregated[f'{key}_std'] = float(np.std(values))

        return aggregated

    async def _save_model_to_mlflow(
        self,
        model: Any,
        feature_names: List[str],
        metrics: Dict,
        run: TrainingRun
    ) -> str:
        """Save trained model to MLflow registry."""

        self.mlflow_tracker.start_run(run_name=run.run_name)

        try:
            # Log parameters
            self.mlflow_tracker.log_params(run.hyperparameters)

            # Log metrics
            self.mlflow_tracker.log_metrics(metrics)

            # Log model
            import mlflow.xgboost
            mlflow.xgboost.log_model(model, "model")

            # Log feature names
            self.mlflow_tracker.log_artifact_text(
                '\n'.join(feature_names),
                'feature_names.txt'
            )

            # Get MLflow run ID
            run.mlflow_run_id = self.mlflow_tracker.get_run_id()

            # Get model version
            model_version = f"v{run.id}"  # Simple versioning

            logger.info(f"Model saved to MLflow: {model_version}")

            return model_version

        finally:
            self.mlflow_tracker.end_run()


# Standalone training function
async def train_reversal_classifier(
    symbol: str = 'CrudeOIL',
    timeframe: str = 'H1',
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    model_type: str = 'xgboost',
    use_smote: bool = True,
    walk_forward: bool = True,
    n_splits: int = 5
) -> Dict[str, Any]:
    """
    Standalone function to train reversal classifier.

    Usage:
        python -m src.ml.training.train_reversal_classifier
    """
    from src.database.config import initialize_database

    # Default dates: last 2 years
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=730)  # 2 years

    # Initialize database
    initialize_database()
    db = get_database()

    async with db.get_session() as session:
        trainer = ReversalClassifierTrainer(session)
        result = await trainer.train(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            model_type=model_type,
            use_smote=use_smote,
            walk_forward=walk_forward,
            n_splits=n_splits
        )

        print("\n" + "="*60)
        print(f"Reversal Classifier Training Complete")
        print("="*60)
        print(f"Symbol: {symbol} {timeframe}")
        print(f"Model Type: {model_type}")
        print(f"Training Run ID: {result['run_id']}")
        print(f"MLflow Run ID: {result.get('mlflow_run_id', 'N/A')}")
        print("\nMetrics:")
        for key, value in result['metrics'].items():
            if isinstance(value, (int, float)):
                print(f"  {key}: {value:.4f}")
        print("="*60)

        return result


if __name__ == '__main__':
    import sys

    symbol = sys.argv[1] if len(sys.argv) > 1 else 'CrudeOIL'
    timeframe = sys.argv[2] if len(sys.argv) > 2 else 'H1'

    asyncio.run(train_reversal_classifier(symbol, timeframe))
