#!/usr/bin/env python3
"""
Quick data sync for portfolio optimization
Downloads latest data from Dukascopy for our target symbols
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, '/app')

from src.data.dukascopy import DukascopyDownloader
from src.data.base import Timeframe


# Symbols to download
SYMBOLS = [
    "CrudeOIL",  # Maps to LIGHTCMDUSD
    "XAUUSD",    # Gold
    "EURUSD",
    "GBPUSD",
    "USDJPY",
]


async def main():
    """Download latest data for all symbols"""
    print("=" * 60)
    print("DATA SYNC - Downloading latest market data")
    print("=" * 60)

    downloader = DukascopyDownloader(data_dir=Path("/app/data/downloads"))

    # Download last 6 months of data
    end_date = date.today()
    start_date = end_date - timedelta(days=180)

    print(f"\nPeriod: {start_date} to {end_date}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print()

    for symbol in SYMBOLS:
        print(f"\n📥 Downloading {symbol}...")
        try:
            result = await downloader.download(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=Timeframe.M1
            )

            if result.get("success"):
                print(f"   ✅ Downloaded {result.get('bars_count', 0):,} bars")
                print(f"   📁 File: {result.get('file_path', 'N/A')}")
            else:
                print(f"   ⚠️  Warning: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("✅ Data sync complete!")
    print("=" * 60)
    print("\nNext: Run the portfolio optimizer:")
    print("  python scripts/portfolio_optimizer.py")


if __name__ == "__main__":
    asyncio.run(main())
