"""Statistics and aggregation views."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query

from cache import get_redis
from controllers.stats import get_density, get_hourly, get_top_n

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/top-n")
async def top_n(
    field: Literal["origin_country", "callsign"] = "origin_country",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    from_ts: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_ts: Annotated[Optional[datetime], Query(alias="to")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    return await get_top_n(redis=redis, field=field, limit=limit, from_ts=from_ts, to_ts=to_ts)


@router.get("/hourly")
async def hourly(
    from_ts: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_ts: Annotated[Optional[datetime], Query(alias="to")] = None,
    redis=Depends(get_redis),
) -> list[dict]:
    return await get_hourly(redis=redis, from_ts=from_ts, to_ts=to_ts)


@router.get("/density")
async def density(
    bbox: str = Query(description="lon_min,lat_min,lon_max,lat_max"),
    interval: Literal["1h", "6h", "24h"] = "1h",
    redis=Depends(get_redis),
) -> list[dict]:
    return await get_density(redis=redis, bbox=bbox, interval=interval)
