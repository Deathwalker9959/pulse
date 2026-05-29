from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from itertools import chain
from typing import Iterator

import httpx

from controllers.anomaly import _data_quality, _significant_events, _tsunami_risk, historical_pattern_anomalies
from db import get_clickhouse_client
from decorators import retry
from models import EarthquakeEvent
from writer import write_anomalies, write_earthquakes

COMCAT_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
COMCAT_LIMIT = 20_000
SYNC_KEY = "last_synced_to"
HISTORICAL_START = date(1970, 1, 1)
logger = logging.getLogger(__name__)


def month_ranges(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Yield (month_start, month_end) pairs covering [start, end], one calendar month at a time."""
    current = start.replace(day=1)
    while current <= end:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = min(next_month - timedelta(days=1), end)
        yield current, month_end
        current = next_month


async def get_last_synced(clickhouse) -> date:
    """Read the last fully-synced date from sync state, or HISTORICAL_START if never synced.

    The caller clamps this forward to the retention window, so the 1970 default never causes
    a futile multi-decade crawl through data the earthquakes_raw TTL would immediately delete.
    """
    result = await clickhouse.query(
        "SELECT value FROM ingestion_sync_state FINAL WHERE key = {key:String}",
        parameters={"key": SYNC_KEY},
    )
    if result.result_rows:
        return date.fromisoformat(result.result_rows[0][0])
    return HISTORICAL_START


async def set_last_synced(clickhouse, d: date) -> None:
    """Persist `d` as the new high-water mark for historical sync progress."""
    await clickhouse.insert(
        "ingestion_sync_state",
        [[SYNC_KEY, d.isoformat()]],
        column_names=["key", "value"],
    )


@retry(max_attempts=5, backoff_base=2.0, max_delay=30.0, exceptions=(httpx.HTTPError,))
async def fetch_month(http: httpx.AsyncClient, t0: date, t1: date) -> list[EarthquakeEvent]:
    """Fetch one month of events from USGS ComCat; warns if the 20k cap is hit (possible truncation)."""
    params = {
        "format": "geojson",
        "starttime": t0.isoformat(),
        "endtime": (t1 + timedelta(days=1)).isoformat(),
        "limit": str(COMCAT_LIMIT),
        "orderby": "time-asc",
    }
    response = await http.get(COMCAT_URL, params=params, timeout=60.0)
    response.raise_for_status()
    features = response.json().get("features", [])
    if len(features) == COMCAT_LIMIT:
        logger.warning("month %s–%s hit 20k cap — some events may be missing", t0, t1)
    return [EarthquakeEvent.from_geojson_feature(f) for f in features if f.get("id")]


RETENTION_DAYS = 400  # must match earthquakes_raw TTL


async def backfill_anomalies_for_range(clickhouse, start: datetime, end: datetime) -> int:
    """Re-run anomaly detection over stored events in [start, end] (clamped to retention) and persist results."""
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    effective_start = max(start, retention_cutoff)
    if effective_start >= end:
        return 0
    result = await clickhouse.query(
        """
        SELECT event_id, time, updated, latitude, longitude, depth_km, magnitude, mag_type, place,
               event_type, status, alert, tsunami, significance, net, nst, gap
        FROM earthquakes_raw FINAL
        WHERE time >= {start:DateTime} AND time <= {end:DateTime}
        ORDER BY time ASC
        """,
        parameters={"start": effective_start, "end": end},
    )
    events = [EarthquakeEvent(**row) for row in result.named_results()]
    if not events:
        return 0
    anomalies = list(chain(_significant_events(events), _tsunami_risk(events), _data_quality(events), historical_pattern_anomalies(events)))
    if not anomalies:
        return 0
    await write_anomalies(clickhouse, anomalies)
    return len(anomalies)


def _seconds_until_midnight() -> float:
    """Seconds until 00:05 UTC tomorrow — the idle interval between completed daily sync passes."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return (tomorrow - now).total_seconds()


async def run_historical_sync() -> None:
    """Daily catalog backfill: fetch month-by-month from last-synced to yesterday (prefetching ahead), then sleep."""
    clickhouse = await get_clickhouse_client()
    http = httpx.AsyncClient(
        headers={"User-Agent": "PULSE/historical-sync"},
        follow_redirects=True,
    )
    logger.info("historical sync service started")
    try:
        while True:
            try:
                # Don't bother fetching data older than the earthquakes_raw retention window —
                # the table's TTL (RETENTION_DAYS) deletes it on merge, so syncing it is wasted
                # work that never persists. Clamp a fresh or stale high-water mark forward.
                earliest = date.today() - timedelta(days=RETENTION_DAYS)
                last = max(await get_last_synced(clickhouse), earliest)
                target = date.today() - timedelta(days=1)
                if last >= target:
                    wait = _seconds_until_midnight()
                    logger.info("historical sync current (last=%s); sleeping %.0fs until midnight", last, wait)
                    await asyncio.sleep(wait)
                    continue
                logger.info("historical sync: %s → %s", last, target)
                months = list(month_ranges(last, target))
                prefetch: asyncio.Task[list[EarthquakeEvent]] | None = (
                    asyncio.create_task(fetch_month(http, *months[0])) if months else None
                )
                try:
                    for i, (t0, t1) in enumerate(months):
                        logger.info("syncing %s – %s", t0, t1)
                        try:
                            events = await prefetch if prefetch else []
                        except Exception:
                            logger.exception("failed to fetch %s – %s; skipping", t0, t1)
                            events = []

                        prefetch = (
                            asyncio.create_task(fetch_month(http, *months[i + 1]))
                            if i + 1 < len(months) else None
                        )

                        if events:
                            await write_earthquakes(clickhouse, events)
                            start_dt = datetime.combine(t0, datetime.min.time(), tzinfo=timezone.utc)
                            end_dt = datetime.combine(t1 + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) - timedelta(seconds=1)
                            anomaly_count = await backfill_anomalies_for_range(clickhouse, start_dt, end_dt)
                            logger.info("  wrote %d events, %d anomalies", len(events), anomaly_count)
                        await set_last_synced(clickhouse, t1)
                finally:
                    if prefetch is not None:
                        if not prefetch.done():
                            prefetch.cancel()
                        await asyncio.gather(prefetch, return_exceptions=True)
                logger.info("historical sync pass complete")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("historical sync error; retrying in 60s")
                await asyncio.sleep(60)
    finally:
        await http.aclose()
        await clickhouse.close()
