"""
Reversal Training Service

Full ML training pipeline: indicators → ZigZag labels → train models → save best.

Extracted from scripts/train_and_compare.py for reuse by API routes and MCP tools.
"""
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.ml.labeling.zigzag_labeler import ZigZagConfig
from src.ml.labeling.zigzag_label_service import ZigZagLabelService
from src.ml.training.train_reversal_classifier import ReversalClassifierTrainer
from src.services.indicator_compute_service import IndicatorComputeService

logger = logging.getLogger(__name__)

# Per-symbol ZigZag point size (price precision)
ZIGZAG_POINT_SIZE = {
    "CrudeOIL": 0.01,
    "XAUUSD": 0.01,
    "GBPJPY": 0.001,
    "BRENT_OIL": 0.01,
    "USA500": 0.01,
}

# Default model configurations
DEFAULT_MODEL_CONFIGS = [
    {
        "name": "XGB-default",
        "model_type": "xgboost",
        "hyperparameters": {
            "max_depth": 6,
            "learning_rate": 0.1,
            "n_estimators": 200,
        },
    },
    {
        "name": "XGB-aggressive",
        "model_type": "xgboost",
        "hyperparameters": {
            "max_depth": 8,
            "learning_rate": 0.05,
            "n_estimators": 500,
        },
    },
    {
        "name": "XGB-conservative",
        "model_type": "xgboost",
        "hyperparameters": {
            "max_depth": 4,
            "learning_rate": 0.2,
            "n_estimators": 100,
        },
    },
    {
        "name": "LSTM-default",
        "model_type": "lstm",
        "hyperparameters": {
            "lookback": 20,
            "hidden_size": 128,
            "num_layers": 2,
            "dropout": 0.2,
            "epochs": 50,
            "learning_rate": 0.001,
        },
    },
]

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "reversal_classifier"


