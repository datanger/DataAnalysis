from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from workbench.jsonutil import dumps


class NotesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, *, symbol: str, exchange: str, content_md: str, references: list[dict] | None = None) -> str:
        note_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO notes(note_id, symbol, exchange, created_at, content_md, references_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (note_id, symbol, exchange, now, content_md, dumps(references or [])),
            )
        return note_id

    def list(self, *, symbol: str, exchange: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT note_id, created_at, content_md, references_json
            FROM notes
            WHERE symbol=? AND exchange=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (symbol, exchange, limit),
        ).fetchall()

        import json

        return [
            {
                "note_id": r[0],
                "created_at": r[1],
                "content_md": r[2],
                "references": json.loads(r[3]) if r[3] else [],
            }
            for r in rows
        ]

    def get(self, note_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT note_id, symbol, exchange, created_at, content_md, references_json
            FROM notes
            WHERE note_id=?
            """,
            (note_id,),
        ).fetchone()
        if not row:
            return None

        import json

        return {
            "note_id": row[0],
            "symbol": row[1],
            "exchange": row[2],
            "created_at": row[3],
            "content_md": row[4],
            "references": json.loads(row[5]) if row[5] else [],
        }
