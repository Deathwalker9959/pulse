CREATE TABLE IF NOT EXISTS anomaly_events
(
    anomaly_id       String,
    detected_at      DateTime,
    event_time       DateTime DEFAULT toDateTime(0),
    anomaly_type     LowCardinality(String),
    severity         LowCardinality(String),
    source_event_id  String,
    source_place     String,
    latitude         Float64,
    longitude        Float64,
    detail           String
)
ENGINE = ReplacingMergeTree(detected_at)
PARTITION BY toYYYYMMDD(detected_at)
ORDER BY anomaly_id
TTL detected_at + INTERVAL 30 DAY DELETE
SETTINGS storage_policy = 'hot_cold';

ALTER TABLE anomaly_events
    ADD COLUMN IF NOT EXISTS event_time DateTime DEFAULT toDateTime(0) AFTER detected_at;
