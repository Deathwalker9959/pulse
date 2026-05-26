"""
Anomaly detection + async weather enrichment (extension capability).

Detection runs per poll cycle. Each detected event is:
  1. Written to ClickHouse anomaly_events (weather fields null initially)
  2. Published to Redis Stream pulse:anomalies
  3. Enriched with Open-Meteo weather data (async, best-effort)
  4. Written again (latest row wins via ORDER BY detected_at)
  5. Published to Redis Stream pulse:alerts (enriched payload consumed by API)
"""
from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime, timezone
from typing import Optional

import httpx

from decorators import retry, timed
from models import AnomalyEvent, AnomalyType, FlightState, Severity

logger = logging.getLogger(__name__)

# Emergency squawk codes per ICAO Annex 10.
EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}
SQUAWK_LABELS = {"7500": "hijack", "7600": "radio failure", "7700": "emergency"}

# Rapid descent threshold: 3000 ft/min ≈ 15.24 m/s downward.
# OpenSky vertical_rate is in m/s; negative = descending.
DESCENT_THRESHOLD_MS = -15.24

# Speed outlier: Z-score threshold within one poll batch.
SPEED_ZSCORE_THRESHOLD = 2.5

# Density spike: 1-degree grid cell.
# SCALE: finer grid (0.5° or 0.25°) at higher volumes improves spatial resolution.
GRID_RESOLUTION = 1.0
DENSITY_ZSCORE_THRESHOLD = 3.0


def _grid_key(lat: float, lon: float) -> str:
    cell_lat = math.floor(lat / GRID_RESOLUTION) * GRID_RESOLUTION
    cell_lon = math.floor(lon / GRID_RESOLUTION) * GRID_RESOLUTION
    return f"{cell_lat:.1f}:{cell_lon:.1f}"


@timed(logger=logger, threshold_ms=200)
async def detect_anomalies(
    states: list[FlightState],
    redis,  # redis.asyncio.Redis
) -> list[AnomalyEvent]:
    """Run all detectors over one poll batch. Returns list of detected anomalies."""
    anomalies: list[AnomalyEvent] = []

    anomalies.extend(_detect_emergency_squawks(states))
    anomalies.extend(await _detect_altitude_drops(states, redis))
    anomalies.extend(_detect_speed_outliers(states))
    anomalies.extend(await _detect_density_spikes(states, redis))

    if anomalies:
        logger.info("detected %d anomalies in batch of %d", len(anomalies), len(states))

    await _update_last_states(states, redis)
    return anomalies


def _detect_emergency_squawks(states: list[FlightState]) -> list[AnomalyEvent]:
    events = []
    for s in states:
        if s.squawk in EMERGENCY_SQUAWKS and s.has_position():
            label = SQUAWK_LABELS[s.squawk]
            events.append(AnomalyEvent(
                anomaly_type=AnomalyType.EMERGENCY_SQUAWK,
                severity=Severity.CRITICAL,
                icao24=s.icao24,
                callsign=s.callsign,
                latitude=s.latitude,  # type: ignore[arg-type]
                longitude=s.longitude,  # type: ignore[arg-type]
                detail=f"Squawk {s.squawk} ({label}) — {s.callsign or s.icao24} over {s.origin_country}",
            ))
    return events


async def _detect_altitude_drops(states: list[FlightState], redis) -> list[AnomalyEvent]:
    events = []
    airborne = [s for s in states if s.is_airborne() and s.vertical_rate is not None]
    if not airborne:
        return events

    pipe = redis.pipeline()
    for s in airborne:
        pipe.hgetall(f"pulse:laststate:{s.icao24}")
    results = await pipe.execute()

    for s, prev_data in zip(airborne, results):
        if not prev_data:
            continue
        try:
            key = b"vertical_rate" if b"vertical_rate" in prev_data else "vertical_rate"
            prev_vr = float(prev_data.get(key, 0))
        except (ValueError, TypeError):
            continue

        vr = s.vertical_rate  # type: ignore[assignment]
        # Sustained rapid descent: both current and previous reading below threshold.
        if vr < DESCENT_THRESHOLD_MS and prev_vr < DESCENT_THRESHOLD_MS:
            rate_fpm = abs(vr) * 196.85  # m/s → ft/min
            events.append(AnomalyEvent(
                anomaly_type=AnomalyType.ALTITUDE_DROP,
                severity=Severity.WARNING,
                icao24=s.icao24,
                callsign=s.callsign,
                latitude=s.latitude,  # type: ignore[arg-type]
                longitude=s.longitude,  # type: ignore[arg-type]
                detail=(
                    f"Rapid descent at {rate_fpm:.0f} ft/min — "
                    f"{s.callsign or s.icao24} at {(s.baro_altitude or 0):.0f}m"
                ),
            ))
    return events


