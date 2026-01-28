-- Migration: Monitor and Alerts System

-- Table for alert rules
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id TEXT PRIMARY KEY,
    portfolio_id TEXT,
    symbol TEXT,
    exchange TEXT,
    rule_type TEXT NOT NULL,
    threshold REAL NOT NULL,
    condition TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    trigger_count INTEGER NOT NULL DEFAULT 0,
    last_triggered TEXT,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_alert_rules_portfolio ON alert_rules(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_symbol ON alert_rules(symbol, exchange);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled);

-- Table for triggered alerts
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    data_json TEXT,
    FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id);
