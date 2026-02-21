"""
Stealth Stop Manager API Routes

Endpoints for managing and monitoring automated trailing stops.
"""
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/stealth-stops", tags=["Stealth Stops"])


class TrailConfigResponse(BaseModel):
    """Response model for trail configuration."""
    atr_multiplier_initial: float
    atr_multiplier_trail: float
    trail_trigger_atr: float
    breakeven_trigger_atr: float
    min_offset_pips: float
    max_offset_pips: float
    pip_value: float


class PositionResponse(BaseModel):
    """Response model for a monitored position."""
    ticket: int
    symbol: str
    direction: str
    entry_price: float
    current_stop: float
    current_tp: float
    lots: float
    current_price: float
    breakeven_triggered: bool
    trailing_activated: bool
    disaster_stop_set: bool
    profit_highwater: float
    last_trail_price: Optional[float]


class ProtectionStatsResponse(BaseModel):
    """Response model for protection statistics."""
    total_positions: int
    disaster_stops_set: int
    trailing_activated: int
    breakeven_triggered: int


class AlertResponse(BaseModel):
    """Response model for an alert."""
    type: str
    ticket: Optional[int]
    message: str
    severity: str
    timestamp: str


class FeatureFlagsResponse(BaseModel):
    """Response model for feature flags."""
    enable_disaster_stops: bool
    enable_profit_erosion: bool
    enable_early_breakeven: bool
    enable_institutional_pricing: bool
    enable_alerts: bool


class StatusResponse(BaseModel):
    """Response model for service status."""
    enabled: bool
    running: bool
    positions_monitored: int
    poll_interval: int
    mt4_host: str
    mt4_port: int
    config: Optional[TrailConfigResponse]


