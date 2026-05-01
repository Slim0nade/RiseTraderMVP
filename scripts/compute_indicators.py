#!/usr/bin/env python3
"""
Compute Technical Indicators from market_data → indicators table.

Thin CLI wrapper around IndicatorComputeService.

Usage:
    python scripts/compute_indicators.py --symbols CrudeOIL,XAUUSD --timeframes H1
    python scripts/compute_indicators.py --symbols all --timeframes H1,M30
    python scripts/compute_indicators.py --symbols CrudeOIL --timeframes H1 --force
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.config import initialize_database, get_database
from src.services.indicator_compute_service import (
    IndicatorComputeService,
    ALL_SYMBOLS,
    compute_indicators_df,  # Re-export for backwards compatibility
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def compute_for_symbol(symbol: str, timeframe: str, force: bool = False):
    """
    Backwards-compatible wrapper used by train_and_compare.py.
    """
    db = get_database()
    async with db.get_session() as session:
        service = IndicatorComputeService(session)
        return await service.compute_for_symbol(symbol, timeframe, force=force)


async def main(symbols: List[str], timeframes: List[str], force: bool = False):
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("RiseTrader Indicator Computation")
    logger.info("=" * 60)

    initialize_database()
    db = get_database()

    async with db.get_session() as session:
        service = IndicatorComputeService(session)
        results = await service.compute_batch(symbols, timeframes, force=force)

    # Print summary
    print("\n" + "=" * 70)
    print("INDICATOR COMPUTATION SUMMARY")
    print("=" * 70)
    print(f"{'Symbol':<12} {'TF':<5} {'Status':<12} {'Candles':>8} {'Upserted':>10}")
    print("-" * 70)
    for r in results:
        status = r["status"]
        candles = r.get("candles", r.get("existing", 0))
        upserted = r.get("upserted", 0)
        print(f"{r['symbol']:<12} {r['timeframe']:<5} {status:<12} {candles:>8} {upserted:>10}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute technical indicators for market data")
    parser.add_argument(
        "--symbols",
        type=str,
        default="all",
        help="Comma-separated symbols or 'all' (default: all)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="H1",
        help="Comma-separated timeframes (default: H1)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute even if indicators already exist",
    )

    args = parser.parse_args()

    symbols = ALL_SYMBOLS if args.symbols.lower() == "all" else [s.strip() for s in args.symbols.split(",")]
    timeframes = [t.strip() for t in args.timeframes.split(",")]

    asyncio.run(main(symbols, timeframes, force=args.force))
