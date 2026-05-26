-- Project PULSE — ClickHouse schema
-- Run once on startup via Docker init scripts volume

CREATE TABLE IF NOT EXISTS flights_raw
(
    icao24         LowCardinality(String),   -- ~100k unique globally; dict-encoded
    callsign       String,
    origin_country LowCardinality(String),   -- ~200 unique values
    time_position  DateTime,
    last_contact   DateTime,
    longitude      Float64,
    latitude       Float64,
    baro_altitude  Float32,
    on_ground      Bool,
    velocity       Float32,
    true_track     Float32,
    vertical_rate  Float32,
    squawk         LowCardinality(String),
    ingested_at    DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(last_contact)
PARTITION BY toYYYYMMDD(time_position)
-- SCALE: daily partitions allow partition pruning on time-range queries.
-- At 10k aircraft × 10s cadence ≈ 86M rows/day. With 7-day TTL, max ~600M rows.
-- For longer retention add a tiered storage policy to object storage (S3/GCS).
ORDER BY (icao24, time_position)
TTL time_position + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

-- Hourly rollup: maintained incrementally at insert time by ClickHouse.
-- Dashboard hourly queries hit this MV; sub-millisecond vs seconds on raw.
-- SCALE: SummingMergeTree merges lazily — reads must use sum(flight_count),
-- not count(*), to account for unmerged parts.
CREATE TABLE IF NOT EXISTS flights_hourly_mv_data
(
    hour           DateTime,
    origin_country LowCardinality(String),
    flight_count   UInt64,
    avg_altitude   Float64,
    avg_velocity   Float64,
    airborne_count UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, origin_country);

CREATE MATERIALIZED VIEW IF NOT EXISTS flights_hourly_mv
TO flights_hourly_mv_data
AS
SELECT
    toStartOfHour(time_position) AS hour,
    origin_country,
    count()                      AS flight_count,
    avg(baro_altitude)           AS avg_altitude,
    avg(velocity)                AS avg_velocity,
    countIf(on_ground = false)   AS airborne_count
FROM flights_raw
GROUP BY hour, origin_country;

-- Anomaly events with weather correlation (extension capability).
-- weather_* fields populated async after anomaly detection fires.
-- SCALE: MergeTree with 30-day TTL. Anomaly rate is low (~100s/day)
-- so this table stays small. Index on (detected_at, severity) covers
-- both dashboard alert history and analytics queries.
CREATE TABLE IF NOT EXISTS anomaly_events
(
    event_id           UUID DEFAULT generateUUIDv4(),
    detected_at        DateTime,
    anomaly_type       LowCardinality(String), -- EMERGENCY_SQUAWK | ALTITUDE_DROP | SPEED_OUTLIER | DENSITY_SPIKE
    severity           LowCardinality(String), -- INFO | WARNING | CRITICAL
    icao24             String,
    callsign           String,
    latitude           Float64,
    longitude          Float64,
    detail             String,
    -- Weather correlation (Open-Meteo, fetched async on anomaly detection)
    weather_temp_c     Nullable(Float32),
    weather_wind_kts   Nullable(Float32),
    weather_condition  Nullable(String),
    weather_visibility Nullable(Float32),
    weather_fetched_at Nullable(DateTime)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(detected_at)
ORDER BY (detected_at, severity, anomaly_type)
TTL detected_at + INTERVAL 30 DAY;
