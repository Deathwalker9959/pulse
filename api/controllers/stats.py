from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from decorators import cached
from db import query

VALID_BUCKETS = {"1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"}

RANGE_PRESETS: dict[str, tuple[timedelta | None, str]] = {
    "1h":  (timedelta(hours=1),  "5m"),
    "6h":  (timedelta(hours=6),  "15m"),
    "24h": (timedelta(hours=24), "1h"),
    "7d":  (timedelta(days=7),   "6h"),
    "30d": (timedelta(days=30),  "1d"),
    "ytd": (None,                "1d"),
}


def default_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=24), now


def auto_bucket(t0: datetime, t1: datetime) -> str:
    span = (t1 - t0).total_seconds()
    if span <= 3600:
        return "5m"
    if span <= 6 * 3600:
        return "15m"
    if span <= 24 * 3600:
        return "1h"
    if span <= 7 * 86400:
        return "6h"
    return "1d"


def resolve_range(name: str) -> tuple[datetime, datetime, str]:
    span, bucket = RANGE_PRESETS[name]
    now = datetime.now(timezone.utc)
    t0 = datetime(now.year, 1, 1, tzinfo=timezone.utc) if span is None else now - span
    return t0, now, bucket


def cache_ttl(to_ts: datetime | None) -> int:
    target = to_ts or datetime.now(timezone.utc)
    aware = target if target.tzinfo else target.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - aware).total_seconds()
    if age_seconds < 300:
        return 15
    if age_seconds < 3600:
        return 60
    return 300


