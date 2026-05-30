from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cache import close_redis
from db import close_client
from views.earthquakes import anomaly_router, earthquake_router, ingestion_router
from views.ws import alert_broadcaster, event_broadcaster, router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the WebSocket broadcasters on boot; stop them and close Redis/ClickHouse on shutdown."""
    await asyncio.gather(event_broadcaster.start(), alert_broadcaster.start())
    try:
        yield
    finally:
        await asyncio.gather(event_broadcaster.stop(), alert_broadcaster.stop())
        await close_redis()
        await close_client()


app = FastAPI(title="PULSE Earthquake API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(earthquake_router)
app.include_router(anomaly_router)
app.include_router(ingestion_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: always returns {"status": "ok"} if the process is serving."""
    return {"status": "ok"}
