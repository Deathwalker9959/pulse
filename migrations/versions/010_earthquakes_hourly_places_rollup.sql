-- ===========================================================================
-- 010 — Per-hour, per-place rollup.
--
-- GAP 2: get_top_n("place") had no materialized view — every top-places request
-- did a full earthquakes_raw FINAL scan with GROUP BY place. place is a free-text
-- string with thousands of distinct values (unbounded cardinality), so it cannot
-- use LowCardinality (degrades past ~10k distinct values) and cannot leverage the
-- hourly-network rollup. This migration adds a dedicated per-hour per-place MV
-- following the same AggregatingMergeTree + uniqExactState pattern as the network
-- rollup (004), making top-places queries use the same efficient hybrid path.
--
-- REVISION-SAFE: uniqExactState(event_id) is immune to USGS event revisions —
-- re-inserting the same event_id into the MV state does not double-count it.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_hourly_places_mv_data
(
    hour              DateTime,
    place             String CODEC(ZSTD(1)),              -- unbounded cardinality: String, not LowCardinality
    event_count_state AggregateFunction(uniqExact, String) -- distinct event_ids per (hour, place)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, place)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

-- Re-assert TTL idempotently (matches pattern in 004–006).
ALTER TABLE earthquakes_hourly_places_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

-- Materialized view: every insert to earthquakes_raw aggregates into the target.
CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_hourly_places_mv
TO earthquakes_hourly_places_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    place,
    uniqExactState(event_id) AS event_count_state
FROM earthquakes_raw
GROUP BY hour, place;
