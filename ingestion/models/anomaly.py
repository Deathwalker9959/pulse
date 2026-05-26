from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AnomalyType(StrEnum):
    EMERGENCY_SQUAWK = "EMERGENCY_SQUAWK"
    ALTITUDE_DROP = "ALTITUDE_DROP"
    SPEED_OUTLIER = "SPEED_OUTLIER"
    DENSITY_SPIKE = "DENSITY_SPIKE"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AnomalyEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    anomaly_type: AnomalyType
    severity: Severity
    icao24: str
    callsign: str = ""
    latitude: float
    longitude: float
    detail: str
    # Populated async after initial detection
    weather_temp_c: Optional[float] = None
    weather_wind_kts: Optional[float] = None
    weather_condition: Optional[str] = None
    weather_visibility: Optional[float] = None
    weather_fetched_at: Optional[datetime] = None

    def is_weather_enriched(self) -> bool:
        return self.weather_fetched_at is not None
