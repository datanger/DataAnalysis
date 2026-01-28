-- Migration: Risk Rules Configuration

-- Table for risk rules configuration
CREATE TABLE IF NOT EXISTS risk_rules (
    rule_name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_risk_rules_name ON risk_rules(rule_name);
