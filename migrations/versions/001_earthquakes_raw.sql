-- ===========================================================================
-- 001_earthquakes_raw — canonical store of every ingested earthquake.
--
-- This is the source of truth the API queries (with FINAL) and every rollup
-- materialized view reads from. One row per (time, event_id); USGS revisions
-- to an event are deduplicated by the engine.
--
-- Per-column CODECs are applied: timestamps use DoubleDelta (near-monotonic →
-- tiny deltas) and the rest ZSTD. These cut on-disk size and, because scans are
-- I/O-bound, speed up the wide-window FINAL queries the API runs.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_raw
(
    event_id     String CODEC(ZSTD(1)),                     -- USGS event id (e.g. "us7000abcd")
    time         DateTime CODEC(DoubleDelta, ZSTD(1)),      -- origin time of the quake (UTC)
    updated      DateTime CODEC(DoubleDelta, ZSTD(1)),      -- last USGS revision time; ReplacingMergeTree version column
    latitude     Float64 CODEC(ZSTD(1)),
    longitude    Float64 CODEC(ZSTD(1)),
    depth_km     Float32 CODEC(ZSTD(1)),
    magnitude    Float32 CODEC(ZSTD(1)),
    mag_type     LowCardinality(String),                    -- magnitude scale (mww, ml, …); few distinct values
    place        String CODEC(ZSTD(1)),
    event_type   LowCardinality(String),                    -- "earthquake", "quarry blast", …
    status       LowCardinality(String),                    -- "automatic" / "reviewed"
    alert        LowCardinality(String),                    -- PAGER alert level: ""/green/yellow/orange/red
    tsunami      Bool,
    significance UInt16 CODEC(T64, ZSTD(1)),                 -- USGS "sig" score (impact estimate)
    net          LowCardinality(String),                    -- reporting network code
    nst          Nullable(UInt16),                          -- number of seismic stations (may be absent)
    gap          Nullable(Float32),                         -- azimuthal station gap in degrees (may be absent)
    mag_band     LowCardinality(String),                    -- precomputed magnitude band (micro…great) for fast GROUP BY
    depth_band   LowCardinality(String),                    -- precomputed depth band (shallow/intermediate/deep)
    geohash      LowCardinality(String),                    -- precision-5 geohash, for geospatial rollups
    ingested_at  DateTime DEFAULT now() CODEC(DoubleDelta, ZSTD(1))  -- when our pipeline wrote the row (freshness checks)
)
-- ReplacingMergeTree(updated): rows sharing the ORDER BY key collapse on merge,
-- keeping the one with the largest `updated` — so a revised event supersedes its
-- earlier version. Reads use FINAL to force this dedup at query time.
--
-- DEDUP-KEY ASSUMPTION: the dedup key is (time, event_id), so dedup only works if
-- an event's origin `time` is immutable across revisions. USGS origin time is
-- effectively stable, so this holds in practice; were `time` ever revised, the
-- new row would carry a different key and FINAL would keep both. We accept this
-- to retain `time` in the sort key, which the live/windowed queries rely on for
-- granule pruning (a stable-id-only key would lose that).
ENGINE = ReplacingMergeTree(updated)
PARTITION BY toYYYYMM(time)                   -- monthly partitions: cheap drops + partition pruning
ORDER BY (time, event_id)                     -- primary key / dedup key
-- Tiered retention: after 7 days move parts to the 'cold' volume, fully delete
-- after 400 days (the window the historical backfill is allowed to reach).
TTL time + INTERVAL 7 DAY TO VOLUME 'cold', time + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold', index_granularity = 8192;

-- Re-assert the TTL so re-running this migration over a table created before the
-- TTL existed updates it (CREATE ... IF NOT EXISTS never alters an existing table).
ALTER TABLE earthquakes_raw
    MODIFY TTL time + INTERVAL 7 DAY TO VOLUME 'cold',
               time + INTERVAL 400 DAY DELETE;

-- Data-skipping indexes. ClickHouse has no secondary B-tree indexes — only the
-- ORDER BY primary key plus these per-granule skip indexes. They let queries that
-- filter on non-sort-key columns skip granules instead of scanning the whole time
-- range. Each ALTER is idempotent (IF NOT EXISTS); indexes apply to newly written
-- parts (run MATERIALIZE INDEX to backfill existing parts if needed).
-- idx_magnitude: min_magnitude (live), b-value (>=2.5), magnitude-frequency filters
ALTER TABLE earthquakes_raw ADD INDEX IF NOT EXISTS idx_magnitude magnitude TYPE minmax GRANULARITY 4;
-- idx_latitude / idx_longitude: geospatial-density bbox range filters
ALTER TABLE earthquakes_raw ADD INDEX IF NOT EXISTS idx_latitude latitude TYPE minmax GRANULARITY 4;
ALTER TABLE earthquakes_raw ADD INDEX IF NOT EXISTS idx_longitude longitude TYPE minmax GRANULARITY 4;
-- idx_net: network rollup / network filter equality
ALTER TABLE earthquakes_raw ADD INDEX IF NOT EXISTS idx_net net TYPE set(100) GRANULARITY 4;
-- idx_ingested_at: ingestion-status freshness probe (ingested_at >= now() - 2 MINUTE)
ALTER TABLE earthquakes_raw ADD INDEX IF NOT EXISTS idx_ingested_at ingested_at TYPE minmax GRANULARITY 4;
