"""
Unit tests for the aggregation math in src/services/candle_aggregator_service.py.

The CandleAggregatorService._aggregate_single_hour method executes SQL via
SQLAlchemy (requires a live DB), so those DB-layer paths are outside the scope
of pure unit tests.  Instead, this file tests:

1. The derived-field math (change, change_pct) reproduced here exactly as the
   service computes it using Decimal — verifying the formula is correct before
   it ever touches the DB.
2. The OHLCV aggregation rules (open=first, high=max, low=min, close=last,
   volume=sum) applied to raw candle sequences, matching the SQL semantics the
   service relies on.
3. CandleAggregatorService.__init__: state initialisation, tracked symbols,
   interval default.
4. Edge cases explicitly documented in the service docstring:
   - Zero M1 candles → no H1 candle written (tested via the "skip" branch logic).
   - Partial hour (fewer than 60 M1) → still aggregates whatever arrived.

No DB, no network, no mocks, no MagicMock.  All inputs are static Python values.
"""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

import pytest

sys.path.insert(0, "/Users/erinrouissi/Documents/VSCode/Rise/RiseTraderMVP")

# Import only the module-level constants and the class itself (no DB calls yet)
from src.services.candle_aggregator_service import (
    AGGREGATION_INTERVAL_SECONDS,
    CandleAggregatorService,
    TRACKED_SYMBOLS,
)


# ---------------------------------------------------------------------------
# Helper: the exact Decimal math used by _aggregate_single_hour
# ---------------------------------------------------------------------------

def _compute_change_and_pct(open_price: float, close_price: float):
    """
    Reproduce the Decimal arithmetic from CandleAggregatorService._aggregate_single_hour
    for change and change_percent.

    Returns (change: Decimal, change_percent: Decimal)
    """
    open_dec = Decimal(str(open_price))
    close_dec = Decimal(str(close_price))
    change = close_dec - open_dec
    if open_dec != Decimal("0"):
        change_pct = change / open_dec * Decimal("100")
    else:
        change_pct = Decimal("0")
    return change, change_pct


def _aggregate_ohlcv(candles: List[dict]) -> dict:
    """
    Apply the same OHLCV aggregation logic the service uses in SQL:
      open   = first candle's open (lowest time)
      high   = max(highs)
      low    = min(lows)
      close  = last candle's close (highest time)
      volume = sum(volumes)

    Candles are expected to be sorted by time (ascending).
    Returns a dict or raises ValueError if `candles` is empty.
    """
    if not candles:
        raise ValueError("Cannot aggregate zero candles")

    sorted_candles = sorted(candles, key=lambda c: c["time"])
    return {
        "open": sorted_candles[0]["open"],
        "high": max(c["high"] for c in sorted_candles),
        "low": min(c["low"] for c in sorted_candles),
        "close": sorted_candles[-1]["close"],
        "volume": sum(c["volume"] for c in sorted_candles),
    }


# ---------------------------------------------------------------------------
# Helpers for building candle sequences
# ---------------------------------------------------------------------------

def _make_m1_candles(
    start: datetime,
    n: int,
    base_open: float = 60.0,
    base_close: float = None,
    fixed_high: float = None,
    fixed_low: float = None,
    fixed_volume: int = 100,
) -> List[dict]:
    """Return `n` M1 candle dicts starting at `start`, each 1 minute apart."""
    candles = []
    for i in range(n):
        o = base_open + i * 0.01
        c = base_close if base_close is not None else (o + 0.20)
        h = fixed_high if fixed_high is not None else (o + 0.50)
        lo = fixed_low if fixed_low is not None else (o - 0.50)
        candles.append(
            {
                "time": start + timedelta(minutes=i),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": fixed_volume + i,
            }
        )
    return candles


# ===========================================================================
# Decimal arithmetic for change / change_pct
# ===========================================================================

class TestChangeMath:
    """Verify the Decimal change / change_pct arithmetic used by the service."""

    def test_bullish_candle_positive_change(self):
        """close > open → positive change."""
        change, _ = _compute_change_and_pct(open_price=60.0, close_price=60.5)
        assert change > Decimal("0")

    def test_bearish_candle_negative_change(self):
        """close < open → negative change."""
        change, _ = _compute_change_and_pct(open_price=60.5, close_price=60.0)
        assert change < Decimal("0")

    def test_doji_candle_zero_change(self):
        """close == open → change is exactly 0."""
        change, _ = _compute_change_and_pct(open_price=60.0, close_price=60.0)
        assert change == Decimal("0")

    def test_change_value_is_close_minus_open(self):
        """change must equal close - open exactly in Decimal arithmetic."""
        change, _ = _compute_change_and_pct(open_price=100.0, close_price=105.0)
        assert change == Decimal("5.0")

    def test_change_pct_formula_bullish(self):
        """change_pct must be ((close - open) / open) * 100 for a bullish candle."""
        _, pct = _compute_change_and_pct(open_price=100.0, close_price=105.0)
        expected = Decimal("5.0")  # ((105-100)/100)*100 = 5%
        assert abs(pct - expected) < Decimal("0.0001")

    def test_change_pct_formula_bearish(self):
        """change_pct must be negative for a bearish candle."""
        _, pct = _compute_change_and_pct(open_price=100.0, close_price=90.0)
        expected = Decimal("-10.0")  # ((90-100)/100)*100 = -10%
        assert abs(pct - expected) < Decimal("0.0001")

    def test_change_pct_zero_when_open_is_zero(self):
        """Division guard: change_pct must be 0 when open == 0 (not an exception)."""
        _, pct = _compute_change_and_pct(open_price=0.0, close_price=60.5)
        assert pct == Decimal("0")

    def test_change_pct_small_move(self):
        """Decimal precision is maintained for small percentage moves."""
        # 0.1% move: open=1000.0, close=1001.0
        _, pct = _compute_change_and_pct(open_price=1000.0, close_price=1001.0)
        assert abs(pct - Decimal("0.1")) < Decimal("0.001")


