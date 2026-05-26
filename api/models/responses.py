from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FlightLive(BaseModel):
    icao24: str
    callsign: str
    origin_country: str
    latitude: float
    longitude: float
    baro_altitude: float
    on_ground: bool
    velocity: float
    true_track: float
    vertical_rate: float
    squawk: str
    last_contact: datetime


class FlightPoint(BaseModel):
    time_position: datetime
    latitude: float
    longitude: float
    baro_altitude: float
    velocity: float
    on_ground: bool


class HourlyBucket(BaseModel):
    hour: datetime
    origin_country: str
    flight_count: int
    avg_altitude: float
    avg_velocity: float
    airborne_count: int


class TopNItem(BaseModel):
    label: str
    count: int


class DensityCell(BaseModel):
    lat: float
    lon: float
    count: int


class AnomalyResponse(BaseModel):
    event_id: str
    detected_at: datetime
    anomaly_type: str
    severity: str
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    detail: str
    weather_temp_c: Optional[float] = None
    weather_wind_kts: Optional[float] = None
    weather_condition: Optional[str] = None
    weather_visibility: Optional[float] = None
    weather_fetched_at: Optional[datetime] = None
