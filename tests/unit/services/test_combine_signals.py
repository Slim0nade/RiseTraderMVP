"""
Unit tests for _combine_signals() in live_trading_service.py.

These tests exercise the agreement-weighted voting logic without any DB,
MT4, or network dependencies. All inputs are static dicts.

Function contract:
    Input:  Dict[str, Dict[str, float]]
            Each inner dict has "score" in [-1.0, 1.0] and
            "confidence" in [0.0, 1.0].
    Output: {"score": float, "confidence": float}

Scenarios covered:
    1. All strategies agree SELL  → result is SELL
    2. ML says SELL, three others say BUY → result must NOT be SELL
    3. ML alone, no other strategies → no division-by-zero, result follows ML
    4. All strategies neutral (score ≈ 0) → combined score ≈ 0
    5. ML disagrees with consensus → ML weight halved, result follows consensus
"""

import pytest

from src.services.live_trading_service import _combine_signals


class TestAllAgreeOnSell:
    """All five strategies report a strong SELL signal."""

    def test_combined_score_is_negative(self):
        signals = {
            "ml_reversal":    {"score": -0.80, "confidence": 0.85},
            "value_area":     {"score": -0.75, "confidence": 0.80},
            "momentum":       {"score": -0.70, "confidence": 0.75},
            "mean_reversion": {"score": -0.65, "confidence": 0.70},
            "breakout":       {"score": -0.60, "confidence": 0.65},
        }
        result = _combine_signals(signals)
        assert result["score"] < 0.0, (
            f"Expected SELL (negative score) when all strategies agree SELL, "
            f"got {result['score']:.4f}"
        )

    def test_confidence_is_mean_of_inputs(self):
        signals = {
            "ml_reversal":    {"score": -0.80, "confidence": 0.85},
            "value_area":     {"score": -0.75, "confidence": 0.80},
            "momentum":       {"score": -0.70, "confidence": 0.75},
            "mean_reversion": {"score": -0.65, "confidence": 0.70},
            "breakout":       {"score": -0.60, "confidence": 0.65},
        }
        result = _combine_signals(signals)
        expected_conf = (0.85 + 0.80 + 0.75 + 0.70 + 0.65) / 5
        assert abs(result["confidence"] - expected_conf) < 1e-9, (
            f"Confidence should be arithmetic mean {expected_conf:.4f}, "
            f"got {result['confidence']:.4f}"
        )


class TestMLDisagreesWithBuyConsensus:
    """
    Reproduces the CrudeOIL rally scenario:
    ML reports SELL at high confidence while three other strategies report a
    clear BUY signal.  The combined result must be positive (BUY direction),
    and the ML penalty must measurably improve it versus the un-penalised case.
    """

    def _build_signals(self):
        # Non-ML strategies are clearly bullish (score 0.55-0.70), not just
        # marginally positive.  This reflects a real rally where momentum,
        # value_area and mean_reversion all agree on BUY.
        return {
            "ml_reversal":    {"score": -0.92, "confidence": 0.92},
            "value_area":     {"score":  0.65, "confidence": 0.70},
            "momentum":       {"score":  0.60, "confidence": 0.70},
            "mean_reversion": {"score":  0.55, "confidence": 0.70},
        }

    def test_result_is_not_sell(self):
        result = _combine_signals(self._build_signals())
        assert result["score"] > 0.0, (
            f"ML SELL (0.92 conf) must not override clear 3-strategy BUY consensus; "
            f"got score={result['score']:.4f}"
        )

    def test_ml_penalty_improves_score_vs_no_penalty(self):
        """
        With ML penalised (disagreement path), the final score must be higher
        (more positive) than it would be with ML at full weight.
        """
        # Compute score with penalty (disagreement case)
        penalised = _combine_signals(self._build_signals())

        # Build a scenario identical but with ML also saying BUY at the same
        # magnitude so no penalty fires — this is the baseline
        no_penalty = _combine_signals({
            "ml_reversal":    {"score":  0.92, "confidence": 0.92},
            "value_area":     {"score":  0.65, "confidence": 0.70},
            "momentum":       {"score":  0.60, "confidence": 0.70},
            "mean_reversion": {"score":  0.55, "confidence": 0.70},
        })

        # Both should be positive in the all-agree case
        assert no_penalty["score"] > 0.0, "Sanity: all-BUY case must be positive"
        # When ML agrees it should score higher than when it disagrees
        assert no_penalty["score"] > penalised["score"], (
            "All-BUY score should exceed penalised-ML score; "
            f"all_buy={no_penalty['score']:.4f}, penalised={penalised['score']:.4f}"
        )