@cached(ttl=30, key_prefix="stats:topn")
async def get_top_n(*, redis, field: Literal["net", "place"], limit: int, from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    if field == "net":
        return await query("""
            SELECT net AS label, sum(event_count) AS count
            FROM earthquakes_hourly_mv_data
            WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
            GROUP BY net
            ORDER BY count DESC
            LIMIT {limit:UInt32}
        """, {"t0": t0, "t1": t1, "limit": limit})
    return await query("""
        SELECT place AS label, count() AS count
        FROM earthquakes_raw
        WHERE time BETWEEN {t0:DateTime} AND {t1:DateTime}
          AND place != ''
        GROUP BY place
        ORDER BY count DESC
        LIMIT {limit:UInt32}
    """, {"t0": t0, "t1": t1, "limit": limit})


@cached(ttl=30, key_prefix="stats:timeseries")
async def get_timeseries(*, redis, bucket: Literal["1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"], from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    if bucket == "1h":
        return await query("""
            SELECT
                time,
                event_count,
                if(event_count > 0, magnitude_sum / event_count, 0) AS avg_magnitude
            FROM
            (
                SELECT
                    hour AS time,
                    sum(event_count) AS event_count,
                    sum(magnitude_sum) AS magnitude_sum
                FROM earthquakes_hourly_mv_data
                WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
                GROUP BY hour
            )
            ORDER BY time ASC
        """, {"t0": t0, "t1": t1})
    if bucket == "6h":
        return await query("""
            SELECT
                time,
                event_count,
                if(event_count > 0, magnitude_sum / event_count, 0) AS avg_magnitude
            FROM (
                SELECT
                    toStartOfInterval(hour, INTERVAL 6 HOUR, 'UTC') AS time,
                    sum(event_count) AS event_count,
                    sum(magnitude_sum) AS magnitude_sum
                FROM earthquakes_hourly_mv_data
                WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
                GROUP BY time
            )
            ORDER BY time ASC
        """, {"t0": t0, "t1": t1})
    if bucket == "1d":
        return await query("""
            SELECT
                time,
                event_count,
                if(event_count > 0, magnitude_sum / event_count, 0) AS avg_magnitude
            FROM (
                SELECT
                    toStartOfDay(hour, 'UTC') AS time,
                    sum(event_count) AS event_count,
                    sum(magnitude_sum) AS magnitude_sum
                FROM earthquakes_hourly_mv_data
                WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
                GROUP BY time
            )
            ORDER BY time ASC
        """, {"t0": t0, "t1": t1})
    if bucket == "1mo":
        return await query("""
            SELECT
                time,
                event_count,
                if(event_count > 0, magnitude_sum / event_count, 0) AS avg_magnitude
            FROM (
                SELECT
                    toStartOfMonth(hour, 'UTC') AS time,
                    sum(event_count) AS event_count,
                    sum(magnitude_sum) AS magnitude_sum
                FROM earthquakes_hourly_mv_data
                WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
                GROUP BY time
            )
            ORDER BY time ASC
        """, {"t0": t0, "t1": t1})
    if bucket == "1y":
        return await query("""
            SELECT
                time,
                event_count,
                if(event_count > 0, magnitude_sum / event_count, 0) AS avg_magnitude
            FROM (
                SELECT
                    toStartOfYear(hour, 'UTC') AS time,
                    sum(event_count) AS event_count,
                    sum(magnitude_sum) AS magnitude_sum
                FROM earthquakes_hourly_mv_data
                WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
                GROUP BY time
            )
            ORDER BY time ASC
        """, {"t0": t0, "t1": t1})
    interval = {"1m": 1, "5m": 5, "15m": 15}[bucket]
    return await query("""
        SELECT
            toStartOfInterval(time, INTERVAL {interval:UInt32} MINUTE) AS time,
            count() AS event_count,
            avg(toFloat64(magnitude)) AS avg_magnitude
        FROM earthquakes_raw
        WHERE time BETWEEN {t0:DateTime} AND {t1:DateTime}
        GROUP BY time
        ORDER BY time ASC
    """, {"t0": t0, "t1": t1, "interval": interval})


@cached(ttl=60, key_prefix="stats:magbands")
async def get_magnitude_bands(*, redis, from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    return await query("""
        SELECT mag_band, sum(event_count) AS event_count
        FROM earthquakes_mag_band_mv_data
        WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
          AND mag_band != ''
        GROUP BY mag_band
        ORDER BY event_count DESC
    """, {"t0": t0, "t1": t1})


@cached(ttl=60, key_prefix="stats:depthbands")
async def get_depth_bands(*, redis, from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    return await query("""
        SELECT depth_band, sum(event_count) AS event_count
        FROM earthquakes_depth_band_mv_data
        WHERE hour BETWEEN {t0:DateTime} AND {t1:DateTime}
          AND depth_band != ''
        GROUP BY depth_band
        ORDER BY event_count DESC
    """, {"t0": t0, "t1": t1})


@cached(ttl=30, key_prefix="stats:density")
async def get_density(*, redis, bbox: str, interval: Literal["1h", "6h", "24h"]) -> list[dict]:
    lon_min, lat_min, lon_max, lat_max = map(float, bbox.split(","))
    hours = {"1h": 1, "6h": 6, "24h": 24}[interval]
    return await query("""
        SELECT floor(latitude) AS lat, floor(longitude) AS lon, count() AS count
        FROM earthquakes_raw
        WHERE time >= now() - INTERVAL {hours:UInt32} HOUR
          AND longitude BETWEEN {lon_min:Float64} AND {lon_max:Float64}
          AND latitude BETWEEN {lat_min:Float64} AND {lat_max:Float64}
        GROUP BY lat, lon
        ORDER BY count DESC
        LIMIT 2000
    """, {"hours": hours, "lon_min": lon_min, "lon_max": lon_max, "lat_min": lat_min, "lat_max": lat_max})


async def get_network_rollups(*, redis, bucket: str, from_ts: datetime | None, to_ts: datetime | None, net: str, limit: int) -> list[dict]:
    if bucket not in VALID_BUCKETS:
        raise ValueError(f"bucket must be one of {sorted(VALID_BUCKETS)}")
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    network = net.strip()
    if bucket == "5m":
        return await query("""
            SELECT
                bucket,
                net,
                uniqMerge(event_count_state) AS event_count,
                avgMerge(avg_magnitude_state) AS avg_magnitude,
                avgMerge(avg_depth_state) AS avg_depth_km,
                countMerge(position_count_state) AS position_count
            FROM earthquakes_rollup_net_5m
            WHERE bucket >= {t0:DateTime}
              AND bucket < {t1:DateTime}
              AND ({net:String} = '' OR net = {net:String})
            GROUP BY bucket, net
            ORDER BY bucket ASC, event_count DESC
            LIMIT {limit:UInt32}
        """, {"t0": t0, "t1": t1, "net": network, "limit": limit})
    interval = {"1m": "1 MINUTE", "6h": "6 HOUR", "15m": "15 MINUTE", "1h": "1 HOUR", "1d": "1 DAY"}[bucket]
    return await query(f"""
        SELECT
            toStartOfInterval(time, INTERVAL {interval}, 'UTC') AS bucket,
            net,
            count() AS event_count,
            avg(toFloat64(magnitude)) AS avg_magnitude,
            avg(toFloat64(depth_km)) AS avg_depth_km,
            count() AS position_count
        FROM earthquakes_raw
        WHERE time >= {{t0:DateTime}}
          AND time < {{t1:DateTime}}
          AND ({{net:String}} = '' OR net = {{net:String}})
        GROUP BY bucket, net
        ORDER BY bucket ASC, event_count DESC
        LIMIT {{limit:UInt32}}
    """, {"t0": t0, "t1": t1, "net": network, "limit": limit})
