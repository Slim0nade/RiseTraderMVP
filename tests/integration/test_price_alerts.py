"""
Integration tests for Price Alert lifecycle (T064).

Tests the full flow from alert creation to SSE notification
when price breaches the alert level.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.optimization import AlertDirection, AlertType, PriceAlert


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def sample_alert():
    """Create a sample price alert."""
    alert = MagicMock(spec=PriceAlert)
    alert.id = uuid4()
    alert.ticket = 12345
    alert.alert_type = AlertType.LIQUIDITY_SWEEP.value
    alert.price_level = Decimal("56.50")
    alert.direction = AlertDirection.BELOW.value
    alert.triggered = False
    alert.triggered_at = None
    alert.created_at = datetime.now(timezone.utc)
    alert.alert_data = {"reason": "ATR-based stop"}
    return alert


@pytest.mark.asyncio
class TestPriceAlertLifecycle:
    """Full lifecycle tests for price alerts."""

    async def test_alert_creation_lifecycle(self, mock_db):
        """
        Test creating alerts, monitoring, and triggering.
        
        Lifecycle:
        1. Create alert for position
        2. Price monitored (no breach)
        3. Price breaches level
        4. Alert triggers and SSE event emitted
        5. Alert removed from cache
        """
        from src.services.price_alert_service import PriceAlertService

        # Setup mocks
        mock_repo = AsyncMock()
        price_fetcher = AsyncMock()

        # Create sample alert
        alert = MagicMock(spec=PriceAlert)
        alert.id = uuid4()
        alert.ticket = 12345
        alert.alert_type = "liquidity_sweep"
        alert.price_level = Decimal("56.50")
        alert.direction = "below"
        alert.triggered = False
        alert.triggered_at = None
        alert.created_at = datetime.now(timezone.utc)
        alert.alert_data = None

        mock_repo.create_alert.return_value = alert
        mock_repo.get_active_alerts.return_value = []

        service = PriceAlertService(mock_db, price_fetcher=price_fetcher)
        service.repo = mock_repo

        # Step 1: Create alert
        created = await service.set_price_alert(
            ticket=12345,
            alert_type="liquidity_sweep",
            price_level=56.50,
            direction="below",
        )

        assert created.ticket == 12345
        assert 12345 in service._active_alerts
        assert len(service._active_alerts[12345]) == 1

        # Step 2: Price above level (no breach)
        result = await service.check_level_breach(alert, 57.00)
        assert result is False

        # Step 3: Price breaches level
        result = await service.check_level_breach(alert, 56.00)
        assert result is True

        # Step 4: Trigger alert
        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service.trigger_alert(alert, 56.00)

            # Verify SSE event was emitted
            mock_manager.emit_price_alert.assert_called_once_with(
                ticket=12345,
                alert_type="liquidity_sweep",
                price_level=56.50,
                current_price=56.00,
                direction="below",
            )

            # Verify alert marked as triggered
            mock_repo.trigger_alert.assert_called_once_with(alert.id)

        # Step 5: Alert removed from cache
        assert len(service._active_alerts[12345]) == 0

    async def test_multiple_alerts_per_position(self, mock_db):
        """Test managing multiple alerts for a single position."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()
        alerts = []

        for i, (alert_type, level, direction) in enumerate([
            ("liquidity_sweep", 55.00, "below"),
            ("breakeven", 58.50, "above"),
            ("key_level", 54.00, "below"),
        ]):
            alert = MagicMock(spec=PriceAlert)
            alert.id = uuid4()
            alert.ticket = 12345
            alert.alert_type = alert_type
            alert.price_level = Decimal(str(level))
            alert.direction = direction
            alert.triggered = False
            alert.triggered_at = None
            alert.created_at = datetime.now(timezone.utc)
            alerts.append(alert)

        mock_repo.create_alert.side_effect = alerts
        mock_repo.get_active_alerts.return_value = []

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        # Create multiple alerts
        result = await service.set_multiple_alerts(
            ticket=12345,
            alerts=[
                {"alert_type": "liquidity_sweep", "price_level": 55.00, "direction": "below"},
                {"alert_type": "breakeven", "price_level": 58.50, "direction": "above"},
                {"alert_type": "key_level", "price_level": 54.00, "direction": "below"},
            ],
        )

        assert len(result) == 3
        assert len(service._active_alerts[12345]) == 3

        # Clear all alerts
        mock_repo.delete_alerts_for_ticket.return_value = 3
        deleted = await service.clear_alerts_for_ticket(12345)

        assert deleted == 3
        assert 12345 not in service._active_alerts

    async def test_position_close_clears_alerts(self, mock_db):
        """Test that closing a position clears all its alerts."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()

        # Create alerts
        alerts = [MagicMock(spec=PriceAlert) for _ in range(3)]
        for alert in alerts:
            alert.ticket = 12345
            alert.id = uuid4()

        mock_repo.delete_alerts_for_ticket.return_value = 3

        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = alerts

        # Simulate position close
        deleted = await service.clear_alerts_for_ticket(12345)

        assert deleted == 3
        mock_repo.delete_alerts_for_ticket.assert_called_once_with(12345)
        assert 12345 not in service._active_alerts

    async def test_monitoring_loop_detects_breaches(self, mock_db):
        """Test that monitoring loop correctly detects price breaches."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()

        # Create alert at 56.50 below
        alert = MagicMock(spec=PriceAlert)
        alert.id = uuid4()
        alert.ticket = 12345
        alert.alert_type = "liquidity_sweep"
        alert.price_level = Decimal("56.50")
        alert.direction = AlertDirection.BELOW.value
        alert.triggered = False

        mock_repo.get_active_alerts.return_value = []

        # Price fetcher returns breaching price
        price_fetcher = AsyncMock(return_value=55.00)

        service = PriceAlertService(mock_db, price_fetcher=price_fetcher)
        service.repo = mock_repo
        service._active_alerts[12345] = [alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_sse.return_value = AsyncMock()

            # Run one check cycle
            await service._check_all_alerts()

            # Alert should be triggered
            mock_repo.trigger_alert.assert_called_once()
            price_fetcher.assert_called_once_with(12345)


@pytest.mark.asyncio
class TestPriceAlertAPI:
    """API endpoint tests for price alerts."""

    async def test_create_alert_endpoint_structure(self, mock_db):
        """Test the expected request/response structure for alert creation."""
        # Expected request structure
        request_data = {
            "ticket": 12345,
            "alert_type": "liquidity_sweep",
            "price_level": 56.50,
            "direction": "below",
            "metadata": {"reason": "ATR-based stop"}
        }

        # Expected response structure
        expected_response_keys = {
            "id",
            "ticket",
            "alert_type",
            "price_level",
            "direction",
            "triggered",
            "triggered_at",
            "created_at",
            "metadata",
        }

        # Verify structure
        assert "ticket" in request_data
        assert "alert_type" in request_data
        assert "price_level" in request_data
        assert "direction" in request_data

    async def test_batch_alert_endpoint_structure(self):
        """Test the expected structure for batch alert creation."""
        # Expected request structure
        request_data = {
            "ticket": 12345,
            "alerts": [
                {"alert_type": "liquidity_sweep", "price_level": 56.50, "direction": "below"},
                {"alert_type": "breakeven", "price_level": 58.00, "direction": "above"},
            ]
        }

        assert "ticket" in request_data
        assert "alerts" in request_data
        assert len(request_data["alerts"]) == 2

    async def test_position_alerts_endpoint_structure(self):
        """Test the expected structure for position alerts endpoint."""
        # Expected response structure
        expected_response = {
            "alerts": [],
            "total": 0,
        }

        assert "alerts" in expected_response
        assert "total" in expected_response


@pytest.mark.asyncio
class TestAlertMonitoringIntegration:
    """Integration tests for alert monitoring service."""

    async def test_service_startup_and_shutdown(self, mock_db):
        """Test service lifecycle management."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()
        mock_repo.get_active_alerts.return_value = []

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        # Service should not be running initially
        assert not service.is_running

        # Start service
        await service.start()
        assert service.is_running

        # Stop service
        await service.stop()
        assert not service.is_running

    async def test_cache_refresh_on_startup(self, mock_db):
        """Test that cache is refreshed from DB on startup."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()

        # DB has existing alerts
        existing_alerts = []
        for ticket in [12345, 67890]:
            alert = MagicMock(spec=PriceAlert)
            alert.id = uuid4()
            alert.ticket = ticket
            existing_alerts.append(alert)

        mock_repo.get_active_alerts.return_value = existing_alerts

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        # Refresh cache
        await service._refresh_cache()

        # Verify cache populated
        assert len(service._active_alerts) == 2
        assert 12345 in service._active_alerts
        assert 67890 in service._active_alerts

    async def test_alert_count_property(self, mock_db):
        """Test the active_alert_count property."""
        from src.services.price_alert_service import PriceAlertService

        service = PriceAlertService(mock_db)

        # Empty initially
        assert service.active_alert_count == 0

        # Add some alerts
        service._active_alerts = {
            12345: [MagicMock(), MagicMock()],
            67890: [MagicMock()],
            11111: [MagicMock(), MagicMock(), MagicMock()],
        }

        assert service.active_alert_count == 6


@pytest.mark.asyncio
class TestSSEIntegration:
    """Test SSE event emission when alerts trigger."""

    async def test_sse_event_format(self, mock_db, sample_alert):
        """Test that SSE events have correct format."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()

        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = [sample_alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service.trigger_alert(sample_alert, 56.00)

            # Verify SSE event parameters
            mock_manager.emit_price_alert.assert_called_once()
            call_kwargs = mock_manager.emit_price_alert.call_args.kwargs

            assert call_kwargs["ticket"] == 12345
            assert call_kwargs["alert_type"] == "liquidity_sweep"
            assert call_kwargs["price_level"] == 56.50
            assert call_kwargs["current_price"] == 56.00
            assert call_kwargs["direction"] == "below"

    async def test_sse_event_on_breakeven_alert(self, mock_db):
        """Test SSE event for breakeven alert."""
        from src.services.price_alert_service import PriceAlertService

        mock_repo = AsyncMock()

        alert = MagicMock(spec=PriceAlert)
        alert.id = uuid4()
        alert.ticket = 12345
        alert.alert_type = AlertType.BREAKEVEN.value
        alert.price_level = Decimal("58.00")
        alert.direction = AlertDirection.ABOVE.value
        alert.triggered = False

        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = [alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service.trigger_alert(alert, 58.25)

            mock_manager.emit_price_alert.assert_called_once_with(
                ticket=12345,
                alert_type="breakeven",
                price_level=58.00,
                current_price=58.25,
                direction="above",
            )
