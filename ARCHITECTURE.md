# PULSE — Architecture Document

## System Overview

PULSE is a real-time flight intelligence platform built around a single data source (OpenSky Network) and a deliberately simple pipeline:

```
OpenSky REST API (10s cadence)
         │
         ▼
  [ingestion service]
   ├─ normalise FlightState
   ├─ XADD → Redis Stream: pulse:flights   (raw states, transit buffer)
   ├─ batch INSERT → ClickHouse: flights_raw
   ├─ anomaly detection per batch
   │   ├─ XADD → pulse:anomalies (pre-enrichment)
   │   ├─ INSERT → ClickHouse: anomaly_events
   │   ├─ enrich with Open-Meteo weather (async, best-effort)
   │   └─ XADD → pulse:alerts (enriched payload)
         │
         ▼
   [api service]
   ├─ XREADGROUP pulse:alerts → WebSocket fan-out (AlertManager)
   ├─ REST GET /api/flights/live → ClickHouse (Redis-cached, TTL 10s)
   ├─ REST GET /api/stats/* → ClickHouse hourly MV (Redis-cached, TTL 30-60s)
   └─ WS  /ws/alerts → connected dashboard clients
         │
         ▼
   [frontend]
   ├─ TanStack Query polls REST endpoints (10-60s intervals)
   └─ useAlerts hook maintains WebSocket connection (auto-reconnect)
```

---

## Design Decisions

### 1. Data source: OpenSky Network

OpenSky provides live ADS-B aircraft positions via a free public REST API (`/api/states/all`). No WebSocket stream is available from OpenSky itself — the polling model is intentional and rate-limited to 1 request per 10 seconds for anonymous callers. The ingestion layer adds resilience (retry, backoff, dedup) so the downstream pipeline is unaffected by transient failures.

### 2. Redis Streams over Pub/Sub

Pub/Sub would lose messages if any consumer is down at the moment of publish. Redis Streams persist messages until explicitly acknowledged or trimmed. This guarantees that a restarting API service can replay recent alerts without loss — a hard requirement given "resilient ingestion" is evaluated.

Consumer groups (`api-workers`) give at-most-once delivery per group member across multiple API instances, with ACK-based tracking. Pub/Sub cannot do this.

Trade-off: messages accumulate if consumers lag. Mitigated by `MAXLEN ~N` approximate trimming. ClickHouse is the durable store; streams are transit infrastructure only.

### 3. ClickHouse table engines

**`flights_raw` — `ReplacingMergeTree(last_contact)`**

OpenSky returns the same aircraft in successive polls. Rather than explicit dedup in application code, `ReplacingMergeTree` keeps the row with the highest `last_contact` per `(icao24, time_position)` during background merges. This is async — reads may see duplicates until a merge occurs. Queries that need exact counts use the `FINAL` modifier; dashboard queries omit it for performance.

**`flights_hourly_mv_data` — `SummingMergeTree`**

Materialized view maintained incrementally at insert time. Dashboard hourly queries hit the MV (microseconds) rather than scanning `flights_raw` (seconds). Read queries use `sum(flight_count)` not `count(*)` to handle unmerged parts correctly.

**`anomaly_events` — `MergeTree`**

Low-volume table (~100s of rows per day). No dedup requirement. 30-day TTL. Standard MergeTree is appropriate.

### 4. `LowCardinality` column types

`origin_country`, `squawk`, `anomaly_type`, `severity` all have bounded, low cardinality (< 1000 unique values). ClickHouse dictionary-encodes these columns, reducing storage ~10x and accelerating GROUP BY / WHERE operations. No application-level change required.

### 5. Redis TTL cache (not event-driven invalidation)

Cache keys are `pulse:v1:{endpoint}:{sha256(params)}` with TTLs calibrated to endpoint volatility:
- `/flights/live`: 10s — data refreshes every poll cycle
- `/stats/top-n`: 30s — changes slowly
- `/stats/hourly`: 60s — MV aggregates lag by ~1 poll cycle anyway

