# RiseTrader State-of-the-Art Forecasting Models
## Implementation Guide for Crude Oil & Gold

**Version:** 1.0.0  
**Date:** November 2025  
**Based on:** 2023-2025 Academic Research Review

---

## Executive Summary

This guide provides complete implementation instructions for integrating state-of-the-art forecasting models into your RiseTrader platform, specifically optimized for **Crude Oil (WTI/Brent)** and **Gold (XAUUSD)**.

### Model Recommendations by Use Case

| Horizon | Crude Oil | Gold | Expected Improvement |
|---------|-----------|------|---------------------|
| Daily (1-5 days) | **TCN** | **BiGRU-Attention** | MAE: 1.44 (WTI) |
| Weekly (7-14 days) | **FEDformer** | **TFT** | 38-57% vs LSTM |
| Monthly (14-30 days) | **FEDformer** | **FEDformer** | Best long-horizon |
| Trading Signals | **PPO + MoE** | **PPO + MoE** | Sharpe: 2.7+ |

---

## Table of Contents

1. [Installation & Dependencies](#1-installation--dependencies)
2. [Directory Structure](#2-directory-structure)
3. [Model Implementations](#3-model-implementations)
   - [TCN for Daily Forecasting](#31-tcn-temporal-convolutional-network)
   - [BiGRU-Attention](#32-bigru-attention)
   - [FEDformer for Long-Horizon](#33-fedformer)
   - [TFT for Probabilistic Forecasting](#34-temporal-fusion-transformer)
   - [Mixture of Experts](#35-mixture-of-experts-moe)
   - [PPO Reinforcement Learning](#36-ppo-trader)
4. [Data Pipeline](#4-data-pipeline)
5. [Training Procedures](#5-training-procedures)
6. [Evaluation & Validation](#6-evaluation--validation)
7. [Production Deployment](#7-production-deployment)
8. [Asset-Specific Configurations](#8-asset-specific-configurations)

---

## 1. Installation & Dependencies

### Update requirements.txt

Add these dependencies to your existing `requirements.txt`:

```txt
# State-of-the-Art ML Models
# =========================

# Core Deep Learning (update existing)
torch>=2.1.0
torchvision>=0.16.0

# Time Series Transformers
pytorch-forecasting>=1.0.0
neuralforecast>=1.6.0

# Reinforcement Learning
stable-baselines3>=2.1.0
gymnasium>=0.29.0

# Signal Processing (for decomposition)
PyWavelets>=1.4.0
EMD-signal>=1.4.0

# Additional utilities
einops>=0.7.0
rotary-embedding-torch>=0.3.0
```

### Install command:

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP
pip install -r requirements.txt
```

---

## 2. Directory Structure

Create this structure in your `src/ml/` directory:

```
src/ml/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── base.py                    # Base classes & interfaces
│   ├── temporal/
│   │   ├── __init__.py
│   │   ├── tcn.py                 # TCN for daily
│   │   └── gru.py                 # BiGRU-Attention
│   ├── transformers/
│   │   ├── __init__.py
│   │   ├── fedformer.py           # FEDformer
│   │   ├── tft.py                 # Temporal Fusion Transformer
│   │   └── patchtst.py            # PatchTST (optional)
│   ├── ensemble/
│   │   ├── __init__.py
│   │   ├── moe.py                 # Mixture of Experts
│   │   └── stacking.py            # Model stacking
│   ├── rl/
│   │   ├── __init__.py
│   │   ├── ppo.py                 # PPO Trader
│   │   └── environment.py         # Trading environment
│   └── decomposition/
│       ├── __init__.py
│       ├── vmd.py                 # Variational Mode Decomposition
│       └── wavelet.py             # Wavelet decomposition
├── data/
│   ├── __init__.py
│   ├── preprocessor.py            # Feature engineering
│   ├── dataset.py                 # PyTorch datasets
│   └── loaders.py                 # Data loading utilities
├── training/
│   ├── __init__.py
│   ├── config.py                  # Model configurations
│   ├── trainer.py                 # Unified trainer
│   └── callbacks.py               # Training callbacks
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py                 # Custom metrics
│   └── backtester.py              # Walk-forward validation
└── inference/
    ├── __init__.py
    └── predictor.py               # Production inference
```

---

## 3. Model Implementations

### 3.1 TCN (Temporal Convolutional Network)

**Best for:** Daily crude oil forecasting  
**Performance:** MAE 1.444 (WTI), 1.295 (Brent) - lowest among all models

#### Key Features:
- Causal convolutions (no future leakage)
- Exponentially growing receptive field
- Residual connections
- Fast inference (~milliseconds)

#### Configuration for Crude Oil:

```yaml
# config/ml/tcn_crude_oil.yaml
model:
  name: "tcn_crude_oil_daily"
  num_channels: [64, 128, 256, 128]
  kernel_size: 3
  dropout: 0.2
  use_weight_norm: true

features:
  lookback_window: 30  # 30 days (research optimal)
  prediction_length: 5  # 5-day forecast
  
training:
  learning_rate: 0.001
  batch_size: 64
  max_epochs: 100
  early_stopping_patience: 15
```

#### Training Example:

```python
from src.ml.models.temporal.tcn import create_tcn_for_crude_oil
from src.ml.data.preprocessor import prepare_commodity_data

# Load and prepare data
train_df, val_df, test_df = prepare_commodity_data(
    symbol="CRUDE_OIL",
    start_date="2015-01-01",
    end_date="2024-12-31",
    train_ratio=0.7,
    val_ratio=0.15
)

# Create model
model = create_tcn_for_crude_oil(input_features=15)  # OHLCV + 10 indicators

# Train
history = model.fit(
    train_data=train_df,
    val_data=val_df,
    target_col="close"
)

# Evaluate
from src.ml.evaluation.metrics import evaluate_forecast
metrics = evaluate_forecast(model, test_df)
print(f"MAE: {metrics['mae']:.4f}, RMSE: {metrics['rmse']:.4f}")

# Save model
model.save("models/tcn_crude_oil_v1.pt")
```

---

### 3.2 BiGRU-Attention

**Best for:** Daily gold forecasting  
**Performance:** MAE 15.188 for gold with 30-day windows

#### Configuration for Gold:

```yaml
# config/ml/bigru_gold.yaml
model:
  name: "bigru_gold_daily"
  hidden_size: 128
  num_layers: 2
  bidirectional: true
  use_attention: true
  attention_heads: 4
  dropout: 0.25

features:
  lookback_window: 30
  prediction_length: 5

training:
  learning_rate: 0.001
  batch_size: 64
  max_epochs: 100
```

#### Training Example:

```python
from src.ml.models.temporal.gru import create_bigru_for_gold

model = create_bigru_for_gold(input_features=15)
history = model.fit(train_df, val_df, target_col="close")

# Get prediction with uncertainty
forecast = model.predict(recent_data, return_uncertainty=True)
print(f"Prediction: {forecast.predictions}")
print(f"95% CI: [{forecast.lower_bound}, {forecast.upper_bound}]")
```

---

### 3.3 FEDformer

**Best for:** Weekly/monthly commodity forecasting  
**Performance:** 38.5% MAE reduction vs LSTM, 56.6% vs GRU

#### Key Innovations:
- Frequency-domain attention (Fourier transform)
- Series decomposition (trend + seasonal)
- O(L log L) complexity vs O(L²) for vanilla attention

#### Configuration for Crude Oil Weekly:

```yaml
# config/ml/fedformer_crude_oil.yaml
model:
  name: "fedformer_crude_oil_weekly"
  d_model: 256
  n_heads: 8
  e_layers: 2
  d_layers: 1
  d_ff: 512
  modes: 32  # Fourier modes to keep
  moving_avg: 25  # Decomposition window
  dropout: 0.1

features:
  lookback_window: 60
  prediction_length: 14  # 2-week forecast

training:
  learning_rate: 0.0001
  batch_size: 32
  max_epochs: 100
```

#### Training Example:

```python
from src.ml.models.transformers.fedformer import create_fedformer_for_crude_oil

# Create model for weekly forecasting
model = create_fedformer_for_crude_oil(input_features=15)

# Use daily data aggregated to capture weekly patterns
history = model.fit(
    train_data=train_df,
    val_data=val_df,
    target_col="close"
)

# 14-day forecast
forecast = model.predict(recent_60_days)
print(f"14-day forecast: {forecast.predictions}")
```

---

### 3.4 Temporal Fusion Transformer (TFT)

**Best for:** Multi-horizon probabilistic forecasting  
**Performance:** R² of 0.94, excellent tail risk estimation

#### Key Features:
- Variable selection (learns feature importance)
- Interpretable attention weights
- Quantile outputs for uncertainty
- Handles static covariates

#### Configuration:

```yaml
# config/ml/tft_gold.yaml
model:
  name: "tft_gold_multihorizon"
  d_model: 160
  n_heads: 4
  dropout: 0.1
  quantiles: [0.1, 0.25, 0.5, 0.75, 0.9]

features:
  lookback_window: 60
  prediction_length: 14
  static_vars: ["asset_class", "market_regime"]
  time_varying_known: ["day_of_week", "month", "is_holiday"]
  time_varying_unknown: ["price", "volume", "volatility"]
```

#### Training Example:

```python
from src.ml.models.transformers.tft import create_tft_for_gold

model = create_tft_for_gold(num_features=15)
history = model.fit(train_df, val_df)

# Get probabilistic forecast
forecast = model.predict(recent_data, return_attention=True)

print(f"Median forecast: {forecast.predictions}")
print(f"10th percentile: {forecast.lower_bound}")
print(f"90th percentile: {forecast.upper_bound}")
print(f"Feature importance: {forecast.feature_importance}")
```

---

### 3.5 Mixture of Experts (MoE)

**Best for:** Regime-adaptive forecasting  
**Performance:** 17-33% error reduction over dense models

#### Key Features:
- Multiple specialized expert networks
- Sparse routing (top-K activation)
- Regime-aware gating
- Efficient compute scaling

#### Configuration for Crude Oil:

```yaml
# config/ml/moe_crude_oil.yaml
model:
  name: "moe_crude_oil"
  num_experts: 8
  top_k: 2  # Activate 2 experts per sample
  expert_hidden_size: 128
  expert_type: "gru"  # "gru", "tcn", "transformer"
  use_shared_expert: true
  router_type: "volatility"  # For regime-based routing
  load_balancing_weight: 0.01

features:
  lookback_window: 30
  prediction_length: 5
```

#### Training Example:

```python
from src.ml.models.ensemble.moe import create_moe_for_crude_oil

model = create_moe_for_crude_oil(input_features=15)
history = model.fit(train_df, val_df)

# Inspect expert routing
forecast = model.predict(recent_data)
print(f"Expert routing: {forecast.feature_importance}")
# Output: {'expert_3': 0.65, 'expert_7': 0.35}
```

---

### 3.6 PPO Trader

**Best for:** End-to-end trading decisions  
**Performance:** Sharpe ratio 2.72 (Trading-R1), 5-52% return improvement

#### Key Features:
- Learns trading policy directly
- Handles transaction costs
- Sharpe ratio-based rewards
- Position sizing

#### Configuration:

```yaml
# config/ml/ppo_crude_oil.yaml
model:
  name: "ppo_crude_oil_trader"
  hidden_size: 256
  num_lstm_layers: 2
  
ppo:
  clip_epsilon: 0.2
  value_loss_coef: 0.5
  entropy_coef: 0.01
  gamma: 0.99
  gae_lambda: 0.95
  ppo_epochs: 10
  rollout_length: 256

trading:
  action_type: "discrete"  # BUY/HOLD/SELL
  max_position: 1.0
  transaction_cost: 0.001
  use_sharpe_reward: true
```

#### Training Example:

```python
from src.ml.models.rl.ppo import create_ppo_for_crude_oil

agent = create_ppo_for_crude_oil(input_features=15)
history = agent.fit(train_df)

print(f"Final Sharpe: {history['sharpe_ratio'][-1]:.2f}")

# Get trading signal
signal = agent.get_trading_signal(recent_data)
print(f"Action: {signal['action']}")
print(f"Position: {signal['position']}")
print(f"Confidence: {signal['confidence']:.2%}")
```

---

## 4. Data Pipeline

### 4.1 Feature Engineering for Commodities

```python
# src/ml/data/preprocessor.py

import pandas as pd
import numpy as np
from typing import Tuple, List

def prepare_commodity_data(
    symbol: str,
    start_date: str,
    end_date: str,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    include_sentiment: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Prepare commodity data with optimal features for forecasting.
    
    Recommended features (research-based):
    - OHLCV
    - Technical indicators: RSI, MACD, ATR, BB
    - Sentiment: OVX, VIX, EPU (Economic Policy Uncertainty)
    - Cross-commodity: DXY (Dollar Index), gold-oil ratio
    """
    from src.database.repositories import MarketDataRepository
    from src.ml.data.features import compute_technical_indicators
    
    # Load data
    repo = MarketDataRepository()
    df = repo.get_market_data(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        timeframe="D1"
    )
    
    # Compute features
    df = compute_technical_indicators(df)
    
    # Add exogenous variables
    if include_sentiment:
        df = add_sentiment_features(df)
        
    # Normalize
    df = normalize_features(df, method="z-score")
    
    # Split chronologically (NO random splitting!)
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))
    
    train_df = df.iloc[:train_end]
    val_df = df.iloc[train_end:val_end]
    test_df = df.iloc[val_end:]
    
    return train_df, val_df, test_df


def compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators optimal for commodity forecasting."""
    import pandas_ta as ta
    
    # RSI (14-day)
    df["rsi_14"] = ta.rsi(df["close"], length=14)
    
    # MACD
    macd = ta.macd(df["close"])
    df["macd"] = macd["MACD_12_26_9"]
    df["macd_signal"] = macd["MACDs_12_26_9"]
    
    # Bollinger Bands
    bb = ta.bbands(df["close"], length=20, std=2)
    df["bb_upper"] = bb["BBU_20_2.0"]
    df["bb_lower"] = bb["BBL_20_2.0"]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["close"]
    
    # ATR
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    
    # Volatility (20-day rolling std of returns)
    df["returns"] = df["close"].pct_change()
    df["volatility"] = df["returns"].rolling(20).std()
    
    # Lag features
    for lag in [1, 5, 10, 20]:
        df[f"return_lag_{lag}"] = df["returns"].shift(lag)
        
    return df.dropna()


def add_sentiment_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add sentiment/macro features for commodities."""
    import yfinance as yf
    
    # DXY (Dollar Index) - significant for oil/gold
    dxy = yf.download("DX-Y.NYB", start=df.index[0], end=df.index[-1])
    df["dxy"] = dxy["Close"].reindex(df.index, method="ffill")
    
    # VIX
    vix = yf.download("^VIX", start=df.index[0], end=df.index[-1])
    df["vix"] = vix["Close"].reindex(df.index, method="ffill")
    
    # OVX (Oil Volatility Index) - for crude oil
    ovx = yf.download("^OVX", start=df.index[0], end=df.index[-1])
    df["ovx"] = ovx["Close"].reindex(df.index, method="ffill")
    
    return df
```

---

## 5. Training Procedures

### 5.1 Walk-Forward Validation (Critical!)

**Warning:** Standard train/test split causes data leakage in financial data. Always use walk-forward validation.

```python
# src/ml/evaluation/backtester.py

from typing import Generator, Tuple
import pandas as pd
import numpy as np

class WalkForwardValidator:
    """
    Walk-forward validation that mimics live trading.
    
    Research: CPCV (Combinatorial Purged Cross-Validation) shows 
    marked superiority in mitigating backtest overfitting.
    """
    
    def __init__(
        self,
        train_window: int = 252,  # 1 year
        test_window: int = 21,     # 1 month
        step_size: int = 21,       # Monthly retraining
        purge_gap: int = 5         # Gap between train/test
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step_size = step_size
        self.purge_gap = purge_gap
        
    def split(
        self, 
        df: pd.DataFrame
    ) -> Generator[Tuple[pd.DataFrame, pd.DataFrame], None, None]:
        """Generate train/test splits for walk-forward validation."""
        n = len(df)
        
        start = 0
        while start + self.train_window + self.purge_gap + self.test_window <= n:
            train_end = start + self.train_window
            test_start = train_end + self.purge_gap
            test_end = test_start + self.test_window
            
            train_df = df.iloc[start:train_end]
            test_df = df.iloc[test_start:test_end]
            
            yield train_df, test_df
            
            start += self.step_size
            
    def evaluate_model(
        self,
        model_class,
        model_kwargs: dict,
        df: pd.DataFrame,
        target_col: str = "close"
    ) -> dict:
        """
        Run walk-forward evaluation.
        
        Returns:
            Aggregated metrics across all folds
        """
        all_predictions = []
        all_actuals = []
        all_metrics = []
        
        for fold, (train_df, test_df) in enumerate(self.split(df)):
            # Create fresh model
            model = model_class(**model_kwargs)
            
            # Train
            model.fit(train_df, target_col=target_col)
            
            # Predict
            for i in range(len(test_df) - model.config.prediction_length):
                input_data = test_df.iloc[
                    i:i + model.config.lookback_window
                ]
                forecast = model.predict(input_data)
                
                actual = test_df[target_col].iloc[
                    i + model.config.lookback_window:
                    i + model.config.lookback_window + model.config.prediction_length
                ].values
                
                all_predictions.append(forecast.predictions)
                all_actuals.append(actual)
                
            # Fold metrics
            fold_metrics = model.evaluate(
                np.concatenate(all_actuals[-len(test_df):]),
                np.concatenate(all_predictions[-len(test_df):])
            )
            fold_metrics["fold"] = fold
            all_metrics.append(fold_metrics)
            
            print(f"Fold {fold}: RMSE={fold_metrics['rmse']:.4f}")
            
        # Aggregate
        return {
            "mean_mae": np.mean([m["mae"] for m in all_metrics]),
            "mean_rmse": np.mean([m["rmse"] for m in all_metrics]),
            "std_rmse": np.std([m["rmse"] for m in all_metrics]),
            "mean_mape": np.mean([m["mape"] for m in all_metrics]),
            "all_folds": all_metrics
        }
```

### 5.2 Unified Training Script

```python
# scripts/train_models.py

import argparse
from pathlib import Path
import yaml
import mlflow

from src.ml.models.temporal.tcn import create_tcn_for_crude_oil, create_tcn_for_gold
from src.ml.models.temporal.gru import create_bigru_for_crude_oil, create_bigru_for_gold
from src.ml.models.transformers.fedformer import create_fedformer_for_crude_oil
from src.ml.models.transformers.tft import create_tft_for_gold
from src.ml.models.ensemble.moe import create_moe_for_crude_oil
from src.ml.models.rl.ppo import create_ppo_for_crude_oil
from src.ml.data.preprocessor import prepare_commodity_data
from src.ml.evaluation.backtester import WalkForwardValidator

MODEL_REGISTRY = {
    "tcn_crude_oil": create_tcn_for_crude_oil,
    "tcn_gold": create_tcn_for_gold,
    "bigru_crude_oil": create_bigru_for_crude_oil,
    "bigru_gold": create_bigru_for_gold,
    "fedformer_crude_oil": create_fedformer_for_crude_oil,
    "tft_gold": create_tft_for_gold,
    "moe_crude_oil": create_moe_for_crude_oil,
    "ppo_crude_oil": create_ppo_for_crude_oil,
}


def train_model(
    model_name: str,
    symbol: str,
    config_path: str,
    output_dir: str
):
    """Train a model and log to MLflow."""
    
    # Load config
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    # Prepare data
    train_df, val_df, test_df = prepare_commodity_data(
        symbol=symbol,
        start_date=config.get("start_date", "2015-01-01"),
        end_date=config.get("end_date", "2024-12-31"),
    )
    
    num_features = len([c for c in train_df.columns if c not in ["close", "symbol", "time"]])
    
    # Create model
    model_factory = MODEL_REGISTRY[model_name]
    model = model_factory(input_features=num_features)
    
    # MLflow tracking
    mlflow.set_experiment(f"risetrader_{symbol.lower()}")
    
    with mlflow.start_run(run_name=model_name):
        # Log config
        mlflow.log_params(config)
        
        # Train
        history = model.fit(train_df, val_df, target_col="close")
        
        # Log metrics
        for metric, values in history.items():
            for i, v in enumerate(values):
                mlflow.log_metric(metric, v, step=i)
                
        # Walk-forward evaluation
        validator = WalkForwardValidator()
        wf_metrics = validator.evaluate_model(
            model_class=model_factory,
            model_kwargs={"input_features": num_features},
            df=pd.concat([train_df, val_df, test_df]),
            target_col="close"
        )
        
        mlflow.log_metrics({
            "wf_mae": wf_metrics["mean_mae"],
            "wf_rmse": wf_metrics["mean_rmse"],
            "wf_mape": wf_metrics["mean_mape"],
        })
        
        # Save model
        output_path = Path(output_dir) / f"{model_name}_{symbol}.pt"
        model.save(output_path)
        mlflow.log_artifact(output_path)
        
        print(f"Model saved to {output_path}")
        print(f"Walk-forward RMSE: {wf_metrics['mean_rmse']:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=list(MODEL_REGISTRY.keys()))
    parser.add_argument("--symbol", required=True, choices=["CRUDE_OIL", "GOLD"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="models/")
    
    args = parser.parse_args()
    train_model(args.model, args.symbol, args.config, args.output)
```

---

## 6. Evaluation & Validation

### 6.1 Metrics

```python
# src/ml/evaluation/metrics.py

import numpy as np
from typing import Dict

def evaluate_forecast(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    prices: np.ndarray = None
) -> Dict[str, float]:
    """
    Calculate standard forecasting metrics.
    
    Returns:
        mae: Mean Absolute Error
        rmse: Root Mean Squared Error
        mape: Mean Absolute Percentage Error
        mpe: Mean Percentage Error (bias)
        directional_accuracy: % correct direction
        r2: R-squared
    """
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-8))) * 100
    mpe = np.mean((y_pred - y_true) / (y_true + 1e-8)) * 100
    
    # R-squared
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - (ss_res / (ss_tot + 1e-8))
    
    metrics = {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "mpe": mpe,
        "r2": r2,
    }
    
    # Directional accuracy
    if prices is not None and len(prices) > 1:
        true_dir = np.sign(np.diff(y_true))
        pred_dir = np.sign(np.diff(y_pred))
        metrics["directional_accuracy"] = np.mean(true_dir == pred_dir) * 100
        
    return metrics


def calculate_trading_metrics(
    returns: np.ndarray,
    benchmark_returns: np.ndarray = None
) -> Dict[str, float]:
    """Calculate trading-specific metrics."""
    
    # Sharpe ratio (annualized)
    sharpe = returns.mean() / (returns.std() + 1e-8) * np.sqrt(252)
    
    # Maximum drawdown
    cumulative = (1 + returns).cumprod()
    rolling_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = drawdown.min()
    
    # Sortino ratio (downside deviation)
    downside = returns[returns < 0]
    sortino = returns.mean() / (downside.std() + 1e-8) * np.sqrt(252)
    
    # Win rate
    win_rate = np.mean(returns > 0) * 100
    
    metrics = {
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "cumulative_return": (1 + returns).prod() - 1,
    }
    
    # Information ratio (if benchmark provided)
    if benchmark_returns is not None:
        excess = returns - benchmark_returns
        info_ratio = excess.mean() / (excess.std() + 1e-8) * np.sqrt(252)
        metrics["information_ratio"] = info_ratio
        
    return metrics
```

---

## 7. Production Deployment

### 7.1 Inference Pipeline

```python
# src/ml/inference/predictor.py

from typing import Dict, List, Optional
from datetime import datetime
import torch

from src.ml.models.base import BaseForecaster, ForecastResult


class CommodityPredictor:
    """
    Production inference pipeline for commodity forecasting.
    Handles model loading, preprocessing, and prediction.
    """
    
    def __init__(
        self,
        model_paths: Dict[str, str],
        device: str = "cuda"
    ):
        """
        Args:
            model_paths: Dict mapping model names to checkpoint paths
                e.g., {"tcn_daily": "models/tcn_crude_oil.pt"}
        """
        self.device = device
        self.models: Dict[str, BaseForecaster] = {}
        
        for name, path in model_paths.items():
            self.models[name] = self._load_model(path)
            
    def _load_model(self, path: str) -> BaseForecaster:
        """Load model from checkpoint."""
        checkpoint = torch.load(path, map_location=self.device)
        
        # Reconstruct model based on config
        config = checkpoint["config"]
        model_type = config.model_name.split("_")[0]
        
        # Import appropriate factory
        if model_type == "tcn":
            from src.ml.models.temporal.tcn import TCN, TCNConfig
            model = TCN(TCNConfig(**vars(config)), input_size=config.input_size)
        elif model_type == "fedformer":
            from src.ml.models.transformers.fedformer import FEDformer, FEDformerConfig
            model = FEDformer(FEDformerConfig(**vars(config)), input_size=config.input_size)
        # ... add other model types
        
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self.device)
        model.eval()
        
        return model
    
    def predict(
        self,
        data: pd.DataFrame,
        model_name: str,
        symbol: str
    ) -> ForecastResult:
        """
        Generate forecast using specified model.
        
        Args:
            data: Recent market data (must include lookback_window rows)
            model_name: Name of model to use
            symbol: Asset symbol
            
        Returns:
            ForecastResult with predictions
        """
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not loaded")
            
        model = self.models[model_name]
        
        return model.predict(data)
    
    def ensemble_predict(
        self,
        data: pd.DataFrame,
        model_names: List[str],
        weights: Optional[List[float]] = None
    ) -> ForecastResult:
        """
        Generate ensemble forecast from multiple models.
        
        Args:
            data: Recent market data
            model_names: List of model names to ensemble
            weights: Optional weights (default: equal)
            
        Returns:
            Weighted average forecast
        """
        if weights is None:
            weights = [1.0 / len(model_names)] * len(model_names)
            
        predictions = []
        for name in model_names:
            forecast = self.predict(data, name, symbol="")
            predictions.append(forecast.predictions)
            
        # Weighted average
        ensemble_pred = np.average(predictions, axis=0, weights=weights)
        
        # Uncertainty from disagreement
        std = np.std(predictions, axis=0)
        
        return ForecastResult(
            timestamp=datetime.now(),
            symbol=data.get("symbol", ["UNKNOWN"])[0] if "symbol" in data.columns else "UNKNOWN",
            model_name="ensemble",
            model_version="weighted_avg",
            predictions=ensemble_pred,
            lower_bound=ensemble_pred - 1.96 * std,
            upper_bound=ensemble_pred + 1.96 * std,
            confidence_scores=1.0 / (1.0 + std),
            inference_time_ms=0.0
        )
```

### 7.2 API Integration

```python
# src/api/routes/forecast.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/forecast", tags=["forecasting"])


class ForecastRequest(BaseModel):
    symbol: str  # "CRUDE_OIL" or "GOLD"
    horizon: str  # "daily", "weekly"
    model: Optional[str] = None  # Specific model or auto-select


class ForecastResponse(BaseModel):
    symbol: str
    model_used: str
    timestamp: datetime
    predictions: List[float]
    lower_bound: Optional[List[float]]
    upper_bound: Optional[List[float]]
    direction_prob: Optional[float]


# Initialize predictor (singleton)
from src.ml.inference.predictor import CommodityPredictor

predictor = CommodityPredictor({
    "tcn_crude_oil": "models/tcn_crude_oil.pt",
    "tcn_gold": "models/tcn_gold.pt",
    "fedformer_crude_oil": "models/fedformer_crude_oil.pt",
    "tft_gold": "models/tft_gold.pt",
})


@router.post("/", response_model=ForecastResponse)
async def generate_forecast(request: ForecastRequest):
    """Generate price forecast for commodity."""
    
    # Auto-select model based on horizon if not specified
    if request.model is None:
        if request.horizon == "daily":
            model_name = f"tcn_{request.symbol.lower()}"
        else:
            model_name = f"fedformer_{request.symbol.lower()}"
    else:
        model_name = request.model
        
    # Get recent data
    from src.database.repositories import MarketDataRepository
    repo = MarketDataRepository()
    
    recent_data = repo.get_recent_data(
        symbol=request.symbol,
        n_days=60  # Max lookback
    )
    
    if len(recent_data) < 30:
        raise HTTPException(400, "Insufficient data for forecast")
        
    # Generate forecast
    forecast = predictor.predict(recent_data, model_name, request.symbol)
    
    return ForecastResponse(
        symbol=request.symbol,
        model_used=model_name,
        timestamp=forecast.timestamp,
        predictions=forecast.predictions.tolist(),
        lower_bound=forecast.lower_bound.tolist() if forecast.lower_bound is not None else None,
        upper_bound=forecast.upper_bound.tolist() if forecast.upper_bound is not None else None,
        direction_prob=forecast.direction_prob
    )
```

---

## 8. Asset-Specific Configurations

### 8.1 Crude Oil Optimal Setup

Based on research, the optimal setup for crude oil:

| Horizon | Model | Config |
|---------|-------|--------|
| Daily | TCN | lookback=30, kernel=3, channels=[64,128,256,128] |
| Weekly | FEDformer | lookback=60, modes=32, d_model=256 |
| Trading | MoE + PPO | 8 experts, volatility routing, Sharpe reward |

**Key features to include:**
- OHLCV
- DXY (Dollar Index) - highest impact
- OVX (Oil Volatility Index)
- VIX
- RSI, MACD, ATR
- Cross-commodity: Gold, Natural Gas

### 8.2 Gold Optimal Setup

| Horizon | Model | Config |
|---------|-------|--------|
| Daily | BiGRU-Attention | lookback=30, hidden=128, attention_heads=4 |
| Weekly | TFT | lookback=60, quantiles=[0.1,0.5,0.9] |
| Monthly | FEDformer | lookback=60, modes=32 |

**Key features to include:**
- OHLCV
- DXY (Dollar Index) - inverse correlation
- VIX - safe haven effect
- Real interest rates
- RSI, MACD, BB
- Gold/Silver ratio

---

## Quick Start Commands

```bash
# Train TCN for crude oil daily
python scripts/train_models.py \
    --model tcn_crude_oil \
    --symbol CRUDE_OIL \
    --config config/ml/tcn_crude_oil.yaml \
    --output models/

# Train FEDformer for crude oil weekly
python scripts/train_models.py \
    --model fedformer_crude_oil \
    --symbol CRUDE_OIL \
    --config config/ml/fedformer_crude_oil.yaml \
    --output models/

# Train TFT for gold
python scripts/train_models.py \
    --model tft_gold \
    --symbol GOLD \
    --config config/ml/tft_gold.yaml \
    --output models/

# Train PPO trader
python scripts/train_models.py \
    --model ppo_crude_oil \
    --symbol CRUDE_OIL \
    --config config/ml/ppo_crude_oil.yaml \
    --output models/
```

---

## Next Steps

1. **Copy model files** to your `src/ml/models/` directory
2. **Update requirements.txt** with new dependencies
3. **Create config files** in `config/ml/`
4. **Run training** with walk-forward validation
5. **Integrate with API** for production inference
6. **Monitor performance** via MLflow dashboard

For questions or issues, check the model docstrings or refer to the research paper citations in the accompanying research report.
