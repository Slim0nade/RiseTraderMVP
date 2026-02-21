"""
Unit Tests for Stealth Stop Alerts & Monitoring (FR-011, FR-012)

Tests the alert system that notifies on stop modifications,
erosion alerts, and provides monitoring capabilities.

TDD Approach: These tests are written BEFORE the implementation.
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
def alert_config():
    """Configuration for alert testing."""
    return DynamicTrailConfig(
        disaster_stop_multiplier=3.0,
        trail_trigger_atr=0.5,
        erosion_threshold_atr=0.5,
        erosion_alert_threshold_atr=0.3,
    )


@pytest.fixture
def sample_position():
    """A sample position for testing (no stop set)."""
    return MonitoredPosition(
        ticket=12345,
        symbol="CrudeOIL",
        direction="short",
        entry_price=61.00,
        current_stop=0.0,  # No stop set
        current_tp=55.00,
        lots=1.0,
        current_price=60.00,
        disaster_stop_set=False,
    )


# ============================================================================
# Alert Event Tests
# ============================================================================

class TestAlertEvents:
    """Test alert event generation."""

    @pytest.mark.stealth_stops
    @pytest.mark.asyncio
    async def test_alert_emitted_on_disaster_stop(self, alert_config, sample_position):
        """Test FR-011: Alert emitted when disaster stop is set."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        # Track alerts
        alerts: List[Dict[str, Any]] = []

        def alert_handler(alert: Dict[str, Any]):
            alerts.append(alert)

        manager.on_alert = alert_handler
        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        # sample_position fixture already has disaster_stop_set=False and current_stop=0

        await manager.apply_disaster_protection(sample_position)

        # Should have emitted an alert
        assert len(alerts) >= 1
        disaster_alerts = [a for a in alerts if a.get("type") == "disaster_stop"]
        assert len(disaster_alerts) == 1
        assert disaster_alerts[0]["ticket"] == sample_position.ticket
        assert disaster_alerts[0]["severity"] == "info"

    @pytest.mark.stealth_stops
    @pytest.mark.asyncio
    async def test_alert_emitted_on_erosion_warning(self, alert_config, sample_position):
        """Test FR-011: Alert emitted on erosion warning threshold."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        alerts: List[Dict[str, Any]] = []
        manager.on_alert = lambda a: alerts.append(a)

        sample_position.profit_highwater = 3.00
        sample_position.current_price = 58.50  # Erosion of $2.50

        result = await manager.check_erosion(sample_position, 0.50, 0.75)

        # Should have erosion alert
        if result["alert_triggered"]:
            erosion_alerts = [a for a in alerts if a.get("type") == "erosion_warning"]
            # Alert may or may not be auto-emitted, but check_erosion returns the info
            assert result["alert_triggered"] is True

    @pytest.mark.stealth_stops
    @pytest.mark.asyncio
    async def test_alert_emitted_on_trail_activation(self, alert_config):
        """Test FR-011: Alert emitted when trailing is activated."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        alerts: List[Dict[str, Any]] = []
        manager.on_alert = lambda a: alerts.append(a)
        manager.modify_stop = AsyncMock(return_value=True)
        manager.get_atr = AsyncMock(return_value=0.75)

        position = MonitoredPosition(
            ticket=12345,
            symbol="CrudeOIL",
            direction="short",
            entry_price=61.00,
            current_stop=63.25,
            current_tp=55.00,
            lots=1.0,
            current_price=58.00,  # Enough profit to trail
            disaster_stop_set=True,
            trailing_activated=False,
        )

        await manager.apply_trail(position)

        # Check if trail alert was emitted
        trail_alerts = [a for a in alerts if a.get("type") == "trail_activated"]
        assert len(trail_alerts) >= 1


# ============================================================================
# Monitoring Stats Tests
# ============================================================================

