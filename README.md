# PULSE — Real-Time Flight Intelligence Platform

Real-time flight tracking platform: ingests OpenSky Network ADS-B data, stores in ClickHouse, exposes via FastAPI, and presents through a React dashboard with live anomaly alerting.

## Quick start

```bash
docker compose up --build
```

Open `http://localhost:5173` — aircraft appear on the map within ~30 seconds.

**Prerequisites:** Docker 24+ with BuildKit enabled (default since Docker 23).

## Optional: OpenSky credentials

Anonymous access is rate-limited to 1 request per 10 seconds (~5k–10k aircraft per poll). For higher limits, create a free account at https://opensky-network.org and set:

```bash
cp .env.example .env
# edit .env with your credentials
docker compose up --build
```

## Services

| Service | URL | Description |
|---|---|---|
| Frontend | http://localhost:5173 | React dashboard |
| API | http://localhost:8000 | FastAPI + WebSocket |
| ClickHouse | http://localhost:8123 | HTTP interface (admin) |
| Redis | localhost:6379 | Stream bus + cache |

## API endpoints

```
GET  /api/flights/live                          Current aircraft positions
GET  /api/flights/history?icao24=&from=&to=     Position track for one aircraft
GET  /api/stats/top-n?field=origin_country&limit=10  Top-N by field
GET  /api/stats/hourly?from=&to=                Hourly counts
GET  /api/stats/density?bbox=lon,lat,lon,lat    Grid density
GET  /api/anomalies/history                     Recent anomaly events
WS   /ws/alerts                                 Live anomaly stream
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for design decisions, trade-offs, and scaling notes.

## Stack

- **Ingestion**: Python 3.14, asyncio, httpx
- **Stream bus**: Redis 8 Streams (XADD/XREADGROUP)
- **Storage**: ClickHouse 24 (ReplacingMergeTree + materialized views)
- **Cache**: Redis 8 (TTL-keyed)
- **API**: FastAPI, uvicorn, WebSocket
- **Frontend**: React 19, TypeScript, Vite, Leaflet, Recharts, TanStack Query
- **Deploy**: Docker Compose with BuildKit layer caching
