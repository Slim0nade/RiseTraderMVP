# SOTA Models Integration Plan
**Feature**: 003-ml-forecasting-pipeline  
**Date**: 2025-11-29  
**Type**: Integration (Parallel Development Merge)

---

## Problem Statement

Two parallel implementations of the ML forecasting system exist:

### Implementation A: MVP (Completed)
- **Files**: `src/ml/models/base_model.py`, `lstm_forecaster.py`, `xgboost_forecaster.py`
- **Approach**: Simple abstract base class
- **Models**: LSTM (PyTorch), XGBoost
- **Interface**: `train()`, `predict()`, `save()`, `load()`
- **Status**: ✅ Integrated with API, services, repositories

### Implementation B: SOTA Models (Parallel)
- **Files**: `src/ml/models/base.py`, `IMPLEMENTATION_GUIDE.md`
- **Approach**: Sophisticated with enums, dataclasses, factory methods
- **Models**: TCN, BiGRU, FEDformer, TFT, MoE, PPO
- **Directories**: `transformers/`, `temporal/`, `ensemble/`, `rl/`, `decomposition/`
- **Interface**: `BaseForecaster(nn.Module)`, `ForecastResult`, `ModelConfig`
- **Status**: ⏳ Not integrated with existing infrastructure

---

## Analysis

### Key Differences

| Aspect | MVP Implementation | SOTA Implementation |
|--------|-------------------|---------------------|
| **Base Class** | `BaseModel` (ABC) | `BaseForecaster(ABC, nn.Module)` |
| **Config** | Dict-based | `ModelConfig` dataclass |
| **Output** | `np.ndarray` | `ForecastResult` dataclass |
| **Asset Types** | Generic | `AssetType` enum (crude_oil, gold, forex) |
| **Horizons** | Generic | `ForecastHorizon` enum (intraday, daily, weekly, monthly) |
| **Evaluation** | Separate metrics module | Built-in `evaluate()` method |
| **Save/Load** | Simple pickle/torch | PyTorch checkpoints with metadata |
| **Ensemble** | Not supported | `EnsembleForecaster` base class |

### Compatibility Issues

1. **API Layer**: Expects simple dict/array responses, SOTA uses `ForecastResult`
2. **Service Layer**: `MLTrainingService` uses MVP interface
3. **Repository**: `ForecastRepository` saves to database format matching MVP
4. **Inference**: `ModelPredictor` loads MVP models only

---

## Integration Strategy

### ✅ Recommended Approach: Adapter Pattern with Gradual Migration

**Phase 1: Coexistence** (Week 1)
- Keep both base classes
- Create adapters for interoperability
- No breaking changes to existing code

**Phase 2: Selective Adoption** (Week 2-3)
- Add SOTA models alongside MVP models
- Unified API that supports both interfaces
- A/B testing in production

**Phase 3: Migration** (Week 4+)
- Deprecate MVP base class
- Migrate LSTM/XGBoost to new interface
- Standardize on SOTA architecture

---

## Implementation Tasks

### Phase 1: Adapter Layer (3-5 days)

#### T001: Create Base Class Adapter
**File**: `src/ml/models/adapters.py`

