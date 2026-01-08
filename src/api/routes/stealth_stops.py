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
    last_trail_price: Optional[float]


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
