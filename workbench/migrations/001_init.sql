-- 001_init.sql

-- Core migrations table is created by the migrator.

CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market TEXT NOT NULL,
    name TEXT,
    industry TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS bars_daily (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    adj TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    amount REAL,
    pre_close REAL,
    source TEXT NOT NULL,
    quality TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange, trade_date, adj)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_bars_daily_symbol_date ON bars_daily(symbol, exchange, trade_date);

CREATE TABLE IF NOT EXISTS fundamental_snapshot (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    report_period TEXT NOT NULL,
    report_type TEXT NOT NULL,
    revenue REAL,
    net_profit REAL,
    roe REAL,
    gross_margin REAL,
    debt_ratio REAL,
    pe_ttm REAL,
    pb REAL,
    ps_ttm REAL,
    mv REAL,
    source TEXT NOT NULL,
    quality TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange, report_period, report_type)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS capital_flow_daily (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    net_inflow REAL,
    main_inflow REAL,
    northbound_net REAL,
    source TEXT NOT NULL,
    quality TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange, trade_date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS news_items (
    news_id TEXT PRIMARY KEY,
    symbol TEXT,
    exchange TEXT,
    published_at TEXT,
    title TEXT,
    summary TEXT,
    source_site TEXT,
    url TEXT,
    keywords_json TEXT,
    saved INTEGER NOT NULL DEFAULT 0,
    quality TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_symbol_time ON news_items(symbol, exchange, published_at);

CREATE TABLE IF NOT EXISTS score_snapshots (
    score_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    score_total REAL NOT NULL,
    breakdown_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_score_symbol_date ON score_snapshots(symbol, exchange, trade_date);

CREATE TABLE IF NOT EXISTS trade_plans (
    plan_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    created_at TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    plan_json TEXT NOT NULL,
    based_on_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_symbol_time ON trade_plans(symbol, exchange, created_at);

CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    created_at TEXT NOT NULL,
    content_md TEXT NOT NULL,
    references_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_symbol_time ON notes(symbol, exchange, created_at);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    portfolio_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    qty INTEGER NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, symbol, exchange)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS order_drafts (
    draft_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    price REAL,
    qty INTEGER NOT NULL,
    notes TEXT,
    origin TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_drafts_portfolio ON order_drafts(portfolio_id, created_at);

CREATE TABLE IF NOT EXISTS risk_check_results (
    riskcheck_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    items_json TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    input_draft_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sim_orders (
    order_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    draft_ids_json TEXT NOT NULL,
    filled_qty INTEGER NOT NULL,
    avg_fill_price REAL,
    fee_total REAL NOT NULL,
    slippage_total REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_orders_portfolio ON sim_orders(portfolio_id, created_at);

CREATE TABLE IF NOT EXISTS sim_trades (
    trade_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    filled_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    fill_price REAL NOT NULL,
    fill_qty INTEGER NOT NULL,
    fee REAL NOT NULL,
    slippage REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_trades_portfolio ON sim_trades(portfolio_id, filled_at);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    output_snapshot_json TEXT NOT NULL,
    ruleset_version TEXT,
    data_version TEXT,
    model_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id, ts);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_time ON tasks(status, created_at);
