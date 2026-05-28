from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from cache import get_redis
from controllers.alerts import get_anomaly_history
from controllers.earthquakes import get_heatmap, get_live, render_events_atlas, render_heatmap_atlas
from controllers.stats import (
    RANGE_PRESETS,
    VALID_BUCKETS,
    get_density,
    get_depth_bands,
    get_magnitude_bands,
    get_network_rollups,
    get_timeseries,
    get_top_n,
    resolve_range,
)
from db import query

earthquake_router = APIRouter(prefix="/api/earthquakes", tags=["earthquakes"])
anomaly_router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])
ingestion_router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@earthquake_router.get("/live")
async def live(
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    min_magnitude: Annotated[float, Query(alias="min_magnitude", ge=0.0, le=10.0)] = 0.0,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, _ = resolve_range(range_preset)
    return await get_live(redis=redis, from_ts=from_ts, to_ts=to_ts, min_magnitude=min_magnitude)


@earthquake_router.get("/atlas")
async def atlas(
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    mode: Annotated[str, Query()] = "events",
    resolution: Annotated[int, Query(ge=1, le=5)] = 3,
    redis=Depends(get_redis),
) -> StreamingResponse:
    if mode == "heatmap" and from_ts and to_ts:
        cells = await get_heatmap(redis=redis, from_ts=from_ts, to_ts=to_ts, resolution=resolution)
        png = await _run_in_thread(render_heatmap_atlas, cells)
    else:
        events = await get_live(redis=redis, from_ts=from_ts, to_ts=to_ts)
        png = await _run_in_thread(render_events_atlas, events)
    return StreamingResponse(
        io.BytesIO(png),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=120"},
    )


async def _run_in_thread(fn, *args):
    import asyncio, functools
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args))


@earthquake_router.get("/heatmap")
async def heatmap(
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
    resolution: Annotated[int, Query(ge=1, le=5)] = 3,
    redis=Depends(get_redis),
) -> list[dict]:
    return await get_heatmap(redis=redis, from_ts=from_ts, to_ts=to_ts, resolution=resolution)


@earthquake_router.get("/timeseries")
async def timeseries(
    bucket: Literal["1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"] = "1h",
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, bucket = resolve_range(range_preset)
    return await get_timeseries(redis=redis, bucket=bucket, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/top-networks")
async def top_networks(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, _ = resolve_range(range_preset)
    return await get_top_n(redis=redis, field="net", limit=limit, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/top-places")
async def top_places(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, _ = resolve_range(range_preset)
    return await get_top_n(redis=redis, field="place", limit=limit, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/magnitude-bands")
async def magnitude_bands(
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, _ = resolve_range(range_preset)
    return await get_magnitude_bands(redis=redis, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/depth-bands")
async def depth_bands(
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, _ = resolve_range(range_preset)
    return await get_depth_bands(redis=redis, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/geospatial-density")
async def geospatial_density(
    bbox: str = Query(description="lon_min,lat_min,lon_max,lat_max"),
    interval: Literal["1h", "6h", "24h"] = "1h",
    redis=Depends(get_redis),
) -> list[dict]:
    return await get_density(redis=redis, bbox=bbox, interval=interval)


@earthquake_router.get("/rollups/network")
async def network_rollups(
    bucket: str = "5m",
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
    net: str = "",
    limit: Annotated[int, Query(ge=1, le=10_000)] = 500,
    redis=Depends(get_redis),
) -> list[dict]:
    if range_preset is not None:
        if range_preset not in RANGE_PRESETS:
            raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
        from_ts, to_ts, bucket = resolve_range(range_preset)
    if bucket not in VALID_BUCKETS:
        raise HTTPException(status_code=422, detail=f"bucket must be one of {sorted(VALID_BUCKETS)}")
    return await get_network_rollups(redis=redis, bucket=bucket, from_ts=from_ts, to_ts=to_ts, net=net, limit=limit)


@anomaly_router.get("/history")
async def anomaly_history(
    limit: Annotated[int, Query(ge=1, le=100000)] = 200,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    return await get_anomaly_history(redis=redis, limit=limit, from_ts=from_ts, to_ts=to_ts)


@ingestion_router.get("/status")
async def ingestion_status() -> dict:
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

