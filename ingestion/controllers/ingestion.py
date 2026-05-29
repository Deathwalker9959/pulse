from __future__ import annotations

import asyncio
import logging
import os

import httpx
import redis.asyncio as aioredis

from controllers.anomaly import detect_anomalies
from db import get_clickhouse_client
from models import AnomalyEvent, EarthquakeEvent
from poller import POLL_INTERVAL, fetch_events
from writer import write_anomalies, write_earthquakes

logger = logging.getLogger(__name__)

STREAM_EVENTS = "pulse:events"
STREAM_ALERTS = "pulse:alerts"
SEEN_HASH = "pulse:seen-events"


async def _new_or_revised(redis: aioredis.Redis, events: list[EarthquakeEvent]) -> list[EarthquakeEvent]:
    """Keep only events whose `updated` timestamp differs from the last-seen value in Redis, recording the new value."""
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


async def _publish(
    redis: aioredis.Redis,
    stream: str,
    events: list[EarthquakeEvent] | list[AnomalyEvent],
    maxlen: int,
) -> None:
    """Append each event's JSON to a capped Redis stream in one pipeline (no-op if empty)."""
    if not events:
        return
    pipe = redis.pipeline()
    for event in events:
        pipe.xadd(stream, {"data": event.model_dump_json()}, maxlen=maxlen, approximate=True)
    await pipe.execute()


async def run() -> None:
    """Main ingestion loop: poll USGS, dedup, then publish + persist events and detected anomalies forever."""
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=False)
    clickhouse = await get_clickhouse_client()
    http = httpx.AsyncClient(headers={"User-Agent": "PULSE earthquake assessment app"}, follow_redirects=True)
    logger.info("ingestion started; polling USGS every %ss", POLL_INTERVAL)
    try:
        while True:
            try:
                fetched = await fetch_events(http)
                events = await _new_or_revised(redis, fetched)
                if events:
                    earthquake_task = asyncio.gather(
                        _publish(redis, STREAM_EVENTS, events, maxlen=50_000),
                        write_earthquakes(clickhouse, events),
                    )
                    try:
                        anomalies = await detect_anomalies(events, redis)
                    except asyncio.CancelledError:
                        earthquake_task.cancel()
                        await asyncio.gather(earthquake_task, return_exceptions=True)
                        raise
                    except Exception:
                        await asyncio.gather(earthquake_task, return_exceptions=True)
                        raise
                    await earthquake_task
                    await asyncio.gather(
                        write_anomalies(clickhouse, anomalies),
                        _publish(redis, STREAM_ALERTS, anomalies, maxlen=10_000),
                    )
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

