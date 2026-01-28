-- 003_portfolio_accounts.sql

CREATE TABLE IF NOT EXISTS portfolio_accounts (
    portfolio_id TEXT PRIMARY KEY,
    cash REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_accounts_updated ON portfolio_accounts(updated_at);
