"""
Unit tests for CrossAssetFilter.

All assertions use pure math with hand-crafted price series — no DB, no MT4,
no mocks of external services.

Coverage:
    _short_term_direction:
        1. Rising prices → positive direction
        2. Falling prices → negative direction
        3. Flat prices → near-zero direction
        4. Single price → 0.0 (edge case)
        5. Fewer bars than requested → uses all available

    Confirmation scoring (via _score_confirm / _score_context):
        6.  CrudeOIL BUY + BRENT_OIL rising → score > 0
        7.  CrudeOIL BUY + BRENT_OIL falling → score < -0.3 (reject)
        8.  CrudeOIL SELL + BRENT_OIL falling → score > 0
        9.  CrudeOIL SELL + BRENT_OIL rising → score < -0.3 (reject)

    check_confirmation (async, DB fetch replaced with a subclass override):
        10. CrudeOIL BUY + BRENT rising + USA500 rising → passes (score > -0.3)
        11. CrudeOIL BUY + BRENT falling → rejects (score < -0.3)
        12. CrudeOIL SELL + BRENT falling + USA500 falling → passes
        13. Symbol not in asset groups → score 0.0, reason "no_group"
        14. Symbol with no related assets → score 0.0

    check_confirmation — missing data path:
        15. Related symbol returns empty list → no_data, treated as neutral

The async tests use an in-process subclass that overrides _fetch_closes to
return synthetic closes, keeping these tests pure (no network, no DB).
"""

from __future__ import annotations

import math
import pytest
import asyncio
from typing import Dict, List, Optional

from src.trading.filters.cross_asset_filter import CrossAssetFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rising(n: int = 15, start: float = 100.0, step: float = 0.5) -> List[float]:
    """Return `n` steadily rising closes."""
    return [start + i * step for i in range(n)]


def _falling(n: int = 15, start: float = 100.0, step: float = 0.5) -> List[float]:
    """Return `n` steadily falling closes."""
    return [start - i * step for i in range(n)]


def _flat(n: int = 15, value: float = 100.0) -> List[float]:
    """Return `n` identical closes."""
    return [value] * n


class _StubbedFilter(CrossAssetFilter):
    """
    CrossAssetFilter subclass that replaces _fetch_closes with in-process stubs.

    Provide `stub_closes` as {symbol: [close, ...]} in the constructor.
    Missing entries raise ValueError to simulate a DB fetch error.
    """

    def __init__(self, stub_closes: Dict[str, List[float]]) -> None:
        super().__init__()
        self._stub_closes = stub_closes

    async def _fetch_closes(self, symbol: str, limit: int) -> List[float]:
        if symbol not in self._stub_closes:
            raise ValueError(f"no stub data for {symbol}")
        closes = self._stub_closes[symbol]
        # Respect the limit so behaviour matches the real implementation
        return closes[-limit:] if len(closes) > limit else closes


# ---------------------------------------------------------------------------
# _short_term_direction tests (pure, synchronous)
# ---------------------------------------------------------------------------


class TestShortTermDirection:
    f = CrossAssetFilter()

    def test_rising_prices_return_positive_direction(self) -> None:
        closes = _rising(n=15, start=100.0, step=1.0)
        direction = self.f._short_term_direction(closes, bars=10)
        assert direction > 0.0

    def test_falling_prices_return_negative_direction(self) -> None:
        closes = _falling(n=15, start=100.0, step=1.0)
        direction = self.f._short_term_direction(closes, bars=10)
        assert direction < 0.0

    def test_flat_prices_return_near_zero(self) -> None:
        closes = _flat(n=15, value=50.0)
        direction = self.f._short_term_direction(closes, bars=10)
        assert abs(direction) < 1e-9

    def test_single_price_returns_zero(self) -> None:
        direction = self.f._short_term_direction([55.0], bars=10)
        assert direction == 0.0

    def test_empty_list_returns_zero(self) -> None:
        direction = self.f._short_term_direction([], bars=10)
        assert direction == 0.0

    def test_fewer_bars_than_requested_uses_all_available(self) -> None:
        # 5 prices, requesting 10 bars — should still compute without error
        closes = _rising(n=5, start=100.0, step=1.0)
        direction = self.f._short_term_direction(closes, bars=10)
        assert direction > 0.0

    def test_direction_capped_at_plus_one(self) -> None:
        # Very large move: +100% over 10 bars → ROC = 1.0, cap maps to 1.0
        closes = [100.0] * 9 + [200.0]
        direction = self.f._short_term_direction(closes, bars=10)
        assert direction == pytest.approx(1.0)

    def test_direction_capped_at_minus_one(self) -> None:
        # Very large drop: -100% over 10 bars (impossible price, but checks clamp)
        closes = [100.0] * 9 + [1e-9]
        direction = self.f._short_term_direction(closes, bars=10)
        assert direction == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# _score_confirm tests (pure, synchronous)
