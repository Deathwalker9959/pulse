CREATE TABLE IF NOT EXISTS earthquakes_raw
(
    event_id     LowCardinality(String),
    time         DateTime,
    updated      DateTime,
    latitude     Float64,
    longitude    Float64,
    depth_km     Float32,
    magnitude    Float32,
    mag_type     LowCardinality(String),
    place        String,
    event_type   LowCardinality(String),
    status       LowCardinality(String),
    alert        LowCardinality(String),
    tsunami      Bool,
    significance UInt16,
    net          LowCardinality(String),
    nst          Nullable(UInt16),
    gap          Nullable(Float32),
    mag_band     LowCardinality(String),
    depth_band   LowCardinality(String),
    geohash      LowCardinality(String),
    ingested_at  DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated)
PARTITION BY toYYYYMMDD(time)
ORDER BY (event_id, time)
TTL time + INTERVAL 7 DAY TO VOLUME 'cold', time + INTERVAL 400 DAY DELETE
SETTINGS storage_policy = 'hot_cold', index_granularity = 8192;

ALTER TABLE earthquakes_raw
    MODIFY TTL time + INTERVAL 7 DAY TO VOLUME 'cold',
               time + INTERVAL 400 DAY DELETE;
