# PULSE — Architecture Document

## System Overview

PULSE is a real-time earthquake intelligence platform. It ingests the USGS global seismic feed, detects anomalies, persists events to a columnar store, and surfaces live analytics through a REST API and WebSocket dashboard.

```
USGS GeoJSON feed (60 s cadence)
         │
         ▼
  [ingestion service]
   ├─ fetch & parse EarthquakeEvent (httpx async, retry/backoff)
   ├─ SETEX pulse:last-poll-at  → Redis (pipeline health heartbeat)
   ├─ dedup via Redis hash (pulse:seen-events, 7-day TTL)
   ├─ assign plate_name via H3 pre-index → PB2002 point-in-polygon (shapely)
   ├─ assign boundary_km via STRtree over PB2002 LineStrings
   ├─ XADD → pulse:events stream   (raw events, transit buffer)
   ├─ batch INSERT → ClickHouse: earthquakes_raw
   ├─ 13 anomaly detectors in parallel (asyncio.gather)
   │   ├─ 7 live detectors (Redis-backed rolling state)
   │   └─ 6 stateless / per-batch detectors
   ├─ INSERT → ClickHouse: anomaly_events  (with plate_name, source_net)
   └─ XADD → pulse:alerts stream   (detected anomalies)
         │
         ▼
  [api service]
   ├─ XREAD pulse:events / pulse:alerts → WebSocket fan-out
   ├─ GET /api/earthquakes/*  → ClickHouse (Redis TTL cache 10–120 s); all endpoints accept ?plate=&net= filters
   ├─ GET /api/earthquakes/plates → static plate name list from PB2002 GeoJSON (uncached)
   ├─ GET /api/anomalies/*    → ClickHouse (Redis TTL cache 10 s)
   ├─ GET /api/earthquakes/seismic-risk → ClickHouse (cached 120 s)
   ├─ GET /api/ingestion/status → ClickHouse + Redis (uncached)
   └─ WS /ws/events, /ws/alerts → connected dashboard clients
         │
         ▼
  [frontend — React 19 + MapLibre GL]
   ├─ TanStack Query polls REST endpoints (staleTime 30–120 s)
   ├─ useWebSocket maintains two WS connections (auto-reconnect)
   └─ MapLibreView renders epicentres, anomaly hexes, seismic risk spikes
```

---

## Design Decisions

### 1. Data source: USGS Earthquake Hazards Program

USGS provides global earthquake data via GeoJSON REST feeds updated continuously. The `all_hour` summary (~100 events, last hour) is polled every 60 seconds. An optional secondary feed (`USGS_SECONDARY_FEED_URL`) can be configured for concurrent fetching — both are merged with `asyncio.gather` and deduplicated by `(event_id, updated)` timestamp before writing.

The ingestion poller writes a `pulse:last-poll-at` heartbeat key to Redis (TTL 300 s) after every successful fetch, whether or not new events were found. This lets the API distinguish "quiet seismic period" from "pipeline down" in the ingestion status endpoint.

### 2. Redis Streams over Pub/Sub

Pub/Sub loses messages if any consumer is down at the moment of publish. Streams persist messages until trimmed. This guarantees that a restarting API service can replay recent events without loss.

`MAXLEN ~N` approximate trimming keeps memory bounded (`pulse:events` capped at 50 000, `pulse:alerts` at 10 000). ClickHouse is the durable store; streams are transit infrastructure only.

### 3. ClickHouse table engines

**`earthquakes_raw` — `ReplacingMergeTree(updated)`**

USGS revises events continuously (new stations, recalculated magnitudes). `ReplacingMergeTree` keeps the row with the highest `updated` timestamp per `(time, event_id)` during background merges. Reads that need exact counts use `FINAL`; dashboard queries use the rollup materialized views to avoid the merge cost.

**`earthquakes_hourly_mv_data` / `earthquakes_hourly_plate_mv_data` / `earthquakes_mag_band_mv_data` / `earthquakes_depth_band_mv_data` / `earthquakes_rollup_net_5m` / `earthquakes_hourly_bvalue_mv_data` — `AggregatingMergeTree`**

Materialized views maintained incrementally at insert time using `-State` combinators (`uniqExactState`, `sumState`, `countState`). Dashboard queries re-aggregate with `-Merge` combinators, hitting microsecond-latency rollup tables rather than scanning the raw fact table. A hybrid pattern (`_aligned_split`) serves whole-bucket queries from the rollup and partial edge buckets from the raw table, guaranteeing exactness for any window.

