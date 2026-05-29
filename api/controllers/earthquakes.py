from __future__ import annotations

import bisect
from datetime import datetime, timedelta, timezone

from controllers.stats import _bucket_expr
from decorators import cached
from db import query


@cached(ttl=10, key_prefix="earthquakes:live")
async def get_live(*, redis, from_ts: datetime | None = None, to_ts: datetime | None = None, min_magnitude: float = 0.0) -> list[dict]:
    mag_clause = "AND magnitude >= {min_mag:Float32}" if min_magnitude > 0 else ""
    if from_ts or to_ts:
        t0 = from_ts or (datetime.now(timezone.utc) - timedelta(hours=2))
        t1 = to_ts or datetime.now(timezone.utc)
        return await query(f"""
            SELECT
                event_id, time, updated, latitude, longitude, depth_km, magnitude,
                mag_type, place, event_type, status, alert, tsunami, significance,
                net, mag_band, depth_band
            FROM earthquakes_raw FINAL
            WHERE time >= {{t0:DateTime}} AND time <= {{t1:DateTime}} {mag_clause}
            ORDER BY magnitude DESC, time DESC
            LIMIT 5000
        """, {"t0": t0, "t1": t1, "min_mag": min_magnitude})
    return await query(f"""
        SELECT
            event_id, time, updated, latitude, longitude, depth_km, magnitude,
            mag_type, place, event_type, status, alert, tsunami, significance,
            net, mag_band, depth_band
        FROM earthquakes_raw FINAL
        WHERE time >= now() - INTERVAL 2 HOUR {mag_clause}
        ORDER BY time DESC
        LIMIT 5000
    """, {"min_mag": min_magnitude} if min_magnitude > 0 else {})


_IET_BINS: list[tuple[str, float, float]] = [
    ("0–60s",   0,      60),
    ("1–5 min", 60,     300),
    ("5–30 min",300,    1_800),
    ("30m–2h",  1_800,  7_200),
    ("2–12h",   7_200,  43_200),
    ("12h+",    43_200, float("inf")),
]
_IET_BOUNDARIES = [lo for _, lo, _ in _IET_BINS[1:]]  # lower bounds for bisect, skipping bin 0


@cached(ttl=120, key_prefix="earthquakes:magfreq")
async def get_magnitude_frequency(*, redis, from_ts: datetime, to_ts: datetime) -> list[dict]:
    return await query("""
        SELECT
            round(toFloat64(magnitude), 1) AS mag_bin,
            count() AS event_count
        FROM earthquakes_raw FINAL
        WHERE time >= {t0:DateTime} AND time <= {t1:DateTime}
          AND magnitude >= 0
        GROUP BY mag_bin
        ORDER BY mag_bin ASC
    """, {"t0": from_ts, "t1": to_ts})


@cached(ttl=60, key_prefix="earthquakes:energy")
async def get_energy_timeseries(*, redis, from_ts: datetime, to_ts: datetime, bucket: str = "1d") -> list[dict]:
    expr = _bucket_expr(bucket)
    return await query(f"""
        SELECT
            {expr} AS bucket,
            sum(pow(10, toFloat64(magnitude) * 1.5 + 4.8)) AS energy_joules
        FROM earthquakes_raw FINAL
        WHERE time >= {{t0:DateTime}} AND time <= {{t1:DateTime}}
        GROUP BY bucket
        ORDER BY bucket ASC
    """, {"t0": from_ts, "t1": to_ts})


@cached(ttl=120, key_prefix="earthquakes:bvalue")
async def get_b_value_history(*, redis, from_ts: datetime, to_ts: datetime) -> list[dict]:
    return await query("""
        SELECT
            toStartOfDay(time) AS day,
            1.0 / (log(10) * (avg(toFloat64(magnitude)) - 2.5)) AS b_value,
            count() AS sample_size
        FROM earthquakes_raw FINAL
        WHERE time >= {t0:DateTime} AND time <= {t1:DateTime}
          AND magnitude >= 2.5
        GROUP BY day
        HAVING sample_size >= 10
        ORDER BY day ASC
    """, {"t0": from_ts, "t1": to_ts})


@cached(ttl=120, key_prefix="earthquakes:iet")
async def get_inter_event_times(*, redis, from_ts: datetime, to_ts: datetime) -> list[dict]:
    rows = await query("""
        SELECT time FROM earthquakes_raw FINAL
        WHERE time >= {t0:DateTime} AND time <= {t1:DateTime}
        ORDER BY time ASC
        LIMIT 50000
    """, {"t0": from_ts, "t1": to_ts})
    if len(rows) < 2:
        return [{"bin_label": label, "count": 0} for label, *_ in _IET_BINS]
    times = [r["time"] for r in rows]
    counts = [0] * len(_IET_BINS)
    for i in range(1, len(times)):
        dt = (times[i] - times[i - 1]).total_seconds()
        counts[bisect.bisect_right(_IET_BOUNDARIES, dt)] += 1
    return [{"bin_label": label, "count": counts[i]} for i, (label, *_) in enumerate(_IET_BINS)]


@cached(ttl=60, key_prefix="earthquakes:heatmap")
async def get_heatmap(*, redis, from_ts: datetime, to_ts: datetime, resolution: int = 3) -> list[dict]:
    return await query("""
        SELECT
            lower(hex(geoToH3(longitude, latitude, {resolution:UInt8}))) AS h3_index,
            count() AS event_count,
            max(magnitude) AS max_magnitude,
            avg(magnitude) AS avg_magnitude,
            avg(latitude) AS centroid_lat,
            avg(longitude) AS centroid_lon
        FROM earthquakes_raw FINAL
        WHERE time >= {t0:DateTime} AND time <= {t1:DateTime}
        GROUP BY h3_index
        ORDER BY event_count DESC
        LIMIT 10000
    """, {"t0": from_ts, "t1": to_ts, "resolution": resolution})
