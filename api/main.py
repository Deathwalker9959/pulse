"""FastAPI application factory."""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cache import get_redis
from controllers.alerts import alert_manager
from views.flights import router as flights_router
from views.stats import router as stats_router
from views.ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)

app = FastAPI(title="PULSE API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(flights_router)
app.include_router(stats_router)
app.include_router(ws_router)


@app.on_event("startup")
async def startup() -> None:
    redis = get_redis()
    await alert_manager.start(redis)


@app.on_event("shutdown")
async def shutdown() -> None:
    await alert_manager.stop()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
