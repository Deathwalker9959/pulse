from __future__ import annotations

import os

import httpx

from decorators import retry
from models import EarthquakeEvent

USGS_FEED_URL = os.getenv(
    "USGS_FEED_URL",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
)
POLL_INTERVAL = int(os.getenv("USGS_POLL_INTERVAL", "60"))


@retry(max_attempts=5, backoff_base=2.0, max_delay=30.0, exceptions=(httpx.HTTPError,))
async def fetch_events(http: httpx.AsyncClient) -> list[EarthquakeEvent]:
    response = await http.get(USGS_FEED_URL, timeout=20.0)
    response.raise_for_status()
    body = response.json()
    return [
        EarthquakeEvent.from_geojson_feature(feature)
        for feature in body.get("features", [])
        if feature.get("id")
    ]

