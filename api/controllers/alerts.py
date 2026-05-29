from __future__ import annotations

from datetime import datetime, timezone

from decorators import cached
from db import query


_OUTER_SELECT = """
    selected_anomaly_id AS anomaly_id,
    selected_detected_at AS detected_at,
    selected_event_time AS event_time,
    selected_anomaly_type AS anomaly_type,
    selected_severity AS severity,
    selected_source_event_id AS source_event_id,
    selected_source_place AS source_place,
    selected_latitude AS latitude,
    selected_longitude AS longitude,
    selected_detail AS detail
"""

def _dedup_select(prefix: str = "") -> str:
    """Build the per-(source_event_id, anomaly_type) dedup projection.

    `prefix` qualifies column refs with a table alias (e.g. "ae.") for the joined/range query.
    """
    p = prefix
    return f"""
        argMax({p}anomaly_id, {p}detected_at)   AS selected_anomaly_id,
        max({p}detected_at)                     AS selected_detected_at,
        argMax({p}event_time, {p}detected_at)   AS selected_event_time,
        {p}anomaly_type                         AS selected_anomaly_type,
        argMax({p}severity, {p}detected_at)     AS selected_severity,
        {p}source_event_id                      AS selected_source_event_id,
        argMax({p}source_place, {p}detected_at) AS selected_source_place,
        argMax({p}latitude, {p}detected_at)     AS selected_latitude,
        argMax({p}longitude, {p}detected_at)    AS selected_longitude,
        argMax({p}detail, {p}detected_at)       AS selected_detail,
        max({p}event_time)                      AS selected_sort_time
    """


@cached(ttl=10, key_prefix="anomalies:history")
async def get_anomaly_history(*, redis, limit: int, from_ts: datetime | None = None, to_ts: datetime | None = None) -> list[dict]:
    """Most-recent anomalies, deduped to the latest detection per (event, type); optionally time-filtered."""
    if from_ts or to_ts:
        t0 = from_ts or datetime(1970, 1, 1, tzinfo=timezone.utc)
        t1 = to_ts or datetime.now(timezone.utc)
        return await query(f"""
            SELECT {_OUTER_SELECT}
            FROM (
                SELECT {_dedup_select("ae.")}
                FROM anomaly_events AS ae
                WHERE ae.event_time BETWEEN {{t0:DateTime}} AND {{t1:DateTime}}
                GROUP BY ae.source_event_id, ae.anomaly_type
            )
            ORDER BY selected_sort_time DESC
            LIMIT {{limit:UInt32}}
        """, {"limit": limit, "t0": t0, "t1": t1})
    return await query(f"""
        SELECT {_OUTER_SELECT}
        FROM (
            SELECT {_dedup_select()}
            FROM anomaly_events
            GROUP BY source_event_id, anomaly_type
        )
        ORDER BY selected_sort_time DESC
        LIMIT {{limit:UInt32}}
    """, {"limit": limit})

