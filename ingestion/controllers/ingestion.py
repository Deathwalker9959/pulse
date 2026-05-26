"""
Ingestion controller — orchestrates the poll → stream → store pipeline.

Flow per cycle:
  1. fetch_states() → list[FlightState]
  2. Publish raw states to Redis Stream pulse:flights
  3. write_flights() → ClickHouse flights_raw
  4. detect_anomalies() → list[AnomalyEvent]
  5. For each anomaly:
       a. write_anomaly() → ClickHouse (weather fields null)
       b. Publish to pulse:anomalies stream
       c. enrich_with_weather() → updated AnomalyEvent
       d. update_anomaly_weather() → ClickHouse (latest row)
       e. Publish enriched event to pulse:alerts stream

SCALE: at higher volumes, steps 1–3 and 4–5 can be separate services
consuming the pulse:flights stream via consumer groups.
"""
from __future__ import annotations

import asyncio
import logging
import os

import clickhouse_connect
import httpx
import redis.asyncio as aioredis

from controllers.anomaly import detect_anomalies, enrich_with_weather
from models import AnomalyEvent
from poller import fetch_states
from writer import update_anomaly_weather, write_anomaly, write_flights

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "default")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
OPENSKY_USER = os.getenv("OPENSKY_USER", "")
OPENSKY_PASSWORD = os.getenv("OPENSKY_PASSWORD", "")

STREAM_FLIGHTS = "pulse:flights"
STREAM_ANOMALIES = "pulse:anomalies"
STREAM_ALERTS = "pulse:alerts"


async def _publish_flights(redis: aioredis.Redis, states) -> None:
    if not states:
        return
    pipe = redis.pipeline()
    for s in states:
        pipe.xadd(STREAM_FLIGHTS, {"data": s.model_dump_json()}, maxlen=50_000, approximate=True)
    await pipe.execute()


async def _publish_event(
    redis: aioredis.Redis, stream: str, event: AnomalyEvent, maxlen: int = 10_000,
) -> None:
    await redis.xadd(stream, {"data": event.model_dump_json()}, maxlen=maxlen, approximate=True)


async def _process_anomaly(
    event: AnomalyEvent,
    ch_client,
    redis: aioredis.Redis,
    http: httpx.AsyncClient,
) -> None:
    await write_anomaly(ch_client, event)
    await _publish_event(redis, STREAM_ANOMALIES, event)

    try:
        enriched = await enrich_with_weather(event, http)
        await update_anomaly_weather(ch_client, enriched)
        await _publish_event(redis, STREAM_ALERTS, enriched, maxlen=5_000)
        logger.info(
            "anomaly %s enriched: %s, wind %.1fkts",
            event.anomaly_type, enriched.weather_condition, enriched.weather_wind_kts or 0,
        )
    except Exception as exc:
        # Weather enrichment is best-effort; publish un-enriched alert as fallback.
        logger.warning("weather enrichment failed for %s: %s — publishing without weather", event.event_id, exc)
        await _publish_event(redis, STREAM_ALERTS, event, maxlen=5_000)


async def run_ingestion_loop() -> None:
    """Main ingestion loop — runs until cancelled."""
    redis = aioredis.from_url(REDIS_URL, decode_responses=False)
    ch_client = await clickhouse_connect.get_async_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DB,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )
    http = httpx.AsyncClient(
        headers={"User-Agent": "PULSE/1.0 (open-source assessment project)"},
        follow_redirects=True,
    )

    logger.info("ingestion loop started")
    try:
        while True:
            try:
                states = await fetch_states(
                    http,
                    username=OPENSKY_USER,
                    password=OPENSKY_PASSWORD,
                )
                await asyncio.gather(
                    write_flights(ch_client, states),
                    _publish_flights(redis, states),
                )
                anomalies = await detect_anomalies(states, redis)
                if anomalies:
                    await asyncio.gather(*[
                        _process_anomaly(ev, ch_client, redis, http)
                        for ev in anomalies
                    ])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Catch-all so the loop survives unexpected errors.
                # @retry handles retries inside sub-functions; this covers the rest.
                logger.error("unexpected error in ingestion cycle: %s", exc, exc_info=True)
                await asyncio.sleep(5)
    finally:
        await http.aclose()
        await redis.aclose()
        await ch_client.close()
        logger.info("ingestion loop stopped")
