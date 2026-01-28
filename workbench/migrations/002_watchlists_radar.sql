-- 002_watchlists_radar.sql

CREATE TABLE IF NOT EXISTS watchlist_items (
    item_id TEXT PRIMARY KEY,
    list_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (list_type, symbol, exchange)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_type_symbol ON watchlist_items(list_type, symbol, exchange);

CREATE TABLE IF NOT EXISTS radar_templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    universe_json TEXT NOT NULL,
    rules_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS radar_results (
    task_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    score_total REAL NOT NULL,
    breakdown_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    key_metrics_json TEXT NOT NULL,
    PRIMARY KEY (task_id, symbol, exchange)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_radar_results_task_score ON radar_results(task_id, score_total DESC);
