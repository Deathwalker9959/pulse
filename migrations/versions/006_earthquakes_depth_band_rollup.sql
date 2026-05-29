-- ===========================================================================
-- 006_earthquakes_depth_band_rollup — per-hour distinct-event counts by depth band.
--
-- Revision-safe AggregatingMergeTree pattern from 004 (see its header):
-- uniqExactState(event_id) gives counts that don't inflate on USGS revision.
-- Read with uniqExactMerge(event_count_state).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_depth_band_mv_data
(
    hour              DateTime,
    depth_band        LowCardinality(String),                -- negative / shallow / intermediate / deep
    event_count_state AggregateFunction(uniqExact, String)   -- distinct event_ids per (hour, depth_band)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, depth_band)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_depth_band_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_depth_band_mv
TO earthquakes_depth_band_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    depth_band,
    uniqExactState(event_id) AS event_count_state
FROM earthquakes_raw
GROUP BY hour, depth_band;
