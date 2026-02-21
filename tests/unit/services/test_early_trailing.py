"""
Unit Tests for Early Trailing (FR-004)

Tests the early trailing feature that activates at 0.5× ATR profit instead of 1.0× ATR,
locking in profits earlier during volatile moves.

TDD Approach: These tests are written BEFORE the implementation.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.services.stealth_stop_manager import (
    StealthStopManager,
    MonitoredPosition,
    DynamicTrailConfig,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def early_trail_config():
    """Configuration with early trailing settings."""
    return DynamicTrailConfig(
        trail_trigger_atr=0.5,        # Early trail at 0.5× ATR (was 1.0×)
        breakeven_trigger_atr=0.5,    # Early breakeven at 0.5× ATR (was 1.5×)
        atr_multiplier_trail=1.5,     # Trail distance
        breakeven_offset_pips=5,
        pip_value=0.01,
    )


@pytest.fixture
def short_position_in_profit():
    """A short position with profit that can trigger trailing."""
    return MonitoredPosition(
        ticket=12345,
        symbol="CrudeOIL",
        direction="short",
        entry_price=61.00,
        current_stop=63.25,  # Disaster stop
        current_tp=55.00,
        lots=1.0,
        current_price=60.50,  # Small profit
        disaster_stop_set=True,
        trailing_activated=False,
    )


@pytest.fixture
def long_position_in_profit():
    """A long position with profit that can trigger trailing."""
    return MonitoredPosition(
        ticket=12346,
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.00,
        current_stop=2612.50,  # Disaster stop
        current_tp=2700.00,
        lots=0.5,
        current_price=2665.00,  # In profit
        disaster_stop_set=True,
        trailing_activated=False,
    )


# ============================================================================
# Trail Trigger Tests
# ============================================================================

class TestTrailTrigger:
    """Test when trailing should be triggered."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_trail_triggers_at_half_atr_short(self, early_trail_config):
        """
        Test FR-004: Trail triggers at 0.5× ATR for SHORT.

        SHORT at $61.00, ATR = $0.75
        Trigger threshold: 0.5 × 0.75 = $0.375 profit
        Price at $60.50 = $0.50 profit → Should trigger
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # $0.50 profit
            disaster_stop_set=True,
        )

        atr = 0.75

        should_trail = manager.should_trail(position, atr)

        # Profit ($0.50) >= threshold ($0.375) → should trail
        assert should_trail is True

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_trail_does_not_trigger_below_threshold_short(self, early_trail_config):
        """Test trail does NOT trigger below 0.5× ATR for SHORT."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.80,  # Only $0.20 profit
            disaster_stop_set=True,
        )

        atr = 0.75

        should_trail = manager.should_trail(position, atr)

        # Profit ($0.20) < threshold ($0.375) → should NOT trail
        assert should_trail is False

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_trail_triggers_at_half_atr_long(self, early_trail_config):
        """
        Test FR-004: Trail triggers at 0.5× ATR for LONG.

        LONG at $2650, ATR = $12.50
        Trigger threshold: 0.5 × 12.50 = $6.25 profit
        Price at $2658 = $8.00 profit → Should trigger
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12346,
            symbol="XAUUSD",
            direction="long",
            entry_price=2650.00,
            current_stop=2612.50,
            current_tp=2700.00,
            lots=0.5,
            current_price=2658.00,  # $8.00 profit
            disaster_stop_set=True,
        )

        atr = 12.50

        should_trail = manager.should_trail(position, atr)

        # Profit ($8.00) >= threshold ($6.25) → should trail
        assert should_trail is True


# ============================================================================
# Trail Stop Calculation Tests
# ============================================================================

class TestTrailStopCalculation:
    """Test trail stop price calculation."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_calculate_trail_stop_short(self, early_trail_config):
        """Test trail stop calculation for SHORT position."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,  # $1.00 profit
            disaster_stop_set=True,
        )

        atr = 0.75

        trail_stop = manager.calculate_trail_stop(position, position.current_price, atr)

        # For SHORT: stop = current_price + (atr × multiplier)
        # = 60.00 + (0.75 × 1.5) = 60.00 + 1.125 = 61.125
        # But must be below entry (61.00) to lock profit → returns None here
        # Actually at $60.00 profit = $1.00 > 0.5 × 0.75 = $0.375, should trail
        # Stop = 60.00 + 1.125 = 61.125, but 61.125 > 61.00 → no lock

        # This is the edge case: not enough profit to have stop below entry
        # Need more profit for trail stop to lock profit
        assert trail_stop is None  # Can't lock profit yet

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_calculate_trail_stop_short_sufficient_profit(self, early_trail_config):
        """Test trail stop calculation for SHORT with sufficient profit."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=58.00,  # $3.00 profit
            disaster_stop_set=True,
        )

        atr = 0.75

        trail_stop = manager.calculate_trail_stop(position, position.current_price, atr)

        # For SHORT: stop = current_price + (atr × multiplier)
        # = 58.00 + (0.75 × 1.5) = 58.00 + 1.125 = 59.125
        # 59.125 < 61.00 (entry) → locks profit
        assert trail_stop is not None
        assert trail_stop == pytest.approx(59.125, abs=0.01)
        assert trail_stop < position.entry_price  # Must lock profit

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_calculate_trail_stop_long_sufficient_profit(self, early_trail_config):
        """Test trail stop calculation for LONG with sufficient profit."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12346,
            symbol="XAUUSD",
            direction="long",
            entry_price=2650.00,
            current_stop=2612.50,  # Disaster stop
            current_tp=2700.00,
            lots=0.5,
            current_price=2680.00,  # $30.00 profit
            disaster_stop_set=True,
        )

        atr = 12.50

        trail_stop = manager.calculate_trail_stop(position, position.current_price, atr)

        # For LONG: stop = current_price - (atr × multiplier)
        # = 2680.00 - (12.50 × 1.5) = 2680.00 - 18.75 = 2661.25
        # 2661.25 > 2650.00 (entry) → locks profit
        assert trail_stop is not None
        assert trail_stop == pytest.approx(2661.25, abs=0.01)
        assert trail_stop > position.entry_price  # Must lock profit


# ============================================================================
# Early Trail vs Standard Trail Comparison
# ============================================================================

class TestEarlyVsStandardTrail:
    """Compare early trail (0.5×) vs standard trail (1.0×)."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_early_trail_activates_sooner(self):
        """Test that early trail (0.5× ATR) activates before standard (1.0× ATR)."""
        early_config = DynamicTrailConfig(
            trail_trigger_atr=0.5,  # Early
            atr_multiplier_trail=1.5,
        )

        standard_config = DynamicTrailConfig(
            trail_trigger_atr=1.0,  # Standard
            atr_multiplier_trail=1.5,
        )

        early_manager = StealthStopManager(mt4_host="mock", config=early_config)
        standard_manager = StealthStopManager(mt4_host="mock", config=standard_config)

        # Position with 0.6× ATR profit (between early and standard threshold)
        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.55,  # $0.45 profit = 0.6× ATR (0.75)
            disaster_stop_set=True,
        )

        atr = 0.75

        # Early trail should trigger (0.45 >= 0.375)
        assert early_manager.should_trail(position, atr) is True

        # Standard trail should NOT trigger (0.45 < 0.75)
        assert standard_manager.should_trail(position, atr) is False