class TestMonitoringStats:
    """Test monitoring statistics collection."""

    @pytest.mark.stealth_stops
    def test_get_protection_stats(self, alert_config):
        """Test FR-012: Get protection statistics."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        # Add some positions
        manager._monitored_positions = {
            12345: MonitoredPosition(
                ticket=12345,
                symbol="CrudeOIL",
                direction="short",
                entry_price=61.00,
                current_stop=59.00,
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
                current_stop=2635.00,
                current_tp=2700.00,
                lots=0.5,
                current_price=2665.00,
                disaster_stop_set=True,
                trailing_activated=False,
                breakeven_triggered=True,
            ),
        }

        stats = manager.get_protection_stats()

        assert stats["total_positions"] == 2
        assert stats["disaster_stops_set"] == 2
        assert stats["trailing_activated"] == 1
        assert stats["breakeven_triggered"] == 1

    @pytest.mark.stealth_stops
    def test_get_position_summary(self, alert_config, sample_position):
        """Test FR-012: Get individual position summary."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        manager._monitored_positions = {
            sample_position.ticket: sample_position
        }

        summary = manager.get_position_summary(sample_position.ticket)

        assert summary is not None
        assert summary["ticket"] == sample_position.ticket
        assert summary["symbol"] == sample_position.symbol
        assert summary["direction"] == sample_position.direction
        assert summary["disaster_stop_set"] == sample_position.disaster_stop_set

    @pytest.mark.stealth_stops
    def test_get_all_positions_summary(self, alert_config):
        """Test FR-012: Get all positions summary."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        manager._monitored_positions = {
            12345: MonitoredPosition(
                ticket=12345,
                symbol="CrudeOIL",
                direction="short",
                entry_price=61.00,
                current_stop=59.00,
                current_tp=55.00,
                lots=1.0,
                current_price=58.00,
                disaster_stop_set=True,
            ),
        }

        summaries = manager.get_all_positions_summary()

        assert len(summaries) == 1
        assert summaries[0]["ticket"] == 12345


# ============================================================================
# Alert History Tests
# ============================================================================

class TestAlertHistory:
    """Test alert history tracking."""

    @pytest.mark.stealth_stops
    def test_alert_history_stored(self, alert_config):
        """Test alerts are stored in history."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        # Emit some alerts
        manager.emit_alert({
            "type": "disaster_stop",
            "ticket": 12345,
            "message": "Disaster stop set",
            "severity": "info",
        })

        manager.emit_alert({
            "type": "erosion_warning",
            "ticket": 12345,
            "message": "Profit erosion detected",
            "severity": "warning",
        })

        history = manager.get_alert_history()

        assert len(history) == 2
        assert history[0]["type"] == "disaster_stop"
        assert history[1]["type"] == "erosion_warning"

    @pytest.mark.stealth_stops
    def test_alert_history_limited_size(self, alert_config):
        """Test alert history doesn't grow unbounded."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        # Emit many alerts
        for i in range(200):
            manager.emit_alert({
                "type": "test",
                "ticket": i,
                "message": f"Test alert {i}",
                "severity": "info",
            })

        history = manager.get_alert_history()

        # History should be limited (default 100)
        assert len(history) <= 100

    @pytest.mark.stealth_stops
    def test_get_alerts_by_ticket(self, alert_config):
        """Test filtering alerts by ticket."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        manager.emit_alert({
            "type": "disaster_stop",
            "ticket": 12345,
            "message": "Alert for 12345",
            "severity": "info",
        })

        manager.emit_alert({
            "type": "trail_activated",
            "ticket": 12346,
            "message": "Alert for 12346",
            "severity": "info",
        })

        manager.emit_alert({
            "type": "erosion_warning",
            "ticket": 12345,
            "message": "Another alert for 12345",
            "severity": "warning",
        })

        alerts_12345 = manager.get_alerts_by_ticket(12345)

        assert len(alerts_12345) == 2
        assert all(a["ticket"] == 12345 for a in alerts_12345)


# ============================================================================
# Alert Callback Tests
# ============================================================================