`earthquakes_hourly_plate_mv_data` is a plate-keyed variant of the hourly rollup, used when a `plate=` filter is active. `earthquakes_hourly_bvalue_mv_data` pre-aggregates per-hour magnitude sums for fast b-value history queries.

**`anomaly_events` — `MergeTree`**

Low-volume (~100s of rows per day). Deterministic `anomaly_id = SHA256(event_id + anomaly_type)[:36]` makes inserts idempotent. 30-day TTL.

### 4. LowCardinality column types

`net`, `mag_type`, `event_type`, `status`, `alert`, `mag_band`, `depth_band`, `geohash` all have < 1 000 distinct values. ClickHouse dictionary-encodes these, reducing storage ~10× and accelerating GROUP BY / WHERE filters. Pre-computed `mag_band` and `depth_band` columns on the raw table turn expensive `CASE WHEN magnitude BETWEEN …` expressions into equality predicates.

### 5. Redis cache — keying and invalidation

Cache keys: `pulse:v1:{endpoint}:{sha256(sorted_params)[:20]}`

TTLs calibrated to endpoint volatility:
- `/earthquakes/live`, `/anomalies/history`: 10 s — direct event view, must refresh quickly
- `/timeseries`, `/top-networks`, `/top-places`, `/density`, `/rollups/network`: 30 s
- `/magnitude-bands`, `/depth-bands`, `/energy-timeseries`, `/heatmap`: 60 s
- `/magnitude-frequency`, `/b-value-history`, `/inter-event-times`, `/seismic-risk`: 120 s

**Active invalidation for freshness-critical endpoints**: after each ingestion cycle that writes new events, the ingestion service performs a Redis SCAN+DEL over `pulse:v1:earthquakes:live:*`, `pulse:v1:stats:timeseries:*`, and `pulse:v1:anomalies:history:*`. This ensures the live feed and timeseries reflect new data within seconds, not after a TTL timeout. Slowly-moving aggregates (bands, b-value, risk) are correctly left to TTL-only expiry.

`allkeys-lru` eviction policy with a 512 MB cap — correct for a pure-cache workload where no key needs explicit retention.

### 6. Anomaly detection — 13 detectors

Seven live detectors maintain rolling state in Redis (z-score windows, geohash-keyed sorted sets) and run in parallel via `asyncio.gather` each poll cycle:

| Detector | Signal | Redis key type |
|---|---|---|
| MAGNITUDE_SPIKE | z-score > 2.5 vs 12-batch window | List (LPUSH/LTRIM) |
| ENERGY_BURST | cumulative energy z-score | List |
| SWARM_DETECTION | per-geohash-5 event count z-score | List per cell |
| AFTERSHOCK_CASCADE | M<5.5 near recent M≥5.5 mainshocks | Hash (48 h TTL) |
| GLOBAL_RATE_SPIKE / SEISMIC_QUIESCENCE | event rate z-score | List |
| DEEP_FOCUS_CLUSTER | 3+ events >300 km deep per geohash-3 | Counter (24 h TTL) |
| FORESHOCK_SEQUENCE | frequency acceleration + magnitude escalation | Sorted set (72 h) |

Six stateless detectors run per-batch with no Redis state: SIGNIFICANT_EVENT, TSUNAMI_ALERT, TSUNAMI_RISK, B_VALUE_ANOMALY, DATA_QUALITY_ANOMALY, and their historical variants for backfill.

Historical backfill runs daily as a separate concurrent worker, re-running stateless anomaly detectors over month-by-month USGS ComCat data with a pipelined prefetch (month N+1 fetches while month N inserts).

### 7. No Kafka / message queue

At 60 s poll cadence, direct ClickHouse writes are ~50 ms — well within tolerance. Kafka's operational overhead is unjustified. Redis Streams provide the same ordering and consumer-group guarantees for this workload.

---

## Extension: Seismic Risk Forecast

### Motivation

The existing anomaly detectors are reactive: they fire when something unusual has already happened. The seismic risk layer adds a *prospective* view — a spatial probability surface showing where elevated risk exists based on recent seismicity patterns, independent of whether an anomaly has fired.

### Method

The endpoint `GET /api/earthquakes/seismic-risk` aggregates the last 30 days of seismicity into H3 cells (resolution 2, ~500 km edge by default) and computes a risk score (0–1) per cell from three signals:

**1. Normalised 7-day event rate**
Short-term seismicity rate is a first-order hazard proxy. The rate is normalised across all active cells so the score reflects *relative* elevation rather than an absolute count, making it robust across global baselines.

