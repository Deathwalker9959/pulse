from __future__ import annotations

from datetime import datetime, timezone

import pytest

from controllers.anomaly import detect_anomalies, historical_pattern_anomalies
from models import AnomalyType, EarthquakeEvent, Severity


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[float | int]] = {}

    async def lrange(self, key: str, start: int, end: int):
        return self.lists.get(key, [1.0, 1.1, 1.0, 1.2])

    async def lpush(self, key: str, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key: str, start: int, end: int):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    async def expire(self, key: str, seconds: int):
        return True

    async def set(self, key: str, value: str, ex: int | None = None):
        return True

    async def get(self, key: str):
        return None

    async def incr(self, key: str):
        return 1

    async def zadd(self, key: str, mapping: dict):
        return True

    async def zremrangebyscore(self, key: str, min_score, max_score):
        return True

    async def zrangebyscore(self, key: str, min_score, max_score):
        return []


def quake(**overrides) -> EarthquakeEvent:
    values = {
        "event_id": "us-alert",
        "time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "latitude": 35.0,
        "longitude": 33.0,
        "depth_km": 10.0,
        "magnitude": 6.8,
        "place": "Test region",
        "alert": "red",
        "significance": 700,
        "net": "us",
    }
    values.update(overrides)
    return EarthquakeEvent(**values)


@pytest.mark.asyncio
async def test_significant_event_detection_uses_earthquake_fields() -> None:
    anomalies = await detect_anomalies([quake()], FakeRedis())

    assert any(item.anomaly_type == AnomalyType.SIGNIFICANT_EVENT for item in anomalies)
    alert = anomalies[0]
    assert alert.severity == Severity.CRITICAL
    assert alert.source_event_id == "us-alert"
    assert "Major impact event" in alert.detail



def test_historical_pattern_anomalies_detect_catalog_backfill_patterns() -> None:
    events = [
        quake(event_id="deep-1", time=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), updated=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc), magnitude=4.1, depth_km=520, latitude=-20.0, longitude=-178.0, alert="", significance=300),
        quake(event_id="deep-2", time=datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc), updated=datetime(2026, 1, 1, 3, 1, tzinfo=timezone.utc), magnitude=4.2, depth_km=540, latitude=-20.1, longitude=-178.1, alert="", significance=310),
        quake(event_id="deep-3", time=datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc), updated=datetime(2026, 1, 1, 6, 1, tzinfo=timezone.utc), magnitude=4.3, depth_km=560, latitude=-20.2, longitude=-178.2, alert="", significance=320),
        quake(event_id="mainshock", time=datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc), updated=datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc), magnitude=6.2, depth_km=20, latitude=35.0, longitude=33.0, alert="", significance=600),
        quake(event_id="aftershock", time=datetime(2026, 1, 2, 1, 0, tzinfo=timezone.utc), updated=datetime(2026, 1, 2, 1, 1, tzinfo=timezone.utc), magnitude=3.2, depth_km=18, latitude=35.1, longitude=33.1, alert="", significance=150),
    ]

    anomalies = historical_pattern_anomalies(events)
    types = {item.anomaly_type for item in anomalies}

    assert AnomalyType.DEEP_FOCUS_CLUSTER in types
    assert AnomalyType.AFTERSHOCK_CASCADE in types