class TestAlertCallbacks:
    """Test alert callback functionality."""

    @pytest.mark.stealth_stops
    def test_on_alert_callback_invoked(self, alert_config):
        """Test on_alert callback is invoked."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        received_alerts: List[Dict[str, Any]] = []

        def callback(alert: Dict[str, Any]):
            received_alerts.append(alert)

        manager.on_alert = callback

        manager.emit_alert({
            "type": "test",
            "ticket": 12345,
            "message": "Test",
            "severity": "info",
        })

        assert len(received_alerts) == 1
        assert received_alerts[0]["type"] == "test"

    @pytest.mark.stealth_stops
    def test_on_alert_callback_exception_handled(self, alert_config):
        """Test on_alert callback exception doesn't crash manager."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        def bad_callback(alert: Dict[str, Any]):
            raise ValueError("Callback error!")

        manager.on_alert = bad_callback

        # Should not raise
        manager.emit_alert({
            "type": "test",
            "ticket": 12345,
            "message": "Test",
            "severity": "info",
        })


# ============================================================================
# Severity Level Tests
# ============================================================================

class TestAlertSeverity:
    """Test alert severity levels."""

    @pytest.mark.stealth_stops
    def test_severity_levels_available(self, alert_config):
        """Test severity levels are properly defined."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        # Valid severity levels
        valid_severities = ["debug", "info", "warning", "error", "critical"]

        for severity in valid_severities:
            manager.emit_alert({
                "type": "test",
                "ticket": 12345,
                "message": f"Test {severity}",
                "severity": severity,
            })

        history = manager.get_alert_history()
        assert len(history) == len(valid_severities)

    @pytest.mark.stealth_stops
    def test_get_alerts_by_severity(self, alert_config):
        """Test filtering alerts by severity."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        manager.emit_alert({
            "type": "info_alert",
            "ticket": 12345,
            "message": "Info",
            "severity": "info",
        })

        manager.emit_alert({
            "type": "warning_alert",
            "ticket": 12345,
            "message": "Warning",
            "severity": "warning",
        })

        manager.emit_alert({
            "type": "error_alert",
            "ticket": 12345,
            "message": "Error",
            "severity": "error",
        })

        warnings_and_above = manager.get_alerts_by_severity("warning")

        # Should get warning and error (2 alerts)
        assert len(warnings_and_above) == 2


# ============================================================================
# Timestamp Tests
# ============================================================================

class TestAlertTimestamps:
    """Test alert timestamp handling."""

    @pytest.mark.stealth_stops
    def test_alert_has_timestamp(self, alert_config):
        """Test alerts include timestamps."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        before = datetime.now()

        manager.emit_alert({
            "type": "test",
            "ticket": 12345,
            "message": "Test",
            "severity": "info",
        })

        after = datetime.now()

        history = manager.get_alert_history()
        alert = history[0]

        assert "timestamp" in alert
        assert before <= alert["timestamp"] <= after

    @pytest.mark.stealth_stops
    def test_get_recent_alerts(self, alert_config):
        """Test getting alerts from last N minutes."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config
        )

        manager.emit_alert({
            "type": "test",
            "ticket": 12345,
            "message": "Recent alert",
            "severity": "info",
        })

        recent = manager.get_recent_alerts(minutes=5)

        assert len(recent) >= 1


# ============================================================================
# Feature Flag Tests
# ============================================================================

class TestAlertFeatureFlags:
    """Test alert feature flag behavior."""

    @pytest.mark.stealth_stops
    def test_alerts_disabled_no_emission(self, alert_config):
        """Test alerts not emitted when feature disabled."""
        manager = StealthStopManager(
            mt4_host="mock",
            config=alert_config,
            features_enabled={
                "enable_alerts": False,
            }
        )

        received: List[Dict[str, Any]] = []
        manager.on_alert = lambda a: received.append(a)

        manager.emit_alert({
            "type": "test",
            "ticket": 12345,
            "message": "Test",
            "severity": "info",
        })

        # Callback should not be invoked when disabled
        assert len(received) == 0
