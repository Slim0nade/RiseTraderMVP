#!/usr/bin/env python3
"""Test the Dukascopy downloader with a small date range."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from scripts.download_free_data import DukascopyDownloader, HistDataDownloader

def test_dukascopy():
    """Test Dukascopy downloader with 2 days of WTI data."""
    print("=" * 60)
    print("Testing Dukascopy Downloader")
    print("=" * 60)
    
    downloader = DukascopyDownloader(output_dir="data/dukascopy")
    
    # Test with just 2 days of data
    df = downloader.download_range(
        symbol="WTIUSD",
        start_date=datetime(2024, 12, 1),
        end_date=datetime(2024, 12, 2)
    )
    
    print(f"\nDownloaded {len(df)} M1 candles")
    
    if len(df) > 0:
        print("\nFirst 5 records:")
        print(df.head().to_string())
        print("\nLast 5 records:")
        print(df.tail().to_string())
        
        # Save to CSV
        filepath = downloader.save_csv(df, "WTIUSD", datetime(2024, 12, 1), datetime(2024, 12, 2))
        print(f"\nSaved to: {filepath}")
        
    return df


def test_histdata():
    """Test HistData downloader with 1 year of WTI data."""
    print("\n" + "=" * 60)
    print("Testing HistData Downloader")
    print("=" * 60)
    
    downloader = HistDataDownloader(output_dir="data/histdata")
    
    # Test with just 2024 data
    df = downloader.download_range(
        symbol="WTIUSD",
        start_year=2024,
        end_year=2024
    )
    
    print(f"\nDownloaded {len(df)} M1 candles")
    
    if len(df) > 0:
        print("\nFirst 5 records:")
        print(df.head().to_string())
        print("\nLast 5 records:")
        print(df.tail().to_string())
        
        # Save to CSV
        filepath = downloader.save_csv(df, "WTIUSD")
        if filepath:
            print(f"\nSaved to: {filepath}")
        
    return df


if __name__ == "__main__":
    print("Testing Free Data Downloaders\n")
    
    # Test Dukascopy
    try:
        duka_df = test_dukascopy()
    except Exception as e:
        print(f"Dukascopy test failed: {e}")
        duka_df = None
    
    # Test HistData
    try:
        hist_df = test_histdata()
    except Exception as e:
        print(f"HistData test failed: {e}")
        hist_df = None
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Dukascopy: {'✅ ' + str(len(duka_df)) + ' records' if duka_df is not None and len(duka_df) > 0 else '❌ Failed'}")
    print(f"HistData:  {'✅ ' + str(len(hist_df)) + ' records' if hist_df is not None and len(hist_df) > 0 else '❌ Failed'}")
