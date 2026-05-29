from __future__ import annotations

import pygeohash

from decorators import retry
from models import AnomalyEvent, EarthquakeEvent


def magnitude_band(magnitude: float) -> str:
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
    if depth_km < 0:
        return "negative"
    if depth_km < 70:
        return "shallow"
    if depth_km < 300:
        return "intermediate"
    return "deep"


def geohash5(latitude: float, longitude: float) -> str:
    try:
        return pygeohash.encode(latitude, longitude, precision=5)
    except Exception:
        return ""


def earthquake_row(event: EarthquakeEvent) -> dict:
    return {
        "event_id": event.event_id,
        "time": event.time,
        "updated": event.updated,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "depth_km": event.depth_km,
        "magnitude": event.magnitude,
        "mag_type": event.mag_type,
        "place": event.place,
        "event_type": event.event_type,
        "status": event.status,
        "alert": event.alert,
        "tsunami": event.tsunami,
        "significance": event.significance,
        "net": event.net,
        "nst": event.nst,
        "gap": event.gap,
        "mag_band": magnitude_band(event.magnitude),
        "depth_band": depth_band(event.depth_km),
        "geohash": geohash5(event.latitude, event.longitude),
    }


def anomaly_row(event: AnomalyEvent) -> dict:
    return event.model_dump(mode="python")


async def _insert(client, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    await client.insert(table, [[row[c] for c in columns] for row in rows], column_names=columns)


@retry(max_attempts=10, backoff_base=2.0, max_delay=30.0)
async def write_earthquakes(client, events: list[EarthquakeEvent]) -> None:
    await _insert(client, "earthquakes_raw", [earthquake_row(e) for e in events if e.has_position()])


@retry(max_attempts=10, backoff_base=2.0, max_delay=30.0)
async def write_anomalies(client, events: list[AnomalyEvent]) -> None:
    await _insert(client, "anomaly_events", [anomaly_row(e) for e in events])

