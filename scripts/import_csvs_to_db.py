#!/usr/bin/env python3.12
"""
Import stock CSV data (TSLA, MSFT from yfinance) directly to PostgreSQL.
Runs on HOST Mac, connects to PostgreSQL container on port 5433.

Also handles importing Dukascopy CSVs for GOLD and USA500.

Usage:
    python3.12 scripts/import_csvs_to_db.py
"""
import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from datetime import datetime, timezone

# Database connection
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'dbname': 'risetrader',
    'user': 'postgres',
    'password': 'risetrader2024',
}

# yfinance downloads directory
YFINANCE_DIR = Path(__file__).parent.parent / "data" / "downloads" / "yfinance"
DUKASCOPY_DIR = Path(__file__).parent.parent / "data" / "downloads" / "dukascopy"

# Stock symbol config: internal_symbol -> (source, import_symbol)
YFINANCE_STOCKS = {
    "TSLA": {"source": "CSV", "import_symbol": "TSLA_YF"},
    "MSFT": {"source": "CSV", "import_symbol": "MSFT_YF"},
}

DUKASCOPY_SYMBOLS = {
    "GOLD": {"source": "DUKASCOPY", "import_symbol": "XAUUSD"},
    "USA500": {"source": "DUKASCOPY", "import_symbol": "USA500IDXUSD"},
}


def import_csv_to_db(conn, csv_path: Path, symbol: str, timeframe: str,
                     source: str, import_symbol: str, close_col: str = "close"):
    """Import a CSV file to market_data table."""
    df = pd.read_csv(csv_path, parse_dates=['time'])
    
    if df.empty:
        print(f"  SKIP {csv_path.name}: empty file")
        return 0
    
    # Ensure timezone-aware timestamps (UTC)
    if df['time'].dt.tz is None:
        df['time'] = df['time'].dt.tz_localize('UTC')
    else:
        df['time'] = df['time'].dt.tz_convert('UTC')
    
    # Remove NaN rows
    df = df.dropna(subset=['open', 'high', 'low', close_col])
    df = df.sort_values('time').drop_duplicates(subset=['time'])
    
    # Calculate change and change_percent
    df['change_val'] = df[close_col] - df['open']
    df['change_pct'] = ((df[close_col] - df['open']) / df['open'] * 100).round(4)
    
    # Handle volume (default 0 if missing)
    if 'volume' not in df.columns:
        df['volume'] = 0
    df['volume'] = df['volume'].fillna(0).astype(int)
    
    # Prepare data tuples
    rows = []
    for _, row in df.iterrows():
        rows.append((
            row['time'].to_pydatetime(),
            symbol,
            import_symbol,
            timeframe,
            source,
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row[close_col]),
            float(row['change_val']),
            float(row['change_pct']),
            int(row['volume']),
        ))
    
    # Batch insert with ON CONFLICT matching the unique constraint
    insert_sql = """
        INSERT INTO market_data 
            (time, symbol, import_symbol, timeframe, source, 
             open, high, low, last, change, change_percent, volume,
             created_at, updated_at)
        VALUES %s
        ON CONFLICT (time, source, timeframe, symbol) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            last = EXCLUDED.last,
            change = EXCLUDED.change,
            change_percent = EXCLUDED.change_percent,
            volume = EXCLUDED.volume,
            updated_at = NOW()
    """
    
    template = """(
        %s, %s, %s, %s::timeframe, %s::datasource,
        %s, %s, %s, %s, %s, %s, %s,
        NOW(), NOW()
    )"""
    
    cur = conn.cursor()
    
    # Insert in batches of 5000
    batch_size = 5000
    total_inserted = 0
    
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        execute_values(cur, insert_sql, batch, template=template, page_size=batch_size)
        total_inserted += len(batch)
        if total_inserted % 10000 == 0 or total_inserted == len(rows):
            print(f"    {total_inserted:>8,}/{len(rows):,} rows...")
    
    conn.commit()
    print(f"  OK {csv_path.name}: {len(rows):,} candles [{df['time'].min().date()} → {df['time'].max().date()}]")
    return len(rows)


def import_yfinance_stocks(conn):
    """Import all yfinance stock CSVs."""
    if not YFINANCE_DIR.exists():
        print(f"yfinance directory not found: {YFINANCE_DIR}")
        return
    
    print("\n" + "=" * 60)
    print("IMPORTING YFINANCE STOCKS (TSLA, MSFT)")
    print("=" * 60)
    
    total = 0
    for symbol, config in YFINANCE_STOCKS.items():
        print(f"\n{symbol}:")
        for tf in ['M5', 'M30', 'H1', 'D1']:
            csv_path = YFINANCE_DIR / f"{symbol}_{tf}.csv"
            if csv_path.exists():
                count = import_csv_to_db(
                    conn, csv_path, symbol, tf,
                    config['source'], config['import_symbol']
                )
                total += count
            else:
                print(f"  MISSING: {csv_path.name}")
    
    print(f"\nTotal yfinance: {total:,} candles imported")
    return total


def import_dukascopy_csvs(conn):
    """Import Dukascopy combined CSV files."""
    if not DUKASCOPY_DIR.exists():
        print(f"Dukascopy directory not found: {DUKASCOPY_DIR}")
        return 0
    
    print("\n" + "=" * 60)
    print("IMPORTING DUKASCOPY DATA (GOLD, USA500)")
    print("=" * 60)
    
    total = 0
    for symbol, config in DUKASCOPY_SYMBOLS.items():
        print(f"\n{symbol}:")
        for tf in ['M1', 'M5', 'M30', 'H1']:
            csv_path = DUKASCOPY_DIR / f"{symbol}_{tf}_combined.csv"
            if csv_path.exists():
                count = import_csv_to_db(
                    conn, csv_path, symbol, tf,
                    config['source'], config['import_symbol']
                )
                total += count
            else:
                print(f"  MISSING: {csv_path.name}")
    
    print(f"\nTotal Dukascopy: {total:,} candles imported")
    return total


def main():
    print("=" * 60)
    print("RiseTrader CSV Data Importer")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Connect to database
    print(f"\nConnecting to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}...")
    conn = psycopg2.connect(**DB_CONFIG)
    print("Connected!")
    
    try:
        # Import yfinance stocks
        yf_total = import_yfinance_stocks(conn)
        
        # Import Dukascopy data (if available)
        dk_total = import_dukascopy_csvs(conn)
        
        # Summary
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, COUNT(*) as candles,
                   MIN(time)::date as start_date, MAX(time)::date as end_date
            FROM market_data
            WHERE symbol IN ('TSLA', 'MSFT', 'GOLD', 'USA500')
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
        """)
        
        rows = cur.fetchall()
        print(f"\n{'Symbol':<10} {'TF':<5} {'Candles':>10} {'Start':>12} {'End':>12}")
        print("-" * 55)
        for r in rows:
            print(f"{r[0]:<10} {r[1]:<5} {r[2]:>10,} {str(r[3]):>12} {str(r[4]):>12}")
        
    finally:
        conn.close()
    
    print("\nDone!")


if __name__ == "__main__":
    main()
