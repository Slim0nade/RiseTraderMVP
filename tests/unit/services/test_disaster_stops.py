"""
Unit Tests for Disaster Stop Protection (FR-002)

Tests the disaster stop protection feature that sets an initial stop loss
on every detected position within 10 seconds.

TDD Approach: These tests are written BEFORE the implementation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.stealth_stop_manager import (
    StealthStopManager,
    MonitoredPosition,
    DynamicTrailConfig,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_config():
    """Standard test configuration."""
    return DynamicTrailConfig(
        disaster_stop_multiplier=3.0,
        trail_trigger_atr=0.5,
        breakeven_trigger_atr=0.5,
        erosion_threshold_atr=0.5,
        erosion_alert_threshold_atr=0.3,
    )


@pytest.fixture
def short_position_no_stop():
    """A short position without any stop loss set."""
    return MonitoredPosition(
        ticket=12345,
        symbol="CrudeOIL",
        direction="short",
        entry_price=60.00,
        current_stop=0.0,  # No stop set
        current_tp=55.00,
        lots=1.0,
        disaster_stop_set=False,
    )


@pytest.fixture
def long_position_no_stop():
    """A long position without any stop loss set."""
    return MonitoredPosition(
        ticket=12346,
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.00,
        current_stop=0.0,  # No stop set
        current_tp=2700.00,
        lots=0.5,
        disaster_stop_set=False,
    )


@pytest.fixture
def position_with_stop():
    """A position that already has a stop loss set."""
    return MonitoredPosition(
        ticket=12347,
        symbol="CrudeOIL",
        direction="short",
        entry_price=58.00,
        current_stop=60.25,  # Stop already set
        current_tp=54.00,
        lots=1.0,
        disaster_stop_set=True,
    )


# ============================================================================
# Disaster Stop Calculation Tests
# ============================================================================

class TestDisasterStopCalculation:
    """Test disaster stop price calculation."""

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_short_position(self, mock_config, short_position_no_stop):
        """
        Test FR-002: Disaster stop for SHORT position.

        For SHORT positions:
        - Loss occurs when price rises
        - Stop must be ABOVE entry price
        - Formula: entry_price + (disaster_multiplier × ATR)
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        atr = 0.75  # Typical crude oil ATR

        # Calculate disaster stop
        disaster_stop = await manager.calculate_disaster_stop(
            short_position_no_stop,
            atr
        )

        # Expected: 60.00 + (3.0 × 0.75) = 62.25
        assert disaster_stop == pytest.approx(62.25, abs=0.01)

        # For SHORT, stop must be above entry
        assert disaster_stop > short_position_no_stop.entry_price

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_long_position(self, mock_config, long_position_no_stop):
        """
        Test FR-002: Disaster stop for LONG position.

        For LONG positions:
        - Loss occurs when price falls
        - Stop must be BELOW entry price
        - Formula: entry_price - (disaster_multiplier × ATR)
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        atr = 12.50  # Typical gold ATR

        # Calculate disaster stop
        disaster_stop = await manager.calculate_disaster_stop(
            long_position_no_stop,
            atr
        )

        # Expected: 2650.00 - (3.0 × 12.50) = 2612.50
        assert disaster_stop == pytest.approx(2612.50, abs=0.01)

        # For LONG, stop must be below entry
        assert disaster_stop < long_position_no_stop.entry_price

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_uses_fallback_when_atr_unavailable(
        self, mock_config, short_position_no_stop
    ):
        """
        Test FR-002: Use percentage fallback when ATR unavailable.

        Fallback: 2% of entry price
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        atr = None  # ATR unavailable

        disaster_stop = await manager.calculate_disaster_stop(
            short_position_no_stop,
            atr
        )

        # Fallback: 60.00 × 0.02 × 3.0 = 3.60 distance
        # Stop: 60.00 + 3.60 = 63.60
        assert disaster_stop == pytest.approx(63.60, abs=0.01)


# ============================================================================
# Disaster Stop Application Tests
# ============================================================================

class TestDisasterStopApplication:
    """Test disaster stop is applied to positions correctly."""

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_applied_on_new_position(
        self, mock_config, short_position_no_stop
    ):
        """
        Test FR-002: Disaster stop applied when new position detected.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        # Mock modify_stop to track calls
        manager.modify_stop = AsyncMock(return_value=True)

        # Mock ATR
        manager.get_atr = AsyncMock(return_value=0.75)

        # Apply disaster protection
        result = await manager.apply_disaster_protection(short_position_no_stop)

        assert result is True
        assert short_position_no_stop.disaster_stop_set is True
        manager.modify_stop.assert_called_once()

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_not_reapplied(self, mock_config, position_with_stop):
        """
        Test FR-002: Disaster stop not re-applied if already set.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        manager.modify_stop = AsyncMock(return_value=True)

        # Should skip since disaster_stop_set=True
        result = await manager.apply_disaster_protection(position_with_stop)

        assert result is False  # Already set, no action
        manager.modify_stop.assert_not_called()

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_respects_existing_tighter_stop(
        self, mock_config
    ):
        """
        Test FR-002: Don't widen stop if existing stop is tighter.

        If user/strategy set a tighter stop, respect it.
        """
        position = MonitoredPosition(
            ticket=12348,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=61.00,  # Tighter than disaster stop (62.25)
            current_tp=55.00,
            lots=1.0,
            disaster_stop_set=False,
        )

        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        result = await manager.apply_disaster_protection(position)

        # Should mark as set but not modify
        assert position.disaster_stop_set is True
        manager.modify_stop.assert_not_called()  # Existing stop is tighter


