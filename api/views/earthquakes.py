from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from cache import get_redis
from controllers.alerts import get_anomaly_history
from controllers.earthquakes import (
    get_b_value_history,
    get_energy_timeseries,
    get_heatmap,
    get_inter_event_times,
    get_live,
    get_magnitude_frequency,
)
from controllers.stats import (
    RANGE_PRESETS,
    VALID_BUCKETS,
    get_density,
    get_depth_bands,
    get_ingestion_status,
    get_magnitude_bands,
    get_network_rollups,
    get_timeseries,
    get_top_n,
    resolve_range,
)

earthquake_router = APIRouter(prefix="/api/earthquakes", tags=["earthquakes"])
anomaly_router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])
ingestion_router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])

Window = tuple[datetime | None, datetime | None, str]


def resolve_window(
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    range_preset: Annotated[str | None, Query(alias="range")] = None,
) -> Window:
    """Resolve the from/to/range query params into (from_ts, to_ts, bucket).

    A `range` preset overrides explicit from/to and also supplies a default bucket.
    """
    if range_preset is None:
        return from_ts, to_ts, ""
    if range_preset not in RANGE_PRESETS:
        raise HTTPException(status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}")
    return resolve_range(range_preset)


@earthquake_router.get("/live")
async def live(
    window: Annotated[Window, Depends(resolve_window)],
    min_magnitude: Annotated[float, Query(ge=0.0, le=10.0)] = 0.0,
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/live — recent events, optionally windowed and magnitude-filtered."""
    from_ts, to_ts, _ = window
    return await get_live(redis=redis, from_ts=from_ts, to_ts=to_ts, min_magnitude=min_magnitude)


@earthquake_router.get("/heatmap")
async def heatmap(
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
    resolution: Annotated[int, Query(ge=1, le=5)] = 3,
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/heatmap — H3-cell density for the (required) window."""
    return await get_heatmap(redis=redis, from_ts=from_ts, to_ts=to_ts, resolution=resolution)


@earthquake_router.get("/timeseries")
async def timeseries(
    window: Annotated[Window, Depends(resolve_window)],
    bucket: Literal["1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"] = "1h",
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/timeseries — counts/avg-magnitude per bucket (range preset overrides bucket)."""
    from_ts, to_ts, resolved_bucket = window
    return await get_timeseries(redis=redis, bucket=resolved_bucket or bucket, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/top-networks")
async def top_networks(
    window: Annotated[Window, Depends(resolve_window)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/top-networks — busiest reporting networks in the window."""
    from_ts, to_ts, _ = window
    return await get_top_n(redis=redis, field="net", limit=limit, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/top-places")
async def top_places(
    window: Annotated[Window, Depends(resolve_window)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/top-places — most active place labels in the window."""
    from_ts, to_ts, _ = window
    return await get_top_n(redis=redis, field="place", limit=limit, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/magnitude-bands")
async def magnitude_bands(
    window: Annotated[Window, Depends(resolve_window)],
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/magnitude-bands — event counts per magnitude band."""
    from_ts, to_ts, _ = window
    return await get_magnitude_bands(redis=redis, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/depth-bands")
async def depth_bands(
    window: Annotated[Window, Depends(resolve_window)],
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/depth-bands — event counts per depth band."""
    from_ts, to_ts, _ = window
    return await get_depth_bands(redis=redis, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/geospatial-density")
async def geospatial_density(
    bbox: str = Query(description="lon_min,lat_min,lon_max,lat_max"),
    interval: Literal["1h", "6h", "24h"] = "1h",
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/geospatial-density — recent event counts per grid cell inside a bbox."""
    return await get_density(redis=redis, bbox=bbox, interval=interval)


@earthquake_router.get("/rollups/network")
async def network_rollups(
    window: Annotated[Window, Depends(resolve_window)],
    bucket: str = "5m",
    net: str = "",
    limit: Annotated[int, Query(ge=1, le=10_000)] = 500,
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/rollups/network — per-bucket per-network rollups; validates the bucket."""
    from_ts, to_ts, resolved_bucket = window
    bucket = resolved_bucket or bucket
    if bucket not in VALID_BUCKETS:
        raise HTTPException(status_code=422, detail=f"bucket must be one of {sorted(VALID_BUCKETS)}")
    return await get_network_rollups(redis=redis, bucket=bucket, from_ts=from_ts, to_ts=to_ts, net=net, limit=limit)


@earthquake_router.get("/magnitude-frequency")
async def magnitude_frequency(
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/magnitude-frequency — frequency-magnitude distribution for the window."""
    return await get_magnitude_frequency(redis=redis, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/energy-timeseries")
async def energy_timeseries(
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
    bucket: str = "1d",
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/energy-timeseries — radiated energy per bucket; validates the bucket."""
    if bucket not in VALID_BUCKETS:
        raise HTTPException(status_code=422, detail=f"bucket must be one of {sorted(VALID_BUCKETS)}")
    return await get_energy_timeseries(redis=redis, from_ts=from_ts, to_ts=to_ts, bucket=bucket)


@earthquake_router.get("/b-value-history")
async def b_value_history(
    window: Annotated[Window, Depends(resolve_window)],
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/b-value-history — daily b-value series; defaults to last 30 days."""
    from_ts, to_ts, _ = window
    if not from_ts or not to_ts:
        from_ts, to_ts, _ = resolve_range("30d")
    return await get_b_value_history(redis=redis, from_ts=from_ts, to_ts=to_ts)


@earthquake_router.get("/inter-event-times")
async def inter_event_times(
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/earthquakes/inter-event-times — histogram of gaps between consecutive events."""
    return await get_inter_event_times(redis=redis, from_ts=from_ts, to_ts=to_ts)


@anomaly_router.get("/history")
async def anomaly_history(
    limit: Annotated[int, Query(ge=1, le=100000)] = 200,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    """GET /api/anomalies/history — recent deduped anomalies, optionally time-filtered."""
    return await get_anomaly_history(redis=redis, limit=limit, from_ts=from_ts, to_ts=to_ts)


@ingestion_router.get("/status")
async def ingestion_status() -> dict:
    """GET /api/ingestion/status — pipeline health/freshness snapshot."""
    return await get_ingestion_status()
