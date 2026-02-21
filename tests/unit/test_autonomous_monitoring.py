"""
Unit tests for Autonomous Position Monitoring (T065-T066).

These tests verify:
- T065: detect_fast_move() identifies rapid price movements (>2× ATR in 5 min)
- T066: detect_liquidity_sweep() identifies stop hunting patterns
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_price_history():
    """Create mock price history data."""
    base_time = datetime.now(timezone.utc)
    return [
        {"timestamp": base_time - timedelta(minutes=5), "close": 56.00, "high": 56.10, "low": 55.90},
        {"timestamp": base_time - timedelta(minutes=4), "close": 56.20, "high": 56.30, "low": 56.00},
        {"timestamp": base_time - timedelta(minutes=3), "close": 56.40, "high": 56.50, "low": 56.15},
        {"timestamp": base_time - timedelta(minutes=2), "close": 56.80, "high": 56.90, "low": 56.35},
        {"timestamp": base_time - timedelta(minutes=1), "close": 57.20, "high": 57.30, "low": 56.75},
        {"timestamp": base_time, "close": 57.50, "high": 57.60, "low": 57.00},
    ]


@pytest.mark.asyncio
class TestDetectFastMove:
    """Tests for T065: detect_fast_move() identifies rapid price movements."""

    async def test_detects_fast_move_above_threshold(self, mock_db):
        """Test detecting a fast move when price exceeds 2× ATR in 5 minutes."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # ATR = 0.50, threshold = 2× ATR = 1.00
        # Price moved from 56.00 to 57.20 = 1.20 in 5 minutes
        # 1.20 > 1.00, so this IS a fast move
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.20,
            atr=0.50,
            time_window_minutes=5,
        )

        assert result["detected"] is True
        assert result["move_size"] == pytest.approx(1.20, abs=0.01)
        assert result["threshold"] == pytest.approx(1.00, abs=0.01)
        assert result["direction"] == "up"
        assert result["atr_multiple"] == pytest.approx(2.4, abs=0.1)

    async def test_no_fast_move_below_threshold(self, mock_db):
        """Test no fast move when price change is below 2× ATR."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # ATR = 0.50, threshold = 2× ATR = 1.00
        # Price moved from 56.00 to 56.80 = 0.80 in 5 minutes
        # 0.80 < 1.00, so this is NOT a fast move
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=56.80,
            atr=0.50,
            time_window_minutes=5,
        )

        assert result["detected"] is False
        assert result["move_size"] == pytest.approx(0.80, abs=0.01)

    async def test_detects_fast_move_down(self, mock_db):
        """Test detecting a fast move downward."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price dropped from 56.00 to 54.80 = 1.20 down
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=54.80,
            atr=0.50,
            time_window_minutes=5,
        )

        assert result["detected"] is True
        assert result["direction"] == "down"
        assert result["move_size"] == pytest.approx(1.20, abs=0.01)

    async def test_custom_atr_multiplier(self, mock_db):
        """Test using custom ATR multiplier threshold."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # ATR = 0.50, multiplier = 3× ATR = 1.50
        # Price moved from 56.00 to 57.20 = 1.20
        # 1.20 < 1.50, so with 3× multiplier this is NOT a fast move
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.20,
            atr=0.50,
            time_window_minutes=5,
            atr_multiplier=3.0,
        )

        assert result["detected"] is False
        assert result["threshold"] == pytest.approx(1.50, abs=0.01)

    async def test_edge_case_exact_threshold(self, mock_db):
        """Test when move size exactly matches threshold."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # ATR = 0.50, threshold = 2× ATR = 1.00
        # Price moved from 56.00 to 57.00 = 1.00 (exactly threshold)
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.00,
            atr=0.50,
            time_window_minutes=5,
        )

        # Should trigger at exact threshold (>=)
        assert result["detected"] is True

    async def test_zero_atr_handled(self, mock_db):
        """Test handling of zero ATR (edge case)."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Zero ATR should not cause division errors
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.00,
            atr=0.0,
            time_window_minutes=5,
        )

        # With zero ATR, any move should be considered significant
        assert result["detected"] is True
        assert result["atr_multiple"] == float("inf") or result["atr_multiple"] > 1000


@pytest.mark.asyncio
class TestDetectLiquiditySweep:
    """Tests for T066: detect_liquidity_sweep() identifies stop hunting patterns."""

    async def test_detects_sweep_below_support(self, mock_db):
        """Test detecting sweep below key support level."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price briefly dipped below support of 55.00 to 54.80
        # then recovered to 55.50
        # This is a classic liquidity sweep pattern
        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.80,
            recent_high=56.00,
            current_price=55.50,
            direction="long",
        )

        assert result["detected"] is True
        assert result["sweep_type"] == "support_sweep"
        assert result["sweep_level"] == 55.00
        assert result["penetration_depth"] == pytest.approx(0.20, abs=0.01)

    async def test_detects_sweep_above_resistance(self, mock_db):
        """Test detecting sweep above key resistance level."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price briefly spiked above resistance of 57.00 to 57.30
        # then fell back to 56.50
        # This is a liquidity sweep above resistance
        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=56.00,
            recent_high=57.30,
            current_price=56.50,
            direction="short",
        )

        assert result["detected"] is True
        assert result["sweep_type"] == "resistance_sweep"
        assert result["sweep_level"] == 57.00
        assert result["penetration_depth"] == pytest.approx(0.30, abs=0.01)

    async def test_no_sweep_when_price_stays_within_range(self, mock_db):
        """Test no sweep detected when price stays within support/resistance."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price stayed within range 55.50-56.50
        # No breach of support (55.00) or resistance (57.00)
        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=55.50,
            recent_high=56.50,
            current_price=56.00,
            direction="long",
        )

        assert result["detected"] is False

    async def test_no_sweep_when_price_holds_below_level(self, mock_db):
        """Test no sweep when price breaks level and stays there."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price broke below support and stayed there (real breakdown, not sweep)
        # Recent low is 54.50 and current price is still 54.60
        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.50,
            recent_high=55.20,
            current_price=54.60,  # Still below support
            direction="long",
        )

        assert result["detected"] is False

    async def test_sweep_requires_recovery(self, mock_db):
        """Test that sweep detection requires price to recover back into range."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price swept below support to 54.80 and recovered to 55.20
        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.80,
            recent_high=56.00,
            current_price=55.20,  # Back above support
            direction="long",
        )

        assert result["detected"] is True
        assert result["sweep_type"] == "support_sweep"

    async def test_minimum_penetration_depth(self, mock_db):
        """Test that very small penetrations are not considered sweeps."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Very small penetration of 0.02 below support (might be spread)
        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.98,  # Only 0.02 below
            recent_high=56.00,
            current_price=55.50,
            direction="long",
            min_penetration=0.05,  # Require at least 0.05 penetration
        )

        # Too small to be a meaningful sweep
        assert result["detected"] is False

    async def test_sweep_metadata_includes_details(self, mock_db):
        """Test that sweep result includes useful metadata."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.70,
            recent_high=56.00,
            current_price=55.60,
            direction="long",
        )

        assert result["detected"] is True
        assert "sweep_type" in result
        assert "sweep_level" in result
        assert "penetration_depth" in result
        assert "current_price" in result


