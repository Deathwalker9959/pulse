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
    """Placeholder db.query that fails loudly if a test forgets to monkeypatch the real one."""
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
    """Cache fake that always misses, so the @cached wrapper falls through to the (patched) query."""

    async def get(self, key: str):
        """Always miss, forcing the cache wrapper to call the underlying query."""
        return None

    async def setex(self, key: str, ttl: int, value: str):
        """Accept the cache write and discard it."""
        return True


@pytest.mark.asyncio
async def test_timeseries_coarse_bucket_uses_hourly_rollup_plus_raw_edges(monkeypatch) -> None:
    """A coarse, hour-aligned timeseries re-aggregates the hourly rollup (whole hours) and reads
    earthquakes_raw FINAL only for the partial edge hours; the outer bucket alias avoids a `time` collision."""
    captured: dict[str, str] = {}

    async def fake_query(sql: str, params: dict):
        """Capture the SQL/params the controller would run and return a canned row."""
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

    sql = captured["sql"]
    assert result[0]["event_count"] == 71
    assert "earthquakes_hourly_mv_data" in sql                    # rollup body
    assert "uniqExactMerge(event_count_state)" in sql
    assert "FROM earthquakes_raw FINAL" in sql                    # partial edge hours
    assert "bucket_time AS time" in sql                           # outer alias, no `time` collision
    assert "toStartOfMonth(hour, 'UTC') AS bucket_time" in sql    # body re-aggregates the rollup hours
    assert "toStartOfMonth(time, 'UTC') AS bucket_time" in sql    # edges bucket raw rows


@pytest.mark.asyncio
async def test_timeseries_sub_hour_bucket_reads_raw_only(monkeypatch) -> None:
    """Sub-hour buckets are finer than the hourly rollup, so timeseries reads earthquakes_raw directly."""
    captured: dict[str, str] = {}

    async def fake_query(sql: str, params: dict):
        captured["sql"] = sql
        return []

    monkeypatch.setattr(stats, "query", fake_query)
    await stats.get_timeseries(
        redis=FakeRedis(),
        bucket="5m",
        from_ts=datetime(2026, 5, 28, tzinfo=timezone.utc),
        to_ts=datetime(2026, 5, 29, tzinfo=timezone.utc),
    )
    assert "FROM earthquakes_raw FINAL" in captured["sql"]
    assert "_mv_data" not in captured["sql"]


@pytest.mark.asyncio
async def test_network_rollups_use_5m_rollup_for_coarse_buckets(monkeypatch) -> None:
    """A 5-minute-aligned network rollup re-aggregates the 5m rollup plus raw edges; 1m reads raw only."""
    captured: list[str] = []

    async def fake_query(sql: str, params: dict):
        captured.append(sql)
        return []

    monkeypatch.setattr(stats, "query", fake_query)
    start = datetime(2026, 5, 28, tzinfo=timezone.utc)
    end = datetime(2026, 5, 29, tzinfo=timezone.utc)

    await stats.get_network_rollups(redis=FakeRedis(), bucket="1h", from_ts=start, to_ts=end, net="", limit=500)
    await stats.get_network_rollups(redis=FakeRedis(), bucket="1m", from_ts=start, to_ts=end, net="", limit=500)

    assert "earthquakes_rollup_net_5m" in captured[0]            # coarse bucket → rollup body
    assert "uniqExactMerge(event_count_state)" in captured[0]
    assert "FROM earthquakes_raw FINAL" in captured[0]           # + raw edges
    assert "earthquakes_rollup_net_5m" not in captured[1]        # 1m → raw only
    assert "FROM earthquakes_raw FINAL" in captured[1]


@pytest.mark.asyncio
async def test_band_and_topn_queries_use_hourly_rollup_plus_raw_edges(monkeypatch) -> None:
    """For an hour-aligned window, net top-n and band queries read the hourly rollup for whole
    hours and earthquakes_raw FINAL only for the partial edge hours (the hybrid path)."""
    captured: list[str] = []

    async def fake_query(sql: str, params: dict):
        """Record each SQL string the controllers issue."""
        captured.append(sql)
        return []

    monkeypatch.setattr(stats, "query", fake_query)
    start = datetime(2026, 5, 28, tzinfo=timezone.utc)
    end = datetime(2026, 5, 29, tzinfo=timezone.utc)  # both on hour boundaries → rollup body exists

    await stats.get_top_n(redis=FakeRedis(), field="net", limit=10, from_ts=start, to_ts=end)
    await stats.get_magnitude_bands(redis=FakeRedis(), from_ts=start, to_ts=end)
    await stats.get_depth_bands(redis=FakeRedis(), from_ts=start, to_ts=end)

    assert len(captured) == 3
    expected_rollups = [
        "earthquakes_hourly_mv_data",
        "earthquakes_mag_band_mv_data",
        "earthquakes_depth_band_mv_data",
    ]
    for sql, rollup in zip(captured, expected_rollups):
        assert rollup in sql                          # whole-hour body from the rollup
        assert "uniqExactMerge(event_count_state)" in sql
        assert "FROM earthquakes_raw FINAL" in sql    # partial edge hours from raw
        assert "_mv_data" not in sql.split("UNION ALL")[1]  # raw edge side touches no rollup


@pytest.mark.asyncio
async def test_band_queries_fall_back_to_raw_for_sub_hour_window(monkeypatch) -> None:
    """A window with no complete hour has no rollup body, so the query reads earthquakes_raw only."""
    captured: list[str] = []

    async def fake_query(sql: str, params: dict):
        captured.append(sql)
        return []

    monkeypatch.setattr(stats, "query", fake_query)
    start = datetime(2026, 5, 28, 0, 10, tzinfo=timezone.utc)
    end = datetime(2026, 5, 28, 0, 40, tzinfo=timezone.utc)  # 30 min, spans no whole hour

    await stats.get_magnitude_bands(redis=FakeRedis(), from_ts=start, to_ts=end)
    await stats.get_top_n(redis=FakeRedis(), field="net", limit=10, from_ts=start, to_ts=end)

    assert len(captured) == 2
    assert all("FROM earthquakes_raw FINAL" in sql for sql in captured)
    assert all("_mv_data" not in sql for sql in captured)
