#!/usr/bin/env python3.12
"""
Download GOLD and USA500 historical data from Dukascopy.
Runs on HOST Mac (not Docker) - saves CSV files for import.

Dukascopy provides free tick data in bi5 (gzip binary) format.
URL: https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YEAR}/{MONTH_0IDX}/{DAY}/{HOUR}h_ticks.bi5

Usage:
    python3.12 scripts/download_dukascopy_host.py
    python3.12 scripts/download_dukascopy_host.py --symbol GOLD --start 2023-01-01 --end 2026-02-10
    python3.12 scripts/download_dukascopy_host.py --symbol USA500 --start 2023-01-01 --end 2026-02-10
"""
import asyncio
import aiohttp
import struct
import gzip
import lzma
import ssl
import pandas as pd
import argparse
import time
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

# Dukascopy symbol mappings (point = multiply factor, NOT divide)
SYMBOLS = {
    'GOLD': {'dk': 'XAUUSD', 'point': 0.001},           # Gold: 3 decimals
    'USA500': {'dk': 'USA500IDXUSD', 'point': 0.001},     # Index: 3 decimals (verified Jan 2025 ~6000)
    'CrudeOIL': {'dk': 'LIGHTCMDUSD', 'point': 0.001},   # WTI Oil: 3 decimals (was WTICOUSD)
}

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "downloads" / "dukascopy"


def parse_bi5_ticks(data: bytes, point_value: float) -> list:
    """Parse Dukascopy bi5 binary tick data (20 bytes per record).
    Format: LZMA or gzip compressed, each record 20 bytes:
      - uint32 BE: ms from start of hour
      - uint32 BE: ask price (integer)
      - uint32 BE: bid price (integer)
      - float32 BE: ask volume
      - float32 BE: bid volume
    Price = raw_int * point_value
    """
    ticks = []
    try:
        # Try LZMA first (newer Dukascopy format), then gzip (legacy)
        try:
            decompressed = lzma.decompress(data)
        except Exception:
            decompressed = gzip.decompress(data)
    except Exception:
        return ticks

    record_size = 20
    num_records = len(decompressed) // record_size

    for i in range(num_records):
        offset = i * record_size
        record = decompressed[offset:offset + record_size]
        if len(record) < record_size:
            break
        ms, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack('>IIIff', record)
        ask = ask_raw * point_value
        bid = bid_raw * point_value
        ticks.append({
            'ms': ms,
            'mid': (ask + bid) / 2,
            'volume': ask_vol + bid_vol,
        })
    return ticks


def aggregate_ticks_to_m1(ticks: list, hour_start: datetime) -> list:
    """Aggregate ticks to 1-minute OHLCV candles."""
    if not ticks:
        return []
    minute_groups = defaultdict(list)
    for tick in ticks:
        minute = tick['ms'] // 60000
        minute_groups[minute].append(tick)

    candles = []
    for minute, group in sorted(minute_groups.items()):
        candle_time = hour_start + timedelta(minutes=minute)
        prices = [t['mid'] for t in group]
        volumes = [t['volume'] for t in group]
        candles.append({
            'time': candle_time,
            'open': prices[0],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': int(sum(volumes)),
        })
    return candles


async def download_hour(session, dk_symbol, dt, point_value, semaphore, retry=2):
    """Download one hour of tick data -> M1 candles."""
    month_0idx = dt.month - 1
    url = f"{BASE_URL}/{dk_symbol}/{dt.year}/{month_0idx:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"

    for attempt in range(retry + 1):
        async with semaphore:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 0:
                            ticks = parse_bi5_ticks(data, point_value)
                            return aggregate_ticks_to_m1(ticks, dt)
                    elif resp.status == 503:
                        if attempt < retry:
                            await asyncio.sleep(1)
                            continue
                    return []
            except Exception as e:
                if attempt < retry:
                    await asyncio.sleep(1)
                    continue
                return []
    return []


async def download_day(session, dk_symbol, day, point_value, semaphore):
    """Download all 24 hours for a day."""
    tasks = []
    for hour in range(24):
        dt = datetime(day.year, day.month, day.day, hour)
        tasks.append(download_hour(session, dk_symbol, dt, point_value, semaphore))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    candles = []
    for result in results:
        if isinstance(result, list):
            candles.extend(result)
    return candles


