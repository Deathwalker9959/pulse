# PULSE — Real-Time Earthquake Intelligence Platform

Live seismic monitoring platform: ingests the USGS global earthquake feed, stores events in ClickHouse for analytical querying, exposes aggregation endpoints through FastAPI, and presents them through a React dashboard with live anomaly alerting and a seismic risk forecast.

## Quick start

```bash
docker compose up --build
```

Open **http://localhost** — events appear on the map within ~60 seconds as the USGS feed is polled.

**Prerequisites:** Docker 24+ with BuildKit enabled (default since Docker 23). No other setup required; all services start and wire together automatically.

## Services

| Service | URL | Description |
|---|---|---|
| Dashboard | http://localhost | React dashboard (nginx reverse proxy) |
| API | http://localhost:8000 | FastAPI REST + WebSocket |
| ClickHouse | http://localhost:8123 | Analytical store (HTTP interface) |
| Redis | localhost:6379 | Stream bus + query cache |
| MinIO | http://localhost:9001 | Cold-tier object storage console |

## API endpoints

```
GET  /api/earthquakes/live                           Recent events (windowed, magnitude-filtered)
GET  /api/earthquakes/timeseries?bucket=1h           Event counts + avg magnitude per time bucket
GET  /api/earthquakes/top-networks                   Top-N reporting networks by event count
GET  /api/earthquakes/top-places                     Top-N place labels by event count
GET  /api/earthquakes/magnitude-bands                Event counts per magnitude band
GET  /api/earthquakes/depth-bands                    Event counts per depth band
GET  /api/earthquakes/heatmap                        H3-cell density for map heatmap layer
GET  /api/earthquakes/geospatial-density             1°x1° grid counts inside a bbox
GET  /api/earthquakes/rollups/network                Per-bucket per-network counts and averages
GET  /api/earthquakes/magnitude-frequency            Gutenberg-Richter frequency-magnitude distribution
GET  /api/earthquakes/energy-timeseries              Radiated seismic energy per time bucket
GET  /api/earthquakes/b-value-history                Daily Gutenberg-Richter b-value series
GET  /api/earthquakes/inter-event-times              Histogram of gaps between consecutive events
GET  /api/earthquakes/seismic-risk                   Probabilistic risk score per H3 cell (extension)
GET  /api/anomalies/history                          Recent detected anomaly signals
GET  /api/ingestion/status                           Pipeline health: data age, poll heartbeat, counts
GET  /health                                         Liveness probe
WS   /ws/events                                      Live stream of new/revised earthquake events
WS   /ws/alerts                                      Live stream of detected anomaly signals
```

## Configuration

Copy `.env.example` to `.env` to customise behaviour:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `USGS_FEED_URL` | `all_hour.geojson` | Primary USGS GeoJSON feed |
| `USGS_SECONDARY_FEED_URL` | `all_day.geojson` | Secondary feed (fetched concurrently; empty to disable) |
| `USGS_POLL_INTERVAL` | `60` | Seconds between USGS polls |
| `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` | `default` / `` | ClickHouse credentials |

## Running tests

Unit and integration tests are in `tests/`. Unit tests run without any services:

```bash
# unit tests only (no Docker required)
pytest tests/ -m "not integration"

# integration tests (requires docker compose up --build first)
pytest tests/ -m integration
```

## Stack

| Layer | Technology |
|---|---|
| Ingestion | Python 3.12, asyncio, httpx — live poller + historical backfill |
| Stream bus | Redis 8 Streams (XADD / XREAD) |
| Analytical store | ClickHouse 24 — ReplacingMergeTree + AggregatingMergeTree materialized views |
| Query cache | Redis 8 — TTL-keyed with active invalidation after writes |
| API | FastAPI, uvicorn, WebSocket |
| Frontend | React 19, TypeScript, Vite, MapLibre GL, Recharts, MUI, TanStack Query |
| Cold storage | MinIO (S3-compatible) — ClickHouse tiered storage after 7 days |
| Deployment | Docker Compose — single command, healthcheck-gated startup ordering |

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for design decisions, trade-offs, known limitations, and scaling notes.
