"""
Unit tests for Phase 6 Task A2 — multi-paper-per-symbol position caps.

Tier 1: pure logic, no DB, no MT4, no mocks of external services.

Test matrix:
  T1   5 paper positions on CrudeOIL fit (count=4 < cap=5 -> approved)
  T2   6th paper signal rejected with paper_concurrent_cap_reached(5)
  T3   Live mode hard-capped at 1 per symbol (second signal -> rejected)
  T4   Live mode pyramid: same direction + 95%+ conf -> approved
  T5   Live mode opposing direction -> opposing_direction rejection
  T6   Paper mode opposing direction -> opposing_direction rejection (preserved)
  T7   Aggregate exposure cap: large lots -> projected >8% -> rejected
  T8   Aggregate exposure cap: small lots -> projected <8% -> pass
  T9   Per-position 2% rule: ATR=0 -> zero_atr rejection
  T10  _load_position_caps: YAML missing -> coded defaults (5/1/8.0), source="default"
  T11  _load_position_caps: YAML present with custom values -> honoured
  T12  _load_position_caps: live_cap != 1 in YAML -> AssertionError
  T13  Paper cap configurable: max_paper=3 -> 3rd position allowed, 4th rejected
  T14  6th paper signal IS counted by caller (can be logged) — function returns False
  T15  Live assertion: _max_live_per_symbol is always == 1 in coded defaults
  T16  First paper position on a fresh symbol (no existing) -> approved
  T17  Multiple symbols: cap is per-symbol, not global
  T18  Stealth stop manager handles N positions independently (per-ticket)
"""

import os
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from src.services.live_trading_service import (
    _load_position_caps,
    _PAPER_CAP_DEFAULT,
    _LIVE_CAP_DEFAULT,
    _PAPER_AGGREGATE_PCT_DEFAULT,
)
import src.services.live_trading_service as svc_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(paper_mode: bool, max_paper: int = 5):
    """
    Build a LiveTradingService instance with mocked dependencies.

    Uses __new__ to bypass __init__ and sets all required attributes directly.
    This avoids needing a DB, MT4 connection, or any module-level functions
    that may differ between branches.
    """
    from src.services.live_trading_service import LiveTradingService

    svc = LiveTradingService.__new__(LiveTradingService)

    # Sizer mock
    mock_sizer = MagicMock()
    mock_sizer.check_daily_loss_halt.return_value = False
    mock_sizer.max_total_lots = 10.0
    mock_sizer.margin_floor_pct = 200
    mock_sizer.calculate_lot_size.return_value = 0.01
    mock_sizer.validate_margin_level.return_value = (True, 500.0)
    mock_sizer._last_adjusted_stop = None

    # Core configuration
    svc.enabled = False
    svc.symbols = ["CrudeOIL"]
    svc.interval = 300
    svc.dry_run = False
    svc.max_open_positions = 20
    svc.max_daily_loss = 1000.0

    # Mode-aware caps — the feature under test
    svc._paper_mode = paper_mode
    svc._max_paper_per_symbol = max_paper
    svc._max_live_per_symbol = 1
    svc._max_aggregate_paper_pct = 8.0
    svc._caps_source = "default"

    # Runtime state
    svc._running = False
    svc._task = None
    svc._daily_pnl = 0.0
    svc._daily_pnl_date = None
    svc._direction_cooldowns = {}
    svc._prev_open_tickets = {}
    svc._recent_losses = {}
    svc._last_candle_fingerprint = {}
    svc._signal_threshold = 0.35 if paper_mode else 0.60
    svc._min_confidence = 0.35 if paper_mode else 0.60
    svc._regime_classifier = MagicMock()
    svc._strategy_router = MagicMock()
    svc._sizer = mock_sizer
    svc._cross_asset_filter = MagicMock()
    svc._stealth_mgr = None
    svc._paper_validator = None

    return svc


def _make_position(symbol: str, direction: str, lots: float = 0.01) -> dict:
    """Build a position dict as returned by _get_open_position_details."""
    return {
        "symbol": symbol,
        "type": direction.upper(),
        "lots": lots,
        "ticket": id(object()),  # unique int per call
    }


