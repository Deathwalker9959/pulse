-- ===========================================================================
-- 003_ingestion_sync_state — tiny key/value store for pipeline bookkeeping.
--
-- The historical backfill stores its high-water mark here (key
-- "last_synced_to") so it resumes where it left off after a restart.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS ingestion_sync_state
(
    key        LowCardinality(String),       -- bookkeeping key, e.g. "last_synced_to"
    value      String,                        -- value as text (e.g. an ISO date)
    updated_at DateTime DEFAULT now()         -- write time; ReplacingMergeTree version column
)
-- ReplacingMergeTree(updated_at) + ORDER BY key: at most one current row per key,
-- latest write wins (read with FINAL).
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY key;
