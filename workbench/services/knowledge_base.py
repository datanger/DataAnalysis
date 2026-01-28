from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any
from uuid import uuid4

from workbench.jsonutil import dumps


class KnowledgeBaseRepo:
    """Local, offline-first knowledge base with SQLite FTS.

    Documents are stored in kb_documents and indexed into kb_documents_fts via triggers.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self,
        *,
        doc_type: str,
        title: str | None,
        content: str,
        source_url: str | None = None,
        symbol: str | None = None,
        exchange: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if not content or not str(content).strip():
            raise ValueError("content is required")

        doc_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO kb_documents(
                    doc_id, doc_type, title, content, source_url,
                    symbol, exchange, tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    str(doc_type),
                    title,
                    str(content),
                    source_url,
                    symbol,
                    exchange,
                    dumps(tags or []),
                    now,
                ),
            )

        return self.get(doc_id) or {"doc_id": doc_id}

    def get(self, doc_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT doc_id, doc_type, title, content, source_url, symbol, exchange, tags_json, created_at
            FROM kb_documents WHERE doc_id=?
            """,
            (doc_id,),
        ).fetchone()
        if not row:
            return None

        import json

        return {
            "doc_id": row[0],
            "doc_type": row[1],
            "title": row[2],
            "content": row[3],
            "source_url": row[4],
            "symbol": row[5],
            "exchange": row[6],
            "tags": json.loads(row[7]) if row[7] else [],
            "created_at": row[8],
        }

    def list(self, *, symbol: str | None = None, exchange: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = """
            SELECT doc_id, doc_type, title, source_url, symbol, exchange, tags_json, created_at
            FROM kb_documents
            WHERE 1=1
        """
        params: list[Any] = []

        if symbol:
            query += " AND symbol=?"
            params.append(symbol)
        if exchange:
            query += " AND exchange=?"
            params.append(exchange)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))

        rows = self._conn.execute(query, params).fetchall()
        import json

        return [
            {
                "doc_id": r[0],
                "doc_type": r[1],
                "title": r[2],
                "source_url": r[3],
                "symbol": r[4],
                "exchange": r[5],
                "tags": json.loads(r[6]) if r[6] else [],
                "created_at": r[7],
            }
            for r in rows
        ]

    def search(
        self,
        *,
        q: str,
        symbol: str | None = None,
        exchange: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not q or not str(q).strip():
            return []

        query = """
            SELECT d.doc_id, d.doc_type, d.title, d.source_url, d.symbol, d.exchange, d.created_at,
                   snippet(kb_documents_fts, 2, '[', ']', '...', 12) AS snippet,
                   bm25(kb_documents_fts) AS rank
            FROM kb_documents_fts
            JOIN kb_documents d ON d.doc_id = kb_documents_fts.doc_id
            WHERE kb_documents_fts MATCH ?
        """
        params: list[Any] = [q]

        if symbol:
            query += " AND d.symbol=?"
            params.append(symbol)
        if exchange:
            query += " AND d.exchange=?"
            params.append(exchange)

        query += " ORDER BY rank LIMIT ?"
        params.append(int(limit))

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "doc_id": r[0],
                "doc_type": r[1],
                "title": r[2],
                "source_url": r[3],
                "symbol": r[4],
                "exchange": r[5],
                "created_at": r[6],
                "snippet": r[7],
                "rank": float(r[8]) if r[8] is not None else None,
            }
            for r in rows
        ]

