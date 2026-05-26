"""Ingestion service entrypoint."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def _main() -> None:
    from controllers.ingestion import run_ingestion_loop

    loop = asyncio.get_running_loop()
    task = asyncio.create_task(run_ingestion_loop(), name="ingestion-loop")

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("received %s — shutting down", sig.name)
        task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        await task
    except asyncio.CancelledError:
        logger.info("ingestion loop cancelled cleanly")


if __name__ == "__main__":
    asyncio.run(_main())
