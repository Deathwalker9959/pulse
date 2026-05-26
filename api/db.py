"""ClickHouse async client — singleton pattern, one per API process."""
from __future__ import annotations

import os
from typing import Any

import clickhouse_connect

_client: Any = None  # clickhouse_connect.driver.AsyncClient


async def get_client() -> Any:
    global _client
    if _client is None:
        _client = await clickhouse_connect.get_async_client(
            host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            database=os.getenv("CLICKHOUSE_DB", "default"),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )
    return _client


async def query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a SELECT and return list of row dicts."""
    client = await get_client()
    result = await client.query(sql, parameters=params or {})
    return [dict(zip(result.column_names, row)) for row in result.result_rows]
