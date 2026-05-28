CREATE TABLE IF NOT EXISTS earthquakes_mag_band_mv_data
(
    hour        DateTime,
    mag_band    LowCardinality(String),
    event_count UInt64
)
ENGINE = SummingMergeTree
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
    count() AS event_count
FROM earthquakes_raw
GROUP BY hour, mag_band;