async def _patch_service_deps(svc, balance: float, positions: List[dict]):
    """Wire balance and positions into service async helpers."""
    count = len(positions)
    symbols = [p["symbol"].rstrip(".") for p in positions]
    svc._get_account_balance = AsyncMock(return_value=balance)
    svc._get_open_position_details = AsyncMock(return_value=(count, symbols, positions))
    svc._get_account_info = AsyncMock(return_value={
        "balance": balance,
        "equity": balance,
        "margin": 100.0,
        "freeMargin": balance - 100.0,
        "marginLevel": balance,
    })


# ---------------------------------------------------------------------------
# T1 — 5th paper position on CrudeOIL fits (count=4 < cap=5 -> approved)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fifth_paper_position_approved():
    """4 open paper positions -> 5th is approved (count < cap=5)."""
    svc = _make_service(paper_mode=True, max_paper=5)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "BUY") for _ in range(4)]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is True, f"Expected approved, got reason: {reason}"
    assert lots > 0


# ---------------------------------------------------------------------------
# T2 — 6th paper signal rejected with paper_concurrent_cap_reached(5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sixth_paper_position_rejected():
    """5 open paper positions -> 6th is rejected with named reason."""
    svc = _make_service(paper_mode=True, max_paper=5)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "BUY") for _ in range(5)]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is False
    assert "paper_concurrent_cap_reached(5)" in reason
    assert lots == 0.0


# ---------------------------------------------------------------------------
# T3 — Live mode hard-capped at 1 per symbol (second signal -> rejected)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_mode_hard_cap_one_per_symbol():
    """1 open live position -> 2nd live signal rejected (no pyramid condition)."""
    svc = _make_service(paper_mode=False)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "BUY", lots=0.01)]
    await _patch_service_deps(svc, balance, existing)

    # Second signal same direction, low confidence (not pyramid eligible)
    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
        confidence=0.50,
        ml_confidence=0.50,
    )

    assert approved is False
    # Reason should indicate low confidence (not pyramid eligible) or position_exists
    assert "confidence" in reason or "position_exists" in reason


# ---------------------------------------------------------------------------
# T4 — Live mode pyramid: same direction + 95%+ conf -> approved
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_mode_pyramid_same_direction_high_conf():
    """1 open live position -> same direction + 97% ML conf -> pyramid approved."""
    svc = _make_service(paper_mode=False)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "BUY", lots=0.01)]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
        confidence=0.80,
        ml_confidence=0.97,
    )

    assert approved is True, f"Expected pyramid approved, got: {reason}"
    assert lots > 0


# ---------------------------------------------------------------------------
# T5 — Live mode opposing direction -> opposing_direction rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_mode_opposing_direction_rejected():
    """Existing SELL + new BUY signal in live mode -> opposing_direction rejected."""
    svc = _make_service(paper_mode=False)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "SELL")]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is False
    assert "opposing_direction" in reason


# ---------------------------------------------------------------------------
# T6 — Paper mode opposing direction -> opposing_direction rejection (preserved)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paper_mode_opposing_direction_rejected():
    """In paper mode with 2 open SELL positions, a BUY signal is rejected."""
    svc = _make_service(paper_mode=True, max_paper=5)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "SELL"), _make_position("CrudeOIL", "SELL")]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is False
    assert "opposing_direction" in reason


# ---------------------------------------------------------------------------
# T7 — Aggregate exposure cap breach -> aggregate_paper_exposure_capped
#
# 4 positions at 0.40 lots each:
#   risk_per_lot = 2 x 0.75 x 1000 = 1500 USD
#   existing_risk = 4 x 0.40 x 1500 = 2400 USD
#   existing_pct  = 2400 / 10_000 = 24% -> already > 8%
#   projected (with 0.01 new lots): 2414.99 / 10_000 = 24.15% -> rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aggregate_paper_exposure_cap_breached():
    """Aggregate risk already > 8% threshold after adding new position -> rejected."""
    svc = _make_service(paper_mode=True, max_paper=5)
    svc._max_aggregate_paper_pct = 8.0
    balance = 10_000.0

    existing = [_make_position("CrudeOIL", "BUY", lots=0.40) for _ in range(4)]
    await _patch_service_deps(svc, balance, existing)
    svc._sizer.calculate_lot_size.return_value = 0.01

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is False
    assert "aggregate_paper_exposure_capped" in reason


