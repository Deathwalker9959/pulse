from __future__ import annotations

from datetime import datetime, timezone

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
decorators_spec = importlib.util.spec_from_file_location("decorators", ROOT / "api" / "decorators.py")
assert decorators_spec and decorators_spec.loader
api_decorators = importlib.util.module_from_spec(decorators_spec)
decorators_spec.loader.exec_module(api_decorators)
previous_decorators = sys.modules.get("decorators")
previous_db = sys.modules.get("db")
fake_db = types.ModuleType("db")

async def _unpatched_query(*args, **kwargs):
    raise AssertionError("stats.query must be monkeypatched in unit tests")

fake_db.query = _unpatched_query
sys.modules["decorators"] = api_decorators
sys.modules["db"] = fake_db
try:
    spec = importlib.util.spec_from_file_location("api_stats", ROOT / "api" / "controllers" / "stats.py")
    assert spec and spec.loader
    stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stats)
finally:
    if previous_decorators is not None:
        sys.modules["decorators"] = previous_decorators
    else:
        sys.modules.pop("decorators", None)
    if previous_db is not None:
        sys.modules["db"] = previous_db
    else:
        sys.modules.pop("db", None)


class FakeRedis:
    async def get(self, key: str):
        return None

    async def setex(self, key: str, ttl: int, value: str):
        return True


@pytest.mark.asyncio
async def test_timeseries_aggregates_from_final_raw_table_and_avoids_time_alias_collision(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_query(sql: str, params: dict):
        captured["sql"] = sql
        captured["params"] = params
        return [{"time": "2026-05-01T00:00:00", "event_count": 71, "avg_magnitude": 2.5}]

    monkeypatch.setattr(stats, "query", fake_query)
    result = await stats.get_timeseries(
        redis=FakeRedis(),
        bucket="1mo",
        from_ts=datetime(2026, 5, 28, tzinfo=timezone.utc),
        to_ts=datetime(2026, 5, 29, tzinfo=timezone.utc),
    )

    assert result[0]["event_count"] == 71
    assert "FROM earthquakes_raw FINAL" in captured["sql"]
    assert "bucket_time AS time" in captured["sql"]
    assert "toStartOfMonth(time, 'UTC') AS bucket_time" in captured["sql"]
    assert "GROUP BY bucket_time" in captured["sql"]
    assert "earthquakes_hourly_mv_data" not in captured["sql"]


@pytest.mark.asyncio
async def test_band_and_topn_queries_use_final_raw_table(monkeypatch) -> None:
    captured: list[str] = []

    async def fake_query(sql: str, params: dict):
        captured.append(sql)
        return []

    monkeypatch.setattr(stats, "query", fake_query)
    start = datetime(2026, 5, 28, tzinfo=timezone.utc)
    end = datetime(2026, 5, 29, tzinfo=timezone.utc)

    await stats.get_top_n(redis=FakeRedis(), field="net", limit=10, from_ts=start, to_ts=end)
    await stats.get_magnitude_bands(redis=FakeRedis(), from_ts=start, to_ts=end)
    await stats.get_depth_bands(redis=FakeRedis(), from_ts=start, to_ts=end)

    assert len(captured) == 3
    assert all("FROM earthquakes_raw FINAL" in sql for sql in captured)
    assert all("_mv_data" not in sql for sql in captured)