# ============================================================================
# Trailing Activation Tests
# ============================================================================

class TestTrailingActivation:
    """Test trailing activation and stop modification."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    @pytest.mark.asyncio
    async def test_trailing_marks_position_as_activated(self, early_trail_config):
        """Test that applying trail marks position as trailing_activated."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=58.00,  # $3.00 profit
            disaster_stop_set=True,
            trailing_activated=False,
        )

        # Apply trail
        await manager.apply_trail(position)

        # Position should be marked as trailing
        assert position.trailing_activated is True
        manager.modify_stop.assert_called_once()

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    @pytest.mark.asyncio
    async def test_trail_tightens_stop_when_price_improves(self, early_trail_config):
        """Test stop tightens further as price continues improving."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=59.125,  # Already trailing
            current_tp=55.00,
            lots=1.0,
            current_price=57.00,  # Price improved further
            disaster_stop_set=True,
            trailing_activated=True,
        )

        # Apply trail with improved price
        await manager.apply_trail(position)

        # Stop should be tightened
        manager.modify_stop.assert_called_once()

        # Get the new stop
        call_args = manager.modify_stop.call_args
        new_stop = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("new_stop")

        # New stop = 57.00 + 1.125 = 58.125 (tighter than 59.125)
        # Allow for institutional pricing offset (±0.15)
        assert new_stop == pytest.approx(58.125, abs=0.20)
        assert new_stop < 59.125  # Must be tighter

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    @pytest.mark.asyncio
    async def test_trail_does_not_loosen_stop(self, early_trail_config):
        """Test stop does NOT loosen if price retraces (for SHORT)."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=58.125,  # Tight trailing stop
            current_tp=55.00,
            lots=1.0,
            current_price=59.00,  # Price retraced (against us)
            disaster_stop_set=True,
            trailing_activated=True,
        )

        # Apply trail with retraced price
        await manager.apply_trail(position)

        # Stop should NOT be modified (would loosen)
        manager.modify_stop.assert_not_called()


