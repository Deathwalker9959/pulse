from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EarthquakeEvent(BaseModel):
    event_id: str
    time: datetime
    updated: datetime
    latitude: float
    longitude: float
    depth_km: float
    magnitude: float
    mag_type: str
    place: str
    event_type: str
    status: str
    alert: str
    tsunami: bool
    significance: int
    net: str
    mag_band: str
    depth_band: str


class AnomalyEvent(BaseModel):
    anomaly_id: str
    detected_at: datetime
    anomaly_type: str
    severity: str
    source_event_id: str
    source_place: str
    latitude: float
    longitude: float
    detail: str

