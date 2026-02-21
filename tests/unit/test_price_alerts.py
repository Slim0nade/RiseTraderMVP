"""
Unit tests for Price Alert Service (T049-T051).

These tests verify:
- T049: set_price_alert() creates alerts correctly
- T050: check_level_breach() detects price crossings
- T051: alert cleanup on position close
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.optimization import AlertDirection, AlertType, PriceAlert
from src.services.price_alert_service import PriceAlertService


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_repo():
    """Create a mock optimization repository."""
    repo = AsyncMock()
    repo.create_alert = AsyncMock()
    repo.get_active_alerts = AsyncMock(return_value=[])
    repo.trigger_alert = AsyncMock()
    repo.delete_alerts_for_ticket = AsyncMock(return_value=0)
    return repo


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
class TestSetPriceAlert:
    """Tests for T049: set_price_alert() creates alerts correctly."""

    async def test_creates_alert_with_all_fields(self, mock_db, mock_repo, sample_alert):
        """Test creating an alert with all fields specified."""
        mock_repo.create_alert.return_value = sample_alert

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        alert = await service.set_price_alert(
            ticket=12345,
            alert_type="liquidity_sweep",
            price_level=56.50,
            direction="below",
            metadata={"reason": "ATR-based stop"},
        )

        mock_repo.create_alert.assert_called_once_with(
            ticket=12345,
            alert_type="liquidity_sweep",
            price_level=56.50,
            direction="below",
            metadata={"reason": "ATR-based stop"},
        )
        mock_db.commit.assert_called_once()

    async def test_creates_alert_without_metadata(self, mock_db, mock_repo, sample_alert):
        """Test creating an alert without metadata."""
        mock_repo.create_alert.return_value = sample_alert

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        await service.set_price_alert(
            ticket=12345,
            alert_type="breakeven",
            price_level=57.00,
            direction="above",
        )

        mock_repo.create_alert.assert_called_once()
        call_args = mock_repo.create_alert.call_args
        assert call_args.kwargs["metadata"] is None

    async def test_updates_cache_on_creation(self, mock_db, mock_repo, sample_alert):
        """Test that alert is added to cache after creation."""
        mock_repo.create_alert.return_value = sample_alert

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        assert 12345 not in service._active_alerts

        await service.set_price_alert(
            ticket=12345,
            alert_type="key_level",
            price_level=55.00,
            direction="below",
        )

        assert 12345 in service._active_alerts
        assert len(service._active_alerts[12345]) == 1

    async def test_batch_alert_creation(self, mock_db, mock_repo):
        """Test creating multiple alerts at once."""
        alerts = [MagicMock(spec=PriceAlert) for _ in range(3)]
        for i, alert in enumerate(alerts):
            alert.id = uuid4()
            alert.ticket = 12345
        mock_repo.create_alert.side_effect = alerts

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        result = await service.set_multiple_alerts(
            ticket=12345,
            alerts=[
                {"alert_type": "liquidity_sweep", "price_level": 56.0, "direction": "below"},
                {"alert_type": "breakeven", "price_level": 58.0, "direction": "above"},
                {"alert_type": "key_level", "price_level": 55.0, "direction": "below"},
            ],
        )

        assert len(result) == 3
        assert mock_repo.create_alert.call_count == 3
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
class TestCheckLevelBreach:
    """Tests for T050: check_level_breach() detects price crossings."""

    async def test_breach_above_when_price_exceeds_level(self, mock_db, sample_alert):
        """Test detecting price breach above level."""
        sample_alert.direction = AlertDirection.ABOVE.value
        sample_alert.price_level = Decimal("57.00")

        service = PriceAlertService(mock_db)

        # Price at level - should breach
        result = await service.check_level_breach(sample_alert, 57.00)
        assert result is True

        # Price above level - should breach
        result = await service.check_level_breach(sample_alert, 57.50)
        assert result is True

        # Price below level - should not breach
        result = await service.check_level_breach(sample_alert, 56.99)
        assert result is False

    async def test_breach_below_when_price_falls_below_level(self, mock_db, sample_alert):
        """Test detecting price breach below level."""
        sample_alert.direction = AlertDirection.BELOW.value
        sample_alert.price_level = Decimal("56.50")

        service = PriceAlertService(mock_db)

        # Price at level - should breach
        result = await service.check_level_breach(sample_alert, 56.50)
        assert result is True

        # Price below level - should breach
        result = await service.check_level_breach(sample_alert, 56.00)
        assert result is True

        # Price above level - should not breach
        result = await service.check_level_breach(sample_alert, 56.51)
        assert result is False

    async def test_no_breach_when_price_between_levels(self, mock_db, sample_alert):
        """Test that no breach is detected when price is between levels."""
        sample_alert.direction = AlertDirection.BELOW.value
        sample_alert.price_level = Decimal("55.00")

        service = PriceAlertService(mock_db)

        # Price above the "below" level
        result = await service.check_level_breach(sample_alert, 56.00)
        assert result is False


@pytest.mark.asyncio
class TestAlertTrigger:
    """Tests for alert triggering and SSE emission."""

    async def test_trigger_alert_marks_as_triggered(self, mock_db, mock_repo, sample_alert):
        """Test that triggering an alert marks it in DB."""
        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = [sample_alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service.trigger_alert(sample_alert, 56.25)

            mock_repo.trigger_alert.assert_called_once_with(sample_alert.id)
            mock_db.commit.assert_called()

    async def test_trigger_alert_emits_sse_event(self, mock_db, mock_repo, sample_alert):
        """Test that triggering emits SSE event."""
        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = [sample_alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_manager = AsyncMock()
            mock_sse.return_value = mock_manager

            await service.trigger_alert(sample_alert, 56.25)

            mock_manager.emit_price_alert.assert_called_once_with(
                ticket=12345,
                alert_type=sample_alert.alert_type,
                price_level=56.50,  # float(Decimal)
                current_price=56.25,
                direction=sample_alert.direction,
            )

    async def test_trigger_removes_from_cache(self, mock_db, mock_repo, sample_alert):
        """Test that triggered alert is removed from cache."""
        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = [sample_alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_sse.return_value = AsyncMock()

            await service.trigger_alert(sample_alert, 56.25)

            assert len(service._active_alerts[12345]) == 0


@pytest.mark.asyncio
class TestAlertCleanup:
    """Tests for T051: alert cleanup on position close."""

    async def test_clear_alerts_for_ticket(self, mock_db, mock_repo, sample_alert):
        """Test clearing all alerts for a closed position."""
        mock_repo.delete_alerts_for_ticket.return_value = 3

        service = PriceAlertService(mock_db)
        service.repo = mock_repo
        service._active_alerts[12345] = [sample_alert]

        deleted = await service.clear_alerts_for_ticket(12345)

        assert deleted == 3
        mock_repo.delete_alerts_for_ticket.assert_called_once_with(12345)
        mock_db.commit.assert_called()
        assert 12345 not in service._active_alerts

    async def test_clear_nonexistent_ticket(self, mock_db, mock_repo):
        """Test clearing alerts for a ticket with no alerts."""
        mock_repo.delete_alerts_for_ticket.return_value = 0

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        deleted = await service.clear_alerts_for_ticket(99999)

        assert deleted == 0

    async def test_delete_single_alert(self, mock_db, sample_alert):
        """Test deleting a specific alert."""
        service = PriceAlertService(mock_db)
        service._active_alerts[12345] = [sample_alert]

        # Mock get_alert_by_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_alert
        mock_db.execute.return_value = mock_result

        result = await service.delete_alert(sample_alert.id)

        assert result is True
        mock_db.delete.assert_called_once_with(sample_alert)
        mock_db.commit.assert_called()

    async def test_delete_nonexistent_alert(self, mock_db):
        """Test deleting an alert that doesn't exist."""
        service = PriceAlertService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.delete_alert(uuid4())

        assert result is False
        mock_db.delete.assert_not_called()


