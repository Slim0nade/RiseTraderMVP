"""
Integration tests for Autonomous Position Monitoring (T070).

Tests the full flow:
- Open position → simulate fast move → receive fast_move alert
- Open position → simulate liquidity sweep → receive liquidity_sweep alert
"""

import asyncio
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
def mock_position():
    """Create a mock open position."""
    return {
        "ticket": 12345,
        "symbol": "CrudeOIL",
        "type": "buy",
        "open_price": 56.00,
        "current_price": 56.00,
        "lots": 1.0,
        "profit": 0.0,
        "sl": 55.00,
        "tp": 58.00,
        "open_time": datetime.now(timezone.utc) - timedelta(hours=1),
    }


@pytest.mark.asyncio
class TestFastMoveDetectionIntegration:
    """Integration tests for fast move detection."""

    async def test_full_fast_move_detection_flow(self, mock_db, mock_position):
        """
        Test complete fast move detection:
        1. Position opened at 56.00
        2. Price moves rapidly to 57.50 (3× ATR in 5 min)
        3. Fast move detected
        4. SSE event emitted
        5. Suggestion logged (no auto-execution)
        """
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Scenario: ATR is 0.50, price moved from 56.00 to 57.50 = 3× ATR
        entry_price = mock_position["open_price"]
        current_price = 57.50
        atr = 0.50

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            # Step 1: Detect fast move
            result = await service.detect_fast_move(
                ticket=mock_position["ticket"],
                entry_price=entry_price,
                current_price=current_price,
                atr=atr,
                time_window_minutes=5,
            )

            # Verify detection
            assert result["detected"] is True
            assert result["direction"] == "up"
            assert result["atr_multiple"] == pytest.approx(3.0, abs=0.1)

            # Step 2: Emit SSE event
            await service._emit_fast_move_alert(
                ticket=mock_position["ticket"],
                result=result,
            )

            # Verify SSE event emitted
            mock_manager.emit.assert_called_once()
            call_args = mock_manager.emit.call_args
            assert call_args[0][0] == "fast_move"
            event_data = call_args[0][1]
            assert event_data["ticket"] == mock_position["ticket"]
            assert event_data["direction"] == "up"
            assert "suggestion" in event_data

    async def test_fast_move_with_sudden_drop(self, mock_db, mock_position):
        """Test fast move detection on sudden price drop."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price dropped from 56.00 to 54.50 = -1.50 (3× ATR of 0.50)
        entry_price = mock_position["open_price"]
        current_price = 54.50
        atr = 0.50

        result = await service.detect_fast_move(
            ticket=mock_position["ticket"],
            entry_price=entry_price,
            current_price=current_price,
            atr=atr,
            time_window_minutes=5,
        )

        assert result["detected"] is True
        assert result["direction"] == "down"
        assert result["move_size"] == pytest.approx(1.50, abs=0.01)
        assert "suggestion" in result

    async def test_no_false_positives_on_normal_movement(self, mock_db, mock_position):
        """Test that normal price movement doesn't trigger false positive."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Normal move: 56.00 to 56.40 = 0.40 (less than 2× ATR of 0.50)
        entry_price = mock_position["open_price"]
        current_price = 56.40
        atr = 0.50

        result = await service.detect_fast_move(
            ticket=mock_position["ticket"],
            entry_price=entry_price,
            current_price=current_price,
            atr=atr,
            time_window_minutes=5,
        )

        assert result["detected"] is False


@pytest.mark.asyncio
class TestLiquiditySweepIntegration:
    """Integration tests for liquidity sweep detection."""

    async def test_full_liquidity_sweep_detection_flow(self, mock_db, mock_position):
        """
        Test complete liquidity sweep detection:
        1. Long position with stop at 55.00
        2. Price briefly dips to 54.80 (stops triggered)
        3. Price recovers to 55.60
        4. Liquidity sweep detected
        5. SSE event emitted
        6. Suggestion logged
        """
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            # Step 1: Detect liquidity sweep
            result = await service.detect_liquidity_sweep(
                ticket=mock_position["ticket"],
                support_level=55.00,  # Where stops likely are
                resistance_level=57.00,
                recent_low=54.80,  # Price swept below support
                recent_high=56.00,
                current_price=55.60,  # Recovered above support
                direction="long",
            )

            # Verify detection
            assert result["detected"] is True
            assert result["sweep_type"] == "support_sweep"
            assert result["penetration_depth"] == pytest.approx(0.20, abs=0.01)

            # Step 2: Emit SSE event
            await service._emit_liquidity_sweep_alert(
                ticket=mock_position["ticket"],
                result=result,
            )

            # Verify SSE event emitted
            mock_manager.emit.assert_called_once()
            call_args = mock_manager.emit.call_args
            assert call_args[0][0] == "liquidity_sweep"
            event_data = call_args[0][1]
            assert event_data["ticket"] == mock_position["ticket"]
            assert event_data["sweep_type"] == "support_sweep"
            assert "suggestion" in event_data

    async def test_resistance_sweep_for_short_position(self, mock_db):
        """Test liquidity sweep detection above resistance for short positions."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Short position with stop at 57.00
        # Price spiked to 57.30, then fell back to 56.50
        result = await service.detect_liquidity_sweep(
            ticket=67890,
            support_level=55.00,
            resistance_level=57.00,  # Where short stops likely are
            recent_low=56.00,
            recent_high=57.30,  # Price swept above resistance
            current_price=56.50,  # Fell back below resistance
            direction="short",
        )

        assert result["detected"] is True
        assert result["sweep_type"] == "resistance_sweep"
        assert result["penetration_depth"] == pytest.approx(0.30, abs=0.01)

    async def test_no_sweep_when_breakdown_holds(self, mock_db, mock_position):
        """Test no sweep detected when price breaks and holds below level."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Price broke below support and stayed there (real breakdown)
        result = await service.detect_liquidity_sweep(
            ticket=mock_position["ticket"],
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.50,  # Broke below support
            recent_high=55.20,
            current_price=54.60,  # Still below support
            direction="long",
        )

        assert result["detected"] is False


