"""
Unit Tests for Profit Erosion Detection (FR-010)

Tests the profit erosion detection feature that tracks profit highwater marks
and tightens stops when erosion exceeds thresholds.

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
def erosion_config():
    """Configuration with erosion detection settings."""
    return DynamicTrailConfig(
        erosion_threshold_atr=0.5,       # Tighten at 0.5× ATR erosion
        erosion_alert_threshold_atr=0.3,  # Alert at 0.3× ATR erosion
        atr_multiplier_trail=1.5,
        trail_trigger_atr=0.5,
    )


@pytest.fixture
def profitable_short_position():
    """A short position with profit to track."""
    return MonitoredPosition(
        ticket=12345,
        symbol="CrudeOIL",
        direction="short",
        entry_price=61.00,
        current_stop=63.25,  # Disaster stop set
        current_tp=55.00,
        lots=1.0,
        current_price=55.00,  # Currently at $6.00 profit
        disaster_stop_set=True,
        profit_highwater=0.0,  # Not tracked yet
        profit_erosion=0.0,
    )


@pytest.fixture
def position_at_highwater():
    """A position that reached profit highwater."""
    return MonitoredPosition(
        ticket=12346,
        symbol="CrudeOIL",
        direction="short",
        entry_price=61.00,
        current_stop=56.13,  # Trailed stop
        current_tp=55.00,
        lots=1.0,
        current_price=55.00,  # $6.00 profit = highwater
        disaster_stop_set=True,
        profit_highwater=6.00,  # Highwater set
        profit_erosion=0.0,
        trailing_activated=True,
    )


# ============================================================================
# Profit Calculation Tests
# ============================================================================

class TestProfitCalculation:
    """Test profit calculation for erosion tracking."""

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_calculate_profit_short_position(self, erosion_config):
        """Test profit calculation for SHORT position."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=62.25,
            current_tp=55.00,
            lots=1.0,
            current_price=59.25,  # Price dropped
        )

        profit = manager.calculate_profit(position)

        # SHORT: Profit = entry - current = 60.00 - 59.25 = 0.75
        assert profit == pytest.approx(0.75, abs=0.01)

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_calculate_profit_long_position(self, erosion_config):
        """Test profit calculation for LONG position."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = MonitoredPosition(
            ticket=12346,
            symbol="XAUUSD",
            direction="long",
            entry_price=2650.00,
            current_stop=2612.50,
            current_tp=2700.00,
            lots=0.5,
            current_price=2665.00,  # Price rose
        )

        profit = manager.calculate_profit(position)

        # LONG: Profit = current - entry = 2665.00 - 2650.00 = 15.00
        assert profit == pytest.approx(15.00, abs=0.01)

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_calculate_profit_negative(self, erosion_config):
        """Test profit calculation when in loss."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = MonitoredPosition(
            ticket=12347,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=62.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # Price rose against us
        )

        profit = manager.calculate_profit(position)

        # SHORT: Profit = entry - current = 60.00 - 60.50 = -0.50
        assert profit == pytest.approx(-0.50, abs=0.01)


# ============================================================================
# Highwater Mark Tests
# ============================================================================

