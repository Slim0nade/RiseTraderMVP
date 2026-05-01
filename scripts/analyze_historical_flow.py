"""
Historical Informed Flow Analyzer

Scans the 13.5M candle database for price velocity anomalies
and generates a report of detected events.

Usage:
    python scripts/analyze_historical_flow.py --symbol CrudeOIL --start 2024-01-01 --end 2024-12-31
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector
from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector


async def fetch_candles(symbol: str, start: str, end: str, timeframe: str = "M1") -> List[Dict]:
    """Fetch candles from database.

    Args:
        symbol: MT4 symbol string (e.g. 'CrudeOIL').
        start: ISO date string 'YYYY-MM-DD' for the range start (inclusive).
        end: ISO date string 'YYYY-MM-DD' for the range end (inclusive).
        timeframe: DB timeframe ENUM value — must be uppercase ('M1', 'H1', etc.).

    Returns:
        Oldest-first list of candle dicts with keys:
        'time', 'open', 'high', 'low', 'close', 'volume'.
        'volume' is 0.0 for rows where the DB field is NULL.

    Edge cases:
        - Returns an empty list if no rows match the query.
        - 'last' column is aliased to 'close' to match detector API.
    """
    from src.api.dependencies import get_db_context
    from sqlalchemy import text as sa_text

    async with get_db_context() as db:
        result = await db.execute(
            sa_text("""
                SELECT time, open, high, low, last as close, volume
                FROM market_data
                WHERE symbol = :symbol
                  AND CAST(timeframe AS TEXT) = :tf
                  AND time >= :start_time
                  AND time <= :end_time
                ORDER BY time ASC
            """),
            {
                "symbol": symbol,
                "tf": timeframe,
                "start_time": start,
                "end_time": end,
            }
        )
        rows = result.fetchall()

    return [{
        "time": str(row[0]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]) if row[5] else 0.0,
    } for row in rows]


async def analyze(symbol: str, start: str, end: str, output: str) -> None:
    """Main analysis loop.

    Runs a sliding window over all fetched candles, feeding each position
    to both detectors. Events from both detectors are collected into a
    single list and written to the output JSON file.

    Args:
        symbol: MT4 symbol string (e.g. 'CrudeOIL').
        start: ISO date string 'YYYY-MM-DD' for the range start (inclusive).
        end: ISO date string 'YYYY-MM-DD' for the range end (inclusive).
        output: File path for the JSON report. Parent directories are created
            if they do not exist.

    Edge cases:
        - Fewer than 120 candles in the range: prints a message and returns
          without writing any output file.
        - window_size (120) must be <= baseline_window (60) + 1 to guarantee
          the detectors always receive enough history. With window_size=121
          candles passed to detect(), detectors receive 121 bars which exceeds
          their baseline_window=60 requirement.
    """
    print(f"Fetching {symbol} M1 candles from {start} to {end}...")
    candles = await fetch_candles(symbol, start, end)
    print(f"Loaded {len(candles)} candles")

    if len(candles) < 120:
        print("Insufficient data (need at least 120 candles)")
        return

    # Initialize detectors
    velocity_detector = PriceVelocityDetector(
        velocity_threshold_pct=0.3,  # Lower threshold for historical scan
        z_score_threshold=2.0,
    )
    tick_detector = TickClusteringDetector(
        burst_multiplier=3.0,
        min_absolute_ticks=100,  # Lower for historical (varied activity)
    )

    events = []
    window_size = 120  # 2 hours of M1 data for baseline

    total = len(candles) - window_size
    report_interval = max(1, total // 20)  # Report every 5%

    for i in range(window_size, len(candles)):
        window = candles[i - window_size:i + 1]

        # Progress bar
        progress = i - window_size
        if progress % report_interval == 0:
            pct = round(progress / total * 100)
            print(f"  Scanning... {pct}% ({progress}/{total})", end="\r")

        # Price velocity check
        velocity_alert = velocity_detector.detect(symbol, window)
        if velocity_alert:
            events.append({
                "type": "price_velocity",
                "timestamp": candles[i]["time"],
                "price": candles[i]["close"],
                "price_change_pct": round(velocity_alert.price_change_pct, 4),
                "z_score": round(velocity_alert.z_score, 2),
                "direction": velocity_alert.direction,
                "confidence": round(velocity_alert.confidence, 3),
            })

        # Tick clustering check
        cluster = tick_detector.analyze(window)
        if cluster.is_anomaly:
            events.append({
                "type": "tick_cluster",
                "timestamp": candles[i]["time"],
                "price": candles[i]["close"],
                "tick_count": cluster.tick_count,
                "tick_z_score": cluster.tick_z_score,
                "price_direction": cluster.price_direction,
                "confidence": round(cluster.confidence, 3),
            })

    print(f"\n\nAnalysis complete!")
    print(f"Events detected: {len(events)}")

    # Summary stats
    velocity_events = [e for e in events if e["type"] == "price_velocity"]
    cluster_events = [e for e in events if e["type"] == "tick_cluster"]

    print(f"  Price velocity alerts: {len(velocity_events)}")
    print(f"  Tick cluster alerts: {len(cluster_events)}")

    if velocity_events:
        avg_change = np.mean([abs(e["price_change_pct"]) for e in velocity_events])
        max_change = max([abs(e["price_change_pct"]) for e in velocity_events])
        print(f"  Avg price change: {avg_change:.3f}%")
        print(f"  Max price change: {max_change:.3f}%")

    # Build report
    report = {
        "symbol": symbol,
        "timeframe": "M1",
        "start": start,
        "end": end,
        "total_candles": len(candles),
        "total_events": len(events),
        "velocity_events": len(velocity_events),
        "cluster_events": len(cluster_events),
        "events": events,
    }

    # Save
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to {output}")


def main():
    parser = argparse.ArgumentParser(description="Historical Informed Flow Analyzer")
    parser.add_argument("--symbol", required=True, help="Trading symbol (e.g., CrudeOIL)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default="reports/flow_analysis.json", help="Output file path")
    args = parser.parse_args()

    asyncio.run(analyze(args.symbol, args.start, args.end, args.output))


if __name__ == "__main__":
    main()