# ---------------------------------------------------------------------------


class TestScoreConfirm:
    f = CrossAssetFilter()

    # BUY scenarios
    def test_buy_confirm_rising_returns_positive_score(self) -> None:
        score, reason = self.f._score_confirm("BRENT_OIL", "BUY", direction=0.5)
        assert score > 0.0
        assert "confirm_rising" in reason

    def test_buy_confirm_falling_returns_strong_negative_score(self) -> None:
        score, reason = self.f._score_confirm("BRENT_OIL", "BUY", direction=-0.5)
        assert score < -0.3
        assert "falling_vs_BUY" in reason

    def test_buy_confirm_flat_returns_zero(self) -> None:
        score, _ = self.f._score_confirm("BRENT_OIL", "BUY", direction=0.05)
        assert score == 0.0

    # SELL scenarios
    def test_sell_confirm_falling_returns_positive_score(self) -> None:
        score, reason = self.f._score_confirm("BRENT_OIL", "SELL", direction=-0.5)
        assert score > 0.0
        assert "confirm_falling" in reason

    def test_sell_confirm_rising_returns_strong_negative_score(self) -> None:
        score, reason = self.f._score_confirm("BRENT_OIL", "SELL", direction=0.5)
        assert score < -0.3
        assert "rising_vs_SELL" in reason


# ---------------------------------------------------------------------------
# _score_context tests (pure, synchronous)
# ---------------------------------------------------------------------------


class TestScoreContext:
    f = CrossAssetFilter()

    def test_oil_buy_usa500_rising_risk_on_confirm(self) -> None:
        score, reason = self.f._score_context("USA500", "CrudeOIL", "BUY", direction=0.5)
        assert score > 0.0
        assert "risk_on" in reason

    def test_oil_buy_usa500_falling_supply_shock(self) -> None:
        score, reason = self.f._score_context("USA500", "CrudeOIL", "BUY", direction=-0.5)
        assert score > 0.0
        assert "supply_shock" in reason

    def test_oil_sell_usa500_falling_demand_destruction(self) -> None:
        score, reason = self.f._score_context("USA500", "CrudeOIL", "SELL", direction=-0.5)
        assert score > 0.0
        assert "demand_destruction" in reason

    def test_oil_sell_usa500_rising_deflationary_mild_reject(self) -> None:
        score, reason = self.f._score_context("USA500", "CrudeOIL", "SELL", direction=0.5)
        assert score < 0.0
        assert "deflationary" in reason

    def test_brent_buy_usa500_rising(self) -> None:
        score, _ = self.f._score_context("USA500", "BRENT_OIL", "BUY", direction=0.5)
        assert score > 0.0

    def test_gbpjpy_buy_usa500_rising_generic_agree(self) -> None:
        score, _ = self.f._score_context("USA500", "GBPJPY", "BUY", direction=0.5)
        assert score > 0.0

    def test_gbpjpy_sell_usa500_rising_generic_contra(self) -> None:
        score, _ = self.f._score_context("USA500", "GBPJPY", "SELL", direction=0.5)
        assert score < 0.0


# ---------------------------------------------------------------------------
# check_confirmation (async, via _StubbedFilter)
# ---------------------------------------------------------------------------