class TestHighwaterMark:
    """Test profit highwater mark tracking."""

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_update_highwater_when_profit_increases(
        self, erosion_config, profitable_short_position
    ):
        """Test highwater mark updates when profit increases."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = profitable_short_position
        position.profit_highwater = 3.00  # Previous highwater

        # Update with higher profit
        current_profit = 6.00
        manager.update_highwater(position, current_profit)

        # Highwater should update to new high
        assert position.profit_highwater == 6.00

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_highwater_not_updated_when_profit_decreases(
        self, erosion_config, position_at_highwater
    ):
        """Test highwater mark NOT updated when profit decreases."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = position_at_highwater
        original_highwater = position.profit_highwater  # 6.00

        # Update with lower profit (erosion)
        current_profit = 4.50
        manager.update_highwater(position, current_profit)

        # Highwater should remain at 6.00
        assert position.profit_highwater == original_highwater

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_calculate_erosion(self, erosion_config, position_at_highwater):
        """Test erosion calculation from highwater."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = position_at_highwater
        position.profit_highwater = 6.00
        current_profit = 3.75  # Profit eroded

        erosion = manager.calculate_erosion(position, current_profit)

        # Erosion = highwater - current = 6.00 - 3.75 = 2.25
        assert erosion == pytest.approx(2.25, abs=0.01)


# ============================================================================
# Erosion Detection Tests
# ============================================================================

class TestErosionDetection:
    """Test profit erosion threshold detection."""

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_detect_erosion_below_alert_threshold(
        self, erosion_config, position_at_highwater
    ):
        """Test no alert when erosion below threshold."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = position_at_highwater
        position.profit_highwater = 6.00
        atr = 0.75

        # Erosion of $0.10 = 0.13× ATR (below 0.3× threshold)
        current_profit = 5.90

        result = await manager.check_erosion(position, current_profit, atr)

        assert result["alert_triggered"] is False
        assert result["protection_triggered"] is False

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_detect_erosion_at_alert_threshold(
        self, erosion_config, position_at_highwater
    ):
        """Test alert when erosion reaches alert threshold."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = position_at_highwater
        position.profit_highwater = 6.00
        atr = 0.75

        # Erosion of $0.24 = 0.32× ATR (above alert threshold of 0.3×)
        current_profit = 5.76

        result = await manager.check_erosion(position, current_profit, atr)

        assert result["alert_triggered"] is True
        assert result["protection_triggered"] is False
        assert result["erosion_atr_ratio"] >= 0.3

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_detect_erosion_at_protection_threshold(
        self, erosion_config, position_at_highwater
    ):
        """Test protection when erosion reaches protection threshold."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = position_at_highwater
        position.profit_highwater = 6.00
        atr = 0.75

        # Erosion of $0.375 = 0.50× ATR (at protection threshold)
        current_profit = 5.625

        result = await manager.check_erosion(position, current_profit, atr)

        assert result["alert_triggered"] is True
        assert result["protection_triggered"] is True
        assert result["erosion_atr_ratio"] >= 0.5


# ============================================================================
# Stop Tightening Tests
# ============================================================================

class TestStopTighteningOnErosion:
    """Test stop tightening when erosion exceeds threshold."""

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_tighten_stop_on_erosion(
        self, erosion_config
    ):
        """Test stop is tightened when protection threshold reached."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        # Position with loose disaster stop - erosion protection should tighten
        position = MonitoredPosition(
            ticket=12350,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=62.25,  # Disaster stop (loose)
            current_tp=55.00,
            lots=1.0,
            current_price=57.00,  # $4.00 profit (eroded from $6.00)
            disaster_stop_set=True,
            profit_highwater=6.00,  # Was at $6.00 profit
            trailing_activated=False,
        )

        await manager.apply_erosion_protection(position)

        # Stop should be tightened from disaster stop to trail stop
        manager.modify_stop.assert_called_once()

        # Get the stop price that was set
        call_args = manager.modify_stop.call_args
        new_stop = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("new_stop")

        # For SHORT at price $57.00 with ATR 0.75, trail distance = 1.5 × 0.75 = 1.125
        # Expected stop around $58.125 (tighter than $62.25 disaster stop)
        assert new_stop == pytest.approx(58.13, abs=0.20)
        assert new_stop < position.entry_price  # Must be below entry for short

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_no_tightening_when_below_threshold(
        self, erosion_config, position_at_highwater
    ):
        """Test stop NOT tightened when erosion below threshold."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        position = position_at_highwater
        position.profit_highwater = 6.00
        position.current_price = 55.10  # Only small erosion

        await manager.apply_erosion_protection(position)

        # Stop should NOT be modified
        manager.modify_stop.assert_not_called()


# ============================================================================
# January 12-13 Scenario Replay
# ============================================================================

