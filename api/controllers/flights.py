"""Flight query controllers — live snapshot and history."""
from __future__ import annotations

from datetime import datetime

import redis.asyncio as aioredis

from db import query
from decorators import cached, timed


@cached(ttl=10, key_prefix="flights:live")
@timed(threshold_ms=500)
async def get_live(
    *,
    redis: aioredis.Redis,
) -> list[dict]:
    """Latest known state per aircraft (max one row per ICAO24).

    Uses anyLast aggregation over the last 2 minutes to avoid FINAL.
    SCALE: Replace with a flights_latest table (AggregatingMergeTree keyed
    by icao24) populated by a materialized view for O(1) lookups without FINAL.
    """
    rows = await query("""
        SELECT
            icao24, callsign, origin_country,
            anyLast(latitude)      AS latitude,
            anyLast(longitude)     AS longitude,
            anyLast(baro_altitude) AS baro_altitude,
            anyLast(on_ground)     AS on_ground,
            anyLast(velocity)      AS velocity,
            anyLast(true_track)    AS true_track,
            anyLast(vertical_rate) AS vertical_rate,
            anyLast(squawk)        AS squawk,
            max(last_contact)      AS last_contact
        FROM flights_raw
        WHERE time_position >= now() - INTERVAL 2 MINUTE
          AND latitude != 0 AND longitude != 0
        GROUP BY icao24, callsign, origin_country
        LIMIT 5000
    """)
    return rows


@cached(ttl=60, key_prefix="flights:history")
@timed(threshold_ms=1_000)
async def get_history(
    *,
    redis: aioredis.Redis,
    icao24: str,
    from_ts: datetime,
    to_ts: datetime,
) -> list[dict]:
    """Time-ordered position track for a single aircraft."""
    rows = await query(
        """
        SELECT
            time_position, latitude, longitude,
            baro_altitude, velocity, on_ground
        FROM flights_raw FINAL
        WHERE icao24 = {icao24:String}
          AND time_position BETWEEN {from_ts:DateTime} AND {to_ts:DateTime}
          AND latitude != 0 AND longitude != 0
        ORDER BY time_position ASC
        LIMIT 10000
        """,
        params={"icao24": icao24, "from_ts": from_ts, "to_ts": to_ts},
    )
    return rows