@pytest.mark.asyncio
class TestMonitoringLoopIntegration:
    """Test integration with the main monitoring loop."""

    async def test_monitor_checks_positions_for_fast_moves(self, mock_db):
        """Test that monitoring loop can detect fast moves on positions."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Simulate checking a position for fast moves
        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=58.00,  # 4× ATR move
            atr=0.50,
            time_window_minutes=5,
        )

        # Should detect the fast move
        assert result["detected"] is True
        assert result["atr_multiple"] == pytest.approx(4.0, abs=0.1)

    async def test_multiple_positions_monitored_independently(self, mock_db):
        """Test that multiple positions are monitored independently."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Position 1: Fast move
        result1 = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.50,
            atr=0.50,
            time_window_minutes=5,
        )

        # Position 2: No fast move
        result2 = await service.detect_fast_move(
            ticket=67890,
            entry_price=100.00,
            current_price=100.50,
            atr=0.50,
            time_window_minutes=5,
        )

        assert result1["detected"] is True
        assert result2["detected"] is False


@pytest.mark.asyncio
class TestSSEEventDelivery:
    """Test SSE event delivery for autonomous monitoring."""

    async def test_fast_move_event_format(self, mock_db):
        """Test that fast move SSE events have correct format."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=57.50,
            atr=0.50,
            time_window_minutes=5,
        )

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service._emit_fast_move_alert(ticket=12345, result=result)

            call_args = mock_manager.emit.call_args
            event_type = call_args[0][0]
            event_data = call_args[0][1]

            # Verify event type
            assert event_type == "fast_move"

            # Verify required fields
            assert "ticket" in event_data
            assert "direction" in event_data
            assert "move_size" in event_data
            assert "atr_multiple" in event_data
            assert "current_price" in event_data
            assert "suggestion" in event_data

    async def test_liquidity_sweep_event_format(self, mock_db):
        """Test that liquidity sweep SSE events have correct format."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.80,
            recent_high=56.00,
            current_price=55.60,
            direction="long",
        )

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service._emit_liquidity_sweep_alert(ticket=12345, result=result)

            call_args = mock_manager.emit.call_args
            event_type = call_args[0][0]
            event_data = call_args[0][1]

            # Verify event type
            assert event_type == "liquidity_sweep"

            # Verify required fields
            assert "ticket" in event_data
            assert "sweep_type" in event_data
            assert "sweep_level" in event_data
            assert "penetration_depth" in event_data
            assert "current_price" in event_data
            assert "suggestion" in event_data


@pytest.mark.asyncio
class TestNoAutoExecution:
    """Test that autonomous monitoring never auto-executes trades."""

    async def test_fast_move_only_suggests(self, mock_db):
        """Verify fast move only suggests, never executes."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_fast_move(
            ticket=12345,
            entry_price=56.00,
            current_price=58.00,
            atr=0.50,
            time_window_minutes=5,
        )

        # Result should contain suggestion text
        assert result["detected"] is True
        assert "suggestion" in result
        assert isinstance(result["suggestion"], str)
        assert len(result["suggestion"]) > 0

        # Result should NOT contain any execution flags
        assert "executed" not in result
        assert "trade_id" not in result

    async def test_liquidity_sweep_only_suggests(self, mock_db):
        """Verify liquidity sweep only suggests, never executes."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        result = await service.detect_liquidity_sweep(
            ticket=12345,
            support_level=55.00,
            resistance_level=57.00,
            recent_low=54.80,
            recent_high=56.00,
            current_price=55.60,
            direction="long",
        )

        # Result should contain suggestion text
        assert result["detected"] is True
        assert "suggestion" in result
        assert isinstance(result["suggestion"], str)
        assert len(result["suggestion"]) > 0

        # Result should NOT contain any execution flags
        assert "executed" not in result
        assert "trade_id" not in result
