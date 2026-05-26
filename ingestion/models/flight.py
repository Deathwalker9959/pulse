from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FlightState(BaseModel):
    """Normalised representation of a single OpenSky aircraft state vector."""

    icao24: str
    callsign: str = ""
    origin_country: str = ""
    time_position: Optional[datetime] = None
    last_contact: Optional[datetime] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    baro_altitude: Optional[float] = None
    on_ground: bool = False
    velocity: Optional[float] = None
    true_track: Optional[float] = None
    vertical_rate: Optional[float] = None
    squawk: str = ""

    @field_validator("callsign", "origin_country", "squawk", mode="before")
    @classmethod
    def strip_nullable_str(cls, v: object) -> str:
        return (v or "").strip()

    @field_validator("icao24", mode="before")
    @classmethod
    def lower_icao(cls, v: object) -> str:
        return str(v or "").lower().strip()

    def is_airborne(self) -> bool:
        return not self.on_ground and self.baro_altitude is not None and self.baro_altitude > 0

    def has_position(self) -> bool:
        return self.longitude is not None and self.latitude is not None

    @classmethod
    def from_opensky_state(cls, state: list) -> FlightState:
        """Parse raw OpenSky states/all array element (26-field list)."""
        def _ts(v: int | None) -> Optional[datetime]:
            return datetime.utcfromtimestamp(v) if v else None

        return cls(
            icao24=state[0] or "",
            callsign=state[1] or "",
            origin_country=state[2] or "",
            time_position=_ts(state[3]),
            last_contact=_ts(state[4]),
            longitude=state[5],
            latitude=state[6],
            baro_altitude=state[7],
            on_ground=bool(state[8]),
            velocity=state[9],
            true_track=state[10],
            vertical_rate=state[11],
            squawk=state[14] or "",
        )
