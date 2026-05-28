from __future__ import annotations

import os
from typing import Any

import clickhouse_connect

_client = None


async def get_client():
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


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    client = await get_client()
    result = await client.query(sql, parameters=params or {})
    return list(result.named_results())

