CREATE TABLE IF NOT EXISTS earthquakes_rollup_net_5m
(
    bucket               DateTime,
    net                  LowCardinality(String),
    event_count_state    AggregateFunction(uniq, String),
    avg_magnitude_state  AggregateFunction(avg, Float64),
    avg_depth_state      AggregateFunction(avg, Float64),
    position_count_state AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(bucket)
ORDER BY (bucket, net)
TTL bucket + INTERVAL 7 DAY TO VOLUME 'cold', bucket + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_rollup_net_5m
    MODIFY TTL bucket + INTERVAL 7 DAY TO VOLUME 'cold',
               bucket + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_rollup_net_5m_mv
TO earthquakes_rollup_net_5m
AS
SELECT
    toStartOfInterval(time, INTERVAL 5 MINUTE, 'UTC') AS bucket,
    net,
    uniqState(event_id) AS event_count_state,
    avgState(toFloat64(magnitude)) AS avg_magnitude_state,
    avgState(toFloat64(depth_km)) AS avg_depth_state,
    countState() AS position_count_state
FROM earthquakes_raw
GROUP BY bucket, net;
