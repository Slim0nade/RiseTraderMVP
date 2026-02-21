"""
SSE Events API Routes (T042)

Endpoints for Server-Sent Events streaming.
Provides real-time notifications for:
- Optimization job progress
- Price alerts
- System events
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

import structlog

from src.utils.sse_events import get_sse_manager, SSEEvent

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


# =============================================================================
# SSE Streaming Endpoints
# =============================================================================


@router.get("/stream")
async def stream_events(
    request: Request,
    since_sequence: Optional[int] = Query(
        None,
        description="Only receive events after this sequence number",
    ),
    job_id: Optional[str] = Query(
        None,
        description="Filter events for a specific optimization job",
    ),
):
    """
    Stream real-time SSE events.

    This endpoint establishes a persistent SSE connection for receiving:
    - job_started: Optimization job started
    - job_progress: Optimization progress updates
    - job_complete: Optimization completed successfully
    - job_failed: Optimization failed
    - job_cancelled: Optimization cancelled
    - price_alert: Price level triggered

    The client should handle reconnection and use `since_sequence` to
    resume from where they left off without missing events.

    Example usage:
    ```javascript
    const eventSource = new EventSource('/api/v1/events/stream');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(data);
    };
    eventSource.addEventListener('job_progress', (event) => {
        // Handle progress specifically
    });
    ```
    """
    sse_manager = await get_sse_manager()

    async def event_generator():
        """Generate SSE events for the client."""
        # First, send any missed events if client is reconnecting
        if since_sequence is not None:
            missed_events = sse_manager.get_events_since(since_sequence)
            for event in missed_events:
                if job_id is None or event.data.get("job_id") == job_id:
                    yield {
                        "event": event.event,
                        "id": event.id,
                        "data": event.to_dict(),
                    }

        # Then stream live events
        async for event in sse_manager.subscribe():
            # Check if client disconnected
            if await request.is_disconnected():
                logger.debug("sse_client_disconnected")
                break

            # Filter by job_id if specified
            if job_id is not None and event.data.get("job_id") != job_id:
                continue

            yield {
                "event": event.event,
                "id": event.id,
                "data": event.to_dict(),
            }

    return EventSourceResponse(event_generator())


@router.get("/stream/optimization/{job_id}")
async def stream_optimization_events(
    request: Request,
    job_id: str,
    since_sequence: Optional[int] = Query(None),
):
    """
    Stream events for a specific optimization job.

    Convenience endpoint that filters events for a single job.
    Automatically closes when the job completes, fails, or is cancelled.
    """
    sse_manager = await get_sse_manager()

    async def event_generator():
        """Generate events for the specific job."""
        # Send missed events
        if since_sequence is not None:
            missed_events = sse_manager.get_events_since(since_sequence)
            for event in missed_events:
                if event.data.get("job_id") == job_id:
                    yield {
                        "event": event.event,
                        "id": event.id,
                        "data": event.to_dict(),
                    }

        # Stream live events
        async for event in sse_manager.subscribe():
            if await request.is_disconnected():
                break

            # Only events for this job
            if event.data.get("job_id") != job_id:
                continue

            yield {
                "event": event.event,
                "id": event.id,
                "data": event.to_dict(),
            }

            # Close stream when job ends
            if event.event in ("job_complete", "job_failed", "job_cancelled"):
                break

    return EventSourceResponse(event_generator())


@router.get("/stream/alerts")
async def stream_price_alerts(
    request: Request,
    ticket: Optional[int] = Query(
        None,
        description="Filter alerts for a specific position ticket",
    ),
):
    """
    Stream price alert events only.

    Filters the event stream to only include price_alert events.
    """
    sse_manager = await get_sse_manager()

    async def event_generator():
        """Generate price alert events."""
        async for event in sse_manager.subscribe():
            if await request.is_disconnected():
                break

            # Only price alerts
            if event.event != "price_alert":
                continue

            # Filter by ticket if specified
            if ticket is not None and event.data.get("ticket") != ticket:
                continue

            yield {
                "event": event.event,
                "id": event.id,
                "data": event.to_dict(),
            }

    return EventSourceResponse(event_generator())


# =============================================================================
# Event History Endpoints (for debugging/testing)
# =============================================================================


@router.get("/history")
async def get_event_history(
    since_sequence: Optional[int] = Query(
        None,
        description="Get events since this sequence number",
    ),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Get buffered event history.

    Returns events from the in-memory buffer. Useful for:
    - Debugging SSE connectivity
    - Replaying missed events
    - Testing event emission

    Note: Buffer is limited to the most recent events (default 1000).
    """
    sse_manager = await get_sse_manager()

    if since_sequence is not None:
        events = sse_manager.get_events_since(since_sequence)
    else:
        events = sse_manager._event_buffer[-limit:]

    return {
        "events": [e.to_dict() for e in events[:limit]],
        "total": len(events),
        "current_sequence": sse_manager._sequence,
    }


@router.get("/health")
async def get_sse_health():
    """
    Check SSE manager health status.

    Returns current state of the SSE event system.
    """
    sse_manager = await get_sse_manager()

    return {
        "status": "healthy" if sse_manager._running else "stopped",
        "current_sequence": sse_manager._sequence,
        "buffer_size": len(sse_manager._event_buffer),
        "buffer_capacity": sse_manager._buffer_size,
        "active_subscribers": len(sse_manager._subscribers),
        "redis_connected": sse_manager._redis is not None,
    }