def aggregate_m1_to_higher(df_m1: pd.DataFrame, symbol: str, output_dir: Path):
    """Aggregate M1 to M5, M30, H1."""
    results = {}
    df = df_m1.copy()
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time')

    for tf_name, minutes in [('M5', 5), ('M30', 30), ('H1', 60)]:
        df['bucket'] = df['time'].dt.floor(f'{minutes}min')
        agg = df.groupby('bucket').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        }).reset_index()
        agg = agg.rename(columns={'bucket': 'time'})
        tf_file = output_dir / f"{symbol}_{tf_name}_combined.csv"
        agg.to_csv(tf_file, index=False)
        results[tf_name] = len(agg)
        logger.info(f"  {tf_name}: {len(agg):,} candles -> {tf_file.name}")

    return results


async def download_symbol(symbol: str, start_date: date, end_date: date):
    """Download full M1 data for a symbol."""
    config = SYMBOLS.get(symbol)
    if not config:
        logger.error(f"Unknown symbol: {symbol}")
        return None

    dk_symbol = config['dk']
    point_value = config['point']
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_days = (end_date - start_date).days
    logger.info(f"Downloading {symbol} ({dk_symbol}) from {start_date} to {end_date} ({total_days} days)")

    all_candles = []
    current_date = start_date
    semaphore = asyncio.Semaphore(15)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(limit=30, limit_per_host=15, ssl=ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        while current_date < end_date:
            # Process in monthly chunks
            month_end = date(
                current_date.year + (1 if current_date.month == 12 else 0),
                (current_date.month % 12) + 1, 1
            )
            month_end = min(month_end, end_date)
            days_in_chunk = (month_end - current_date).days

            logger.info(f"  {symbol} | {current_date.strftime('%Y-%m')} | {days_in_chunk} days...")
            start_time = time.time()

            month_candles = []
            for day_offset in range(days_in_chunk):
                day = current_date + timedelta(days=day_offset)
                if day.weekday() >= 5:  # Skip weekends
                    continue
                day_candles = await download_day(session, dk_symbol, day, point_value, semaphore)
                month_candles.extend(day_candles)

            elapsed = time.time() - start_time

            if month_candles:
                df_month = pd.DataFrame(month_candles)
                df_month = df_month.sort_values('time').drop_duplicates(subset=['time'])
                month_file = OUTPUT_DIR / f"{symbol}_M1_{current_date.strftime('%Y_%m')}.csv"
                df_month.to_csv(month_file, index=False)
                logger.info(f"    -> {len(df_month):,} candles ({elapsed:.1f}s)")
                all_candles.extend(month_candles)
            else:
                logger.info(f"    -> No data ({elapsed:.1f}s)")

            current_date = month_end

    if all_candles:
        df_all = pd.DataFrame(all_candles)
        df_all = df_all.sort_values('time').drop_duplicates(subset=['time'])
        combined_file = OUTPUT_DIR / f"{symbol}_M1_combined.csv"
        df_all.to_csv(combined_file, index=False)
        logger.info(f"\n{symbol} COMPLETE: {len(df_all):,} M1 candles")
        logger.info(f"  Range: {df_all['time'].min()} to {df_all['time'].max()}")

        # Aggregate to higher timeframes
        logger.info(f"\nAggregating {symbol} to higher timeframes...")
        aggregate_m1_to_higher(df_all, symbol, OUTPUT_DIR)

        return combined_file
    return None


async def main():
    parser = argparse.ArgumentParser(description='Download Dukascopy data')
    parser.add_argument('--symbol', type=str, help='Symbol to download (GOLD, USA500)')
    parser.add_argument('--start', type=str, default='2023-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, default='2026-02-10', help='End date YYYY-MM-DD')
    args = parser.parse_args()

    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()

    symbols = [args.symbol] if args.symbol else ['GOLD', 'USA500']

    for symbol in symbols:
        logger.info(f"\n{'='*60}")
        logger.info(f"DOWNLOADING: {symbol}")
        logger.info(f"{'='*60}")
        await download_symbol(symbol, start, end)


if __name__ == "__main__":
    asyncio.run(main())
