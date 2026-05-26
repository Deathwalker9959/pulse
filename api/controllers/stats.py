"""Aggregation query controllers — top-N, hourly, density."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import redis.asyncio as aioredis

from db import query
from decorators import cached, timed


def _default_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=24), now


@cached(ttl=30, key_prefix="stats:topn")
@timed(threshold_ms=500)
async def get_top_n(
    *,
    redis: aioredis.Redis,
    field: Literal["origin_country", "callsign"],
    limit: int,
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> list[dict]:
    """Top-N aircraft count grouped by field over a time window.

    Uses hourly MV for origin_country (fast path); raw table for callsign.
    SCALE: add callsign to MV if this query becomes a hot path.
    """
    t0, t1 = from_ts or _default_window()[0], to_ts or _default_window()[1]

    if field == "origin_country":
        rows = await query(
            """
            SELECT origin_country AS label, sum(flight_count) AS count
            FROM flights_hourly_mv_data
            WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
            GROUP BY origin_country
            ORDER BY count DESC
            LIMIT {limit:UInt32}
            """,
            params={"t0": t0, "t1": t1, "limit": limit},
        )
    else:
        rows = await query(
            """
            SELECT callsign AS label, count() AS count
            FROM flights_raw
            WHERE time_position BETWEEN {t0:DateTime} AND {t1:DateTime}
              AND callsign != ''
            GROUP BY callsign
            ORDER BY count DESC
            LIMIT {limit:UInt32}
            """,
            params={"t0": t0, "t1": t1, "limit": limit},
        )
    return rows


@cached(ttl=60, key_prefix="stats:hourly")
@timed(threshold_ms=500)
async def get_hourly(
    *,
    redis: aioredis.Redis,
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> list[dict]:
    """Hourly flight counts from the materialized view (all countries summed)."""
    t0, t1 = from_ts or _default_window()[0], to_ts or _default_window()[1]
    rows = await query(
        """
        SELECT
            hour,
            sum(flight_count)   AS flight_count,
            avg(avg_altitude)   AS avg_altitude,
            avg(avg_velocity)   AS avg_velocity,
            sum(airborne_count) AS airborne_count
        FROM flights_hourly_mv_data
        WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
        GROUP BY hour
        ORDER BY hour ASC
        """,
        params={"t0": t0, "t1": t1},
    )
    return rows


@cached(ttl=30, key_prefix="stats:density")
@timed(threshold_ms=1_000)
async def get_density(
    *,
    redis: aioredis.Redis,
    bbox: str,
    interval: Literal["1h", "6h", "24h"],
) -> list[dict]:
    """Count aircraft per 1° grid cell within a bounding box.

    SCALE: pre-compute via materialized view keyed on (toStartOfHour, grid_lat, grid_lon)
    for instant response at higher volumes.
    """
    interval_map = {"1h": 1, "6h": 6, "24h": 24}
    hours = interval_map[interval]
    lon_min, lat_min, lon_max, lat_max = map(float, bbox.split(","))

    rows = await query(
        """
        SELECT
            floor(latitude)  AS lat,
            floor(longitude) AS lon,
            count()          AS count
        FROM flights_raw
        WHERE time_position >= now() - INTERVAL {hours:UInt32} HOUR
          AND longitude BETWEEN {lon_min:Float64} AND {lon_max:Float64}
          AND latitude  BETWEEN {lat_min:Float64} AND {lat_max:Float64}
          AND latitude != 0 AND longitude != 0
        GROUP BY lat, lon
        ORDER BY count DESC
        LIMIT 2000
        """,
        params={
            "hours": hours,
            "lon_min": lon_min, "lon_max": lon_max,
            "lat_min": lat_min, "lat_max": lat_max,
        },
    )
    return rows
