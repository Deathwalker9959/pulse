from __future__ import annotations

import pygeohash

from decorators import retry
from models import AnomalyEvent, EarthquakeEvent


def magnitude_band(magnitude: float) -> str:
    """Classify a magnitude into a USGS severity band (micro…great) for pre-bucketed aggregation."""
    if magnitude < 1:
        return "micro"
    if magnitude < 3:
        return "minor"
    if magnitude < 5:
        return "light"
    if magnitude < 6:
        return "moderate"
    if magnitude < 7:
        return "strong"
    if magnitude < 8:
        return "major"
    return "great"


def depth_band(depth_km: float) -> str:
    """Classify a hypocenter depth into a band (negative/shallow/intermediate/deep)."""
    if depth_km < 0:
        return "negative"
    if depth_km < 70:
        return "shallow"
    if depth_km < 300:
        return "intermediate"
    return "deep"


def geohash5(latitude: float, longitude: float) -> str:
    """Encode a position as a precision-5 geohash; empty string if the coords can't be encoded."""
    try:
        return pygeohash.encode(latitude, longitude, precision=5)
    except Exception:
        return ""


def earthquake_row(event: EarthquakeEvent) -> dict:
    """Flatten an EarthquakeEvent into a ClickHouse row, adding the derived band/geohash columns."""
    return {
        **event.model_dump(mode="python"),
        "mag_band": magnitude_band(event.magnitude),
        "depth_band": depth_band(event.depth_km),
        "geohash": geohash5(event.latitude, event.longitude),
    }


async def _insert(client, table: str, rows: list[dict]) -> None:
    """Column-wise insert of dict rows into `table`; no-op on empty input. Columns taken from row 0."""
    if not rows:
        return
    columns = list(rows[0].keys())
    await client.insert(table, [[row[c] for c in columns] for row in rows], column_names=columns)


@retry(max_attempts=10, backoff_base=2.0, max_delay=30.0)
async def write_earthquakes(client, events: list[EarthquakeEvent]) -> None:
    """Persist earthquakes to ClickHouse (only those with valid coords), retrying on transient failures."""
    await _insert(client, "earthquakes_raw", [earthquake_row(e) for e in events if e.has_position()])


@retry(max_attempts=10, backoff_base=2.0, max_delay=30.0)
async def write_anomalies(client, events: list[AnomalyEvent]) -> None:
    """Persist detected anomalies to ClickHouse, retrying on transient failures."""
    await _insert(client, "anomaly_events", [e.model_dump(mode="python") for e in events])

