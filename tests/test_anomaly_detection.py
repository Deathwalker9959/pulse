from __future__ import annotations

from datetime import datetime, timezone

import pytest

from controllers.anomaly import detect_anomalies, historical_pattern_anomalies
from models import AnomalyType, EarthquakeEvent, Severity


class _FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._queue: list = []

    def zadd(self, key, mapping):
        self._queue.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self._queue.append(("expire", key, seconds))
        return self

    def zremrangebyscore(self, key, min_score, max_score):
        self._queue.append(("zremrangebyscore", key, min_score, max_score))
        return self

    def zrangebyscore(self, key, min_score, max_score):
        self._queue.append(("zrangebyscore", key, min_score, max_score))
        return self

    def set(self, key, value, ex=None):
        self._queue.append(("set", key, value, ex))
        return self

    def get(self, key):
        self._queue.append(("get", key))
        return self

    def incr(self, key):
        self._queue.append(("incr", key))
        return self

    async def execute(self):
        results = []
        for cmd, *args in self._queue:
            fn = getattr(self._redis, cmd)
            results.append(await fn(*args))
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[float | int]] = {}
        self.strings: dict[str, str] = {}
        self.counters: dict[str, int] = {}

    async def lrange(self, key: str, start: int, end: int):
        return self.lists.get(key, [1.0, 1.1, 1.0, 1.2])

    async def lpush(self, key: str, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key: str, start: int, end: int):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    async def expire(self, key: str, seconds: int):
        return True

    async def set(self, key: str, value: str, ex: int | None = None):
        self.strings[key] = value
        return True

    async def get(self, key: str):
        return self.strings.get(key)

    async def incr(self, key: str):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def zadd(self, key: str, mapping: dict):
        return True

    async def zremrangebyscore(self, key: str, min_score, max_score):
        return True

    async def zrangebyscore(self, key: str, min_score, max_score):
        return []

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)


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


@pytest.mark.asyncio
async def test_aftershock_cascade_uses_pipelined_mainshock_state() -> None:
    events = [
        quake(event_id="mainshock", magnitude=6.0, latitude=35.0, longitude=33.0, alert="", significance=100),
        quake(event_id="aftershock", magnitude=3.2, latitude=35.1, longitude=33.1, alert="", significance=100),
    ]

    anomalies = await detect_anomalies(events, FakeRedis())

    assert any(
        item.anomaly_type == AnomalyType.AFTERSHOCK_CASCADE
        and item.source_event_id == "aftershock"
        for item in anomalies
    )


@pytest.mark.asyncio
async def test_deep_focus_cluster_uses_pipelined_counts() -> None:
    events = [
        quake(event_id="deep-1", magnitude=4.1, depth_km=520, latitude=-20.0, longitude=-178.0, alert="", significance=300),
        quake(event_id="deep-2", magnitude=4.2, depth_km=540, latitude=-20.1, longitude=-178.1, alert="", significance=310),
        quake(event_id="deep-3", magnitude=4.3, depth_km=560, latitude=-20.2, longitude=-178.2, alert="", significance=320),
    ]

    anomalies = await detect_anomalies(events, FakeRedis())

    assert any(
        item.anomaly_type == AnomalyType.DEEP_FOCUS_CLUSTER
        and item.source_event_id == "deep-3"
        for item in anomalies
    )



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
