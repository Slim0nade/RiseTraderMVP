"""
Unit tests for pure math/transform functions in scripts/backfill_historical_data.py.

Covers:
- aggregate_m1_to_h1: OHLCV aggregation correctness, single/multi-hour, partial hour, empty input
- df_to_rows: tuple format, field mapping, change/change_pct math, UTC timezone handling
- filter_histdata_month: correct month isolation from a multi-month DataFrame
- _ticks_to_m1: tick grouping into M1 candles, open/high/low/close/volume correctness

No DB, network, or mocks needed — all tests use static in-process DataFrames.
"""
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

# Ensure scripts/ is importable from the repo root
sys.path.insert(0, "/Users/erinrouissi/Documents/VSCode/Rise/RiseTraderMVP")

from scripts.backfill_historical_data import (
    _ticks_to_m1,
    aggregate_m1_to_h1,
    df_to_rows,
    filter_histdata_month,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_m1_df(start_dt: datetime, n_minutes: int, base_price: float = 60.0) -> pd.DataFrame:
    """Build a minimal M1 DataFrame with `n_minutes` rows starting at `start_dt`."""
    rows = []
    for i in range(n_minutes):
        o = base_price + i * 0.01
        rows.append(
            {
                "time": start_dt + timedelta(minutes=i),
                "open": o,
                "high": o + 0.50,
                "low": o - 0.50,
                "close": o + 0.20,
                "volume": 100 + i,
            }
        )
    return pd.DataFrame(rows)


# ===========================================================================
# aggregate_m1_to_h1
# ===========================================================================

class TestAggregateM1ToH1:
    """Tests for aggregate_m1_to_h1 — pure pandas groupby + aggregation math."""

    def test_single_hour_60_candles_open_is_first_m1_open(self):
        """H1 open must equal the first M1 open within the hour."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=60, base_price=62.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        assert len(df_h1) == 1
        # The very first M1 row has open = 62.0
        assert df_h1.iloc[0]["open"] == pytest.approx(62.0)

    def test_single_hour_60_candles_high_is_max_of_m1_highs(self):
        """H1 high must be the maximum of all M1 high values within the hour."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=60, base_price=62.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        expected_max_high = df_m1["high"].max()
        assert df_h1.iloc[0]["high"] == pytest.approx(expected_max_high)

    def test_single_hour_60_candles_low_is_min_of_m1_lows(self):
        """H1 low must be the minimum of all M1 low values within the hour."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=60, base_price=62.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        expected_min_low = df_m1["low"].min()
        assert df_h1.iloc[0]["low"] == pytest.approx(expected_min_low)

    def test_single_hour_60_candles_close_is_last_m1_close(self):
        """H1 close must equal the last M1 close within the hour."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=60, base_price=62.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        # Last M1 row (minute 59) has open = 62.0 + 59*0.01 = 62.59, close = +0.20
        expected_last_close = df_m1.iloc[-1]["close"]
        assert df_h1.iloc[0]["close"] == pytest.approx(expected_last_close)

    def test_single_hour_60_candles_volume_is_sum(self):
        """H1 volume must equal the sum of all M1 volumes within the hour."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=60, base_price=62.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        expected_total_volume = df_m1["volume"].sum()
        assert df_h1.iloc[0]["volume"] == pytest.approx(expected_total_volume)

    def test_two_hours_120_candles_produces_two_h1_bars(self):
        """120 consecutive M1 candles spanning two hours must produce exactly 2 H1 bars."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=120, base_price=60.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        assert len(df_h1) == 2

    def test_two_hours_first_bar_covers_09_to_10(self):
        """First H1 bar time must be the floor-of-hour of the first minute."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=120, base_price=60.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        first_h1_time = pd.Timestamp(df_h1.iloc[0]["time"])
        assert first_h1_time.hour == 9
        assert first_h1_time.minute == 0

    def test_two_hours_second_bar_covers_10_to_11(self):
        """Second H1 bar time must be the floor-of-hour of the second block."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=120, base_price=60.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        second_h1_time = pd.Timestamp(df_h1.iloc[1]["time"])
        assert second_h1_time.hour == 10
        assert second_h1_time.minute == 0

    def test_two_hours_open_of_each_bar_correct(self):
        """Each H1 bar's open must equal the first M1 open within that hour."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=120, base_price=60.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        # Hour 1: first M1 is minute 0 -> open = 60.0
        assert df_h1.iloc[0]["open"] == pytest.approx(60.0)
        # Hour 2: first M1 is minute 60 -> open = 60.0 + 60*0.01 = 60.60
        assert df_h1.iloc[1]["open"] == pytest.approx(60.60)

    def test_partial_hour_30_candles_produces_one_h1_bar(self):
        """Fewer than 60 M1 candles for an hour must still produce exactly 1 H1 bar."""
        start = datetime(2024, 3, 5, 14, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=30, base_price=70.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        assert len(df_h1) == 1

    def test_partial_hour_ohlcv_math_is_correct(self):
        """Partial hour H1 OHLCV must still reflect first open, max high, min low,
        last close, and total volume of the partial M1 data."""
        start = datetime(2024, 3, 5, 14, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=30, base_price=70.0)

        df_h1 = aggregate_m1_to_h1(df_m1)

        assert df_h1.iloc[0]["open"] == pytest.approx(df_m1.iloc[0]["open"])
        assert df_h1.iloc[0]["high"] == pytest.approx(df_m1["high"].max())
        assert df_h1.iloc[0]["low"] == pytest.approx(df_m1["low"].min())
        assert df_h1.iloc[0]["close"] == pytest.approx(df_m1.iloc[-1]["close"])
        assert df_h1.iloc[0]["volume"] == pytest.approx(df_m1["volume"].sum())

    def test_empty_dataframe_returns_empty_dataframe(self):
        """Empty input must return an empty DataFrame, not raise."""
        df_h1 = aggregate_m1_to_h1(pd.DataFrame())

        assert isinstance(df_h1, pd.DataFrame)
        assert df_h1.empty

    def test_single_m1_candle_produces_one_h1_bar(self):
        """Edge case: a single M1 row must still produce a valid H1 row."""
        single_row = pd.DataFrame(
            [
                {
                    "time": datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
                    "open": 65.0,
                    "high": 65.5,
                    "low": 64.5,
                    "close": 65.2,
                    "volume": 1000,
                }
            ]
        )

        df_h1 = aggregate_m1_to_h1(single_row)

        assert len(df_h1) == 1
        assert df_h1.iloc[0]["open"] == pytest.approx(65.0)
        assert df_h1.iloc[0]["high"] == pytest.approx(65.5)
        assert df_h1.iloc[0]["low"] == pytest.approx(64.5)
        assert df_h1.iloc[0]["close"] == pytest.approx(65.2)
        assert df_h1.iloc[0]["volume"] == pytest.approx(1000)

    def test_output_sorted_by_time_ascending(self):
        """H1 output rows must be sorted ascending by time."""
        # Supply M1 data for three separate hours in reverse order
        rows = []
        for hour in [11, 9, 10]:
            for minute in range(10):
                rows.append(
                    {
                        "time": datetime(2024, 3, 5, hour, minute, tzinfo=timezone.utc),
                        "open": 60.0,
                        "high": 61.0,
                        "low": 59.0,
                        "close": 60.5,
                        "volume": 100,
                    }
                )
        df_m1 = pd.DataFrame(rows)

        df_h1 = aggregate_m1_to_h1(df_m1)

        times = list(df_h1["time"])
        assert times == sorted(times), "H1 output is not sorted ascending by time"

    def test_output_columns_present(self):
        """Output DataFrame must contain all five expected OHLCV columns plus time."""
        start = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        df_m1 = _make_m1_df(start, n_minutes=5)

        df_h1 = aggregate_m1_to_h1(df_m1)

        for col in ["time", "open", "high", "low", "close", "volume"]:
            assert col in df_h1.columns, f"Missing column: {col}"


# ===========================================================================
# df_to_rows
# ===========================================================================

class TestDfToRows:
    """Tests for df_to_rows — converts DataFrame to 12-element DB tuples."""

    def _make_single_row_df(
        self,
        t: datetime = None,
        open_: float = 60.0,
        high: float = 61.0,
        low: float = 59.0,
        close: float = 60.5,
        volume: int = 500,
    ) -> pd.DataFrame:
        if t is None:
            t = datetime(2024, 3, 5, 9, 0)
        return pd.DataFrame(
            [{"time": t, "open": open_, "high": high, "low": low, "close": close, "volume": volume}]
        )

    def test_returns_list_of_tuples(self):
        """df_to_rows must return a list."""
        df = self._make_single_row_df()
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        assert isinstance(result, list)

    def test_one_row_df_produces_one_tuple(self):
        """One DataFrame row must produce exactly one tuple."""
        df = self._make_single_row_df()
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        assert len(result) == 1

    def test_tuple_has_12_elements(self):
        """Each tuple must have exactly 12 elements matching the DB schema."""
        df = self._make_single_row_df()
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        assert len(result[0]) == 12

    def test_tuple_field_order(self):
        """Tuple order: (time, symbol, import_symbol, timeframe, source, open, high, low, last, change, change_pct, volume)."""
        t = datetime(2024, 3, 5, 9, 0)
        df = self._make_single_row_df(t=t, open_=60.0, high=61.0, low=59.0, close=60.5, volume=500)

        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        row = result[0]

        # Positional checks for each field
        assert row[1] == "USA500"           # symbol
        assert row[2] == "USA500IDXUSD"     # import_symbol
        assert row[3] == "H1"               # timeframe
        assert row[4] == "DUKASCOPY"        # source
        assert row[5] == pytest.approx(60.0)  # open
        assert row[6] == pytest.approx(61.0)  # high
        assert row[7] == pytest.approx(59.0)  # low
        assert row[8] == pytest.approx(60.5)  # last (= close)

    def test_change_equals_close_minus_open(self):
        """change field must equal close - open, rounded to 6 dp."""
        df = self._make_single_row_df(open_=60.0, close=60.5)
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        change = result[0][9]  # index 9 = change
        assert change == pytest.approx(0.5, abs=1e-5)

    def test_change_negative_when_bearish(self):
        """change must be negative when close < open (bearish candle)."""
        df = self._make_single_row_df(open_=61.0, close=60.0)
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        change = result[0][9]
        assert change < 0

    def test_change_pct_formula(self):
        """change_percent must be ((close - open) / open) * 100, rounded to 4 dp."""
        df = self._make_single_row_df(open_=100.0, close=105.0)
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        change_pct = result[0][10]  # index 10 = change_percent
        expected = round((105.0 - 100.0) / 100.0 * 100, 4)  # 5.0
        assert change_pct == pytest.approx(expected)

    def test_change_pct_is_zero_when_open_is_zero(self):
        """change_percent must be 0.0 when open==0 to avoid division by zero."""
        df = self._make_single_row_df(open_=0.0, close=60.5)
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        change_pct = result[0][10]
        assert change_pct == pytest.approx(0.0)

    def test_volume_is_int(self):
        """volume field must be an integer in the output tuple."""
        df = self._make_single_row_df(volume=1234)
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        assert isinstance(result[0][11], int)
        assert result[0][11] == 1234

    def test_timezone_naive_timestamp_becomes_utc_aware(self):
        """A naive datetime in the 'time' column must be localised to UTC in the output."""
        naive_dt = datetime(2024, 3, 5, 9, 0)  # no tzinfo
        df = self._make_single_row_df(t=naive_dt)
        result = df_to_rows(df, "USA500", "USA500IDXUSD", "H1", "DUKASCOPY")
        ts = result[0][0]
        # The function attaches UTC; the Timestamp must have timezone info
        assert ts.tzinfo is not None

    def test_multiple_rows_produce_multiple_tuples(self):
        """Three DataFrame rows must produce exactly three tuples."""
        rows = []
        base = datetime(2024, 3, 5, 9, 0)
        for i in range(3):
            rows.append(
                {
                    "time": base + timedelta(hours=i),
                    "open": 60.0 + i,
                    "high": 61.0 + i,
                    "low": 59.0 + i,
                    "close": 60.5 + i,
                    "volume": 500 + i * 100,
                }
            )
        df = pd.DataFrame(rows)
        result = df_to_rows(df, "CrudeOIL", "LIGHTCMDUSD", "M1", "DUKASCOPY")
        assert len(result) == 3

    def test_symbol_and_source_passed_through(self):
        """db_symbol and source string are propagated into every row unchanged."""
        df = self._make_single_row_df()
        result = df_to_rows(df, "GBPJPY", "GBPJPY", "M1", "HISTDATA")
        assert result[0][1] == "GBPJPY"
        assert result[0][4] == "HISTDATA"


# ===========================================================================
# filter_histdata_month
# ===========================================================================

class TestFilterHistdataMonth:
    """Tests for filter_histdata_month — month isolation from a full-year DF."""

    def _make_year_df(self, year: int = 2024) -> pd.DataFrame:
        """Build a DataFrame covering all 12 months with one row per month."""
        rows = []
        for month in range(1, 13):
            rows.append(
                {
                    "time": datetime(year, month, 15, 10, 0),
                    "open": 1.0,
                    "high": 1.1,
                    "low": 0.9,
                    "close": 1.05,
                    "volume": 100,
                }
            )
        return pd.DataFrame(rows)

    def test_returns_only_target_month(self):
        """Only rows from the specified month must be returned."""
        df_year = self._make_year_df()
        df_feb = filter_histdata_month(df_year, 2024, 2)
        assert len(df_feb) == 1
        assert df_feb.iloc[0]["time"].month == 2

    def test_no_rows_from_other_months(self):
        """Rows from all other months must be excluded."""
        df_year = self._make_year_df()
        df_feb = filter_histdata_month(df_year, 2024, 2)
        # Should contain only February data
        assert all(row["time"].month == 2 for _, row in df_feb.iterrows())

    def test_returns_all_rows_within_target_month(self):
        """All rows belonging to the target month must appear."""
        # Build DF with two rows in March
        rows = [
            {"time": datetime(2024, 2, 1, 10, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
            {"time": datetime(2024, 3, 1, 10, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
            {"time": datetime(2024, 3, 15, 12, 0), "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 200},
            {"time": datetime(2024, 4, 1, 10, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
        ]
        df_year = pd.DataFrame(rows)
        df_march = filter_histdata_month(df_year, 2024, 3)
        assert len(df_march) == 2

    def test_empty_result_for_month_with_no_data(self):
        """Month with no matching rows must return an empty DataFrame."""
        df_year = self._make_year_df()
        # No data for December in a special case: rebuild without December
        df_no_dec = df_year[df_year["time"].dt.month != 12].copy()
        df_dec = filter_histdata_month(df_no_dec, 2024, 12)
        assert df_dec.empty

    def test_output_is_sorted_by_time(self):
        """Filtered output must be sorted ascending by time."""
        rows = [
            {"time": datetime(2024, 5, 20, 14, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
            {"time": datetime(2024, 5, 1, 10, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
            {"time": datetime(2024, 5, 10, 8, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
        ]
        df_year = pd.DataFrame(rows)
        df_may = filter_histdata_month(df_year, 2024, 5)
        times = list(df_may["time"])
        assert times == sorted(times), "Output is not sorted ascending by time"

    def test_year_boundary_not_crossed(self):
        """Filter must respect both year AND month to avoid cross-year contamination."""
        rows = [
            {"time": datetime(2023, 6, 15, 10, 0), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100},
            {"time": datetime(2024, 6, 15, 10, 0), "open": 2.0, "high": 2.1, "low": 1.9, "close": 2.05, "volume": 200},
        ]
        df_mixed = pd.DataFrame(rows)
        df_june_2024 = filter_histdata_month(df_mixed, 2024, 6)
        assert len(df_june_2024) == 1
        assert df_june_2024.iloc[0]["open"] == pytest.approx(2.0)


# ===========================================================================
# _ticks_to_m1
# ===========================================================================

class TestTicksToM1:
    """Tests for _ticks_to_m1 — aggregates intra-hour ticks to 1-minute candles."""

    _HOUR_START = datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)

    def test_empty_ticks_returns_empty_list(self):
        """No ticks must produce an empty list (not an error)."""
        result = _ticks_to_m1([], self._HOUR_START)
        assert result == []

    def test_single_tick_produces_one_m1_candle(self):
        """A single tick at ms=0 must produce exactly one M1 candle for minute 0."""
        ticks = [{"ms": 0, "mid": 62.0, "volume": 100.0}]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert len(result) == 1

    def test_single_tick_ohlcv_all_equal_mid(self):
        """When only one tick exists, open==high==low==close==mid."""
        ticks = [{"ms": 5000, "mid": 62.5, "volume": 200.0}]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        candle = result[0]
        assert candle["open"] == pytest.approx(62.5)
        assert candle["high"] == pytest.approx(62.5)
        assert candle["low"] == pytest.approx(62.5)
        assert candle["close"] == pytest.approx(62.5)

    def test_two_ticks_same_minute_produce_one_candle(self):
        """Two ticks in the same minute must be merged into a single M1 candle."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},
            {"ms": 30000, "mid": 60.5, "volume": 150.0},  # 30s into minute 0
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert len(result) == 1

    def test_two_ticks_same_minute_open_is_first_price(self):
        """Open of the M1 candle must equal the first tick's mid price."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},
            {"ms": 30000, "mid": 60.5, "volume": 150.0},
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert result[0]["open"] == pytest.approx(60.0)

    def test_two_ticks_same_minute_close_is_last_price(self):
        """Close of the M1 candle must equal the last tick's mid price."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},
            {"ms": 30000, "mid": 60.5, "volume": 150.0},
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert result[0]["close"] == pytest.approx(60.5)

    def test_high_is_max_mid_within_minute(self):
        """High must be the maximum mid price among all ticks in that minute."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},
            {"ms": 10000, "mid": 61.2, "volume": 80.0},  # highest
            {"ms": 50000, "mid": 60.7, "volume": 90.0},
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert result[0]["high"] == pytest.approx(61.2)

    def test_low_is_min_mid_within_minute(self):
        """Low must be the minimum mid price among all ticks in that minute."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},
            {"ms": 10000, "mid": 59.3, "volume": 80.0},  # lowest
            {"ms": 50000, "mid": 60.7, "volume": 90.0},
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert result[0]["low"] == pytest.approx(59.3)

    def test_volume_is_sum_within_minute(self):
        """Volume must be the integer sum of all tick volumes in that minute."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},
            {"ms": 30000, "mid": 60.5, "volume": 150.0},
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert result[0]["volume"] == 250  # int sum

    def test_volume_is_integer_type(self):
        """Volume in the returned candle must be an integer (int())."""
        ticks = [{"ms": 0, "mid": 60.0, "volume": 123.7}]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert isinstance(result[0]["volume"], int)

    def test_ticks_spanning_two_minutes_produce_two_candles(self):
        """Ticks at ms<60000 (minute 0) and ms>=60000 (minute 1) must produce 2 candles."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},      # minute 0
            {"ms": 30000, "mid": 60.5, "volume": 150.0},   # minute 0
            {"ms": 60000, "mid": 61.0, "volume": 200.0},   # minute 1
            {"ms": 90000, "mid": 61.5, "volume": 250.0},   # minute 1
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert len(result) == 2

    def test_candle_time_aligned_to_minute_boundary(self):
        """Each M1 candle's 'time' field must be at the exact minute boundary (second=0)."""
        ticks = [
            {"ms": 0, "mid": 60.0, "volume": 100.0},       # minute 0 → 09:00
            {"ms": 120000, "mid": 61.0, "volume": 200.0},  # minute 2 → 09:02
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert result[0]["time"] == datetime(2024, 3, 5, 9, 0, tzinfo=timezone.utc)
        assert result[1]["time"] == datetime(2024, 3, 5, 9, 2, tzinfo=timezone.utc)

    def test_candles_sorted_by_minute_ascending(self):
        """Returned candles must be ordered by minute index ascending."""
        # Feed ticks out of minute order — function must still sort by minute_idx
        ticks = [
            {"ms": 120000, "mid": 62.0, "volume": 100.0},  # minute 2
            {"ms": 0, "mid": 60.0, "volume": 100.0},       # minute 0
            {"ms": 60000, "mid": 61.0, "volume": 100.0},   # minute 1
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        times = [c["time"] for c in result]
        assert times == sorted(times), "Candles not sorted ascending by time"

    def test_large_volume_of_ticks_all_same_minute_collapses_to_one_candle(self):
        """100 ticks all within minute 0 must still produce exactly 1 M1 candle."""
        ticks = [
            {"ms": i * 500, "mid": 60.0 + i * 0.001, "volume": 10.0}
            for i in range(100)
        ]
        result = _ticks_to_m1(ticks, self._HOUR_START)
        assert len(result) == 1
