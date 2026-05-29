-- ===========================================================================
-- 002_anomaly_events — detected anomalies (alerts) emitted by the detectors.
--
-- Both the live pipeline and the historical backfill write here. The same
-- (event, type) anomaly can be re-detected; the engine keeps only the latest.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS anomaly_events
(
    anomaly_id       String,                          -- deterministic hash of (source_event_id, type); the dedup key
    detected_at      DateTime,                         -- when detection ran; ReplacingMergeTree version column
    event_time       DateTime DEFAULT toDateTime(0),   -- origin time of the source quake (0 = unknown, pre-backfill rows)
    anomaly_type     LowCardinality(String),           -- MAGNITUDE_SPIKE, SWARM_DETECTION, …
    severity         LowCardinality(String),           -- INFO / WARNING / CRITICAL
    source_event_id  String,                           -- earthquakes_raw.event_id that triggered it
    source_place     String,
    latitude         Float64,
    longitude        Float64,
    detail           String                            -- human-readable explanation shown in the UI
)
-- ReplacingMergeTree(detected_at): re-detecting the same anomaly_id collapses to
-- the most recently detected row. Reads dedup with FINAL / argMax.
ENGINE = ReplacingMergeTree(detected_at)
PARTITION BY toYYYYMMDD(detected_at)                  -- daily partitions (short 30-day retention)
ORDER BY anomaly_id
TTL detected_at + INTERVAL 30 DAY DELETE              -- alerts are short-lived; keep 30 days
SETTINGS storage_policy = 'hot_cold';

-- event_time was added after the table first shipped; this makes the migration
-- idempotent and upgrades older deployments in place (default 0 for old rows,
-- so history queries can fall back to the source event's time when needed).
ALTER TABLE anomaly_events
    ADD COLUMN IF NOT EXISTS event_time DateTime DEFAULT toDateTime(0) AFTER detected_at;
