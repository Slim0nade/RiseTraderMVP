#!/usr/bin/env python3.12
"""
Synchronous Dukascopy downloader - uses requests (no async).
Simpler and more reliable than async version.

Usage:
    python3.12 scripts/download_dukascopy_sync.py --symbol GOLD --start 2023-01-01 --end 2026-02-10
"""
import requests
import struct
import lzma
import gzip
import pandas as pd
import argparse
import time
import logging
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Symbol configs: point = multiply factor for price conversion
SYMBOLS = {
    'GOLD': {'dk': 'XAUUSD', 'point': 0.001},
    'USA500': {'dk': 'USA500IDXUSD', 'point': 0.001},
    'CrudeOIL': {'dk': 'LIGHTCMDUSD', 'point': 0.001},
}

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "downloads" / "dukascopy"

# Create session with SSL verification disabled (macOS Python cert issue)
SESSION = requests.Session()
SESSION.verify = False
# Suppress InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_bi5(data: bytes, point_value: float) -> list:
    """Parse Dukascopy bi5 tick data (LZMA or gzip compressed)."""
    try:
        try:
            decompressed = lzma.decompress(data)
        except Exception:
            decompressed = gzip.decompress(data)
    except Exception:
        return []

    ticks = []
    n = len(decompressed) // 20
    for i in range(n):
        offset = i * 20
        ms, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(
            '>IIIff', decompressed[offset:offset + 20]
        )
        ask = ask_raw * point_value
        bid = bid_raw * point_value
        ticks.append({'ms': ms, 'mid': (ask + bid) / 2, 'volume': ask_vol + bid_vol})
    return ticks


def ticks_to_m1(ticks: list, hour_start: datetime) -> list:
    """Aggregate ticks to 1-minute OHLCV candles."""
    if not ticks:
        return []
    minute_groups = defaultdict(list)
    for t in ticks:
        minute_groups[t['ms'] // 60000].append(t)

    candles = []
    for minute, group in sorted(minute_groups.items()):
        prices = [t['mid'] for t in group]
        candles.append({
            'time': hour_start + timedelta(minutes=minute),
            'open': prices[0],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': int(sum(t['volume'] for t in group)),
        })
    return candles


def download_hour(dk_symbol: str, dt: datetime, point_value: float) -> list:
    """Download one hour of data."""
    month_0idx = dt.month - 1
    url = f"{BASE_URL}/{dk_symbol}/{dt.year}/{month_0idx:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 200 and len(resp.content) > 0:
            ticks = parse_bi5(resp.content, point_value)
            return ticks_to_m1(ticks, dt)
    except Exception:
        pass
    return []


def download_day(dk_symbol: str, day: date, point_value: float) -> list:
    """Download all 24 hours for a day using thread pool."""
    candles = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        for hour in range(24):
            dt = datetime(day.year, day.month, day.day, hour)
            f = executor.submit(download_hour, dk_symbol, dt, point_value)
            futures[f] = hour

        for f in as_completed(futures):
            result = f.result()
            if result:
                candles.extend(result)

    return sorted(candles, key=lambda x: x['time'])


def aggregate_m1(df_m1: pd.DataFrame, symbol: str, output_dir: Path):
    """Aggregate M1 to M5, M30, H1."""
    df = df_m1.copy()
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time')

    for tf_name, minutes in [('M5', 5), ('M30', 30), ('H1', 60)]:
        df['bucket'] = df['time'].dt.floor(f'{minutes}min')
        agg = df.groupby('bucket').agg({
            'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'volume': 'sum',
        }).reset_index().rename(columns={'bucket': 'time'})
        tf_file = output_dir / f"{symbol}_{tf_name}_combined.csv"
        agg.to_csv(tf_file, index=False)
        logger.info(f"  {tf_name}: {len(agg):,} candles -> {tf_file.name}")


def download_symbol(symbol: str, start_date: date, end_date: date):
    """Download full M1 data for a symbol."""
    config = SYMBOLS[symbol]
    dk_symbol = config['dk']
    point_value = config['point']
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_days = (end_date - start_date).days
    logger.info(f"Downloading {symbol} ({dk_symbol}) from {start_date} to {end_date} ({total_days} days)")

    all_candles = []
    current_date = start_date

    while current_date < end_date:
        # Monthly chunks
        month_end = date(
            current_date.year + (1 if current_date.month == 12 else 0),
            (current_date.month % 12) + 1, 1
        )
        month_end = min(month_end, end_date)
        days_in_chunk = (month_end - current_date).days

        logger.info(f"  {symbol} | {current_date.strftime('%Y-%m')} | {days_in_chunk} days...")
        t0 = time.time()
        month_candles = []

        for day_offset in range(days_in_chunk):
            day = current_date + timedelta(days=day_offset)
            if day.weekday() >= 5:
                continue
            day_candles = download_day(dk_symbol, day, point_value)
            month_candles.extend(day_candles)
            # Flush progress every 5 days
            if day_offset % 5 == 4:
                sys.stderr.flush()

        elapsed = time.time() - t0

        if month_candles:
            df = pd.DataFrame(month_candles)
            df = df.sort_values('time').drop_duplicates(subset=['time'])
            month_file = OUTPUT_DIR / f"{symbol}_M1_{current_date.strftime('%Y_%m')}.csv"
            df.to_csv(month_file, index=False)
            logger.info(f"    -> {len(df):,} candles ({elapsed:.0f}s)")
            all_candles.extend(month_candles)
        else:
            logger.info(f"    -> No data ({elapsed:.0f}s)")

        current_date = month_end

    if all_candles:
        df_all = pd.DataFrame(all_candles)
        df_all = df_all.sort_values('time').drop_duplicates(subset=['time'])
        combined = OUTPUT_DIR / f"{symbol}_M1_combined.csv"
        df_all.to_csv(combined, index=False)
        logger.info(f"\n{symbol} COMPLETE: {len(df_all):,} M1 candles")
        logger.info(f"  Range: {df_all['time'].min()} to {df_all['time'].max()}")

        # Aggregate
        logger.info(f"Aggregating {symbol}...")
        aggregate_m1(df_all, symbol, OUTPUT_DIR)
        return combined
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str)
    parser.add_argument('--start', type=str, default='2023-01-01')
    parser.add_argument('--end', type=str, default='2026-02-10')
    args = parser.parse_args()

    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    symbols = [args.symbol] if args.symbol else ['GOLD', 'USA500']

    for symbol in symbols:
        logger.info(f"\n{'='*60}")
        logger.info(f"DOWNLOADING: {symbol}")
        logger.info(f"{'='*60}")
        download_symbol(symbol, start, end)
        logger.info(f"{symbol} DONE\n")


if __name__ == "__main__":
    main()
