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
    column = "net" if field == "net" else "place"
    return await query(f"""
        SELECT {column} AS label, count() AS count
        FROM earthquakes_raw FINAL
        WHERE time BETWEEN {{t0:DateTime}} AND {{t1:DateTime}}
          AND {column} != ''
        GROUP BY {column}
        ORDER BY count DESC
        LIMIT {{limit:UInt32}}
    """, {"t0": t0, "t1": t1, "limit": limit})


@cached(ttl=30, key_prefix="stats:timeseries")
async def get_timeseries(*, redis, bucket: Literal["1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"], from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    if bucket == "1mo":
        bucket_expr = "toStartOfMonth(time, 'UTC')"
    elif bucket == "1y":
        bucket_expr = "toStartOfYear(time, 'UTC')"
    else:
        interval = {
            "1m": "1 MINUTE",
            "5m": "5 MINUTE",
            "15m": "15 MINUTE",
            "1h": "1 HOUR",
            "6h": "6 HOUR",
            "1d": "1 DAY",
        }[bucket]
        bucket_expr = f"toStartOfInterval(time, INTERVAL {interval}, 'UTC')"
    return await query(f"""
        SELECT
            bucket_time AS time,
            event_count,
            avg_magnitude
        FROM (
            SELECT
                {bucket_expr} AS bucket_time,
                count() AS event_count,
                avg(toFloat64(magnitude)) AS avg_magnitude
            FROM earthquakes_raw FINAL
            WHERE time BETWEEN {{t0:DateTime}} AND {{t1:DateTime}}
            GROUP BY bucket_time
        )
        ORDER BY time ASC
    """, {"t0": t0, "t1": t1})


@cached(ttl=60, key_prefix="stats:magbands")
async def get_magnitude_bands(*, redis, from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    return await query("""
        SELECT mag_band, count() AS event_count
        FROM earthquakes_raw FINAL
        WHERE time BETWEEN {t0:DateTime} AND {t1:DateTime}
          AND mag_band != ''
        GROUP BY mag_band
        ORDER BY event_count DESC
    """, {"t0": t0, "t1": t1})


@cached(ttl=60, key_prefix="stats:depthbands")
async def get_depth_bands(*, redis, from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    t0, t1 = from_ts or default_window()[0], to_ts or default_window()[1]
    return await query("""
        SELECT depth_band, count() AS event_count
        FROM earthquakes_raw FINAL
        WHERE time BETWEEN {t0:DateTime} AND {t1:DateTime}
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
        FROM earthquakes_raw FINAL
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
    if bucket == "1mo":
        bucket_expr = "toStartOfMonth(time, 'UTC')"
    elif bucket == "1y":
        bucket_expr = "toStartOfYear(time, 'UTC')"
    else:
        interval = {
            "1m": "1 MINUTE",
            "5m": "5 MINUTE",
            "15m": "15 MINUTE",
            "1h": "1 HOUR",
            "6h": "6 HOUR",
            "1d": "1 DAY",
        }[bucket]
        bucket_expr = f"toStartOfInterval(time, INTERVAL {interval}, 'UTC')"
    return await query(f"""
        SELECT
            {bucket_expr} AS bucket,
            net,
            count() AS event_count,
            avg(toFloat64(magnitude)) AS avg_magnitude,
            avg(toFloat64(depth_km)) AS avg_depth_km,
            count() AS position_count
        FROM earthquakes_raw FINAL
        WHERE time BETWEEN {{t0:DateTime}} AND {{t1:DateTime}}
          AND ({{net:String}} = '' OR net = {{net:String}})
        GROUP BY bucket, net
        ORDER BY bucket ASC, event_count DESC
        LIMIT {{limit:UInt32}}
    """, {"t0": t0, "t1": t1, "net": network, "limit": limit})
