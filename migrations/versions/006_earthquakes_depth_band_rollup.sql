CREATE TABLE IF NOT EXISTS earthquakes_depth_band_mv_data
(
    hour        DateTime,
    depth_band  LowCardinality(String),
    event_count UInt64
)
ENGINE = SummingMergeTree
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
    count() AS event_count
FROM earthquakes_raw
GROUP BY hour, depth_band;
