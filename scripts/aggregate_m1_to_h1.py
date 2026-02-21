#!/usr/bin/env python3
"""
Aggregate M1 candles to H1 candles in the database.

This script:
1. Reads all M1 candles for a symbol
2. Aggregates them into H1 bars
3. Inserts them with timeframe='H1'

Usage:
    python scripts/aggregate_m1_to_h1.py --symbol CrudeOIL
"""
import asyncio
import argparse
from datetime import datetime
from decimal import Decimal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.database.config import create_session_factory, create_engine_from_env


async def aggregate_m1_to_h1(symbol: str, batch_size: int = 10000):
    """Aggregate M1 candles to H1 candles."""
    
    engine = create_engine_from_env()
    session_factory = create_session_factory(engine)
    
    async with session_factory() as session:
        # First, check if H1 data already exists
        check_query = text("""
            SELECT COUNT(*) as cnt 
            FROM market_data 
            WHERE symbol = :symbol AND timeframe = 'H1'
        """)
        result = await session.execute(check_query, {"symbol": symbol})
        existing_count = result.scalar()
        
        if existing_count > 0:
            print(f"⚠️  Found {existing_count} existing H1 candles for {symbol}")
            response = input("Delete and recreate? (y/n): ")
            if response.lower() != 'y':
                print("Aborted.")
                return
            
            delete_query = text("""
                DELETE FROM market_data 
                WHERE symbol = :symbol AND timeframe = 'H1'
            """)
            await session.execute(delete_query, {"symbol": symbol})
            await session.commit()
            print(f"Deleted {existing_count} H1 candles")
        
        # Count M1 candles
        count_query = text("""
            SELECT COUNT(*) as cnt 
            FROM market_data 
            WHERE symbol = :symbol AND timeframe = 'M1'
        """)
        result = await session.execute(count_query, {"symbol": symbol})
        m1_count = result.scalar()
        print(f"Found {m1_count:,} M1 candles for {symbol}")
        
        # Aggregate and insert H1 candles
        # Using a single INSERT...SELECT for efficiency
        aggregate_query = text("""
            INSERT INTO market_data (
                time, symbol, import_symbol, timeframe, source,
                open, high, low, last, 
                change, change_percent, volume,
                created_at, updated_at
            )
            SELECT 
                date_trunc('hour', time) as time,
                symbol,
                'AGGREGATED' as import_symbol,
                'H1' as timeframe,
                'MT4' as source,
                (array_agg(open ORDER BY time))[1] as open,
                MAX(high) as high,
                MIN(low) as low,
                (array_agg(last ORDER BY time DESC))[1] as last,
                '0' as change,
                '0' as change_percent,
                SUM(volume) as volume,
                NOW() as created_at,
                NOW() as updated_at
            FROM market_data
            WHERE symbol = :symbol AND timeframe = 'M1'
            GROUP BY date_trunc('hour', time), symbol
            ORDER BY date_trunc('hour', time)
        """)
        
        print("Aggregating M1 to H1...")
        start_time = datetime.now()
        
        await session.execute(aggregate_query, {"symbol": symbol})
        await session.commit()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Verify results
        verify_query = text("""
            SELECT 
                COUNT(*) as cnt,
                MIN(time) as first_bar,
                MAX(time) as last_bar
            FROM market_data 
            WHERE symbol = :symbol AND timeframe = 'H1'
        """)
        result = await session.execute(verify_query, {"symbol": symbol})
        row = result.fetchone()
        
        print(f"\n✅ Created {row.cnt:,} H1 candles in {elapsed:.1f}s")
        print(f"   First bar: {row.first_bar}")
        print(f"   Last bar:  {row.last_bar}")
        print(f"   Compression ratio: {m1_count / row.cnt:.0f}:1")


async def main():
    parser = argparse.ArgumentParser(description="Aggregate M1 to H1 candles")
    parser.add_argument("--symbol", required=True, help="Symbol to aggregate")
    args = parser.parse_args()
    
    await aggregate_m1_to_h1(args.symbol)


if __name__ == "__main__":
    asyncio.run(main())
