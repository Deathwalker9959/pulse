-- ===========================================================================
-- 008_earthquakes_network_5m_rollup — 5-minute, per-network rollup.
--
-- Serves get_network_rollups via a hybrid query: whole 5-minute buckets come
-- from this rollup, partial edge buckets from earthquakes_raw.
--
-- AggregatingMergeTree storing intermediate aggregation *states* (the "-State"
-- combinators), merged by ORDER BY key and finalized by readers with "-Merge".
-- Revision-safe like 004 (source is a ReplacingMergeTree, so revised events
-- re-enter the MV):
--   * event_count_state = uniqExactState(event_id) → EXACT distinct count.
--   * magnitude_sum_state / depth_sum_state / position_count_state are additive
--     (sumState/countState), so rollup rows and raw edge rows combine by addition
--     in a UNION. avg_x = x_sum / position_count (exact when no revision; else a
--     tiny bias). position_count = total rows incl. duplicate revisions.
--
-- NOTE: the simple runner won't alter an existing table (IF NOT EXISTS), so
-- schema changes here only take effect on a fresh ClickHouse volume.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS earthquakes_rollup_net_5m
(
    bucket               DateTime,                              -- start of the 5-minute interval (UTC)
    net                  LowCardinality(String),
    event_count_state    AggregateFunction(uniqExact, String),  -- exact distinct event_ids (dedups USGS revisions)
    magnitude_sum_state  AggregateFunction(sum, Float64),        -- additive Σ magnitude (avg numerator)
    depth_sum_state      AggregateFunction(sum, Float64),        -- additive Σ depth_km (avg numerator)
    position_count_state AggregateFunction(count)                -- additive Σ rows incl. revisions (avg denominator)
)
ENGINE = AggregatingMergeTree                                -- merges aggregate states by ORDER BY key
PARTITION BY toYYYYMMDD(bucket)                              -- daily partitions (5m granularity = many rows)
ORDER BY (bucket, net)
-- Same hot→cold→delete tiering as earthquakes_raw: 7-day hot window, 400-day life.
TTL bucket + INTERVAL 7 DAY TO VOLUME 'cold', bucket + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

-- Re-assert TTL for tables created before it was added (idempotent upgrade).
ALTER TABLE earthquakes_rollup_net_5m
    MODIFY TTL bucket + INTERVAL 7 DAY TO VOLUME 'cold',
               bucket + INTERVAL 400 DAY DELETE;

-- MV trigger: aggregate each insert into earthquakes_raw using the "-State"
-- combinators that produce the partial states stored above.
CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_rollup_net_5m_mv
TO earthquakes_rollup_net_5m
AS
SELECT
    toStartOfInterval(time, INTERVAL 5 MINUTE, 'UTC') AS bucket,
    net,
    uniqExactState(event_id) AS event_count_state,
    sumState(toFloat64(magnitude)) AS magnitude_sum_state,
    sumState(toFloat64(depth_km)) AS depth_sum_state,
    countState() AS position_count_state
FROM earthquakes_raw
GROUP BY bucket, net;
