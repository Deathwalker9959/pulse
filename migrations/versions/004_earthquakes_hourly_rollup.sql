-- ===========================================================================
-- 004_earthquakes_hourly_rollup — per-hour, per-network rollup.
--
-- Serves get_top_n(net) and get_timeseries (coarse buckets) via a hybrid query:
-- whole hours come from this rollup, partial edge hours from earthquakes_raw.
--
-- REVISION-SAFE design (pattern shared by 004–006). The source earthquakes_raw
-- is a ReplacingMergeTree: a revised USGS event is re-inserted, and the MV sees
-- every insert block (before dedup). So we store:
--   * event_count_state  = uniqExactState(event_id) → EXACT distinct count,
--     immune to revisions (read with uniqExactMerge).
--   * magnitude_sum_state / row_count_state = sumState/countState → additive, so
--     a rollup row and a raw edge row combine by simple addition in a UNION.
--     avg = magnitude_sum / row_count is exact when no event is revised and
--     slightly off otherwise (rare; tiny deltas). Exact stats: earthquakes_raw FINAL.
--
-- NOTE: this naive runner re-applies migrations with IF NOT EXISTS and never
-- alters an existing table, so changing a rollup's schema takes effect only on a
-- fresh database (reset the ClickHouse volume to pick it up).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_hourly_mv_data
(
    hour                DateTime,                              -- start of the hour (UTC)
    net                 LowCardinality(String),
    event_count_state   AggregateFunction(uniqExact, String), -- distinct event_ids → revision-proof count
    magnitude_sum_state AggregateFunction(sum, Float64),       -- additive Σ magnitude (avg numerator)
    row_count_state     AggregateFunction(count)               -- additive Σ rows (avg denominator; incl. revisions)
)
ENGINE = AggregatingMergeTree                  -- merges aggregate states by ORDER BY key
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, net)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

-- Re-assert TTL for tables created before it was added (idempotent upgrade).
ALTER TABLE earthquakes_hourly_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

-- The MV is the insert trigger: every batch written to earthquakes_raw is
-- aggregated (with -State combinators) and appended to the target table above.
CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_hourly_mv
TO earthquakes_hourly_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    net,
    uniqExactState(event_id) AS event_count_state,
    sumState(toFloat64(magnitude)) AS magnitude_sum_state,
    countState() AS row_count_state
FROM earthquakes_raw
GROUP BY hour, net;
