"""WebSocket view — real-time alert stream to dashboard clients."""
from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from cache import get_redis
from controllers.alerts import alert_manager, get_anomaly_history

router = APIRouter(tags=["alerts"])


@router.get("/api/anomalies/history")
async def anomaly_history(
    limit: int = 100,
    redis=Depends(get_redis),
) -> list[dict]:
    """Recent anomaly events with weather correlation, newest first."""
    return await get_anomaly_history(redis=redis, limit=limit)


@router.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket) -> None:
    """Stream enriched anomaly alerts to the dashboard in real time.

    Protocol: server sends JSON-serialised AnomalyEvent objects.
    Client sends nothing (read-only stream).
    Auto-reconnect is handled by the frontend useAlerts hook.

    SCALE: all clients on this API instance receive every alert (fan-out).
    Across multiple instances each has its own cursor in the same Redis
    consumer group — no duplicate delivery.
    """
    await alert_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        alert_manager.disconnect(websocket)
    except Exception:
        alert_manager.disconnect(websocket)
