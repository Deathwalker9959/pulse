-- ===========================================================================
-- 012_earthquakes_plate_enrichment — tectonic plate data + rollups.
--
-- Enriches earthquakes_raw with plate info (computed at ingest time via
-- H3 res-2 cell → plate dict lookup, built once from tectonic_plates.json).
-- Creates rollup tables grouped by (plate_name, h3_index) for efficient
-- plate-filtered queries.
--
-- Hot/cold tiering:
--   earthquakes_hourly_plate_mv_data  — hourly buckets → hot 30d, cold 30–400d, delete 400d
--   Static rollups (energy, bvalue, iet, risk, mag_band) — no datetime column;
--     hot/cold TTL moves are not possible. These are small global aggregates; kept on hot.
-- ===========================================================================

-- plate_name: LowCardinality = 52 distinct values → dictionary-encoded, ~8x smaller than String
-- boundary_distance_km: centroid of H3 res-2 cell to nearest plate boundary (km), pre-computed at startup
ALTER TABLE earthquakes_raw ADD COLUMN IF NOT EXISTS plate_name LowCardinality(String) DEFAULT '';
ALTER TABLE earthquakes_raw ADD COLUMN IF NOT EXISTS boundary_distance_km Float32 DEFAULT -1;

-- Skip index for granule pruning on plate-filtered queries (mirrors idx_net)
ALTER TABLE earthquakes_raw ADD INDEX IF NOT EXISTS idx_plate_name plate_name TYPE set(100) GRANULARITY 4;

-- ===========================================================================
-- Hourly rollup by plate + H3 (time-series aggregation, tiered hot/cold)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_hourly_plate_mv_data
(
    hour                DateTime,
    plate_name          LowCardinality(String),
    h3_index            LowCardinality(String),
    event_count_state   AggregateFunction(uniqExact, String),
    magnitude_sum_state AggregateFunction(sum, Float64),
    row_count_state     AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, plate_name, h3_index)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_hourly_plate_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_hourly_plate_mv
TO earthquakes_hourly_plate_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    plate_name,
    h3r2 AS h3_index,
    uniqExactState(event_id) AS event_count_state,
    sumState(toFloat64(magnitude)) AS magnitude_sum_state,
    countState() AS row_count_state
FROM earthquakes_raw
GROUP BY hour, plate_name, h3_index;

-- ===========================================================================
-- Static aggregates — no datetime column; live on hot disk indefinitely.
-- These are global summaries (per plate × h3 cell), not time-series.
-- Small enough to stay on hot without tiering concern.
-- ===========================================================================

-- Magnitude band distribution per plate
CREATE TABLE IF NOT EXISTS earthquakes_mag_band_plate_mv_data
(
    mag_band            LowCardinality(String),
    plate_name          LowCardinality(String),
    h3_index            LowCardinality(String),
    event_count_state   AggregateFunction(uniqExact, String),
    row_count_state     AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
ORDER BY (plate_name, h3_index, mag_band);

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_mag_band_plate_mv
TO earthquakes_mag_band_plate_mv_data
AS
SELECT
    mag_band,
    plate_name,
    h3r2 AS h3_index,
    uniqExactState(event_id) AS event_count_state,
    countState() AS row_count_state
FROM earthquakes_raw
WHERE mag_band != ''
GROUP BY mag_band, plate_name, h3_index;

-- Seismic energy per plate (for energy timeseries queries)
CREATE TABLE IF NOT EXISTS earthquakes_energy_plate_mv_data
(
    plate_name          LowCardinality(String),
    h3_index            LowCardinality(String),
    magnitude_sum_state AggregateFunction(sum, Float64),
    count_state         AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
ORDER BY (plate_name, h3_index);

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_energy_plate_mv
TO earthquakes_energy_plate_mv_data
AS
SELECT
    plate_name,
    h3r2 AS h3_index,
    sumState(toFloat64(magnitude)) AS magnitude_sum_state,
    countState() AS count_state
FROM earthquakes_raw
GROUP BY plate_name, h3_index;

-- B-value aggregate per plate (M >= 2.5, Gutenberg-Richter)
CREATE TABLE IF NOT EXISTS earthquakes_bvalue_plate_mv_data
(
    plate_name          LowCardinality(String),
    h3_index            LowCardinality(String),
    mag_sum_state       AggregateFunction(sum, Float64),
    count_state         AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
ORDER BY (plate_name, h3_index);

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_bvalue_plate_mv
TO earthquakes_bvalue_plate_mv_data
AS
SELECT
    plate_name,
    h3r2 AS h3_index,
    sumState(toFloat64(magnitude)) AS mag_sum_state,
    countState() AS count_state
FROM earthquakes_raw
WHERE magnitude >= 2.5
GROUP BY plate_name, h3_index;

-- Seismic risk aggregate per plate (M >= 2.0)
CREATE TABLE IF NOT EXISTS earthquakes_risk_plate_mv_data
(
    plate_name          LowCardinality(String),
    h3_index            LowCardinality(String),
    event_count_state   AggregateFunction(uniqExact, String),
    events_7d_state     AggregateFunction(count),
    max_m6_30d_state    AggregateFunction(max, Float64),
    mag_sum_25_state    AggregateFunction(sum, Float64),
    count_25_state      AggregateFunction(count),
    max_mag_state       AggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree
ORDER BY (plate_name, h3_index);

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_risk_plate_mv
TO earthquakes_risk_plate_mv_data
AS
SELECT
    plate_name,
    h3r2 AS h3_index,
    uniqExactState(event_id) AS event_count_state,
    countState() AS events_7d_state,
    maxState(CAST(magnitude AS Float64)) AS max_m6_30d_state,
    sumState(CAST(magnitude AS Float64)) AS mag_sum_25_state,
    countState() AS count_25_state,
    maxState(CAST(magnitude AS Float64)) AS max_mag_state
FROM earthquakes_raw
WHERE magnitude >= 2.0
GROUP BY plate_name, h3_index;
