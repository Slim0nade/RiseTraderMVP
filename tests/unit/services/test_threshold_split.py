"""
Unit tests for Phase 6 Task A1 — paper/live threshold split.

Tier 1: pure logic, no DB, no MT4, no mocks of external services.

Test matrix:
  T1  paper mode (PAPER_VALIDATION_MODE=true)  → 0.40 / 0.40
  T2  live mode  (ENABLE_LIVE_TRADING=true)    → 0.60 / 0.60
  T3  both flags set → paper wins (safer)
  T4  neither flag set → defaults to paper
  T5  fat-finger assert fires when live < paper + 0.10
  T6  fat-finger assert fires on confidence too
  T7  YAML missing → falls back to coded defaults, no crash
  T8  YAML present with custom values → values honoured
  T9  source field is "yaml" when YAML read, "default" otherwise
  T10 mode returned as "paper" / "live" string
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

# We test the helpers directly — import them after setting env so the module
# picks up a clean state each time via monkeypatch.
from src.services.live_trading_service import _load_thresholds, _resolve_trading_mode


# ---------------------------------------------------------------------------
# T1 — paper flag → paper thresholds
# ---------------------------------------------------------------------------
def test_paper_mode_returns_paper_thresholds(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPER_VALIDATION_MODE", "true")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)

    # Remove the real YAML so we always use coded defaults in this test.
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", tmp_path / "nonexistent.yaml")

    st, mc, source = _load_thresholds(is_paper=True)
    assert st == pytest.approx(0.40)
    assert mc == pytest.approx(0.40)
    assert source == "default"


# ---------------------------------------------------------------------------
# T2 — live mode → live thresholds
# ---------------------------------------------------------------------------
def test_live_mode_returns_live_thresholds(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.delenv("PAPER_VALIDATION_MODE", raising=False)
    monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)

    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", tmp_path / "nonexistent.yaml")

    st, mc, source = _load_thresholds(is_paper=False)
    assert st == pytest.approx(0.60)
    assert mc == pytest.approx(0.60)
    assert source == "default"


# ---------------------------------------------------------------------------
# T3 — both flags set → _resolve_trading_mode returns paper
# ---------------------------------------------------------------------------
def test_both_flags_set_paper_wins(monkeypatch):
    monkeypatch.setenv("PAPER_VALIDATION_MODE", "true")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ENABLE_PAPER_TRADING", "true")
    assert _resolve_trading_mode() is True


# ---------------------------------------------------------------------------
# T4 — neither flag set → defaults to paper
# ---------------------------------------------------------------------------
def test_no_flags_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("PAPER_VALIDATION_MODE", raising=False)
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)
    assert _resolve_trading_mode() is True


# ---------------------------------------------------------------------------
# T5 — fat-finger: live signal_threshold < paper + 0.10 raises AssertionError
# ---------------------------------------------------------------------------
def test_fat_finger_signal_threshold_assert(monkeypatch, tmp_path):
    bad_yaml = tmp_path / "risk.yaml"
    bad_yaml.write_text(
        "thresholds:\n"
        "  paper:\n"
        "    signal_threshold: 0.50\n"
        "    min_confidence: 0.40\n"
        "  live:\n"
        "    signal_threshold: 0.55\n"   # only 0.05 above paper — violates invariant
        "    min_confidence: 0.60\n"
    )
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", bad_yaml)

    with pytest.raises(AssertionError, match="live_signal_threshold"):
        _load_thresholds(is_paper=True)


# ---------------------------------------------------------------------------
# T6 — fat-finger: live min_confidence < paper + 0.10 raises AssertionError
# ---------------------------------------------------------------------------
def test_fat_finger_min_confidence_assert(monkeypatch, tmp_path):
    bad_yaml = tmp_path / "risk.yaml"
    bad_yaml.write_text(
        "thresholds:\n"
        "  paper:\n"
        "    signal_threshold: 0.40\n"
        "    min_confidence: 0.50\n"
        "  live:\n"
        "    signal_threshold: 0.60\n"
        "    min_confidence: 0.55\n"   # only 0.05 above paper — violates invariant
    )
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", bad_yaml)

    with pytest.raises(AssertionError, match="live_min_confidence"):
        _load_thresholds(is_paper=True)


# ---------------------------------------------------------------------------
# T7 — YAML missing → coded defaults, no crash, source="default"
# ---------------------------------------------------------------------------
def test_missing_yaml_falls_back_to_defaults(monkeypatch, tmp_path):
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", tmp_path / "does_not_exist.yaml")

    st, mc, source = _load_thresholds(is_paper=True)
    assert st == pytest.approx(0.40)
    assert mc == pytest.approx(0.40)
    assert source == "default"


# ---------------------------------------------------------------------------
# T8 — YAML present with custom values → values honoured
# ---------------------------------------------------------------------------
def test_yaml_custom_values_honoured(monkeypatch, tmp_path):
    custom_yaml = tmp_path / "risk.yaml"
    custom_yaml.write_text(
        "thresholds:\n"
        "  paper:\n"
        "    signal_threshold: 0.35\n"
        "    min_confidence: 0.38\n"
        "  live:\n"
        "    signal_threshold: 0.65\n"
        "    min_confidence: 0.68\n"
    )
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", custom_yaml)

    st_paper, mc_paper, source = _load_thresholds(is_paper=True)
    assert st_paper == pytest.approx(0.35)
    assert mc_paper == pytest.approx(0.38)
    assert source == "yaml"

    st_live, mc_live, source_live = _load_thresholds(is_paper=False)
    assert st_live == pytest.approx(0.65)
    assert mc_live == pytest.approx(0.68)
    assert source_live == "yaml"


# ---------------------------------------------------------------------------
# T9 — source field "yaml" vs "default"
# ---------------------------------------------------------------------------
def test_source_field_yaml_when_file_present(monkeypatch, tmp_path):
    good_yaml = tmp_path / "risk.yaml"
    good_yaml.write_text(
        "thresholds:\n"
        "  paper:\n"
        "    signal_threshold: 0.40\n"
        "    min_confidence: 0.40\n"
        "  live:\n"
        "    signal_threshold: 0.60\n"
        "    min_confidence: 0.60\n"
    )
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", good_yaml)

    _, _, source = _load_thresholds(is_paper=True)
    assert source == "yaml"


def test_source_field_default_when_file_absent(monkeypatch, tmp_path):
    import src.services.live_trading_service as svc_mod
    monkeypatch.setattr(svc_mod, "_RISK_YAML", tmp_path / "missing.yaml")

    _, _, source = _load_thresholds(is_paper=False)
    assert source == "default"


# ---------------------------------------------------------------------------
# T10 — resolve_trading_mode returns bool (paper=True / live=False)
# ---------------------------------------------------------------------------
def test_resolve_mode_paper_flag(monkeypatch):
    monkeypatch.setenv("PAPER_VALIDATION_MODE", "true")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)
    assert _resolve_trading_mode() is True


def test_resolve_mode_live_flag(monkeypatch):
    monkeypatch.delenv("PAPER_VALIDATION_MODE", raising=False)
    monkeypatch.delenv("ENABLE_PAPER_TRADING", raising=False)
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    assert _resolve_trading_mode() is False


def test_resolve_mode_enable_paper_flag(monkeypatch):
    monkeypatch.delenv("PAPER_VALIDATION_MODE", raising=False)
    monkeypatch.setenv("ENABLE_PAPER_TRADING", "true")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    assert _resolve_trading_mode() is True
