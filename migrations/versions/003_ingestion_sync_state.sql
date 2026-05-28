CREATE TABLE IF NOT EXISTS ingestion_sync_state
(
    key        LowCardinality(String),
    value      String,
    updated_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY key;
