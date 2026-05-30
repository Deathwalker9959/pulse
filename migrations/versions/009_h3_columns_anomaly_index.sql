-- ===========================================================================
-- 009 — Pre-computed H3 columns on earthquakes_raw + skip index on anomaly_events
--
-- GAP 1: geoToH3() was called at query time in get_heatmap() and get_seismic_risk().
-- ClickHouse evaluates this function for every row that passes the time filter —
-- at 400-day retention that is potentially millions of calls per query. The fix is
-- the same pattern already used for mag_band, depth_band, and geohash: store the
-- derived value at INSERT time as a MATERIALIZED column.
--
-- MATERIALIZED columns: computed by ClickHouse at insert time, stored on disk,
-- returned only when named explicitly in SELECT (invisible to SELECT *). No change
-- to the ingestion writer is needed — named-column inserts ignore MATERIALIZED
-- columns and ClickHouse derives them automatically.
--
-- GAP 3: anomaly_events ORDER BY is anomaly_id (a SHA256-derived hash — random
-- order). The get_anomaly_history() time-range path filters on event_time, but
-- without a skip index every granule in every daily partition is read. A minmax
-- skip index lets ClickHouse skip granules whose event_time range falls outside
-- the query window, matching the same pattern used on earthquakes_raw for
-- magnitude, lat/lon, net, and ingested_at.
-- ===========================================================================

-- H3 resolution-2 cell (~500 km edge) — used by get_seismic_risk() and as a
-- coarse fallback when the map requests low-resolution heatmap data.
ALTER TABLE earthquakes_raw
    ADD COLUMN IF NOT EXISTS h3r2 LowCardinality(String)
        MATERIALIZED lower(hex(geoToH3(longitude, latitude, 2)));

-- H3 resolution-3 cell (~100 km edge) — used by get_heatmap() at default resolution.
ALTER TABLE earthquakes_raw
    ADD COLUMN IF NOT EXISTS h3r3 LowCardinality(String)
        MATERIALIZED lower(hex(geoToH3(longitude, latitude, 3)));

-- Backfill existing parts so historical queries benefit immediately.
-- MATERIALIZE COLUMN is an async mutation; it completes in the background and is
-- safe to re-run (idempotent via IF NOT EXISTS guard above).
ALTER TABLE earthquakes_raw MATERIALIZE COLUMN h3r2;
ALTER TABLE earthquakes_raw MATERIALIZE COLUMN h3r3;

-- anomaly_events: add minmax skip index on event_time for time-range queries.
ALTER TABLE anomaly_events
    ADD INDEX IF NOT EXISTS idx_event_time event_time TYPE minmax GRANULARITY 4;
ALTER TABLE anomaly_events MATERIALIZE INDEX idx_event_time;
