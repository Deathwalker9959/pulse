from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class AnomalyType(StrEnum):
    SIGNIFICANT_EVENT = "SIGNIFICANT_EVENT"
    TSUNAMI_ALERT = "TSUNAMI_ALERT"
    TSUNAMI_RISK = "TSUNAMI_RISK"
    MAGNITUDE_SPIKE = "MAGNITUDE_SPIKE"
    SWARM_DETECTION = "SWARM_DETECTION"
    DATA_QUALITY_ANOMALY = "DATA_QUALITY_ANOMALY"
    ENERGY_BURST = "ENERGY_BURST"
    AFTERSHOCK_CASCADE = "AFTERSHOCK_CASCADE"
    GLOBAL_RATE_SPIKE = "GLOBAL_RATE_SPIKE"
    SEISMIC_QUIESCENCE = "SEISMIC_QUIESCENCE"
    B_VALUE_ANOMALY = "B_VALUE_ANOMALY"
    DEEP_FOCUS_CLUSTER = "DEEP_FOCUS_CLUSTER"
    FORESHOCK_SEQUENCE = "FORESHOCK_SEQUENCE"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def _anomaly_id(source_event_id: str, anomaly_type: str) -> str:
    return hashlib.sha256(f"{source_event_id}:{anomaly_type}".encode()).hexdigest()[:36]


class AnomalyEvent(BaseModel):
    anomaly_id: str = ""
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    anomaly_type: AnomalyType
    severity: Severity
    source_event_id: str
    source_place: str = ""
    latitude: float
    longitude: float
    detail: str

