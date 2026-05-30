-- ===========================================================================
-- 011_earthquakes_hourly_bvalue_rollup — per-hour global b-value rollup.
--
-- Serves get_b_value_history(bucket="1h") efficiently for large-scale queries.
-- Stores magnitude aggregate states for events M >= 2.5 (b-value calculation).
--
-- Design: mirrors 004 (revision-safe with -State combinators).
-- Global (no network dimension) since b-value is typically calculated over
-- all networks combined for the time window.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_hourly_bvalue_mv_data
(
    hour                DateTime,                              -- start of the hour (UTC)
    magnitude_sum_state AggregateFunction(sum, Float64),       -- Σ magnitude (b-value numerator)
    row_count_state     AggregateFunction(count)               -- Σ rows (b-value denominator)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY hour
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_hourly_bvalue_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_hourly_bvalue_mv
TO earthquakes_hourly_bvalue_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    sumState(toFloat64(magnitude)) AS magnitude_sum_state,
    countState() AS row_count_state
FROM earthquakes_raw
WHERE magnitude >= 2.5
GROUP BY hour;