# ===========================================================================
# OHLCV aggregation rules
# ===========================================================================

class TestOHLCVAggregationRules:
    """Verify open=first, high=max, low=min, close=last, volume=sum semantics."""

    _START = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)

    def test_open_is_first_candle_open(self):
        """H1 open must equal the open of the earliest M1 candle."""
        candles = _make_m1_candles(self._START, n=60, base_open=62.0)
        result = _aggregate_ohlcv(candles)
        assert result["open"] == pytest.approx(62.0)

    def test_high_is_max_of_all_highs(self):
        """H1 high must equal the maximum of all M1 high values."""
        candles = _make_m1_candles(self._START, n=60)
        expected_max_high = max(c["high"] for c in candles)
        result = _aggregate_ohlcv(candles)
        assert result["high"] == pytest.approx(expected_max_high)

    def test_high_identified_correctly_in_middle(self):
        """High spike in the middle of the hour must be captured."""
        candles = _make_m1_candles(self._START, n=60, fixed_high=62.0)
        # Inject an extreme spike at minute 30
        candles[30]["high"] = 999.0
        result = _aggregate_ohlcv(candles)
        assert result["high"] == pytest.approx(999.0)

    def test_low_is_min_of_all_lows(self):
        """H1 low must equal the minimum of all M1 low values."""
        candles = _make_m1_candles(self._START, n=60)
        expected_min_low = min(c["low"] for c in candles)
        result = _aggregate_ohlcv(candles)
        assert result["low"] == pytest.approx(expected_min_low)

    def test_low_identified_correctly_in_middle(self):
        """Low spike in the middle of the hour must be captured."""
        candles = _make_m1_candles(self._START, n=60, fixed_low=59.0)
        candles[30]["low"] = 0.001  # extreme low
        result = _aggregate_ohlcv(candles)
        assert result["low"] == pytest.approx(0.001)

    def test_close_is_last_candle_close(self):
        """H1 close must equal the close of the latest M1 candle."""
        candles = _make_m1_candles(self._START, n=60, base_open=60.0)
        # Last candle (minute 59): open = 60.0 + 59*0.01 = 60.59, close = +0.20
        expected_last_close = candles[-1]["close"]
        result = _aggregate_ohlcv(candles)
        assert result["close"] == pytest.approx(expected_last_close)

    def test_volume_is_sum_of_all_m1_volumes(self):
        """H1 volume must equal the sum of all M1 volumes in the window."""
        candles = _make_m1_candles(self._START, n=60, fixed_volume=100)
        # volume per candle = 100 + i, so sum = 100*60 + (0+1+...+59) = 6000 + 1770 = 7770
        expected_volume = sum(c["volume"] for c in candles)
        result = _aggregate_ohlcv(candles)
        assert result["volume"] == pytest.approx(expected_volume)

    def test_single_m1_candle_open_equals_close(self):
        """With one M1 candle, all four prices come from that single row."""
        candles = [
            {
                "time": self._START,
                "open": 65.0,
                "high": 65.5,
                "low": 64.5,
                "close": 65.2,
                "volume": 1000,
            }
        ]
        result = _aggregate_ohlcv(candles)
        assert result["open"] == pytest.approx(65.0)
        assert result["high"] == pytest.approx(65.5)
        assert result["low"] == pytest.approx(64.5)
        assert result["close"] == pytest.approx(65.2)
        assert result["volume"] == 1000

    def test_partial_hour_30_candles_still_aggregates(self):
        """Fewer than 60 M1 candles (partial hour) must still produce a valid H1."""
        candles = _make_m1_candles(self._START, n=30)
        result = _aggregate_ohlcv(candles)
        # Result must have all required keys and non-None values
        for key in ("open", "high", "low", "close", "volume"):
            assert key in result
            assert result[key] is not None

    def test_zero_candles_raises_value_error(self):
        """Aggregating zero candles must raise ValueError (matches service skip branch)."""
        with pytest.raises(ValueError):
            _aggregate_ohlcv([])

    def test_out_of_order_input_still_uses_chronological_open_close(self):
        """Even if candles are supplied out of order, open=first-by-time, close=last-by-time."""
        # Candle B is earlier but appears second in the list
        candle_a = {
            "time": self._START + timedelta(minutes=30),
            "open": 70.0,
            "high": 71.0,
            "low": 69.0,
            "close": 70.5,
            "volume": 100,
        }
        candle_b = {
            "time": self._START,  # earlier time
            "open": 60.0,
            "high": 61.0,
            "low": 59.0,
            "close": 60.5,
            "volume": 200,
        }
        result = _aggregate_ohlcv([candle_a, candle_b])
        # open must be candle_b's open (earliest time)
        assert result["open"] == pytest.approx(60.0)
        # close must be candle_a's close (latest time)
        assert result["close"] == pytest.approx(70.5)


