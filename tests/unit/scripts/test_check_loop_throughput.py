"""
Unit tests for check_loop_throughput.py — pure data transformation logic.

These tests cover:
  - _top5_with_other: reason truncation and ...other collapsing
  - _total_resolved: summing across reason buckets
  - _check_breaches: threshold logic, exit-code semantics
  - _fmt_pnl: sign formatting
  - _parse_args: argparse defaults and overrides

No DB connections, no mocks of psycopg2 — these are pure function tests.
All test inputs are synthetic dicts that represent what the DB query helpers
would return, NOT the output of DB calls themselves.
"""
import sys
import os
import pytest

# Add project root so the import resolves without installing the package.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.check_loop_throughput import (
    _top5_with_other,
    _total_resolved,
    _check_breaches,
    _fmt_pnl,
    _parse_args,
)


# ---------------------------------------------------------------------------
# _top5_with_other
# ---------------------------------------------------------------------------

class TestTop5WithOther:
    def test_empty(self):
        assert _top5_with_other({}) == []

    def test_fewer_than_five_reasons(self):
        reasons = {"max_positions": 3, "low_score": 2}
        result = _top5_with_other(reasons)
        assert len(result) == 2
        # sorted descending
        assert result[0] == ("max_positions", 3)
        assert result[1] == ("low_score", 2)

    def test_exactly_five_reasons(self):
        reasons = {"a": 5, "b": 4, "c": 3, "d": 2, "e": 1}
        result = _top5_with_other(reasons)
        assert len(result) == 5
        assert "...other" not in dict(result)

    def test_six_reasons_collapses_tail(self):
        reasons = {"a": 10, "b": 9, "c": 8, "d": 7, "e": 6, "f": 1}
        result = _top5_with_other(reasons)
        assert len(result) == 6  # top 5 + ...other
        labels = [label for label, _ in result]
        assert "...other" in labels
        other_count = dict(result)["...other"]
        assert other_count == 1  # "f" with count 1

    def test_many_reasons_other_sums_correctly(self):
        # 8 reasons: top-5 = 100+90+80+70+60, tail = 5+4+3 = 12
        reasons = {str(i): i for i in range(3, 103, 10)}  # 3,13,23,...,93,103
        # That is 11 items: 3,13,23,33,43,53,63,73,83,93,103
        result = _top5_with_other(reasons)
        assert len(result) == 6  # top 5 + ...other
        top5_sum = sum(cnt for _, cnt in result[:5])
        other_count = dict(result)["...other"]
        total_in_result = top5_sum + other_count
        assert total_in_result == sum(reasons.values())

    def test_single_reason(self):
        result = _top5_with_other({"no_candle_data": 42})
        assert result == [("no_candle_data", 42)]
        assert "...other" not in dict(result)


# ---------------------------------------------------------------------------
# _total_resolved
# ---------------------------------------------------------------------------

class TestTotalResolved:
    def test_empty(self):
        assert _total_resolved({}) == 0

    def test_all_zero(self):
        assert _total_resolved({"tp_hit": 0, "sl_hit": 0, "watchdog_24h": 0, "other": 0}) == 0

    def test_sum_all_buckets(self):
        assert _total_resolved({"tp_hit": 5, "sl_hit": 3, "watchdog_24h": 1, "other": 0}) == 9

    def test_only_tp_hit(self):
        assert _total_resolved({"tp_hit": 7}) == 7

    def test_large_counts(self):
        data = {"tp_hit": 1000, "sl_hit": 500, "watchdog_24h": 100, "other": 50}
        assert _total_resolved(data) == 1650


# ---------------------------------------------------------------------------
# _check_breaches
# ---------------------------------------------------------------------------

