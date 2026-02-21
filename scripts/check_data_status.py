#!/usr/bin/env python3
"""
Quick data status check for RiseTrader.
Run this to see current data coverage and gaps.
"""
import sys
from datetime import date, timedelta

# Database connection
import psycopg2

def check_data_status():
    """Check current data status in database."""
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        database="risetrader",
        user="postgres",
        password="risetrader2024"
    )
    cur = conn.cursor()
    
    print("=" * 70)
    print("RISETRADER DATA STATUS REPORT")
    print("=" * 70)
    
    # Get coverage by symbol and source
    cur.execute("""
        SELECT 
            symbol,
            source,
            timeframe,
            COUNT(*) as records,
            MIN(time)::date as start_date,
            MAX(time)::date as end_date,
            COUNT(DISTINCT DATE(time)) as days_with_data
        FROM market_data
        WHERE timeframe = 'M1'
        GROUP BY symbol, source, timeframe
        ORDER BY symbol, source
    """)
    
    rows = cur.fetchall()
    
    print("\n📊 CURRENT DATA COVERAGE (M1 timeframe):")
    print("-" * 70)
    print(f"{'Symbol':<12} {'Source':<10} {'Records':>12} {'Start':<12} {'End':<12} {'Days':>6}")
    print("-" * 70)
    
    for row in rows:
        symbol, source, tf, records, start, end, days = row
        print(f"{symbol:<12} {source:<10} {records:>12,} {str(start):<12} {str(end):<12} {days:>6}")
    
    # Check gaps for CrudeOIL specifically
    print("\n" + "=" * 70)
    print("🔍 CRUDEOIL DATA GAP ANALYSIS")
    print("=" * 70)
    
    # Get BC data end date
    cur.execute("""
        SELECT MAX(time)::date FROM market_data 
        WHERE symbol = 'CrudeOIL' AND source = 'BC' AND timeframe = 'M1'
    """)
    bc_end = cur.fetchone()[0]
    
    # Get MT4 data range
    cur.execute("""
        SELECT MIN(time)::date, MAX(time)::date FROM market_data 
        WHERE symbol = 'CrudeOIL' AND source = 'MT4' AND timeframe = 'M1'
    """)
    mt4_start, mt4_end = cur.fetchone()
    
    today = date.today()
    
    print(f"\n  Barchart (BC) data ends:     {bc_end}")
    print(f"  MT4 data range:              {mt4_start} to {mt4_end}")
    print(f"  Today:                       {today}")
    
    # Calculate gap
    if bc_end:
        gap_start = bc_end + timedelta(days=1)
        gap_days = (today - bc_end).days
        trading_days = sum(1 for i in range(gap_days) 
                         if (bc_end + timedelta(days=i+1)).weekday() < 5)
        
        print(f"\n  ⚠️  GAP TO FILL: {gap_start} to {today}")
        print(f"      Calendar days: {gap_days}")
        print(f"      Trading days:  ~{trading_days}")
        print(f"\n  📥 RECOMMENDED ACTION:")
        print(f"      python scripts/download_dukascopy.py full")
        print(f"      (Downloads {gap_start} to {today} from Dukascopy)")
    
    # Check data quality - bars per day
    print("\n" + "=" * 70)
    print("📈 DATA QUALITY CHECK (expected ~1440 bars/day for 24h market)")
    print("=" * 70)
    
    cur.execute("""
        WITH daily_counts AS (
            SELECT 
                source,
                DATE(time) as day,
                COUNT(*) as bars
            FROM market_data
            WHERE symbol = 'CrudeOIL' AND timeframe = 'M1'
            GROUP BY source, DATE(time)
        )
        SELECT 
            source,
            ROUND(AVG(bars)) as avg_bars_per_day,
            MIN(bars) as min_bars,
            MAX(bars) as max_bars,
            COUNT(*) as total_days
        FROM daily_counts
        GROUP BY source
    """)
    
    print(f"\n{'Source':<10} {'Avg Bars/Day':>14} {'Min':>8} {'Max':>8} {'Days':>8}")
    print("-" * 50)
    for row in cur.fetchall():
        source, avg, min_b, max_b, days = row
        print(f"{source:<10} {avg:>14.0f} {min_b:>8} {max_b:>8} {days:>8}")
    
    conn.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    check_data_status()
