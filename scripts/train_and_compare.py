#!/usr/bin/env python3
"""
ML Model Training & Comparison Pipeline for RiseTrader.

Thin CLI wrapper around ReversalTrainingService.

Usage:
    python scripts/train_and_compare.py --symbols CrudeOIL,XAUUSD --timeframes H1
    python scripts/train_and_compare.py --symbols all --timeframes H1,M30
    python scripts/train_and_compare.py --symbols CrudeOIL --timeframes H1 --skip-indicators
    python scripts/train_and_compare.py --symbols CrudeOIL --timeframes H1 --configs LSTM-default
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.config import initialize_database, get_database
from src.services.reversal_training_service import (
    ReversalTrainingService,
    DEFAULT_MODEL_CONFIGS,
)
from src.services.indicator_compute_service import ALL_SYMBOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_comparison_table(all_model_results: List[dict]) -> None:
    """Print a formatted comparison table of all model results."""
    print("\n" + "=" * 110)
    print("MODEL COMPARISON RESULTS")
    print("=" * 110)

    header = (
        f"{'Symbol':<12} {'TF':<5} {'Model':<20} {'Status':<8} "
        f"{'Rev F1':>8} {'Peak F1':>8} {'Valley F1':>10} "
        f"{'Macro F1':>9} {'Time':>7}"
    )
    print(header)
    print("-" * 110)

    current_group = None
    for r in all_model_results:
        group = (r["symbol"], r["timeframe"])
        if group != current_group:
            if current_group is not None:
                print("-" * 110)
            current_group = group

        status = r["status"]
        rev_f1 = f"{r['reversal_f1']:.3f}" if status == "success" else "N/A"
        peak_f1 = f"{r['peak_f1']:.3f}" if status == "success" else "N/A"
        valley_f1 = f"{r['valley_f1']:.3f}" if status == "success" else "N/A"
        macro_f1 = f"{r['macro_f1']:.3f}" if status == "success" else "N/A"
        elapsed = f"{r['elapsed_seconds']:.0f}s"

        line = (
            f"{r['symbol']:<12} {r['timeframe']:<5} {r['model_name']:<20} {status:<8} "
            f"{rev_f1:>8} {peak_f1:>8} {valley_f1:>10} "
            f"{macro_f1:>9} {elapsed:>7}"
        )
        print(line)

    print("=" * 110)

    # Best per symbol/timeframe
    print("\nBEST MODELS (by Reversal F1):")
    print("-" * 60)
    groups = {}
    for r in all_model_results:
        if r["status"] != "success":
            continue
        key = (r["symbol"], r["timeframe"])
        if key not in groups or r["reversal_f1"] > groups[key]["reversal_f1"]:
            groups[key] = r

    for (sym, tf), best in sorted(groups.items()):
        print(f"  {sym} {tf}: {best['model_name']} (F1={best['reversal_f1']:.3f})")


async def main(
    symbols: List[str],
    timeframes: List[str],
    skip_indicators: bool = False,
    skip_labels: bool = False,
    configs: Optional[List[str]] = None,
):
    """Main pipeline entry point."""
    logger.info("=" * 60)
    logger.info("RiseTrader ML Training & Comparison Pipeline")
    logger.info("=" * 60)
    logger.info(f"Symbols: {symbols}")
    logger.info(f"Timeframes: {timeframes}")

    initialize_database()
    db = get_database()

    # Filter model configs if specified
    active_configs = DEFAULT_MODEL_CONFIGS
    if configs:
        active_configs = [c for c in DEFAULT_MODEL_CONFIGS if c["name"] in configs]
        if not active_configs:
            logger.error(f"No matching configs found for: {configs}")
            return

    all_model_results = []

    for timeframe in timeframes:
        for symbol in symbols:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing {symbol} {timeframe}")
            logger.info(f"{'='*60}")

            async with db.get_session() as session:
                service = ReversalTrainingService(session)
                result = await service.train_pipeline(
                    symbol=symbol,
                    timeframe=timeframe,
                    skip_indicators=skip_indicators,
                    skip_labels=skip_labels,
                    model_configs=active_configs,
                )

            if result.get("best_model_dir"):
                print(f"\nBest model saved to: {result['best_model_dir']}")

            all_model_results.extend(result.get("model_results", []))

    # Print comparison table
    if all_model_results:
        print_comparison_table(all_model_results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ML model training and comparison pipeline"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="CrudeOIL",
        help="Comma-separated symbols or 'all' (default: CrudeOIL)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="H1",
        help="Comma-separated timeframes (default: H1)",
    )
    parser.add_argument(
        "--skip-indicators",
        action="store_true",
        help="Skip indicator computation (assume already computed)",
    )
    parser.add_argument(
        "--skip-labels",
        action="store_true",
        help="Skip ZigZag labeling (assume already labeled)",
    )
    parser.add_argument(
        "--configs",
        type=str,
        default=None,
        help="Comma-separated config names to run (default: all). "
             "Options: XGB-default,XGB-aggressive,XGB-conservative,LSTM-default",
    )

    args = parser.parse_args()

    symbols = ALL_SYMBOLS if args.symbols.lower() == "all" else [s.strip() for s in args.symbols.split(",")]
    timeframes = [t.strip() for t in args.timeframes.split(",")]
    configs = [c.strip() for c in args.configs.split(",")] if args.configs else None

    asyncio.run(main(symbols, timeframes, args.skip_indicators, args.skip_labels, configs))
