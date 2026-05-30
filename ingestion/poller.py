from __future__ import annotations

import asyncio
import os

import httpx

from decorators import retry
from models import EarthquakeEvent

USGS_FEED_URL = os.getenv(
    "USGS_FEED_URL",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
)
USGS_SECONDARY_FEED_URL = os.getenv("USGS_SECONDARY_FEED_URL", "")
POLL_INTERVAL = int(os.getenv("USGS_POLL_INTERVAL", "60"))


async def _fetch_one(http: httpx.AsyncClient, url: str) -> list[EarthquakeEvent]:
    """Fetch a single USGS GeoJSON feed URL and parse it into EarthquakeEvents."""
    response = await http.get(url, timeout=20.0)
    response.raise_for_status()
    body = response.json()
    return [
        EarthquakeEvent.from_geojson_feature(feature)
        for feature in body.get("features", [])
        if feature.get("id")
    ]


@retry(max_attempts=5, backoff_base=2.0, max_delay=30.0, exceptions=(httpx.HTTPError,))
async def fetch_events(http: httpx.AsyncClient) -> list[EarthquakeEvent]:
    """Fetch all configured USGS feeds concurrently, merge, and dedup by latest updated timestamp."""
    urls = [u for u in (USGS_FEED_URL, USGS_SECONDARY_FEED_URL) if u]
    results = await asyncio.gather(*(_fetch_one(http, u) for u in urls))
    seen: dict[str, EarthquakeEvent] = {}
    for event in (e for batch in results for e in batch):
        existing = seen.get(event.event_id)
        if existing is None or event.updated > existing.updated:
            seen[event.event_id] = event
    return list(seen.values())