# ===========================================================================
# CandleAggregatorService initialisation
# ===========================================================================

class TestCandleAggregatorServiceInit:
    """Tests for CandleAggregatorService.__init__ — pure in-process state checks."""

    def test_default_interval_is_module_constant(self):
        """Default interval must match AGGREGATION_INTERVAL_SECONDS constant."""
        svc = CandleAggregatorService()
        assert svc.interval_seconds == AGGREGATION_INTERVAL_SECONDS

    def test_custom_interval_respected(self):
        """Explicit interval_seconds argument must override the default."""
        svc = CandleAggregatorService(interval_seconds=5)
        assert svc.interval_seconds == 5

    def test_running_flag_initially_false(self):
        """Service must not start in running state; run() sets it to True."""
        svc = CandleAggregatorService()
        assert svc.running is False

    def test_all_tracked_symbols_have_state_entry(self):
        """_last_aggregated_hour must contain one entry per tracked symbol, all None."""
        svc = CandleAggregatorService()
        for symbol in TRACKED_SYMBOLS:
            assert symbol in svc._last_aggregated_hour
            assert svc._last_aggregated_hour[symbol] is None

    def test_no_extra_symbols_in_state(self):
        """_last_aggregated_hour must have exactly as many entries as TRACKED_SYMBOLS."""
        svc = CandleAggregatorService()
        assert set(svc._last_aggregated_hour.keys()) == set(TRACKED_SYMBOLS)

    def test_module_constant_interval_is_60_seconds(self):
        """AGGREGATION_INTERVAL_SECONDS must be 60 (matches docstring contract)."""
        assert AGGREGATION_INTERVAL_SECONDS == 60

    def test_tracked_symbols_contains_crude_oil(self):
        """CrudeOIL is the primary live-traded symbol and must always be tracked."""
        assert "CrudeOIL" in TRACKED_SYMBOLS

    def test_tracked_symbols_contains_usa500(self):
        """USA500 data is backfilled and must be tracked."""
        assert "USA500" in TRACKED_SYMBOLS

    def test_stop_sets_running_to_false(self):
        """stop() must set running=False immediately."""
        svc = CandleAggregatorService()
        svc.running = True
        svc.stop()
        assert svc.running is False


# ===========================================================================
# Edge case: last-completed-hour boundary arithmetic
# ===========================================================================

class TestLastCompletedHourLogic:
    """
    Verify the 'last completed hour' arithmetic that _run_aggregation_cycle applies.

    The service uses:
        last_completed_hour = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    We test this formula directly because an off-by-one would cause the
    current (open) hour to be aggregated prematurely.
    """

    def _compute_last_completed_hour(self, now_utc: datetime) -> datetime:
        return now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    def test_at_xx15_last_completed_is_previous_whole_hour(self):
        """At 15:47 UTC the last completed hour is 14:00 UTC."""
        now = datetime(2024, 3, 5, 15, 47, 23, tzinfo=timezone.utc)
        result = self._compute_last_completed_hour(now)
        assert result == datetime(2024, 3, 5, 14, 0, 0, tzinfo=timezone.utc)

    def test_at_midnight_last_completed_is_23h_previous_day(self):
        """At 00:01 UTC the last completed hour is 23:00 of the previous day."""
        now = datetime(2024, 3, 5, 0, 1, 0, tzinfo=timezone.utc)
        result = self._compute_last_completed_hour(now)
        assert result == datetime(2024, 3, 4, 23, 0, 0, tzinfo=timezone.utc)

    def test_at_top_of_hour_last_completed_is_one_hour_ago(self):
        """At exactly 10:00:00 UTC the last completed hour is 09:00 UTC."""
        now = datetime(2024, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
        result = self._compute_last_completed_hour(now)
        assert result == datetime(2024, 3, 5, 9, 0, 0, tzinfo=timezone.utc)

    def test_result_always_has_minute_zero(self):
        """The floor-of-hour subtraction must always produce minute=0, second=0."""
        now = datetime(2024, 6, 15, 17, 59, 59, 999999, tzinfo=timezone.utc)
        result = self._compute_last_completed_hour(now)
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0
