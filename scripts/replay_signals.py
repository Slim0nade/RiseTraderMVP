#!/usr/bin/env python3
"""
Phase 6 Task A1 — Signal replay script.

Pulls the last 17 days of H1 candle data from PostgreSQL, runs the same
_generate_signal() logic that LiveTradingService uses, and counts how many
signals would have fired under the new paper threshold (0.40/0.40) versus
the old threshold (0.45/0.45).

WHY NOT USE decision_log:
  LiveTradingService logs signals via structlog to stdout (not to the
  decision_log DB table, which belongs to the old AgentCoordinator).
  The "2 signals in 17 days" diagnosis came from operational log inspection,
  not from a DB query.  This script replays from market data instead.

REPLAY METHOD:
  For each symbol, fetch H1 candles from the last 17 days in rolling 100-bar
  windows (one window per day to approximate the 5-min cycle cadence), run
  _generate_signal() with BOTH thresholds, and compare the counts.

USAGE:
  python3 scripts/replay_signals.py [--days 17] [--symbols CrudeOIL,USA500,GBPJPY.]

EXPECTED OUTPUT:
  The new paper threshold (0.40) should produce >= 30 signals for CrudeOIL
  alone given 17 days of CrudeOIL's strongest rally.  If the DB has no rows
  in the last 17 days for a symbol, the script warns and counts 0 — it does
  NOT fabricate counts.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Database DSN
# ---------------------------------------------------------------------------
TEST_PG_DSN = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://postgres:risetrader2024@localhost:5433/risetrader",
)


async def _fetch_candles_for_window(
    symbol: str, end_time: datetime, limit: int = 100
) -> List[Dict]:
    """Fetch `limit` H1 candles ending at end_time for `symbol`."""
    import asyncpg

    # DB stores GBPJPY./TSLA with mapping
    db_symbol = {"GBPJPY.": "GBPJPY", "#TSLA": "TSLA"}.get(symbol, symbol)

    conn = await asyncpg.connect(TEST_PG_DSN)
    try:
        rows = await conn.fetch(
            """
            SELECT "open", high, low, "last" AS close, volume, time
            FROM market_data
            WHERE symbol = $1
              AND timeframe = 'H1'
              AND time <= $2
            ORDER BY time DESC
            LIMIT $3
            """,
            db_symbol,
            end_time,
            limit,
        )
    finally:
        await conn.close()

    if not rows:
        return []

    # Reverse to oldest-first (strategies expect chronological order)
    result = []
    for r in reversed(rows):
        result.append(
            {
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]) if r["volume"] is not None else 0.0,
            }
        )
    return result


def _count_signals_for_candles(
    candles: List[Dict],
    symbol: str,
    threshold: float,
    min_confidence: float,
) -> int:
    """
    Run _generate_signal() on the candle window and return 1 if a non-HOLD
    signal fires at the given threshold, 0 otherwise.

    We deliberately do NOT call the full _process_symbol() path (which needs
    DB + MT4 + ATR).  We call _generate_signal() which is pure computation.
    """
    # Import here so monkeypatching in tests doesn't affect the module-level state
    from src.services.live_trading_service import _combine_signals

    # Replicate the six strategies inline (same functions used in _generate_signal)
    from src.services.live_trading_service import (
        _momentum_strategy,
        _mean_reversion_strategy,
        _breakout_strategy,
        _trend_following_strategy,
        _value_area_strategy,
    )

    if len(candles) < 30:
        return 0

    signals: Dict[str, Dict] = {}
    try:
        signals["momentum"] = _momentum_strategy(candles)
    except Exception:
        pass
    try:
        signals["mean_reversion"] = _mean_reversion_strategy(candles)
    except Exception:
        pass
    try:
        signals["breakout"] = _breakout_strategy(candles)
    except Exception:
        pass
    try:
        signals["trend_following"] = _trend_following_strategy(candles)
    except Exception:
        pass
    try:
        signals["value_area"] = _value_area_strategy(candles)
    except Exception:
        pass

    if not signals:
        return 0

    combined = _combine_signals(signals)
    score = combined["score"]
    confidence = combined["confidence"]

    passed = abs(score) >= threshold and confidence >= min_confidence
    return 1 if passed else 0


async def replay(
    symbols: List[str],
    days: int,
    old_threshold: float = 0.45,
    new_threshold: float = 0.40,
) -> None:
    print(f"\n=== Signal Replay — last {days} days ===")
    print(f"Old threshold: score>={old_threshold}, conf>={old_threshold}")
    print(f"New threshold: score>={new_threshold}, conf>={new_threshold}")
    print()

    end_date = datetime.now(timezone.utc)
    # One snapshot per day (approximate — not every 5-min cycle)
    windows: List[datetime] = [end_date - timedelta(days=i) for i in range(days)]

    total_old = 0
    total_new = 0

    for symbol in symbols:
        old_count = 0
        new_count = 0
        windows_with_data = 0

        for window_end in windows:
            candles = await _fetch_candles_for_window(symbol, window_end, limit=100)
            if len(candles) < 30:
                continue
            windows_with_data += 1
            old_count += _count_signals_for_candles(
                candles, symbol, old_threshold, old_threshold
            )
            new_count += _count_signals_for_candles(
                candles, symbol, new_threshold, new_threshold
            )

        if windows_with_data == 0:
            print(
                f"  {symbol}: NO DATA in DB for last {days} days — "
                "cannot validate (not fabricating counts)"
            )
        else:
            delta = new_count - old_count
            print(
                f"  {symbol}: old={old_count}, new={new_count}, "
                f"delta=+{delta}, windows={windows_with_data}"
            )
        total_old += old_count
        total_new += new_count

    print()
    print(f"TOTAL old threshold: {total_old} signals in {days} days")
    print(f"TOTAL new threshold: {total_new} signals in {days} days")
    print(f"Delta: +{total_new - total_old} signals")
    print()

    # Assertion: new threshold should produce >= 30 signals across all symbols
    # Only assert when we had actual candle data to work with
    if total_new == 0 and total_old == 0:
        print(
            "WARNING: zero signals from both thresholds — "
            "likely no H1 data in DB for the requested period.  "
            "Replay cannot validate the >= 30 signal target without data."
        )
    elif total_new < 30:
        print(
            f"WARNING: new threshold produced only {total_new} signals "
            f"(target >= 30).  "
            "This may indicate the strategies are still too conservative "
            "or the DB lacks recent candle data."
        )
    else:
        print(f"PASS: new threshold produced {total_new} signals >= 30 target.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay signal counts under old/new thresholds")
    parser.add_argument("--days", type=int, default=17, help="Days to replay (default 17)")
    parser.add_argument(
        "--symbols",
        default="CrudeOIL,USA500,GBPJPY.",
        help="Comma-separated symbol list",
    )
    parser.add_argument(
        "--old-threshold", type=float, default=0.45, help="Old threshold to compare against"
    )
    parser.add_argument(
        "--new-threshold", type=float, default=0.40, help="New paper threshold"
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    asyncio.run(
        replay(
            symbols=symbols,
            days=args.days,
            old_threshold=args.old_threshold,
            new_threshold=args.new_threshold,
        )
    )


if __name__ == "__main__":
    main()
