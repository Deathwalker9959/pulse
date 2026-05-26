"""ClickHouse batch writer for FlightState and AnomalyEvent records."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from decorators import retry, timed
from models import AnomalyEvent, FlightState

if TYPE_CHECKING:
    import clickhouse_connect

logger = logging.getLogger(__name__)


def _flight_row(s: FlightState) -> dict:
    now = datetime.utcnow()
    return {
        "icao24": s.icao24,
        "callsign": s.callsign,
        "origin_country": s.origin_country,
        "time_position": s.time_position or now,
        "last_contact": s.last_contact or now,
        "longitude": s.longitude or 0.0,
        "latitude": s.latitude or 0.0,
        "baro_altitude": s.baro_altitude or 0.0,
        "on_ground": s.on_ground,
        "velocity": s.velocity or 0.0,
        "true_track": s.true_track or 0.0,
        "vertical_rate": s.vertical_rate or 0.0,
        "squawk": s.squawk,
    }


def _anomaly_row(a: AnomalyEvent) -> dict:
    return {
        "event_id": a.event_id,
        "detected_at": a.detected_at,
        "anomaly_type": a.anomaly_type.value,
        "severity": a.severity.value,
        "icao24": a.icao24,
        "callsign": a.callsign,
        "latitude": a.latitude,
        "longitude": a.longitude,
        "detail": a.detail,
        "weather_temp_c": a.weather_temp_c,
        "weather_wind_kts": a.weather_wind_kts,
        "weather_condition": a.weather_condition,
        "weather_visibility": a.weather_visibility,
        "weather_fetched_at": a.weather_fetched_at,
    }


@retry(max_attempts=5, backoff_base=2.0, max_delay=30.0)
@timed(logger=logger, threshold_ms=2_000)
async def write_flights(client: "clickhouse_connect.driver.AsyncClient", states: list[FlightState]) -> None:
    if not states:
        return
    rows = [_flight_row(s) for s in states if s.has_position()]
    if not rows:
        return
    cols = list(rows[0].keys())
    data = [[r[c] for c in cols] for r in rows]
    await client.insert("flights_raw", data, column_names=cols)
    logger.debug("inserted %d flight rows", len(rows))


@retry(max_attempts=5, backoff_base=2.0, max_delay=30.0)
@timed(logger=logger, threshold_ms=500)
async def write_anomaly(client: "clickhouse_connect.driver.AsyncClient", event: AnomalyEvent) -> None:
    row = _anomaly_row(event)
    cols = list(row.keys())
    await client.insert("anomaly_events", [[row[c] for c in cols]], column_names=cols)
    logger.debug("inserted anomaly %s (%s)", event.event_id, event.anomaly_type)


@retry(max_attempts=5, backoff_base=2.0, max_delay=30.0)
@timed(logger=logger, threshold_ms=500)
async def update_anomaly_weather(
    client: "clickhouse_connect.driver.AsyncClient",
    event: AnomalyEvent,
) -> None:
    """Re-insert enriched anomaly; ClickHouse keeps both rows, latest read via ORDER BY."""
    await write_anomaly(client, event)
