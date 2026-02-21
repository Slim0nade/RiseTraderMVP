#!/usr/bin/env python3
"""
Test ZigZag Labeler

Quick test to verify the ZigZag labeler works correctly
before running it against the database.

Usage:
    python scripts/test_zigzag_labeler.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from src.ml.labeling import ZigZagLabeler, ZigZagConfig


def create_sample_data() -> pd.DataFrame:
    """Create sample OHLC data with clear swings."""
    
    # Simulate a price series with clear peaks and valleys
    np.random.seed(42)
    
    n = 200
    base_price = 60.0
    
    # Create a trending/swinging price pattern
    trend = np.zeros(n)
    
    # Up-down-up-down pattern
    for i in range(n):
        if i < 30:
            trend[i] = base_price + i * 0.1  # Up
        elif i < 60:
            trend[i] = base_price + 3 - (i - 30) * 0.15  # Down
        elif i < 100:
            trend[i] = base_price - 1.5 + (i - 60) * 0.12  # Up
        elif i < 140:
            trend[i] = base_price + 3.3 - (i - 100) * 0.1  # Down
        else:
            trend[i] = base_price - 0.7 + (i - 140) * 0.08  # Up
    
    # Add some noise
    noise = np.random.randn(n) * 0.1
    close = trend + noise
    
    # Generate OHLC from close
    data = {
        'time': pd.date_range('2026-01-01', periods=n, freq='h'),
        'open': close - np.random.rand(n) * 0.2,
        'high': close + np.random.rand(n) * 0.3,
        'low': close - np.random.rand(n) * 0.3,
        'close': close,
        'volume': np.random.randint(100, 1000, n)
    }
    
    return pd.DataFrame(data)


def test_labeler():
    """Test the ZigZag labeler."""
    
    print("="*60)
    print("ZigZag Labeler Test")
    print("="*60)
    
    # Create sample data
    df = create_sample_data()
    print(f"\nCreated sample data with {len(df)} candles")
    print(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    
    # Apply labeler
    config = ZigZagConfig(depth=12, deviation=5, backstep=3, point=0.01)
    labeler = ZigZagLabeler(config)
    
    labeled_df = labeler.label_dataframe(df)
    
    # Get statistics
    stats = labeler.get_statistics(labeled_df)
    
    print(f"\n--- Labeling Results ---")
    print(f"Total candles:     {stats['total_candles']}")
    print(f"Peaks:             {stats['peaks']} ({stats['peak_pct']}%)")
    print(f"Valleys:           {stats['valleys']} ({stats['valley_pct']}%)")
    print(f"Neither:           {stats['neither']}")
    print(f"Reversal %:        {stats['reversal_pct']}%")
    print(f"Avg bars between:  {stats['avg_bars_between_reversals']}")
    
    # Show reversals
    reversals = labeler.get_reversals(labeled_df)
    print(f"\n--- Reversal Points ({len(reversals)}) ---")
    
    for _, row in reversals.head(10).iterrows():
        label_type = "PEAK" if row['zigzag_label'] == 1 else "VALLEY"
        print(f"  {row['time']}: {label_type} @ ${row['close']:.2f}")
    
    if len(reversals) > 10:
        print(f"  ... and {len(reversals) - 10} more")
    
    # Verify alternating pattern
    labels = reversals['zigzag_label'].tolist()
    alternating = all(
        labels[i] != labels[i+1] 
        for i in range(len(labels)-1)
    )
    
    print(f"\n--- Validation ---")
    print(f"Peaks and valleys alternate: {'✅ YES' if alternating else '❌ NO'}")
    print(f"First reversal is: {'PEAK' if labels[0] == 1 else 'VALLEY'}")
    print(f"Last reversal is:  {'PEAK' if labels[-1] == 1 else 'VALLEY'}")
    
    print("\n" + "="*60)
    print("Test Complete!")
    print("="*60)
    
    return labeled_df, stats


def test_with_real_data():
    """Test with actual database data (requires DB connection)."""
    
    print("\n" + "="*60)
    print("Testing with Real Database Data")
    print("="*60)
    
    try:
        import asyncio
        from src.database.config import initialize_database, get_database
        from src.ml.labeling import ZigZagLabelService
        
        async def run():
            initialize_database()
            db = get_database()
            
            async with db.get_session() as session:
                service = ZigZagLabelService(session)
                
                # Just get distribution without updating
                dist = await service.get_label_distribution('CrudeOIL', 'H1')
                print(f"\nCurrent label distribution in DB:")
                print(f"  Peaks:   {dist['peak']}")
                print(f"  Valleys: {dist['valley']}")
                print(f"  Neither: {dist['neither']}")
                print(f"  Total:   {dist['total']}")
        
        asyncio.run(run())
        
    except Exception as e:
        print(f"Could not connect to database: {e}")
        print("Run with database to test real data labeling.")


if __name__ == '__main__':
    # Run basic test
    labeled_df, stats = test_labeler()
    
    # Optionally test with real data
    if '--db' in sys.argv:
        test_with_real_data()
