from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Stub out db and models so ingestion.controllers.ingestion imports cleanly.
for mod_name in ("db", "models", "poller", "writer", "controllers.anomaly"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# db stub needs get_clickhouse_client
async def _stub_get_ch(*a, **kw):
    pass

sys.modules["db"].get_clickhouse_client = _stub_get_ch  # type: ignore[attr-defined]

# poller stub needs POLL_INTERVAL and fetch_events
sys.modules["poller"].POLL_INTERVAL = 60  # type: ignore[attr-defined]

async def _stub_fetch(*a, **kw):
    return []

sys.modules["poller"].fetch_events = _stub_fetch  # type: ignore[attr-defined]

# writer stubs
async def _noop(*a, **kw):
    pass

sys.modules["writer"].write_earthquakes = _noop  # type: ignore[attr-defined]
sys.modules["writer"].write_anomalies = _noop  # type: ignore[attr-defined]

# anomaly stub
async def _stub_detect(*a, **kw):
    return []

sys.modules["controllers.anomaly"].detect_anomalies = _stub_detect  # type: ignore[attr-defined]

# models stub — needs AnomalyEvent and EarthquakeEvent names
sys.modules["models"].AnomalyEvent = object  # type: ignore[attr-defined]
sys.modules["models"].EarthquakeEvent = object  # type: ignore[attr-defined]

import importlib.util

spec = importlib.util.spec_from_file_location(
    "ingestion_ctrl",
    ROOT / "ingestion" / "controllers" / "ingestion.py",
)
assert spec and spec.loader
ingestion_ctrl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingestion_ctrl)


class _FakeRedis:
    """Minimal Redis fake that tracks SCAN and DEL calls."""

    def __init__(self, keys: list[str]) -> None:
        self._keys: set[str] = set(keys)
        self.deleted: list[str] = []

    async def scan(self, cursor: int, match: str = "*", count: int = 100):
        prefix = match.rstrip("*")
        matched = [k for k in self._keys if k.startswith(prefix)]
        return 0, matched

    async def delete(self, *keys: str) -> int:
        for k in keys:
            self._keys.discard(k)
            self.deleted.append(k)
        return len(keys)


@pytest.mark.asyncio
async def test_invalidate_deletes_live_timeseries_anomaly_keys() -> None:
    """_invalidate_live_caches removes live, timeseries, and anomaly history keys."""
    redis = _FakeRedis([
        "pulse:v1:earthquakes:live:abc123",
        "pulse:v1:earthquakes:live:def456",
        "pulse:v1:stats:timeseries:111aaa",
        "pulse:v1:anomalies:history:222bbb",
    ])
    await ingestion_ctrl._invalidate_live_caches(redis)
    assert len(redis.deleted) == 4
    assert redis._keys == set()


@pytest.mark.asyncio
async def test_invalidate_leaves_slow_aggregate_keys_intact() -> None:
    """_invalidate_live_caches does NOT touch band, b-value, or magnitude-frequency keys."""
    slow_keys = {
        "pulse:v1:stats:magbands:aaa",
        "pulse:v1:stats:depthbands:bbb",
        "pulse:v1:earthquakes:bvalue:ccc",
        "pulse:v1:earthquakes:magfreq:ddd",
        "pulse:v1:stats:topn:eee",
        "pulse:v1:stats:rollups:network:fff",
    }
    redis = _FakeRedis(list(slow_keys))
    await ingestion_ctrl._invalidate_live_caches(redis)
    assert redis._keys == slow_keys
    assert redis.deleted == []


@pytest.mark.asyncio
async def test_invalidate_is_noop_when_no_matching_keys() -> None:
    """_invalidate_live_caches completes without error when no matching keys exist."""
    redis = _FakeRedis([])
    await ingestion_ctrl._invalidate_live_caches(redis)
    assert redis.deleted == []
