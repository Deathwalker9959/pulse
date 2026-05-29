from __future__ import annotations

import logging
import os
from pathlib import Path

import clickhouse_connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrations")


def _split_statements(sql: str) -> list[str]:
    """Split a .sql file into individual statements on `;`, dropping blank lines and `--` comments."""
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements


def main() -> None:
    """Apply every versions/*.sql migration in filename order against ClickHouse."""
    client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        database=os.getenv("CLICKHOUSE_DB", "default"),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
    )
    for path in sorted(Path("versions").glob("*.sql")):
        logger.info("applying %s", path)
        for statement in _split_statements(path.read_text()):
            client.command(statement)
    logger.info("migrations complete")


if __name__ == "__main__":
    main()

