#!/usr/bin/env python3
"""
Download stock data (TSLA, MSFT) using yfinance and import to RiseTrader database.

yfinance data availability:
  - M1:  ~7 days
  - M5:  ~60 days
  - M15: ~60 days
  - M30: ~60 days
  - H1:  ~730 days (2 years)
  - D1:  ~20+ years

Usage (run from HOST Mac, not Docker):
    python3 scripts/download_stocks_yfinance.py

This script:
  1. Downloads max available data from yfinance
  2. Saves to CSV files in data/downloads/yfinance/
  3. Prints Docker import command to run
"""

import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system(f"{sys.executable} -m pip install yfinance --quiet")
    import yfinance as yf

# Configuration
STOCKS = {
    "TSLA": {"yf": "TSLA", "mt4": "#TSLA", "internal": "TSLA"},
    "MSFT": {"yf": "MSFT", "mt4": "#MICROSOFT", "internal": "MSFT"},
}

TIMEFRAMES = {
    "M1":  {"interval": "1m",  "period": "7d",   "max_period": "7d"},
    "M5":  {"interval": "5m",  "period": "60d",  "max_period": "60d"},
    "M30": {"interval": "30m", "period": "60d",  "max_period": "60d"},
    "H1":  {"interval": "1h",  "period": "730d", "max_period": "730d"},
    "D1":  {"interval": "1d",  "period": "max",  "max_period": "max"},
}

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "downloads" / "yfinance"


def download_stock(symbol_config: dict, timeframes: dict) -> dict:
    """Download all timeframes for a stock."""
    yf_symbol = symbol_config["yf"]
    internal = symbol_config["internal"]

    print(f"\n{'='*60}")
    print(f"Downloading {yf_symbol} (internal: {internal})")
    print(f"{'='*60}")

    ticker = yf.Ticker(yf_symbol)
    results = {}

    for tf_name, tf_config in timeframes.items():
        try:
            print(f"\n  {tf_name} (interval={tf_config['interval']}, period={tf_config['period']})...")

            hist = ticker.history(
                period=tf_config["period"],
                interval=tf_config["interval"],
            )

            if hist.empty:
                print(f"    No data returned")
                continue

            # Normalize columns to match RiseTrader format
            df = pd.DataFrame({
                "time": hist.index.tz_localize(None) if hist.index.tz else hist.index,
                "open": hist["Open"].values,
                "high": hist["High"].values,
                "low": hist["Low"].values,
                "close": hist["Close"].values,
                "volume": hist["Volume"].astype(int).values,
            })

            # Remove rows with NaN
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df.sort_values("time").drop_duplicates(subset=["time"])

            # Save CSV
            csv_path = OUTPUT_DIR / f"{internal}_{tf_name}.csv"
            df.to_csv(csv_path, index=False)

            results[tf_name] = {
                "candles": len(df),
                "start": str(df["time"].min()),
                "end": str(df["time"].max()),
                "file": str(csv_path),
            }

            print(f"    {len(df):,} candles: {df['time'].min()} → {df['time'].max()}")
            print(f"    Saved: {csv_path.name}")

        except Exception as e:
            print(f"    ERROR: {e}")
            continue

    return results


def generate_import_sql(symbol: str, source: str, timeframe: str, csv_path: str) -> str:
    """Generate SQL import command for a CSV file."""
    return f"""
-- Import {symbol} {timeframe} from {source}
COPY market_data_staging FROM '{csv_path}' CSV HEADER;
"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("RiseTrader Stock Data Downloader (yfinance)")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_results = {}

    for stock_name, config in STOCKS.items():
        results = download_stock(config, TIMEFRAMES)
        all_results[stock_name] = results

    # Summary
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)

    csv_files = []
    for stock_name, results in all_results.items():
        print(f"\n{stock_name}:")
        for tf, info in results.items():
            print(f"  {tf}: {info['candles']:>8,} candles  [{info['start'][:10]} → {info['end'][:10]}]")
            csv_files.append((stock_name, tf, info["file"]))

    # Generate Docker import command
    print("\n" + "=" * 60)
    print("IMPORT INSTRUCTIONS")
    print("=" * 60)
    print("\nRun this command to import all data to the database:")
    print()

    for stock_name, tf, csv_file in csv_files:
        rel_path = os.path.relpath(csv_file, Path(__file__).parent.parent)
        print(f'docker exec risetrader-api python3 -c "')
        print(f"import asyncio, sys, pandas as pd")
        print(f"from pathlib import Path")
        print(f"sys.path.insert(0, '/app')")
        print(f"from sqlalchemy import text")
        print(f"from src.database.config import create_engine_from_env, create_session_factory")
        print(f"")
        print(f"async def import_csv():")
        print(f"    df = pd.read_csv('/app/{rel_path}', parse_dates=['time'])")
        print(f"    engine = create_engine_from_env()")
        print(f"    sf = create_session_factory(engine)")
        print(f"    async with sf() as session:")
        print(f"        for _, row in df.iterrows():")
        print(f"            await session.execute(text('''")
        print(f"                INSERT INTO market_data (time, symbol, import_symbol, timeframe, source,")
        print(f"                    open, high, low, last, change, change_percent, volume, created_at, updated_at)")
        print(f"                VALUES (:time, :symbol, :import_symbol, :timeframe, :source,")
        print(f"                    :open, :high, :low, :last, '0', '0', :volume, NOW(), NOW())")
        print(f"                ON CONFLICT (symbol, timeframe, time) DO UPDATE SET")
        print(f"                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,")
        print(f"                    last=EXCLUDED.last, volume=EXCLUDED.volume, updated_at=NOW()")
        print(f"            '''), dict(time=row['time'], symbol='{stock_name}', import_symbol='YFINANCE',")
        print(f"                timeframe='{tf}', source='CSV', open=str(row['open']),")
        print(f"                high=str(row['high']), low=str(row['low']), last=str(row['close']),")
        print(f"                volume=int(row['volume'])))")
        print(f"        await session.commit()")
        print(f"        print(f'Imported {{len(df)}} {stock_name} {tf} candles')")
        print(f"asyncio.run(import_csv())")
        print(f'"')
        print()


if __name__ == "__main__":
    main()
