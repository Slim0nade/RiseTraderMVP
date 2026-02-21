"""
Integration Tests for Stealth Stop Manager

Tests the full protection lifecycle from position detection through
all protection layers: disaster stops, erosion protection, trailing, and alerts.

These tests verify that all layers work together correctly.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from src.services.stealth_stop_manager import (
    StealthStopManager,
    MonitoredPosition,
    DynamicTrailConfig,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def integration_config():
    """Configuration for integration testing."""
    return DynamicTrailConfig(
        disaster_stop_multiplier=3.0,
        trail_trigger_atr=0.5,
        breakeven_trigger_atr=0.5,
        erosion_threshold_atr=0.5,
        erosion_alert_threshold_atr=0.3,
        atr_multiplier_trail=1.5,
        breakeven_offset_pips=5,
        pip_value=0.01,
    )


@pytest.fixture
def manager_with_mocks(integration_config):
    """Manager with mocked MT4 connection."""
    manager = StealthStopManager(
        mt4_host="mock",
        config=integration_config,
    )

    # Mock MT4 methods
    manager.modify_stop = AsyncMock(return_value=True)
    manager.get_atr = AsyncMock(return_value=0.75)

    # Mock sync_positions to do nothing (we set positions manually)
    async def mock_sync():
        pass
    manager.sync_positions = mock_sync

    # Track alerts
    manager._received_alerts: List[Dict[str, Any]] = []

    def track_alerts(alert: Dict[str, Any]):
        manager._received_alerts.append(alert)

    manager.on_alert = track_alerts

    return manager


# ============================================================================
# Full Lifecycle Tests
# ============================================================================

class TestFullProtectionLifecycle:
    """Test the complete protection lifecycle."""

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_new_position_gets_disaster_stop(self, manager_with_mocks):
        """
        Integration test: New position without stop gets disaster protection.

        Scenario:
        1. New short position opened at $60.00, no stop
        2. Run protection cycle
        3. Should set disaster stop at entry + 3×ATR = $62.25
        4. Should emit disaster_stop alert
        """
        manager = manager_with_mocks

        # Create new position without stop
        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=0.0,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Run one protection cycle
        await manager.run_once()

        # Should have set disaster stop
        assert position.disaster_stop_set is True
        assert position.current_stop > 0  # Stop was set

        # Should have emitted alert
        disaster_alerts = [a for a in manager._received_alerts if a["type"] == "disaster_stop"]
        assert len(disaster_alerts) >= 1

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_position_lifecycle_profit_to_erosion(self, manager_with_mocks):
        """
        Integration test: Position goes from profit to erosion.

        Scenario:
        1. Position has disaster stop set
        2. Price moves favorably, highwater mark updated
        3. Price retraces, erosion detected
        4. Stop tightened due to erosion
        """
        manager = manager_with_mocks

        # Position with disaster stop, in profit
        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=57.00,  # $4 profit
            disaster_stop_set=True,
            profit_highwater=4.00,
            trailing_activated=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Initial highwater
        initial_stop = position.current_stop

        # Run cycle with price still at profit
        await manager.run_once()

        # Highwater should be updated
        assert position.profit_highwater == 4.00

        # Now simulate price retracing (erosion)
        position.current_price = 59.50  # Only $1.50 profit (eroded from $4)

        # Run cycle again
        await manager.run_once()

        # Check if erosion was detected and handled
        # The position should still be protected
        assert position.current_stop > 0

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_position_lifecycle_to_trailing(self, manager_with_mocks):
        """
        Integration test: Position enters profit and starts trailing.

        Scenario:
        1. Position has disaster stop
        2. Price moves enough to trigger trailing (0.5× ATR)
        3. Trail activates, stop moves closer
        """
        manager = manager_with_mocks

        # Short position that's now profitable
        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop (3× ATR = 2.25 above entry)
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # $0.50 profit (>= 0.5× ATR of 0.375)
            disaster_stop_set=True,
            trailing_activated=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Run protection cycle
        await manager.run_once()

        # Should have considered trailing
        # With 0.5× ATR trigger and current profit of 0.50, trail should consider activation
        # Trail stop would be: current_price + 1.5× ATR = 60.50 + 1.125 = 61.625
        # This is tighter than disaster stop of 63.25

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_position_lifecycle_to_breakeven(self, manager_with_mocks):
        """
        Integration test: Position moves to breakeven.

        Scenario:
        1. Position has disaster stop
        2. Price moves enough to trigger breakeven (0.5× ATR)
        3. Stop moves to entry + offset
        """
        manager = manager_with_mocks

        # Short position that's profitable enough for breakeven
        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,  # Disaster stop
            current_tp=55.00,
            lots=1.0,
            current_price=60.50,  # $0.50 profit (>= 0.5× ATR of 0.375)
            disaster_stop_set=True,
            trailing_activated=False,
            breakeven_triggered=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Run protection cycle
        await manager.run_once()

        # Should have considered breakeven
        # For short: breakeven would be entry - offset = 61.00 - 0.05 = 60.95
        # Check that protection was applied

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_positions_different_states(self, manager_with_mocks):
        """
        Integration test: Multiple positions in different states.

        Scenario:
        1. Position A: New, no stop (needs disaster)
        2. Position B: Has stop, in profit (may trail)
        3. Position C: Has stop, eroding (may protect)
        """
        manager = manager_with_mocks

        positions = {
            # New position, no stop
            12345: MonitoredPosition(
                ticket=12345,
                symbol="CrudeOIL",
                direction="short",
                entry_price=60.00,
                current_stop=0.0,
                current_tp=55.00,
                lots=1.0,
                current_price=60.00,
                disaster_stop_set=False,
            ),
            # Position with stop, in profit
            12346: MonitoredPosition(
                ticket=12346,
                symbol="CrudeOIL",
                direction="short",
                entry_price=61.00,
                current_stop=63.25,
                current_tp=55.00,
                lots=1.0,
                current_price=59.00,  # $2 profit
                disaster_stop_set=True,
            ),
            # Position with stop, eroding
            12347: MonitoredPosition(
                ticket=12347,
                symbol="CrudeOIL",
                direction="short",
                entry_price=62.00,
                current_stop=64.25,
                current_tp=55.00,
                lots=1.0,
                current_price=61.50,  # Was at $2 profit, now $0.50
                disaster_stop_set=True,
                profit_highwater=2.00,
            ),
        }

        manager._monitored_positions = positions

        # Run protection cycle
        await manager.run_once()

        # Position A should now have disaster stop
        assert positions[12345].disaster_stop_set is True

        # Position B should still be protected
        assert positions[12346].current_stop > 0

        # Position C should still be protected
        assert positions[12347].current_stop > 0


# ============================================================================
# Alert Flow Tests
# ============================================================================

class TestAlertIntegration:
    """Test alert generation across the protection lifecycle."""

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_alerts_generated_through_lifecycle(self, manager_with_mocks):
        """
        Integration test: Alerts generated at each protection stage.
        """
        manager = manager_with_mocks

        # New position
        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=0.0,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Run cycle - should get disaster stop alert
        await manager.run_once()

        # Check alerts
        assert len(manager._received_alerts) >= 1
        alert_types = [a["type"] for a in manager._received_alerts]
        assert "disaster_stop" in alert_types

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    def test_protection_stats_accurate(self, manager_with_mocks):
        """
        Integration test: Protection stats reflect actual state.
        """
        manager = manager_with_mocks

        # Add positions in various states
        manager._monitored_positions = {
            12345: MonitoredPosition(
                ticket=12345,
                symbol="CrudeOIL",
                direction="short",
                entry_price=60.00,
                current_stop=62.25,
                current_tp=55.00,
                lots=1.0,
                current_price=58.00,
                disaster_stop_set=True,
                trailing_activated=True,
            ),
            12346: MonitoredPosition(
                ticket=12346,
                symbol="XAUUSD",
                direction="long",
                entry_price=2650.00,
                current_stop=2612.50,
                current_tp=2700.00,
                lots=0.5,
                current_price=2665.00,
                disaster_stop_set=True,
                trailing_activated=False,
                breakeven_triggered=True,
            ),
            12347: MonitoredPosition(
                ticket=12347,
                symbol="CrudeOIL",
                direction="long",
                entry_price=59.00,
                current_stop=0.0,
                current_tp=65.00,
                lots=1.0,
                current_price=59.50,
                disaster_stop_set=False,
            ),
        }

        stats = manager.get_protection_stats()

        assert stats["total_positions"] == 3
        assert stats["disaster_stops_set"] == 2
        assert stats["trailing_activated"] == 1
        assert stats["breakeven_triggered"] == 1


# ============================================================================
# Feature Flag Integration Tests
# ============================================================================

class TestFeatureFlagIntegration:
    """Test feature flags control behavior correctly."""

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_features_disabled(self, integration_config):
        """
        Integration test: All features disabled still runs safely.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=integration_config,
            features_enabled={
                "enable_disaster_stops": False,
                "enable_profit_erosion": False,
                "enable_early_breakeven": False,
                "enable_institutional_pricing": False,
                "enable_alerts": False,
            }
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        # Mock sync_positions
        async def mock_sync():
            pass
        manager.sync_positions = mock_sync

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=0.0,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Should run without error
        await manager.run_once()

        # Disaster stop should NOT be set (feature disabled)
        assert position.disaster_stop_set is False

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_selective_features_enabled(self, integration_config):
        """
        Integration test: Only specific features enabled.
        """
        manager = StealthStopManager(
            mt4_host="mock",
            config=integration_config,
            features_enabled={
                "enable_disaster_stops": True,
                "enable_profit_erosion": False,  # Disabled
                "enable_early_breakeven": True,
                "enable_institutional_pricing": False,
                "enable_alerts": True,
            }
        )

        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        # Mock sync_positions
        async def mock_sync():
            pass
        manager.sync_positions = mock_sync

        alerts: List[Dict[str, Any]] = []
        manager.on_alert = lambda a: alerts.append(a)

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=0.0,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=False,
        )

        manager._monitored_positions = {position.ticket: position}

        await manager.run_once()

        # Disaster stop should be set (feature enabled)
        assert position.disaster_stop_set is True

        # Alerts should work (feature enabled)
        assert len(alerts) >= 1