@pytest.mark.asyncio
class TestGetAlerts:
    """Tests for alert retrieval."""

    async def test_get_alerts_for_ticket(self, mock_db, mock_repo, sample_alert):
        """Test getting alerts for a specific ticket."""
        mock_repo.get_active_alerts.return_value = [sample_alert]

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        alerts = await service.get_alerts_for_ticket(12345)

        assert len(alerts) == 1
        mock_repo.get_active_alerts.assert_called_once_with(ticket=12345)

    async def test_get_all_active_alerts(self, mock_db, mock_repo):
        """Test getting all active alerts."""
        alerts = [MagicMock(spec=PriceAlert) for _ in range(5)]
        mock_repo.get_active_alerts.return_value = alerts

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        result = await service.get_all_active_alerts()

        assert len(result) == 5


@pytest.mark.asyncio
class TestMonitorLoop:
    """Tests for the monitoring loop."""

    async def test_start_sets_running_flag(self, mock_db, mock_repo):
        """Test that start() sets running flag."""
        mock_repo.get_active_alerts.return_value = []

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        assert not service.is_running

        await service.start()

        assert service.is_running

        await service.stop()

    async def test_stop_clears_running_flag(self, mock_db, mock_repo):
        """Test that stop() clears running flag."""
        mock_repo.get_active_alerts.return_value = []

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        await service.start()
        await service.stop()

        assert not service.is_running

    async def test_monitor_checks_prices(self, mock_db, mock_repo, sample_alert):
        """Test that monitor loop checks prices."""
        mock_repo.get_active_alerts.return_value = [sample_alert]

        price_fetcher = AsyncMock(return_value=55.00)  # Below 56.50 - should trigger

        service = PriceAlertService(mock_db, price_fetcher=price_fetcher)
        service.repo = mock_repo

        # Manually populate cache and run check
        service._active_alerts[12345] = [sample_alert]

        with patch("src.services.price_alert_service.get_sse_manager") as mock_sse:
            mock_sse.return_value = AsyncMock()

            await service._check_all_alerts()

            price_fetcher.assert_called_once_with(12345)
            mock_repo.trigger_alert.assert_called_once()

    async def test_monitor_handles_price_fetch_error(self, mock_db, mock_repo, sample_alert):
        """Test that monitor handles price fetch errors gracefully."""
        mock_repo.get_active_alerts.return_value = [sample_alert]

        price_fetcher = AsyncMock(side_effect=Exception("Network error"))

        service = PriceAlertService(mock_db, price_fetcher=price_fetcher)
        service.repo = mock_repo
        service._active_alerts[12345] = [sample_alert]

        # Should not raise
        await service._check_all_alerts()

        mock_repo.trigger_alert.assert_not_called()


@pytest.mark.asyncio
class TestCacheManagement:
    """Tests for alert cache management."""

    async def test_refresh_cache_from_db(self, mock_db, mock_repo):
        """Test refreshing cache from database."""
        alerts = []
        for i in range(3):
            alert = MagicMock(spec=PriceAlert)
            alert.ticket = 12345 if i < 2 else 67890
            alerts.append(alert)
        mock_repo.get_active_alerts.return_value = alerts

        service = PriceAlertService(mock_db)
        service.repo = mock_repo

        await service._refresh_cache()

        assert len(service._active_alerts) == 2  # 2 unique tickets
        assert len(service._active_alerts[12345]) == 2
        assert len(service._active_alerts[67890]) == 1

    async def test_active_alert_count(self, mock_db):
        """Test counting total active alerts."""
        service = PriceAlertService(mock_db)
        service._active_alerts = {
            12345: [MagicMock(), MagicMock()],
            67890: [MagicMock()],
        }

        assert service.active_alert_count == 3
