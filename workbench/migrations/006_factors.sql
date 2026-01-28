-- Migration: Factor Engineering and Factor Library

-- Table for factor values
CREATE TABLE IF NOT EXISTS factor_values (
    factor_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    values_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (symbol, exchange) REFERENCES instruments(symbol, exchange)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_factor_values_symbol ON factor_values(symbol, exchange);
CREATE INDEX IF NOT EXISTS idx_factor_values_factor ON factor_values(factor_name);
CREATE INDEX IF NOT EXISTS idx_factor_values_date ON factor_values(trade_date);

-- Table for factor analysis results
CREATE TABLE IF NOT EXISTS factor_analysis (
    analysis_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (symbol, exchange) REFERENCES instruments(symbol, exchange)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_factor_analysis_symbol ON factor_analysis(symbol, exchange);
CREATE INDEX IF NOT EXISTS idx_factor_analysis_factor ON factor_analysis(factor_name);
CREATE INDEX IF NOT EXISTS idx_factor_analysis_date ON factor_analysis(analysis_date);
