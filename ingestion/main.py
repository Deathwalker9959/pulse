from __future__ import annotations

import asyncio
import logging
import sys

from controllers.historical import run_historical_sync
from controllers.ingestion import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)


async def main() -> None:
    """Run the live USGS poller and the historical backfill sync concurrently for the process lifetime."""
    await asyncio.gather(
        run(),
        run_historical_sync(),
    )


if __name__ == "__main__":
    asyncio.run(main())
