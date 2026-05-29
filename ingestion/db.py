from __future__ import annotations

import os

import clickhouse_connect


async def get_clickhouse_client():
    """Create a fresh ClickHouse async client from the CLICKHOUSE_* environment vars."""
    return await clickhouse_connect.get_async_client(
        host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        database=os.getenv("CLICKHOUSE_DB", "default"),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
    )