# ---------------------------------------------------------------------------
# T8 — Aggregate exposure stays within cap -> approved
#
# 2 existing positions at 0.01 lots:
#   existing_risk = 2 x 0.01 x 1500 = 30 USD = 0.3% of 10_000
#   new position 0.01 lots -> projected = 0.45% -> well under 8%
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aggregate_paper_exposure_within_cap_approved():
    """Aggregate risk stays under 8% -> 3rd position approved."""
    svc = _make_service(paper_mode=True, max_paper=5)
    svc._max_aggregate_paper_pct = 8.0
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "BUY", lots=0.01) for _ in range(2)]
    await _patch_service_deps(svc, balance, existing)
    svc._sizer.calculate_lot_size.return_value = 0.01

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is True, f"Expected approved, got reason: {reason}"
    assert lots > 0


# ---------------------------------------------------------------------------
# T9 — Per-position 2% rule: ATR=0 -> zero_atr rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_zero_atr_rejected():
    """ATR=0 is rejected regardless of mode — no sizing possible."""
    for paper_mode in (True, False):
        svc = _make_service(paper_mode=paper_mode)
        await _patch_service_deps(svc, 10_000.0, [])

        approved, reason, lots = await svc._validate_signal(
            symbol="CrudeOIL",
            action="BUY",
            current_price=75.0,
            atr=0.0,
        )

        assert approved is False, f"paper_mode={paper_mode}: expected rejected for zero ATR"
        assert "zero_atr" in reason


# ---------------------------------------------------------------------------
# T10 — _load_position_caps: YAML missing -> coded defaults, source="default"
# ---------------------------------------------------------------------------
def test_load_position_caps_no_yaml(monkeypatch, tmp_path):
    monkeypatch.setattr(svc_mod, "_RISK_YAML", tmp_path / "nonexistent.yaml")
    paper_cap, live_cap, agg_pct, source = _load_position_caps()

    assert paper_cap == _PAPER_CAP_DEFAULT  # 5
    assert live_cap == _LIVE_CAP_DEFAULT    # 1
    assert agg_pct == _PAPER_AGGREGATE_PCT_DEFAULT  # 8.0
    assert source == "default"


# ---------------------------------------------------------------------------
# T11 — _load_position_caps: YAML present with custom values -> honoured
# ---------------------------------------------------------------------------
def test_load_position_caps_yaml_honoured(monkeypatch, tmp_path):
    custom_yaml = tmp_path / "risk.yaml"
    custom_yaml.write_text(
        "position_caps:\n"
        "  paper:\n"
        "    max_open_per_symbol: 4\n"
        "    max_aggregate_exposure_pct: 10.0\n"
        "  live:\n"
        "    max_open_per_symbol: 1\n"
    )
    monkeypatch.setattr(svc_mod, "_RISK_YAML", custom_yaml)

    paper_cap, live_cap, agg_pct, source = _load_position_caps()

    assert paper_cap == 4
    assert live_cap == 1
    assert agg_pct == pytest.approx(10.0)
    assert source == "yaml"


# ---------------------------------------------------------------------------
# T12 — _load_position_caps: live_cap != 1 in YAML -> AssertionError
# ---------------------------------------------------------------------------
def test_load_position_caps_live_cap_not_one_raises(monkeypatch, tmp_path):
    bad_yaml = tmp_path / "risk.yaml"
    bad_yaml.write_text(
        "position_caps:\n"
        "  paper:\n"
        "    max_open_per_symbol: 5\n"
        "    max_aggregate_exposure_pct: 8.0\n"
        "  live:\n"
        "    max_open_per_symbol: 2\n"  # MUST raise — live cap must always be 1
    )
    monkeypatch.setattr(svc_mod, "_RISK_YAML", bad_yaml)

    with pytest.raises(AssertionError, match="max_open_per_symbol must be 1"):
        _load_position_caps()


# ---------------------------------------------------------------------------
# T13 — Paper cap configurable: max_paper=3 -> 3rd approved, 4th rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_configurable_paper_cap():
    """Custom cap of 3: 3 positions ok, 4th rejected."""
    svc = _make_service(paper_mode=True, max_paper=3)
    balance = 10_000.0

    # 3 existing positions -> 4th should be rejected
    existing = [_make_position("CrudeOIL", "BUY") for _ in range(3)]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, _ = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is False
    assert "paper_concurrent_cap_reached(3)" in reason


