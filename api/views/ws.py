from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cache import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class StreamBroadcaster:
    """Fans out one Redis stream to every connected WebSocket via a single background reader task."""

    def __init__(self, stream: str, name: str) -> None:
        """Configure (but don't start) a broadcaster for `stream`; `name` labels logs/tasks."""
        self.stream = stream
        self.name = name
        self.connections: set[WebSocket] = set()
        self.running = False
        self.last_id = "$"
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background stream-reader task once (idempotent)."""
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run(), name=f"{self.name}-broadcast")
        logger.info("%s broadcaster started on %s", self.name, self.stream)

    async def stop(self) -> None:
        """Signal the reader to stop and await cancellation of its task."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket and register it to receive broadcasts."""
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Drop a WebSocket from the broadcast set (safe if already absent)."""
        self.connections.discard(websocket)

    async def _run(self) -> None:
        """Block-read the Redis stream and push each new message to all clients until stopped."""
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
        """Send `payload` to every client, pruning any whose send fails."""
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


async def _serve(websocket: WebSocket, broadcaster: StreamBroadcaster) -> None:
    """Register the socket with a broadcaster and hold the connection open until it disconnects."""
    await broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        broadcaster.disconnect(websocket)


@router.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    """WS /ws/events — live stream of new/revised earthquake events."""
    await _serve(websocket, event_broadcaster)


@router.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket) -> None:
    """WS /ws/alerts — live stream of detected anomaly alerts."""
    await _serve(websocket, alert_broadcaster)

