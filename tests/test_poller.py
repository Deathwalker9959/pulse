from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Ensure the real ingestion package is importable before loading poller.
ingestion_path = str(ROOT / "ingestion")
if ingestion_path not in sys.path:
    sys.path.insert(0, ingestion_path)

# Remove any stale stubs that other test files may have installed for these modules.
for _m in ("poller", "models", "decorators"):
    sys.modules.pop(_m, None)

import poller  # noqa: E402 — loaded fresh from ingestion/ on sys.path


def _make_feature(event_id: str, updated_iso: str, magnitude: float = 1.0) -> dict:
    ts_ms = int(datetime.fromisoformat(updated_iso).timestamp() * 1000)
    return {
        "id": event_id,
        "properties": {
            "time": ts_ms,
            "updated": ts_ms,
            "latitude": 0.0,
            "longitude": 0.0,
            "depth": 10.0,
            "mag": magnitude,
            "magType": "ml",
            "place": "test",
            "type": "earthquake",
            "status": "reviewed",
            "alert": None,
            "tsunami": 0,
            "sig": 100,
            "net": "ci",
            "nst": None,
            "gap": None,
        },
        "geometry": {"coordinates": [0.0, 0.0, 10.0]},
    }


@pytest.mark.asyncio
async def test_fetch_events_single_feed_returns_parsed_events(monkeypatch) -> None:
    """Single-URL mode returns parsed events from the primary feed."""
    from models.earthquake import EarthquakeEvent

    monkeypatch.setattr(poller, "USGS_SECONDARY_FEED_URL", "")
    feature = _make_feature("ev1", "2026-05-01T00:00:00+00:00", magnitude=2.5)

    async def fake_fetch_one(http, url):
        return [EarthquakeEvent.from_geojson_feature(feature)]

    monkeypatch.setattr(poller, "_fetch_one", fake_fetch_one)
    result = await poller.fetch_events.__wrapped__(MagicMock())
    assert len(result) == 1
    assert result[0].event_id == "ev1"


@pytest.mark.asyncio
async def test_fetch_events_merges_two_feeds_without_overlap(monkeypatch) -> None:
    """Two feeds with disjoint events are both included in the merged result."""
    from models.earthquake import EarthquakeEvent

    monkeypatch.setattr(poller, "USGS_SECONDARY_FEED_URL", "https://example.com/feed2")
    f1 = _make_feature("ev1", "2026-05-01T00:00:00+00:00")
    f2 = _make_feature("ev2", "2026-05-01T01:00:00+00:00")
    call_order: list[str] = []

    async def fake_fetch_one(http, url):
        call_order.append(url)
        return [EarthquakeEvent.from_geojson_feature(f2 if "feed2" in url else f1)]

    monkeypatch.setattr(poller, "_fetch_one", fake_fetch_one)
    result = await poller.fetch_events.__wrapped__(MagicMock())
    assert {e.event_id for e in result} == {"ev1", "ev2"}
    assert len(call_order) == 2


@pytest.mark.asyncio
async def test_fetch_events_dedup_keeps_latest_updated(monkeypatch) -> None:
    """When the same event_id appears in both feeds, the entry with the later updated timestamp wins."""
    from models.earthquake import EarthquakeEvent

    monkeypatch.setattr(poller, "USGS_SECONDARY_FEED_URL", "https://example.com/feed2")
    stale = _make_feature("ev1", "2026-05-01T00:00:00+00:00", magnitude=1.0)
    fresh = _make_feature("ev1", "2026-05-01T00:05:00+00:00", magnitude=1.5)

    async def fake_fetch_one(http, url):
        return [EarthquakeEvent.from_geojson_feature(fresh if "feed2" in url else stale)]

    monkeypatch.setattr(poller, "_fetch_one", fake_fetch_one)
    result = await poller.fetch_events.__wrapped__(MagicMock())
    assert len(result) == 1
    assert abs(result[0].magnitude - 1.5) < 0.01


@pytest.mark.asyncio
async def test_fetch_events_secondary_disabled_when_empty(monkeypatch) -> None:
    """When USGS_SECONDARY_FEED_URL is empty, only one fetch is issued."""
    monkeypatch.setattr(poller, "USGS_SECONDARY_FEED_URL", "")
    calls: list[str] = []

    async def fake_fetch_one(http, url):
        calls.append(url)
        return []

    monkeypatch.setattr(poller, "_fetch_one", fake_fetch_one)
    await poller.fetch_events.__wrapped__(MagicMock())
    assert len(calls) == 1
    assert calls[0] == poller.USGS_FEED_URL
