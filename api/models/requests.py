from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class HistoryParams(BaseModel):
    icao24: str
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def check_range(self) -> "HistoryParams":
        if self.from_ts >= self.to_ts:
            raise ValueError("'from' must be before 'to'")
        return self


class TopNParams(BaseModel):
    field: Literal["origin_country", "callsign"] = "origin_country"
    limit: int = Field(default=10, ge=1, le=100)
    from_ts: Optional[datetime] = Field(default=None, alias="from")
    to_ts: Optional[datetime] = Field(default=None, alias="to")

    model_config = {"populate_by_name": True}


class HourlyParams(BaseModel):
    from_ts: Optional[datetime] = Field(default=None, alias="from")
    to_ts: Optional[datetime] = Field(default=None, alias="to")

    model_config = {"populate_by_name": True}


class DensityParams(BaseModel):
    """Geographic bounding-box density query.

    bbox format: lon_min,lat_min,lon_max,lat_max (comma-separated string).
    """
    bbox: str = Field(description="lon_min,lat_min,lon_max,lat_max")
    interval: Literal["1h", "6h", "24h"] = "1h"

    @model_validator(mode="after")
    def parse_bbox(self) -> "DensityParams":
        parts = self.bbox.split(",")
        if len(parts) != 4:
            raise ValueError("bbox must have 4 comma-separated floats")
        try:
            lon_min, lat_min, lon_max, lat_max = map(float, parts)
        except ValueError:
            raise ValueError("bbox values must be numeric")
        if not (-180 <= lon_min < lon_max <= 180):
            raise ValueError("invalid longitude range")
        if not (-90 <= lat_min < lat_max <= 90):
            raise ValueError("invalid latitude range")
        return self

    def bbox_floats(self) -> tuple[float, float, float, float]:
        lon_min, lat_min, lon_max, lat_max = map(float, self.bbox.split(","))
        return lon_min, lat_min, lon_max, lat_max
