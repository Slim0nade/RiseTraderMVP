#!/usr/bin/env python3.12
"""
Dukascopy downloader v3 - fully sequential, resumable, no threading.
Fixes thread deadlock issues from v2.

Usage (from RiseTraderMVP root):
    python3.12 scripts/download_dukascopy_v3.py --symbol GOLD --start 2023-01-01 --end 2026-02-10
    python3.12 scripts/download_dukascopy_v3.py --symbol USA500 --start 2023-01-01 --end 2026-02-10
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
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Suppress SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SYMBOLS = {
    'GOLD': {'dk': 'XAUUSD', 'point': 0.001},
    'USA500': {'dk': 'USA500IDXUSD', 'point': 0.001},
    'CrudeOIL': {'dk': 'LIGHTCMDUSD', 'point': 0.001},
}

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "downloads" / "dukascopy"


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


def download_hour(session: requests.Session, dk_symbol: str, dt: datetime, point_value: float) -> list:
    """Download one hour of data - sequential, with retries."""
    month_0idx = dt.month - 1
    url = f"{BASE_URL}/{dk_symbol}/{dt.year}/{month_0idx:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 0:
                ticks = parse_bi5(resp.content, point_value)
                return ticks_to_m1(ticks, dt)
            return []
        except requests.exceptions.Timeout:
            if attempt < 2:
                time.sleep(1)
                continue
            return []
        except Exception:
            if attempt < 2:
                time.sleep(0.5)
                continue
            return []
    return []


def download_day_sequential(session: requests.Session, dk_symbol: str, day: date, point_value: float) -> list:
    """Download all 24 hours for a day - SEQUENTIAL, no threading."""
    candles = []
    for hour in range(24):
        dt = datetime(day.year, day.month, day.day, hour)
        hour_candles = download_hour(session, dk_symbol, dt, point_value)
        candles.extend(hour_candles)
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
    """Download full M1 data for a symbol with resume support."""
    config = SYMBOLS[symbol]
    dk_symbol = config['dk']
    point_value = config['point']
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_days = (end_date - start_date).days
    logger.info(f"Downloading {symbol} ({dk_symbol}) from {start_date} to {end_date} ({total_days} days)")

    # Create a fresh session for each symbol
    session = requests.Session()
    session.verify = False
    session.headers.update({'User-Agent': 'Mozilla/5.0'})

    all_candles = []
    current_date = start_date
    skipped_months = 0

    while current_date < end_date:
        # Monthly chunks
        month_end = date(
            current_date.year + (1 if current_date.month == 12 else 0),
            (current_date.month % 12) + 1, 1
        )
        month_end = min(month_end, end_date)

        # Check if this month's file already exists (resume support)
        month_file = OUTPUT_DIR / f"{symbol}_M1_{current_date.strftime('%Y_%m')}.csv"
        if month_file.exists() and month_file.stat().st_size > 100:
            logger.info(f"  {symbol} | {current_date.strftime('%Y-%m')} | SKIPPED (already downloaded)")
            # Load existing data
            existing = pd.read_csv(month_file)
            all_candles.extend(existing.to_dict('records'))
            skipped_months += 1
            current_date = month_end
            continue

        days_in_chunk = (month_end - current_date).days
        logger.info(f"  {symbol} | {current_date.strftime('%Y-%m')} | {days_in_chunk} days...")
        t0 = time.time()
        month_candles = []
        days_downloaded = 0

        for day_offset in range(days_in_chunk):
            day = current_date + timedelta(days=day_offset)
            if day.weekday() >= 5:
                continue
            day_candles = download_day_sequential(session, dk_symbol, day, point_value)
            month_candles.extend(day_candles)
            days_downloaded += 1
            # Progress indicator
            if days_downloaded % 5 == 0:
                print(f"    day {days_downloaded}...", file=sys.stderr, flush=True)

        elapsed = time.time() - t0

        if month_candles:
            df = pd.DataFrame(month_candles)
            df = df.sort_values('time').drop_duplicates(subset=['time'])
            df.to_csv(month_file, index=False)
            logger.info(f"    -> {len(df):,} candles ({elapsed:.0f}s) [saved: {month_file.name}]")
            all_candles.extend(month_candles)
        else:
            logger.info(f"    -> No data ({elapsed:.0f}s)")

        current_date = month_end
        sys.stderr.flush()

    session.close()

    if all_candles:
        df_all = pd.DataFrame(all_candles)
        df_all = df_all.sort_values('time').drop_duplicates(subset=['time'])
        combined = OUTPUT_DIR / f"{symbol}_M1_combined.csv"
        df_all.to_csv(combined, index=False)
        logger.info(f"\n{symbol} COMPLETE: {len(df_all):,} M1 candles")
        logger.info(f"  Range: {df_all['time'].min()} to {df_all['time'].max()}")

        logger.info(f"Aggregating {symbol} to M5/M30/H1...")
        aggregate_m1(df_all, symbol, OUTPUT_DIR)
        logger.info(f"{symbol} ALL DONE! (skipped {skipped_months} already-downloaded months)")
        return combined
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, help='GOLD, USA500, or CrudeOIL')
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
