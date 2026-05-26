"""OpenSky Network REST poller — produces FlightState records."""
from __future__ import annotations

import logging

import httpx

from decorators import rate_limit, retry, timed
from models import FlightState

logger = logging.getLogger(__name__)

OPENSKY_URL = "https://opensky-network.org/api/states/all"
# OpenSky public API: anonymous callers limited to 1 request per 10s.
# Authenticated users get higher limits — credentials optional via env vars.
POLL_INTERVAL = 10.0


@retry(max_attempts=8, backoff_base=2.0, max_delay=60.0, exceptions=(httpx.HTTPError, Exception))
@rate_limit(min_interval=POLL_INTERVAL)
@timed(logger=logger, threshold_ms=8_000)
async def fetch_states(client: httpx.AsyncClient, username: str = "", password: str = "") -> list[FlightState]:
    """Fetch current aircraft states from OpenSky.

    Returns an empty list on transient failures so the write pipeline
    continues without crashing — @retry handles persistent failures.
    """
    auth = (username, password) if username else None
    response = await client.get(OPENSKY_URL, auth=auth, timeout=15.0)

    if response.status_code == 429:
        logger.warning("OpenSky rate limited (429); backing off")
        raise httpx.HTTPStatusError("rate limited", request=response.request, response=response)

    response.raise_for_status()
    body = response.json()
    raw_states = body.get("states") or []

    states = []
    for raw in raw_states:
        try:
            states.append(FlightState.from_opensky_state(raw))
        except Exception as exc:
            # Malformed state vectors are skipped, not fatal.
            logger.debug("skipping malformed state vector: %s", exc)

    logger.info("fetched %d aircraft states", len(states))
    return states