def get_stealth_stop_manager():
    """Get the global stealth stop manager instance."""
    from src.api.main import _stealth_stop_manager
    return _stealth_stop_manager


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get the status of the Stealth Stop Manager."""
    manager = get_stealth_stop_manager()
    
    if not manager:
        return StatusResponse(
            enabled=False,
            running=False,
            positions_monitored=0,
            poll_interval=0,
            mt4_host="",
            mt4_port=0,
            config=None
        )
    
    return StatusResponse(
        enabled=True,
        running=manager._running,
        positions_monitored=len(manager._monitored_positions),
        poll_interval=manager.poll_interval,
        mt4_host=manager.mt4_host,
        mt4_port=manager.mt4_port,
        config=TrailConfigResponse(
            atr_multiplier_initial=manager.config.atr_multiplier_initial,
            atr_multiplier_trail=manager.config.atr_multiplier_trail,
            trail_trigger_atr=manager.config.trail_trigger_atr,
            breakeven_trigger_atr=manager.config.breakeven_trigger_atr,
            min_offset_pips=manager.config.min_offset_pips,
            max_offset_pips=manager.config.max_offset_pips,
            pip_value=manager.config.pip_value
        )
    )


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions():
    """Get all monitored positions."""
    manager = get_stealth_stop_manager()

    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")

    positions = []
    for pos in manager._monitored_positions.values():
        positions.append(PositionResponse(
            ticket=pos.ticket,
            symbol=pos.symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            current_stop=pos.current_stop,
            current_tp=pos.current_tp,
            lots=pos.lots,
            current_price=pos.current_price,
            breakeven_triggered=pos.breakeven_triggered,
            trailing_activated=pos.trailing_activated,
            disaster_stop_set=pos.disaster_stop_set,
            profit_highwater=pos.profit_highwater,
            last_trail_price=pos.last_trail_price
        ))

    return positions


@router.post("/sync")
async def sync_positions():
    """Force sync positions with MT4."""
    manager = get_stealth_stop_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")
    
    await manager.sync_positions()
    
    return {
        "success": True,
        "positions_monitored": len(manager._monitored_positions)
    }


@router.get("/atr/{symbol}")
async def get_atr(symbol: str, timeframe: str = "H1", period: int = 14):
    """Get current ATR for a symbol."""
    manager = get_stealth_stop_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")
    
    atr = await manager.get_atr(symbol, period, timeframe)
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "atr": atr
    }


class UpdateConfigRequest(BaseModel):
    """Request model for updating trail configuration."""
    atr_multiplier_trail: Optional[float] = Field(None, ge=0.5, le=5.0)
    trail_trigger_atr: Optional[float] = Field(None, ge=0.5, le=5.0)
    breakeven_trigger_atr: Optional[float] = Field(None, ge=0.5, le=5.0)
    min_offset_pips: Optional[float] = Field(None, ge=1, le=50)
    max_offset_pips: Optional[float] = Field(None, ge=1, le=50)


@router.patch("/config")
async def update_config(request: UpdateConfigRequest):
    """Update trail configuration dynamically."""
    manager = get_stealth_stop_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")
    
    if request.atr_multiplier_trail is not None:
        manager.config.atr_multiplier_trail = request.atr_multiplier_trail
    if request.trail_trigger_atr is not None:
        manager.config.trail_trigger_atr = request.trail_trigger_atr
    if request.breakeven_trigger_atr is not None:
        manager.config.breakeven_trigger_atr = request.breakeven_trigger_atr
    if request.min_offset_pips is not None:
        manager.config.min_offset_pips = request.min_offset_pips
    if request.max_offset_pips is not None:
        manager.config.max_offset_pips = request.max_offset_pips
    
    return {
        "success": True,
        "config": TrailConfigResponse(
            atr_multiplier_initial=manager.config.atr_multiplier_initial,
            atr_multiplier_trail=manager.config.atr_multiplier_trail,
            trail_trigger_atr=manager.config.trail_trigger_atr,
            breakeven_trigger_atr=manager.config.breakeven_trigger_atr,
            min_offset_pips=manager.config.min_offset_pips,
            max_offset_pips=manager.config.max_offset_pips,
            pip_value=manager.config.pip_value
        )
    }


# ============================================================================
# Protection Stats Endpoints
# ============================================================================

@router.get("/stats", response_model=ProtectionStatsResponse)
async def get_protection_stats():
    """Get protection statistics."""
    manager = get_stealth_stop_manager()

    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")

    stats = manager.get_protection_stats()

    return ProtectionStatsResponse(
        total_positions=stats["total_positions"],
        disaster_stops_set=stats["disaster_stops_set"],
        trailing_activated=stats["trailing_activated"],
        breakeven_triggered=stats["breakeven_triggered"]
    )


# ============================================================================
# Alert Endpoints
# ============================================================================

@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    ticket: Optional[int] = None,
    severity: Optional[str] = None,
    minutes: Optional[int] = None
):
    """
    Get alerts from the stealth stop manager.

    Optional filters:
    - ticket: Filter by position ticket
    - severity: Filter by minimum severity (debug, info, warning, error, critical)
    - minutes: Only get alerts from last N minutes
    """
    manager = get_stealth_stop_manager()

    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")

    # Get alerts based on filters
    if ticket is not None:
        alerts = manager.get_alerts_by_ticket(ticket)
    elif severity is not None:
        alerts = manager.get_alerts_by_severity(severity)
    elif minutes is not None:
        alerts = manager.get_recent_alerts(minutes)
    else:
        alerts = manager.get_alert_history()

    return [
        AlertResponse(
            type=a["type"],
            ticket=a.get("ticket"),
            message=a.get("message", ""),
            severity=a["severity"],
            timestamp=a["timestamp"].isoformat() if hasattr(a.get("timestamp"), "isoformat") else str(a.get("timestamp", ""))
        )
        for a in alerts
    ]


# ============================================================================
# Feature Flags Endpoints
# ============================================================================

@router.get("/features", response_model=FeatureFlagsResponse)
async def get_features():
    """Get current feature flags."""
    manager = get_stealth_stop_manager()

    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")

    return FeatureFlagsResponse(
        enable_disaster_stops=manager.features_enabled.get("enable_disaster_stops", True),
        enable_profit_erosion=manager.features_enabled.get("enable_profit_erosion", True),
        enable_early_breakeven=manager.features_enabled.get("enable_early_breakeven", True),
        enable_institutional_pricing=manager.features_enabled.get("enable_institutional_pricing", True),
        enable_alerts=manager.features_enabled.get("enable_alerts", True)
    )


class UpdateFeaturesRequest(BaseModel):
    """Request model for updating feature flags."""
    enable_disaster_stops: Optional[bool] = None
    enable_profit_erosion: Optional[bool] = None
    enable_early_breakeven: Optional[bool] = None
    enable_institutional_pricing: Optional[bool] = None
    enable_alerts: Optional[bool] = None


@router.patch("/features")
async def update_features(request: UpdateFeaturesRequest):
    """Update feature flags dynamically."""
    manager = get_stealth_stop_manager()

    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")

    if request.enable_disaster_stops is not None:
        manager.features_enabled["enable_disaster_stops"] = request.enable_disaster_stops
    if request.enable_profit_erosion is not None:
        manager.features_enabled["enable_profit_erosion"] = request.enable_profit_erosion
    if request.enable_early_breakeven is not None:
        manager.features_enabled["enable_early_breakeven"] = request.enable_early_breakeven
    if request.enable_institutional_pricing is not None:
        manager.features_enabled["enable_institutional_pricing"] = request.enable_institutional_pricing
    if request.enable_alerts is not None:
        manager.features_enabled["enable_alerts"] = request.enable_alerts

    return {
        "success": True,
        "features": FeatureFlagsResponse(
            enable_disaster_stops=manager.features_enabled.get("enable_disaster_stops", True),
            enable_profit_erosion=manager.features_enabled.get("enable_profit_erosion", True),
            enable_early_breakeven=manager.features_enabled.get("enable_early_breakeven", True),
            enable_institutional_pricing=manager.features_enabled.get("enable_institutional_pricing", True),
            enable_alerts=manager.features_enabled.get("enable_alerts", True)
        )
    }


# ============================================================================
# Position Summary Endpoint
# ============================================================================

@router.get("/positions/{ticket}/summary")
async def get_position_summary(ticket: int):
    """Get detailed summary for a specific position."""
    manager = get_stealth_stop_manager()

    if not manager:
        raise HTTPException(status_code=503, detail="Stealth Stop Manager is not running")

    summary = manager.get_position_summary(ticket)

    if summary is None:
        raise HTTPException(status_code=404, detail=f"Position {ticket} not found")

    return summary
