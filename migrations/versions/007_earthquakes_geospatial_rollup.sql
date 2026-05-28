CREATE TABLE IF NOT EXISTS earthquakes_geospatial_mv_data
(
    hour    DateTime,
    geohash LowCardinality(String),
    count   UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, geohash)
TTL hour + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE earthquakes_geospatial_mv_data
    MODIFY TTL hour + INTERVAL 400 DAY DELETE;

CREATE MATERIALIZED VIEW IF NOT EXISTS earthquakes_geospatial_mv
TO earthquakes_geospatial_mv_data
AS
SELECT
    toStartOfHour(time) AS hour,
    geohash,
    count() AS count
FROM earthquakes_raw
WHERE geohash != ''
GROUP BY hour, geohash;
