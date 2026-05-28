from __future__ import annotations

import asyncio
import logging
import os

import clickhouse_connect
import httpx
import redis.asyncio as aioredis

from controllers.anomaly import detect_anomalies
from models import AnomalyEvent, EarthquakeEvent
from poller import POLL_INTERVAL, fetch_events
from writer import write_anomalies, write_earthquakes

logger = logging.getLogger(__name__)

STREAM_EVENTS = "pulse:events"
STREAM_ALERTS = "pulse:alerts"
SEEN_HASH = "pulse:seen-events"


async def _new_or_revised(redis: aioredis.Redis, events: list[EarthquakeEvent]) -> list[EarthquakeEvent]:
    fresh: list[EarthquakeEvent] = []
    pipe = redis.pipeline()
    for event in events:
        pipe.hget(SEEN_HASH, event.event_id)
    previous = await pipe.execute()

    pipe = redis.pipeline()
    for event, stored in zip(events, previous):
        updated = event.updated.isoformat()
        stored_text = stored.decode() if isinstance(stored, bytes) else stored
        if stored_text != updated:
            fresh.append(event)
            pipe.hset(SEEN_HASH, event.event_id, updated)
    if fresh:
        pipe.expire(SEEN_HASH, 7 * 24 * 3600)
        await pipe.execute()
    return fresh


async def _publish_events(redis: aioredis.Redis, events: list[EarthquakeEvent]) -> None:
    if not events:
        return
    pipe = redis.pipeline()
    for event in events:
        pipe.xadd(STREAM_EVENTS, {"data": event.model_dump_json()}, maxlen=50_000, approximate=True)
    await pipe.execute()


async def _publish_alerts(redis: aioredis.Redis, events: list[AnomalyEvent]) -> None:
    if not events:
        return
    pipe = redis.pipeline()
    for event in events:
        pipe.xadd(STREAM_ALERTS, {"data": event.model_dump_json()}, maxlen=10_000, approximate=True)
    await pipe.execute()


async def run() -> None:
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=False)
    clickhouse = await clickhouse_connect.get_async_client(
        host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        database=os.getenv("CLICKHOUSE_DB", "default"),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
    )
    http = httpx.AsyncClient(headers={"User-Agent": "PULSE earthquake assessment app"}, follow_redirects=True)
    logger.info("ingestion started; polling USGS every %ss", POLL_INTERVAL)
    try:
        while True:
            try:
                fetched = await fetch_events(http)
                events = await _new_or_revised(redis, fetched)
                if events:
                    await _publish_events(redis, events)
                    await write_earthquakes(clickhouse, events)
                    anomalies = await detect_anomalies(events, redis)
                    await write_anomalies(clickhouse, anomalies)
                    await _publish_alerts(redis, anomalies)
                    logger.info("processed %d new/revised events and %d anomalies", len(events), len(anomalies))
                else:
                    logger.info("USGS poll returned no new revisions")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ingestion cycle failed")
            await asyncio.sleep(POLL_INTERVAL)
    finally:
        await http.aclose()
        await redis.aclose()
        await clickhouse.close()