```python
"""Adapters to bridge MVP and SOTA implementations."""

from typing import Dict, Any
import numpy as np
from datetime import datetime

from src.ml.models.base_model import BaseModel  # MVP
from src.ml.models.base import BaseForecaster, ForecastResult, ModelConfig  # SOTA


class SOTAtoMVPAdapter:
    """Wraps SOTA BaseForecaster to look like MVP BaseModel."""
    
    def __init__(self, sota_model: BaseForecaster):
        self.model = sota_model
        self.is_trained = False
    
    def train(self, X: np.ndarray, y: np.ndarray, X_val=None, y_val=None, **kwargs) -> Dict[str, Any]:
        """Convert MVP train() call to SOTA fit()."""
        import pandas as pd
        
        # Convert arrays to DataFrame (SOTA expects this)
        train_df = self._arrays_to_dataframe(X, y)
        val_df = self._arrays_to_dataframe(X_val, y_val) if X_val is not None else None
        
        history = self.model.fit(train_df, val_df, **kwargs)
        self.is_trained = True
        
        # Convert SOTA history format to MVP format
        return {
            'train_loss': history.get('train_loss', [0.0])[-1],
            'val_loss': history.get('val_loss', [0.0])[-1] if val_df else None
        }
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Convert MVP predict() call to SOTA predict()."""
        df = self._arrays_to_dataframe(X, None)
        result: ForecastResult = self.model.predict(df, return_uncertainty=False)
        return result.predictions
    
    def save(self, filepath: str) -> bool:
        self.model.save(filepath)
        return True
    
    def load(self, filepath: str) -> bool:
        self.model.load(filepath)
        self.is_trained = True
        return True
    
    @staticmethod
    def _arrays_to_dataframe(X: np.ndarray, y: np.ndarray = None) -> pd.DataFrame:
        """Convert numpy arrays to DataFrame expected by SOTA models."""
        import pandas as pd
        
        # Create DataFrame with feature columns
        feature_cols = [f"feature_{i}" for i in range(X.shape[-1])]
        
        if X.ndim == 3:  # (batch, seq, features) for LSTM
            # Flatten to (samples, features) for simplicity
            X_flat = X.reshape(-1, X.shape[-1])
        else:
            X_flat = X
        
        df = pd.DataFrame(X_flat, columns=feature_cols)
        
        if y is not None:
            df['close'] = y.flatten() if y.ndim > 1 else y
        
        return df


class MVPtoSOTAAdapter(BaseForecaster):
    """Wraps MVP BaseModel to look like SOTA BaseForecaster."""
    
    def __init__(self, mvp_model: BaseModel, config: ModelConfig):
        super().__init__(config)
        self.mvp_model = mvp_model
    
    def forward(self, x):
        """Not used for MVP models."""
        raise NotImplementedError("MVP models don't use forward()")
    
    def fit(self, train_data, val_data=None, **kwargs):
        """Convert SOTA fit() to MVP train()."""
        X_train, y_train = self._dataframe_to_arrays(train_data)
        X_val, y_val = self._dataframe_to_arrays(val_data) if val_data is not None else (None, None)
        
        metrics = self.mvp_model.train(X_train, y_train, X_val, y_val, **kwargs)
        self._is_fitted = True
        
        # Convert to SOTA history format
        return {
            'train_loss': [metrics.get('train_loss', 0.0)],
            'val_loss': [metrics.get('val_loss', 0.0)] if val_data else []
        }
    
    def predict(self, data, return_uncertainty=True):
        """Convert SOTA predict() to MVP predict()."""
        X, _ = self._dataframe_to_arrays(data)
        predictions = self.mvp_model.predict(X)
        
        return ForecastResult(
            timestamp=datetime.utcnow(),
            symbol=data.get('symbol', ['UNKNOWN'])[0] if 'symbol' in data.columns else 'UNKNOWN',
            model_name=self.config.model_name,
            model_version=self.model_version,
            predictions=predictions,
            lower_bound=None,  # MVP doesn't provide uncertainty
            upper_bound=None,
            confidence_scores=None,
            inference_time_ms=0.0
        )
    
    @staticmethod
    def _dataframe_to_arrays(df):
        """Convert DataFrame to numpy arrays for MVP models."""
        feature_cols = [c for c in df.columns if c not in ['close', 'symbol', 'timestamp']]
        X = df[feature_cols].values
        y = df['close'].values if 'close' in df.columns else None
        return X, y
```

#### T002: Update Model Registry
**File**: `src/ml/models/__init__.py`

```python
"""Unified model registry supporting both MVP and SOTA models."""

from enum import Enum
from typing import Union

from .base_model import BaseModel  # MVP
from .base import BaseForecaster  # SOTA
from .adapters import SOTAtoMVPAdapter, MVPtoSOTAAdapter


class ModelType(str, Enum):
    # MVP Models
    LSTM = "lstm"
    XGBOOST = "xgboost"
    
    # SOTA Models
    TCN = "tcn"
    BIGRU = "bigru"
    FEDFORMER = "fedformer"
    TFT = "tft"
    MOE = "moe"
    PPO = "ppo"


def create_model(model_type: ModelType, **kwargs) -> Union[BaseModel, BaseForecaster]:
    """Factory to create any model type."""
    
    if model_type == ModelType.LSTM:
        from .lstm_forecaster import LSTMForecaster
        return LSTMForecaster(**kwargs)
    
    elif model_type == ModelType.XGBOOST:
        from .xgboost_forecaster import XGBoostForecaster
        return XGBoostForecaster(**kwargs)
    
    elif model_type == ModelType.TCN:
        from .temporal.tcn import create_tcn_for_crude_oil
        return create_tcn_for_crude_oil(**kwargs)
    
    elif model_type == ModelType.BIGRU:
        from .temporal.gru import create_bigru_for_gold
        return create_bigru_for_gold(**kwargs)
    
    elif model_type == ModelType.FEDFORMER:
        from .transformers.fedformer import create_fedformer_for_crude_oil
        return create_fedformer_for_crude_oil(**kwargs)
    
    elif model_type == ModelType.TFT:
        from .transformers.tft import create_tft_for_gold
        return create_tft_for_gold(**kwargs)
    
    elif model_type == ModelType.MOE:
        from .ensemble.moe import create_moe_for_crude_oil
        return create_moe_for_crude_oil(**kwargs)
    
    elif model_type == ModelType.PPO:
        from .rl.ppo import create_ppo_for_crude_oil
        return create_ppo_for_crude_oil(**kwargs)
    
    else:
        raise ValueError(f"Unknown model type: {model_type}")
```

#### T003: Extend API Models
**File**: `src/api/models/ml_models.py` (update)