# ============================================================================
# Breakeven Tests
# ============================================================================

class TestBreakevenTrigger:
    """Test early breakeven trigger at 0.5× ATR."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_breakeven_triggers_at_half_atr(self, early_trail_config):
        """
        Test FR-005: Breakeven triggers at 0.5× ATR (was 1.5×).

        This provides earlier protection.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # $0.50 profit = 0.67× ATR
            disaster_stop_set=True,
            breakeven_triggered=False,
        )

        atr = 0.75

        # Check if breakeven should trigger
        should_breakeven = manager.should_breakeven(position, atr)

        # Profit ($0.50) >= breakeven threshold (0.5 × 0.75 = $0.375)
        assert should_breakeven is True

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    @pytest.mark.asyncio
    async def test_breakeven_sets_stop_at_entry(self, early_trail_config):
        """Test breakeven sets stop at entry + small offset."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,  # $1.00 profit
            disaster_stop_set=True,
            breakeven_triggered=False,
        )

        await manager.apply_breakeven(position)

        # Stop should be set near entry
        manager.modify_stop.assert_called_once()

        call_args = manager.modify_stop.call_args
        new_stop = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("new_stop")

        # For SHORT: breakeven = entry - offset = 61.00 - (5 × 0.01) = 60.95
        assert new_stop == pytest.approx(60.95, abs=0.05)
        assert position.breakeven_triggered is True


# ============================================================================
# Feature Flag Tests
# ============================================================================

class TestEarlyTrailingFeatureFlag:
    """Test early trailing feature flag behavior."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    @pytest.mark.asyncio
    async def test_early_trailing_disabled_uses_standard_threshold(
        self, early_trail_config
    ):
        """Test standard threshold used when early trailing disabled."""
        # This is controlled by config, not feature flag
        # When trail_trigger_atr=1.0, it's "standard" mode
        standard_config = DynamicTrailConfig(
            trail_trigger_atr=1.0,  # Standard threshold
            atr_multiplier_trail=1.5,
        )

        manager = StealthStopManager(
            mt4_host="mock",
            config=standard_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # $0.50 profit = 0.67× ATR
            disaster_stop_set=True,
        )

        atr = 0.75

        # With standard config, should NOT trail at 0.67× ATR
        assert manager.should_trail(position, atr) is False


# ============================================================================
# Edge Cases
# ============================================================================

class TestEarlyTrailingEdgeCases:
    """Test edge cases for early trailing."""

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_trail_with_zero_atr(self, early_trail_config):
        """Test trailing handles zero ATR gracefully."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=True,
        )

        # Zero ATR should not cause crash
        should_trail = manager.should_trail(position, 0.0)
        assert should_trail is False  # Can't trail without ATR

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_trail_with_negative_profit(self, early_trail_config):
        """Test trailing not triggered when in loss."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=61.50,  # In loss
            disaster_stop_set=True,
        )

        atr = 0.75

        should_trail = manager.should_trail(position, atr)
        assert should_trail is False

    @pytest.mark.stealth_stops
    @pytest.mark.early_trailing
    def test_trail_exactly_at_threshold(self, early_trail_config):
        """Test trailing at exactly the threshold."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=early_trail_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.625,  # Exactly $0.375 profit = 0.5× ATR
            disaster_stop_set=True,
        )

        atr = 0.75

        # At exactly threshold, should trail
        should_trail = manager.should_trail(position, atr)
        assert should_trail is True