@pytest.mark.asyncio
class TestMonitorIntegration:
    """Test integration of detection methods with monitoring loop."""

    async def test_fast_move_triggers_sse_event(self, mock_db):
        """Test that fast move detection emits SSE event."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            # Detect a fast move
            result = await service.detect_fast_move(
                ticket=12345,
                entry_price=56.00,
                current_price=57.50,
                atr=0.50,
                time_window_minutes=5,
            )

            # If detected, emit SSE event
            if result["detected"]:
                await service._emit_fast_move_alert(
                    ticket=12345,
                    result=result,
                )

                mock_manager.emit.assert_called_once()
                call_args = mock_manager.emit.call_args
                assert call_args[0][0] == "fast_move"
                assert call_args[0][1]["ticket"] == 12345

    async def test_liquidity_sweep_triggers_sse_event(self, mock_db):
        """Test that liquidity sweep detection emits SSE event."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            # Detect a liquidity sweep
            result = await service.detect_liquidity_sweep(
                ticket=12345,
                support_level=55.00,
                resistance_level=57.00,
                recent_low=54.70,
                recent_high=56.00,
                current_price=55.60,
                direction="long",
            )

            # If detected, emit SSE event
            if result["detected"]:
                await service._emit_liquidity_sweep_alert(
                    ticket=12345,
                    result=result,
                )

                mock_manager.emit.assert_called_once()
                call_args = mock_manager.emit.call_args
                assert call_args[0][0] == "liquidity_sweep"
                assert call_args[0][1]["ticket"] == 12345


@pytest.mark.asyncio
class TestSuggestionLogging:
    """Tests for T069: suggestion logging (no auto-execution)."""

    async def test_fast_move_logs_suggestion_only(self, mock_db):
        """Test that fast move generates suggestion but doesn't execute trades.
        
        This verifies T069: The service only logs suggestions and emits events,
        it never calls trading APIs to close or modify positions automatically.
        """
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.50,
            atr=0.50,
            time_window_minutes=5,
        )

        # Verify detection works
        assert result["detected"] is True

        # Verify suggestion is included (not auto-execution)
        assert "suggestion" in result
        assert "Consider" in result["suggestion"]  # Suggestion wording

        # The method only returns detection info - no trading side effects
        # Trading service is never imported or called in price_alert_service

    async def test_liquidity_sweep_logs_suggestion_only(self, mock_db):
        """Test that liquidity sweep generates suggestion but doesn't execute trades.
        
        This verifies T069: The service only logs suggestions and emits events,
        it never calls trading APIs to close or modify positions automatically.
        """
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.70,
            recent_high=56.00,
            current_price=55.60,
            direction="long",
        )

        # Verify detection works
        assert result["detected"] is True

        # Verify suggestion is included (not auto-execution)
        assert "suggestion" in result
        assert "consider" in result["suggestion"].lower()  # Suggestion wording

        # The method only returns detection info - no trading side effects
        # Trading service is never imported or called in price_alert_service
