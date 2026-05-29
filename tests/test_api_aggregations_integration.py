from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from typing import Any

import pytest

API_BASE = "http://localhost:8000"
CLICKHOUSE_CONTAINER = "fivecell-clickhouse-1"
INGESTION_CONTAINER = "fivecell-ingestion-1"


def _docker(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def _require_container(name: str) -> None:
    result = _docker("ps", "--format", "{{.Names}}")
    if result.returncode != 0:
        pytest.skip(f"docker is unavailable: {result.stderr.strip()}")
    if name not in result.stdout.splitlines():
        pytest.skip(f"{name} is not running")


def _api(path: str, params: dict[str, Any] | None = None) -> Any:
    params = params or {}
    url = API_BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read()
            if "json" in content_type:
                return json.loads(body)
            return {"content_type": content_type, "bytes": len(body)}
    except Exception as exc:
        pytest.skip(f"API is unavailable at {API_BASE}: {exc}")


def _clickhouse_json(sql: str) -> list[dict[str, Any]]:
    _require_container(CLICKHOUSE_CONTAINER)
    result = _docker(
        "exec",
        CLICKHOUSE_CONTAINER,
        "clickhouse-client",
        "--query",
        sql.strip() + " FORMAT JSON",
    )
    if result.returncode != 0:
        pytest.fail(result.stderr)
    return json.loads(result.stdout)["data"]


def _clickhouse_multi(sql: str) -> None:
    result = _docker("exec", CLICKHOUSE_CONTAINER, "clickhouse-client", "--multiquery", "--query", sql)
    if result.returncode != 0:
        pytest.fail(result.stderr)


def _as_int(value: Any) -> int:
    return int(value)


@pytest.fixture(scope="module")
def may_28_window() -> tuple[str, str, str, str, int]:
    _require_container(CLICKHOUSE_CONTAINER)
    start_api = "2026-05-28T00:00:00.000Z"
    end_api = "2026-05-28T23:59:59.000Z"
    start_sql = "2026-05-28 00:00:00"
    end_sql = "2026-05-28 23:59:59"
    rows = _clickhouse_json(
        f"""
        SELECT count() AS count
        FROM earthquakes_raw FINAL
        WHERE time BETWEEN toDateTime('{start_sql}') AND toDateTime('{end_sql}')
        """
    )
    raw_count = _as_int(rows[0]["count"])
    if raw_count == 0:
        pytest.skip("fixture data for 2026-05-28 is not loaded")
    return start_api, end_api, start_sql, end_sql, raw_count


@pytest.mark.integration
def test_every_http_route_responds(may_28_window: tuple[str, str, str, str, int]) -> None:
    start_api, end_api, *_ = may_28_window
    routes = [
        ("/health", {}),
        ("/api/earthquakes/live", {"from": start_api, "to": end_api}),
        ("/api/earthquakes/heatmap", {"from": start_api, "to": end_api, "resolution": "3"}),
        ("/api/earthquakes/timeseries", {"from": start_api, "to": end_api, "bucket": "1h"}),
        ("/api/earthquakes/top-networks", {"from": start_api, "to": end_api, "limit": "10"}),
        ("/api/earthquakes/top-places", {"from": start_api, "to": end_api, "limit": "10"}),
        ("/api/earthquakes/magnitude-bands", {"from": start_api, "to": end_api}),
        ("/api/earthquakes/depth-bands", {"from": start_api, "to": end_api}),
        ("/api/earthquakes/geospatial-density", {"bbox": "-180,-90,180,90", "interval": "24h"}),
        ("/api/earthquakes/rollups/network", {"from": start_api, "to": end_api, "bucket": "5m", "limit": "10000"}),
        ("/api/anomalies/history", {"from": start_api, "to": end_api, "limit": "100000"}),
        ("/api/ingestion/status", {}),
    ]
    for path, params in routes:
        payload = _api(path, params)
        assert payload is not None


@pytest.mark.integration
@pytest.mark.parametrize("bucket", ["1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"])
def test_timeseries_totals_match_final_raw_table(may_28_window: tuple[str, str, str, str, int], bucket: str) -> None:
    start_api, end_api, _, _, raw_count = may_28_window
    rows = _api("/api/earthquakes/timeseries", {"from": start_api, "to": end_api, "bucket": bucket})
    assert sum(_as_int(row["event_count"]) for row in rows) == raw_count


@pytest.mark.integration
@pytest.mark.parametrize("bucket", ["1m", "5m", "15m", "1h", "6h", "1d", "1mo", "1y"])
def test_network_rollups_totals_match_final_raw_table(may_28_window: tuple[str, str, str, str, int], bucket: str) -> None:
    start_api, end_api, _, _, raw_count = may_28_window
    rows = _api("/api/earthquakes/rollups/network", {"from": start_api, "to": end_api, "bucket": bucket, "limit": "10000"})
    assert sum(_as_int(row["event_count"]) for row in rows) == raw_count


@pytest.mark.integration
def test_band_topn_heatmap_and_anomaly_aggregations_match_clickhouse(may_28_window: tuple[str, str, str, str, int]) -> None:
    start_api, end_api, start_sql, end_sql, raw_count = may_28_window

    heatmap = _api("/api/earthquakes/heatmap", {"from": start_api, "to": end_api, "resolution": "3"})
    assert sum(_as_int(row["event_count"]) for row in heatmap) == raw_count

    api_mag = {row["mag_band"]: _as_int(row["event_count"]) for row in _api("/api/earthquakes/magnitude-bands", {"from": start_api, "to": end_api})}
    raw_mag = {
        row["mag_band"]: _as_int(row["event_count"])
        for row in _clickhouse_json(
            f"""
            SELECT mag_band, count() AS event_count
            FROM earthquakes_raw FINAL
            WHERE time BETWEEN toDateTime('{start_sql}') AND toDateTime('{end_sql}')
              AND mag_band != ''
            GROUP BY mag_band
            ORDER BY event_count DESC
            """
        )
    }
    assert api_mag == raw_mag

    api_depth = {row["depth_band"]: _as_int(row["event_count"]) for row in _api("/api/earthquakes/depth-bands", {"from": start_api, "to": end_api})}
    raw_depth = {
        row["depth_band"]: _as_int(row["event_count"])
        for row in _clickhouse_json(
            f"""
            SELECT depth_band, count() AS event_count
            FROM earthquakes_raw FINAL
            WHERE time BETWEEN toDateTime('{start_sql}') AND toDateTime('{end_sql}')
              AND depth_band != ''
            GROUP BY depth_band
            ORDER BY event_count DESC
            """
        )
    }
    assert api_depth == raw_depth

    api_networks = {row["label"]: _as_int(row["count"]) for row in _api("/api/earthquakes/top-networks", {"from": start_api, "to": end_api, "limit": "10"})}
    raw_networks = {
        row["label"]: _as_int(row["count"])
        for row in _clickhouse_json(
            f"""
            SELECT net AS label, count() AS count
            FROM earthquakes_raw FINAL
            WHERE time BETWEEN toDateTime('{start_sql}') AND toDateTime('{end_sql}')
              AND net != ''
            GROUP BY net
            ORDER BY count DESC
            LIMIT 10
            """
        )
    }
    assert api_networks == raw_networks

    api_anomalies = _api("/api/anomalies/history", {"from": start_api, "to": end_api, "limit": "100000"})
    raw_anomaly_count = _as_int(
        _clickhouse_json(
            f"""
            SELECT count() AS count
            FROM (
                SELECT ae.source_event_id, ae.anomaly_type
                FROM anomaly_events AS ae
                LEFT JOIN (
                    SELECT event_id, argMax(time, ingested_at) AS source_event_time
                    FROM earthquakes_raw
                    GROUP BY event_id
                ) AS er ON ae.source_event_id = er.event_id
                WHERE if(ae.event_time > toDateTime(0), ae.event_time, er.source_event_time) > toDateTime(0)
                  AND if(ae.event_time > toDateTime(0), ae.event_time, er.source_event_time) BETWEEN toDateTime('{start_sql}') AND toDateTime('{end_sql}')
                GROUP BY ae.source_event_id, ae.anomaly_type
            )
            """
        )[0]["count"]
    )
    assert len(api_anomalies) == raw_anomaly_count


@pytest.mark.integration
def test_ingestion_writer_to_api_end_to_end() -> None:
    _require_container(INGESTION_CONTAINER)
    _require_container(CLICKHOUSE_CONTAINER)
    event_id = "test-e2e-aggregation-api-001"
    start = "2026-12-31T23:30:00.000Z"
    end = "2027-01-01T00:30:00.000Z"
    cleanup = f"""
    ALTER TABLE anomaly_events DELETE WHERE source_event_id = '{event_id}';
    ALTER TABLE earthquakes_raw DELETE WHERE event_id = '{event_id}';
    """
    _clickhouse_multi(cleanup)

    script = f"""
import asyncio
from datetime import datetime, timezone
import os
import clickhouse_connect
from models import EarthquakeEvent, AnomalyEvent, AnomalyType, Severity
from models.anomaly import _anomaly_id
from writer import write_anomalies, write_earthquakes

async def main():
    client = await clickhouse_connect.get_async_client(
        host=os.getenv('CLICKHOUSE_HOST', 'clickhouse'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
        database=os.getenv('CLICKHOUSE_DB', 'default'),
        username=os.getenv('CLICKHOUSE_USER', 'default'),
        password=os.getenv('CLICKHOUSE_PASSWORD', ''),
    )
    event = EarthquakeEvent(
        event_id='{event_id}',
        time=datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc),
        updated=datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc),
        latitude=12.34,
        longitude=56.78,
        depth_km=12.0,
        magnitude=6.6,
        mag_type='mww',
        place='Integration Test Ridge',
        event_type='earthquake',
        status='reviewed',
        alert='yellow',
        tsunami=True,
        significance=650,
        net='it',
    )
    anomaly = AnomalyEvent(
        anomaly_id=_anomaly_id(event.event_id, AnomalyType.TSUNAMI_ALERT),
        event_time=event.time,
        anomaly_type=AnomalyType.TSUNAMI_ALERT,
        severity=Severity.CRITICAL,
        source_event_id=event.event_id,
        source_place=event.place,
        latitude=event.latitude,
        longitude=event.longitude,
        detail='Integration tsunami alert',
    )
    await write_earthquakes(client, [event])
    await write_anomalies(client, [anomaly])
    await client.close()
asyncio.run(main())
"""
    result = _docker("exec", "-i", INGESTION_CONTAINER, "python", "-", input_text=script)
    assert result.returncode == 0, result.stderr

    try:
        live = _api("/api/earthquakes/live", {"from": start, "to": end, "min_magnitude": "6"})
        assert any(row["event_id"] == event_id for row in live)

        anomalies = _api("/api/anomalies/history", {"from": start, "to": end, "limit": "100"})
        matching = [row for row in anomalies if row["source_event_id"] == event_id and row["anomaly_type"] == "TSUNAMI_ALERT"]
        assert len(matching) == 1
        assert matching[0]["severity"] == "CRITICAL"

        timeseries = _api("/api/earthquakes/timeseries", {"from": start, "to": end, "bucket": "1h"})
        assert sum(_as_int(row["event_count"]) for row in timeseries) >= 1
    finally:
        _clickhouse_multi(cleanup)