class ReversalTrainingService:
    """
    Full ML training pipeline service.

    Usage:
        async with db.get_session() as session:
            service = ReversalTrainingService(session)
            result = await service.train_pipeline("CrudeOIL", "H1")
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.indicator_service = IndicatorComputeService(session)

    async def train_pipeline(
        self,
        symbol: str,
        timeframe: str,
        skip_indicators: bool = False,
        skip_labels: bool = False,
        model_configs: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Run the full training pipeline for a symbol/timeframe.

        Steps:
          1. Compute indicators (unless skip_indicators)
          2. Generate ZigZag labels (unless skip_labels)
          3. Train all model configs
          4. Save best model per type to disk

        Returns dict with results for all models and path to saved best model.
        """
        active_configs = model_configs or DEFAULT_MODEL_CONFIGS
        t0 = time.time()

        # Step 1: Compute indicators
        indicator_result = None
        if not skip_indicators:
            logger.info(f"Step 1: Computing indicators for {symbol} {timeframe}...")
            indicator_result = await self.indicator_service.compute_for_symbol(
                symbol, timeframe, force=False
            )
            logger.info(f"  Indicators: {indicator_result['status']}")

        # Step 2: ZigZag labeling
        label_result = None
        if not skip_labels:
            logger.info(f"Step 2: ZigZag labeling for {symbol} {timeframe}...")
            label_result = await self._run_zigzag_labeling(symbol, timeframe)
            peaks = label_result.get("peaks", 0)
            valleys = label_result.get("valleys", 0)
            logger.info(f"  Labels: {peaks} peaks, {valleys} valleys")

            if peaks == 0 and valleys == 0:
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "no_labels",
                    "indicator_result": indicator_result,
                    "label_result": label_result,
                    "model_results": [],
                    "best_model_dir": None,
                    "elapsed_seconds": round(time.time() - t0, 1),
                }

        # Step 3: Train models
        logger.info(f"Step 3: Training {len(active_configs)} model configs...")
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=730)

        model_results = []
        for cfg in active_configs:
            result = await self._train_model_config(
                symbol, timeframe, cfg, start_date, end_date
            )
            model_results.append(result)

        # Step 4: Save best models per type
        xgb_dir = self._save_best_model(model_results, symbol, timeframe, "xgboost")
        lstm_dir = self._save_best_model(model_results, symbol, timeframe, "lstm")
        best_dir = str(xgb_dir or lstm_dir or "")

        elapsed = round(time.time() - t0, 1)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "success",
            "indicator_result": indicator_result,
            "label_result": label_result,
            "model_results": [
                {k: v for k, v in r.items() if k not in ("model", "feature_names")}
                for r in model_results
            ],
            "best_model_dir": best_dir,
            "elapsed_seconds": elapsed,
        }

    async def _run_zigzag_labeling(self, symbol: str, timeframe: str) -> Dict:
        """Run ZigZag labeling for a symbol/timeframe."""
        point_size = ZIGZAG_POINT_SIZE.get(symbol, 0.01)
        config = ZigZagConfig(
            depth=12,
            deviation=5,
            backstep=3,
            point=point_size,
        )
        service = ZigZagLabelService(self.session, config=config)
        return await service.label_symbol(symbol, timeframe)

    async def _train_model_config(
        self,
        symbol: str,
        timeframe: str,
        config: Dict,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Train a single model configuration."""
        model_name = config["name"]
        logger.info(f"  Training {model_name} for {symbol} {timeframe}...")
        t0 = time.time()

        try:
            trainer = ReversalClassifierTrainer(
                self.session,
                enable_mlflow=False,
            )
            result = await trainer.train(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                model_type=config["model_type"],
                hyperparameters=config["hyperparameters"],
                use_smote=True,
                walk_forward=True,
                n_splits=5,
                run_name=f"{model_name}_{symbol}_{timeframe}",
            )

            elapsed = time.time() - t0
            metrics = result.get("metrics", {})

            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "model_name": model_name,
                "model_type": config["model_type"],
                "status": "success",
                "reversal_f1": metrics.get("reversal_f1_mean", metrics.get("reversal_f1", 0)),
                "peak_f1": metrics.get("peak_f1_mean", metrics.get("peak_f1", 0)),
                "valley_f1": metrics.get("valley_f1_mean", metrics.get("valley_f1", 0)),
                "macro_f1": metrics.get("macro_f1_mean", metrics.get("macro_f1", 0)),
                "weighted_f1": metrics.get("weighted_f1_mean", metrics.get("weighted_f1", 0)),
                "elapsed_seconds": round(elapsed, 1),
                "model": result.get("model"),
                "feature_names": result.get("feature_names"),
            }

        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"  {model_name} FAILED: {e}")
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "model_name": model_name,
                "model_type": config["model_type"],
                "status": "failed",
                "error": str(e),
                "reversal_f1": 0,
                "peak_f1": 0,
                "valley_f1": 0,
                "macro_f1": 0,
                "weighted_f1": 0,
                "elapsed_seconds": round(elapsed, 1),
            }

    def _save_best_model(
        self,
        results: List[Dict],
        symbol: str,
        timeframe: str,
        model_type: str,
    ) -> Optional[Path]:
        """
        Save the best model of a given type to disk.

        For XGBoost: model.json + feature_names.json + metadata.json
        For LSTM: lstm_model.pt + lstm_config.json + feature_names.json
        """
        candidates = [
            r for r in results
            if r["status"] == "success"
            and r["model_type"] == model_type
            and r.get("model") is not None
        ]

        if not candidates:
            return None

        best = max(candidates, key=lambda r: r["reversal_f1"])
        model = best["model"]
        feature_names = best.get("feature_names", [])

        model_dir = MODELS_DIR / f"{symbol}_{timeframe}"
        model_dir.mkdir(parents=True, exist_ok=True)

        if model_type == "xgboost":
            # Save XGBoost native format via booster (avoids _estimator_type error)
            model.get_booster().save_model(str(model_dir / "model.json"))

            with open(model_dir / "feature_names.json", "w") as f:
                json.dump(feature_names, f)

        elif model_type == "lstm":
            import torch
            torch.save(model.state_dict(), str(model_dir / "lstm_model.pt"))

            # Save LSTM config for loading
            lstm_config = best.get("hyperparameters", {})
            lstm_config["n_features"] = len(feature_names)
            with open(model_dir / "lstm_config.json", "w") as f:
                json.dump(lstm_config, f, indent=2)

            with open(model_dir / "feature_names.json", "w") as f:
                json.dump(feature_names, f)

        # Save metadata
        metadata = {
            "symbol": symbol,
            "timeframe": timeframe,
            "model_name": best["model_name"],
            "model_type": model_type,
            "training_date": datetime.utcnow().isoformat(),
            "reversal_f1": best["reversal_f1"],
            "peak_f1": best["peak_f1"],
            "valley_f1": best["valley_f1"],
            "macro_f1": best["macro_f1"],
            "weighted_f1": best["weighted_f1"],
            "feature_count": len(feature_names),
            "elapsed_seconds": best["elapsed_seconds"],
        }
        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved best {model_type} model to {model_dir}")
        return model_dir
