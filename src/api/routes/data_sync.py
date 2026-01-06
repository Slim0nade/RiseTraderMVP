"""
Data Sync API Routes.

Provides endpoints to trigger data sync operations and check status.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/data-sync", tags=["Data Sync"])


class DataStatus(BaseModel):
    """Data status for a symbol/source combination."""
    symbol: str
    source: str
    records: int
    start_date: Optional[date]
    end_date: Optional[date]
    days_with_data: int
    avg_bars_per_day: int


class GapInfo(BaseModel):
    """Information about a data gap."""
    symbol: str
    source: str
    gap_start: date
    gap_end: date
    trading_days: int


class SyncRequest(BaseModel):
    """Request to sync data."""
    symbol: Optional[str] = None  # None = sync all
    force_days: int = 0  # Force re-download last N days
    dry_run: bool = False


class SyncResult(BaseModel):
    """Result of a sync operation."""
    symbol: str
    source: str
    success: bool
    bars_downloaded: int = 0
    bars_imported: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0


class StatusResponse(BaseModel):
    """Response with data status."""
    data: List[DataStatus]
    gaps: List[GapInfo]


class SyncResponse(BaseModel):
    """Response from sync operation."""
    message: str
    results: List[SyncResult]
    total_downloaded: int
    total_imported: int


# In-memory state for background sync
_sync_in_progress = False
_last_sync_results: List[dict] = []


@router.get("/status", response_model=StatusResponse)
async def get_data_status():
    """
    Get current data status and gaps.
    
    Returns information about all data sources and any gaps that need filling.
    """
    from src.data.sync import DataSyncService
    
    service = DataSyncService()
    
    try:
        status = await service.get_data_status()
        gaps = await service.detect_gaps()
        
        return StatusResponse(
            data=[
                DataStatus(
                    symbol=s["symbol"],
                    source=s["source"],
                    records=s["records"],
                    start_date=s["start_date"],
                    end_date=s["end_date"],
                    days_with_data=s["days_with_data"],
                    avg_bars_per_day=s["avg_bars_per_day"]
                )
                for s in status.values()
            ],
            gaps=[
                GapInfo(
                    symbol=g.symbol,
                    source=g.source,
                    gap_start=g.gap_start,
                    gap_end=g.gap_end,
                    trading_days=g.trading_days
                )
                for g in gaps
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync", response_model=SyncResponse)
async def sync_data(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Trigger a data sync operation.
    
    If no symbol is specified, syncs all enabled symbols.
    Use dry_run=True to see what would be done without actually downloading.
    Use force_days to re-download the last N days even if data exists.
    """
    global _sync_in_progress
    
    if _sync_in_progress:
        raise HTTPException(status_code=409, detail="Sync already in progress")
    
    from src.data.sync import DataSyncService, SymbolConfig, DEFAULT_SYMBOLS
    
    service = DataSyncService()
    
    # Determine symbols to sync
    if request.symbol:
        config = next((s for s in DEFAULT_SYMBOLS if s.symbol == request.symbol), None)
        if config is None:
            config = SymbolConfig(request.symbol, ["DUKASCOPY", "HISTDATA"])
        symbols = [config]
    else:
        symbols = None
    
    try:
        _sync_in_progress = True
        
        results = await service.sync_all(
            symbols=symbols,
            dry_run=request.dry_run,
            force_days=request.force_days
        )
        
        global _last_sync_results
        _last_sync_results = [
            {
                "symbol": r.symbol,
                "source": r.source,
                "success": r.success,
                "bars_downloaded": r.bars_downloaded,
                "bars_imported": r.bars_imported,
                "error": r.error,
                "duration_seconds": r.duration_seconds
            }
            for r in results
        ]
        
        return SyncResponse(
            message="Sync completed" if not request.dry_run else "Dry run completed",
            results=[
                SyncResult(**r) for r in _last_sync_results
            ],
            total_downloaded=sum(r.bars_downloaded for r in results),
            total_imported=sum(r.bars_imported for r in results)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _sync_in_progress = False


@router.get("/last-sync")
async def get_last_sync_results():
    """Get results from the last sync operation."""
    return {
        "results": _last_sync_results,
        "sync_in_progress": _sync_in_progress
    }


@router.post("/sync-background")
async def sync_data_background(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Trigger a data sync operation in the background.
    
    Returns immediately while sync runs in background.
    Check /data-sync/last-sync for results.
    """
    global _sync_in_progress
    
    if _sync_in_progress:
        raise HTTPException(status_code=409, detail="Sync already in progress")
    
    async def run_sync():
        global _sync_in_progress, _last_sync_results
        
        from src.data.sync import DataSyncService, SymbolConfig, DEFAULT_SYMBOLS
        
        service = DataSyncService()
        
        if request.symbol:
            config = next((s for s in DEFAULT_SYMBOLS if s.symbol == request.symbol), None)
            if config is None:
                config = SymbolConfig(request.symbol, ["DUKASCOPY", "HISTDATA"])
            symbols = [config]
        else:
            symbols = None
        
        try:
            _sync_in_progress = True
            results = await service.sync_all(
                symbols=symbols,
                dry_run=request.dry_run,
                force_days=request.force_days
            )
            
            _last_sync_results = [
                {
                    "symbol": r.symbol,
                    "source": r.source,
                    "success": r.success,
                    "bars_downloaded": r.bars_downloaded,
                    "bars_imported": r.bars_imported,
                    "error": r.error,
                    "duration_seconds": r.duration_seconds
                }
                for r in results
            ]
        finally:
            _sync_in_progress = False
    
    background_tasks.add_task(run_sync)
    
    return {
        "message": "Sync started in background",
        "check_status": "/data-sync/last-sync"
    }
