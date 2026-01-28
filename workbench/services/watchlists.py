from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from workbench.jsonutil import dumps


class WatchlistRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_items(self, list_type: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT item_id, list_type, symbol, exchange, tags_json, created_at
            FROM watchlist_items
            WHERE list_type=?
            ORDER BY created_at DESC
            """,
            (list_type,),
        ).fetchall()

        import json

        return [
            {
                "item_id": r[0],
                "list_type": r[1],
                "symbol": r[2],
                "exchange": r[3],
                "tags": json.loads(r[4]) if r[4] else [],
                "created_at": r[5],
            }
            for r in rows
        ]

    def add_item(self, list_type: str, symbol: str, exchange: str, tags: list[str] | None = None) -> str:
        item_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        tags_json = dumps(tags or [])
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO watchlist_items(item_id, list_type, symbol, exchange, tags_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(list_type, symbol, exchange) DO UPDATE SET
                    tags_json=excluded.tags_json
                """,
                (item_id, list_type, symbol, exchange, tags_json, now),
            )
        return item_id

    def delete_item(self, item_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM watchlist_items WHERE item_id=?", (item_id,))