```python
# Add new forecast response fields for SOTA models

class ForecastResponse(BaseModel):
    """Individual forecast response (enhanced for SOTA)."""
    id: int
    symbol: str
    timestamp: datetime
    forecast_horizon: str
    model_type: str
    model_version: str
    predicted_value: float
    
    # Enhanced fields for SOTA models
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    confidence_score: Optional[float]
    direction_prob: Optional[float] = None  # NEW: Direction probability
    feature_importance: Optional[Dict[str, float]] = None  # NEW: Feature importance
    
    created_at: datetime
    inference_time_ms: Optional[float]
    
    class Config:
        from_attributes = True
```

#### T004: Update Service Layer
**File**: `src/services/ml_training_service.py` (update)

```python
# Add support for SOTA models in training service

from src.ml.models import ModelType, create_model
from src.ml.models.adapters import SOTAtoMVPAdapter

async def train_model(
    self,
    symbol: str,
    model_type: str,
    config: Dict[str, Any],
    run_name: str
) -> Dict[str, Any]:
    """Train model (supports both MVP and SOTA models)."""
    
    # ... existing code ...
    
    # Create model using unified factory
    model_enum = ModelType(model_type)
    model = create_model(model_enum, **config.get('model', {}))
    
    # If SOTA model, wrap with adapter for compatibility
    from src.ml.models.base import BaseForecaster
    if isinstance(model, BaseForecaster):
        model = SOTAtoMVPAdapter(model)
    
    # Rest of training logic works with either interface
    trainer = ModelTrainer(model, config)
    # ...
```

---

### Phase 2: SOTA Model Integration (1-2 weeks)

#### T005-T010: Copy SOTA Model Implementations
- Copy `transformers/`, `temporal/`, `ensemble/`, `rl/`, `decomposition/` directories
- Ensure all imports work correctly
- Update `__init__.py` files

#### T011: Create SOTA-specific Configs
**Files**: `config/ml/tcn_config.yaml`, `fedformer_config.yaml`, etc.

#### T012: Update Requirements
**File**: `requirements.txt`

Add SOTA dependencies:
```txt
pytorch-forecasting>=1.0.0
neuralforecast>=1.6.0
stable-baselines3>=2.1.0
gymnasium>=0.29.0
PyWavelets>=1.4.0
EMD-signal>=1.4.0
einops>=0.7.0
rotary-embedding-torch>=0.3.0
```

#### T013: Create Training Scripts
**File**: `scripts/train_sota_models.py`

#### T014: Update Inference Service
**File**: `src/ml/inference/predictor.py`

Support loading SOTA models alongside MVP models.

#### T015: A/B Testing Framework
**File**: `src/services/ml_ab_testing_service.py`

Enable comparing MVP vs SOTA models in production.

---

### Phase 3: Migration & Cleanup (Optional, Week 4+)

#### T016: Refactor LSTM to SOTA Interface
#### T017: Refactor XGBoost to SOTA Interface  
#### T018: Deprecate `base_model.py`
#### T019: Update all tests
#### T020: Documentation update

---

## Decision Points

### Question 1: Which base class should be primary?

**Option A: Keep MVP base (`base_model.py`)**
- ✅ No breaking changes
- ✅ Simpler interface
- ❌ Less feature-rich
- ❌ Doesn't support advanced models well

**Option B: Migrate to SOTA base (`base.py`)** ⭐ RECOMMENDED
- ✅ More comprehensive
- ✅ Better for advanced models (TCN, FEDformer, TFT)
- ✅ Built-in evaluation, configs, ensembles
- ❌ Requires refactoring
- ❌ Breaking changes

**Recommendation**: Option B with Phase 1 adapters for backward compatibility.

---

## Testing Strategy

1. **Unit Tests**: Test adapters thoroughly
2. **Integration Tests**: Test SOTA models with existing API/services
3. **A/B Tests**: Compare LSTM vs TCN, XGBoost vs FEDformer
4. **Performance Tests**: Ensure <50ms p95 latency maintained

---

## Rollout Plan

### Week 1: Adapters & Coexistence
- Implement adapter layer
- No changes to existing MVP code
- SOTA models available but optional

### Week 2: SOTA Model Deployment
- Deploy TCN for crude oil daily forecasts
- Deploy FEDformer for weekly forecasts
- A/B test against LSTM/XGBoost

### Week 3: Performance Validation
- Monitor accuracy metrics
- Compare inference latency
- Evaluate model quality

### Week 4+: Migration (if SOTA proves superior)
- Gradually migrate traffic to SOTA models
- Deprecate MVP models if not needed
- Complete refactoring

---

## Success Criteria

✅ Both model types coexist without conflicts  
✅ Existing API functionality preserved  
✅ SOTA models achieve better accuracy (target: 15-30% improvement)  
✅ Inference latency <50ms p95 maintained  
✅ No production incidents during integration  

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking API changes | HIGH | Use adapter pattern, phased rollout |
| Performance degradation | HIGH | Benchmark before deployment, A/B test |
| Dependency conflicts | MEDIUM | Virtual env, Docker isolation |
| Complexity increase | MEDIUM | Clear documentation, training |

---

## Next Steps

1. **Review this plan** with team
2. **Approve integration strategy**
3. **Begin Phase 1 implementation** (adapters)
4. **Set up A/B testing infrastructure**
5. **Create migration timeline**

