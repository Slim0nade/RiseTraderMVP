"""
Test & Demo Script for ZigZag Reversal Classifier

Demonstrates the complete pipeline:
1. Label data with ZigZag
2. Extract features
3. Train classifier
4. Make predictions
5. Test API endpoints

Usage:
    python scripts/test_reversal_classifier.py --full
    python scripts/test_reversal_classifier.py --quick  # Skip training
"""
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.config import initialize_database, get_database
from src.ml.labeling.zigzag_label_service import ZigZagLabelService
from src.ml.features.reversal_features import ReversalFeatureExtractor
from src.ml.training.train_reversal_classifier import ReversalClassifierTrainer
from src.ml.inference.reversal_predictor import ReversalPredictor


def print_section(title: str):
    """Print formatted section header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


async def test_labeling(symbol: str = 'CrudeOIL', timeframe: str = 'H1'):
    """Test Step 1: Label data with ZigZag."""
    print_section("STEP 1: ZigZag Labeling")

    db = get_database()

    async with db.get_session() as session:
        service = ZigZagLabelService(session)

        print(f"Labeling {symbol} {timeframe} data...")
        stats = await service.label_symbol(symbol, timeframe)

        print(f"\n✅ Labeling Complete:")
        print(f"   Total candles:    {stats.get('total_candles', 0):,}")
        print(f"   Peaks:            {stats.get('peaks', 0):,} ({stats.get('peak_pct', 0)}%)")
        print(f"   Valleys:          {stats.get('valleys', 0):,} ({stats.get('valley_pct', 0)}%)")
        print(f"   Neither:          {stats.get('neither', 0):,}")
        print(f"   Avg bars between: {stats.get('avg_bars_between_reversals', 0)}")
        print(f"   DB rows updated:  {stats.get('updated_rows', 0):,}")

        return stats


async def test_feature_extraction(
    symbol: str = 'CrudeOIL',
    timeframe: str = 'H1'
):
    """Test Step 2: Extract features."""
    print_section("STEP 2: Feature Extraction")

    db = get_database()

    async with db.get_session() as session:
        extractor = ReversalFeatureExtractor(session)

        # Use last 6 months of data for quick test
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=180)

        print(f"Extracting features for {symbol} {timeframe}")
        print(f"Date range: {start_date.date()} to {end_date.date()}")

        X, y, feature_names = await extractor.extract_training_data(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date
        )

        print(f"\n✅ Feature Extraction Complete:")
        print(f"   Samples:          {len(X):,}")
        print(f"   Features:         {len(feature_names)}")
        print(f"   Class distribution:")
        print(f"     Valleys (-1):   {(y == -1).sum():,}")
        print(f"     Neither (0):    {(y == 0).sum():,}")
        print(f"     Peaks (1):      {(y == 1).sum():,}")

        print(f"\n   Top 10 features:")
        for i, name in enumerate(feature_names[:10], 1):
            print(f"     {i}. {name}")

        return X, y, feature_names


async def test_training(
    symbol: str = 'CrudeOIL',
    timeframe: str = 'H1',
    quick: bool = False
):
    """Test Step 3: Train classifier."""
    print_section("STEP 3: Model Training")

    db = get_database()

    # Use smaller dataset for quick test
    if quick:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=180)  # 6 months
        n_splits = 3
        print("⚡ Quick mode: Using 6 months of data with 3 splits")
    else:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=730)  # 2 years
        n_splits = 5
        print("🔥 Full mode: Using 2 years of data with 5 splits")

    async with db.get_session() as session:
        trainer = ReversalClassifierTrainer(session)

        print(f"Training {symbol} {timeframe} classifier...")
        print(f"Date range: {start_date.date()} to {end_date.date()}")

        result = await trainer.train(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            model_type='xgboost',
            use_smote=True,
            walk_forward=True,
            n_splits=n_splits,
            run_name=f"test_run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        )

        print(f"\n✅ Training Complete:")
        print(f"   Run ID:           {result['run_id']}")
        print(f"   MLflow Run ID:    {result.get('mlflow_run_id', 'N/A')}")
        print(f"   Best Fold:        {result.get('best_fold', 'N/A') + 1}")

        metrics = result['metrics']
        print(f"\n   Metrics (mean ± std across folds):")
        print(f"     Peak Precision:    {metrics.get('peak_precision_mean', 0):.3f} ± {metrics.get('peak_precision_std', 0):.3f}")
        print(f"     Peak Recall:       {metrics.get('peak_recall_mean', 0):.3f} ± {metrics.get('peak_recall_std', 0):.3f}")
        print(f"     Peak F1:           {metrics.get('peak_f1_mean', 0):.3f} ± {metrics.get('peak_f1_std', 0):.3f}")
        print(f"     Valley Precision:  {metrics.get('valley_precision_mean', 0):.3f} ± {metrics.get('valley_precision_std', 0):.3f}")
        print(f"     Valley Recall:     {metrics.get('valley_recall_mean', 0):.3f} ± {metrics.get('valley_recall_std', 0):.3f}")
        print(f"     Valley F1:         {metrics.get('valley_f1_mean', 0):.3f} ± {metrics.get('valley_f1_std', 0):.3f}")
        print(f"     Reversal F1:       {metrics.get('reversal_f1_mean', 0):.3f} ± {metrics.get('reversal_f1_std', 0):.3f}")

        return result


async def test_inference(
    symbol: str = 'CrudeOIL',
    timeframe: str = 'H1',
    model_path: str = None
):
    """Test Step 4: Make predictions."""
    print_section("STEP 4: Real-Time Inference")

    db = get_database()

    async with db.get_session() as session:
        # For testing, load from local path or MLflow
        if model_path:
            predictor = ReversalPredictor(session, model_path=Path(model_path))
        else:
            # This would normally load from MLflow
            print("⚠️  Skipping inference test (requires trained model in MLflow)")
            print("   Train a model first, then run:")
            print("   python scripts/test_reversal_classifier.py --inference-only")
            return

        print(f"Making prediction for {symbol} {timeframe}...")

        # Current prediction
        result = await predictor.predict(
            symbol=symbol,
            timeframe=timeframe,
            current_time=datetime.utcnow()
        )

        print(f"\n✅ Prediction Complete:")
        print(f"   Timestamp:        {result['timestamp']}")
        print(f"   Signal:           {result['signal']}")
        print(f"   Confidence:       {result['confidence']:.2%}")
        print(f"   Peak Prob:        {result['peak_prob']:.2%}")
        print(f"   Valley Prob:      {result['valley_prob']:.2%}")
        print(f"   Neutral Prob:     {result['neutral_prob']:.2%}")

        # Interpretation
        if result['signal'] == 'SHORT':
            print(f"\n   📉 SHORT signal - High probability peak detected")
        elif result['signal'] == 'LONG':
            print(f"\n   📈 LONG signal - High probability valley detected")
        else:
            print(f"\n   ⏸️  WAIT - No clear reversal signal")

        return result


async def test_api_endpoints():
    """Test Step 5: Test API endpoints."""
    print_section("STEP 5: API Endpoint Testing")

    try:
        import httpx

        print("Testing API endpoints (requires running server)...")
        print("Start server with: docker-compose up api")

        client = httpx.Client(base_url='http://localhost:8003', timeout=30.0)

        # Test health
        print("\n1. Testing health endpoint...")
        response = client.get('/api/v1/reversals/health')
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")

        # Test prediction
        print("\n2. Testing prediction endpoint...")
        response = client.post('/api/v1/reversals/predict', json={
            'symbol': 'CrudeOIL',
            'timeframe': 'H1',
            'model_version': 'latest'
        })
        if response.status_code == 200:
            result = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Signal: {result['signal']}")
            print(f"   Confidence: {result['confidence']:.2%}")
        else:
            print(f"   Status: {response.status_code}")
            print(f"   Error: {response.text}")

        # Test model info
        print("\n3. Testing model info endpoint...")
        response = client.get('/api/v1/reversals/model/info?model_version=latest')
        if response.status_code == 200:
            info = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Model Type: {info['model_type']}")
            print(f"   Features: {info['feature_count']}")
        else:
            print(f"   Status: {response.status_code}")
            print(f"   Error: {response.text}")

        print("\n✅ API tests complete")

    except ImportError:
        print("⚠️  httpx not installed. Skipping API tests.")
        print("   Install with: pip install httpx")
    except Exception as e:
        print(f"⚠️  API tests failed: {str(e)}")
        print("   Make sure the API server is running: docker-compose up api")


async def run_full_pipeline(symbol: str, timeframe: str, quick: bool):
    """Run the complete pipeline."""
    print_section("ZigZag Reversal Classifier - Full Pipeline Test")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Mode: {'Quick' if quick else 'Full'}")

    start_time = datetime.utcnow()

    # Initialize database
    initialize_database()

    # Step 1: Label data
    await test_labeling(symbol, timeframe)

    # Step 2: Extract features
    await test_feature_extraction(symbol, timeframe)

    # Step 3: Train model
    await test_training(symbol, timeframe, quick=quick)

    # Step 4: Test inference (optional if model saved locally)
    # await test_inference(symbol, timeframe)

    # Step 5: Test API
    await test_api_endpoints()

    # Summary
    duration = (datetime.utcnow() - start_time).total_seconds()
    print_section("Pipeline Test Complete")
    print(f"✅ All steps completed successfully")
    print(f"⏱️  Total time: {duration:.1f} seconds")
    print(f"\n📖 Next steps:")
    print(f"   1. Check MLflow UI: http://localhost:5000")
    print(f"   2. Test API: http://localhost:8003/docs")
    print(f"   3. Read full guide: docs/ZIGZAG_REVERSAL_CLASSIFIER.md")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test ZigZag Reversal Classifier Pipeline"
    )
    parser.add_argument(
        '--symbol',
        default='CrudeOIL',
        help='Trading symbol (default: CrudeOIL)'
    )
    parser.add_argument(
        '--timeframe',
        default='H1',
        help='Candle timeframe (default: H1)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Run full pipeline (label + train + test)'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick test (smaller dataset, fewer splits)'
    )
    parser.add_argument(
        '--label-only',
        action='store_true',
        help='Only label data'
    )
    parser.add_argument(
        '--train-only',
        action='store_true',
        help='Only train model'
    )
    parser.add_argument(
        '--api-only',
        action='store_true',
        help='Only test API endpoints'
    )

    args = parser.parse_args()

    # Initialize database
    initialize_database()

    if args.full or args.quick:
        asyncio.run(run_full_pipeline(args.symbol, args.timeframe, args.quick))
    elif args.label_only:
        asyncio.run(test_labeling(args.symbol, args.timeframe))
    elif args.train_only:
        asyncio.run(test_training(args.symbol, args.timeframe, quick=args.quick))
    elif args.api_only:
        asyncio.run(test_api_endpoints())
    else:
        print("Usage:")
        print("  python scripts/test_reversal_classifier.py --full    # Full pipeline")
        print("  python scripts/test_reversal_classifier.py --quick   # Quick test")
        print("  python scripts/test_reversal_classifier.py --label-only")
        print("  python scripts/test_reversal_classifier.py --train-only")
        print("  python scripts/test_reversal_classifier.py --api-only")
        print("\nOr run individual steps interactively:")
        print("  python scripts/test_reversal_classifier.py")


if __name__ == '__main__':
    main()