Event-driven invalidation (clearing cache on write) would require tight coupling between ingestion and API services. TTL is simpler, correct enough for this use case, and survives service restarts without stale cache.

### 6. No Kafka / message queue

At OpenSky's 10s poll cadence (~5k–10k aircraft per batch), direct write to ClickHouse is ~50ms and well within tolerance. Kafka's operational overhead (ZooKeeper or KRaft, topic management, partition rebalancing) is unjustified at this volume. Redis Streams provide the same ordering and consumer-group guarantees for this workload. Kafka becomes warranted at ~10k events/second sustained throughput.

### 7. Extension: Automatic Weather Contextualization

When an anomaly fires, the system automatically fetches weather from Open-Meteo (free, no auth, ~100ms) for the anomaly's lat/lon. The enriched alert is stored in ClickHouse and pushed to the dashboard. This derives information neither dataset provides alone: OpenSky can tell you *that* flights are deviating; Open-Meteo can tell you *why*.

The enrichment is async and best-effort. Alerts reach the dashboard immediately (pre-enrichment), then the ClickHouse row is updated when weather resolves. Frontend can refetch the full anomaly detail on click to get the latest weather context.

Weather per-grid caching (1° cell, 15-min TTL) is a planned optimization — currently each anomaly triggers a fresh fetch. At low anomaly rates this is fine.

---

## Trade-offs and Known Limitations

| Limitation | Correct approach with more time |
|---|---|
| `FINAL` queries on `flights_raw` are slow at high row counts | Replace with `flights_latest` table (AggregatingMergeTree, keyed by icao24) populated by a MV — O(1) live lookups |
| Single Redis instance is a SPOF | Redis Sentinel or Redis Cluster for HA |
| Per-process `rate_limit` state doesn't coordinate across multiple ingestion workers | Move rate-limit state to Redis INCR+TTL |
| Weather fetch per anomaly (no dedup by grid cell) | Cache weather by 1° cell with 15-min TTL in Redis |
| No auth on API endpoints | Add OAuth2/JWT, scope read-only for dashboard |
| OpenSky anonymous rate limit (10s/req) caps throughput | Authenticated OpenSky credentials (free registration) or ADS-B Exchange for higher throughput |
| No write-ahead log in ingestion | If the process crashes between `xadd` and `insert`, a batch may be lost. Tolerable for flight tracking; not for financial data |

---

## Expected Failure Points at Scale

1. **ClickHouse write throughput**: At 10x volume (100k aircraft), the 10s insert batch grows to ~100k rows. ClickHouse handles this comfortably (designed for 100k+ inserts/s). The bottleneck shifts to the `FINAL` modifier on live queries — see above.

2. **Redis Streams memory**: At sustained high volume with a slow consumer, stream length grows unboundedly. `MAXLEN ~50000` trims approximate. Monitor `XLEN pulse:flights`; reduce maxlen or add consumers if lag grows.

3. **WebSocket fan-out**: At 10k concurrent dashboard users, broadcasting from a single goroutine-equivalent asyncio task becomes a bottleneck. Add a dedicated broadcast worker per API instance, or use Redis Pub/Sub for intra-instance fan-out from a single Streams consumer.

4. **Open-Meteo API**: Free tier has undocumented rate limits. At high anomaly rates, weather fetches will start failing. The fallback (publish anomaly without weather) is implemented; add grid-cell caching to reduce calls.

---

## Planned Next Steps

- ClickHouse `flights_latest` table for O(1) live queries
- Authenticated OpenSky credentials (free registration)
- Weather fetch deduplication by 1° grid cell (Redis cache)
- API authentication (read-only JWT)
- Prometheus metrics endpoint (`/metrics`) on API and ingestion
- E2E test: `docker compose up`, assert data flows within 60s
