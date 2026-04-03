"""
Reversal Classifier Training Pipeline

Trains XGBoost/LSTM classifier to predict reversal points (peaks/valleys)
using ZigZag-labeled historical data.

Features:
- Walk-forward validation for time-series
- Class imbalance handling (SMOTE, class weights)
- MLflow experiment tracking (optional — gracefully degrades if MLflow unavailable)
- Hyperparameter tuning with Optuna (optional)
- Model versioning and deployment
- LSTM support with sequence windowing for temporal patterns
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import os
# Fix oneDNN matmul primitive error on some CPUs (must be set before torch import)
os.environ["DNNL_DEFAULT_FPMATH_MODE"] = "STRICT"
os.environ["TORCH_MKLDNN_ENABLED"] = "0"
os.environ["ONEDNN_PRIMITIVE_CACHE_CAPACITY"] = "0"

import numpy as np
import torch
# Disable MKL-DNN (oneDNN) backend to avoid matmul primitive errors
torch.backends.mkldnn.enabled = False
import torch.nn as nn
import xgboost as xgb
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
)

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.config import get_database
from src.database.models.training_runs import TrainingRun, TrainingStatus
from src.ml.features.reversal_features import ReversalFeatureExtractor

logger = logging.getLogger(__name__)


# Default LSTM lookback window for sequence creation
LSTM_LOOKBACK = 20


class LSTMClassifier(nn.Module):
    """
    LSTM classifier for reversal prediction (3 classes: valley, neither, peak).

    Wraps a bidirectional LSTM with attention into a classifier that outputs
    class probabilities via softmax. Uses CrossEntropyLoss for training.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
        num_classes: int = 3,
    ):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=True,
            batch_first=True,
        )

        # Attention layer
        lstm_out_size = hidden_size * 2  # bidirectional
        self.attention = nn.Linear(lstm_out_size, 1)

        # Classification head
        self.fc = nn.Sequential(
            nn.Linear(lstm_out_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

        self.to(self.device)

    def forward(self, x):
        # x: (batch, seq_len, features)
        lstm_out, _ = self.lstm(x)
        # Attention-weighted sum
        attn_weights = torch.softmax(self.attention(lstm_out), dim=1)
        context = torch.sum(attn_weights * lstm_out, dim=1)
        return self.fc(context)

    def fit(self, X_train, y_train, eval_set=None, verbose=False,
            epochs=50, lr=0.001, batch_size=64):
        """
        Train the LSTM classifier. Mimics XGBoost's fit() interface.

        Args:
            X_train: 3D numpy array (samples, lookback, features)
            y_train: 1D numpy array of class labels (0, 1, 2)
            eval_set: list of (X_val, y_val) tuples
            epochs: max training epochs
            lr: learning rate
            batch_size: mini-batch size
        """
        self.train()
        optimizer = torch.optim.Adam(self.parameters(), lr=lr)
        # Class weights to handle imbalance
        class_counts = np.bincount(y_train.astype(int), minlength=3).astype(float)
        class_counts[class_counts == 0] = 1.0
        weights = 1.0 / class_counts
        weights = weights / weights.sum() * len(weights)
        class_weights = torch.FloatTensor(weights).to(self.device)
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        X_t = torch.FloatTensor(X_train).to(self.device)
        y_t = torch.LongTensor(y_train.astype(int)).to(self.device)

        X_val_t, y_val_t = None, None
        if eval_set:
            X_val_t = torch.FloatTensor(eval_set[0][0]).to(self.device)
            y_val_t = torch.LongTensor(eval_set[0][1].astype(int)).to(self.device)

        best_val_loss = float('inf')
        patience, patience_limit = 0, 10

        for epoch in range(epochs):
            self.train()
            epoch_loss = 0
            n_batches = 0

            indices = torch.randperm(len(X_t))
            for i in range(0, len(X_t), batch_size):
                batch_idx = indices[i:i + batch_size]
                bx, by = X_t[batch_idx], y_t[batch_idx]

                optimizer.zero_grad()
                out = self(bx)
                loss = criterion(out, by)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.parameters(), 1.0)
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            # Validation early stopping
            if X_val_t is not None:
                self.eval()
                with torch.no_grad():
                    val_out = self(X_val_t)
                    val_loss = criterion(val_out, y_val_t).item()
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience = 0
                else:
                    patience += 1
                    if patience >= patience_limit:
                        break

    def predict(self, X):
        """Predict class labels. X is 3D numpy array."""
        self.eval()
        X_t = torch.FloatTensor(X).to(self.device)
        with torch.no_grad():
            logits = self(X_t)
            return logits.argmax(dim=1).cpu().numpy()


def create_sequences(X: np.ndarray, y: np.ndarray, lookback: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert 2D feature matrix into 3D sequences for LSTM.

    Args:
        X: (N, F) feature matrix
        y: (N,) labels
        lookback: number of timesteps per sequence

    Returns:
        X_seq: (N - lookback, lookback, F)
        y_seq: (N - lookback,) — label for the last timestep in each window
    """
    X_seq, y_seq = [], []
    for i in range(lookback, len(X)):
        X_seq.append(X[i - lookback:i])
        y_seq.append(y[i])
    return np.array(X_seq), np.array(y_seq)


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
        mlflow_tracker: Optional[Any] = None,
        enable_mlflow: bool = False
    ):
        self.session = session
        self.mlflow_tracker = mlflow_tracker
        self.enable_mlflow = enable_mlflow and mlflow_tracker is not None
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
            logger.info(f"Class distribution: valleys={np.sum(y == -1)}, neither={np.sum(y == 0)}, peaks={np.sum(y == 1)}")

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

            # Include feature names in results for model persistence
            results['feature_names'] = feature_names

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
        """Train a single model instance (XGBoost or LSTM)."""

        # Map labels from {-1, 0, 1} to {0, 1, 2}
        y_train_mapped = y_train + 1  # -1→0, 0→1, 1→2
        y_val_mapped = y_val + 1

        if model_type == 'xgboost':
            model = self._create_xgboost_classifier(hyperparameters)

            model.fit(
                X_train, y_train_mapped,
                eval_set=[(X_val, y_val_mapped)],
                verbose=False
            )

            y_pred = model.predict(X_val)

        elif model_type == 'lstm':
            lookback = (hyperparameters or {}).get('lookback', LSTM_LOOKBACK)
            hidden_size = (hyperparameters or {}).get('hidden_size', 128)
            num_layers = (hyperparameters or {}).get('num_layers', 2)
            dropout = (hyperparameters or {}).get('dropout', 0.2)
            epochs = (hyperparameters or {}).get('epochs', 50)
            lr = (hyperparameters or {}).get('learning_rate', 0.001)

            # Create sequences for LSTM (2D → 3D)
            X_train_seq, y_train_seq = create_sequences(X_train, y_train_mapped, lookback)
            X_val_seq, y_val_seq = create_sequences(X_val, y_val_mapped, lookback)

            if len(X_train_seq) == 0 or len(X_val_seq) == 0:
                raise ValueError(
                    f"Not enough data for LSTM lookback={lookback}. "
                    f"Train: {len(X_train)} samples, Val: {len(X_val)} samples"
                )

            model = LSTMClassifier(
                input_size=X_train.shape[1],
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout,
            )

            model.fit(
                X_train_seq, y_train_seq,
                eval_set=[(X_val_seq, y_val_seq)],
                epochs=epochs,
                lr=lr,
            )

            y_pred = model.predict(X_val_seq)
            # Use only the matching validation labels (after sequence windowing)
            y_val_mapped = y_val_seq

        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        # Map predictions back to {-1, 0, 1}
        y_pred = y_pred - 1
        y_val_orig = y_val_mapped - 1

        # Calculate metrics
        metrics = self._calculate_classification_metrics(y_val_orig, y_pred)

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
        """Save trained model to MLflow registry (if tracker available)."""

        if self.mlflow_tracker is None:
            return f"v{run.id}"

        try:
            self.mlflow_tracker.start_run(run_name=run.run_name)

            # Log parameters
            self.mlflow_tracker.log_params(run.hyperparameters)

            # Log metrics (filter out non-numeric values like confusion_matrix)
            numeric_metrics = {
                k: v for k, v in metrics.items()
                if isinstance(v, (int, float)) and not np.isnan(v)
            }
            self.mlflow_tracker.log_metrics(numeric_metrics)

            # Log model
            self.mlflow_tracker.log_model(model, "model")

            # Get MLflow run ID
            run.mlflow_run_id = self.mlflow_tracker.get_run_id()

            model_version = f"v{run.id}"
            logger.info(f"Model saved to MLflow: {model_version}")
            return model_version

        except Exception as e:
            logger.warning(f"MLflow save failed (non-fatal): {e}")
            return f"v{run.id}"

        finally:
            try:
                self.mlflow_tracker.end_run()
            except Exception:
                pass


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
