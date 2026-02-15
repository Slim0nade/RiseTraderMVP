"""
Price Alerts API Routes (T058-T060)

Endpoints for managing price level alerts on open positions.
Integrates with SSE for real-time alert notifications.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from src.api.dependencies import get_db
from src.services.price_alert_service import get_price_alert_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["price-alerts"])


# =============================================================================
# Request/Response Models
# =============================================================================


class CreateAlertRequest(BaseModel):
    """Request to create a price alert."""

    ticket: int = Field(..., description="MT4 position ticket number")
    alert_type: str = Field(
        ...,
        description="Alert type: liquidity_sweep, breakeven, key_level, custom"
    )
    price_level: float = Field(..., description="Price level to monitor")
    direction: str = Field(
        ...,
        description="Trigger direction: above or below"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional alert data"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": 12345,
                "alert_type": "liquidity_sweep",
                "price_level": 56.50,
                "direction": "below",
                "metadata": {"reason": "ATR-based institutional stop"}
            }
        }


class BatchAlertItem(BaseModel):
    """Single alert in a batch request."""

    alert_type: str
    price_level: float
    direction: str
    metadata: Optional[Dict[str, Any]] = None


class BatchAlertRequest(BaseModel):
    """Request to create multiple alerts for a position."""

    ticket: int = Field(..., description="MT4 position ticket number")
    alerts: List[BatchAlertItem] = Field(
        ...,
        description="List of alerts to create",
        min_length=1,
        max_length=10
    )


class AlertResponse(BaseModel):
    """Price alert response."""

    id: str
    ticket: int
    alert_type: str
    price_level: float
    direction: str
    triggered: bool
    triggered_at: Optional[str]
    created_at: str
    metadata: Optional[Dict[str, Any]]


class AlertListResponse(BaseModel):
    """List of alerts response."""

    alerts: List[AlertResponse]
    total: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=AlertResponse, status_code=201)
async def create_alert(
    request: CreateAlertRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new price alert (T058).

    Sets up monitoring for a specific price level on a position.
    When the price breaches the level in the configured direction,
    an SSE event is emitted and the alert is marked as triggered.
    """
    try:
        service = await get_price_alert_service(db)

        alert = await service.set_price_alert(
            ticket=request.ticket,
            alert_type=request.alert_type,
            price_level=request.price_level,
            direction=request.direction,
            metadata=request.metadata,
        )

        return AlertResponse(
            id=str(alert.id),
            ticket=alert.ticket,
            alert_type=alert.alert_type,
            price_level=float(alert.price_level),
            direction=alert.direction,
            triggered=alert.triggered,
            triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
            created_at=alert.created_at.isoformat(),
            metadata=alert.alert_data,
        )

    except Exception as e:
        logger.error("create_alert_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=AlertListResponse, status_code=201)
async def create_batch_alerts(
    request: BatchAlertRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create multiple alerts for a position in batch (T059).

    Useful for setting up multiple price levels at once, e.g.:
    - Initial stop loss (liquidity sweep level)
    - Breakeven price
    - Key support/resistance levels
    """
    try:
        service = await get_price_alert_service(db)

        alerts = await service.set_multiple_alerts(
            ticket=request.ticket,
            alerts=[
                {
                    "alert_type": a.alert_type,
                    "price_level": a.price_level,
                    "direction": a.direction,
                    "metadata": a.metadata,
                }
                for a in request.alerts
            ],
        )

        return AlertListResponse(
            alerts=[
                AlertResponse(
                    id=str(a.id),
                    ticket=a.ticket,
                    alert_type=a.alert_type,
                    price_level=float(a.price_level),
                    direction=a.direction,
                    triggered=a.triggered,
                    triggered_at=a.triggered_at.isoformat() if a.triggered_at else None,
                    created_at=a.created_at.isoformat(),
                    metadata=a.alert_data,
                )
                for a in alerts
            ],
            total=len(alerts),
        )

    except Exception as e:
        logger.error("create_batch_alerts_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    triggered: Optional[bool] = Query(None, description="Filter by triggered status"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all active alerts (T058).
    """
    try:
        service = await get_price_alert_service(db)

        if triggered is False:
            alerts = await service.get_all_active_alerts()
        else:
            # For now, return active only (untriggered)
            alerts = await service.get_all_active_alerts()

        return AlertListResponse(
            alerts=[
                AlertResponse(
                    id=str(a.id),
                    ticket=a.ticket,
                    alert_type=a.alert_type,
                    price_level=float(a.price_level),
                    direction=a.direction,
                    triggered=a.triggered,
                    triggered_at=a.triggered_at.isoformat() if a.triggered_at else None,
                    created_at=a.created_at.isoformat(),
                    metadata=a.alert_data,
                )
                for a in alerts
            ],
            total=len(alerts),
        )

    except Exception as e:
        logger.error("list_alerts_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str = Path(..., description="Alert UUID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific alert by ID.
    """
    try:
        service = await get_price_alert_service(db)

        alert = await service.get_alert_by_id(UUID(alert_id))

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return AlertResponse(
            id=str(alert.id),
            ticket=alert.ticket,
            alert_type=alert.alert_type,
            price_level=float(alert.price_level),
            direction=alert.direction,
            triggered=alert.triggered,
            triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
            created_at=alert.created_at.isoformat(),
            metadata=alert.alert_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_alert_failed", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: str = Path(..., description="Alert UUID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a specific alert (T058).
    """
    try:
        service = await get_price_alert_service(db)

        deleted = await service.delete_alert(UUID(alert_id))

        if not deleted:
            raise HTTPException(status_code=404, detail="Alert not found")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_alert_failed", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Position-Specific Endpoints (T060)
# =============================================================================


@router.get("/position/{ticket}", response_model=AlertListResponse)
async def get_position_alerts(
    ticket: int = Path(..., description="MT4 position ticket"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all alerts for a specific position (T060).
    """
    try:
        service = await get_price_alert_service(db)

        alerts = await service.get_alerts_for_ticket(ticket)

        return AlertListResponse(
            alerts=[
                AlertResponse(
                    id=str(a.id),
                    ticket=a.ticket,
                    alert_type=a.alert_type,
                    price_level=float(a.price_level),
                    direction=a.direction,
                    triggered=a.triggered,
                    triggered_at=a.triggered_at.isoformat() if a.triggered_at else None,
                    created_at=a.created_at.isoformat(),
                    metadata=a.alert_data,
                )
                for a in alerts
            ],
            total=len(alerts),
        )

    except Exception as e:
        logger.error("get_position_alerts_failed", ticket=ticket, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/position/{ticket}", status_code=200)
async def clear_position_alerts(
    ticket: int = Path(..., description="MT4 position ticket"),
    db: AsyncSession = Depends(get_db),
):
    """
    Clear all alerts for a position (T060).

    Should be called when a position is closed to clean up
    any remaining alerts.
    """
    try:
        service = await get_price_alert_service(db)

        deleted = await service.clear_alerts_for_ticket(ticket)

        return {"deleted": deleted, "ticket": ticket}

    except Exception as e:
        logger.error("clear_position_alerts_failed", ticket=ticket, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Service Status
# =============================================================================


@router.get("/status/health")
async def get_alert_service_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get price alert service status.
    """
    try:
        service = await get_price_alert_service(db)

        return {
            "running": service.is_running,
            "active_alerts": service.active_alert_count,
            "cached_tickets": len(service._active_alerts),
        }

    except Exception as e:
        logger.error("get_alert_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