**2. Gutenberg-Richter b-value anomaly**
The GR relation log₁₀(N) = a − b·M describes how frequently earthquakes of different magnitudes occur. Globally b ≈ 1.0. A locally low b-value (< 0.8) means the magnitude distribution skews towards larger events — a pattern observed before some major sequences. The b-value is estimated by maximum likelihood: `b = log₁₀(e) / (mean_M − Mc)` where Mc = 2.5 (the USGS global completeness threshold). Cells with fewer than 5 qualifying events default to neutral b = 1.0.

**3. Large-event boost (Omori-Utsu aftershock elevation)**
Any M≥6.0 within the last 30 days adds up to +0.3 to the raw score. This reflects the Omori-Utsu law: aftershock rates decay as 1/(t+c)^p, so a recent large event implies elevated near-term hazard.

**Score composition:**
```
raw  = (events_7d / max_events_7d) × (1 / max(b_value, 0.3)) + large_event_boost
risk = min(1.0, raw)
```

### Visualisation

The risk layer renders as translucent H3 hex cells on the map:
- Green (< 0.2) → low
- Yellow-orange (0.2–0.4) → low-moderate
- Orange (0.4–0.7) → moderate
- Red (≥ 0.7) → elevated

Clicking a cell shows a popup with the risk score, b-value, 30-day max magnitude, and event count. The layer is toggled independently of the event and anomaly layers.

### Caveats

This is a statistical pattern score, not a deterministic earthquake prediction. It captures where recent activity makes elevated risk plausible given known seismological relationships — useful for situational awareness and directing attention, not for civil-engineering decisions.

---

## Trade-offs and Known Limitations

| Limitation | Correct approach with more time |
|---|---|
| `FINAL` on `earthquakes_raw` is slow at high row counts | Replace with a `earthquakes_latest` AggregatingMergeTree MV (O(1) live lookups) |
| Single Redis instance is a SPOF | Redis Sentinel or Cluster for HA |
| Risk score uses raw counts without magnitude-of-completeness correction | Fit Mc locally per cell using the maximum-curvature method before b-value estimation |
| b-value estimator assumes linear GR above Mc=2.5 globally | Local Mc fitting per cell produces more accurate b-values in low-seismicity regions; dashboard warns when filtered subset has <10 qualifying buckets |
| No API authentication | Add OAuth2/JWT, scope read-only for dashboard |
| Top-places rollup MV only populated from new inserts | Historical rows populate on next ingestion cycle; a backfill via OPTIMIZE TABLE would be needed for immediate accuracy after first deploy |

---

## Expected Failure Points at Scale

The following components become bottlenecks at 10× current volume (~100k events/day) and are the expected first points of failure:

**1. `FINAL` modifier on `earthquakes_raw`**
At ~4M rows (400-day retention at current volume), `FINAL` scans and deduplicates the full partition range. At 10× volume this becomes seconds-per-query. Fix: materialise a `earthquakes_latest` AggregatingMergeTree keyed by `event_id` that holds only the most recent row per event — O(1) point lookups without `FINAL`.

**2. Redis Streams memory**
`pulse:events` is capped at 50k entries with approximate trimming. At 10× event rate the stream fills and trims faster, potentially dropping messages before slow WebSocket consumers read them. Fix: monitor `XLEN pulse:events`; reduce maxlen if lag grows, or add a dedicated consumer group per API instance.

**3. WebSocket fan-out**
The `StreamBroadcaster` fans out to all connections from a single asyncio task. At ~1k concurrent dashboard users, this task monopolises the event loop. Fix: move broadcast to a dedicated worker thread, or use Redis Pub/Sub for intra-instance fan-out and one Streams consumer per API instance.

**4. Single-process anomaly detection**
The 13 anomaly detectors run inline in the ingestion loop. At 10× event rate, the detection window grows and Redis round-trips pile up. Fix: offload detection to a separate async worker consuming from `pulse:events` rather than running synchronously in the poll cycle.

**5. ClickHouse materialized view fan-out**
Each insert to `earthquakes_raw` triggers 6 MV inserts (hourly, hourly-plate, hourly-bvalue, mag-band, depth-band, 5m-net). At very high insert rates this creates write amplification. Fix: batch inserts into larger blocks (currently per-poll-cycle) and monitor part merges with `system.parts`.

---

## Planned Next Steps

- `earthquakes_latest` AggregatingMergeTree for O(1) live lookups replacing `FINAL`
- Magnitude-of-completeness correction in the seismic risk forecast
- Prometheus `/metrics` endpoint on API and ingestion services
- API authentication (read-only JWT)
- E2E test: `docker compose up --build`, assert data flows end-to-end within 60 s