class TestJan12To13ScenarioReplay:
    """
    Replay the January 12-13, 2026 scenario.

    SC-008: +$600 profit must not result in losses exceeding -$100
    """

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_jan_12_13_scenario_prevents_catastrophic_loss(
        self, erosion_config
    ):
        """
        Test SC-008: Replay Jan 12-13 scenario with erosion protection.

        Original outcome: $600 profit → -$50 loss (total erosion: $650)

        Scenario: Position had $6 profit at highwater, but trailing never kicked in
        (perhaps due to quick reversal). Disaster stop still at 62.25.

        With erosion protection: When profit erodes 0.5× ATR, stop tightens to lock remaining profit.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        # Position that reached highwater but has disaster stop (loose)
        # This represents the Jan 12-13 scenario where trailing hadn't activated
        position = MonitoredPosition(
            ticket=24494956,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=62.25,  # Disaster stop (loose) - trailing hadn't activated
            current_tp=55.00,
            lots=1.0,
            current_price=55.00,  # Highwater: $6.00 profit
            disaster_stop_set=True,
            profit_highwater=6.00,
            trailing_activated=False,  # Trailing hadn't kicked in yet
        )

        # Simulate price rising (profit eroding)
        # Price at $57.25 = $3.75 profit, erosion = $2.25 = 3.00× ATR (above protection threshold)
        position.current_price = 57.25
        result = await manager.check_erosion(
            position,
            manager.calculate_profit(position),
            0.75
        )
        assert result["alert_triggered"] is True

        # Price at $58.50 = $2.50 profit, erosion = $3.50 = 4.67× ATR (way above threshold)
        position.current_price = 58.50
        result = await manager.check_erosion(
            position,
            manager.calculate_profit(position),
            0.75
        )

        # Protection is triggered (erosion exceeds 0.5× ATR)
        assert result["protection_triggered"] is True

        # Apply erosion protection
        await manager.apply_erosion_protection(position)

        # Verify stop was tightened from disaster stop to trail stop
        manager.modify_stop.assert_called()

        # The new stop should be tighter than the disaster stop
        call_args = manager.modify_stop.call_args
        new_stop = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("new_stop")

        # For SHORT at price $58.50, trail stop = 58.50 + 1.125 = 59.625
        # This locks ~$1.375 profit (61.00 - 59.625) vs losing with disaster stop
        assert new_stop < 61.00  # Must be below entry to lock profit
        assert new_stop < 62.25  # Must be tighter than disaster stop
        assert new_stop == pytest.approx(59.63, abs=0.20)


# ============================================================================
# Feature Flag Tests
# ============================================================================

class TestProfitErosionFeatureFlag:
    """Test profit erosion feature flag behavior."""

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_erosion_disabled_when_feature_off(
        self, erosion_config, position_at_highwater
    ):
        """Test erosion detection disabled when feature off."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config,
            features_enabled={
                "enable_disaster_stops": True,
                "enable_profit_erosion": False,  # Disabled
                "enable_early_breakeven": True,
                "enable_institutional_pricing": True,
            }
        )

        manager.modify_stop = AsyncMock(return_value=True)

        position = position_at_highwater
        position.profit_highwater = 6.00
        position.current_price = 58.50  # Would trigger protection

        await manager.apply_erosion_protection(position)

        # Stop should NOT be modified when feature disabled
        manager.modify_stop.assert_not_called()


# ============================================================================
# Edge Cases
# ============================================================================

class TestProfitErosionEdgeCases:
    """Test edge cases for profit erosion."""

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    @pytest.mark.asyncio
    async def test_no_erosion_on_first_profit(self, erosion_config):
        """Test no erosion calculated on first profitable tick."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = MonitoredPosition(
            ticket=12348,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=62.25,
            current_tp=55.00,
            lots=1.0,
            current_price=59.25,  # First profitable price
            profit_highwater=0.0,  # Never set
        )

        current_profit = 0.75
        erosion = manager.calculate_erosion(position, current_profit)

        # No erosion on first profit (highwater is 0)
        assert erosion == 0.0

    @pytest.mark.stealth_stops
    @pytest.mark.profit_erosion
    def test_erosion_when_position_in_loss(self, erosion_config):
        """Test erosion when position goes into loss."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=erosion_config
        )

        position = MonitoredPosition(
            ticket=12349,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=62.25,
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # In loss
            profit_highwater=2.00,  # Was profitable
        )

        current_profit = -0.50  # Now in loss
        erosion = manager.calculate_erosion(position, current_profit)

        # Erosion = highwater - current = 2.00 - (-0.50) = 2.50
        assert erosion == pytest.approx(2.50, abs=0.01)
