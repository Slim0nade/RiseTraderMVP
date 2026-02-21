# ZigZag ML Labeling Implementation

**Date:** 2026-01-14
**Status:** Ready for deployment

## Purpose
Use ZigZag indicator to label historical candles with peak/valley markers
for training ML models to predict reversals in real-time.

## Key Insight
ZigZag repaints, so it can't be used for real-time signals. BUT it's perfect
for creating training labels because in hindsight it's 100% accurate. We train
a model to recognize the PATTERNS that precede peaks/valleys.

## Files Created

### Database
- `src/database/migrations/versions/012_add_zigzag_label.py` - Migration
- `src/database/models/indicators.py` - Added zigzag_label column

### ML Labeling
- `src/ml/labeling/__init__.py` - Module init
- `src/ml/labeling/zigzag_labeler.py` - Core ZigZag algorithm (ported from MQL4)
- `src/ml/labeling/zigzag_label_service.py` - Database service

### Scripts
- `scripts/test_zigzag_labeler.py` - Test script

## Label Values
- `1` = PEAK (short/sell signal)
- `0` = NEITHER (no trade)
- `-1` = VALLEY (long/buy signal)

## ZigZag Parameters (MT4 defaults)
- depth: 12 (minimum bars between swings)
- deviation: 5 (minimum price deviation in points)
- backstep: 3 (bars to look back for confirmation)

## Usage

### Run Migration
```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP
alembic upgrade head
```

### Test Labeler
```bash
python scripts/test_zigzag_labeler.py
```

### Label Database
```bash
python -m src.ml.labeling.zigzag_label_service CrudeOIL H1
```

### Programmatic Usage
```python
from src.ml.labeling import ZigZagLabelService

async with db.get_session() as session:
    service = ZigZagLabelService(session)
    stats = await service.label_symbol('CrudeOIL', 'H1')
```

## Implementation Complete ✅

**Status:** Full pipeline implemented and ready for use

### Files Created

**ML Pipeline:**
- `src/ml/features/reversal_features.py` - Feature extractor (~50+ features)
- `src/ml/training/train_reversal_classifier.py` - Training pipeline with walk-forward validation
- `src/ml/inference/reversal_predictor.py` - Real-time inference service

**API:**
- `src/api/routes/reversals.py` - REST API endpoints for predictions
- Registered in `src/api/main.py`

**Documentation:**
- `docs/ZIGZAG_REVERSAL_CLASSIFIER.md` - Complete usage guide
- `scripts/test_reversal_classifier.py` - Test/demo script

### Next Steps
1. ✅ Run migration: `alembic upgrade head`
2. ✅ Label data: `python -m src.ml.labeling.zigzag_label_service CrudeOIL H1`
3. ✅ Train model: `python -m src.ml.training.train_reversal_classifier CrudeOIL H1`
4. ✅ Start API: `docker-compose up api`
5. 🔄 Test: `python scripts/test_reversal_classifier.py --quick`
6. 🔄 Use in trading: `POST /api/v1/reversals/predict`

### Features Implemented
- 50+ reversal-specific features (RSI divergence, volume climax, candle patterns, temporal)
- Walk-forward validation for time-series
- SMOTE for class imbalance handling
- MLflow integration for model tracking
- Configurable probability thresholds
- Batch prediction support
- Model reloading without downtime

## Expected Class Distribution
- Peaks: ~3-5% of candles
- Valleys: ~3-5% of candles  
- Neither: ~90-94% of candles
- Avg bars between reversals: ~15-20

## ML Architecture Options
1. XGBoost Classifier (fast, interpretable)
2. LSTM Classifier (sequence-aware, uses existing infra)
3. Ensemble (both)