def _detect_speed_outliers(states: list[FlightState]) -> list[AnomalyEvent]:
    airborne_with_velocity = [
        s for s in states if s.is_airborne() and s.velocity and s.velocity > 0
    ]
    if len(airborne_with_velocity) < 10:
        return []

    velocities = [s.velocity for s in airborne_with_velocity]  # type: ignore[misc]
    mean = statistics.mean(velocities)
    stdev = statistics.stdev(velocities)
    if stdev == 0:
        return []

    events = []
    for s in airborne_with_velocity:
        z = (s.velocity - mean) / stdev  # type: ignore[operator]
        if z > SPEED_ZSCORE_THRESHOLD:
            events.append(AnomalyEvent(
                anomaly_type=AnomalyType.SPEED_OUTLIER,
                severity=Severity.INFO,
                icao24=s.icao24,
                callsign=s.callsign,
                latitude=s.latitude,  # type: ignore[arg-type]
                longitude=s.longitude,  # type: ignore[arg-type]
                detail=(
                    f"Unusual speed {s.velocity:.0f} m/s (z={z:.1f}) — "  # type: ignore[str-format]
                    f"{s.callsign or s.icao24}"
                ),
            ))
    return events


async def _detect_density_spikes(states: list[FlightState], redis) -> list[AnomalyEvent]:
    """Compare current grid cell counts against rolling history stored in Redis.

    Redis structure: pulse:grid:{key} → list of recent counts (capped at 6).
    SCALE: replace with Redis TimeSeries module for richer statistics at high volume.
    """
    from collections import Counter
    positioned = [s for s in states if s.has_position()]
    if not positioned:
        return []

    cell_counts: Counter[str] = Counter(
        _grid_key(s.latitude, s.longitude)  # type: ignore[arg-type]
        for s in positioned
    )

    keys = list(cell_counts.keys())
    pipe = redis.pipeline()
    for k in keys:
        pipe.lrange(f"pulse:grid:{k}", 0, -1)
    histories = await pipe.execute()

    pipe = redis.pipeline()
    for k, current_count in cell_counts.items():
        pipe.lpush(f"pulse:grid:{k}", current_count)
        pipe.ltrim(f"pulse:grid:{k}", 0, 5)
        pipe.expire(f"pulse:grid:{k}", 3600)
    await pipe.execute()

    events = []
    for k, history_raw in zip(keys, histories):
        if len(history_raw) < 3:
            continue
        try:
            history = [int(v) for v in history_raw]
        except (ValueError, TypeError):
            continue
        mean = statistics.mean(history)
        stdev = statistics.stdev(history) if len(history) > 1 else 0
        current = cell_counts[k]
        if stdev > 0 and (current - mean) / stdev > DENSITY_ZSCORE_THRESHOLD:
            lat_str, lon_str = k.split(":")
            events.append(AnomalyEvent(
                anomaly_type=AnomalyType.DENSITY_SPIKE,
                severity=Severity.WARNING,
                icao24="N/A",
                callsign="",
                latitude=float(lat_str),
                longitude=float(lon_str),
                detail=(
                    f"Density spike: {current} aircraft in 1° cell at "
                    f"{lat_str}°N {lon_str}°E (mean={mean:.1f}, z={(current-mean)/stdev:.1f})"
                ),
            ))
    return events


async def _update_last_states(states: list[FlightState], redis) -> None:
    pipe = redis.pipeline()
    for s in states:
        if s.is_airborne() and s.vertical_rate is not None:
            pipe.hset(
                f"pulse:laststate:{s.icao24}",
                mapping={
                    "vertical_rate": s.vertical_rate,
                    "baro_altitude": s.baro_altitude or 0,
                    "velocity": s.velocity or 0,
                },
            )
            pipe.expire(f"pulse:laststate:{s.icao24}", 120)
    await pipe.execute()


@retry(max_attempts=3, backoff_base=2.0, max_delay=10.0, exceptions=(httpx.HTTPError,))
@timed(logger=logger, threshold_ms=1_000)
async def enrich_with_weather(
    event: AnomalyEvent,
    http: httpx.AsyncClient,
) -> AnomalyEvent:
    """Fetch current weather from Open-Meteo and return enriched event.

    Open-Meteo is free, no auth required, ~100ms typical latency.
    SCALE: cache weather per 1° grid cell with 15-min TTL to avoid
    redundant calls when many anomalies fire in the same region.
    """
    params = {
        "latitude": round(event.latitude, 2),
        "longitude": round(event.longitude, 2),
        "current_weather": "true",
        "hourly": "visibility",
        "forecast_days": 1,
    }
    resp = await http.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=8.0)
    resp.raise_for_status()
    body = resp.json()

    cw = body.get("current_weather", {})
    wind_kmh = cw.get("windspeed", 0)
    wind_kts = wind_kmh * 0.539957

    visibility_m: Optional[float] = None
    vis_list = body.get("hourly", {}).get("visibility", [])
    if vis_list:
        visibility_m = float(vis_list[0])

    wmo_codes = {
        0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
        95: "Thunderstorm", 96: "Thunderstorm+hail", 99: "Thunderstorm+heavy hail",
    }
    code = cw.get("weathercode", -1)
    condition = wmo_codes.get(code, f"WMO {code}")

    return event.model_copy(update={
        "weather_temp_c": cw.get("temperature"),
        "weather_wind_kts": round(wind_kts, 1),
        "weather_condition": condition,
        "weather_visibility": visibility_m,
        "weather_fetched_at": datetime.now(timezone.utc),
    })