# ============================================================================
# Timing Tests
# ============================================================================

class TestDisasterStopTiming:
    """Test disaster stop timing requirements."""

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_applied_within_10_seconds(
        self, mock_config, short_position_no_stop
    ):
        """
        Test SC-001: Disaster stop applied within 10 seconds of detection.

        This is a performance/timing requirement.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        # Simulate position detection
        short_position_no_stop.detected_at = datetime.now()

        start_time = datetime.now()
        await manager.apply_disaster_protection(short_position_no_stop)
        elapsed = (datetime.now() - start_time).total_seconds()

        # Should complete in well under 10 seconds (typically <1 second)
        assert elapsed < 10.0
        assert short_position_no_stop.disaster_stop_set is True


# ============================================================================
# Feature Flag Tests
# ============================================================================

class TestDisasterStopFeatureFlag:
    """Test disaster stop feature flag behavior."""

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_disabled_when_feature_off(
        self, mock_config, short_position_no_stop
    ):
        """
        Test: Disaster stops not applied when feature disabled.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        # Disable feature
        manager.features_enabled = {
            "enable_disaster_stops": False
        }

        manager.modify_stop = AsyncMock(return_value=True)

        result = await manager.apply_disaster_protection(short_position_no_stop)

        assert result is False
        manager.modify_stop.assert_not_called()


# ============================================================================
# Edge Cases
# ============================================================================

class TestDisasterStopEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_handles_zero_atr(
        self, mock_config, short_position_no_stop
    ):
        """
        Test: Gracefully handle zero ATR value.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        manager.get_atr = AsyncMock(return_value=0.0)
        manager.modify_stop = AsyncMock(return_value=True)

        # Should use fallback
        result = await manager.apply_disaster_protection(short_position_no_stop)

        # Should still apply disaster stop using fallback
        assert short_position_no_stop.disaster_stop_set is True

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_handles_modify_failure(
        self, mock_config, short_position_no_stop
    ):
        """
        Test: Handle MT4 modify failure gracefully.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        manager.get_atr = AsyncMock(return_value=0.75)
        manager.modify_stop = AsyncMock(return_value=False)  # Simulate failure

        result = await manager.apply_disaster_protection(short_position_no_stop)

        # Should return False but not crash
        assert result is False
        # Should NOT mark as set since modification failed
        assert short_position_no_stop.disaster_stop_set is False

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_with_very_small_atr(
        self, mock_config
    ):
        """
        Test: Handle very small ATR (forex pip values).
        """
        position = MonitoredPosition(
            ticket=12349,
            symbol="EURUSD",
            direction="long",
            entry_price=1.0850,
            current_stop=0.0,
            current_tp=1.0950,
            lots=0.1,
            disaster_stop_set=False,
        )

        config = DynamicTrailConfig(
            disaster_stop_multiplier=3.0,
            pip_value=0.0001,  # Forex pip value
        )

        manager = StealthStopManager(
            mt4_host="mock",
            config=config
        )

        atr = 0.0050  # Typical EURUSD ATR

        disaster_stop = await manager.calculate_disaster_stop(position, atr)

        # Expected: 1.0850 - (3.0 × 0.0050) = 1.0700
        assert disaster_stop == pytest.approx(1.0700, abs=0.0001)
        assert disaster_stop < position.entry_price  # For LONG


# ============================================================================
# Integration with Institutional Pricing
# ============================================================================

class TestDisasterStopInstitutionalPricing:
    """Test disaster stop with institutional pricing offset."""

    @pytest.mark.stealth_stops
    @pytest.mark.disaster_stops
    @pytest.mark.asyncio
    async def test_disaster_stop_applies_institutional_offset(
        self, mock_config, short_position_no_stop
    ):
        """
        Test: Disaster stop includes random institutional offset.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=mock_config
        )

        manager.features_enabled = {
            "enable_institutional_pricing": True
        }

        atr = 0.75

        # Calculate multiple times - should get different values due to randomness
        stops = []
        for _ in range(10):
            stop = await manager.calculate_disaster_stop(
                short_position_no_stop,
                atr,
                apply_offset=True
            )
            stops.append(stop)

        # All stops should be near 62.25 but with slight variations
        for stop in stops:
            # Base is 62.25, offset range is ±5-15 pips (0.05-0.15)
            assert 62.10 <= stop <= 62.40

        # Should have some variation (not all identical)
        unique_stops = set(round(s, 4) for s in stops)
        assert len(unique_stops) > 1  # At least 2 different values
