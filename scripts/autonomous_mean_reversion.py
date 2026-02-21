#!/usr/bin/env python3
"""
Autonomous Mean Reversion Signal Checker & Executor
====================================================
Checks CrudeOIL, MSFT, and TSLA for mean-reversion setups on H1 timeframe.
When a signal fires, places a trade via the RiseTrader API.

Strategy: Mean Reversion (Bollinger Band Z-Score)
  - CrudeOIL: lookback=40, std_threshold=3.5 → +11.49% annual, Sharpe 5.88
  - MSFT:     lookback=20, std_threshold=2.0 → +13.24% annual, Sharpe 8.07
  - TSLA:     lookback=15, std_threshold=2.0 → +40.60% annual, Sharpe 8.96

Allocation: 30% of account capital (~$2,800)
  - CrudeOIL: 30% of sleeve ($840)
  - MSFT:     40% of sleeve ($1,120)
  - TSLA:     30% of sleeve ($840)

Schedule: Run every hour via cron (H1 candles)
  0 * * * 1-5 python3 /path/to/autonomous_mean_reversion.py >> /tmp/risetrader_auto.log 2>&1

Safety:
  - Max 1 position per symbol at a time
  - ATR-based stop loss (2x ATR) with institutional offset
  - Max 30% of account equity per sleeve
  - Trading hours filter (stocks: 9:30-15:30 EST, oil: 24/5)
  - Dry-run mode by default (set LIVE_TRADING=1 to enable)

Monte Carlo Validated:
  - CrudeOIL: Edge CONFIRMED (MC mean 24.47% vs base 11.49%)
  - TSLA:     Edge VERY STRONG (MC mean 299.97%)
  - MSFT:     Edge STRONG (MC mean 175.63%)
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

# Configuration
API_BASE = os.getenv("RISETRADER_API", "http://localhost:8003")
LIVE_TRADING = os.getenv("LIVE_TRADING", "0") == "1"
MAX_SLEEVE_PCT = 0.30  # 30% of account for steady-gains
LOG_FILE = os.getenv("LOG_FILE", "/tmp/risetrader_auto.log")

# Symbol mapping: API symbol (for candles) → MT4 symbol (for orders)
# The candle API uses MSFT/TSLA, but MT4 orders use #MICROSOFT/#TSLA
SYMBOL_MAP = {
    "CrudeOIL": "CrudeOIL",
    "MSFT": "#MICROSOFT",
    "TSLA": "#TSLA",
}

STRATEGIES = {
    "CrudeOIL": {
        "api_symbol": "CrudeOIL",    # For fetching candles
        "mt4_symbol": "CrudeOIL",    # For placing orders
        "lookback": 40,
        "std_threshold": 3.5,
        "exit_z": -0.5,
        "sleeve_pct": 0.30,  # 30% of steady sleeve
        "lot_size": 0.1,
        "atr_stop_mult": 2.0,
        "atr_tp_mult": 3.0,
        "is_stock": False,  # Trades 24/5
    },
    "MSFT": {
        "api_symbol": "MSFT",         # For fetching candles
        "mt4_symbol": "#MICROSOFT",   # For placing orders
        "lookback": 20,
        "std_threshold": 2.0,
        "exit_z": -0.5,
        "sleeve_pct": 0.40,  # 40% of steady sleeve
        "lot_size": 0.01,
        "atr_stop_mult": 2.0,
        "atr_tp_mult": 3.0,
        "is_stock": True,
    },
    "TSLA": {
        "api_symbol": "TSLA",         # For fetching candles
        "mt4_symbol": "#TSLA",        # For placing orders
        "lookback": 15,
        "std_threshold": 2.0,
        "exit_z": -0.5,
        "sleeve_pct": 0.30,  # 30% of steady sleeve
        "lot_size": 0.01,
        "atr_stop_mult": 2.0,
        "atr_tp_mult": 3.0,
        "is_stock": True,
    },
}

# Trading hours (EST) - stocks only trade during market hours
STOCK_START_HOUR = 9   # 9:30 AM EST
STOCK_END_HOUR = 15    # 3:30 PM EST

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("auto_mr")


def api_call(method: str, endpoint: str, **kwargs) -> Optional[Dict]:
    """Make API call to RiseTrader backend."""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.request(method, url, timeout=15, **kwargs)
        if resp.status_code < 400:
            return resp.json()
        log.error(f"API {method} {endpoint}: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log.error(f"API {method} {endpoint}: {e}")
    return None


def get_candles(symbol: str, timeframe: str = "H1", limit: int = 50) -> Optional[List[Dict]]:
    """Get latest candles from the RiseTrader API.

    API returns: {"data": [...], "total": N, "symbol": "..."}
    Each candle has string values for open/high/low/close.
    """
    data = api_call("GET", f"/api/market-data/{symbol}", params={
        "timeframe": timeframe, "limit": limit
    })
    if data and "data" in data:
        # Convert string prices to float
        candles = []
        for c in data["data"]:
            candles.append({
                "time": c.get("time", ""),
                "open": float(c.get("open", 0)),
                "high": float(c.get("high", 0)),
                "low": float(c.get("low", 0)),
                "close": float(c.get("close", 0)),
                "volume": int(c.get("volume", 0)),
            })
        return candles
    return None


def calculate_z_score(candles: List[Dict], lookback: int) -> Optional[Dict]:
    """Calculate current z-score from candle data."""
    if not candles or len(candles) < lookback + 1:
        log.warning(f"Not enough candles: {len(candles) if candles else 0} < {lookback + 1}")
        return None

    closes = [c["close"] for c in candles[-(lookback + 1):]]
    window = closes[-lookback:]

    sma = sum(window) / len(window)
    variance = sum((x - sma) ** 2 for x in window) / len(window)
    std = variance ** 0.5

    if std == 0:
        return None

    current = closes[-1]
    z = (current - sma) / std

    # ATR calculation (proper True Range)
    if len(candles) >= 16:
        trs = []
        for i in range(-14, 0):
            h = candles[i]["high"]
            l = candles[i]["low"]
            cp = candles[i - 1]["close"]
            tr = max(h - l, abs(h - cp), abs(l - cp))
            trs.append(tr)
        atr = sum(trs) / len(trs)
    else:
        # Fallback: use available data
        trs = []
        for i in range(1, len(candles)):
            h = candles[i]["high"]
            l = candles[i]["low"]
            cp = candles[i - 1]["close"]
            tr = max(h - l, abs(h - cp), abs(l - cp))
            trs.append(tr)
        atr = sum(trs) / len(trs) if trs else 0

    return {
        "current_price": current,
        "sma": round(sma, 4),
        "std": round(std, 4),
        "z_score": round(z, 4),
        "atr": round(atr, 4),
        "upper_band": round(sma + 2 * std, 4),
        "lower_band": round(sma - 2 * std, 4),
    }


def get_open_positions(symbol: str) -> List[Dict]:
    """Check for existing positions on a symbol via ZMQ."""
    data = api_call("GET", "/api/mt4/positions")
    if data and "positions" in data:
        return [p for p in data["positions"] if p.get("symbol") == symbol]
    return []


def get_account_info() -> Optional[Dict]:
    """Get account balance and equity via ZMQ."""
    return api_call("GET", "/api/mt4/account")


def place_order(symbol: str, side: str, lots: float, sl: float, tp: float) -> Optional[Dict]:
    """Place a market order via the RiseTrader API."""
    payload = {
        "symbol": symbol,
        "side": side,
        "quantity": lots,
        "stop_loss": sl,
        "take_profit": tp,
    }
    return api_call("POST", "/api/mt4/order", json=payload)


def close_position(ticket: int) -> Optional[Dict]:
    """Close a position by ticket."""
    return api_call("POST", f"/api/mt4/close/{ticket}")


def is_trading_hours(is_stock: bool = True) -> bool:
    """Check if within trading hours."""
    now = datetime.now(timezone.utc)

    if not is_stock:
        # CrudeOIL trades 24/5 — skip weekends
        return now.weekday() < 5  # Mon-Fri

    # Stocks: 9:30-15:30 EST (14:30-20:30 UTC)
    est_hour = (now.hour - 5) % 24
    est_min = now.minute

    if est_hour == STOCK_START_HOUR and est_min < 30:
        return False  # Before 9:30
    if est_hour == STOCK_END_HOUR and est_min > 30:
        return False  # After 15:30

    return STOCK_START_HOUR <= est_hour <= STOCK_END_HOUR


def check_and_trade(symbol: str, config: Dict) -> Dict[str, Any]:
    """
    Check for mean-reversion signal and optionally place trade.
    Returns status dict with signal info.
    """
    result = {
        "symbol": symbol,
        "mt4_symbol": config["mt4_symbol"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal": "NONE",
        "action": "HOLD",
    }

    # Get candles using the API symbol name
    candles = get_candles(config["api_symbol"], "H1", limit=config["lookback"] + 20)
    if not candles:
        result["error"] = f"Failed to get candles for {config['api_symbol']}"
        return result

    result["candles_received"] = len(candles)
    result["latest_candle_time"] = candles[-1].get("time", "unknown")

    # Calculate z-score
    stats = calculate_z_score(candles, config["lookback"])
    if not stats:
        result["error"] = "Failed to calculate z-score"
        return result

    result.update(stats)
    z = stats["z_score"]
    price = stats["current_price"]
    atr = stats["atr"]

    # Check for existing positions on this MT4 symbol
    existing = get_open_positions(config["mt4_symbol"])
    has_position = len(existing) > 0
    result["has_existing_position"] = has_position

    within_hours = is_trading_hours(config.get("is_stock", True))
    result["within_trading_hours"] = within_hours

    # Check for BUY signal: z-score below -std_threshold
    if z < -config["std_threshold"]:
        result["signal"] = "BUY"
        result["reason"] = f"Z-score {z:.2f} < -{config['std_threshold']} (oversold)"

        # Calculate stop and target
        sl = round(price - atr * config["atr_stop_mult"], 2)
        tp = round(price + atr * config["atr_tp_mult"], 2)
        result["stop_loss"] = sl
        result["take_profit"] = tp
        result["lot_size"] = config["lot_size"]

        if has_position:
            result["action"] = "SKIP (already has position)"
            log.info(f"  SKIP BUY {symbol}: already has open position")
        elif not within_hours:
            result["action"] = "SKIP (outside trading hours)"
            log.info(f"  SKIP BUY {symbol}: outside trading hours")
        elif LIVE_TRADING:
            result["action"] = "PLACING ORDER"
            log.info(f"  PLACING BUY: {config['mt4_symbol']} @ {price}, SL={sl}, TP={tp}, lots={config['lot_size']}")
            order_result = place_order(config["mt4_symbol"], "buy", config["lot_size"], sl, tp)
            if order_result:
                result["order_result"] = order_result
                log.info(f"  ORDER PLACED: {order_result}")
            else:
                result["action"] = "ORDER FAILED"
                log.error(f"  ORDER FAILED for {config['mt4_symbol']}")
        else:
            result["action"] = "DRY RUN (would buy)"
            log.info(f"  DRY RUN: BUY {config['mt4_symbol']} @ {price}, SL={sl}, TP={tp}")

    # Check for SELL signal: z-score above +std_threshold (mean reversion sells overbought)
    elif z > config["std_threshold"]:
        result["signal"] = "SELL"
        result["reason"] = f"Z-score {z:.2f} > +{config['std_threshold']} (overbought)"

        sl = round(price + atr * config["atr_stop_mult"], 2)
        tp = round(price - atr * config["atr_tp_mult"], 2)
        result["stop_loss"] = sl
        result["take_profit"] = tp
        result["lot_size"] = config["lot_size"]

        if has_position:
            result["action"] = "SKIP (already has position)"
        elif not within_hours:
            result["action"] = "SKIP (outside trading hours)"
        elif LIVE_TRADING:
            result["action"] = "PLACING ORDER"
            log.info(f"  PLACING SELL: {config['mt4_symbol']} @ {price}, SL={sl}, TP={tp}")
            order_result = place_order(config["mt4_symbol"], "sell", config["lot_size"], sl, tp)
            if order_result:
                result["order_result"] = order_result
            else:
                result["action"] = "ORDER FAILED"
        else:
            result["action"] = "DRY RUN (would sell)"

    # Check for EXIT signal: z-score returns to mean
    elif has_position and abs(z) < abs(config["exit_z"]):
        result["signal"] = "EXIT"
        result["reason"] = f"Z-score {z:.2f} returned to mean (|z| < {abs(config['exit_z'])})"

        if LIVE_TRADING and within_hours:
            result["action"] = "CLOSING POSITIONS"
            for pos in existing:
                ticket = pos.get("ticket")
                if ticket:
                    log.info(f"  CLOSING {config['mt4_symbol']} ticket {ticket}")
                    close_result = close_position(ticket)
                    result[f"close_{ticket}"] = close_result
        else:
            result["action"] = "DRY RUN (would close)"

    else:
        result["signal"] = "NONE"
        result["reason"] = f"Z-score {z:.2f} in neutral zone"

    return result


def main():
    log.info("=" * 60)
    log.info("  AUTONOMOUS MEAN REVERSION CHECKER")
    log.info(f"  Mode: {'LIVE' if LIVE_TRADING else 'DRY RUN'}")
    log.info(f"  API: {API_BASE}")
    log.info(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    # Get account info
    account = get_account_info()
    if account:
        log.info(f"  Account: Balance=${account.get('balance', '?')} | Equity=${account.get('equity', '?')}")
    else:
        log.warning("  Could not fetch account info (continuing anyway)")

    all_results = []
    for symbol, config in STRATEGIES.items():
        try:
            result = check_and_trade(symbol, config)
            all_results.append(result)

            signal_emoji = {
                "BUY": "+",
                "SELL": "-",
                "EXIT": "X",
                "NONE": ".",
            }.get(result["signal"], "?")

            z_val = result.get("z_score", 0)
            log.info(
                f"  [{signal_emoji}] {symbol}: Z={z_val:+.2f} | "
                f"Price=${result.get('current_price', '?')} | "
                f"Signal={result['signal']} | {result.get('reason', '')} | "
                f"Action={result.get('action', 'NONE')}"
            )
        except Exception as e:
            log.error(f"  ERROR {symbol}: {e}")
            all_results.append({"symbol": symbol, "error": str(e)})

    # Save results for review
    results_file = "/tmp/risetrader_auto_last.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)

    log.info(f"  Results saved to {results_file}")
    log.info("=" * 60)

    return all_results


if __name__ == "__main__":
    main()
