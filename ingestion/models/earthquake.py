from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, field_validator


class EarthquakeEvent(BaseModel):
    event_id: str
    time: datetime
    updated: datetime
    latitude: float
    longitude: float
    depth_km: float
    magnitude: float
    mag_type: str = ""
    place: str = ""
    event_type: str = "earthquake"
    status: str = ""
    alert: str = ""
    tsunami: bool = False
    significance: int = 0
    net: str = ""
    nst: int | None = None
    gap: float | None = None

    @field_validator("event_id", "mag_type", "place", "event_type", "status", "alert", "net", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> str:
        return str(value or "").strip()

    def has_position(self) -> bool:
        return -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180

    @classmethod
    def from_geojson_feature(cls, feature: dict) -> "EarthquakeEvent":
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []

        def ts(value: int | float | None) -> datetime:
            return datetime.fromtimestamp((value or 0) / 1000.0, tz=timezone.utc)

        return cls(
            event_id=feature.get("id") or props.get("ids") or "",
            time=ts(props.get("time")),
            updated=ts(props.get("updated") or props.get("time")),
            longitude=float(coords[0]) if len(coords) > 0 and coords[0] is not None else 0.0,
            latitude=float(coords[1]) if len(coords) > 1 and coords[1] is not None else 0.0,
            depth_km=float(coords[2]) if len(coords) > 2 and coords[2] is not None else 0.0,
            magnitude=float(props.get("mag") or 0.0),
            mag_type=props.get("magType") or "",
            place=props.get("place") or "",
            event_type=props.get("type") or "earthquake",
            status=props.get("status") or "",
            alert=props.get("alert") or "",
            tsunami=bool(props.get("tsunami")),
            significance=int(props.get("sig") or 0),
            net=props.get("net") or "",
            nst=int(props["nst"]) if props.get("nst") is not None else None,
            gap=float(props["gap"]) if props.get("gap") is not None else None,
        )