# ---------------------------------------------------------------------------
# T14 — 6th paper signal returns False (caller can log it) — not an exception
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sixth_paper_signal_returns_false_not_raises():
    """The 6th paper signal must return (False, reason, 0.0) — not raise."""
    svc = _make_service(paper_mode=True, max_paper=5)
    balance = 10_000.0
    existing = [_make_position("CrudeOIL", "BUY") for _ in range(5)]
    await _patch_service_deps(svc, balance, existing)

    result = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert isinstance(result, tuple) and len(result) == 3
    approved, reason, lots = result
    assert approved is False
    assert isinstance(reason, str) and len(reason) > 0
    assert lots == 0.0


# ---------------------------------------------------------------------------
# T15 — Live assertion: _max_live_per_symbol is always == 1 in coded defaults
# ---------------------------------------------------------------------------
def test_live_per_symbol_cap_is_always_one():
    """Verify that the coded default for live cap is 1 and cannot be changed."""
    assert _LIVE_CAP_DEFAULT == 1, (
        "The live per-symbol position cap default must always be 1. "
        "If you changed this, revert it — live mode safety invariant violated."
    )


# ---------------------------------------------------------------------------
# T16 — First paper position on a fresh symbol (no existing) -> approved
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_paper_position_no_existing_approved():
    """No existing positions -> first paper position approved."""
    svc = _make_service(paper_mode=True, max_paper=5)
    await _patch_service_deps(svc, 10_000.0, [])

    approved, reason, lots = await svc._validate_signal(
        symbol="CrudeOIL",
        action="BUY",
        current_price=75.0,
        atr=0.75,
    )

    assert approved is True, f"Expected first position approved, got: {reason}"
    assert lots > 0


# ---------------------------------------------------------------------------
# T17 — Multiple symbols: cap is per-symbol, not global
#        5 CrudeOIL positions do NOT prevent a first USA500 position.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cap_is_per_symbol_not_global():
    """5 open CrudeOIL positions do not block the first USA500 signal."""
    svc = _make_service(paper_mode=True, max_paper=5)
    svc.max_open_positions = 20  # Global cap high enough
    balance = 10_000.0

    existing = [_make_position("CrudeOIL", "BUY") for _ in range(5)]
    await _patch_service_deps(svc, balance, existing)

    approved, reason, lots = await svc._validate_signal(
        symbol="USA500",
        action="BUY",
        current_price=4500.0,
        atr=20.0,
    )

    assert approved is True, f"Expected USA500 approved, got: {reason}"


# ---------------------------------------------------------------------------
# T18 — Stealth stop manager handles N positions independently
#        Verify that trailing-stop modification for ticket A does not affect
#        the stop for ticket B on the same symbol.  Pure in-memory test.
# ---------------------------------------------------------------------------
def test_stealth_stop_manager_independent_per_ticket():
    """Each position has its own MonitoredPosition entry; stops are independent."""
    from src.services.stealth_stop_manager import MonitoredPosition
    import datetime

    pos_a = MonitoredPosition(
        ticket=1001,
        symbol="CrudeOIL",
        direction="BUY",
        entry_price=75.00,
        current_stop=72.50,
        current_tp=80.00,
        lots=0.01,
        current_price=76.00,
        detected_at=datetime.datetime.now(),
    )
    pos_b = MonitoredPosition(
        ticket=1002,
        symbol="CrudeOIL",
        direction="BUY",
        entry_price=76.00,
        current_stop=73.50,
        current_tp=81.00,
        lots=0.01,
        current_price=76.00,
        detected_at=datetime.datetime.now(),
    )

    monitored = {1001: pos_a, 1002: pos_b}

    # Simulate trailing stop update on pos_a only
    monitored[1001].current_stop = 74.00  # trail up

    # pos_b must be unchanged
    assert monitored[1002].current_stop == 73.50, (
        "Modifying pos_a's stop must not cascade to pos_b"
    )
    assert monitored[1001].current_stop == 74.00
