from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable

from workbench.providers.base import InstrumentRow


class InstrumentsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert_many(self, rows: Iterable[InstrumentRow]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        n = 0
        with self._conn:
            for r in rows:
                self._conn.execute(
                    """
                    INSERT INTO instruments(symbol, exchange, market, name, industry, is_active, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(symbol, exchange) DO UPDATE SET
                        market=excluded.market,
                        name=excluded.name,
                        industry=excluded.industry,
                        is_active=excluded.is_active,
                        updated_at=excluded.updated_at
                    """,
                    (r.symbol, r.exchange, r.market, r.name, r.industry, now),
                )
                n += 1
        return n

    def search(self, q: str, limit: int = 50) -> list[dict]:
        like = f"%{q}%"
        rows = self._conn.execute(
            """
            SELECT symbol, exchange, market, name, industry
            FROM instruments
            WHERE symbol LIKE ? OR name LIKE ?
            ORDER BY symbol
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()

        return [
            {
                "symbol": row[0],
                "exchange": row[1],
                "market": row[2],
                "name": row[3],
                "industry": row[4],
            }
            for row in rows
        ]
