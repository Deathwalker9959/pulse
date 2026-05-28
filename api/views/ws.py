from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cache import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class StreamBroadcaster:
    def __init__(self, stream: str, name: str) -> None:
        self.stream = stream
        self.name = name
        self.connections: set[WebSocket] = set()
        self.running = False
        self.last_id = "$"
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run(), name=f"{self.name}-broadcast")
        logger.info("%s broadcaster started on %s", self.name, self.stream)

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def _run(self) -> None:
        redis = get_redis()
        while self.running:
            try:
                response = await redis.xread({self.stream: self.last_id}, count=100, block=2000)
                for _stream, messages in response:
                    for message_id, fields in messages:
                        self.last_id = message_id
                        payload = fields.get("data")
                        if payload:
                            await self._broadcast(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s broadcaster failed", self.name)
                await asyncio.sleep(1)

    async def _broadcast(self, payload: str) -> None:
        dead: list[WebSocket] = []
        for websocket in list(self.connections):
            try:
                await websocket.send_text(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)


event_broadcaster = StreamBroadcaster("pulse:events", "live-events")
alert_broadcaster = StreamBroadcaster("pulse:alerts", "alerts")


@router.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await event_broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_broadcaster.disconnect(websocket)
    except Exception:
        event_broadcaster.disconnect(websocket)


@router.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket) -> None:
    await alert_broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        alert_broadcaster.disconnect(websocket)
    except Exception:
        alert_broadcaster.disconnect(websocket)