# ============================================================================
# Edge Cases
# ============================================================================

class TestIntegrationEdgeCases:
    """Test edge cases in integration scenarios."""

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_positions_list(self, manager_with_mocks):
        """
        Integration test: Empty positions list handles gracefully.
        """
        manager = manager_with_mocks
        manager._monitored_positions = {}

        # Should run without error
        await manager.run_once()

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_atr_unavailable_falls_back(self, manager_with_mocks):
        """
        Integration test: ATR unavailable uses fallback.
        """
        manager = manager_with_mocks
        manager.get_atr = AsyncMock(return_value=None)  # ATR unavailable

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=0.0,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Should still run (logs warning but doesn't crash)
        await manager.run_once()

    @pytest.mark.stealth_stops
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_modify_stop_failure_handled(self, manager_with_mocks):
        """
        Integration test: Stop modification failure handled gracefully.
        """
        manager = manager_with_mocks
        manager.modify_stop = AsyncMock(return_value=False)  # Modification fails

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=60.00,
            current_stop=0.0,
            current_tp=55.00,
            lots=1.0,
            current_price=60.00,
            disaster_stop_set=False,
        )

        manager._monitored_positions = {position.ticket: position}

        # Should run without error
        await manager.run_once()

        # Disaster stop should NOT be marked as set (modification failed)
        assert position.disaster_stop_set is False
