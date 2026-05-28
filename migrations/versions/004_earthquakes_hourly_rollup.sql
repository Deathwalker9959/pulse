CREATE TABLE IF NOT EXISTS earthquakes_hourly_mv_data
(
    hour          DateTime,
    net           LowCardinality(String),
    event_count   UInt64,
    magnitude_sum Float64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, net)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_hourly_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_hourly_mv
TO earthquakes_hourly_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    net,
    count() AS event_count,
    sum(toFloat64(magnitude)) AS magnitude_sum
FROM earthquakes_raw
GROUP BY hour, net;
