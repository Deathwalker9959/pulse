"""
Alert controller — Redis Streams consumer + WebSocket fan-out.

One AlertManager instance per API process. All WebSocket connections share
the same Redis Streams cursor, so each alert is delivered to every connected
client (fan-out, not work-queue).

SCALE: Multiple API instances each get their own consumer in the
'api-workers' consumer group → no duplicate delivery across instances.
Add a Redis Cluster when stream throughput exceeds single-node limits.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from db import query
from decorators import cached, timed

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

STREAM_ALERTS = "pulse:alerts"
CONSUMER_GROUP = "api-workers"
CONSUMER_NAME = "api-0"  # unique per pod; set via env in multi-instance deploy


class AlertManager:
    """Manages WebSocket connections and streams alerts to all of them."""

    def __init__(self) -> None:
        self._connections: set["WebSocket"] = set()
        self._running = False

    async def start(self, redis: aioredis.Redis) -> None:
        """Create consumer group (idempotent) and start consume loop."""
        try:
            await redis.xgroup_create(STREAM_ALERTS, CONSUMER_GROUP, id="$", mkstream=True)
        except Exception:
            pass  # group already exists
        self._running = True
        asyncio.create_task(self._consume_loop(redis), name="alert-consume")
        logger.info("AlertManager started, consuming %s", STREAM_ALERTS)

    async def stop(self) -> None:
        self._running = False

    async def connect(self, ws: "WebSocket") -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.debug("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: "WebSocket") -> None:
        self._connections.discard(ws)
        logger.debug("WS client disconnected (%d total)", len(self._connections))

    async def _consume_loop(self, redis: aioredis.Redis) -> None:
        while self._running:
            try:
                results = await redis.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_ALERTS: ">"},
                    count=50,
                    block=2_000,
                )
                if not results:
                    continue
                for _stream, messages in results:
                    for msg_id, fields in messages:
                        payload = fields.get(b"data") or fields.get("data", b"")
                        if payload:
                            await self._broadcast(payload if isinstance(payload, str) else payload.decode())
                        await redis.xack(STREAM_ALERTS, CONSUMER_GROUP, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("alert consume loop error: %s", exc, exc_info=True)
                await asyncio.sleep(1)

    async def _broadcast(self, message: str) -> None:
        dead: list["WebSocket"] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


alert_manager = AlertManager()


@cached(ttl=30, key_prefix="anomalies:history")
@timed(threshold_ms=500)
async def get_anomaly_history(
    *,
    redis: aioredis.Redis,
    limit: int = 100,
    from_ts: datetime | None = None,
) -> list[dict]:
    """Recent anomaly events from ClickHouse, newest first."""
    t0 = from_ts or (datetime.now(timezone.utc) - timedelta(hours=24))
    rows = await query(
        """
        SELECT
            toString(event_id)  AS event_id,
            detected_at, anomaly_type, severity,
            icao24, callsign, latitude, longitude, detail,
            weather_temp_c, weather_wind_kts, weather_condition,
            weather_visibility, weather_fetched_at
        FROM anomaly_events
        WHERE detected_at >= {t0:DateTime}
        ORDER BY detected_at DESC
        LIMIT {limit:UInt32}
        """,
        params={"t0": t0, "limit": limit},
    )
    return rows
