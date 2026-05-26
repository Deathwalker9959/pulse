"""Flight REST views — thin handlers that delegate entirely to controllers."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from cache import get_redis
from controllers.flights import get_history, get_live

router = APIRouter(prefix="/api/flights", tags=["flights"])


@router.get("/live")
async def live(redis=Depends(get_redis)) -> list[dict]:
    """Current state snapshot — latest position per aircraft, last 2 minutes."""
    return await get_live(redis=redis)


@router.get("/history")
async def history(
    icao24: str,
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
    redis=Depends(get_redis),
) -> list[dict]:
    """Time-ordered position track for one aircraft."""
    if from_ts >= to_ts:
        raise HTTPException(422, detail="'from' must be before 'to'")
    return await get_history(redis=redis, icao24=icao24.lower(), from_ts=from_ts, to_ts=to_ts)
