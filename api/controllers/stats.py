from __future__ import annotations

import os
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
    """Default query window: the last 24 hours up to now (UTC)."""
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=24), now


def _window(from_ts: datetime | None, to_ts: datetime | None) -> tuple[datetime, datetime]:
    """Fill in either missing bound from the default 24h window."""
    start, end = default_window()
    return from_ts or start, to_ts or end


def _aligned_split(t0: datetime, t1: datetime, seconds: int) -> tuple[datetime, datetime] | None:
    """Boundaries [lo, hi) of the whole `seconds`-aligned buckets fully contained in [t0, t1].

    Returns None when the window holds no complete bucket. Lets a query serve its bulk
    from a pre-aggregated rollup while the partial edge buckets come from earthquakes_raw —
    exact for any window, since [t0, lo), [lo, hi) and [hi, t1] are disjoint and cover
    [t0, t1]. `seconds` is the rollup grain (3600 for the hourly rollups, 300 for the 5m one).
    """
    e0, e1 = int(t0.timestamp()), int(t1.timestamp())
    lo_e = e0 if e0 % seconds == 0 else (e0 // seconds + 1) * seconds
    hi_e = (e1 // seconds) * seconds
    if lo_e >= hi_e:
        return None
    return (
        datetime.fromtimestamp(lo_e, tz=timezone.utc),
        datetime.fromtimestamp(hi_e, tz=timezone.utc),
    )


def resolve_range(name: str) -> tuple[datetime, datetime, str]:
    """Expand a named range preset (e.g. "7d", "ytd") into (from, to, default-bucket)."""
    span, bucket = RANGE_PRESETS[name]
    now = datetime.now(timezone.utc)
    t0 = datetime(now.year, 1, 1, tzinfo=timezone.utc) if span is None else now - span
    return t0, now, bucket


_BUCKET_INTERVAL = {
    "1m": "1 MINUTE", "5m": "5 MINUTE", "15m": "15 MINUTE",
    "1h": "1 HOUR",   "6h": "6 HOUR",   "1d":  "1 DAY",
}


def _bucket_expr(bucket: str, column: str = "time") -> str:
    """Map a bucket label to the ClickHouse time-truncation expression used for GROUP BY.

    `column` is the timestamp column to truncate ("time" on earthquakes_raw, or the
    rollup's bucket column like "hour"/"bucket" when re-aggregating a rollup).
    """
    if bucket == "1mo":
        return f"toStartOfMonth({column}, 'UTC')"
    if bucket == "1y":
        return f"toStartOfYear({column}, 'UTC')"
    interval = _BUCKET_INTERVAL[bucket]
    return f"toStartOfInterval({column}, INTERVAL {interval}, 'UTC')"


@cached(ttl=30, key_prefix="stats:topn")
async def get_top_n(*, redis, field: Literal["net", "place"], limit: int, from_ts: datetime | None, to_ts: datetime | None) -> list[dict]:
    """Top-N networks or places by distinct-event count within the window, descending.

    `net` is served by the hourly rollup (whole hours) + raw edges; `place` has no
    rollup and reads earthquakes_raw directly.
    """
    t0, t1 = _window(from_ts, to_ts)
    column = "net" if field == "net" else "place"
    split = _aligned_split(t0, t1, 3600) if field == "net" else None
    if split is not None:
        lo, hi = split
        return await query("""
            SELECT label, sum(c) AS count FROM (
                SELECT net AS label, uniqExactMerge(event_count_state) AS c
                FROM earthquakes_hourly_mv_data
                WHERE hour >= {lo:DateTime} AND hour < {hi:DateTime} AND net != ''
                GROUP BY net
                UNION ALL
                SELECT net AS label, count() AS c
                FROM earthquakes_raw FINAL
                WHERE ((time >= {t0:DateTime} AND time < {lo:DateTime})
                    OR (time >= {hi:DateTime} AND time <= {t1:DateTime}))
                  AND net != ''
                GROUP BY net
            )
            GROUP BY label
            ORDER BY count DESC
            LIMIT {limit:UInt32}
        """, {"t0": t0, "t1": t1, "lo": lo, "hi": hi, "limit": limit})
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
    """Event count and average magnitude per time bucket across the window.

    Hour-or-coarser buckets re-aggregate the hourly rollup for the whole hours and read
    earthquakes_raw only for the partial edge hours (event_count exact; avg approximate
    under revision). Sub-hour buckets need finer granularity than the rollup, so they read
    earthquakes_raw directly.
    """
    t0, t1 = _window(from_ts, to_ts)
    split = _aligned_split(t0, t1, 3600) if bucket in {"1h", "6h", "1d", "1mo", "1y"} else None
    if split is not None:
        lo, hi = split
        return await query(f"""
            SELECT bucket_time AS time, sum(cnt) AS event_count, sum(mag_sum) / sum(rows) AS avg_magnitude
            FROM (
                SELECT
                    {_bucket_expr(bucket, "hour")} AS bucket_time,
                    uniqExactMerge(event_count_state) AS cnt,
                    sumMerge(magnitude_sum_state) AS mag_sum,
                    countMerge(row_count_state) AS rows
                FROM earthquakes_hourly_mv_data
                WHERE hour >= {{lo:DateTime}} AND hour < {{hi:DateTime}}
                GROUP BY bucket_time
                UNION ALL
                SELECT
                    {_bucket_expr(bucket, "time")} AS bucket_time,
                    count() AS cnt,
                    sum(toFloat64(magnitude)) AS mag_sum,
                    count() AS rows
                FROM earthquakes_raw FINAL
                WHERE (time >= {{t0:DateTime}} AND time < {{lo:DateTime}})
                   OR (time >= {{hi:DateTime}} AND time <= {{t1:DateTime}})
                GROUP BY bucket_time
            )
            GROUP BY time
            ORDER BY time ASC
        """, {"t0": t0, "t1": t1, "lo": lo, "hi": hi})
    bucket_expr = _bucket_expr(bucket)
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
    """Distinct-event counts grouped by magnitude band over the window (rollup body + raw edges)."""
    t0, t1 = _window(from_ts, to_ts)
    split = _aligned_split(t0, t1, 3600)
    if split is not None:
        lo, hi = split
        return await query("""
            SELECT mag_band, sum(c) AS event_count FROM (
                SELECT mag_band, uniqExactMerge(event_count_state) AS c
                FROM earthquakes_mag_band_mv_data
                WHERE hour >= {lo:DateTime} AND hour < {hi:DateTime} AND mag_band != ''
                GROUP BY mag_band
                UNION ALL
                SELECT mag_band, count() AS c
                FROM earthquakes_raw FINAL
                WHERE ((time >= {t0:DateTime} AND time < {lo:DateTime})
                    OR (time >= {hi:DateTime} AND time <= {t1:DateTime}))
                  AND mag_band != ''
                GROUP BY mag_band
            )
            GROUP BY mag_band
            ORDER BY event_count DESC
        """, {"t0": t0, "t1": t1, "lo": lo, "hi": hi})
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
    """Distinct-event counts grouped by depth band over the window (rollup body + raw edges)."""
    t0, t1 = _window(from_ts, to_ts)
    split = _aligned_split(t0, t1, 3600)
    if split is not None:
        lo, hi = split
        return await query("""
            SELECT depth_band, sum(c) AS event_count FROM (
                SELECT depth_band, uniqExactMerge(event_count_state) AS c
                FROM earthquakes_depth_band_mv_data
                WHERE hour >= {lo:DateTime} AND hour < {hi:DateTime} AND depth_band != ''
                GROUP BY depth_band
                UNION ALL
                SELECT depth_band, count() AS c
                FROM earthquakes_raw FINAL
                WHERE ((time >= {t0:DateTime} AND time < {lo:DateTime})
                    OR (time >= {hi:DateTime} AND time <= {t1:DateTime}))
                  AND depth_band != ''
                GROUP BY depth_band
            )
            GROUP BY depth_band
            ORDER BY event_count DESC
        """, {"t0": t0, "t1": t1, "lo": lo, "hi": hi})
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
    """Event counts per 1°×1° cell inside the bbox over the recent interval (for map density)."""
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
    """Per-bucket, per-network distinct count and average magnitude/depth; optional single-network filter.

    Buckets of 5 minutes or coarser re-aggregate the 5-minute rollup for whole buckets and read
    earthquakes_raw only for the partial edge buckets (event_count exact; avgs approximate under
    revision). The 1-minute bucket is finer than the rollup, so it reads earthquakes_raw directly.
    """
    if bucket not in VALID_BUCKETS:
        raise ValueError(f"bucket must be one of {sorted(VALID_BUCKETS)}")
    t0, t1 = _window(from_ts, to_ts)
    network = net.strip()
    split = _aligned_split(t0, t1, 300) if bucket != "1m" else None
    if split is not None:
        lo, hi = split
        return await query(f"""
            SELECT
                bucket_start AS bucket,
                net,
                sum(cnt) AS event_count,
                sum(mag_sum) / sum(positions) AS avg_magnitude,
                sum(depth_sum) / sum(positions) AS avg_depth_km,
                sum(positions) AS position_count
            FROM (
                SELECT
                    {_bucket_expr(bucket, "bucket")} AS bucket_start,
                    net,
                    uniqExactMerge(event_count_state) AS cnt,
                    sumMerge(magnitude_sum_state) AS mag_sum,
                    sumMerge(depth_sum_state) AS depth_sum,
                    countMerge(position_count_state) AS positions
                FROM earthquakes_rollup_net_5m
                WHERE bucket >= {{lo:DateTime}} AND bucket < {{hi:DateTime}}
                  AND ({{net:String}} = '' OR net = {{net:String}})
                GROUP BY bucket_start, net
                UNION ALL
                SELECT
                    {_bucket_expr(bucket, "time")} AS bucket_start,
                    net,
                    count() AS cnt,
                    sum(toFloat64(magnitude)) AS mag_sum,
                    sum(toFloat64(depth_km)) AS depth_sum,
                    count() AS positions
                FROM earthquakes_raw FINAL
                WHERE ((time >= {{t0:DateTime}} AND time < {{lo:DateTime}})
                    OR (time >= {{hi:DateTime}} AND time <= {{t1:DateTime}}))
                  AND ({{net:String}} = '' OR net = {{net:String}})
                GROUP BY bucket_start, net
            )
            GROUP BY bucket_start, net
            ORDER BY bucket ASC, event_count DESC
            LIMIT {{limit:UInt32}}
        """, {"t0": t0, "t1": t1, "lo": lo, "hi": hi, "net": network, "limit": limit})
    bucket_expr = _bucket_expr(bucket)
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


async def get_ingestion_status() -> dict:
    """Pipeline health snapshot: data freshness, recent event/anomaly counts, and poll interval."""
    rows = await query("""
        SELECT
            max(ingested_at) AS last_ingested_at,
            countIf(time >= now() - INTERVAL 30 MINUTE) AS events_30min,
            countIf(ingested_at >= now() - INTERVAL 2 MINUTE) AS events_2min
        FROM earthquakes_raw FINAL
    """)
    anomaly_rows = await query("""
        SELECT count() AS anomaly_24h
        FROM (
            SELECT source_event_id, anomaly_type
            FROM anomaly_events
            WHERE event_time >= now() - INTERVAL 24 HOUR
            GROUP BY source_event_id, anomaly_type
        )
    """)
    type_rows = await query("""
        SELECT DISTINCT anomaly_type
        FROM anomaly_events
        WHERE event_time >= now() - INTERVAL 1 HOUR
    """)
    row = rows[0] if rows else {}
    last_at = row.get("last_ingested_at")
    age_seconds = None
    if last_at:
        aware = last_at if last_at.tzinfo else last_at.replace(tzinfo=timezone.utc)
        age_seconds = int((datetime.now(timezone.utc) - aware).total_seconds())
    events_2min = row.get("events_2min", 0)
    return {
        "has_live_data": events_2min > 0,
        "last_ingested_at": last_at.isoformat() if last_at else None,
        "data_age_seconds": age_seconds,
        "events_30min": row.get("events_30min", 0),
        "events_2min": events_2min,
        "anomaly_24h": anomaly_rows[0]["anomaly_24h"] if anomaly_rows else 0,
        "active_anomaly_types": [item["anomaly_type"] for item in type_rows],
        "poll_interval_seconds": int(os.getenv("USGS_POLL_INTERVAL", "60")),
    }
