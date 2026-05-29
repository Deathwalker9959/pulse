-- ===========================================================================
-- 005_earthquakes_mag_band_rollup — per-hour distinct-event counts by magnitude band.
--
-- Revision-safe AggregatingMergeTree pattern from 004 (see its header):
-- uniqExactState(event_id) gives counts that don't inflate when USGS revises an
-- event. Read with uniqExactMerge(event_count_state).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_mag_band_mv_data
(
    hour              DateTime,
    mag_band          LowCardinality(String),                -- micro / minor / light / moderate / strong / major / great
    event_count_state AggregateFunction(uniqExact, String)   -- distinct event_ids per (hour, mag_band)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, mag_band)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_mag_band_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_mag_band_mv
TO earthquakes_mag_band_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    mag_band,
    uniqExactState(event_id) AS event_count_state
FROM earthquakes_raw
GROUP BY hour, mag_band;