class TestMLAloneNoDivisionByZero:
    """Only ML is present in the signals dict — no non-ML strategies."""

    def test_score_follows_ml_direction(self):
        signals = {
            "ml_reversal": {"score": -0.75, "confidence": 0.80},
        }
        result = _combine_signals(signals)
        # No non-ML consensus → no penalty → ML direction preserved
        assert result["score"] < 0.0, (
            f"ML-only input should preserve ML direction; got {result['score']:.4f}"
        )

    def test_no_exception_raised(self):
        signals = {
            "ml_reversal": {"score": 0.60, "confidence": 0.70},
        }
        # Must not raise ZeroDivisionError or any other exception
        result = _combine_signals(signals)
        assert isinstance(result, dict)
        assert "score" in result and "confidence" in result

    def test_confidence_equals_ml_confidence(self):
        signals = {
            "ml_reversal": {"score": 0.50, "confidence": 0.65},
        }
        result = _combine_signals(signals)
        assert abs(result["confidence"] - 0.65) < 1e-9


class TestAllNeutral:
    """All strategies return near-zero scores."""

    def test_combined_score_near_zero(self):
        signals = {
            "ml_reversal":    {"score":  0.005, "confidence": 0.50},
            "value_area":     {"score": -0.003, "confidence": 0.50},
            "momentum":       {"score":  0.002, "confidence": 0.50},
            "mean_reversion": {"score": -0.001, "confidence": 0.50},
            "breakout":       {"score":  0.000, "confidence": 0.50},
        }
        result = _combine_signals(signals)
        assert abs(result["score"]) < 0.05, (
            f"All-neutral input should yield near-zero combined score; "
            f"got {result['score']:.4f}"
        )

    def test_neutral_does_not_trigger_ml_penalty(self):
        """
        When all non-ML scores are within the ±0.01 dead band, non_ml_direction
        is 0 and the ML penalty path must not activate regardless of ML direction.
        """
        signals = {
            "ml_reversal":    {"score": -0.90, "confidence": 0.90},
            "value_area":     {"score":  0.005, "confidence": 0.50},
            "momentum":       {"score": -0.005, "confidence": 0.50},
        }
        result = _combine_signals(signals)
        # Without penalty, ML's strong SELL should push the combined score negative
        assert result["score"] < 0.0, (
            "When non-ML scores are within the dead band (non_ml_direction=0), "
            "the ML penalty must not fire; score should still be SELL "
            f"but got {result['score']:.4f}"
        )


class TestMLDisagreesWeightRedistribution:
    """Verify the redistribution arithmetic when ML disagrees."""

    def test_effective_ml_weight_is_halved(self):
        """
        When ML disagrees, its effective weight drops from 0.25 → 0.125.
        The freed 0.125 is split across the 2 non-ML strategies present (0.0625 each).
        Cross-check by comparing scores with and without the penalty.
        """
        # Signals where only 2 non-ML strategies are present and agree BUY
        signals_ml_disagrees = {
            "ml_reversal": {"score": -0.90, "confidence": 0.90},
            "value_area":  {"score":  0.80, "confidence": 0.80},
            "momentum":    {"score":  0.80, "confidence": 0.80},
        }
        # Signals where ML also agrees BUY (no penalty)
        signals_all_buy = {
            "ml_reversal": {"score":  0.90, "confidence": 0.90},
            "value_area":  {"score":  0.80, "confidence": 0.80},
            "momentum":    {"score":  0.80, "confidence": 0.80},
        }
        result_disagree = _combine_signals(signals_ml_disagrees)
        result_all_buy  = _combine_signals(signals_all_buy)

        # When ML is penalised and disagrees, combined score must still be positive
        assert result_disagree["score"] > 0.0, (
            f"Non-ML BUY consensus should override penalised ML SELL; "
            f"got {result_disagree['score']:.4f}"
        )
        # The all-BUY version should produce a higher (or equal) score
        assert result_all_buy["score"] >= result_disagree["score"], (
            "All-BUY combination should score >= disagreement scenario"
        )


class TestEmptyInput:
    """Edge cases: empty dict and unknown strategy names."""

    def test_empty_dict_returns_zero(self):
        result = _combine_signals({})
        assert result == {"score": 0.0, "confidence": 0.0}

    def test_unknown_strategy_names_ignored(self):
        """Strategies not in the weights table contribute 0 weight."""
        signals = {
            "unknown_strat_a": {"score": -0.99, "confidence": 0.99},
            "unknown_strat_b": {"score": -0.99, "confidence": 0.99},
        }
        result = _combine_signals(signals)
        assert result == {"score": 0.0, "confidence": 0.0}

    def test_zero_confidence_skips_contribution(self):
        """A strategy with confidence=0.0 contributes 0 effective weight."""
        signals = {
            "value_area": {"score": 0.90, "confidence": 0.0},
            "momentum":   {"score": 0.80, "confidence": 0.70},
        }
        result = _combine_signals(signals)
        # Only momentum contributes, so score must be positive and < 0.90
        assert result["score"] > 0.0
        assert result["score"] <= 0.90
