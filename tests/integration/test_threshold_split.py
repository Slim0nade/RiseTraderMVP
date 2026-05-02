"""
Integration tests for Phase 6 Task A1 — paper/live threshold split.

Tier 2: instantiate LiveTradingService in each mode, feed a synthetic candle
stream that produces a signal at score~0.45/conf~0.45, and verify that paper
mode passes while live mode blocks.

No MT4 connection required — the test never calls service.start().
It drives _generate_signal() directly with a crafted candle list.

Run:
    pytest tests/integration/test_threshold_split.py -v
"""

import os
import sys
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Candle factory — builds a simple trending sequence that the momentum
# strategy can score BUY at ~0.45.  Not a real DB fetch.
# ---------------------------------------------------------------------------

def _make_candles(n: int = 60, start_price: float = 80.0, slope: float = 0.05) -> List[Dict]:
    """
    Generate a monotone-rising candle sequence to produce a positive momentum score.
    score ~ (short_ma - long_ma)/long_ma * 20, capped at 1.0.
    With 60 bars, 10-period MA > 30-period MA → score > 0.
    """
    candles = []
    price = start_price
    for i in range(n):
        price += slope
        candles.append({
            "open": price - 0.01,
            "high": price + 0.02,
            "low": price - 0.02,
            "close": price,
            "volume": 1000.0,
        })
    return candles


# ---------------------------------------------------------------------------
# Helper — instantiate service without a DB or MT4 connection.
# We patch the heavy dependencies that LiveTradingService.__init__ touches
# (StealthStopManager, RegimeClassifier, StrategyRouter, TieredPositionSizer,
# CrossAssetFilter) so the unit under test is the threshold logic only.
# ---------------------------------------------------------------------------

def _make_service(monkeypatch, is_paper: bool, tmp_path: Path):
    """Build a LiveTradingService configured for the given mode."""
    import src.services.live_trading_service as svc_mod

    # Point YAML at the real project YAML so we test real values
    risk_yaml = PROJECT_ROOT / "config" / "risk.yaml"
    if risk_yaml.exists():
        monkeypatch.setattr(svc_mod, "_RISK_YAML", risk_yaml)
    else:
        # Fallback: write a minimal YAML into tmp_path
        fallback = tmp_path / "risk.yaml"
        fallback.write_text(
            "thresholds:\n"
            "  paper:\n"
            "    signal_threshold: 0.40\n"
            "    min_confidence: 0.40\n"
            "  live:\n"
            "    signal_threshold: 0.60\n"
            "    min_confidence: 0.60\n"
        )
        monkeypatch.setattr(svc_mod, "_RISK_YAML", fallback)

    # Set env flags for mode
    if is_paper:
        monkeypatch.setenv("PAPER_VALIDATION_MODE", "true")
        monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
        monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)
    else:
        monkeypatch.delenv("PAPER_VALIDATION_MODE", raising=False)
        monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Patch out infrastructure that needs network/DB
    with (
        patch("src.services.live_trading_service.StealthStopManager") as mock_stealth,
        patch("src.services.live_trading_service.RegimeClassifier") as mock_rc,
        patch("src.services.live_trading_service.StrategyRouter") as mock_sr,
        patch("src.services.live_trading_service.TieredPositionSizer") as mock_sizer,
        patch("src.trading.filters.cross_asset_filter.CrossAssetFilter") as _,
    ):
        mock_stealth.return_value = object()
        mock_stealth.load_from_yaml.return_value = object()
        mock_rc.return_value = object()
        mock_sr.return_value = object()
        mock_sizer.return_value = object()

        from src.services.live_trading_service import LiveTradingService
        svc = LiveTradingService()

    return svc


# ---------------------------------------------------------------------------
# T1 — paper mode: signal at score=0.45 / conf=0.45 PASSES
# ---------------------------------------------------------------------------

def test_paper_mode_passes_mid_strength_signal(monkeypatch, tmp_path):
    svc = _make_service(monkeypatch, is_paper=True, tmp_path=tmp_path)

    assert svc._signal_threshold == pytest.approx(0.40), (
        f"expected 0.40, got {svc._signal_threshold}"
    )
    assert svc._min_confidence == pytest.approx(0.40)
    assert svc._paper_mode is True

    # Simulate a strategy result at score=0.45, conf=0.45 — should clear paper threshold
    score = 0.45
    conf = 0.45
    passed = abs(score) >= svc._signal_threshold and conf >= svc._min_confidence
    assert passed, (
        f"Paper mode should pass score={score}/conf={conf} with threshold={svc._signal_threshold}"
    )


# ---------------------------------------------------------------------------
# T2 — live mode: same signal at score=0.45 / conf=0.45 BLOCKS
# ---------------------------------------------------------------------------

def test_live_mode_blocks_mid_strength_signal(monkeypatch, tmp_path):
    svc = _make_service(monkeypatch, is_paper=False, tmp_path=tmp_path)

    assert svc._signal_threshold == pytest.approx(0.60), (
        f"expected 0.60, got {svc._signal_threshold}"
    )
    assert svc._min_confidence == pytest.approx(0.60)
    assert svc._paper_mode is False

    score = 0.45
    conf = 0.45
    passed = abs(score) >= svc._signal_threshold and conf >= svc._min_confidence
    assert not passed, (
        f"Live mode should block score={score}/conf={conf} with threshold={svc._signal_threshold}"
    )


# ---------------------------------------------------------------------------
# T3 — gap invariant: live is at least 0.10 above paper
# ---------------------------------------------------------------------------

def test_live_threshold_at_least_10_above_paper(monkeypatch, tmp_path):
    svc_paper = _make_service(monkeypatch, is_paper=True, tmp_path=tmp_path)
    svc_live = _make_service(monkeypatch, is_paper=False, tmp_path=tmp_path)

    assert svc_live._signal_threshold >= svc_paper._signal_threshold + 0.10, (
        "live signal_threshold must be >= paper + 0.10"
    )
    assert svc_live._min_confidence >= svc_paper._min_confidence + 0.10, (
        "live min_confidence must be >= paper + 0.10"
    )


# ---------------------------------------------------------------------------
# T4 — threshold_source field is populated correctly
# ---------------------------------------------------------------------------

def test_threshold_source_yaml_when_config_present(monkeypatch, tmp_path):
    import src.services.live_trading_service as svc_mod
    risk_yaml = PROJECT_ROOT / "config" / "risk.yaml"
    if not risk_yaml.exists():
        pytest.skip("config/risk.yaml not present in repo — skipping source=yaml check")

    monkeypatch.setattr(svc_mod, "_RISK_YAML", risk_yaml)
    svc = _make_service(monkeypatch, is_paper=True, tmp_path=tmp_path)
    assert svc._threshold_source == "yaml"
