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

_DEDUP_SELECT = """
    argMax(anomaly_id, detected_at) AS selected_anomaly_id,
    max(detected_at) AS selected_detected_at,
    argMax(event_time, detected_at) AS selected_event_time,
    anomaly_type AS selected_anomaly_type,
    argMax(severity, detected_at) AS selected_severity,
    source_event_id AS selected_source_event_id,
    argMax(source_place, detected_at) AS selected_source_place,
    argMax(latitude, detected_at) AS selected_latitude,
    argMax(longitude, detected_at) AS selected_longitude,
    argMax(detail, detected_at) AS selected_detail,
    max(if(event_time > toDateTime(0), event_time, detected_at)) AS selected_sort_time
"""

_RANGE_DEDUP_SELECT = """
    argMax(ae.anomaly_id, ae.detected_at) AS selected_anomaly_id,
    max(ae.detected_at) AS selected_detected_at,
    argMax(if(ae.event_time > toDateTime(0), ae.event_time, er.source_event_time), ae.detected_at) AS selected_event_time,
    ae.anomaly_type AS selected_anomaly_type,
    argMax(ae.severity, ae.detected_at) AS selected_severity,
    ae.source_event_id AS selected_source_event_id,
    argMax(ae.source_place, ae.detected_at) AS selected_source_place,
    argMax(ae.latitude, ae.detected_at) AS selected_latitude,
    argMax(ae.longitude, ae.detected_at) AS selected_longitude,
    argMax(ae.detail, ae.detected_at) AS selected_detail,
    max(if(ae.event_time > toDateTime(0), ae.event_time, er.source_event_time)) AS selected_sort_time
"""

_RANGE_JOIN = """
    anomaly_events AS ae
    LEFT JOIN (
        SELECT event_id, argMax(time, ingested_at) AS source_event_time
        FROM earthquakes_raw
        GROUP BY event_id
    ) AS er ON ae.source_event_id = er.event_id
"""


@cached(ttl=10, key_prefix="anomalies:history")
async def get_anomaly_history(*, redis, limit: int, from_ts: datetime | None = None, to_ts: datetime | None = None) -> list[dict]:
    if from_ts or to_ts:
        t0 = from_ts or datetime(1970, 1, 1, tzinfo=timezone.utc)
        t1 = to_ts or datetime.now(timezone.utc)
        return await query(f"""
            SELECT {_OUTER_SELECT}
            FROM (
                SELECT {_RANGE_DEDUP_SELECT}
                FROM {_RANGE_JOIN}
                WHERE if(ae.event_time > toDateTime(0), ae.event_time, er.source_event_time) > toDateTime(0)
                  AND if(ae.event_time > toDateTime(0), ae.event_time, er.source_event_time) BETWEEN {{t0:DateTime}} AND {{t1:DateTime}}
                GROUP BY ae.source_event_id, ae.anomaly_type
            )
            ORDER BY selected_sort_time DESC
            LIMIT {{limit:UInt32}}
        """, {"limit": limit, "t0": t0, "t1": t1})
    return await query(f"""
        SELECT {_OUTER_SELECT}
        FROM (
            SELECT {_DEDUP_SELECT}
            FROM anomaly_events
            GROUP BY source_event_id, anomaly_type
        )
        ORDER BY selected_sort_time DESC
        LIMIT {{limit:UInt32}}
    """, {"limit": limit})

