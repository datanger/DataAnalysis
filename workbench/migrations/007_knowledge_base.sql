-- Migration: Local Knowledge Base (FTS)

CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    source_url TEXT,
    symbol TEXT,
    exchange TEXT,
    tags_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_symbol ON kb_documents(symbol, exchange);
CREATE INDEX IF NOT EXISTS idx_kb_documents_type ON kb_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_kb_documents_created_at ON kb_documents(created_at);

-- Full-text index (keep in sync via triggers)
CREATE VIRTUAL TABLE IF NOT EXISTS kb_documents_fts USING fts5(
    doc_id UNINDEXED,
    title,
    content,
    tags,
    symbol,
    exchange
);

CREATE TRIGGER IF NOT EXISTS kb_documents_ai AFTER INSERT ON kb_documents BEGIN
    INSERT INTO kb_documents_fts(doc_id, title, content, tags, symbol, exchange)
    VALUES (new.doc_id, new.title, new.content, new.tags_json, new.symbol, new.exchange);
END;

CREATE TRIGGER IF NOT EXISTS kb_documents_ad AFTER DELETE ON kb_documents BEGIN
    DELETE FROM kb_documents_fts WHERE doc_id = old.doc_id;
END;

CREATE TRIGGER IF NOT EXISTS kb_documents_au AFTER UPDATE ON kb_documents BEGIN
    DELETE FROM kb_documents_fts WHERE doc_id = old.doc_id;
    INSERT INTO kb_documents_fts(doc_id, title, content, tags, symbol, exchange)
    VALUES (new.doc_id, new.title, new.content, new.tags_json, new.symbol, new.exchange);
END;