class TestCheckBreaches:
    """
    Covers exit-code semantics:
      - exit 0 when all symbols meet threshold
      - exit 1 (breach list non-empty) when any symbol is below threshold
      - exit 0 when symbols list is empty (paused system)
    """

    def test_empty_symbols_no_breach(self):
        """Empty symbol list → no breaches (paused system, don't false-positive)."""
        breaches = _check_breaches([], {}, threshold=10)
        assert breaches == []

    def test_all_symbols_meet_threshold(self):
        resolved = {
            "CrudeOIL": {"tp_hit": 6, "sl_hit": 5, "watchdog_24h": 0, "other": 0},  # 11
            "USA500":   {"tp_hit": 3, "sl_hit": 8, "watchdog_24h": 0, "other": 0},  # 11
        }
        breaches = _check_breaches(["CrudeOIL", "USA500"], resolved, threshold=10)
        assert breaches == []

    def test_one_symbol_below_threshold(self):
        resolved = {
            "CrudeOIL": {"tp_hit": 6, "sl_hit": 5, "watchdog_24h": 0, "other": 0},  # 11
            "GBPJPY.":  {"tp_hit": 2, "sl_hit": 3, "watchdog_24h": 0, "other": 0},  # 5
        }
        breaches = _check_breaches(["CrudeOIL", "GBPJPY."], resolved, threshold=10)
        assert breaches == ["GBPJPY."]

    def test_all_symbols_below_threshold(self):
        resolved = {
            "CrudeOIL": {"tp_hit": 1, "sl_hit": 2},
            "USA500":   {"tp_hit": 0, "sl_hit": 0},
        }
        breaches = _check_breaches(["CrudeOIL", "USA500"], resolved, threshold=10)
        assert set(breaches) == {"CrudeOIL", "USA500"}

    def test_symbol_with_no_data_is_breach(self):
        """A symbol present in the list but absent from resolved dict → breach (0 < threshold)."""
        resolved = {"CrudeOIL": {"tp_hit": 15}}
        breaches = _check_breaches(["CrudeOIL", "USA500"], resolved, threshold=10)
        assert "USA500" in breaches

    def test_exactly_at_threshold_is_pass(self):
        resolved = {"CrudeOIL": {"tp_hit": 10}}
        breaches = _check_breaches(["CrudeOIL"], resolved, threshold=10)
        assert breaches == []

    def test_one_below_threshold_is_breach(self):
        resolved = {"CrudeOIL": {"tp_hit": 9}}
        breaches = _check_breaches(["CrudeOIL"], resolved, threshold=10)
        assert breaches == ["CrudeOIL"]

    def test_threshold_zero_always_passes(self):
        """threshold=0 means every symbol passes regardless of resolved count."""
        breaches = _check_breaches(["CrudeOIL", "USA500"], {}, threshold=0)
        assert breaches == []

    def test_single_symbol_system_paused(self):
        """No resolved trades, threshold=10 → breach."""
        breaches = _check_breaches(["CrudeOIL"], {"CrudeOIL": {}}, threshold=10)
        assert breaches == ["CrudeOIL"]

    def test_exit_code_semantics_pass(self):
        """Simulate the run() return value: 0 when no breaches."""
        breaches = _check_breaches(["CrudeOIL"], {"CrudeOIL": {"tp_hit": 12}}, threshold=10)
        exit_code = 1 if breaches else 0
        assert exit_code == 0

    def test_exit_code_semantics_breach(self):
        """Simulate the run() return value: 1 when breaches exist."""
        breaches = _check_breaches(["CrudeOIL"], {"CrudeOIL": {"tp_hit": 2}}, threshold=10)
        exit_code = 1 if breaches else 0
        assert exit_code == 1


# ---------------------------------------------------------------------------
# _fmt_pnl
# ---------------------------------------------------------------------------

class TestFmtPnl:
    def test_positive(self):
        assert _fmt_pnl(12.34) == "+12.34"

    def test_negative(self):
        assert _fmt_pnl(-5.67) == "-5.67"

    def test_zero(self):
        assert _fmt_pnl(0.0) == "+0.00"

    def test_large_positive(self):
        assert _fmt_pnl(1000.0) == "+1000.00"

    def test_large_negative(self):
        assert _fmt_pnl(-9999.99) == "-9999.99"


# ---------------------------------------------------------------------------
# _parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        args = _parse_args([])
        assert args.days == 7
        assert args.alert_threshold == 10
        assert args.symbols is None
        assert args.include_live_pnl is False

    def test_custom_days(self):
        args = _parse_args(["--days", "14"])
        assert args.days == 14

    def test_custom_threshold(self):
        args = _parse_args(["--alert-threshold", "25"])
        assert args.alert_threshold == 25

    def test_symbols_override(self):
        args = _parse_args(["--symbols", "CrudeOIL,USA500"])
        assert args.symbols == "CrudeOIL,USA500"

    def test_include_live_pnl_flag(self):
        args = _parse_args(["--include-live-pnl"])
        assert args.include_live_pnl is True

    def test_combined_args(self):
        args = _parse_args(["--days", "3", "--alert-threshold", "5", "--symbols", "CrudeOIL"])
        assert args.days == 3
        assert args.alert_threshold == 5
        assert args.symbols == "CrudeOIL"


# ---------------------------------------------------------------------------
# Integration-style: full breach-detection pipeline with synthetic dicts
# (still no DB calls — tests the compose of _check_breaches + _total_resolved)
# ---------------------------------------------------------------------------

class TestBreachDetectionPipeline:
    """
    Feed the same data shapes that the DB query helpers would return into the
    breach-detection chain and assert the correct exit code.
    """

    def test_healthy_system_exit_0(self):
        """All symbols have plenty of resolved trades → exit 0."""
        resolved = {
            "CrudeOIL": {"tp_hit": 8, "sl_hit": 4, "watchdog_24h": 0, "other": 0},
            "USA500":   {"tp_hit": 5, "sl_hit": 7, "watchdog_24h": 1, "other": 0},
            "GBPJPY.":  {"tp_hit": 12, "sl_hit": 2, "watchdog_24h": 0, "other": 0},
        }
        symbols = ["CrudeOIL", "USA500", "GBPJPY."]
        breaches = _check_breaches(symbols, resolved, threshold=10)
        assert breaches == []
        assert (1 if breaches else 0) == 0

    def test_new_symbol_no_trades_exit_1(self):
        """A newly added symbol with zero activity → breach → exit 1."""
        resolved = {
            "CrudeOIL": {"tp_hit": 8, "sl_hit": 5},
            "#TSLA":    {},
        }
        symbols = ["CrudeOIL", "#TSLA"]
        breaches = _check_breaches(symbols, resolved, threshold=10)
        assert "#TSLA" in breaches
        assert (1 if breaches else 0) == 1

    def test_empty_system_exit_0(self):
        """No symbols configured (deliberately paused) → no breaches → exit 0."""
        breaches = _check_breaches([], {}, threshold=10)
        assert breaches == []
        assert (1 if breaches else 0) == 0