class TestCheckConfirmation:

    @pytest.mark.asyncio
    async def test_crude_buy_brent_rising_passes(self) -> None:
        f = _StubbedFilter({
            "BRENT_OIL": _rising(n=15, start=80.0, step=0.5),
            "USA500": _rising(n=15, start=4500.0, step=10.0),
        })
        score, reason = await f.check_confirmation("CrudeOIL", "BUY")
        assert score > -0.3, f"expected pass but score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_crude_buy_brent_falling_rejects(self) -> None:
        f = _StubbedFilter({
            "BRENT_OIL": _falling(n=15, start=80.0, step=0.5),
            "USA500": _flat(n=15, value=4500.0),
        })
        score, reason = await f.check_confirmation("CrudeOIL", "BUY")
        assert score < -0.3, f"expected reject but score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_crude_sell_brent_falling_passes(self) -> None:
        f = _StubbedFilter({
            "BRENT_OIL": _falling(n=15, start=80.0, step=0.5),
            "USA500": _falling(n=15, start=4500.0, step=10.0),
        })
        score, reason = await f.check_confirmation("CrudeOIL", "SELL")
        assert score > -0.3, f"expected pass but score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_crude_sell_brent_rising_rejects(self) -> None:
        f = _StubbedFilter({
            "BRENT_OIL": _rising(n=15, start=80.0, step=0.5),
            "USA500": _flat(n=15, value=4500.0),
        })
        score, reason = await f.check_confirmation("CrudeOIL", "SELL")
        assert score < -0.3, f"expected reject but score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_symbol_not_in_groups_passes_with_no_group(self) -> None:
        f = _StubbedFilter({})
        score, reason = await f.check_confirmation("WHEAT", "BUY")
        assert score == 0.0
        assert reason == "no_group"

    @pytest.mark.asyncio
    async def test_usa500_has_no_confirm_assets(self) -> None:
        # USA500 has confirm=[], context=[CrudeOIL, BRENT_OIL]
        f = _StubbedFilter({
            "CrudeOIL": _rising(n=15, start=75.0, step=0.3),
            "BRENT_OIL": _rising(n=15, start=80.0, step=0.3),
        })
        score, reason = await f.check_confirmation("USA500", "BUY")
        # No confirm assets — context only — should not reject
        assert score > -0.3, f"score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_missing_data_for_confirm_treated_as_neutral(self) -> None:
        # BRENT_OIL not in stubs → _fetch_closes raises → no_data, contribution skipped
        f = _StubbedFilter({
            "USA500": _flat(n=15, value=4500.0),
        })
        score, reason = await f.check_confirmation("CrudeOIL", "BUY")
        assert "no_data" in reason
        # Score should not be < -0.3 from missing data alone
        assert score >= -0.3, f"score={score}"

    @pytest.mark.asyncio
    async def test_all_data_missing_returns_zero(self) -> None:
        f = _StubbedFilter({})
        score, reason = await f.check_confirmation("CrudeOIL", "BUY")
        assert score == 0.0
        assert reason == "all_data_unavailable"

    @pytest.mark.asyncio
    async def test_brent_buy_crude_rising_passes(self) -> None:
        f = _StubbedFilter({
            "CrudeOIL": _rising(n=15, start=75.0, step=0.4),
            "USA500": _flat(n=15, value=4500.0),
        })
        score, reason = await f.check_confirmation("BRENT_OIL", "BUY")
        assert score > -0.3, f"score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_gbpjpy_buy_usa500_rising_mild_confirm(self) -> None:
        f = _StubbedFilter({
            "USA500": _rising(n=15, start=4500.0, step=10.0),
        })
        score, reason = await f.check_confirmation("GBPJPY", "BUY")
        assert score >= 0.0, f"score={score}, reason={reason}"

    @pytest.mark.asyncio
    async def test_case_insensitive_action(self) -> None:
        f = _StubbedFilter({
            "BRENT_OIL": _rising(n=15, start=80.0, step=0.5),
            "USA500": _flat(n=15),
        })
        score_upper, _ = await f.check_confirmation("CrudeOIL", "BUY")
        score_lower, _ = await f.check_confirmation("CrudeOIL", "buy")
        assert score_upper == pytest.approx(score_lower)
